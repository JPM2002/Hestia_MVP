# gateway_app/blueprints/webhook/routes.py
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from gateway_app.core import message_handler


from flask import (
    jsonify,
    render_template,
    request,
)

from . import bp  # blueprint: url_prefix="/webhook"

from gateway_app.config import cfg
from gateway_app.services import audio as audio_svc
from gateway_app.services import whatsapp_api
from gateway_app.core import state as state_machine

logger = logging.getLogger(__name__)


def _parse_inbound(payload: Dict[str, Any]) -> Tuple[
    Optional[str],  # wa_id
    Optional[str],  # from_number
    Optional[str],  # guest_name
    Dict[str, Any],  # msg_data (may be {})
]:
    """
    Extract basic fields from a WhatsApp Cloud API webhook payload.
    """
    try:
        entry = (payload.get("entry") or [])[0]
        change = (entry.get("changes") or [])[0]
        value = change.get("value") or {}
    except Exception:
        return None, None, None, {}

    contacts = value.get("contacts") or []
    wa_id = None
    guest_name = None
    if contacts:
        contact = contacts[0]
        wa_id = contact.get("wa_id") or contact.get("id")
        profile = contact.get("profile") or {}
        guest_name = profile.get("name")

    messages = value.get("messages") or []
    if not messages:
        # No user message (likely a status update)
        return wa_id, None, guest_name, {}

    msg = messages[0]
    from_number = msg.get("from")
    msg_type = msg.get("type")

    return wa_id or from_number, from_number, guest_name, {
        "msg": msg,
        "value": value,
        "type": msg_type,
    }


@bp.route("/whatsapp", methods=["GET", "POST"])
def whatsapp_webhook():
    """
    Main WhatsApp Cloud webhook endpoint.

    - GET: verification handshake with Meta (hub.mode / hub.verify_token / hub.challenge)
    - POST: incoming messages from guests.
    """
    # -----------------------------
    # 1) Verification handshake (GET)
    # -----------------------------
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        expected = (cfg.WHATSAPP_VERIFY_TOKEN or "").strip()

        logger.info(
            "[WEBHOOK] GET verify",
            extra={
                "mode": mode,
                "token_match": token == expected,
                "expected_set": bool(expected),
            },
        )

        if mode == "subscribe" and token == expected and challenge:
            # Meta expects the challenge string as plain body
            return challenge, 200

        return "Verification failed", 403

    # -----------------------------
    # 2) Incoming messages (POST)
    # -----------------------------
    raw_body = request.get_data(as_text=True)
    logger.info("[WEBHOOK] Raw inbound body: %s", raw_body)

    data = request.get_json(force=True, silent=True) or {}

    wa_id, from_number, guest_name, info = _parse_inbound(data)

    # If no from_number, treat as status / non-message payload and ACK
    if not from_number:
        logger.info("[WEBHOOK] No user message found in payload; acknowledging as status.")
        return jsonify({"status": "ignored", "reason": "no_message"}), 200

    msg = info.get("msg") or {}
    msg_type = info.get("type")
    msg_id = msg.get("id")
    timestamp_str = msg.get("timestamp")

    try:
        ts = (
            datetime.fromtimestamp(int(timestamp_str), tz=timezone.utc)
            if timestamp_str
            else datetime.now(timezone.utc)
        )
    except Exception:
        ts = datetime.now(timezone.utc)

    # Text or audio transcription
    text: str = ""
    if msg_type == "text":
        text = (msg.get("text") or {}).get("body") or ""
    elif msg_type == "audio":
        media_id = (msg.get("audio") or {}).get("id")
        if media_id:
            text = audio_svc.transcribe_whatsapp_audio(media_id, language="es") or ""

    logger.info(
        "[WEBHOOK] Parsed inbound",
        extra={
            "wa_id": wa_id,
            "from": from_number,
            "type": msg_type,
            "text": text,
        },
    )

        # Run high-level message handler (DFA + replies)
    media_id = None
    if msg_type == "audio":
        media_id = (msg.get("audio") or {}).get("id")

    message_handler.handle_guest_message(
        wa_id=wa_id or from_number,
        from_phone=from_number,
        guest_name=guest_name,
        msg_type=msg_type,
        text=text,
        media_id=media_id,
        timestamp=ts,
        raw_payload=data,
    )

    # Mark as read (optional)
    if msg_id:
        try:
            whatsapp_api.mark_message_as_read(msg_id)
        except Exception:
            logger.exception("Failed to mark WhatsApp message as read")

    return jsonify({"status": "ok"}), 200


@bp.route("/test", methods=["POST"])
def test_webhook():
    """
    Simplified test endpoint for simulating WhatsApp messages without real WhatsApp integration.

    Expected JSON payload:
    {
        "phone": "56998765432",
        "text": "Hola, necesito ayuda",
        "name": "Guest Name",  # Optional
        "type": "text"  # Optional: "text" or "audio"
    }

    Returns the bot's responses in the JSON response instead of sending via WhatsApp API.
    """
    data = request.get_json(force=True, silent=True) or {}

    phone = data.get("phone")
    text = data.get("text", "")
    guest_name = data.get("name")
    msg_type = data.get("type", "text")

    if not phone:
        return jsonify({"error": "phone is required"}), 400
    if not text and msg_type == "text":
        return jsonify({"error": "text is required for text messages"}), 400

    logger.info(
        "[TEST WEBHOOK] Simulated message",
        extra={
            "phone": phone,
            "type": msg_type,
            "text": text,
        },
    )

    # Load session and process message through state machine
    session = state_machine.load_session(phone)

    actions, new_session = state_machine.handle_incoming_text(
        wa_id=phone,
        guest_phone=phone,
        guest_name=guest_name,
        text=text,
        session=session,
        timestamp=datetime.now(timezone.utc),
        raw_payload=data,
    )

    # Save the new session
    state_machine.save_session(phone, new_session)

    # Extract bot responses from actions
    bot_responses = []
    for act in actions:
        if act.get("type") == "text":
            bot_responses.append(act.get("text", ""))

    # Return the conversation in the response
    return jsonify({
        "status": "ok",
        "message": "Test message processed",
        "conversation": {
            "user_message": text,
            "bot_responses": bot_responses,
            "session_state": new_session.get("state"),
            "session_data": new_session.get("data", {})
        }
    }), 200


@bp.route("/debug", methods=["GET"])
def webhook_debug_view():
    """
    Simple HTML view to check the webhook is wired (manual browser test).
    """
    return render_template("webhook/webhook_debug.html", payload=None, extra=None)
