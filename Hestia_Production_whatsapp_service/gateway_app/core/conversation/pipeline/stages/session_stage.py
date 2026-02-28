"""
Stage 1: Session management.
Ensures session exists and is updated.
"""
from __future__ import annotations
import logging

from gateway_app.core.conversation.pipeline.stages.base import PipelineStage
from gateway_app.core.conversation.pipeline.context import PipelineContext
from gateway_app.core.conversation.session import new_session
from gateway_app.core.timefmt import utcnow
from gateway_app.services.i18n import detect_language

logger = logging.getLogger(__name__)


class SessionStage(PipelineStage):
    """
    Stage 1: Session management.

    Responsabilidades:
    - Crear session si no existe
    - Actualizar campos de session
    - Setear last_message_at
    """

    def process(self, context: PipelineContext) -> PipelineContext:
        self.log_entry(context)

        # Create session if doesn't exist
        if not context.session or not isinstance(context.session, dict):
            context.session = new_session(
                wa_id=context.wa_id,
                guest_phone=context.guest_phone,
                guest_name=context.guest_name,
                timestamp=context.timestamp
            )
            context.metadata["new_conversation"] = True
            logger.info(f"[SESSION] Created new session for {context.wa_id}")
        else:
            # Update existing session
            context.session.setdefault("wa_id", context.wa_id)
            context.session.setdefault("phone", context.guest_phone)
            context.session.setdefault("data", {})
            context.metadata["new_conversation"] = False

        # Update guest name if provided
        context.session["guest_name"] = context.guest_name or context.session.get("guest_name")

        # Update last message timestamp
        context.session["last_message_at"] = utcnow().isoformat()

        # Store detected language in session (best-effort) — but keep session language sticky
        if context.message:
            detected = detect_language(
                context.message,
                default=context.session.get("language") or "es",
            )
            context.session["detected_language_last"] = detected

            # Sticky session language:
            # - If user explicitly changed language, do NOT override it.
            # - Otherwise set it only once (first message) and keep consistent.
            if context.session.get("language_source") == "explicit":
                pass
            else:
                if not context.session.get("language"):
                    context.session["language"] = detected
                    context.session["language_source"] = "auto"


        # Ensure state exists
        if "state" not in context.session:
            context.session["state"] = "GH_S0_INIT"

        self.log_exit(context)
        return context
