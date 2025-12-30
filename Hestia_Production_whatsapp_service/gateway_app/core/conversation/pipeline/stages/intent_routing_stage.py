"""
Stage 6: Intent-based routing.
Routes based on NLU intent.
"""
from __future__ import annotations
import logging
from typing import Dict, Callable

from gateway_app.core.conversation.pipeline.stages.base import PipelineStage
from gateway_app.core.conversation.pipeline.context import PipelineContext
from gateway_app.core.conversation.utils.constants import STATE_INIT, STATE_NEW, CONFIDENCE_THRESHOLD
from gateway_app.core.intents.base import text_action
from gateway_app.core.intents.smalltalk_handler import (
    get_help_message,
    handle_smalltalk,
    get_initial_greeting
)
from gateway_app.core.intents.handoff_handler import handle_handoff_request
from gateway_app.core.intents.ticket_handler import clear_ticket_draft
from gateway_app.core.intents.faq_handler import handle_faq_fallback
from gateway_app.core.intents.identity_handler import (
    has_guest_identity,
    request_guest_identity,
    create_combined_confirmation_direct,
)
from gateway_app.core.conversation.utils.area_utils import build_area_options_text

logger = logging.getLogger(__name__)


class IntentRoutingStage(PipelineStage):
    """
    Stage 6: Intent-based routing.

    Intents:
    - help
    - handoff_request
    - cancel
    - ticket_request
    - general_chat
    - not_understood
    """

    def __init__(self):
        super().__init__()
        self.intent_handlers: Dict[str, Callable] = {
            "help": self._handle_help,
            "handoff_request": self._handle_handoff,
            "cancel": self._handle_cancel,
            "ticket_request": self._handle_ticket_request,
            "general_chat": self._handle_smalltalk,
            "not_understood": self._handle_not_understood,
        }

    def should_skip(self, context: PipelineContext) -> bool:
        """Skip if already handled or no NLU result."""
        if super().should_skip(context):
            return True
        if context.nlu is None:
            return True
        return False

    def process(self, context: PipelineContext) -> PipelineContext:
        if self.should_skip(context):
            return context

        self.log_entry(context)

        intent = context.nlu.intent

        # Check for intent flags first
        if context.nlu.is_help:
            intent = "help"
        elif context.nlu.wants_handoff:
            intent = "handoff_request"
        elif context.nlu.is_cancel:
            intent = "cancel"
        elif context.nlu.is_smalltalk:
            intent = "general_chat"

        handler = self.intent_handlers.get(intent)

        if handler:
            logger.info(
                f"[INTENT_ROUTING] Routing to handler for intent: {intent}",
                extra={"intent": intent, "wa_id": context.wa_id}
            )
            handler(context)

        self.log_exit(context)
        return context

    def _handle_help(self, context: PipelineContext) -> None:
        """Show help message."""
        context.add_action(text_action(get_help_message()))
        context.session["state"] = STATE_INIT
        context.mark_handled()

    def _handle_handoff(self, context: PipelineContext) -> None:
        """Handle human handoff request."""
        actions = handle_handoff_request(context.message, context.session)
        context.actions.extend(actions)
        context.mark_handled()

    def _handle_cancel(self, context: PipelineContext) -> None:
        """Cancel current request."""
        clear_ticket_draft(context.session)
        context.session["state"] = STATE_NEW
        context.add_action(text_action(
            "He cancelado tu solicitud. Si necesitas algo más, "
            "envíame un nuevo mensaje."
        ))
        context.mark_handled()

    def _handle_ticket_request(self, context: PipelineContext) -> None:
        """Handle ticket request workflow."""
        # Check confidence
        routing_confidence = getattr(context.nlu, "routing_confidence", 0.75)
        area = getattr(context.nlu, "area", None)
        multiple_requests = getattr(context.nlu, "multiple_requests", None)

        # Low confidence or missing area → clarification
        if not area or routing_confidence < CONFIDENCE_THRESHOLD:
            self._request_area_clarification(context, multiple_requests)
        # High confidence but missing identity → collect identity
        elif not has_guest_identity(context.session, context.nlu):
            actions = request_guest_identity(context.nlu, context.session)
            context.actions.extend(actions)
            context.mark_handled()
        # Has everything → create confirmation
        else:
            actions = create_combined_confirmation_direct(context.nlu, context.session)
            context.actions.extend(actions)
            context.mark_handled()

    def _request_area_clarification(self, context: PipelineContext, multiple_requests) -> None:
        """Request area clarification from user."""
        logger.warning(
            "[TICKET_WORKFLOW] Low confidence, requesting clarification",
            extra={
                "confidence": getattr(context.nlu, "routing_confidence", None),
                "area": getattr(context.nlu, "area", None)
            }
        )

        context.session["state"] = "GH_AREA_CLARIFICATION"
        context.session["pending_detail"] = getattr(context.nlu, "detail", None)

        # Multi-request handling
        if multiple_requests and isinstance(multiple_requests, list) and len(multiple_requests) >= 2:
            context.session["pending_requests"] = multiple_requests

            # Build requests list
            requests_text = ""
            for i, req in enumerate(multiple_requests, 1):
                area_name = req.get("area", "")
                detail = req.get("detail", "")
                requests_text += f"{i}. *{detail}* ({area_name})\n"

            # Get detected areas
            detected_areas = []
            seen = set()
            for req in multiple_requests:
                req_area = req.get("area", "")
                if req_area and req_area not in seen:
                    detected_areas.append(req_area)
                    seen.add(req_area)

            # Sort by area order
            area_order = {"MANTENCION": 1, "HOUSEKEEPING": 2, "RECEPCION": 3, "GERENCIA": 4}
            detected_areas.sort(key=lambda a: area_order.get(a, 99))

            # Build options
            options_text = build_area_options_text(detected_areas)

            clarification_text = (
                f"Veo que tienes {len(multiple_requests)} necesidades diferentes:\n\n"
                f"{requests_text}\n"
                f"Voy a crear solicitudes separadas para cada una.\n\n"
                f"¿Con cuál quieres empezar?\n\n"
                f"{options_text}\n"
                f"Responde con el número."
            )
        else:
            detail = getattr(context.nlu, "detail", "tu solicitud")
            clarification_text = (
                f"Entiendo que necesitas ayuda con: *{detail}*\n\n"
                "Para asignarlo correctamente, ¿es sobre:\n\n"
                f"{build_area_options_text()}\n\n"
                "Responde con el número (1-4)."
            )

        context.add_action(text_action(clarification_text))
        context.mark_handled()

    def _handle_smalltalk(self, context: PipelineContext) -> None:
        """Handle general chat."""
        new_conversation = context.metadata.get("new_conversation", False)

        if new_conversation:
            context.add_action(text_action(get_initial_greeting(context.session)))
        else:
            actions = handle_smalltalk(context.message, context.session, new_conversation)
            context.actions.extend(actions)

        if context.session.get("state") in {STATE_INIT, "GH_FAQ"}:
            context.session["state"] = STATE_NEW

        context.mark_handled()

    def _handle_not_understood(self, context: PipelineContext) -> None:
        """Handle not understood via FAQ fallback."""
        found_faq, actions = handle_faq_fallback(context.message, context.session)
        context.actions.extend(actions)
        context.mark_handled()
