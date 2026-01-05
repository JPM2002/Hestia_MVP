"""
Servicio para almacenar conversaciones FAQ en base de datos.
Trackea mensajes del huésped y del bot para análisis y encuestas.
"""

import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Importar funciones de BD desde Hestia_Production
try:
    sys.path.append(os.path.join(os.path.dirname(__file__), '../../../Hestia_Production'))
    from hestia_app.services.db import fetchone, execute, fetchall
    DB_AVAILABLE = True
except ImportError:
    logger.warning("[CONV_LOGGER] No se pudo importar DB de Hestia_Production")
    DB_AVAILABLE = False
    fetchone = None
    execute = None
    fetchall = None


def get_or_create_conversation(wa_id: str, guest_phone: str = None, guest_name: str = None) -> Optional[Dict[str, Any]]:
    """
    Obtiene la conversación activa del huésped o crea una nueva.

    Una conversación se considera "activa" si el último mensaje fue hace menos de 15 minutos.

    Args:
        wa_id: WhatsApp ID del huésped
        guest_phone: Número de teléfono (opcional)
        guest_name: Nombre del huésped (opcional)

    Returns:
        Dict con datos de la conversación o None si DB no disponible
    """
    if not DB_AVAILABLE or not fetchone or not execute:
        return None

    try:
        # Buscar conversación activa (última fue hace <15 min)
        fifteen_min_ago = (datetime.utcnow() - timedelta(minutes=15)).isoformat()

        active_conv = fetchone("""
            SELECT * FROM conversation_logs
            WHERE wa_id = ?
              AND (last_bot_message_at > ? OR last_bot_message_at IS NULL)
              AND ended_at IS NULL
            ORDER BY started_at DESC
            LIMIT 1
        """, (wa_id, fifteen_min_ago))

        if active_conv:
            logger.debug(f"[CONV_LOGGER] Conversación activa encontrada: {active_conv['id']}")
            return active_conv

        # No hay conversación activa, crear nueva
        now = datetime.utcnow().isoformat()

        execute("""
            INSERT INTO conversation_logs (
                wa_id,
                guest_phone,
                guest_name,
                started_at,
                message_count,
                bot_message_count,
                faq_count
            ) VALUES (?, ?, ?, ?, 0, 0, 0)
        """, (wa_id, guest_phone, guest_name, now))

        # Obtener la conversación recién creada
        new_conv = fetchone("""
            SELECT * FROM conversation_logs
            WHERE wa_id = ?
            ORDER BY started_at DESC
            LIMIT 1
        """, (wa_id,))

        logger.info(f"[CONV_LOGGER] Nueva conversación creada: {new_conv['id']} para {wa_id}")
        return new_conv

    except Exception as e:
        logger.exception(f"[CONV_LOGGER] Error al obtener/crear conversación: {e}")
        return None


def log_guest_message(wa_id: str, text: str, intent: str = None, confidence: float = None):
    """
    Registra un mensaje del huésped.

    Args:
        wa_id: WhatsApp ID del huésped
        text: Texto del mensaje
        intent: Intent detectado (opcional)
        confidence: Confianza del intent (opcional)
    """
    if not DB_AVAILABLE:
        return

    try:
        conv = get_or_create_conversation(wa_id)
        if not conv:
            return

        # Guardar mensaje
        execute("""
            INSERT INTO conversation_messages (
                conversation_log_id,
                timestamp,
                sender,
                message_text,
                intent,
                intent_confidence
            ) VALUES (?, ?, 'guest', ?, ?, ?)
        """, (
            conv["id"],
            datetime.utcnow().isoformat(),
            text,
            intent,
            confidence
        ))

        # Actualizar contador de mensajes
        execute("""
            UPDATE conversation_logs
            SET message_count = message_count + 1,
                updated_at = ?
            WHERE id = ?
        """, (datetime.utcnow().isoformat(), conv["id"]))

        logger.debug(f"[CONV_LOGGER] Mensaje del huésped registrado en conv {conv['id']}")

    except Exception as e:
        logger.exception(f"[CONV_LOGGER] Error al registrar mensaje del huésped: {e}")


def log_bot_message(wa_id: str, text: str, is_faq: bool = False, faq_id: str = None):
    """
    Registra un mensaje del bot y actualiza timestamp de último mensaje.

    Args:
        wa_id: WhatsApp ID del huésped
        text: Texto del mensaje
        is_faq: Si es respuesta FAQ
        faq_id: ID del FAQ matched (opcional)
    """
    if not DB_AVAILABLE:
        return

    try:
        conv = get_or_create_conversation(wa_id)
        if not conv:
            return

        now = datetime.utcnow().isoformat()

        # Guardar mensaje
        execute("""
            INSERT INTO conversation_messages (
                conversation_log_id,
                timestamp,
                sender,
                message_text,
                is_faq_response,
                faq_matched_id
            ) VALUES (?, ?, 'bot', ?, ?, ?)
        """, (
            conv["id"],
            now,
            text,
            is_faq,
            faq_id
        ))

        # Actualizar contadores y timestamp
        faq_increment = 1 if is_faq else 0

        execute("""
            UPDATE conversation_logs
            SET bot_message_count = bot_message_count + 1,
                faq_count = faq_count + ?,
                last_bot_message_at = ?,
                updated_at = ?
            WHERE id = ?
        """, (faq_increment, now, now, conv["id"]))

        logger.debug(f"[CONV_LOGGER] Mensaje del bot registrado en conv {conv['id']}, is_faq={is_faq}")

    except Exception as e:
        logger.exception(f"[CONV_LOGGER] Error al registrar mensaje del bot: {e}")


def mark_ticket_created(wa_id: str, ticket_id: int):
    """
    Marca que se creó un ticket en esta conversación.

    Args:
        wa_id: WhatsApp ID del huésped
        ticket_id: ID del ticket creado
    """
    if not DB_AVAILABLE:
        return

    try:
        conv = get_or_create_conversation(wa_id)
        if not conv:
            return

        execute("""
            UPDATE conversation_logs
            SET ticket_created = TRUE,
                ticket_id = ?,
                updated_at = ?
            WHERE id = ?
        """, (ticket_id, datetime.utcnow().isoformat(), conv["id"]))

        logger.info(f"[CONV_LOGGER] Ticket {ticket_id} marcado en conversación {conv['id']}")

    except Exception as e:
        logger.exception(f"[CONV_LOGGER] Error al marcar ticket creado: {e}")


def get_active_conversation(wa_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene la conversación activa sin crear una nueva.

    Args:
        wa_id: WhatsApp ID del huésped

    Returns:
        Dict con datos de la conversación o None
    """
    if not DB_AVAILABLE or not fetchone:
        return None

    try:
        fifteen_min_ago = (datetime.utcnow() - timedelta(minutes=15)).isoformat()

        conv = fetchone("""
            SELECT * FROM conversation_logs
            WHERE wa_id = ?
              AND (last_bot_message_at > ? OR last_bot_message_at IS NULL)
              AND ended_at IS NULL
            ORDER BY started_at DESC
            LIMIT 1
        """, (wa_id, fifteen_min_ago))

        return conv

    except Exception as e:
        logger.exception(f"[CONV_LOGGER] Error al obtener conversación activa: {e}")
        return None


def check_survey_cooldown(wa_id: str, cooldown_hours: int = 24) -> bool:
    """
    Verifica si el huésped ya recibió una encuesta recientemente.

    Args:
        wa_id: WhatsApp ID del huésped
        cooldown_hours: Horas de cooldown (default: 24)

    Returns:
        True si puede recibir encuesta, False si está en cooldown
    """
    if not DB_AVAILABLE or not fetchone:
        return True  # Si no hay BD, permitir

    try:
        cooldown_time = (datetime.utcnow() - timedelta(hours=cooldown_hours)).isoformat()

        recent_survey = fetchone("""
            SELECT id FROM conversation_logs
            WHERE wa_id = ?
              AND survey_sent = TRUE
              AND survey_sent_at > ?
            LIMIT 1
        """, (wa_id, cooldown_time))

        if recent_survey:
            logger.info(f"[CONV_LOGGER] Huésped {wa_id} en cooldown de encuesta")
            return False

        return True

    except Exception as e:
        logger.exception(f"[CONV_LOGGER] Error al verificar cooldown: {e}")
        return True  # En caso de error, permitir
