# gateway_app/core/intents/handoff_handler.py
"""
Handoff handler - Handles requests to speak with human agent.

Extracted from state.py to improve modularity.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from gateway_app.core.intents.base import text_action
from gateway_app.services import notify

logger = logging.getLogger(__name__)


def handle_handoff_request(
    msg: str,
    session: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Handle request to speak with human/reception.

    Args:
        msg: User message
        session: Current session

    Returns:
        List of actions to send
    """
    logger.info(
        "[HANDOFF] ✅ DECISION: Intent=HANDOFF → Transfer to human",
        extra={
            "decision": "INTENT_HANDOFF",
            "wa_id": session.get("wa_id"),
            "user_message": msg,
            "location": "gateway_app/core/intents/handoff_handler.py"
        }
    )

    session["state"] = "GH_HANDOFF"

    # Notify internal team
    notify.notify_internal(
        "handoff_request",
        {
            "wa_id": session.get("wa_id"),
            "phone": session.get("phone"),
            "guest_name": session.get("guest_name"),
            "last_message": msg,
        },
    )

    return [
        text_action(
            "De acuerdo, te pongo en contacto con recepción humana. "
            "Un momento por favor."
        )
    ]
