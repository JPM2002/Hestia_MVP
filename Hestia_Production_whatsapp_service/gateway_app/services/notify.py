# gateway_app/services/notify.py
"""
Internal notification helpers for the WhatsApp gateway.

Responsibilities:
- Provide a unified way to send internal notifications (errors, debug, events)
  to another service (Slack bridge, core Hestia app, etc.).
- If INTERNAL_NOTIFY_URL is not configured, notifications are logged only.

Environment:
- INTERNAL_NOTIFY_TOKEN: bearer token for auth (optional but recommended).
- INTERNAL_NOTIFY_URL: HTTP endpoint to receive notifications (optional).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

INTERNAL_NOTIFY_URL = os.getenv("INTERNAL_NOTIFY_URL")
INTERNAL_NOTIFY_TOKEN = os.getenv("INTERNAL_NOTIFY_TOKEN")
DEFAULT_TIMEOUT = 5


def _headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if INTERNAL_NOTIFY_TOKEN:
        headers["Authorization"] = f"Bearer {INTERNAL_NOTIFY_TOKEN}"
    return headers


def notify_internal(event: str, payload: Optional[Dict[str, Any]] = None) -> None:
    """
    Generic internal notification.

    Args:
        event: Short event type label (e.g., "whatsapp_inbound", "ticket_created", "error").
        payload: Optional structured payload (dict) with extra data.

    Behavior:
    - If INTERNAL_NOTIFY_URL is set, POSTs JSON to that endpoint.
    - Otherwise, logs the event at INFO level.
    """
    data = {
        "event": event,
        "payload": payload or {},
    }

    if not INTERNAL_NOTIFY_URL:
        # Fallback: just log
        logger.info("Internal notify (no URL configured): %s", data)
        return

    try:
        resp = requests.post(
            INTERNAL_NOTIFY_URL,
            headers=_headers(),
            json=data,
            timeout=DEFAULT_TIMEOUT,
        )
        if not resp.ok:
            logger.warning(
                "Internal notify failed %s: %s",
                resp.status_code,
                resp.text[:500],
            )
    except Exception:
        logger.exception("Internal notify request error")


def notify_error(message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    """
    Convenience helper for error notifications.
    """
    payload = {"message": message}
    if extra:
        payload["extra"] = extra
    notify_internal("error", payload)


def notify_debug(message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    """
    Convenience helper for debug / trace notifications.
    """
    payload = {"message": message}
    if extra:
        payload["extra"] = extra
    notify_internal("debug", payload)

def _auto_assign_and_notify(ticket_id, area, prioridad, detalle, ubicacion, org_id, hotel_id):
    """
    Compatibility helper used by gateway_app.services.tickets.create_ticket.

    In the original monolith this would:
      - auto-assign the ticket to a technician based on org/hotel/area
      - send WhatsApp/Slack/email notifications

    For the gateway, we implement a minimal version:
      - just emit an internal notification so the rest of the system can react.

    You can later expand this to real auto-assignment logic.
    """
    from gateway_app.services.notify import notify_internal  # local import to avoid cycles

    payload = {
        "ticket_id": ticket_id,
        "area": area,
        "prioridad": prioridad,
        "detalle": detalle,
        "ubicacion": ubicacion,
        "org_id": org_id,
        "hotel_id": hotel_id,
    }

    try:
        # Event name is arbitrary; reuse or rename as you wish
        notify_internal("ticket_auto_assigned", payload)
    except Exception as e:
        logger.warning("[WARN] _auto_assign_and_notify failed: %s", e)
