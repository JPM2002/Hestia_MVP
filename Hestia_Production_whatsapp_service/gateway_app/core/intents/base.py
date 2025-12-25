# gateway_app/core/intents/base.py
"""
Base types and utilities for intent handlers.
"""
from __future__ import annotations

from typing import Any, Dict, List, Protocol


class IntentHandler(Protocol):
    """
    Protocol defining the interface for intent handlers.

    All intent handlers should follow this interface for consistency.
    """

    def handle(
        self,
        msg: str,
        nlu: Any,
        session: Dict[str, Any],
        **kwargs
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Handle the intent and return actions + updated session.

        Args:
            msg: User message text
            nlu: NLU result object
            session: Current session dict
            **kwargs: Additional context

        Returns:
            Tuple of (actions, updated_session)
        """
        ...


def text_action(text: str, preview_url: bool = False) -> Dict[str, Any]:
    """Helper to create a text action."""
    return {
        "type": "text",
        "text": text,
        "preview_url": preview_url,
    }
