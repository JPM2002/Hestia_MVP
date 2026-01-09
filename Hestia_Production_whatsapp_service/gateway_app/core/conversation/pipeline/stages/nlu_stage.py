"""
Stage 5: NLU analysis.
Runs only if not already handled by state routing.
"""
from __future__ import annotations
import logging

from gateway_app.core.conversation.pipeline.stages.base import PipelineStage
from gateway_app.core.conversation.pipeline.context import PipelineContext
from gateway_app.core.models import NLUResult
from gateway_app.services import guest_llm

logger = logging.getLogger(__name__)


class NLUStage(PipelineStage):
    """
    Stage 5: NLU analysis.

    Ejecuta análisis de intención del usuario usando LLM.
    Solo se ejecuta si el mensaje no fue manejado por stages anteriores.
    """

    def should_skip(self, context: PipelineContext) -> bool:
        """Skip if already handled or no message."""
        if super().should_skip(context):
            return True
        if not context.message:
            return True
        return False

    def process(self, context: PipelineContext) -> PipelineContext:
        if self.should_skip(context):
            return context

        self.log_entry(context)

        logger.info(
            "[NLU] Running NLU analysis",
            extra={
                "wa_id": context.wa_id,
                "state": context.session.get("state"),
                "user_message": context.message  # Changed from 'message' to avoid LogRecord conflict
            }
        )

        try:
            nlu_raw = guest_llm.analyze_guest_message(
                context.message,
                session=context.session,
                state=context.session.get("state")
            )

            context.nlu = NLUResult.from_dict(nlu_raw) if nlu_raw else NLUResult()

            # Store full NLU result in session for logging (including token_usage)
            context.session["_nlu_result"] = nlu_raw

            logger.info(
                "[NLU] Analysis complete",
                extra={
                    "wa_id": context.wa_id,
                    "intent": context.nlu.intent,
                    "area": getattr(context.nlu, "area", None),
                    "confidence": getattr(context.nlu, "routing_confidence", None)
                }
            )
        except Exception as e:
            logger.exception("[NLU] Failed to analyze message", exc_info=e)
            # Continue with empty NLU result
            context.nlu = NLUResult()

        self.log_exit(context)
        return context
