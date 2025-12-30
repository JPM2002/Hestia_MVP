"""
Stage 3: Menu shortcuts.
Handles quick commands like 'menu', 'inicio', 'start'.
"""
from __future__ import annotations
import logging

from gateway_app.core.conversation.pipeline.stages.base import PipelineStage
from gateway_app.core.conversation.pipeline.context import PipelineContext
from gateway_app.core.conversation.utils.message_parser import is_menu_shortcut
from gateway_app.core.conversation.utils.constants import STATE_INIT
from gateway_app.core.intents.smalltalk_handler import get_menu_message
from gateway_app.core.intents.base import text_action

logger = logging.getLogger(__name__)


class ShortcutStage(PipelineStage):
    """
    Stage 3: Menu shortcuts.

    Handles special commands:
    - menu
    - inicio
    - start
    """

    def should_skip(self, context: PipelineContext) -> bool:
        return not context.message or super().should_skip(context)

    def process(self, context: PipelineContext) -> PipelineContext:
        if self.should_skip(context):
            return context

        self.log_entry(context)

        if is_menu_shortcut(context.message):
            logger.info(
                "[SHORTCUT] Menu shortcut detected",
                extra={"wa_id": context.wa_id, "user_message": context.message}
            )

            context.session["state"] = STATE_INIT
            context.add_action(text_action(get_menu_message(context.session)))
            context.mark_handled()

        self.log_exit(context)
        return context
