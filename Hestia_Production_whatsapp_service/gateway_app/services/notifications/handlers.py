"""
Handlers de Notificaciones

Cada handler es responsable de un tipo específico de notificación:
- Ticket asignado
- Ticket resuelto + encuesta CSAT
- FAQ respondida + encuesta FAQ
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from . import notification_db as db
from . import notification_whatsapp as wa
from .notification_config import notification_cfg

logger = logging.getLogger(__name__)


# ============================================================================
# Handler: Ticket Asignado
# ============================================================================

def handle_ticket_assignments() -> int:
    """
    Busca tickets recién asignados y envía notificación al huésped.

    Returns:
        Cantidad de notificaciones enviadas
    """
    if not notification_cfg.ENABLE_ASSIGNMENT_NOTIFICATIONS:
        return 0

    ph = "%s" if db.using_pg() else "?"

    # Buscar tickets asignados sin notificar
    # NOTA: Usamos huesped_id (tu campo con el número de WhatsApp) con alias as huesped_phone
    sql = f"""
        SELECT id, huesped_id as huesped_phone, assigned_to, detalle
        FROM tickets
        WHERE assigned_to IS NOT NULL
          AND (assignment_notif_sent IS NULL OR assignment_notif_sent = FALSE)
          AND huesped_id IS NOT NULL
        LIMIT 50
    """

    try:
        tickets = db.fetchall(sql)
    except Exception as e:
        logger.exception(f"[ASSIGNMENTS] Error al buscar tickets: {e}")
        return 0

    count = 0
    for ticket in tickets:
        try:
            ticket_id = ticket["id"]
            phone = ticket["huesped_phone"]
            assigned_to = ticket["assigned_to"]
            detalle = ticket["detalle"] or "tu solicitud"

            # Construir mensaje
            message = f"""¡Hola! Tu ticket #{ticket_id} ha sido asignado.

📋 *Solicitud:* {detalle[:100]}...
👤 *Asignado a:* {assigned_to}

Te mantendremos informado del progreso. Gracias por tu paciencia."""

            # Enviar WhatsApp
            wa.send_text_message(to=phone, text=message)

            # Marcar como enviado
            update_sql = f"UPDATE tickets SET assignment_notif_sent = TRUE WHERE id = {ph}"
            db.execute(update_sql, [ticket_id], commit=True)

            logger.info(f"[ASSIGNMENTS] Notificación enviada para ticket {ticket_id}")
            count += 1

        except wa.WhatsAppError as e:
            logger.warning(f"[ASSIGNMENTS] Error al enviar WhatsApp para ticket {ticket['id']}: {e}")
        except Exception as e:
            logger.exception(f"[ASSIGNMENTS] Error inesperado para ticket {ticket['id']}: {e}")

    if count > 0:
        logger.info(f"[ASSIGNMENTS] {count} notificaciones de asignación enviadas")

    return count


# ============================================================================
# Handler: Ticket Resuelto + Encuesta CSAT
# ============================================================================

def handle_ticket_resolutions() -> int:
    """
    Busca tickets recién resueltos, envía notificación y dispara encuesta CSAT.

    Returns:
        Cantidad de notificaciones enviadas
    """
    if not notification_cfg.ENABLE_RESOLUTION_NOTIFICATIONS:
        return 0

    ph = "%s" if db.using_pg() else "?"

    # Buscar tickets resueltos sin notificar
    # NOTA: Usamos huesped_id (tu campo con el número de WhatsApp) con alias as huesped_phone
    sql = f"""
        SELECT id, huesped_id as huesped_phone, detalle, finished_at
        FROM tickets
        WHERE estado = 'RESUELTO'
          AND (csat_survey_triggered IS NULL OR csat_survey_triggered = FALSE)
          AND huesped_id IS NOT NULL
        LIMIT 50
    """

    try:
        tickets = db.fetchall(sql)
    except Exception as e:
        logger.exception(f"[RESOLUTIONS] Error al buscar tickets: {e}")
        return 0

    count = 0
    for ticket in tickets:
        try:
            ticket_id = ticket["id"]
            phone = ticket["huesped_phone"]
            detalle = ticket["detalle"] or "tu solicitud"

            # 1. Enviar notificación de resolución
            resolution_message = f"""✅ ¡Buenas noticias! Tu ticket #{ticket_id} ha sido resuelto.

📋 *Solicitud:* {detalle[:100]}...

Si necesitas algo más, no dudes en escribirnos."""

            wa.send_text_message(to=phone, text=resolution_message)
            logger.info(f"[RESOLUTIONS] Notificación de resolución enviada para ticket {ticket_id}")

            # 2. Crear y enviar encuesta CSAT (si está habilitado)
            if notification_cfg.ENABLE_CSAT_SURVEYS:
                survey_id = _create_csat_survey(ticket_id, phone)
                if survey_id:
                    _send_csat_q1(phone, ticket_id)
                    logger.info(f"[RESOLUTIONS] Encuesta CSAT iniciada para ticket {ticket_id}")

            # 3. Marcar como procesado
            update_sql = f"UPDATE tickets SET csat_survey_triggered = TRUE WHERE id = {ph}"
            db.execute(update_sql, [ticket_id], commit=True)

            count += 1

        except wa.WhatsAppError as e:
            logger.warning(f"[RESOLUTIONS] Error al enviar WhatsApp para ticket {ticket['id']}: {e}")
        except Exception as e:
            logger.exception(f"[RESOLUTIONS] Error inesperado para ticket {ticket['id']}: {e}")

    if count > 0:
        logger.info(f"[RESOLUTIONS] {count} notificaciones de resolución enviadas")

    return count


def _create_csat_survey(ticket_id: int, guest_phone: str) -> Optional[int]:
    """Crea un registro de encuesta CSAT en la BD"""
    ph = "%s" if db.using_pg() else "?"
    now = datetime.utcnow().isoformat()

    sql = f"""
        INSERT INTO csat_surveys (
            ticket_id,
            guest_phone,
            survey_state,
            survey_last_prompt_at,
            created_at
        ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
    """

    try:
        survey_id = db.insert_and_get_id(sql, [ticket_id, guest_phone, "q1_sent", now, now])
        logger.info(f"[CSAT] Encuesta creada con ID {survey_id} para ticket {ticket_id}")
        return survey_id
    except Exception as e:
        logger.exception(f"[CSAT] Error al crear encuesta para ticket {ticket_id}: {e}")
        return None


def _send_csat_q1(phone: str, ticket_id: int) -> None:
    """Envía la primera pregunta de la encuesta CSAT"""
    message = f"""Nos gustaría conocer tu opinión sobre la atención recibida en tu ticket #{ticket_id}.

¿Cómo calificarías tu experiencia?

Responde con un número del 1 al 5:
1️⃣ - Muy mala
2️⃣ - Mala
3️⃣ - Regular
4️⃣ - Buena
5️⃣ - Excelente"""

    wa.send_text_message(to=phone, text=message)


# ============================================================================
# Handler: FAQ Encuestas
# ============================================================================

def handle_faq_surveys() -> int:
    """
    Busca FAQs respondidas y envía encuesta de satisfacción.

    Returns:
        Cantidad de encuestas enviadas
    """
    if not notification_cfg.ENABLE_FAQ_SURVEYS:
        return 0

    ph = "%s" if db.using_pg() else "?"

    # Calcular timestamp mínimo (debe haber pasado X segundos desde la ÚLTIMA actualización)
    delay_seconds = notification_cfg.FAQ_SURVEY_DELAY_SECONDS
    cutoff_time = (datetime.utcnow() - timedelta(seconds=delay_seconds)).isoformat()

    # Buscar conversaciones FAQ sin encuesta
    # IMPORTANTE: Solo enviamos encuesta si:
    # 1. Tiene FAQs respondidas (faq_count > 0)
    # 2. No se ha enviado encuesta (survey_sent = FALSE)
    # 3. La última actualización fue hace más de X segundos (para evitar spam si sigue escribiendo)
    sql = f"""
        SELECT id, wa_id, guest_phone, created_at, updated_at
        FROM conversation_logs
        WHERE faq_count > 0
          AND (survey_sent IS NULL OR survey_sent = FALSE)
          AND updated_at < {ph}
          AND guest_phone IS NOT NULL
        LIMIT 50
    """

    try:
        conversations = db.fetchall(sql, [cutoff_time])
    except Exception as e:
        logger.exception(f"[FAQ_SURVEYS] Error al buscar conversaciones: {e}")
        return 0

    count = 0
    for conv in conversations:
        try:
            conv_id = conv["id"]
            phone = conv["guest_phone"]

            # Enviar encuesta FAQ
            message = """¿Te fue útil la información que te proporcionamos?

Por favor califica del 1 al 5:
1️⃣ - Nada útil
2️⃣ - Poco útil
3️⃣ - Regular
4️⃣ - Útil
5️⃣ - Muy útil"""

            wa.send_text_message(to=phone, text=message)

            # Marcar como enviado
            update_sql = f"""
                UPDATE conversation_logs
                SET survey_sent = TRUE,
                    survey_state = 'q1_sent',
                    survey_sent_at = {ph}
                WHERE id = {ph}
            """
            db.execute(update_sql, [datetime.utcnow().isoformat(), conv_id], commit=True)

            logger.info(f"[FAQ_SURVEYS] Encuesta enviada para conversación {conv_id}")
            count += 1

        except wa.WhatsAppError as e:
            logger.warning(f"[FAQ_SURVEYS] Error al enviar WhatsApp para conv {conv['id']}: {e}")
        except Exception as e:
            logger.exception(f"[FAQ_SURVEYS] Error inesperado para conv {conv['id']}: {e}")

    if count > 0:
        logger.info(f"[FAQ_SURVEYS] {count} encuestas FAQ enviadas")

    return count


# ============================================================================
# Handler: Ticket en Curso (Trabajador empezó a resolverlo)
# ============================================================================

def handle_ticket_in_progress() -> int:
    """
    Busca tickets que cambiaron a EN_CURSO y notifica al huésped.

    Returns:
        Cantidad de notificaciones enviadas
    """
    if not notification_cfg.ENABLE_ASSIGNMENT_NOTIFICATIONS:  # Usa el mismo flag
        return 0

    ph = "%s" if db.using_pg() else "?"

    # Buscar tickets en curso sin notificar
    # NOTA: Usamos huesped_id (tu campo con el número de WhatsApp) con alias as huesped_phone
    # IMPORTANTE: Usa in_progress_notif_sent (campo separado del de asignación)
    sql = f"""
        SELECT id, huesped_id as huesped_phone, assigned_to, detalle, started_at
        FROM tickets
        WHERE estado = 'EN_CURSO'
          AND (in_progress_notif_sent IS NULL OR in_progress_notif_sent = FALSE)
          AND huesped_id IS NOT NULL
        LIMIT 50
    """

    try:
        tickets = db.fetchall(sql)
    except Exception as e:
        logger.exception(f"[IN_PROGRESS] Error al buscar tickets: {e}")
        return 0

    count = 0
    for ticket in tickets:
        try:
            ticket_id = ticket["id"]
            phone = ticket["huesped_phone"]
            detalle = ticket["detalle"] or "tu solicitud"

            # Construir mensaje
            message = f"""👷 ¡Buenas noticias! Tu ticket #{ticket_id} está siendo atendido.

📋 *Solicitud:* {detalle[:100]}...

Nuestro equipo está trabajando en resolver tu solicitud. Te notificaremos cuando esté lista."""

            # Enviar WhatsApp
            wa.send_text_message(to=phone, text=message)

            # Marcar como enviado
            update_sql = f"UPDATE tickets SET in_progress_notif_sent = TRUE WHERE id = {ph}"
            db.execute(update_sql, [ticket_id], commit=True)

            logger.info(f"[IN_PROGRESS] Notificación enviada para ticket {ticket_id}")
            count += 1

        except wa.WhatsAppError as e:
            logger.warning(f"[IN_PROGRESS] Error al enviar WhatsApp para ticket {ticket['id']}: {e}")
        except Exception as e:
            logger.exception(f"[IN_PROGRESS] Error inesperado para ticket {ticket['id']}: {e}")

    if count > 0:
        logger.info(f"[IN_PROGRESS] {count} notificaciones de inicio enviadas")

    return count


# ============================================================================
# Handler Principal: Ejecuta todos los handlers
# ============================================================================

def process_all_notifications() -> Dict[str, int]:
    """
    Ejecuta todos los handlers de notificaciones en secuencia.

    Returns:
        Dict con contadores de cada tipo de notificación enviada
    """
    results = {
        "assignments": 0,
        "in_progress": 0,
        "resolutions": 0,
        "faq_surveys": 0,
    }

    try:
        results["assignments"] = handle_ticket_assignments()
    except Exception as e:
        logger.exception(f"[PROCESS] Error en handler de asignaciones: {e}")

    try:
        results["in_progress"] = handle_ticket_in_progress()
    except Exception as e:
        logger.exception(f"[PROCESS] Error en handler de inicio: {e}")

    try:
        results["resolutions"] = handle_ticket_resolutions()
    except Exception as e:
        logger.exception(f"[PROCESS] Error en handler de resoluciones: {e}")

    try:
        results["faq_surveys"] = handle_faq_surveys()
    except Exception as e:
        logger.exception(f"[PROCESS] Error en handler de encuestas FAQ: {e}")

    total = sum(results.values())
    if total > 0:
        logger.info(f"[PROCESS] Total de notificaciones procesadas: {results}")

    return results
