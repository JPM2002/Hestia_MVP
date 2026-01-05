"""
Handler para respuestas de encuestas FAQ.
Detecta y procesa respuestas a encuestas de satisfacción FAQ (NO tickets).
"""

import logging
import os
import sys
from typing import Tuple, List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Importar funciones de BD
try:
    sys.path.append(os.path.join(os.path.dirname(__file__), '../../../Hestia_Production'))
    from hestia_app.services.db import fetchone, execute
    DB_AVAILABLE = True
except ImportError:
    logger.warning("[FAQ_SURVEY] No se pudo importar DB de Hestia_Production")
    DB_AVAILABLE = False
    fetchone = None
    execute = None


# Mensajes de la encuesta
FAQ_SURVEY_Q2_MESSAGE = "¿Qué podríamos haber hecho mejor?"
FAQ_SURVEY_THANK_YOU_MESSAGE = "¡Gracias por tu feedback! Nos ayuda a mejorar. 🙏"
FAQ_SURVEY_INVALID_RATING_MESSAGE = "Por favor responde con un número del 1 al 5."
FAQ_SURVEY_INVALID_COMMENT_MESSAGE = "Por favor comparte tu opinión con más detalle."


def extract_rating(text: str) -> Optional[int]:
    """
    Extrae una calificación del 1 al 5 de un mensaje de texto.

    Reutiliza la misma lógica que survey_handler.py para tickets.

    Args:
        text: Texto del mensaje

    Returns:
        Número del 1-5, o None si no se detecta
    """
    import re

    text_lower = text.lower().strip()

    # 1. Buscar número directo
    match = re.search(r'\b([1-5])\b', text)
    if match:
        return int(match.group(1))

    # 2. Contar estrellas
    stars = text.count('⭐') + text.count('*')
    if 1 <= stars <= 5:
        return stars

    # 3. Palabras en español
    word_map = {
        'uno': 1, 'una': 1,
        'dos': 2,
        'tres': 3,
        'cuatro': 4,
        'cinco': 5
    }

    for word, num in word_map.items():
        if word in text_lower:
            return num

    return None


def check_active_faq_survey(wa_id: str) -> Optional[Dict[str, Any]]:
    """
    Verifica si existe una encuesta FAQ activa para el huésped.

    Args:
        wa_id: WhatsApp ID del huésped

    Returns:
        Dict con datos de la conversación si hay encuesta activa, o None
    """
    if not DB_AVAILABLE or not fetchone:
        return None

    try:
        conv = fetchone("""
            SELECT * FROM conversation_logs
            WHERE wa_id = ?
              AND survey_sent = TRUE
              AND survey_state IN ('q1_sent', 'q2_sent')
            ORDER BY survey_sent_at DESC
            LIMIT 1
        """, (wa_id,))

        return conv

    except Exception as e:
        logger.exception(f"[FAQ_SURVEY] Error al buscar encuesta FAQ activa: {e}")
        return None


def handle_faq_survey_response(
    wa_id: str,
    msg_text: str
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Procesa respuesta a encuesta FAQ si existe una activa.

    Args:
        wa_id: WhatsApp ID del huésped
        msg_text: Texto del mensaje

    Returns:
        (is_faq_survey_response, actions)
        - is_faq_survey_response: True si el mensaje es respuesta a encuesta FAQ
        - actions: Lista de acciones a ejecutar (mensajes a enviar)
    """
    if not DB_AVAILABLE:
        return False, []

    # 1. Verificar si hay encuesta FAQ activa
    conv = check_active_faq_survey(wa_id)
    if not conv:
        # No hay encuesta FAQ activa
        return False, []

    conversation_id = conv["id"]
    state = conv["survey_state"]

    logger.info(f"[FAQ_SURVEY] Procesando respuesta para conv {conversation_id}, estado {state}")

    # 2. Procesar según el estado

    if state == "q1_sent":
        # Esperando calificación (1-5)
        return _handle_faq_q1_response(conversation_id, wa_id, msg_text)

    elif state == "q2_sent":
        # Esperando comentario abierto
        return _handle_faq_q2_response(conversation_id, wa_id, msg_text)

    return False, []


def _handle_faq_q1_response(
    conversation_id: int,
    wa_id: str,
    msg_text: str
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Procesa respuesta a Q1 (calificación)"""

    rating = extract_rating(msg_text)

    if rating is None:
        # Respuesta inválida
        return True, [{"type": "text", "text": FAQ_SURVEY_INVALID_RATING_MESSAGE}]

    # Guardar calificación
    try:
        execute("""
            UPDATE conversation_logs
            SET faq_csat_score = ?,
                survey_state = 'q2_sent',
                updated_at = ?
            WHERE id = ?
        """, (rating, datetime.utcnow().isoformat(), conversation_id))

        logger.info(f"[FAQ_SURVEY] Conv {conversation_id}: FAQ CSAT score = {rating}")

    except Exception as e:
        logger.exception(f"[FAQ_SURVEY] Error al guardar CSAT: {e}")
        return True, [{"type": "text", "text": "Hubo un error. Por favor intenta de nuevo."}]

    # Decidir si enviar Q2 (solo si calificación <= 3)
    if rating <= 3:
        # Calificación baja → preguntar qué mejorar
        return True, [{"type": "text", "text": FAQ_SURVEY_Q2_MESSAGE}]
    else:
        # Calificación alta → agradecer y terminar
        execute("""
            UPDATE conversation_logs
            SET survey_state = 'completed',
                updated_at = ?
            WHERE id = ?
        """, (datetime.utcnow().isoformat(), conversation_id))

        logger.info(f"[FAQ_SURVEY] Conv {conversation_id}: Encuesta completada (rating alto, sin Q2)")
        return True, [{"type": "text", "text": FAQ_SURVEY_THANK_YOU_MESSAGE}]


def _handle_faq_q2_response(
    conversation_id: int,
    wa_id: str,
    msg_text: str
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Procesa respuesta a Q2 (comentario)"""

    comment = msg_text.strip()

    if len(comment) < 2:
        # Comentario muy corto
        return True, [{"type": "text", "text": FAQ_SURVEY_INVALID_COMMENT_MESSAGE}]

    # Guardar comentario y completar encuesta
    try:
        execute("""
            UPDATE conversation_logs
            SET faq_csat_comment = ?,
                survey_state = 'completed',
                updated_at = ?
            WHERE id = ?
        """, (comment, datetime.utcnow().isoformat(), conversation_id))

        logger.info(f"[FAQ_SURVEY] Conv {conversation_id}: Encuesta completada con comentario")

    except Exception as e:
        logger.exception(f"[FAQ_SURVEY] Error al guardar comentario: {e}")
        return True, [{"type": "text", "text": "Hubo un error. Por favor intenta de nuevo."}]

    # Agradecer y terminar
    return True, [{"type": "text", "text": FAQ_SURVEY_THANK_YOU_MESSAGE}]
