"""
Notification Worker - Polling Service

Este worker corre en un loop infinito, revisando periódicamente
la base de datos en busca de notificaciones pendientes.

Responsabilidades:
- Polling cada X segundos (configurable)
- Ejecutar handlers de notificaciones
- Manejo de errores y retry
- Logging detallado
- Graceful shutdown
"""

import logging
import signal
import sys
import time
from datetime import datetime
from typing import Optional

from gateway_app.services.notifications.notification_config import notification_cfg
from gateway_app.services.notifications.handlers import process_all_notifications

# Configurar logging
logging.basicConfig(
    level=getattr(logging, notification_cfg.LOG_LEVEL.upper(), logging.INFO),
    format="[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


class NotificationWorker:
    """
    Worker principal que ejecuta el polling loop.
    """

    def __init__(self):
        self.running = False
        self.iteration_count = 0
        self.total_notifications_sent = 0
        self.start_time: Optional[datetime] = None

        # Registrar handlers de señales para graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handler para SIGINT (Ctrl+C) y SIGTERM"""
        signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
        logger.info(f"[WORKER] Recibida señal {signal_name}, iniciando shutdown...")
        self.stop()

    def start(self):
        """Inicia el worker en modo polling"""
        logger.info("=" * 80)
        logger.info("🚀 NOTIFICATION SERVICE - INICIANDO")
        logger.info("=" * 80)

        # Validar configuración
        try:
            notification_cfg.validate()
            notification_cfg.log_config()
        except ValueError as e:
            logger.error(f"[WORKER] Error de configuración: {e}")
            sys.exit(1)

        self.running = True
        self.start_time = datetime.utcnow()

        logger.info(f"[WORKER] Polling interval: {notification_cfg.POLLING_INTERVAL_SECONDS}s")
        logger.info(f"[WORKER] Worker iniciado exitosamente")
        logger.info("=" * 80)

        # Loop principal
        while self.running:
            try:
                self._run_iteration()
            except KeyboardInterrupt:
                logger.info("[WORKER] Interrupción de teclado detectada")
                break
            except Exception as e:
                logger.exception(f"[WORKER] Error inesperado en iteración: {e}")

            # Esperar antes de la siguiente iteración
            if self.running:
                time.sleep(notification_cfg.POLLING_INTERVAL_SECONDS)

        self._shutdown()

    def _run_iteration(self):
        """Ejecuta una iteración del polling"""
        self.iteration_count += 1
        iteration_start = time.time()

        logger.debug(f"[WORKER] === Iteración #{self.iteration_count} ===")

        try:
            # Procesar todas las notificaciones pendientes
            results = process_all_notifications()

            # Actualizar contadores
            notifications_sent = sum(results.values())
            self.total_notifications_sent += notifications_sent

            # Log de resultados
            if notifications_sent > 0:
                logger.info(
                    f"[WORKER] Iteración #{self.iteration_count}: "
                    f"{notifications_sent} notificaciones enviadas - "
                    f"Asignaciones: {results['assignments']}, "
                    f"En Curso: {results['in_progress']}, "
                    f"Resoluciones: {results['resolutions']}, "
                    f"FAQ: {results['faq_surveys']}"
                )
            else:
                logger.debug(f"[WORKER] Iteración #{self.iteration_count}: Sin notificaciones pendientes")

        except Exception as e:
            logger.exception(f"[WORKER] Error al procesar notificaciones: {e}")

        # Tiempo de ejecución
        elapsed = time.time() - iteration_start
        logger.debug(f"[WORKER] Iteración completada en {elapsed:.2f}s")

    def stop(self):
        """Detiene el worker de forma controlada"""
        logger.info("[WORKER] Deteniendo worker...")
        self.running = False

    def _shutdown(self):
        """Limpieza y estadísticas finales"""
        logger.info("=" * 80)
        logger.info("🛑 NOTIFICATION SERVICE - SHUTDOWN")
        logger.info("=" * 80)

        if self.start_time:
            uptime = datetime.utcnow() - self.start_time
            logger.info(f"[WORKER] Uptime: {uptime}")

        logger.info(f"[WORKER] Total iteraciones: {self.iteration_count}")
        logger.info(f"[WORKER] Total notificaciones enviadas: {self.total_notifications_sent}")
        logger.info("=" * 80)
        logger.info("✅ Worker detenido exitosamente")


def main():
    """Entry point del worker"""
    worker = NotificationWorker()
    try:
        worker.start()
    except Exception as e:
        logger.exception(f"[WORKER] Error fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
