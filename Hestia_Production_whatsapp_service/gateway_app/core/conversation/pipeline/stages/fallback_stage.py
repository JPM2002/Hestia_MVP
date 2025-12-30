"""
Stage 7: Final fallback.
Generic response if nothing else handled the message.
"""
from __future__ import annotations
import logging

from gateway_app.core.conversation.pipeline.stages.base import PipelineStage
from gateway_app.core.conversation.pipeline.context import PipelineContext
from gateway_app.core.intents.base import text_action

logger = logging.getLogger(__name__)


class FallbackStage(PipelineStage):
    """
    Stage 7: Final fallback.

    Respuesta genérica si ningún stage anterior manejó el mensaje.
    """

    def should_skip(self, context: PipelineContext) -> bool:
        """Solo ejecutar si NO fue manejado y NO hay acciones."""
        return context.handled or len(context.actions) > 0

    def process(self, context: PipelineContext) -> PipelineContext:
        if self.should_skip(context):
            return context

        self.log_entry(context)

        logger.warning(
            "[FALLBACK] No handler processed message, using fallback",
            extra={"wa_id": context.wa_id, "message": context.message}
        )

        context.add_action(text_action(
            "Gracias por tu mensaje. Si quieres, puedes contarme si "
            "necesitas reportar un problema, pedir algo a la habitación "
            "o hacer una pregunta sobre el hotel."
        ))

        self.log_exit(context)
        return context
