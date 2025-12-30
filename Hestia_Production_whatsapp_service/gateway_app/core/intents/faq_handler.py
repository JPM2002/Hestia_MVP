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

logger = logging.getLogger(__name__)


def get_reception_fallback_message() -> str:
    """
    Generate fallback message for questions without FAQ answer.

    Directs user to contact reception.

    Returns:
        Formatted message to contact reception
    """
    return (
        "No estoy seguro de haber entendido bien. Puedo ayudarte a:\n\n"
        "• Crear solicitudes de mantenimiento, housekeeping o recepción.\n"
        "• Responder preguntas frecuentes sobre el hotel.\n"
        "• Ponerte en contacto con recepción.\n\n"
        "¿Qué necesitas?"
    )


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

    # Intenta FAQ antes del mensaje genérico de "no entendí"
    faq_answer = faq_llm.answer_faq(msg)

    if faq_answer:
        logger.info(
            "[FAQ] ✅ FAQ fallback found answer → TERMINATE",
            extra={
                "decision": "FAQ_FALLBACK_HIT",
                "wa_id": session.get("wa_id"),
                "user_message": msg,
                "answer_preview": faq_answer[:100],
                "location": "gateway_app/core/intents/faq_handler.py"
            }
        )

        session["state"] = "GH_FAQ"

        actions = [
            text_action(faq_answer),
            text_action("¿Puedo ayudarte con algo más durante tu estadía?")
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
        text_action(get_reception_fallback_message())
    ]

    session["state"] = "GH_S0_INIT"

    return False, actions
