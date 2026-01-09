"""
Handler para respuestas de encuestas CSAT post-interacción.
Detecta si un mensaje entrante es respuesta a una encuesta activa.
"""

import logging
import re
from typing import Tuple, List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Importar funciones de BD desde notification_db (compatible con PostgreSQL)
try:
    from gateway_app.services.notifications import notification_db as db
    DB_AVAILABLE = True
except ImportError:
    logger.warning("[SURVEY] No se pudo importar notification_db")
    DB_AVAILABLE = False
    db = None


# Mensajes de la encuesta
SURVEY_Q2_LOW_MESSAGE = "¿Qué podríamos haber hecho mejor?"
SURVEY_Q2_HIGH_MESSAGE = "¡Qué bueno! ¿Qué fue lo que más te gustó?"

SURVEY_Q3_MESSAGE = """Una última pregunta: ¿qué tan útil te pareció usar WhatsApp para esto?

Del 1 al 5:
1 - Nada útil
5 - Muy útil"""

SURVEY_THANK_YOU_MESSAGE = """¡Gracias por tu tiempo! Nos ayuda mucho a mejorar. 🙏

Si necesitas algo más, escríbenos cuando quieras."""

SURVEY_INVALID_RATING_MESSAGE = """No entendí tu calificación.

Por favor responde con un número del 1 al 5 sobre qué tan satisfecho quedaste con el servicio:
1 - Muy insatisfecho
5 - Muy satisfecho"""
SURVEY_INVALID_COMMENT_MESSAGE = "Por favor comparte tu opinión con más detalle para ayudarnos a mejorar."


def extract_rating(text: str) -> Optional[int]:
    """
    Extrae una calificación del 1 al 5 de un mensaje de texto.

    Soporta:
    - Números directos: "4", "5"
    - Estrellas: "⭐⭐⭐⭐"
    - Palabras: "cuatro", "cinco"

    Args:
        text: Texto del mensaje

    Returns:
        Número del 1-5, o None si no se detecta
    """
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


def check_active_survey(guest_phone: str) -> Optional[Dict[str, Any]]:
    """
    Verifica si existe una encuesta activa para el huésped.

    Args:
        guest_phone: Número de WhatsApp del huésped

    Returns:
        Dict con datos de la encuesta activa, o None si no hay encuesta
    """
    if not DB_AVAILABLE or not db:
        return None

    try:
        ph = "%s" if db.using_pg() else "?"

        sql = f"""
            SELECT id, ticket_id, survey_state, csat_score
            FROM csat_surveys
            WHERE guest_phone = {ph}
              AND survey_state IN ('sent', 'in_progress')
            ORDER BY created_at DESC
            LIMIT 1
        """

        survey = db.fetchone(sql, [guest_phone])
        return survey
    except Exception as e:
        logger.exception(f"[SURVEY] Error al buscar encuesta activa: {e}")
        return None


def handle_survey_response(
    guest_phone: str,
    msg_text: str
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Procesa respuesta a encuesta si existe una activa.

    Args:
        guest_phone: Número WhatsApp del huésped
        msg_text: Texto del mensaje

    Returns:
        (is_survey_response, actions)
        - is_survey_response: True si el mensaje es respuesta a encuesta
        - actions: Lista de acciones a ejecutar (mensajes a enviar)
    """
    if not DB_AVAILABLE:
        return False, []

    # 1. Verificar si hay encuesta activa
    survey = check_active_survey(guest_phone)
    if not survey:
        # No hay encuesta activa, no es respuesta a encuesta
        return False, []

    survey_id = survey["id"]
    ticket_id = survey["ticket_id"]
    state = survey["survey_state"]
    csat_score = survey.get("csat_score")

    logger.info(f"[SURVEY] Procesando respuesta para encuesta {survey_id}, estado {state}")

    # 2. Procesar según el estado y qué campos ya están llenos
    # Determinar en qué pregunta está basándonos en qué campos ya tienen respuesta

    if csat_score is None:
        # Esperando calificación CSAT (Q1)
        return _handle_q1_response(survey_id, ticket_id, guest_phone, msg_text)

    # Si ya tiene CSAT, consultar más campos para saber si está en Q2 o Q3
    ph = "%s" if db.using_pg() else "?"
    sql_full = f"""
        SELECT csat_score, csat_comment, tool_utility_score
        FROM csat_surveys
        WHERE id = {ph}
    """
    survey_full = db.fetchone(sql_full, [survey_id])

    if survey_full["csat_comment"] is None:
        # Ya respondió Q1, esperando comentario (Q2)
        return _handle_q2_response(survey_id, ticket_id, guest_phone, msg_text)
    elif survey_full["tool_utility_score"] is None:
        # Ya respondió Q1 y Q2, esperando utilidad (Q3)
        return _handle_q3_response(survey_id, ticket_id, guest_phone, msg_text)

    # Si llegamos aquí, la encuesta ya está completa
    return False, []


def _handle_q1_response(
    survey_id: int,
    ticket_id: int,
    guest_phone: str,
    msg_text: str
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Procesa respuesta a Q1 (CSAT)"""

    rating = extract_rating(msg_text)

    if rating is None:
        # Respuesta inválida
        return True, [{"type": "text", "text": SURVEY_INVALID_RATING_MESSAGE}]

    # Guardar calificación
    try:
        ph = "%s" if db.using_pg() else "?"

        sql = f"""
            UPDATE csat_surveys
            SET csat_score = {ph},
                survey_last_prompt_at = {ph}
            WHERE id = {ph}
        """

        db.execute(sql, [rating, datetime.utcnow().isoformat(), survey_id], commit=True)

        logger.info(f"[SURVEY] Ticket {ticket_id}: CSAT score = {rating}")
    except Exception as e:
        logger.exception(f"[SURVEY] Error al guardar CSAT: {e}")
        return True, [{"type": "text", "text": "Hubo un error. Por favor intenta de nuevo."}]

    # Determinar Q2 según el puntaje
    if rating <= 3:
        q2_message = SURVEY_Q2_LOW_MESSAGE
    else:
        q2_message = SURVEY_Q2_HIGH_MESSAGE

    return True, [{"type": "text", "text": q2_message}]


def _handle_q2_response(
    survey_id: int,
    ticket_id: int,
    guest_phone: str,
    msg_text: str
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Procesa respuesta a Q2 (Comentario)"""

    comment = msg_text.strip()

    if len(comment) < 2:
        # Comentario muy corto
        return True, [{"type": "text", "text": SURVEY_INVALID_COMMENT_MESSAGE}]

    # Guardar comentario
    try:
        ph = "%s" if db.using_pg() else "?"

        sql = f"""
            UPDATE csat_surveys
            SET csat_comment = {ph},
                survey_last_prompt_at = {ph}
            WHERE id = {ph}
        """

        db.execute(sql, [comment, datetime.utcnow().isoformat(), survey_id], commit=True)

        logger.info(f"[SURVEY] Ticket {ticket_id}: Comentario guardado")
    except Exception as e:
        logger.exception(f"[SURVEY] Error al guardar comentario: {e}")
        return True, [{"type": "text", "text": "Hubo un error. Por favor intenta de nuevo."}]

    # Enviar Q3 (utilidad)
    return True, [{"type": "text", "text": SURVEY_Q3_MESSAGE}]


def _handle_q3_response(
    survey_id: int,
    ticket_id: int,
    guest_phone: str,
    msg_text: str
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Procesa respuesta a Q3 (Utilidad)"""

    utility = extract_rating(msg_text)

    if utility is None:
        # Respuesta inválida
        return True, [{"type": "text", "text": SURVEY_INVALID_RATING_MESSAGE}]

    # Guardar utilidad y COMPLETAR encuesta
    try:
        ph = "%s" if db.using_pg() else "?"

        sql = f"""
            UPDATE csat_surveys
            SET tool_utility_score = {ph},
                survey_state = 'completed',
                completed_at = {ph}
            WHERE id = {ph}
        """

        db.execute(sql, [utility, datetime.utcnow().isoformat(), survey_id], commit=True)

        logger.info(f"[SURVEY] Ticket {ticket_id}: Encuesta completada (utilidad = {utility})")
    except Exception as e:
        logger.exception(f"[SURVEY] Error al completar encuesta: {e}")
        return True, [{"type": "text", "text": "Hubo un error. Por favor intenta de nuevo."}]

    # Enviar mensaje de agradecimiento
    return True, [{"type": "text", "text": SURVEY_THANK_YOU_MESSAGE}]
