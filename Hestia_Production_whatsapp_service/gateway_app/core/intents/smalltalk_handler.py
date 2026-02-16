# gateway_app/core/intents/smalltalk_handler.py
"""
Smalltalk handler - Handles greetings, thanks, and casual conversation.

Extracted from state.py to improve modularity.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from gateway_app.core.intents.base import text_action
from gateway_app.services.i18n import get_phrase, normalize_lang


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
    reply = get_smalltalk_reply(msg, session.get("language"))

    return [text_action(reply)]


def get_smalltalk_reply(original: str, lang: str | None = None) -> str:

    """
    Generate appropriate smalltalk reply based on message content.

    Args:
        original: User's message

    Returns:
        Appropriate reply string
    """
    lower = original.lower()
    l = normalize_lang(lang)

    lang = normalize_lang(session_lang) if 'session_lang' in locals() else "es"


    # Detect greetings
    greeting_patterns = ["hola", "buenos días", "buenas tardes", "buenas noches", "buen día", "hey", "hi", "hello"]
    if any(pattern in lower for pattern in greeting_patterns):
        return get_phrase("smalltalk_greeting", l)


    # Detect thanks
    if "gracia" in lower:
        return get_phrase("smalltalk_thanks", l)


    # Detect positive responses
    if "todo bien" in lower or "todo ok" in lower or "estoy bien" in lower:
        return get_phrase("smalltalk_ok", l)


    # Default smalltalk response
    return get_phrase("smalltalk_default", l)



def get_help_message(session: Dict[str, Any] | None = None) -> str:
    """Get help message (localized)."""
    lang = None
    if session:
        lang = session.get("language")
    return get_phrase("help_message", lang)



def get_initial_greeting(session: Dict[str, Any]) -> str:
    """Get initial greeting message for new conversations (localized)."""
    lang = normalize_lang(session.get("language"))
    name = (session.get("guest_name") or "").strip()
    name_part = f" {name}," if name else ","
    return get_phrase("initial_greeting", lang, name_part=name_part)



def get_menu_message(session: Dict[str, Any]) -> str:
    """Get menu/help options message (localized)."""
    return get_phrase("menu_message", session.get("language"))
