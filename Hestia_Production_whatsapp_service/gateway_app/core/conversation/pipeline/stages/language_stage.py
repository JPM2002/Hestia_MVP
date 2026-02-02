# gateway_app/core/conversation/pipeline/stages/language_stage.py
from __future__ import annotations

import logging

from gateway_app.core.conversation.pipeline.stages.base import PipelineStage
from gateway_app.core.conversation.pipeline.context import PipelineContext
from gateway_app.core.intents.base import text_action
from gateway_app.services.i18n import detect_language_command, get_phrase, normalize_lang

logger = logging.getLogger(__name__)


class LanguageStage(PipelineStage):
    """
    Stage: Explicit language command guard.

    If user says "english please" / "in english" / "português" / "español", we:
    - Set session["language"] with source "explicit"
    - Respond with a confirmation message
    - Do NOT go through FAQ/NLU/tickets for that turn
    """

    def should_skip(self, context: PipelineContext) -> bool:
        return not context.message or super().should_skip(context)

    def process(self, context: PipelineContext) -> PipelineContext:
        if self.should_skip(context):
            return context

        self.log_entry(context)

        cmd = detect_language_command(context.message)
        if not cmd:
            self.log_exit(context)
            return context

        prev = context.session.get("language")
        context.session["language"] = normalize_lang(cmd)
        context.session["language_source"] = "explicit"
        context.session["language_override_source"] = "explicit_command"

        logger.info(
            "[LANG] Explicit language command detected",
            extra={
                "wa_id": context.wa_id,
                "user_message": context.message,
                "previous_language": prev,
                "new_language": context.session["language"],
            },
        )

        context.add_action(text_action(get_phrase("language_switch_confirm", context.session["language"])))
        context.mark_handled()

        self.log_exit(context)
        return context
