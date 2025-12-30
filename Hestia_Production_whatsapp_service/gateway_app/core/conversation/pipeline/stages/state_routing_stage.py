"""
Stage 4: State-based routing.
Routes based on current session state.
"""
from __future__ import annotations
import logging
from typing import Dict, Callable

from gateway_app.core.conversation.pipeline.stages.base import PipelineStage
from gateway_app.core.conversation.pipeline.context import PipelineContext
from gateway_app.core.conversation.utils.constants import (
    STATE_AREA_CLARIFICATION,
    STATE_DETAIL_CLARIFICATION,
    STATE_TICKET_CONFIRM,
    STATE_GUEST_IDENTIFY,
    STATE_NEXT_TICKET_CONFIRM,
)

logger = logging.getLogger(__name__)


class StateRoutingStage(PipelineStage):
    """
    Stage 4: State-based routing.

    States que requieren handling especial:
    - GH_AREA_CLARIFICATION
    - GH_DETAIL_CLARIFICATION
    - GH_TICKET_CONFIRM
    - GH_NEXT_TICKET_CONFIRM
    - GH_IDENTIFY
    """

    def __init__(self):
        super().__init__()
        self.state_handlers: Dict[str, Callable] = {
            STATE_AREA_CLARIFICATION: self._handle_area_clarification,
            STATE_DETAIL_CLARIFICATION: self._handle_detail_clarification,
            STATE_TICKET_CONFIRM: self._handle_ticket_confirm,
            STATE_NEXT_TICKET_CONFIRM: self._handle_next_ticket_confirm,
            STATE_GUEST_IDENTIFY: self._handle_identity,
        }

    def should_skip(self, context: PipelineContext) -> bool:
        """Skip if already handled or no message."""
        return not context.message or super().should_skip(context)

    def process(self, context: PipelineContext) -> PipelineContext:
        if self.should_skip(context):
            return context

        self.log_entry(context)

        state = context.session.get("state")
        handler = self.state_handlers.get(state)

        if handler:
            logger.info(
                f"[STATE_ROUTING] Routing to handler for state: {state}",
                extra={"state": state, "wa_id": context.wa_id}
            )
            handler(context)

        self.log_exit(context)
        return context

    def _handle_area_clarification(self, context: PipelineContext) -> None:
        """Handle area clarification response."""
        from gateway_app.core.intents.identity_handler_clarification import (
            handle_area_clarification_response
        )

        handled, actions = handle_area_clarification_response(
            context.message,
            context.session
        )

        if handled:
            context.actions.extend(actions)
            context.mark_handled()

    def _handle_detail_clarification(self, context: PipelineContext) -> None:
        """Handle detail clarification response."""
        from gateway_app.core.intents.identity_handler_clarification import (
            handle_detail_clarification_response
        )

        handled, actions = handle_detail_clarification_response(
            context.message,
            context.session
        )

        if handled:
            context.actions.extend(actions)
            context.mark_handled()

    def _handle_ticket_confirm(self, context: PipelineContext) -> None:
        """Handle ticket confirmation (yes/no)."""
        from gateway_app.core.intents.ticket_handler import (
            handle_ticket_confirmation_yes_no
        )

        handled, actions = handle_ticket_confirmation_yes_no(
            context.message,
            context.session
        )

        if handled:
            context.actions.extend(actions)
            context.mark_handled()

    def _handle_next_ticket_confirm(self, context: PipelineContext) -> None:
        """Handle multi-ticket confirmation."""
        from gateway_app.core.intents.ticket_handler import is_yes, is_no

        if is_yes(context.message):
            self._create_next_ticket(context)
        elif is_no(context.message):
            self._decline_next_ticket(context)

    def _create_next_ticket(self, context: PipelineContext) -> None:
        """Create next ticket in multi-ticket flow."""
        from gateway_app.services.tickets import create_ticket
        from gateway_app.services import notify
        from gateway_app.core.intents.ticket_handler import ORG_ID_DEFAULT, HOTEL_ID_DEFAULT
        from gateway_app.core.intents.base import text_action
        from gateway_app.core.conversation.utils.area_utils import get_area_name
        from gateway_app.core.conversation.utils.constants import STATE_NEW

        next_ticket = context.session.pop("next_ticket_pending", None)
        remaining_requests = context.session.get("remaining_requests", [])

        if not next_ticket:
            return

        # Remove from remaining
        if remaining_requests:
            remaining_requests = remaining_requests[1:]
            context.session["remaining_requests"] = remaining_requests

        # Create ticket
        area = next_ticket.get("area", "MANTENCION")
        priority = next_ticket.get("priority", "MEDIA")
        detail = next_ticket.get("detail", "")
        room = context.session.get("room", "")
        guest_name = context.session.get("guest_name", "")

        payload = {
            "org_id": ORG_ID_DEFAULT,
            "hotel_id": HOTEL_ID_DEFAULT,
            "area": area,
            "prioridad": priority,
            "detalle": detail,
            "canal_origen": "huesped_whatsapp",
            "ubicacion": room,
            "huesped_id": context.session.get("phone"),
            "huesped_phone": context.session.get("phone"),
            "huesped_nombre": guest_name,
            "routing_source": "clarification",
            "routing_reason": f"Sequential multi-ticket: {area}",
            "routing_confidence": 1.0,
            "routing_version": "v1",
        }

        ticket_id = create_ticket(payload, initial_status="PENDIENTE_APROBACION")

        if ticket_id:
            logger.info(f"[MULTI_TICKET] Ticket {ticket_id} created")
        else:
            logger.error("[MULTI_TICKET] Ticket creation failed")

        # Notify
        notify.notify_internal(
            "ticket_created",
            {
                "ticket_id": ticket_id,
                "payload": payload,
                "wa_id": context.session.get("wa_id"),
                "phone": context.session.get("phone"),
                "guest_name": guest_name,
            }
        )

        # Build response
        area_name = get_area_name(area)

        if ticket_id:
            context.add_action(text_action(
                f"¡Listo! Ya notifiqué al equipo de {area_name} sobre tu solicitud "
                f"en la habitación {room}. Te avisaré cuando esté resuelto. ✅"
            ))
        else:
            context.add_action(text_action(
                "He intentado crear tu ticket, pero hubo un problema con el sistema interno. "
                "El equipo de recepción ha sido notificado."
            ))

        # Check for more tickets
        if remaining_requests:
            next_request = remaining_requests[0]
            next_area = next_request.get("area", "")
            next_detail = next_request.get("detail", "")
            next_area_name = get_area_name(next_area)

            context.add_action(text_action(
                f"\n\n📋 También mencionaste: *{next_detail}* ({next_area_name})\n\n"
                f"¿Quieres que cree esta solicitud también? (Sí/No)"
            ))

            context.session["state"] = STATE_NEXT_TICKET_CONFIRM
            context.session["next_ticket_pending"] = next_request
        else:
            context.session["state"] = STATE_NEW
            context.session.pop("remaining_requests", None)

        context.mark_handled()

    def _decline_next_ticket(self, context: PipelineContext) -> None:
        """User declines to create more tickets."""
        from gateway_app.core.intents.base import text_action
        from gateway_app.core.conversation.utils.constants import STATE_NEW

        context.session.pop("next_ticket_pending", None)
        context.session.pop("remaining_requests", None)
        context.session["state"] = STATE_NEW

        context.add_action(text_action(
            "Perfecto. Si necesitas algo más, escríbeme cuando quieras. 😊"
        ))

        logger.info("[MULTI_TICKET] User declined remaining tickets")
        context.mark_handled()

    def _handle_identity(self, context: PipelineContext) -> None:
        """Handle identity collection (requires NLU first)."""
        # Este handler necesita NLU, así que solo se ejecuta si ya tenemos NLU
        # Si no, dejamos que NLU stage lo procese
        if context.nlu is None:
            # NLU stage will handle this
            return

        from gateway_app.core.intents.identity_handler import handle_guest_identify

        handled, actions = handle_guest_identify(
            context.message,
            context.nlu,
            context.session
        )

        if handled:
            context.actions.extend(actions)
            context.mark_handled()
