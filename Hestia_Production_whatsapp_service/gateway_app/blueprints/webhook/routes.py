# gateway_app/blueprints/webhook/routes.py
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
)

from gateway_app.config import cfg
from gateway_app.services import audio as audio_svc
from gateway_app.services import whatsapp_api
from gateway_app.core import state as state_machine

bp = Blueprint("webhook", __name__, url_prefix="/webhook")

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Meta / debug
# -------------------------------------------------------------------


@bp.get("/debug")
def webhook_debug_page():
    """
    Simple debug page so we can hit the service in a browser
    and confirm it's alive / inspect basic info.
    """
    return render_template("webhook/webhook_debug.html")


# -------------------------------------------------------------------
# Meta: healthcheck (optional but useful for Render)
# -------------------------------------------------------------------


@bp.get("/health")
def healthcheck():
    return jsonify({"status": "ok"}), 200


# -------------------------------------------------------------------
# WhatsApp Webhook verification (GET)
# -------------------------------------------------------------------


@bp.get("/")
def verify_webhook():
    """
    Facebook / WhatsApp webhook verification handshake.

    Meta query parameters:
      - hub.mode
      - hub.verify_token
      - hub.challenge
    """
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    logger.info(
        "Webhook verify request",
        extra={"mode": mode, "token": token, "has_challenge": bool(challenge)},
    )

    if mode == "subscribe" and token == cfg.WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verification succeeded.")
        # Facebook expects the raw challenge as the body.
        return challenge or "", 200

    logger.warning(
        "Webhook verification failed",
        extra={"mode": mode, "token": token},
    )
    return "Forbidden", 403


# -------------------------------------------------------------------
# WhatsApp Webhook inbound (POST)
# -------------------------------------------------------------------


@bp.post("/")
def handle_webhook():
    """
    Main WhatsApp webhook endpoint.

    Responsibilities:
    - Parse the raw webhook payload.
    - Extract the single message (we assume 1 message per callback).
    - If it's audio → download + transcribe.
    - Hand off the final text + metadata to the state machine.
    - Send all responses back via WhatsApp Cloud API.
    """
    raw_body = request.get_data(as_text=True)
    logger.debug("[WEBHOOK] Raw inbound body: %s", raw_body)

    try:
        payload = request.get_json(force=True)
    except Exception:
        logger.exception("Invalid JSON payload in WhatsApp webhook.")
        return jsonify({"error": "invalid_json"}), 400

    msg_info = _extract_single_message(payload)
    if msg_info is None:
        # Not a message event we care about (e.g., status updates)
        logger.info("No usable message found in webhook payload; ignoring.")
        return jsonify({"status": "ignored"}), 200

    wa_from = msg_info["from"]
    wa_contact_id = msg_info["wa_id"]
    guest_name = msg_info["name"]
    msg_type = msg_info["type"]
    msg_id = msg_info["id"]
    ts = msg_info["timestamp"]
    text = msg_info["text"]
    audio_media_id = msg_info["audio_media_id"]

    logger.info(
        "[IN ← %s] type=%s text=%r audio_id=%r",
        wa_from,
        msg_type,
        text,
        audio_media_id,
    )

    # Mark message as read (best-effort)
    try:
        whatsapp_api.mark_message_as_read(msg_id)
    except Exception:  # pragma: no cover - best-effort
        logger.warning("Failed to mark message as read in WhatsApp API", exc_info=True)

    # If it's audio, transcribe it first.
    if msg_type == "audio" and audio_media_id:
        try:
            text = audio_svc.transcribe_whatsapp_audio(
                media_id=audio_media_id,
                language="es",  # main traffic is Spanish; Whisper can still auto-detect
            )
            logger.info(
                "Transcription result for media_id=%s: %r",
                audio_media_id,
                text,
            )
        except Exception:
            logger.exception("Audio transcription failed; falling back to empty text.")
            text = text or ""

    # Ensure we have a string to work with
    text = text or ""

    # ------------------------------------------------------------------
    # State machine integration
    # ------------------------------------------------------------------
    # The state machine owns:
    #   - loading/saving session (per guest / wa_id)
    #   - deciding intents / FAQ / ticket flow
    #   - producing a list of "outgoing actions" (currently: text messages)
    # ------------------------------------------------------------------
    session = state_machine.load_session(wa_contact_id)

    logger.debug(
        "[STATE] Before handling message",
        extra={"wa_id": wa_contact_id, "state": session.get("state") if session else None},
    )

    outgoing_actions, new_session = state_machine.handle_incoming_text(
        wa_id=wa_contact_id,
        guest_phone=wa_from,
        guest_name=guest_name,
        text=text,
        session=session,
        timestamp=ts,
        raw_payload=payload,
    )

    state_machine.save_session(wa_contact_id, new_session)

    logger.debug(
        "[STATE] After handling message",
        extra={"wa_id": wa_contact_id, "state": new_session.get("state")},
    )

    # ------------------------------------------------------------------
    # Execute outgoing actions (currently: send text messages)
    # Each action is a small dict like:
    #   {"type": "text", "text": "...", "preview_url": False}
    # ------------------------------------------------------------------
    for action in outgoing_actions:
        _send_action_via_whatsapp(action, to=wa_from)

    return jsonify({"status": "ok"}), 200


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def _extract_single_message(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Navigate the standard WhatsApp Business webhook structure and extract
    the single incoming message we care about.

    Returns a dict with:
      {
        "wa_id": str | None,
        "name": str | None,
        "from": str,
        "id": str,
        "type": str,
        "timestamp": datetime,
        "text": str | None,
        "audio_media_id": str | None,
      }
    or None if no valid message is found.
    """
    try:
        if payload.get("object") != "whatsapp_business_account":
            return None

        entry = (payload.get("entry") or [])[0]
        change = (entry.get("changes") or [])[0]
        value = change.get("value") or {}

        # Contacts
        contacts = value.get("contacts") or []
        contact = contacts[0] if contacts else {}
        profile = contact.get("profile") or {}
        contact_name = profile.get("name")
        wa_id = contact.get("wa_id")

        # Messages
        messages = value.get("messages") or []
        if not messages:
            return None

        msg = messages[0]
        msg_type = msg.get("type")
        msg_id = msg.get("id")
        from_number = msg.get("from")

        # Timestamp
        ts_raw = msg.get("timestamp")
        try:
            ts_int = int(ts_raw)
            ts_dt = datetime.fromtimestamp(ts_int, tz=timezone.utc)
        except Exception:
            ts_dt = datetime.now(tz=timezone.utc)

        text_body: Optional[str] = None
        audio_media_id: Optional[str] = None

        if msg_type == "text":
            text_body = (msg.get("text") or {}).get("body", "")
        elif msg_type == "audio":
            audio_obj = msg.get("audio") or {}
            audio_media_id = audio_obj.get("id")
        elif msg_type in {"button", "interactive"}:
            # Handle basic button / interactive replies as text for the NLU.
            text_body = _extract_interactive_text(msg)
        else:
            # Unsupported type → still try to get something textual if present
            text_body = (msg.get("text") or {}).get("body", "")

        if not from_number or not msg_id:
            return None

        return {
            "wa_id": wa_id,
            "name": contact_name,
            "from": from_number,
            "id": msg_id,
            "type": msg_type,
            "timestamp": ts_dt,
            "text": text_body,
            "audio_media_id": audio_media_id,
        }
    except Exception:
        logger.exception("Failed to extract single WhatsApp message from payload.")
        return None


def _extract_interactive_text(msg: Dict[str, Any]) -> str:
    """
    Normalize different interactive/button message formats into a simple text string
    that the NLU and state machine can consume.
    """
    # Interactive messages can be of types: button, list reply, etc.
    # We keep this intentionally defensive: grab whatever text/title is available.
    interactive = msg.get("interactive") or {}

    # Button reply
    if "button_reply" in interactive:
        return interactive["button_reply"].get("title") or ""

    # List reply
    if "list_reply" in interactive:
        return interactive["list_reply"].get("title") or ""

    # Fallback: plain text if present
    return (msg.get("text") or {}).get("body", "") or ""


def _send_action_via_whatsapp(action: Dict[str, Any], to: str) -> None:
    """
    Dispatch a single action returned by the state machine via WhatsApp Cloud API.

    Current supported actions:
      - {"type": "text", "text": "...", "preview_url": bool}
    """
    action_type = action.get("type")
    if action_type == "text":
        text = action.get("text")
        if not text:
            logger.warning("Text action without 'text' field: %r", action)
            return

        preview_url = bool(action.get("preview_url", False))
        try:
            whatsapp_api.send_text_message(
                to=to,
                text=text,
                preview_url=preview_url,
            )
            logger.info("[OUT → %s] text=%r", to, text)
        except Exception:
            logger.exception("Failed to send WhatsApp text message")
    else:
        logger.warning("Unsupported action type from state machine: %r", action_type)
