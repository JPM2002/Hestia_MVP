# gateway_app/core/intents/smalltalk_handler.py
"""
Smalltalk handler - Handles greetings, thanks, and casual conversation.

Extracted from state.py to improve modularity.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from gateway_app.core.intents.base import text_action

logger = logging.getLogger(__name__)

# Saludos comunes (ES/EN) + variantes
_GREETING_WORDS = {
    "hola",
    "holi",
    "hello",
    "hi",
    "hey",
    "buenas",
    "buenos dias",
    "buenos días",
    "buen dia",
    "buen día",
    "buenas tardes",
    "buenas noches",
}

# Quita puntuación/símbolos, deja letras y espacios (mantiene tildes/ñ)
# Ayuda a detectar saludos "puros", menos latencia y complejidad
def _normalize(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[!¡¿?.,;:()\[\]{}\-—_*~·•«»\"'`´]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_greeting_only(msg: str) -> bool:
    """
    True si el mensaje es esencialmente un saludo (sin contenido extra),
    incluyendo "holaaa", "hola!!", "buenas :)".
    """
    n = _normalize(msg)
    if not n:
        return False

    # "holaaa" / "holaaaaa"
    if re.fullmatch(r"hol+a+", n):
        return True

    return n in _GREETING_WORDS


def handle_smalltalk(
    msg: str,
    session: Dict[str, Any],
    new_conversation: bool = False
) -> List[Dict[str, Any]]:
    """
    Handle smalltalk/general_chat intent.

    Requerimiento #107:
    - En el primer contacto (new_conversation): responder inmediatamente con bienvenida.
    - En conversaciones posteriores: si el huésped SOLO saluda nuevamente, repetir bienvenida.
    - No requerir múltiples intentos.
    """
    # Guard anti-duplicado:
    # Si el welcome ya lo envió el "welcome universal" antes del pipeline (message_handler),
    # entonces no mandamos otro en new_conversation.
    session.setdefault("data", {})
    if new_conversation and session["data"].get("welcome_sent"):
        logger.debug("[SMALLTALK] New conversation but welcome already sent -> skipping")
        return []

    # 1) Primer contacto: enviar bienvenida
    if new_conversation:
        logger.debug("[SMALLTALK] New conversation -> sending initial greeting")
        return [text_action(get_initial_greeting(session))]

    # 2) Si es SOLO un saludo en una conversación ya iniciada: repetir bienvenida
    if _is_greeting_only(msg):
        logger.debug("[SMALLTALK] Greeting-only message -> sending initial greeting")
        return [text_action(get_initial_greeting(session))]

    # 3) Caso normal de smalltalk
    reply = get_smalltalk_reply(msg)
    return [text_action(reply)]


def get_smalltalk_reply(original: str) -> str:
    """
    Generate appropriate smalltalk reply based on message content.
    """
    lower = (original or "").lower()

    # Detect thanks
    if "gracia" in lower:
        return "Con gusto, estoy aquí para ayudarte durante tu estadía. ¿Algo más?"

    # Detect positive responses
    if "todo bien" in lower or "todo ok" in lower or "estoy bien" in lower:
        return "Perfecto, me alegra saberlo. Si necesitas algo más, solo escribe por aquí."

    # Default smalltalk response
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
    """Get initial greeting message (welcome)."""
    name = (session.get("guest_name") or "").strip()
    if name:
        return (
            f"Hola {name}, soy tu asistente virtual del hotel.\n"
            "Puedo ayudarte a reportar problemas en tu habitación y responder preguntas."
        )
    return (
        "Hola, soy tu asistente virtual del hotel.\n"
        "Puedo ayudarte a reportar problemas en tu habitación y responder preguntas."
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
