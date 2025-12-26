# gateway_app/core/conversation/orchestrator.py
"""
Conversation orchestrator - Main routing logic for handling incoming messages.

This module replaces the monolithic handle_incoming_text function in state.py
with a cleaner, more modular architecture.

Extracted from state.py (1,228 lines) to improve maintainability.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from gateway_app.core.models import NLUResult
from gateway_app.core.timefmt import utcnow
from gateway_app.core.conversation.session import new_session
from gateway_app.services import guest_llm

# Import intent handlers
from gateway_app.core.intents.identity_handler import (
    has_guest_identity,
    request_guest_identity,
    handle_guest_identify,
    create_combined_confirmation_direct,
)
from gateway_app.core.intents.ticket_handler import (
    handle_ticket_confirmation_yes_no,
    clear_ticket_draft,
)
from gateway_app.core.intents.smalltalk_handler import (
    handle_smalltalk,
    get_help_message,
    get_initial_greeting,
    get_menu_message,
)
from gateway_app.core.intents.faq_handler import handle_faq_fallback
from gateway_app.core.intents.handoff_handler import handle_handoff_request
from gateway_app.core.intents.base import text_action

logger = logging.getLogger(__name__)

# State constants
STATE_NEW = "GH_S0"
STATE_INIT = "GH_S0_INIT"
STATE_GUEST_IDENTIFY = "GH_IDENTIFY"
STATE_TICKET_CONFIRM = "GH_TICKET_CONFIRM"
STATE_AREA_CLARIFICATION = "GH_AREA_CLARIFICATION"
STATE_DETAIL_CLARIFICATION = "GH_DETAIL_CLARIFICATION"
STATE_FAQ = "GH_FAQ"

# Cancel patterns
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


def looks_like_global_cancel(msg: str) -> bool:
    """
    Best-effort, LLM-independent check for cancellation messages.
    """
    if not msg:
        return False
    lower = msg.lower()
    for pat in _CANCEL_PATTERNS:
        if re.search(pat, lower):
            return True
    return False


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
    Main orchestrator for incoming WhatsApp messages.

    This is a cleaner version of the original monolithic function,
    now delegating to specialized handlers.

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
        session = new_session(
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
            actions.append(text_action(get_initial_greeting(session)))
        return actions, session

    # ------------------------------------------------------------------
    # Global cancellation guardrail (independent of NLU)
    # ------------------------------------------------------------------
    if looks_like_global_cancel(msg):
        clear_ticket_draft(session)
        session["state"] = STATE_NEW
        actions.append(
            text_action(
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
    # Area clarification: user chose department (1-4)
    # ------------------------------------------------------------------
    if state == STATE_AREA_CLARIFICATION:
        from gateway_app.core.intents.identity_handler_clarification import handle_area_clarification_response

        handled, extra_actions = handle_area_clarification_response(msg, session)
        actions.extend(extra_actions)

        if handled:
            logger.debug(
                "[STATE] Area clarified",
                extra={"wa_id": wa_id, "state": session.get("state")}
            )

        return actions, session

    # ------------------------------------------------------------------
    # Detail clarification: user provides specific problem description
    # ------------------------------------------------------------------
    if state == STATE_DETAIL_CLARIFICATION:
        from gateway_app.core.intents.identity_handler_clarification import handle_detail_clarification_response

        handled, extra_actions = handle_detail_clarification_response(msg, session)
        actions.extend(extra_actions)

        if handled:
            logger.debug(
                "[STATE] Detail clarified",
                extra={"wa_id": wa_id, "state": session.get("state")}
            )

        return actions, session

    # ------------------------------------------------------------------
    # Ticket confirmation: handle explicit SI / NO first
    # ------------------------------------------------------------------
    if state == STATE_TICKET_CONFIRM:
        handled, extra_actions = handle_ticket_confirmation_yes_no(msg, session)
        if handled:
            actions.extend(extra_actions)
            logger.debug(
                "[STATE] after ticket confirm",
                extra={"wa_id": wa_id, "state": session.get("state")},
            )
            return actions, session
        # If not handled as SI/NO, fall through and treat as a normal message

    # ------------------------------------------------------------------
    # Next ticket confirmation: handle sequential multi-ticket flow
    # ------------------------------------------------------------------
    if state == "GH_NEXT_TICKET_CONFIRM":
        from gateway_app.core.intents.ticket_handler import is_yes, is_no
        from gateway_app.core.intents.identity_handler import create_combined_confirmation_direct

        if is_yes(msg):
            # User wants to create the next ticket
            next_ticket = session.pop("next_ticket_pending", None)
            remaining_requests = session.get("remaining_requests", [])

            if next_ticket:
                # Remove this request from remaining list
                if remaining_requests and len(remaining_requests) > 0:
                    remaining_requests = remaining_requests[1:]  # Remove first item
                    session["remaining_requests"] = remaining_requests if remaining_requests else []

                # ⭐ CREATE TICKET DIRECTLY (user already confirmed with "Sí")
                from gateway_app.services.tickets import create_ticket
                from gateway_app.services import notify
                from gateway_app.core.intents.ticket_handler import ORG_ID_DEFAULT, HOTEL_ID_DEFAULT

                area = next_ticket.get("area", "MANTENCION")
                priority = next_ticket.get("priority", "MEDIA")
                detail = next_ticket.get("detail", "")
                room = session.get("room", "")
                guest_name = session.get("guest_name", "")

                logger.info(
                    "[TICKET] 📋 Preparing payload for next ticket",
                    extra={
                        "area": area,
                        "detail": detail,
                        "room": room,
                        "guest_name": guest_name,
                        "phone": session.get("phone"),
                        "session_keys": list(session.keys())
                    }
                )

                payload = {
                    "org_id": ORG_ID_DEFAULT,
                    "hotel_id": HOTEL_ID_DEFAULT,
                    "area": area,
                    "prioridad": priority,
                    "detalle": detail,
                    "canal_origen": "huesped_whatsapp",
                    "ubicacion": room,
                    "huesped_id": session.get("phone"),
                    "huesped_phone": session.get("phone"),
                    "huesped_nombre": guest_name,
                    # Routing metadata
                    "routing_source": "clarification",
                    "routing_reason": f"Sequential multi-ticket: {area}",
                    "routing_confidence": 1.0,
                    "routing_version": "v1",
                }

                ticket_id = create_ticket(payload, initial_status="PENDIENTE_APROBACION")

                if ticket_id:
                    logger.info(
                        "[TICKET] ✅ Next ticket created successfully",
                        extra={
                            "ticket_id": ticket_id,
                            "area": area,
                            "detail": detail,
                            "remaining_count": len(remaining_requests)
                        }
                    )
                else:
                    logger.error("[TICKET] ❌ Next ticket creation failed")

                # Notify internal systems
                notify.notify_internal(
                    "ticket_created",
                    {
                        "ticket_id": ticket_id,
                        "payload": payload,
                        "wa_id": session.get("wa_id"),
                        "phone": session.get("phone"),
                        "guest_name": guest_name,
                    },
                )

                # Get area name for user-friendly message
                area_map = {
                    "MANTENCION": "Mantenimiento",
                    "HOUSEKEEPING": "Housekeeping",
                    "RECEPCION": "Recepción",
                    "GERENCIA": "Gerencia",
                }
                area_name = area_map.get(area, area)

                if ticket_id:
                    success_text = (
                        f"¡Listo! Ya notifiqué al equipo de {area_name} sobre tu solicitud "
                        f"en la habitación {room}. Te avisaré cuando esté resuelto. ✅"
                    )
                    actions.append(text_action(success_text))
                else:
                    error_text = (
                        "He intentado crear tu ticket, pero hubo un problema con el sistema interno. "
                        "El equipo de recepción ha sido notificado."
                    )
                    actions.append(text_action(error_text))

                # ⭐ Check if there are MORE remaining requests
                if remaining_requests and len(remaining_requests) > 0:
                    next_request = remaining_requests[0]
                    next_area = next_request.get("area", "")
                    next_detail = next_request.get("detail", "")
                    next_area_name = area_map.get(next_area, next_area)

                    prompt_text = (
                        f"\n\n📋 También mencionaste: *{next_detail}* ({next_area_name})\n\n"
                        f"¿Quieres que cree esta solicitud también? (Sí/No)"
                    )
                    actions.append(text_action(prompt_text))

                    session["state"] = "GH_NEXT_TICKET_CONFIRM"
                    session["next_ticket_pending"] = next_request

                    logger.info(
                        "[TICKET] 📋 Prompting user for next ticket in sequence",
                        extra={
                            "remaining_count": len(remaining_requests),
                            "next_area": next_area,
                            "next_detail": next_detail
                        }
                    )
                else:
                    # No more tickets, reset to normal state
                    session["state"] = STATE_NEW
                    session.pop("remaining_requests", None)

            return actions, session

        elif is_no(msg):
            # User doesn't want to create more tickets
            session.pop("next_ticket_pending", None)
            session.pop("remaining_requests", None)
            session["state"] = STATE_NEW

            actions.append(text_action(
                "Perfecto. Si necesitas algo más, escríbeme cuando quieras. 😊"
            ))

            logger.info("[TICKET] ℹ️ User declined next ticket creation")
            return actions, session

    # ------------------------------------------------------------------
    # Simple commands to reset / show menu
    # ------------------------------------------------------------------
    if msg.lower() in {"menu", "inicio", "start"}:
        session["state"] = STATE_INIT
        actions.append(text_action(get_menu_message(session)))
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
            "location": "gateway_app/core/conversation/orchestrator.py"
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
            "location": "gateway_app/core/conversation/orchestrator.py"
        },
    )

    # ------------------------------------------------------------------
    # Handle identity validation state BEFORE normal intent routing
    # ------------------------------------------------------------------
    if state == STATE_GUEST_IDENTIFY:
        handled, extra_actions = handle_guest_identify(msg, nlu, session)
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
                "location": "gateway_app/core/conversation/orchestrator.py"
            }
        )
        actions.append(text_action(get_help_message()))
        session["state"] = STATE_INIT
        return actions, session

    # Explicit human handoff
    if nlu.intent == "handoff_request" or nlu.wants_handoff:
        actions.extend(handle_handoff_request(msg, session))
        return actions, session

    # Cancel current request
    if nlu.intent == "cancel" or nlu.is_cancel:
        logger.info(
            "[FLOW] ✅ DECISION: Intent=CANCEL → Clear ticket draft",
            extra={
                "decision": "INTENT_CANCEL",
                "wa_id": wa_id,
                "user_message": msg,
                "location": "gateway_app/core/conversation/orchestrator.py"
            }
        )
        clear_ticket_draft(session)
        session["state"] = STATE_NEW
        actions.append(
            text_action(
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
                "location": "gateway_app/core/conversation/orchestrator.py"
            }
        )

        # =========================================================================
        # CONFIDENCE THRESHOLD: Check routing confidence BEFORE asking for identity
        # =========================================================================
        routing_confidence = getattr(nlu, "routing_confidence", 0.75)
        area = getattr(nlu, "area", None)
        multiple_requests = getattr(nlu, "multiple_requests", None)
        CONFIDENCE_THRESHOLD = 0.65

        if not area or routing_confidence < CONFIDENCE_THRESHOLD:
            logger.warning(
                f"[ROUTING] ⚠️ Low confidence ({routing_confidence:.2f}) or missing area → Request clarification",
                extra={
                    "area": area,
                    "confidence": routing_confidence,
                    "threshold": CONFIDENCE_THRESHOLD,
                    "multiple_requests": multiple_requests,
                    "will_ask_clarification": True
                }
            )

            # Guardar contexto pendiente (NO pedir identidad todavía)
            session["state"] = "GH_AREA_CLARIFICATION"
            session["pending_detail"] = getattr(nlu, "detail", None)

            # ⭐ NEW: If multiple requests detected, show them and store for later
            if multiple_requests and isinstance(multiple_requests, list) and len(multiple_requests) >= 2:
                session["pending_requests"] = multiple_requests

                # Build friendly list of requests
                requests_text = ""
                area_map = {
                    "MANTENCION": ("Mantenimiento", "1", "técnico/AC/agua/luz"),
                    "HOUSEKEEPING": ("Housekeeping", "2", "limpieza/toallas/amenities"),
                    "RECEPCION": ("Recepción", "3", "pagos/reservas/info"),
                    "GERENCIA": ("Gerencia", "4", "queja/gerencia")
                }

                # Get unique areas from multiple requests
                detected_areas = []
                seen_areas = set()
                for req in multiple_requests:
                    req_area = req.get("area", "")
                    if req_area and req_area not in seen_areas:
                        detected_areas.append(req_area)
                        seen_areas.add(req_area)

                # Sort detected areas by their fixed number to maintain consistent order
                # (1=MANTENCION, 2=HOUSEKEEPING, 3=RECEPCION, 4=GERENCIA)
                area_order = {
                    "MANTENCION": 1,
                    "HOUSEKEEPING": 2,
                    "RECEPCION": 3,
                    "GERENCIA": 4
                }
                detected_areas.sort(key=lambda area: area_order.get(area, 99))

                # Build list of detected requests with details
                for i, req in enumerate(multiple_requests, 1):
                    req_area = req.get("area", "")
                    area_name = area_map.get(req_area, ("", "", ""))[0]
                    req_detail = req.get("detail", "")
                    requests_text += f"{i}. *{req_detail}* ({area_name})\n"

                # Build options showing ONLY detected areas
                options_text = ""
                for area_code in detected_areas:
                    area_info = area_map.get(area_code)
                    if area_info:
                        area_name, number, description = area_info
                        options_text += f"{number}️⃣ *{area_name}* ({description})\n"

                clarification_text = (
                    f"Veo que tienes {len(multiple_requests)} necesidades diferentes:\n\n"
                    f"{requests_text}\n"
                    f"Voy a crear solicitudes separadas para cada una.\n\n"
                    f"¿Con cuál quieres empezar?\n\n"
                    f"{options_text}\n"
                    f"Responde con el número ({', '.join(area_map[a][1] for a in detected_areas)})."
                )

                logger.info(
                    "[ROUTING] 📋 Multiple requests detected, asking user which to start with",
                    extra={
                        "request_count": len(multiple_requests),
                        "detected_areas": detected_areas
                    }
                )
            else:
                # Original single-request clarification
                clarification_text = (
                    f"Entiendo que necesitas ayuda con: *{getattr(nlu, 'detail', 'tu solicitud')}*\n\n"
                    "Para asignarlo correctamente, ¿es sobre:\n\n"
                    "1️⃣ *Mantenimiento* (técnico/AC/agua/luz)\n"
                    "2️⃣ *Housekeeping* (limpieza/toallas/amenities)\n"
                    "3️⃣ *Recepción* (pagos/reservas/info)\n"
                    "4️⃣ *Otro* (queja/gerencia)\n\n"
                    "Responde con el número (1-4)."
                )

                logger.info("[ROUTING] 📋 Requesting area clarification from user")

            actions.append(text_action(clarification_text))
            return actions, session

        # ⭐ Validate identity BEFORE creating ticket
        if not has_guest_identity(session, nlu):
            actions.extend(request_guest_identity(nlu, session))
            return actions, session

        # If we have identity, create combined confirmation
        actions.extend(create_combined_confirmation_direct(nlu, session))
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
                "location": "gateway_app/core/conversation/orchestrator.py"
            }
        )

        # If new conversation, send initial greeting instead of smalltalk
        if new_conversation:
            actions.append(text_action(get_initial_greeting(session)))
        else:
            extra_actions = handle_smalltalk(msg, session, new_conversation)
            actions.extend(extra_actions)

        if state in {STATE_INIT, STATE_FAQ}:
            session["state"] = STATE_NEW

        return actions, session

    # ------------------------------------------------------------------
    # Not understood or unclassified: try FAQ as FALLBACK (LAST RESORT)
    # ------------------------------------------------------------------
    if nlu.intent == "not_understood" or nlu.intent is None:
        found_faq, faq_actions = handle_faq_fallback(msg, session)
        actions.extend(faq_actions)
        return actions, session

    # ------------------------------------------------------------------
    # Safety net (unexpected intent value)
    # ------------------------------------------------------------------
    actions.append(
        text_action(
            "Gracias por tu mensaje. Si quieres, puedes contarme si "
            "necesitas reportar un problema, pedir algo a la habitación "
            "o hacer una pregunta sobre el hotel."
        )
    )
    return actions, session
