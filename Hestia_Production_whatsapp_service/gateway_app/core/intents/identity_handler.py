# gateway_app/core/intents/identity_handler.py
"""
Identity validation handler - Handles guest name and room number collection.

Extracted from state.py to improve modularity.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from gateway_app.core.intents.base import text_action

logger = logging.getLogger(__name__)


# State constants
STATE_GUEST_IDENTIFY = "GH_IDENTIFY"
STATE_TICKET_CONFIRM = "GH_TICKET_CONFIRM"


def has_guest_identity(session: Dict[str, Any], nlu: Any) -> bool:
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
    nlu_room = getattr(nlu, "room", None)

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


def request_guest_identity(nlu: Any, session: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Request guest name and room number.

    Transitions to STATE_GUEST_IDENTIFY state.

    Returns:
        List of actions (WhatsApp messages) to send.
    """
    session["state"] = STATE_GUEST_IDENTIFY

    # Store partial ticket info in ticket_draft (single source of truth)
    session["ticket_draft"] = {
        "area": getattr(nlu, "area", None),
        "priority": getattr(nlu, "priority", None),
        "detail": getattr(nlu, "detail", None),
        "room": getattr(nlu, "room", None),  # May be None
        # Routing metadata
        "routing_source": getattr(nlu, "routing_source", "fallback"),
        "routing_reason": getattr(nlu, "routing_reason", "No metadata"),
        "routing_confidence": getattr(nlu, "routing_confidence", 0.0),
        "routing_version": getattr(nlu, "routing_version", "v1"),
    }

    logger.info(
        "[IDENTITY] Requesting guest identity",
        extra={
            "wa_id": session.get("wa_id"),
            "state": STATE_GUEST_IDENTIFY,
            "area": getattr(nlu, "area", None),
            "detail": getattr(nlu, "detail", None),
        }
    )

    text = (
        "Para poder ayudarte mejor, necesito confirmar algunos datos:\n\n"
        "📝 ¿Cuál es tu nombre completo?\n"
        "🏨 ¿En qué número de habitación te encuentras?"
    )

    return [text_action(text)]


def handle_guest_identify(
    msg: str,
    nlu: Any,
    session: Dict[str, Any]
) -> tuple[bool, List[Dict[str, Any]]]:
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
    nlu_room = getattr(nlu, "room", None)

    # Fallback to simple extraction if NLU didn't get them
    extracted_name = nlu_name or extract_name_simple(msg)
    extracted_room = nlu_room or extract_room_simple(msg)

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

        actions = create_combined_confirmation(session)
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

    return True, [text_action(text)]


def create_combined_confirmation(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Create a single combined confirmation message with identity + ticket details.

    Uses temp_guest_name, temp_room, and ticket_draft from session.

    Returns:
        List of actions (WhatsApp messages).
    """
    temp_name = session.get("temp_guest_name", "")
    temp_room = session.get("temp_room", "")
    temp_draft = session.get("ticket_draft", {})

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

    # Update ticket_draft with collected identity data (single source of truth)
    session["ticket_draft"].update({
        "room": temp_room,
        "guest_name": temp_name,
    })

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

    return [text_action(text)]


def create_combined_confirmation_direct(nlu: Any, session: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Create combined confirmation when identity is already in session OR in NLU.

    This is used when guest already has guest_name + room in session or NLU extracted them.

    Returns:
        List of actions (WhatsApp messages).
    """
    # Use NLU data if available, otherwise fall back to session
    nlu_name = getattr(nlu, "name", None)
    nlu_room = getattr(nlu, "room", None)

    guest_name = nlu_name or session.get("guest_name", "")
    room = nlu_room or session.get("room", "")

    area = getattr(nlu, "area", None)
    priority = getattr(nlu, "priority", None) or "MEDIA"
    detail = getattr(nlu, "detail", None) or "Sin detalles"

    # Extraer metadata de routing
    routing_source = getattr(nlu, "routing_source", "llm")
    routing_confidence = getattr(nlu, "routing_confidence", 0.75)
    routing_reason = getattr(nlu, "routing_reason", "LLM classification")

    # =========================================================================
    # CONFIDENCE THRESHOLD: Pedir aclaración si confianza es baja
    # =========================================================================
    CONFIDENCE_THRESHOLD = 0.65

    if not area or routing_confidence < CONFIDENCE_THRESHOLD:
        logger.warning(
            f"[ROUTING] ⚠️ Low confidence ({routing_confidence:.2f}) or missing area → Request clarification",
            extra={
                "area": area,
                "confidence": routing_confidence,
                "threshold": CONFIDENCE_THRESHOLD,
                "will_ask_clarification": True
            }
        )

        # Guardar contexto pendiente
        session["state"] = "GH_AREA_CLARIFICATION"
        session["pending_detail"] = detail
        session["pending_room"] = room
        session["pending_guest_name"] = guest_name

        clarification_text = (
            f"Entiendo que necesitas ayuda con: *{detail}*\n\n"
            "Para asignarlo correctamente, ¿es sobre:\n\n"
            "1️⃣ *Mantenimiento* (técnico/AC/agua/luz)\n"
            "2️⃣ *Housekeeping* (limpieza/toallas/amenities)\n"
            "3️⃣ *Recepción* (pagos/reservas/info)\n"
            "4️⃣ *Otro* (queja/gerencia)\n\n"
            "Responde con el número (1-4)."
        )

        logger.info("[ROUTING] 📋 Requesting area clarification from user")

        return [text_action(clarification_text)]

    # Si confidence OK, continuar con confirmación normal...

    # Map area to friendly name
    area_map = {
        "MANTENCION": "Mantenimiento",
        "HOUSEKEEPING": "Housekeeping",
        "RECEPCION": "Recepción",
        "SUPERVISION": "Supervisión",
        "GERENCIA": "Gerencia",
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
        # Metadata de routing
        "routing_source": routing_source,
        "routing_reason": routing_reason,
        "routing_confidence": routing_confidence,
        "routing_version": "v1",
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

    return [text_action(text)]


def extract_name_simple(msg: str) -> Optional[str]:
    """
    Simple regex-based name extraction fallback.

    Looks for patterns like:
    - "mi nombre es Juan Pérez"
    - "soy María González"
    - "Juan Pérez, habitación 205"

    Returns:
        Extracted name or None.
    """
    msg_lower = msg.lower()

    # Pattern 1: "mi nombre es X" - Stop at common room indicators
    match = re.search(
        r"(?:mi nombre es|me llamo|soy)\s+([a-záéíóúñ\s]+?)(?:\s+(?:de la|en la|habitaci[oó]n|room|hab|y\s+|,|\.)|$)",
        msg_lower,
        re.IGNORECASE
    )
    if match:
        name = match.group(1).strip().title()
        if len(name) > 2:
            logger.debug(f"[EXTRACT] Name extracted (pattern 1): {name}")
            return name

    # Pattern 2: Look for capitalized words (likely a name)
    # e.g., "Juan Pérez habitación 205"
    words = msg.split()
    capitalized = [w for w in words if w and w[0].isupper() and w.lower() not in ["habitación", "habitacion", "room"]]
    if len(capitalized) >= 2:
        name = " ".join(capitalized[:3])  # Max 3 words for name
        logger.debug(f"[EXTRACT] Name extracted (pattern 2): {name}")
        return name

    logger.debug("[EXTRACT] No name pattern matched")
    return None


def extract_room_simple(msg: str) -> Optional[str]:
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
