# gateway_app/blueprints/webhook/routes.py
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from flask import (
    current_app,
    jsonify,
    render_template,
    request,
)

from . import bp  # shared blueprint from __init__.py

from gateway_app.config import cfg
from gateway_app.services import audio as audio_svc
from gateway_app.services import whatsapp_api
from gateway_app.core import state as state_machine

logger = logging.getLogger(__name__)

# Last payload for the debug view
_LAST_PAYLOAD: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_timestamp(ts: Optional[str]) -> datetime:
    """
    Parse WhatsApp's timestamp (string with seconds since epoch) into a UTC datetime.
    """
    if not ts:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except Exception:
        logger.warning("Could not parse WA timestamp %r, using now()", ts, exc_info=True)
        return datetime.now(timezone.utc)


def _extract_message(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract the first message from a WhatsApp webhook payload.

    Returns a dict with:
        wa_id, from_number, name, msg_id, timestamp, msg_type,
        text, audio_media_id, raw
    or None if no message is present.
    """
    try:
        if body.get("object") != "whatsapp_business_account":
            return None

        entry_list = body.get("entry") or []
        if not entry_list:
            return None
        entry = entry_list[0]

        changes = entry.get("changes") or []
        if not changes:
            return None
        change = changes[0]

        value = change.get("value") or {}
        contacts = value.get("contacts") or []
        contact = contacts[0] if contacts else {}

        messages = value.get("messages") or []
        if not messages:
            # Could be a status update, etc.
            return None
        msg = messages[0]

        from_number = msg.get("from")
        msg_id = msg.get("id")
        msg_type = msg.get("type")
        ts = msg.get("timestamp")

        profile = contact.get("profile") or {}
        name = profile.get("name")
        wa_id = contact.get("wa_id") or from_number

        text_body: Optional[str] = None
        audio_media_id: Optional[str] = None

        if msg_type == "text":
            text_body = (msg.get("text") or {}).get("body")
        elif msg_type == "audio":
            audio_media_id = (msg.get("audio") or {}).get("id")

        return {
            "wa_id": wa_id,
            "from_number": from_number,
            "name": name,
            "msg_id": msg_id,
            "timestamp": ts,
            "msg_type": msg_type,
            "text": text_body,
            "audio_media_id": audio_media_id,
            "raw": msg,
        }
    except Exception:
        logger.exception("Error extracting WhatsApp message from payload")
        return None


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@bp.get("/health")
def health() -> Any:
    """
    Simple health endpoint for Render / monitoring.
    """
    return jsonify(
        {
            "status": "ok",
            "service": "hestia-whatsapp-gateway",
            "env": current_app.config.get("ENV"),
        }
    )


# ---------------------------------------------------------------------------
# Webhook verification (GET) for Meta / WhatsApp
# ---------------------------------------------------------------------------


@bp.get("/")
def verify_webhook() -> Any:
    """
    GET /webhook

    Used by Meta to verify the webhook when you configure it in the dashboard.

    Meta sends:
      hub.mode=subscribe
      hub.verify_token=...
      hub.challenge=...

    We must echo hub.challenge if verify_token matches our WHATSAPP_VERIFY_TOKEN.
    """
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    expected_token = (cfg.WHATSAPP_VERIFY_TOKEN or "").strip()

    if mode == "subscribe" and token and token == expected_token:
        logger.info("Webhook verified successfully by Meta.")
        return (challenge or ""), 200

    logger.warning(
        "Webhook verification failed: mode=%r token=%r", mode, token
    )
    return "Verification token mismatch", 403


# ---------------------------------------------------------------------------
# Main WhatsApp webhook (POST)
# ---------------------------------------------------------------------------


@bp.post("/")
def handle_webhook() -> Any:
    """
    POST /webhook

    Main entrypoint for WhatsApp message events.
    """
    global _LAST_PAYLOAD

    body = request.get_json(force=True, silent=True) or {}
    _LAST_PAYLOAD = json.dumps(body, ensure_ascii=False, indent=2)

    logger.info(
        "[WEBHOOK] inbound payload",
        extra={"payload": body},
    )

    # Extract a single message (we ignore multiple messages in a single delivery for now)
    msg_info = _extract_message(body)
    if not msg_info:
        # Could be a status or unsupported event; we acknowledge anyway.
        return jsonify({"status": "ignored"}), 200

    wa_id = msg_info["wa_id"]
    from_number = msg_info["from_number"]
    guest_name = msg_info["name"]
    msg_id = msg_info["msg_id"]
    msg_type = msg_info["msg_type"]
    ts_raw = msg_info["timestamp"]
    audio_media_id = msg_info["audio_media_id"]
    text = msg_info["text"] or ""

    received_at = _parse_timestamp(ts_raw)

    # If this is audio, transcribe it
    if msg_type == "audio" and audio_media_id:
        logger.info(
            "[WEBHOOK] audio message received, starting transcription",
            extra={"wa_id": wa_id, "media_id": audio_media_id},
        )
        transcript = audio_svc.transcribe_whatsapp_audio(
            media_id=audio_media_id,
            language="es",
        )
        if transcript:
            text = transcript
        else:
            # No transcript → keep empty text; state machine will handle accordingly.
            text = ""

    # Load existing session (if any)
    session = state_machine.load_session(wa_id)

    # Pass to state machine
    actions, new_session = state_machine.handle_incoming_text(
        wa_id=wa_id,
        guest_phone=from_number,
        guest_name=guest_name,
        text=text,
        session=session,
        timestamp=received_at,
        raw_payload=body,
    )

    # Persist session
    state_machine.save_session(wa_id, new_session)

    # Execute outgoing actions
    for action in actions:
        if action.get("type") == "text":
            out_text = action.get("text") or ""
            preview = bool(action.get("preview_url", False))
            try:
                whatsapp_api.send_text_message(
                    to=from_number,
                    text=out_text,
                    preview_url=preview,
                )
            except Exception:
                logger.exception(
                    "Failed to send WhatsApp text message",
                    extra={"wa_id": wa_id, "to": from_number},
                )

    # Mark incoming message as read (best-effort)
    if msg_id:
        try:
            whatsapp_api.mark_message_as_read(msg_id)
        except Exception:
            logger.exception(
                "Failed to mark WhatsApp message as read",
                extra={"wa_id": wa_id, "message_id": msg_id},
            )

    return jsonify({"status": "ok"}), 200


# ---------------------------------------------------------------------------
# Debug view (browser)
# ---------------------------------------------------------------------------


@bp.get("/debug")
def webhook_debug() -> Any:
    """
    Simple HTML page to inspect the last webhook payload received.

    Useful to open in a browser while testing:
      GET /webhook/debug
    """
    payload = _LAST_PAYLOAD or ""
    extra = {
        "env": current_app.config.get("ENV"),
        "debug": current_app.config.get("DEBUG"),
    }
    return render_template(
        "webhook/webhook_debug.html",
        payload=payload,
        extra=json.dumps(extra, ensure_ascii=False, indent=2),
    )
