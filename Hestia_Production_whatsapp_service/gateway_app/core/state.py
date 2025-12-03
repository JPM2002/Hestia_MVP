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
STATE_INIT = "GH_S0i"
STATE_TICKET_DRAFT = "GH_TICKET_DRAFT"
STATE_TICKET_CONFIRM = "GH_TICKET_CONFIRM"
STATE_FAQ = "GH_FAQ"
STATE_HANDOFF = "GH_HANDOFF"

# In-memory session store: wa_id -> session dict
_SESSIONS: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Public API used by webhook/routes.py
# ---------------------------------------------------------------------------


def load_session(wa_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve the session for a WhatsApp contact id (wa_id).

    Returns:
        dict with session data, or None if not found.
    """
    return _SESSIONS.get(wa_id)


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

    # Optional greeting on very first message
    if new_conversation:
        actions.append(_text_action(_initial_greeting(session)))

    # If no text after greeting (e.g., pure audio that failed), nothing else to do
    if not msg:
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
    nlu_raw = guest_llm.analyze_guest_message(msg, session=session, state=state)
    nlu = NLUResult.from_dict(nlu_raw) if nlu_raw else NLUResult()

    logger.debug(
        "[STATE] NLU result",
        extra={"wa_id": wa_id, "nlu": nlu.to_dict()},
    )

    # ------------------------------------------------------------------
    # Route based on intent / flags
    # ------------------------------------------------------------------

    # Help / capabilities
    if nlu.intent == "help" or nlu.is_help:
        actions.append(_text_action(_help_message()))
        session["state"] = STATE_INIT
        return actions, session

    # Explicit human handoff
    if nlu.intent == "handoff_request" or nlu.wants_handoff:
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
        actions.extend(_handle_ticket_intent(nlu, session))
        return actions, session

    # Smalltalk / general chat (thank you, etc.)
    if nlu.intent == "general_chat" or nlu.is_smalltalk:
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
    # Not understood or unclassified: try FAQ as fallback
    # ------------------------------------------------------------------
    if nlu.intent == "not_understood" or nlu.intent is None:
        faq_answer = faq_llm.answer_faq(msg)
        if faq_answer:
            session["state"] = STATE_FAQ
            actions.append(_text_action(faq_answer))
            actions.append(
                _text_action("¿Puedo ayudarte con algo más durante tu estadía?")
            )
            return actions, session

        # Final fallback
        actions.append(
            _text_action(
                "No estoy seguro de haber entendido bien. "
                "Puedo ayudarte a reportar un problema en tu habitación, "
                "pedir algo al hotel o responder dudas frecuentes "
                "(desayuno, wifi, horarios). ¿Qué necesitas?"
            )
        )
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
        + "soy Hestia, tu asistente virtual del hotel. "
          "Puedo ayudarte a reportar problemas en tu habitación, "
          "pedir toallas, amenities o comida, y responder preguntas "
          "como horarios de desayuno o wifi."
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
        "[STATE] ticket_request draft updated",
        extra={"wa_id": session.get("wa_id"), "draft": draft},
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
    if priority:
        parts.append(f"- Prioridad: {priority}")
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
        draft = session.get("data", {}).get("ticket_draft") or {}

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

        # Crear ticket en tu backend (usa tu create_ticket real)
        ticket_id = create_ticket(payload, initial_status="PENDIENTE_APROBACION")

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

        if ticket_id:
            text = (
                f"Perfecto, he creado tu ticket #{ticket_id} y lo he enviado al equipo del hotel. "
                "Te avisaremos cuando esté resuelto."
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
        session["state"] = STATE_TICKET_DRAFT
        actions.append(
            _text_action(
                "Sin problema. Dime qué parte quieres cambiar "
                "(área, prioridad, habitación o detalle) y te enviaré un nuevo resumen."
            )
        )
        return True, actions

    # Cualquier otra cosa no se interpreta como confirmación
    return False, []
