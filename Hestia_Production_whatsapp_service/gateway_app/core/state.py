# gateway_app/core/state.py
"""
Simple conversation state machine for the Hestia WhatsApp gateway.

This module is called from the webhook layer:

    session = state.load_session(wa_contact_id)
    actions, new_session = state.handle_incoming_text(...)
    state.save_session(wa_contact_id, new_session)

Design notes
------------
- For now, sessions are stored in an in-memory dict (_SESSIONS).
  This keeps the code simple and works both locally and on Render.
  Later you can swap this for a DB-backed implementation.
- Outgoing actions are small dicts, currently only:
      {"type": "text", "text": "...", "preview_url": False}
- States used:
    GH_S0            -> conversación "normal"
    GH_S0i           -> inicio de conversación / saludo
    GH_TICKET_DRAFT  -> editando borrador de ticket
    GH_TICKET_CONFIRM-> esperando confirmación SI/NO
    GH_FAQ           -> flujo de preguntas frecuentes
    GH_HANDOFF       -> derivado a recepción / humano
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from gateway_app.core.models import NLUResult
from gateway_app.core.timefmt import utcnow
from gateway_app.services import faq_llm, guest_llm, notify



logger = logging.getLogger(__name__)


# IDs para tu backend de tickets (ajusta según tu setup)
ORG_ID_DEFAULT = int(os.getenv("ORG_ID_DEFAULT", "2"))
HOTEL_ID_DEFAULT = int(os.getenv("HOTEL_ID_DEFAULT", "1"))

# Import real ticket creator if available; otherwise fall back to a stub.
try:
    from gateway_app.services.tickets import create_ticket
except Exception:
    def create_ticket(payload, initial_status: str = "PENDIENTE_APROBACION"):
        logger.error(
            "create_ticket() stub called. Debes importar aquí tu función real "
            "de creación de tickets para que se escriban en la BD.",
            extra={"payload": payload, "initial_status": initial_status},
        )
        return None


# ---------------------------------------------------------------------------
# Conversation state constants
# ---------------------------------------------------------------------------

STATE_NEW = "GH_S0"
STATE_INIT = "GH_S0_INIT"  # Renamed from GH_S0i to avoid conflict
STATE_GUEST_IDENTIFY = "GH_IDENTIFY"  # NEW: Request name + room
STATE_TICKET_DRAFT = "GH_TICKET_DRAFT"
STATE_TICKET_CONFIRM = "GH_TICKET_CONFIRM"
STATE_FAQ = "GH_FAQ"
STATE_HANDOFF = "GH_HANDOFF"

# Session TTL configuration
SESSION_TTL_SECONDS = 15 * 60  # 15 minutes


# In-memory session store: wa_id -> session dict
_SESSIONS: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Public API used by webhook/routes.py
# ---------------------------------------------------------------------------


def load_session(wa_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve the session for a WhatsApp contact id (wa_id).
    Validates TTL and returns None if session expired.

    Returns:
        dict with session data, or None if not found/expired.
    """
    session = _SESSIONS.get(wa_id)

    if not session:
        return None

    # Validate TTL (15 minutes)
    last_message = session.get("last_message_at")
    if last_message:
        try:
            from datetime import datetime
            last_dt = datetime.fromisoformat(last_message)
            elapsed = (utcnow() - last_dt).total_seconds()

            if elapsed > SESSION_TTL_SECONDS:
                # Session expired, delete it
                _SESSIONS.pop(wa_id, None)
                logger.info(
                    "[SESSION] Session expired due to TTL",
                    extra={
                        "wa_id": wa_id,
                        "elapsed_seconds": int(elapsed),
                        "ttl_seconds": SESSION_TTL_SECONDS
                    }
                )
                return None
        except Exception as e:
            logger.warning(
                "[SESSION] TTL validation failed",
                extra={"wa_id": wa_id, "error": str(e)}
            )

    return session


def save_session(wa_id: str, session: Optional[Dict[str, Any]]) -> None:
    """
    Persist the session in the in-memory store.

    If session is None, the existing one (if any) is removed.
    """
    if session is None:
        _SESSIONS.pop(wa_id, None)
        return

    session.setdefault("wa_id", wa_id)
    session["updated_at"] = utcnow().isoformat()
    _SESSIONS[wa_id] = session


def handle_incoming_text(
    *,
    wa_id: str,
    guest_phone: str,
    guest_name: Optional[str],
    text: str,
    session: Optional[Dict[str, Any]],
    timestamp,
    raw_payload: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Main state machine entry point.

    Args:
        wa_id: WhatsApp contact id (value from 'contacts[0].wa_id').
        guest_phone: Número de WhatsApp (messages[0].from).
        guest_name: Nombre del contacto si está disponible.
        text: Mensaje del huésped (ya transcrito si era audio).
        session: Sesión previa (dict) o None.
        timestamp: datetime de la recepción (ya parseado en routes.py).
        raw_payload: payload completo para debug / futuros usos.

    Returns:
        (outgoing_actions, new_session)
    """
    msg = (text or "").strip()
    actions: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Ensure we have a session object
    # ------------------------------------------------------------------
    if session is None:
        session = _new_session(
            wa_id=wa_id,
            guest_phone=guest_phone,
            guest_name=guest_name,
            timestamp=timestamp,
        )
        new_conversation = True
    else:
        new_conversation = False
        session.setdefault("wa_id", wa_id)
        session.setdefault("phone", guest_phone)
        session.setdefault("data", {})

    session["guest_name"] = guest_name or session.get("guest_name")
    session["last_message_at"] = utcnow().isoformat()
    state = session.get("state") or STATE_INIT

    logger.debug(
        "[STATE] handle_incoming_text start",
        extra={"wa_id": wa_id, "state": state, "text": msg},
    )

    # If no text after greeting (e.g., pure audio that failed), nothing else to do
    if not msg:
        # Only show greeting if there's no message
        if new_conversation:
            actions.append(_text_action(_initial_greeting(session)))
        return actions, session
    
    # ------------------------------------------------------------------
    # Global cancellation guardrail (independent of NLU)
    # ------------------------------------------------------------------
    if _looks_like_global_cancel(msg):
        _clear_ticket_draft(session)
        session["state"] = STATE_NEW
        actions.append(
            _text_action(
                "He cancelado la solicitud actual. Si necesitas algo más para tu habitación, "
                "solo dime por aquí."
            )
        )
        logger.debug(
            "[STATE] global cancel",
            extra={"wa_id": wa_id, "state": session.get("state"), "text": msg},
        )
        return actions, session
    

    # ------------------------------------------------------------------
    # Ticket confirmation: handle explicit SI / NO first
    # ------------------------------------------------------------------
    if state == STATE_TICKET_CONFIRM:
        handled, extra_actions = _handle_ticket_confirmation_yes_no(msg, session)
        if handled:
            actions.extend(extra_actions)
            logger.debug(
                "[STATE] after ticket confirm",
                extra={"wa_id": wa_id, "state": session.get("state")},
            )
            return actions, session
        # If not handled as SI/NO, fall through and treat as a normal message

    # ------------------------------------------------------------------
    # Simple commands to reset / show menu
    # ------------------------------------------------------------------
    if msg.lower() in {"menu", "inicio", "start"}:
        session["state"] = STATE_INIT
        actions.append(_text_action(_menu_message(session)))
        return actions, session

    # ------------------------------------------------------------------
    # NLU analysis
    # ------------------------------------------------------------------
    logger.info(
        "[FLOW] 🔄 STEP 2: Running NLU analysis",
        extra={
            "wa_id": wa_id,
            "state": state,
            "user_message": msg,
            "location": "gateway_app/core/state.py"
        }
    )
    nlu_raw = guest_llm.analyze_guest_message(msg, session=session, state=state)
    nlu = NLUResult.from_dict(nlu_raw) if nlu_raw else NLUResult()

    logger.info(
        "[FLOW] 📊 NLU result received",
        extra={
            "wa_id": wa_id,
            "nlu": nlu.to_dict(),
            "intent": nlu.intent,
            "location": "gateway_app/core/state.py"
        },
    )

    # ------------------------------------------------------------------
    # Handle identity validation state BEFORE normal intent routing
    # ------------------------------------------------------------------
    if state == STATE_GUEST_IDENTIFY:
        handled, extra_actions = _handle_guest_identify(msg, nlu, session)
        if handled:
            actions.extend(extra_actions)
            logger.debug(
                "[STATE] after guest identify",
                extra={"wa_id": wa_id, "state": session.get("state")},
            )
            return actions, session

    # ------------------------------------------------------------------
    # Route based on intent / flags
    # ------------------------------------------------------------------

    # Help / capabilities
    if nlu.intent == "help" or nlu.is_help:
        logger.info(
            "[FLOW] ✅ DECISION: Intent=HELP → Show help message",
            extra={
                "decision": "INTENT_HELP",
                "wa_id": wa_id,
                "user_message": msg,
                "location": "gateway_app/core/state.py"
            }
        )
        actions.append(_text_action(_help_message()))
        session["state"] = STATE_INIT
        return actions, session

    # Explicit human handoff
    if nlu.intent == "handoff_request" or nlu.wants_handoff:
        logger.info(
            "[FLOW] ✅ DECISION: Intent=HANDOFF → Transfer to human",
            extra={
                "decision": "INTENT_HANDOFF",
                "wa_id": wa_id,
                "user_message": msg,
                "location": "gateway_app/core/state.py"
            }
        )
        session["state"] = STATE_HANDOFF
        actions.append(
            _text_action(
                "De acuerdo, te pongo en contacto con recepción humana. "
                "Un momento por favor."
            )
        )
        notify.notify_internal(
            "handoff_request",
            {
                "wa_id": wa_id,
                "phone": guest_phone,
                "guest_name": session.get("guest_name"),
                "last_message": msg,
            },
        )
        return actions, session

    # Cancel current request
    if nlu.intent == "cancel" or nlu.is_cancel:
        logger.info(
            "[FLOW] ✅ DECISION: Intent=CANCEL → Clear ticket draft",
            extra={
                "decision": "INTENT_CANCEL",
                "wa_id": wa_id,
                "user_message": msg,
                "location": "gateway_app/core/state.py"
            }
        )
        _clear_ticket_draft(session)
        session["state"] = STATE_NEW
        actions.append(
            _text_action(
                "He cancelado tu solicitud. Si necesitas algo más, "
                "envíame un nuevo mensaje."
            )
        )
        return actions, session

    # Ticket / request for service
    if nlu.intent == "ticket_request":
        logger.info(
            "[FLOW] ✅ DECISION: Intent=TICKET_REQUEST → Validate identity first",
            extra={
                "decision": "INTENT_TICKET_REQUEST",
                "wa_id": wa_id,
                "user_message": msg,
                "area": nlu.area,
                "room": nlu.room,
                "detail": nlu.detail,
                "location": "gateway_app/core/state.py"
            }
        )

        # ⭐ Validate identity BEFORE creating ticket
        if not _has_guest_identity(session, nlu):
            actions.extend(_request_guest_identity(nlu, session))
            return actions, session

        # If we have identity, create combined confirmation
        actions.extend(_create_combined_confirmation_direct(nlu, session))
        return actions, session

    # Smalltalk / general chat (thank you, etc.)
    if nlu.intent == "general_chat" or nlu.is_smalltalk:
        logger.info(
            "[FLOW] ✅ DECISION: Intent=GENERAL_CHAT → Respond with smalltalk",
            extra={
                "decision": "INTENT_GENERAL_CHAT",
                "wa_id": wa_id,
                "user_message": msg,
                "new_conversation": new_conversation,
                "location": "gateway_app/core/state.py"
            }
        )
        # Si es la primera vez que hablamos en esta sesión y ya mandamos
        # el saludo inicial, NO mandamos otro mensaje para evitar el doble texto.
        if new_conversation:
            if state in {STATE_INIT, STATE_FAQ}:
                session["state"] = STATE_NEW
            return actions, session

        # En conversaciones ya iniciadas, sí respondemos smalltalk normalmente.
        actions.append(_text_action(_smalltalk_reply(msg)))
        if state in {STATE_INIT, STATE_FAQ}:
            session["state"] = STATE_NEW
        return actions, session

    # ------------------------------------------------------------------
    # Not understood or unclassified: try FAQ as FALLBACK (LAST RESORT)
    # ------------------------------------------------------------------
    if nlu.intent == "not_understood" or nlu.intent is None:
        logger.info(
            "[FLOW] 🔄 STEP 3: Intent=NOT_UNDERSTOOD → Try FAQ as fallback",
            extra={
                "decision": "INTENT_NOT_UNDERSTOOD_FAQ_FALLBACK",
                "wa_id": wa_id,
                "user_message": msg,
                "location": "gateway_app/core/state.py"
            }
        )

        # Intenta FAQ antes del mensaje genérico de "no entendí"
        faq_answer = faq_llm.answer_faq(msg)

        if faq_answer:
            logger.info(
                "[FLOW] ✅ DECISION: FAQ fallback found answer → TERMINATE",
                extra={
                    "decision": "FAQ_FALLBACK_HIT",
                    "wa_id": wa_id,
                    "user_message": msg,
                    "answer_preview": faq_answer[:100],
                    "location": "gateway_app/core/state.py"
                }
            )
            session["state"] = STATE_FAQ
            actions.append(_text_action(faq_answer))
            actions.append(
                _text_action("¿Puedo ayudarte con algo más durante tu estadía?")
            )
            return actions, session

        # Si ni siquiera FAQ funciona, mensaje genérico de ayuda
        logger.info(
            "[FLOW] ⚠️ DECISION: FAQ fallback missed → Show help message",
            extra={
                "decision": "FAQ_FALLBACK_MISS_DEFAULT",
                "wa_id": wa_id,
                "user_message": msg,
                "location": "gateway_app/core/state.py"
            }
        )
        actions.append(
            _text_action(
                "No estoy seguro de haber entendido bien. Puedo ayudarte a:\n\n"
                "• Crear solicitudes de mantenimiento, housekeeping o room service.\n"
                "• Responder preguntas frecuentes sobre el hotel.\n"
                "• Ponerte en contacto con recepción.\n\n"
                "¿Qué necesitas?"
            )
        )
        session["state"] = STATE_INIT
        return actions, session

    # ------------------------------------------------------------------
    # Safety net (unexpected intent value)
    # ------------------------------------------------------------------
    actions.append(
        _text_action(
            "Gracias por tu mensaje. Si quieres, puedes contarme si "
            "necesitas reportar un problema, pedir algo a la habitación "
            "o hacer una pregunta sobre el hotel."
        )
    )
    return actions, session


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


def _new_session(
    *,
    wa_id: str,
    guest_phone: str,
    guest_name: Optional[str],
    timestamp,
) -> Dict[str, Any]:
    now_iso = utcnow().isoformat()
    session: Dict[str, Any] = {
        "wa_id": wa_id,
        "phone": guest_phone,
        "guest_name": guest_name or None,
        "state": STATE_INIT,
        "language": None,
        "room": None,
        "created_at": now_iso,
        "updated_at": now_iso,
        "last_message_at": now_iso,
        "data": {},
    }
    logger.info(
        "[STATE] New guest session created",
        extra={"wa_id": wa_id, "phone": guest_phone},
    )
    return session


def _get_ticket_draft(session: Dict[str, Any]) -> Dict[str, Any]:
    data = session.setdefault("data", {})
    draft = data.get("ticket_draft")
    if draft is None:
        draft = {
            "area": None,
            "priority": None,
            "room": None,
            "detail": None,
        }
        data["ticket_draft"] = draft
    return draft


def _clear_ticket_draft(session: Dict[str, Any]) -> None:
    data = session.setdefault("data", {})
    if "ticket_draft" in data:
        del data["ticket_draft"]


# ---------------------------------------------------------------------------
# Conversation fragments
# ---------------------------------------------------------------------------


def _text_action(text: str, preview_url: bool = False) -> Dict[str, Any]:
    return {
        "type": "text",
        "text": text,
        "preview_url": preview_url,
    }


def _initial_greeting(session: Dict[str, Any]) -> str:
    name = session.get("guest_name")
    if name:
        prefix = f"Hola {name}, "
    else:
        prefix = "Hola, "
    return (
        prefix
        + "¡Hola! Te damos la bienvenida a nuestro servicio de asistencia digital.\n"
          "Para poder ayudarte rápidamente por favor indícame tu número de habitación y cuál es tu consulta o solicitud."
    )


def _menu_message(session: Dict[str, Any]) -> str:
    return (
        "Menú de ayuda Hestia:\n"
        "1️⃣ Reportar un problema en la habitación (ej: no funciona el aire, falta limpieza).\n"
        "2️⃣ Pedir algo al hotel (toallas, almohadas, amenities, room service).\n"
        "3️⃣ Preguntar información (desayuno, wifi, horarios, etc.).\n\n"
        "Cuéntame brevemente qué necesitas y yo te ayudo."
    )


def _help_message() -> str:
    return (
        "Puedo ayudarte con:\n"
        "• Reportar problemas en tu habitación (aire, ducha, luz, limpieza, etc.).\n"
        "• Pedir toallas, almohadas u otros artículos de housekeeping.\n"
        "• Pedir comida o bebidas a la habitación.\n"
        "• Responder dudas típicas: horario de desayuno, wifi, check-in / check-out.\n\n"
        "Escríbeme en una frase qué necesitas y me encargo del resto."
    )


def _smalltalk_reply(original: str) -> str:
    lower = original.lower()
    if "gracia" in lower:
        return "Con gusto, estoy aquí para ayudarte durante tu estadía. ¿Algo más?"
    if "todo bien" in lower or "todo ok" in lower or "estoy bien" in lower:
        return "Perfecto, me alegra saberlo. Si necesitas algo más, solo escribe por aquí."
    return "Entendido. Cualquier cosa que necesites, solo escríbeme por aquí."



# ---------------------------------------------------------------------------
# Ticket handling helpers
# ---------------------------------------------------------------------------

_YES_TOKENS = {"si", "sí", "s", "y", "yes", "ok", "vale", "dale", "de acuerdo"}
_NO_TOKENS = {
    "no", "n", "nop", "nope", "para nada",
    "no gracias", "no, gracias",
}

_CANCEL_PATTERNS = [
    r"\bcancela\b",
    r"\bcancelar\b",
    r"\banula\b",
    r"\banular\b",
    r"\bolvídalo\b",
    r"\bolvida eso\b",
    r"\bya no lo necesito\b",
    r"\bya no hace falta\b",
    r"\bya no quiero eso\b",
]


def _looks_like_global_cancel(msg: str) -> bool:
    """
    Best-effort, LLM-independent check for cancellation messages.
    This mirrors the spirit of _gh_is_cancel(..., state='GLOBAL')
    from your old DFA.

    It does NOT look at previous state; it only checks the raw text.
    """
    if not msg:
        return False
    lower = msg.lower()
    for pat in _CANCEL_PATTERNS:
        if re.search(pat, lower):
            return True
    return False



def _normalize_yes_no_token(text: str) -> str:
    t = (text or "").strip().lower()
    # quitar puntuación final, emojis simples, etc.
    t = re.sub(r"[!.,;:()\[\]\-—_*~·•«»\"'`´]+$", "", t).strip()
    return t


def _is_yes(text: str) -> bool:
    return _normalize_yes_no_token(text) in _YES_TOKENS


def _is_no(text: str) -> bool:
    return _normalize_yes_no_token(text) in _NO_TOKENS


# ---------------------------------------------------------------------------
# Ticket handling helpers
# ---------------------------------------------------------------------------


def _handle_ticket_intent(nlu: NLUResult, session: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Apply NLU fields to the current ticket draft and send confirmation message.
    """
    logger.info(
        "[TICKET] 🎫 Creating ticket draft from NLU",
        extra={
            "wa_id": session.get("wa_id"),
            "nlu_area": nlu.area,
            "nlu_room": nlu.room,
            "nlu_detail": nlu.detail,
            "location": "gateway_app/core/state.py"
        }
    )

    draft = _get_ticket_draft(session)

    # Update draft from NLU
    if nlu.area:
        draft["area"] = nlu.area
    if nlu.priority:
        draft["priority"] = nlu.priority
    if nlu.room:
        draft["room"] = nlu.room
        session["room"] = nlu.room
    if nlu.detail:
        draft["detail"] = nlu.detail

    session["state"] = STATE_TICKET_CONFIRM

    summary = _format_ticket_summary(draft)
    confirm_text = guest_llm.render_confirm_draft(summary, session)

    logger.info(
        "[TICKET] ✅ Ticket draft created → Waiting for user confirmation",
        extra={
            "decision": "TICKET_DRAFT_CREATED",
            "wa_id": session.get("wa_id"),
            "draft": draft,
            "new_state": STATE_TICKET_CONFIRM,
            "location": "gateway_app/core/state.py"
        },
    )

    return [_text_action(confirm_text)]


def _format_ticket_summary(draft: Dict[str, Any]) -> str:
    parts: List[str] = []

    area = draft.get("area")
    priority = draft.get("priority")
    room = draft.get("room")
    detail = draft.get("detail")

    if area:
        parts.append(f"- Área: {area}")
    #if priority:
    #    parts.append(f"- Prioridad: {priority}")
    if room:
        parts.append(f"- Habitación: {room}")
    if detail:
        parts.append(f"- Detalle: {detail}")

    if not parts:
        return "Aún no tengo detalles claros de tu solicitud."

    return "\n".join(parts)


def _handle_ticket_confirmation_yes_no(
    msg: str,
    session: Dict[str, Any],
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Process SI / NO responses when in GH_TICKET_CONFIRM.

    Returns:
        (handled, actions)
        handled = True  -> message was treated as a confirmation response.
        handled = False -> caller should continue normal processing.
    """
    actions: List[Dict[str, Any]] = []

    # ---------- YES = crear ticket ----------
    if _is_yes(msg):
        logger.info(
            "[TICKET] ✅ User confirmed YES → Creating ticket in database",
            extra={
                "decision": "USER_CONFIRMED_YES",
                "wa_id": session.get("wa_id"),
                "user_message": msg,
                "location": "gateway_app/core/state.py"
            }
        )

        # ⭐ Move temporary identity to permanent session fields
        temp_name = session.pop("temp_guest_name", None)
        temp_room = session.pop("temp_room", None)

        if temp_name:
            session["guest_name"] = temp_name
            logger.debug(f"[IDENTITY] Moved temp_guest_name to guest_name: {temp_name}")

        if temp_room:
            session["room"] = temp_room
            logger.debug(f"[IDENTITY] Moved temp_room to room: {temp_room}")

        # Read from the correct location where _create_combined_confirmation_direct() stores it
        draft = session.get("ticket_draft") or {}

        # Construir payload equivalente al código monolítico antiguo
        payload = {
            "org_id": ORG_ID_DEFAULT,
            "hotel_id": HOTEL_ID_DEFAULT,
            "area": draft.get("area") or "MANTENCION",
            "prioridad": draft.get("priority") or "MEDIA",
            "detalle": draft.get("detail") or "",
            "canal_origen": "huesped_whatsapp",
            "ubicacion": draft.get("room") or session.get("room"),
            "huesped_id": session.get("phone"),
            "huesped_phone": session.get("phone"),
            "huesped_nombre": session.get("guest_name") or "",
        }

        logger.info(
            "[TICKET] 💾 Calling create_ticket() with payload",
            extra={
                "wa_id": session.get("wa_id"),
                "payload": payload,
                "location": "gateway_app/core/state.py"
            }
        )

        # Crear ticket en tu backend (usa tu create_ticket real)
        ticket_id = create_ticket(payload, initial_status="PENDIENTE_APROBACION")

        if ticket_id:
            logger.info(
                "[TICKET] ✅ Ticket created successfully in database",
                extra={
                    "decision": "TICKET_CREATED_SUCCESS",
                    "wa_id": session.get("wa_id"),
                    "ticket_id": ticket_id,
                    "payload": payload,
                    "location": "gateway_app/core/state.py"
                }
            )
        else:
            logger.error(
                "[TICKET] ❌ Ticket creation FAILED (create_ticket returned None)",
                extra={
                    "decision": "TICKET_CREATED_FAILED",
                    "wa_id": session.get("wa_id"),
                    "payload": payload,
                    "location": "gateway_app/core/state.py"
                }
            )

        # Opcional: seguir notificando al sistema central, si lo usas
        notify.notify_internal(
            "ticket_created",
            {
                "ticket_id": ticket_id,
                "payload": payload,
                "wa_id": session.get("wa_id"),
                "phone": session.get("phone"),
                "guest_name": session.get("guest_name"),
            },
        )

        # Volvemos al estado "normal" después de crear el ticket
        session["state"] = STATE_NEW

        # ⭐ Get area name for user-friendly message
        area = payload.get("area", "MANTENCION")
        area_map = {
            "MANTENCION": "Mantenimiento",
            "HOUSEKEEPING": "Housekeeping",
            "ROOMSERVICE": "Room Service",
        }
        area_name = area_map.get(area, area)
        room = payload.get("ubicacion", "")

        if ticket_id:
            # ⭐ NO mostrar ticket ID al huésped
            text = (
                f"¡Listo! Ya notifiqué al equipo de {area_name} sobre tu solicitud "
                f"en la habitación {room}. Te avisaré cuando esté resuelto. ✅"
            )
        else:
            # Si por cualquier motivo create_ticket devolvió None,
            # avisamos al huésped pero también dejamos constancia en logs.
            text = (
                "He intentado crear tu ticket, pero hubo un problema con el sistema interno. "
                "El equipo de recepción ha sido notificado."
            )

        actions.append(_text_action(text))
        _clear_ticket_draft(session)
        return True, actions

    # ---------- NO = volver a modo edición ----------
    if _is_no(msg):
        logger.info(
            "[TICKET] ⚠️ User said NO → Restart identity collection",
            extra={
                "decision": "USER_SAID_NO",
                "wa_id": session.get("wa_id"),
                "user_message": msg,
                "location": "gateway_app/core/state.py"
            }
        )

        # ⭐ Clear temporary identity fields and restart collection
        session.pop("temp_guest_name", None)
        session.pop("temp_room", None)
        session.pop("temp_ticket_draft", None)

        session["state"] = STATE_GUEST_IDENTIFY

        actions.append(
            _text_action(
                "Sin problema. Volvamos a empezar:\n\n"
                "📝 ¿Cuál es tu nombre completo?\n"
                "🏨 ¿En qué número de habitación te encuentras?"
            )
        )
        return True, actions

    # Cualquier otra cosa no se interpreta como confirmación
    logger.info(
        "[TICKET] ℹ️ Message not recognized as YES/NO → Continue normal processing",
        extra={
            "decision": "NOT_YES_NO_CONTINUE",
            "wa_id": session.get("wa_id"),
            "user_message": msg,
            "location": "gateway_app/core/state.py"
        }
    )
    return False, []


# ==============================================================================
# IDENTITY VALIDATION HELPERS
# ==============================================================================

def _has_guest_identity(session: Dict[str, Any], nlu: NLUResult) -> bool:
    """
    Check if we have both guest_name and room in session OR in NLU.

    Returns:
        True if both name and room are available, False otherwise.
    """
    # Check session first
    session_name = session.get("guest_name")
    session_room = session.get("room")

    # Check NLU
    nlu_name = getattr(nlu, "name", None)
    nlu_room = nlu.room

    has_name = bool(session_name or nlu_name)
    has_room = bool(session_room or nlu_room)

    logger.debug(
        "[IDENTITY] Checking guest identity",
        extra={
            "wa_id": session.get("wa_id"),
            "has_name": has_name,
            "has_room": has_room,
            "session_name": session_name,
            "session_room": session_room,
            "nlu_name": nlu_name,
            "nlu_room": nlu_room,
        }
    )

    return has_name and has_room


def _request_guest_identity(nlu: NLUResult, session: Dict[str, Any]) -> list:
    """
    Request guest name and room number.

    Transitions to STATE_GUEST_IDENTIFY state.

    Returns:
        List of actions (WhatsApp messages) to send.
    """
    session["state"] = STATE_GUEST_IDENTIFY

    # Store partial ticket info in temp_ticket_draft
    session["temp_ticket_draft"] = {
        "area": nlu.area,
        "priority": nlu.priority,
        "detail": nlu.detail,
        "room": nlu.room,  # May be None
    }

    logger.info(
        "[IDENTITY] Requesting guest identity",
        extra={
            "wa_id": session.get("wa_id"),
            "state": STATE_GUEST_IDENTIFY,
            "area": nlu.area,
            "detail": nlu.detail,
        }
    )

    text = (
        "Para poder ayudarte mejor, necesito confirmar algunos datos:\n\n"
        "📝 ¿Cuál es tu nombre completo?\n"
        "🏨 ¿En qué número de habitación te encuentras?"
    )

    return [_text_action(text)]


def _handle_guest_identify(
    msg: str,
    nlu: NLUResult,
    session: Dict[str, Any]
) -> tuple[bool, list]:
    """
    Handle messages in STATE_GUEST_IDENTIFY state.

    Attempts to extract name and room from:
    1. NLU result (name field)
    2. Simple regex patterns

    Once both are extracted, creates combined confirmation.

    Returns:
        (handled: bool, actions: list)
    """
    wa_id = session.get("wa_id")

    # Try to extract from NLU first
    nlu_name = getattr(nlu, "name", None)
    nlu_room = nlu.room

    # Fallback to simple extraction if NLU didn't get them
    extracted_name = nlu_name or _extract_name_simple(msg)
    extracted_room = nlu_room or _extract_room_simple(msg)

    logger.debug(
        "[IDENTITY] Extracting identity from message",
        extra={
            "wa_id": wa_id,
            "msg": msg,
            "nlu_name": nlu_name,
            "nlu_room": nlu_room,
            "extracted_name": extracted_name,
            "extracted_room": extracted_room,
        }
    )

    # Store in temporary fields
    if extracted_name:
        session["temp_guest_name"] = extracted_name
    if extracted_room:
        session["temp_room"] = extracted_room

    # Check if we have both
    temp_name = session.get("temp_guest_name")
    temp_room = session.get("temp_room")

    if temp_name and temp_room:
        # We have both! Create combined confirmation
        logger.info(
            "[IDENTITY] ✅ Both name and room extracted → Creating combined confirmation",
            extra={
                "wa_id": wa_id,
                "temp_name": temp_name,
                "temp_room": temp_room,
            }
        )

        actions = _create_combined_confirmation(session)
        return True, actions

    # Still missing something, ask again
    missing = []
    if not temp_name:
        missing.append("nombre")
    if not temp_room:
        missing.append("número de habitación")

    logger.info(
        "[IDENTITY] ⚠️ Missing identity fields → Asking again",
        extra={
            "wa_id": wa_id,
            "missing": missing,
            "temp_name": temp_name,
            "temp_room": temp_room,
        }
    )

    text = f"Gracias, pero aún necesito tu {' y '.join(missing)}. ¿Puedes proporcionarlo?"

    return True, [_text_action(text)]


def _create_combined_confirmation(session: Dict[str, Any]) -> list:
    """
    Create a single combined confirmation message with identity + ticket details.

    Uses temp_guest_name, temp_room, and temp_ticket_draft from session.

    Returns:
        List of actions (WhatsApp messages).
    """
    temp_name = session.get("temp_guest_name", "")
    temp_room = session.get("temp_room", "")
    temp_draft = session.get("temp_ticket_draft", {})

    area = temp_draft.get("area", "MANTENCION")
    priority = temp_draft.get("priority", "MEDIA")
    detail = temp_draft.get("detail", "Sin detalles")

    # Map area to friendly name
    area_map = {
        "MANTENCION": "Mantenimiento",
        "HOUSEKEEPING": "Housekeeping",
        "ROOMSERVICE": "Room Service",
    }
    area_name = area_map.get(area, area)

    # Build confirmation message - simplified version
    text = (
        f"Perfecto, {temp_name}. Voy a notificar al equipo de {area_name} sobre:\n\n"
        f"📝 {detail}\n"
        f"🏨 Habitación {temp_room}\n\n"
        "¿Confirmas? (Sí/No)"
    )

    # Transition to TICKET_CONFIRM state
    session["state"] = STATE_TICKET_CONFIRM

    logger.info(
        "[IDENTITY] Creating combined confirmation",
        extra={
            "wa_id": session.get("wa_id"),
            "temp_name": temp_name,
            "temp_room": temp_room,
            "area": area,
            "priority": priority,
            "state": STATE_TICKET_CONFIRM,
        }
    )

    return [_text_action(text)]


def _create_combined_confirmation_direct(nlu: NLUResult, session: Dict[str, Any]) -> list:
    """
    Create combined confirmation when identity is already in session OR in NLU.

    This is used when guest already has guest_name + room in session or NLU extracted them.

    Returns:
        List of actions (WhatsApp messages).
    """
    # Use NLU data if available, otherwise fall back to session
    nlu_name = getattr(nlu, "name", None)
    nlu_room = nlu.room

    guest_name = nlu_name or session.get("guest_name", "")
    room = nlu_room or session.get("room", "")

    area = nlu.area or "MANTENCION"
    priority = nlu.priority or "MEDIA"
    detail = nlu.detail or "Sin detalles"

    # Map area to friendly name
    area_map = {
        "MANTENCION": "Mantenimiento",
        "HOUSEKEEPING": "Housekeeping",
        "ROOMSERVICE": "Room Service",
    }
    area_name = area_map.get(area, area)

    # Build confirmation message - simplified version
    text = (
        f"Perfecto, {guest_name}. Voy a notificar al equipo de {area_name} sobre:\n\n"
        f"📝 {detail}\n"
        f"🏨 Habitación {room}\n\n"
        "¿Confirmas? (Sí/No)"
    )

    # Create ticket draft in session
    session["ticket_draft"] = {
        "area": area,
        "priority": priority,
        "room": room,
        "detail": detail,
        "guest_name": guest_name,
    }

    # Transition to TICKET_CONFIRM state
    session["state"] = STATE_TICKET_CONFIRM

    logger.info(
        "[IDENTITY] Creating combined confirmation (direct)",
        extra={
            "wa_id": session.get("wa_id"),
            "guest_name": guest_name,
            "room": room,
            "area": area,
            "priority": priority,
            "state": STATE_TICKET_CONFIRM,
        }
    )

    return [_text_action(text)]


def _extract_name_simple(msg: str) -> Optional[str]:
    """
    Simple regex-based name extraction fallback.

    Looks for patterns like:
    - "mi nombre es Juan Pérez"
    - "soy María González"
    - "Juan Pérez, habitación 205"

    Returns:
        Extracted name or None.
    """
    import re

    msg_lower = msg.lower()

    # Pattern 1: "mi nombre es X" - Stop at common room indicators
    match = re.search(r"(?:mi nombre es|me llamo|soy)\s+([a-záéíóúñ\s]+?)(?:\s+(?:de la|en la|habitaci[oó]n|room|hab|y\s+|,|\.)|$)", msg_lower, re.IGNORECASE)
    if match:
        name = match.group(1).strip().title()
        if len(name) > 2:
            logger.debug(f"[EXTRACT] Name extracted (pattern 1): {name}")
            return name

    # Pattern 2: Look for capitalized words (likely a name)
    # e.g., "Juan Pérez habitación 205"
    words = msg.split()
    capitalized = [w for w in words if w and w[0].isupper() and not w.lower() in ["habitación", "habitacion", "room"]]
    if len(capitalized) >= 2:
        name = " ".join(capitalized[:3])  # Max 3 words for name
        logger.debug(f"[EXTRACT] Name extracted (pattern 2): {name}")
        return name

    logger.debug("[EXTRACT] No name pattern matched")
    return None


def _extract_room_simple(msg: str) -> Optional[str]:
    """
    Simple regex-based room number extraction fallback.

    Looks for patterns like:
    - "habitación 205"
    - "room 305"
    - "hab 123"
    - Just a number like "205"

    Returns:
        Extracted room number or None.
    """
    import re

    msg_lower = msg.lower()

    # Pattern 1: "habitación 205", "room 305", "hab 123"
    match = re.search(r"(?:habitaci[oó]n|room|hab\.?)\s*(\d{2,4})", msg_lower, re.IGNORECASE)
    if match:
        room = match.group(1)
        logger.debug(f"[EXTRACT] Room extracted (pattern 1): {room}")
        return room

    # Pattern 2: Just a standalone number (2-4 digits)
    match = re.search(r"\b(\d{2,4})\b", msg)
    if match:
        room = match.group(1)
        logger.debug(f"[EXTRACT] Room extracted (pattern 2): {room}")
        return room

    logger.debug("[EXTRACT] No room pattern matched")
    return None
