# gateway_app/services/notify.py
"""
Internal notification helpers for Hestia.

This module sends simple JSON events to an internal endpoint so that
the main Hestia system (or any other backend) can react to WhatsApp
events: new tickets, handoff requests, errors, etc.

Environment variables used:

- INTERNAL_NOTIFY_TOKEN : shared secret / bearer token for auth
- INTERNAL_NOTIFY_URL   : base URL for the internal notification endpoint
                          e.g. "https://thehestia.cl/internal/notify"

If INTERNAL_NOTIFY_URL is not set, notifications are logged but not sent.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

INTERNAL_NOTIFY_TOKEN = os.getenv("INTERNAL_NOTIFY_TOKEN") or ""
INTERNAL_NOTIFY_URL = (os.getenv("INTERNAL_NOTIFY_URL") or "").rstrip("/")


class NotifyError(RuntimeError):
    """Raised for internal notification issues."""


def _headers() -> Dict[str, str]:
    headers: Dict[str, str] = {
        "Content-Type": "application/json",
    }
    if INTERNAL_NOTIFY_TOKEN:
        headers["Authorization"] = f"Bearer {INTERNAL_NOTIFY_TOKEN}"
    return headers


def _endpoint() -> Optional[str]:
    """
    Returns the full URL to POST notifications to, or None if not configured.

    By default we expect INTERNAL_NOTIFY_URL to be the full URL already.
    If you prefer a base URL + fixed path, you can change this to:

        base = (os.getenv("INTERNAL_NOTIFY_URL") or "").rstrip("/")
        return f"{base}/internal/notify"

    and set INTERNAL_NOTIFY_URL to the base domain.
    """
    if not INTERNAL_NOTIFY_URL:
        return None
    return INTERNAL_NOTIFY_URL


def send_internal_notification(event: str, payload: Dict[str, Any]) -> None:
    """
    Low-level helper: send a generic event + payload to the internal backend.

    Args:
        event: Short event name, e.g., "ticket_created", "handoff_requested".
        payload: Arbitrary JSON-serializable dict with extra data.

    Behavior:
        - If INTERNAL_NOTIFY_URL is not set, logs a warning and returns.
        - Logs errors but does not raise by default, to avoid breaking
          the WhatsApp webhook flow.
    """
    url = _endpoint()
    if not url:
        logger.warning(
            "INTERNAL_NOTIFY_URL not configured; skipping internal notification.",
            extra={"event": event, "payload": payload},
        )
        return

    body = {
        "event": event,
        "payload": payload,
    }

    try:
        resp = requests.post(url, json=body, headers=_headers(), timeout=5)
    except Exception as exc:
        logger.exception(
            "Failed to send internal notification",
            extra={"event": event, "payload": payload},
        )
        return

    if not resp.ok:
        logger.error(
            "Internal notification error %s: %s",
            resp.status_code,
            resp.text,
            extra={"event": event, "payload": payload},
        )


# ---------- Convenience wrappers (optional, can be extended) ----------


def notify_ticket_created(ticket_id: Any, wa_id: str, room: str | None,
                          area: str | None, priority: str | None,
                          summary: str | None = None) -> None:
    """
    Notify the internal system that a new ticket was created from WhatsApp.
    """
    send_internal_notification(
        "ticket_created",
        {
            "ticket_id": ticket_id,
            "wa_id": wa_id,
            "room": room,
            "area": area,
            "priority": priority,
            "summary": summary,
        },
    )


def notify_handoff_requested(wa_id: str, message: str, room: str | None = None) -> None:
    """
    Notify that the guest requested to talk to a human / reception.
    """
    send_internal_notification(
        "handoff_requested",
        {
            "wa_id": wa_id,
            "room": room,
            "message": message,
        },
    )


def notify_error(message: str, context: Optional[Dict[str, Any]] = None) -> None:
    """
    Notify about an internal error related to the WhatsApp gateway.
    Useful for ops / monitoring.
    """
    send_internal_notification(
        "gateway_error",
        {
            "message": message,
            "context": context or {},
        },
    )
