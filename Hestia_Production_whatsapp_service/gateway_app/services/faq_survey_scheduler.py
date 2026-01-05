"""
Scheduler de encuestas FAQ usando APScheduler.
Programa encuestas para 15 min después del último mensaje del bot.
Si el bot responde antes de 15 min, cancela el job anterior y programa uno nuevo.
"""

import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.memory import MemoryJobStore

logger = logging.getLogger(__name__)

# Importar funciones de BD y WhatsApp
try:
    sys.path.append(os.path.join(os.path.dirname(__file__), '../../../Hestia_Production'))
    from hestia_app.services.db import fetchone, execute
    DB_AVAILABLE = True
except ImportError:
    logger.warning("[FAQ_SCHEDULER] No se pudo importar DB de Hestia_Production")
    DB_AVAILABLE = False
    fetchone = None
    execute = None

# Importar servicio de WhatsApp del gateway
from gateway_app.services import whatsapp_api


# =====================================================
# Configuración del Scheduler
# =====================================================

job_stores = {
    'default': MemoryJobStore()  # Usar memoria por ahora (simple)
}

executors = {
    'default': ThreadPoolExecutor(10)
}

job_defaults = {
    'coalesce': True,  # Si un job se atrasó, ejecutar solo una vez (no múltiples)
    'max_instances': 1  # Solo 1 instancia del mismo job a la vez
}

# Crear scheduler global
scheduler = BackgroundScheduler(
    jobstores=job_stores,
    executors=executors,
    job_defaults=job_defaults,
    timezone='UTC'
)


# =====================================================
# Funciones de Inicialización
# =====================================================

def init_scheduler():
    """
    Inicializa y arranca el scheduler.
    Debe llamarse al arrancar la aplicación.
    """
    if not scheduler.running:
        scheduler.start()
        logger.info("[FAQ_SCHEDULER] ✅ APScheduler iniciado correctamente")
    else:
        logger.info("[FAQ_SCHEDULER] APScheduler ya está corriendo")


def shutdown_scheduler():
    """
    Detiene el scheduler de forma segura.
    Llamar al apagar la aplicación.
    """
    if scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("[FAQ_SCHEDULER] APScheduler detenido")


# =====================================================
# Mensajes de Encuesta
# =====================================================

FAQ_SURVEY_Q1_MESSAGE = """¿Qué tan útil fue mi respuesta?

Responde del 1 al 5:
1 - Nada útil
2 - Poco útil
3 - Neutral
4 - Útil
5 - Muy útil"""

FAQ_SURVEY_Q2_MESSAGE = "¿Qué podríamos haber hecho mejor?"

FAQ_SURVEY_THANK_YOU_MESSAGE = "¡Gracias por tu feedback! Nos ayuda a mejorar. 🙏"


# =====================================================
# Funciones de Programación de Encuestas
# =====================================================

def schedule_faq_survey(conversation_log_id: int, wa_id: str, delay_minutes: int = 15):
    """
    Programa una encuesta FAQ para N minutos después.

    Si ya existe un job programado para este wa_id, lo CANCELA y programa uno nuevo.
    Esto implementa el "reset del timer" cuando el bot responde de nuevo.

    Args:
        conversation_log_id: ID de conversation_logs
        wa_id: WhatsApp ID del huésped
        delay_minutes: Minutos de espera (default: 15)
    """
    if not DB_AVAILABLE:
        logger.warning("[FAQ_SCHEDULER] BD no disponible, skip programación")
        return

    try:
        # 1. Verificar cooldown de 24h
        from gateway_app.services import conversation_logger
        can_send = conversation_logger.check_survey_cooldown(wa_id, cooldown_hours=24)

        if not can_send:
            logger.info(f"[FAQ_SCHEDULER] Huésped {wa_id} en cooldown, no programar encuesta")
            return

        # 2. Calcular tiempo de ejecución
        run_time = datetime.utcnow() + timedelta(minutes=delay_minutes)

        # 3. ID único del job (basado en wa_id)
        job_id = f"faq_survey_{wa_id}"

        # 4. Programar job (si ya existe con ese ID, se reemplaza automáticamente)
        scheduler.add_job(
            func=_send_faq_survey_job,
            trigger='date',
            run_date=run_time,
            args=[conversation_log_id, wa_id],
            id=job_id,
            replace_existing=True,  # ← CLAVE: Cancela job anterior y crea nuevo
            name=f"FAQ Survey for {wa_id}"
        )

        # 5. Actualizar BD con job_id
        execute("""
            UPDATE conversation_logs
            SET survey_scheduled = TRUE,
                survey_job_id = ?,
                updated_at = ?
            WHERE id = ?
        """, (job_id, datetime.utcnow().isoformat(), conversation_log_id))

        logger.info(
            f"[FAQ_SCHEDULER] ⏰ Encuesta programada para {wa_id} "
            f"a las {run_time.strftime('%H:%M:%S')} (en {delay_minutes} min)"
        )

    except Exception as e:
        logger.exception(f"[FAQ_SCHEDULER] Error al programar encuesta: {e}")


def cancel_pending_survey(wa_id: str):
    """
    Cancela una encuesta programada pendiente.

    Args:
        wa_id: WhatsApp ID del huésped
    """
    job_id = f"faq_survey_{wa_id}"

    try:
        job = scheduler.get_job(job_id)
        if job:
            scheduler.remove_job(job_id)
            logger.info(f"[FAQ_SCHEDULER] ❌ Job {job_id} cancelado")

            # Actualizar BD
            if DB_AVAILABLE:
                execute("""
                    UPDATE conversation_logs
                    SET survey_scheduled = FALSE,
                        survey_job_id = NULL,
                        updated_at = ?
                    WHERE wa_id = ?
                      AND survey_sent = FALSE
                """, (datetime.utcnow().isoformat(), wa_id))

    except Exception as e:
        logger.exception(f"[FAQ_SCHEDULER] Error al cancelar job: {e}")


# =====================================================
# Job de Encuesta (Se ejecuta después del delay)
# =====================================================

def _send_faq_survey_job(conversation_log_id: int, wa_id: str):
    """
    Job que se ejecuta después de 15 minutos.
    Verifica condiciones y envía encuesta Q1.

    Args:
        conversation_log_id: ID de conversation_logs
        wa_id: WhatsApp ID del huésped
    """
    logger.info(f"[FAQ_SCHEDULER] 🎯 Ejecutando job de encuesta para {wa_id}")

    if not DB_AVAILABLE:
        logger.error("[FAQ_SCHEDULER] BD no disponible, abortando job")
        return

    try:
        # 1. Obtener conversación
        conv = fetchone("""
            SELECT * FROM conversation_logs WHERE id = ?
        """, (conversation_log_id,))

        if not conv:
            logger.warning(f"[FAQ_SCHEDULER] Conversación {conversation_log_id} no encontrada")
            return

        # 2. Verificar que no se haya enviado ya
        if conv.get("survey_sent"):
            logger.info(f"[FAQ_SCHEDULER] Encuesta ya enviada para conv {conversation_log_id}, skip")
            return

        # 3. Verificar que haya al menos 1 FAQ
        if conv.get("faq_count", 0) == 0:
            logger.info(f"[FAQ_SCHEDULER] No hubo FAQs en conv {conversation_log_id}, skip")
            return

        # 4. Verificar que NO se haya creado ticket
        if conv.get("ticket_created"):
            logger.info(f"[FAQ_SCHEDULER] Se creó ticket en conv {conversation_log_id}, skip (usará encuesta de ticket)")
            return

        # 5. Verificar cooldown nuevamente (por si acaso)
        from gateway_app.services import conversation_logger
        can_send = conversation_logger.check_survey_cooldown(wa_id, cooldown_hours=24)

        if not can_send:
            logger.info(f"[FAQ_SCHEDULER] Huésped {wa_id} en cooldown al momento de enviar")
            return

        # 6. TODO OK → Enviar encuesta Q1
        whatsapp_api.send_text_message(
            to=conv["guest_phone"] or wa_id,
            text=FAQ_SURVEY_Q1_MESSAGE
        )

        # 7. Actualizar estado
        now = datetime.utcnow().isoformat()
        execute("""
            UPDATE conversation_logs
            SET survey_sent = TRUE,
                survey_sent_at = ?,
                survey_state = 'q1_sent',
                updated_at = ?
            WHERE id = ?
        """, (now, now, conversation_log_id))

        logger.info(f"[FAQ_SCHEDULER] ✅ Encuesta Q1 enviada a {wa_id} para conv {conversation_log_id}")

    except Exception as e:
        logger.exception(f"[FAQ_SCHEDULER] Error al ejecutar job de encuesta: {e}")
