# gateway_app/core/conversation/orchestrator.py
"""
Conversation orchestrator - Main entry point for message processing.

REFACTORED: Now uses pipeline architecture for modularity and maintainability.

Previous version: 626 lines with monolithic routing logic.
Current version: ~50 lines delegating to ConversationPipeline.

The pipeline processes messages through 7 stages:
1. SessionStage        - Session management
2. CancellationStage   - Global cancellation check
3. ShortcutStage       - Menu shortcuts
4. StateRoutingStage   - State-based routing
5. NLUStage            - NLU analysis
6. IntentRoutingStage  - Intent routing
7. FallbackStage       - Generic fallback

Each stage is independently testable and maintainable.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Tuple

from gateway_app.core.conversation.pipeline.pipeline import ConversationPipeline

logger = logging.getLogger(__name__)

# Global pipeline instance (singleton)
_pipeline = ConversationPipeline()


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

    REFACTORED: Now delegates to ConversationPipeline.
    Maintains 100% backward compatibility with existing code.

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
        - outgoing_actions: List of action dicts (type, text, etc.)
        - new_session: Updated session dict
    """
    return _pipeline.process(
        wa_id=wa_id,
        guest_phone=guest_phone,
        guest_name=guest_name,
        text=text,
        session=session,
        timestamp=timestamp,
        raw_payload=raw_payload
    )
