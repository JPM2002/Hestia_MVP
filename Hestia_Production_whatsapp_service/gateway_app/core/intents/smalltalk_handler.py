# gateway_app/core/intents/smalltalk_handler.py
"""
Smalltalk handler - Handles greetings, thanks, and casual conversation.

Extracted from state.py to improve modularity.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from gateway_app.core.intents.base import text_action

logger = logging.getLogger(__name__)


def handle_smalltalk(
    msg: str,
    session: Dict[str, Any],
    new_conversation: bool = False
) -> List[Dict[str, Any]]:
    """
    Handle smalltalk/general_chat intent.

    Args:
        msg: User message
        session: Current session
        new_conversation: Whether this is a new conversation

    Returns:
        List of actions to send
    """
    # Si es la primera vez que hablamos en esta sesión y ya mandamos
    # el saludo inicial, NO mandamos otro mensaje para evitar el doble texto.
    if new_conversation:
        logger.debug("[SMALLTALK] New conversation, skipping response to avoid duplicate")
        return []

    # En conversaciones ya iniciadas, sí respondemos smalltalk normalmente.
    reply = get_smalltalk_reply(msg)
    return [text_action(reply)]


def get_smalltalk_reply(original: str) -> str:
    """
    Generate appropriate smalltalk reply based on message content.

    Args:
        original: User's message

    Returns:
        Appropriate reply string
    """
    lower = original.lower()

    if "gracia" in lower:
        return "Con gusto, estoy aquí para ayudarte durante tu estadía. ¿Algo más?"

    if "todo bien" in lower or "todo ok" in lower or "estoy bien" in lower:
        return "Perfecto, me alegra saberlo. Si necesitas algo más, solo escribe por aquí."

    return "Entendido. Cualquier cosa que necesites, solo escríbeme por aquí."


def get_help_message() -> str:
    """Get the help message explaining bot capabilities."""
    return (
        "Puedo ayudarte con:\n"
        "• Reportar problemas en tu habitación (aire, ducha, luz, limpieza, etc.).\n"
        "• Pedir toallas, almohadas u otros artículos de housekeeping.\n"
        "• Pedir comida o bebidas a la habitación.\n"
        "• Responder dudas típicas: horario de desayuno, wifi, check-in / check-out.\n\n"
        "Escríbeme en una frase qué necesitas y me encargo del resto."
    )


def get_initial_greeting(session: Dict[str, Any]) -> str:
    """Get initial greeting message for new conversations."""
    name = session.get("guest_name")
    if name:
        prefix = f"Hola {name}, "
    else:
        prefix = "Hola, "

    return (
        prefix
        + "Te damos la bienvenida a nuestro servicio de asistencia digital.\n"
          "Para poder ayudarte rápidamente, por favor indícame tu número de habitación y cuál es tu consulta o solicitud."
    )


def get_menu_message(session: Dict[str, Any]) -> str:
    """Get menu/help options message."""
    return (
        "Menú de ayuda Hestia:\n"
        "1️⃣ Reportar un problema en la habitación (ej: no funciona el aire, falta limpieza).\n"
        "2️⃣ Pedir algo al hotel (toallas, almohadas, amenities, room service).\n"
        "3️⃣ Preguntar información (desayuno, wifi, horarios, etc.).\n\n"
        "Cuéntame brevemente qué necesitas y yo te ayudo."
    )
