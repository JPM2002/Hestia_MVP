# gateway_app/core/message_handler.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from gateway_app.core import state as state_machine
from gateway_app.services import audio as audio_svc

logger = logging.getLogger(__name__)


def process_guest_message(
    *,
    wa_id: str,
    from_phone: str,
    guest_name: Optional[str],
    msg_type: str,
    text: str,
    media_id: Optional[str],
    timestamp,
    raw_payload: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Process guest message and return bot actions (WITHOUT sending via any channel).

    This is the CORE processing logic shared by ALL channels:
    - WhatsApp (/whatsapp endpoint)
    - Test endpoint (/test)
    - Web chat (custom implementations)
    - Telegram, SMS, etc. (future channels)

    Responsibilities:
    - If needed, transcribe audio -> text.
    - Load DFA session.
    - Call state_machine.handle_incoming_text (the DFA).
    - Save DFA session.
    - Return actions (WITHOUT sending them)

    Args:
        wa_id: User identifier (WhatsApp ID, user ID, etc.)
        from_phone: Phone number or user identifier
        guest_name: Guest name (if available from channel)
        msg_type: Message type ("text", "audio", etc.)
        text: Message text content
        media_id: Media ID for audio/images (optional)
        timestamp: Message timestamp
        raw_payload: Raw webhook payload for debugging

    Returns:
        List of actions (dicts with "type", "text", etc.)
        Example: [{"type": "text", "text": "Hola, ¿cómo puedo ayudarte?"}]
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

    # 5) Retornar acciones (sin enviar por ningún canal)
    return actions
    