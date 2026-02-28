# gateway_app/core/intents/faq_handler.py
"""
FAQ handler - Handles FAQ queries and not_understood intent.

Extracted from state.py to improve modularity.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from gateway_app.core.intents.base import text_action
from gateway_app.services import faq_llm
from gateway_app.services.i18n import get_phrase, detect_language

logger = logging.getLogger(__name__)


def get_reception_fallback_message(lang: str = "es") -> str:
    """
    Generate fallback message for questions without FAQ answer.

    Directs user to contact reception with phone number.

    Returns:
        Formatted message to contact reception
    """
    return get_phrase("reception_fallback", lang)


def handle_faq_fallback(
    msg: str,
    session: Dict[str, Any]
) -> tuple[bool, List[Dict[str, Any]]]:
    """
    Try to answer using FAQ as fallback for not_understood intent.

    Args:
        msg: User message
        session: Current session

    Returns:
        (found_answer: bool, actions: list)
    """
    logger.info(
        "[FAQ] 🔍 Trying FAQ fallback for not_understood message",
        extra={
            "wa_id": session.get("wa_id"),
            "user_message": msg,
            "location": "gateway_app/core/intents/faq_handler.py"
        }
    )

    lang = session.get("language") or detect_language(msg)
    faq_answer, token_usage = faq_llm.answer_faq(msg, session_lang=lang)



    if faq_answer:
        logger.info(
            "[FAQ] ✅ FAQ fallback found answer → TERMINATE",
            extra={
                "decision": "FAQ_FALLBACK_HIT",
                "wa_id": session.get("wa_id"),
                "user_message": msg,
                "answer_preview": faq_answer[:100] if faq_answer else None,
                "token_usage": str(token_usage) if token_usage else None,
                "location": "gateway_app/core/intents/faq_handler.py"
            }
        )

        session["state"] = "GH_FAQ"

        # Store token_usage in session for later logging
        session["_last_faq_token_usage"] = token_usage

        actions = [
            text_action(faq_answer),
            text_action(get_phrase("faq_more_help", lang))
        ]

        return True, actions

    # Si ni siquiera FAQ funciona, derivar a recepción
    logger.info(
        "[FAQ] ⚠️ FAQ fallback missed → Suggest contacting reception",
        extra={
            "decision": "FAQ_FALLBACK_MISS_RECEPTION",
            "wa_id": session.get("wa_id"),
            "user_message": msg,
            "location": "gateway_app/core/intents/faq_handler.py"
        }
    )

    actions = [
        text_action(get_reception_fallback_message(lang))
    ]

    session["state"] = "GH_S0_INIT"

    return False, actions
