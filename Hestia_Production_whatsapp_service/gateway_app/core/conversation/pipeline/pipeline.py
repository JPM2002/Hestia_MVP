"""
Main conversation pipeline.
Coordinates all stages.
"""
from __future__ import annotations
import logging
from typing import List, Dict, Any, Tuple, Optional

from gateway_app.core.conversation.pipeline.context import PipelineContext
from gateway_app.core.conversation.pipeline.stages.base import PipelineStage
from gateway_app.core.conversation.pipeline.stages.session_stage import SessionStage
from gateway_app.core.conversation.pipeline.stages.cancellation_stage import CancellationStage
from gateway_app.core.conversation.pipeline.stages.shortcut_stage import ShortcutStage
from gateway_app.core.conversation.pipeline.stages.state_routing_stage import StateRoutingStage
from gateway_app.core.conversation.pipeline.stages.nlu_stage import NLUStage
from gateway_app.core.conversation.pipeline.stages.intent_routing_stage import IntentRoutingStage
from gateway_app.core.conversation.pipeline.stages.fallback_stage import FallbackStage

logger = logging.getLogger(__name__)


class ConversationPipeline:
    """
    Main conversation processing pipeline.

    Pipeline flow:
    1. SessionStage        - Session management
    2. CancellationStage   - Global cancellation check
    3. ShortcutStage       - Menu shortcuts
    4. StateRoutingStage   - State-based routing (priority)
    5. NLUStage            - NLU analysis (if needed)
    6. IntentRoutingStage  - Intent-based routing
    7. FallbackStage       - Generic response

    Each stage can mark as handled to skip remaining.
    """

    def __init__(self):
        self.stages: List[PipelineStage] = [
            SessionStage(),
            CancellationStage(),
            ShortcutStage(),
            StateRoutingStage(),
            NLUStage(),
            IntentRoutingStage(),
            FallbackStage(),
        ]

    def process(
        self,
        wa_id: str,
        guest_phone: str,
        guest_name: Optional[str],
        text: str,
        session: Optional[Dict[str, Any]],
        timestamp: Any,
        raw_payload: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Process incoming message through pipeline.

        Args:
            wa_id: WhatsApp contact ID
            guest_phone: Phone number
            guest_name: Guest name (if available)
            text: Message text
            session: Session dict (or None)
            timestamp: Message timestamp
            raw_payload: Raw webhook payload

        Returns:
            (actions, session) tuple
        """

        # Initialize context
        context = PipelineContext(
            wa_id=wa_id,
            guest_phone=guest_phone,
            guest_name=guest_name,
            message=(text or "").strip(),
            timestamp=timestamp,
            raw_payload=raw_payload,
            session=session or {}
        )

        logger.info(
            "[PIPELINE] Processing message",
            extra={
                "wa_id": wa_id,
                "message_length": len(context.message),
                "has_session": session is not None
            }
        )

        # Run through pipeline
        for stage in self.stages:
            try:
                logger.info(
                    f"[PIPELINE] 🔄 BEFORE {stage.name}",
                    extra={
                        "stage": stage.name,
                        "skip_remaining": context.skip_remaining,
                        "actions_count": len(context.actions)
                    }
                )

                context = stage.process(context)

                logger.info(
                    f"[PIPELINE] ✅ AFTER {stage.name}",
                    extra={
                        "stage": stage.name,
                        "skip_remaining": context.skip_remaining,
                        "actions_count": len(context.actions)
                    }
                )

                # If marked to skip, break early
                if context.skip_remaining:
                    logger.info(
                        f"[PIPELINE] Stage {stage.name} handled request, skipping remaining",
                        extra={"stage": stage.name, "wa_id": wa_id}
                    )
                    break

            except Exception as e:
                logger.exception(
                    f"[PIPELINE] ❌ Stage {stage.name} FAILED",
                    exc_info=e,
                    extra={"stage": stage.name, "wa_id": wa_id}
                )
                # Continue to next stage on error
                continue

        logger.info(
            "[PIPELINE] Processing complete",
            extra={
                "wa_id": wa_id,
                "actions_count": len(context.actions),
                "final_state": context.session.get("state")
            }
        )

        return context.actions, context.session
