"""
Stage 2: Global cancellation check.
Independent of NLU, pattern-based.
"""
from __future__ import annotations
import logging

from gateway_app.core.conversation.pipeline.stages.base import PipelineStage
from gateway_app.core.conversation.pipeline.context import PipelineContext
from gateway_app.core.conversation.utils.message_parser import looks_like_global_cancel
from gateway_app.core.conversation.utils.constants import STATE_NEW
from gateway_app.core.intents.ticket_handler import clear_ticket_draft
from gateway_app.core.intents.base import text_action

logger = logging.getLogger(__name__)


class CancellationStage(PipelineStage):
    """
    Stage 2: Global cancellation check.

    Verifica patterns de cancelación independientes del NLU.
    Si detecta cancelación, limpia draft y termina pipeline.
    """

    def should_skip(self, context: PipelineContext) -> bool:
        """Skip si no hay mensaje o ya fue manejado."""
        return not context.message or super().should_skip(context)

    def process(self, context: PipelineContext) -> PipelineContext:
        if self.should_skip(context):
            return context

        self.log_entry(context)

        if looks_like_global_cancel(context.message):
            logger.info(
                "[CANCELLATION] Global cancel detected",
                extra={"wa_id": context.wa_id, "user_message": context.message}
            )

            # Clear ticket draft
            clear_ticket_draft(context.session)
            context.session["state"] = STATE_NEW

            # Add response
            from gateway_app.services.i18n import get_phrase

            lang = context.session.get("language") or "es"
            context.add_action(text_action(get_phrase("cancel_confirm", lang)))


            # Mark as handled
            context.mark_handled()

        self.log_exit(context)
        return context
