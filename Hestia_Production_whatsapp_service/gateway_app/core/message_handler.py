# gateway_app/core/message_handler.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from gateway_app.core import state as state_machine
from gateway_app.services import audio as audio_svc
from gateway_app.services import whatsapp_api

logger = logging.getLogger(__name__)


def handle_guest_message(
    *,
    wa_id: str,
    from_phone: str,
    guest_name: Optional[str],
    msg_type: str,
    text: str,
    media_id: Optional[str],
    timestamp,
    raw_payload: Dict[str, Any],
) -> None:
    """
    High-level handler for guest WhatsApp messages.

    Responsibilities:
    - If needed, transcribe audio -> text.
    - Load DFA session.
    - Call state_machine.handle_incoming_text (the DFA).
    - Save DFA session.
    - Send WhatsApp replies using whatsapp_api.
    """
    # 1) Audio -> texto si hace falta
    msg_text = (text or "").strip()
    if msg_type == "audio" and media_id and not msg_text:
        try:
            transcript = audio_svc.transcribe_whatsapp_audio(media_id, language="es")
        except Exception:
            logger.exception("Error transcribing WhatsApp audio media_id=%s", media_id)
            transcript = None
        msg_text = (transcript or "").strip()

    # 2) Cargar sesión actual
    session = state_machine.load_session(wa_id)

    # 3) Ejecutar un paso del autómata
    actions, new_session = state_machine.handle_incoming_text(
        wa_id=wa_id,
        guest_phone=from_phone,
        guest_name=guest_name,
        text=msg_text,
        session=session,
        timestamp=timestamp,
        raw_payload=raw_payload,
    )

    # 4) Guardar nueva sesión
    state_machine.save_session(wa_id, new_session)

    # 5) Enviar acciones salientes
    for act in actions:
        if act.get("type") == "text":
            try:
                whatsapp_api.send_text_message(
                    to=from_phone,
                    text=act.get("text", ""),
                    preview_url=bool(act.get("preview_url", False)),
                )
            except Exception:
                logger.exception("Failed to send WhatsApp text message: %r", act)
    