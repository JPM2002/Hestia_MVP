# gateway_app/core/intents/ticket_handler.py
"""
Ticket creation handler - Handles ticket draft and confirmation flow.

Extracted from state.py to improve modularity.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from gateway_app.core.intents.base import text_action
from gateway_app.services import notify

logger = logging.getLogger(__name__)

# IDs para tu backend de tickets (configurable vía environment variables)
ORG_ID_DEFAULT = int(os.getenv("ORG_ID_DEFAULT", ""))
HOTEL_ID_DEFAULT = int(os.getenv("HOTEL_ID_DEFAULT", ""))

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


# State constants
STATE_NEW = "GH_S0"


def _create_ticket_internal(
    payload: Dict[str, Any],
    session: Dict[str, Any],
    dev_mode: bool = True
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Internal helper to create a ticket (or mock it in dev mode).

    Args:
        payload: Ticket payload
        session: User session
        dev_mode: If True, don't actually create ticket (mock mode)

    Returns:
        (ticket_id, actions) tuple
    """
    actions: List[Dict[str, Any]] = []

    if dev_mode:
        # 🚧 MODO DESARROLLO: No crear ticket en base de datos
        ticket_id = "DEV-MOCK-12345"
        logger.info(
            "[TICKET] 🚧 DEV MODE: Ticket NOT created in database (mock mode)",
            extra={
                "decision": "DEV_MODE_MOCK_TICKET",
                "wa_id": session.get("wa_id"),
                "mock_ticket_id": ticket_id,
                "payload": payload,
                "location": "gateway_app/core/intents/ticket_handler.py::_create_ticket_internal"
            }
        )
    else:
        # Crear ticket real en base de datos
        ticket_id = create_ticket(payload, initial_status="PENDIENTE_APROBACION")

        if ticket_id:
            logger.info(
                "[TICKET] ✅ Ticket created successfully in database",
                extra={
                    "decision": "TICKET_CREATED_SUCCESS",
                    "wa_id": session.get("wa_id"),
                    "ticket_id": ticket_id,
                    "payload": payload,
                    "location": "gateway_app/core/intents/ticket_handler.py::_create_ticket_internal"
                }
            )

            # NUEVO: Marcar que se creó ticket en conversation_logs (evita encuesta FAQ)
            try:
                from gateway_app.services import conversation_logger
                wa_id = session.get("wa_id")
                if wa_id:
                    conversation_logger.mark_ticket_created(wa_id, ticket_id)
            except Exception as e:
                logger.warning(f"[TICKET] No se pudo marcar ticket en conversation_logs: {e}")

        else:
            logger.error(
                "[TICKET] ❌ Ticket creation FAILED (create_ticket returned None)",
                extra={
                    "decision": "TICKET_CREATED_FAILED",
                    "wa_id": session.get("wa_id"),
                    "payload": payload,
                    "location": "gateway_app/core/intents/ticket_handler.py::_create_ticket_internal"
                }
            )

        # Notificación interna
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

    # Build user-facing message
    area = payload.get("area", "MANTENCION")
    area_map = {
        "MANTENCION": "Mantenimiento",
        "HOUSEKEEPING": "Housekeeping",
        "RECEPCION": "Recepción",
        "SUPERVISION": "Supervisión",
        "GERENCIA": "Gerencia",
    }
    area_name = area_map.get(area, area)
    room = payload.get("ubicacion", "")

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

    return ticket_id, actions


def handle_ticket_confirmation_yes_no(
    msg: str,
    session: Dict[str, Any],
) -> tuple[bool, List[Dict[str, Any]]]:
    """
    Process SI / NO responses when in GH_TICKET_CONFIRM.

    Returns:
        (handled, actions)
        handled = True  -> message was treated as a confirmation response.
        handled = False -> caller should continue normal processing.
    """
    actions: List[Dict[str, Any]] = []

    # ---------- YES = crear ticket ----------
    if is_yes(msg):
        logger.info(
            "[TICKET] ✅ User confirmed YES → Creating ticket in database",
            extra={
                "decision": "USER_CONFIRMED_YES",
                "wa_id": session.get("wa_id"),
                "user_message": msg,
                "location": "gateway_app/core/intents/ticket_handler.py"
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

        # Read from the correct location where create_combined_confirmation_direct() stores it
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
            # ⭐ Routing metadata (audit trail)
            "routing_source": draft.get("routing_source", "fallback"),
            "routing_reason": draft.get("routing_reason", "No metadata"),
            "routing_confidence": draft.get("routing_confidence", 0.0),
            "routing_version": draft.get("routing_version", "v1"),
        }

        # Use shared ticket creation logic
        _, ticket_actions = _create_ticket_internal(
            payload=payload,
            session=session,
            dev_mode=False  # ✅ PRODUCTION MODE: Create real tickets in database
        )

        actions.extend(ticket_actions)

        # Reset state and clear draft
        session["state"] = STATE_NEW
        clear_ticket_draft(session)

        # ⭐ NEW: Check if there are remaining requests from multi-request flow
        remaining_requests = session.get("remaining_requests", [])
        if remaining_requests and isinstance(remaining_requests, list) and len(remaining_requests) > 0:
            # Get next request
            next_request = remaining_requests[0]
            next_area = next_request.get("area", "")
            next_detail = next_request.get("detail", "")

            area_map = {
                "MANTENCION": "Mantenimiento",
                "HOUSEKEEPING": "Housekeeping",
                "RECEPCION": "Recepción",
                "GERENCIA": "Gerencia",
            }
            next_area_name = area_map.get(next_area, next_area)

            # Ask if user wants to create the next ticket
            prompt_text = (
                f"\n\n📋 También mencionaste: *{next_detail}* ({next_area_name})\n\n"
                f"¿Quieres que cree esta solicitud también? (Sí/No)"
            )

            actions.append(text_action(prompt_text))

            # Set state to handle next ticket confirmation
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

        return True, actions

    # ---------- NO = volver a modo edición ----------
    if is_no(msg):
        logger.info(
            "[TICKET] ⚠️ User said NO → Restart identity collection",
            extra={
                "decision": "USER_SAID_NO",
                "wa_id": session.get("wa_id"),
                "user_message": msg,
                "location": "gateway_app/core/intents/ticket_handler.py"
            }
        )

        # ⭐ Clear temporary identity fields and restart collection
        session.pop("temp_guest_name", None)
        session.pop("temp_room", None)
        # ticket_draft will be recreated when re-entering identity flow

        session["state"] = "GH_IDENTIFY"

        actions.append(
            text_action(
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
            "location": "gateway_app/core/intents/ticket_handler.py"
        }
    )
    return False, []


def clear_ticket_draft(session: Dict[str, Any]) -> None:
    """Clear ticket draft from session."""
    data = session.setdefault("data", {})
    if "ticket_draft" in data:
        del data["ticket_draft"]
    # Also clear top-level ticket_draft if it exists
    if "ticket_draft" in session:
        del session["ticket_draft"]


# YES/NO detection helpers
_YES_TOKENS = {"si", "sí", "s", "y", "yes", "ok", "vale", "dale", "de acuerdo"}
_NO_TOKENS = {
    "no", "n", "nop", "nope", "para nada",
    "no gracias", "no, gracias",
}


def normalize_yes_no_token(text: str) -> str:
    """Normalize text for YES/NO detection."""
    import re
    t = (text or "").strip().lower()
    # quitar puntuación final, emojis simples, etc.
    t = re.sub(r"[!.,;:()\[\]\-—_*~·•«»\"'`´]+$", "", t).strip()
    return t


def is_yes(text: str) -> bool:
    """Check if text is a YES response."""
    return normalize_yes_no_token(text) in _YES_TOKENS


def is_no(text: str) -> bool:
    """Check if text is a NO response."""
    return normalize_yes_no_token(text) in _NO_TOKENS
