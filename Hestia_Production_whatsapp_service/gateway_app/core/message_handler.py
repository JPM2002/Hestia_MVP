# gateway_app/core/message_handler.py
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from gateway_app.core.conversation import orchestrator, session
from gateway_app.core.intents import smalltalk_handler
from gateway_app.services import audio as audio_svc

logger = logging.getLogger(__name__)

_GREETINGS = {
    "hola", "holi", "buenas", "buenos dias", "buenos días",
    "buen dia", "buen día", "buenas tardes", "buenas noches",
    "hi", "hello", "hey",
}


def _ts_iso(ts) -> str:
    """Best-effort ISO string for timestamp (datetime preferred)."""
    if hasattr(ts, "isoformat"):
        return ts.isoformat()
    return str(ts)


def _is_greeting_only(t: str) -> bool:
    t = (t or "").strip().lower()
    t = re.sub(r"[^\w\sáéíóúüñ]", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()
    return t in _GREETINGS or bool(re.fullmatch(r"hol+a+", t))


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

    # 1.2) NUEVO: Log mensaje del huésped
    from gateway_app.services import conversation_logger
    conversation_logger.log_guest_message(
        wa_id=wa_id,
        text=msg_text,
        intent=None,  # Se llenará después del NLU si es necesario
        confidence=None
    )

    # 1.5) Verificar si es respuesta a encuesta CSAT de TICKET (ANTES del pipeline conversacional)
    from gateway_app.core import survey_handler
    is_ticket_survey, ticket_survey_actions = survey_handler.handle_survey_response(from_phone, msg_text)

    if is_ticket_survey:
        # Es respuesta a encuesta de ticket, retornar acciones sin procesar conversación
        logger.info(f"[SURVEY] Mensaje de {from_phone} procesado como respuesta a encuesta de TICKET")
        return ticket_survey_actions

    # 1.6) NUEVO: Verificar si es respuesta a encuesta FAQ
    from gateway_app.core import faq_survey_handler
    is_faq_survey, faq_survey_actions = faq_survey_handler.handle_faq_survey_response(wa_id, msg_text)

    if is_faq_survey:
        # Es respuesta a encuesta FAQ, retornar acciones sin procesar conversación
        logger.info(f"[FAQ_SURVEY] Mensaje de {wa_id} procesado como respuesta a encuesta FAQ")
        return faq_survey_actions

    # 2) Cargar (o crear) sesión
    user_session = session.load_session(wa_id)
    if user_session is None:
        user_session = session.new_session(
            wa_id=wa_id,
            guest_phone=from_phone,
            guest_name=guest_name,
            timestamp=timestamp,
        )

    user_session.setdefault("data", {})

    # Persistir nombre si viene del canal
    if guest_name and not user_session.get("guest_name"):
        user_session["guest_name"] = guest_name

    # Siempre actualizar last_message_at por TTL
    user_session["last_message_at"] = _ts_iso(timestamp)

    # --- #107 Welcome universal (ANTES del pipeline) ---
    welcome_text = smalltalk_handler.get_initial_greeting(user_session)

    welcome_actions: List[Dict[str, Any]] = []
    if not user_session["data"].get("welcome_sent"):
        user_session["data"]["welcome_sent"] = True
        welcome_actions = [{"type": "text", "text": welcome_text}]

    # Si el mensaje ES SOLO SALUDO -> responder welcome y cortar
    if _is_greeting_only(msg_text):
        session.save_session(wa_id, user_session)
        return [{"type": "text", "text": welcome_text}]

    # Si el primer contacto fue un mensaje vacío (ej: audio sin transcripción),
    # igual respondemos welcome y cortamos.
    if not msg_text and welcome_actions:
        session.save_session(wa_id, user_session)
        return welcome_actions
    # --- fin #107 ---

    # 3) Ejecutar un paso del autómata/pipeline
    actions, new_session = orchestrator.handle_incoming_text(
        wa_id=wa_id,
        guest_phone=from_phone,
        guest_name=guest_name,
        text=msg_text,
        session=user_session,
        timestamp=timestamp,
        raw_payload=raw_payload,
    )

    # 3.5) Preprender el welcome si correspondía (primer contacto)
    if welcome_actions:
        existing_texts = {a.get("text") for a in actions if a.get("type") == "text"}
        if welcome_text not in existing_texts:
            actions = welcome_actions + actions

    # 4.5) NUEVO: Log respuestas del bot y programar encuesta FAQ si aplica
    if actions:
        from gateway_app.services import conversation_logger

        # Determinar si fue respuesta FAQ (basado en estado de sesión)
        state_source = new_session or user_session
        current_state = state_source.get("state", "")
        is_faq_state = current_state in ["GH_FAQ", "IDLE"]  # FAQ responses happen in these states

        # Log cada acción de texto del bot
        for action in actions:
            if action.get("type") == "text":
                conversation_logger.log_bot_message(
                    wa_id=wa_id,
                    text=action["text"],
                    is_faq=is_faq_state
                )

    # 5) Retornar acciones (sin enviar por ningún canal)
    # 4) Asegurar que el flag + last_message_at se mantenga en la sesión final
    if new_session is None:
        new_session = user_session

    new_session.setdefault("data", {})
    new_session["last_message_at"] = _ts_iso(timestamp)

    if user_session.get("data", {}).get("welcome_sent"):
        new_session["data"]["welcome_sent"] = True

    if guest_name and not new_session.get("guest_name"):
        new_session["guest_name"] = guest_name

    # 5) Guardar sesión y retornar acciones
    session.save_session(wa_id, new_session)
    return actions
