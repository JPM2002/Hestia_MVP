# gateway_app/services/whatsapp_api.py
"""
Thin wrapper around the WhatsApp Cloud API.

This module centralizes all outbound WhatsApp calls so that:
- blueprints just call helper functions (send text, templates, etc.)
- we can later swap providers or add logging / retries in one place.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import requests

from gateway_app.config import cfg

logger = logging.getLogger(__name__)

WHATSAPP_API_BASE = "https://graph.facebook.com/v21.0"


class WhatsAppError(RuntimeError):
    """Raised when WhatsApp API returns an error response."""


def _get_headers() -> Dict[str, str]:
    if not cfg.WHATSAPP_CLOUD_TOKEN:
        logger.error("WHATSAPP_CLOUD_TOKEN is not configured.")
    return {
        "Authorization": f"Bearer {cfg.WHATSAPP_CLOUD_TOKEN}",
        "Content-Type": "application/json",
    }


def _messages_url() -> str:
    if not cfg.WHATSAPP_CLOUD_PHONE_ID:
        logger.error("WHATSAPP_CLOUD_PHONE_ID is not configured.")
    return f"{WHATSAPP_API_BASE}/{cfg.WHATSAPP_CLOUD_PHONE_ID}/messages"


def _handle_response(resp: requests.Response) -> Dict[str, Any]:
    try:
        data = resp.json()
    except Exception:
        logger.exception("Failed to decode WhatsApp response JSON")
        resp.raise_for_status()
        # If raise_for_status doesn't raise, still raise a generic error
        raise WhatsAppError("WhatsApp response is not valid JSON")

    if not resp.ok:
        logger.error("WhatsApp API error %s: %s", resp.status_code, json.dumps(data))
        raise WhatsAppError(f"WhatsApp API error {resp.status_code}: {data}")

    return data


def send_text_message(
    to: str,
    body: str,
    preview_url: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Send a simple text message via WhatsApp Cloud API.

    :param to: WhatsApp recipient id (phone number in international format).
    :param body: Message text.
    :param preview_url: Whether to allow link previews.
    :param metadata: Optional extra info to log (e.g., ticket id, org id).
    :return: Parsed JSON response.
    """
    payload: Dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {
            "body": body,
            "preview_url": preview_url,
        },
    }

    log_extra = metadata.copy() if metadata else {}
    log_extra.update({"to": to, "length": len(body)})

    logger.info("Sending WhatsApp text", extra=log_extra)

    resp = requests.post(_messages_url(), headers=_get_headers(), json=payload, timeout=15)
    return _handle_response(resp)


def send_interactive_message(
    to: str,
    interactive: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Send an interactive message (buttons, list, etc.).

    `interactive` should follow WhatsApp Cloud API format, e.g.:

    {
        "type": "button",
        "body": {"text": "Choose an option:"},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": "opt_1", "title": "Option 1"}},
                ...
            ]
        },
    }
    """
    payload: Dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": interactive,
    }

    log_extra = metadata.copy() if metadata else {}
    log_extra.update({"to": to, "interactive_type": interactive.get("type")})

    logger.info("Sending WhatsApp interactive message", extra=log_extra)

    resp = requests.post(_messages_url(), headers=_get_headers(), json=payload, timeout=15)
    return _handle_response(resp)


def send_template_message(
    to: str,
    template_name: str,
    language_code: str = "es",
    components: Optional[list[Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Send a template message (pre-approved by Meta).

    :param to: Recipient WA id.
    :param template_name: Name of the approved template.
    :param language_code: Language code, e.g., 'es', 'en_US'.
    :param components: Optional list of template components.
    """
    template: Dict[str, Any] = {
        "name": template_name,
        "language": {"code": language_code},
    }
    if components:
        template["components"] = components

    payload: Dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": template,
    }

    log_extra = metadata.copy() if metadata else {}
    log_extra.update({"to": to, "template": template_name})

    logger.info("Sending WhatsApp template", extra=log_extra)

    resp = requests.post(_messages_url(), headers=_get_headers(), json=payload, timeout=15)
    return _handle_response(resp)


def mark_message_read(message_id: str) -> Dict[str, Any]:
    """
    Mark an incoming message as 'read' in WhatsApp.

    This is optional but keeps the WA UI tidy.
    """
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }

    logger.info("Marking WhatsApp message as read", extra={"message_id": message_id})

    resp = requests.post(_messages_url(), headers=_get_headers(), json=payload, timeout=15)
    return _handle_response(resp)
