"""
Configuración del Notification Service

Carga variables de entorno y provee configuración centralizada.
"""

import os
from typing import Optional


class NotificationConfig:
    """Configuración centralizada del servicio de notificaciones"""

    # Worker configuration
    POLLING_INTERVAL_SECONDS: int = int(os.getenv("POLLING_INTERVAL_SECONDS", "10"))

    # Notificaciones habilitadas/deshabilitadas
    ENABLE_ASSIGNMENT_NOTIFICATIONS: bool = os.getenv("ENABLE_ASSIGNMENT_NOTIFICATIONS", "true").lower() == "true"
    ENABLE_RESOLUTION_NOTIFICATIONS: bool = os.getenv("ENABLE_RESOLUTION_NOTIFICATIONS", "true").lower() == "true"
    ENABLE_CSAT_SURVEYS: bool = os.getenv("ENABLE_CSAT_SURVEYS", "true").lower() == "true"
    ENABLE_FAQ_SURVEYS: bool = os.getenv("ENABLE_FAQ_SURVEYS", "true").lower() == "true"

    # Delays (esperar X segundos antes de enviar)
    FAQ_SURVEY_DELAY_SECONDS: int = int(os.getenv("FAQ_SURVEY_DELAY_SECONDS", "30"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Retry configuration
    MAX_NOTIFICATION_RETRIES: int = int(os.getenv("MAX_NOTIFICATION_RETRIES", "3"))

    @classmethod
    def validate(cls) -> None:
        """Valida que las configuraciones críticas estén presentes"""
        errors = []

        # Las validaciones de WhatsApp y DB se hacen en tiempo de ejecución
        # ya que dependen de la configuración principal

        if errors:
            raise ValueError(f"Errores de configuración: {', '.join(errors)}")

    @classmethod
    def log_config(cls) -> None:
        """Imprime la configuración actual (sin secretos)"""
        print(f"[NOTIFICATION CONFIG] POLLING_INTERVAL_SECONDS: {cls.POLLING_INTERVAL_SECONDS}")
        print(f"[NOTIFICATION CONFIG] ENABLE_ASSIGNMENT_NOTIFICATIONS: {cls.ENABLE_ASSIGNMENT_NOTIFICATIONS}")
        print(f"[NOTIFICATION CONFIG] ENABLE_RESOLUTION_NOTIFICATIONS: {cls.ENABLE_RESOLUTION_NOTIFICATIONS}")
        print(f"[NOTIFICATION CONFIG] ENABLE_CSAT_SURVEYS: {cls.ENABLE_CSAT_SURVEYS}")
        print(f"[NOTIFICATION CONFIG] ENABLE_FAQ_SURVEYS: {cls.ENABLE_FAQ_SURVEYS}")
        print(f"[NOTIFICATION CONFIG] LOG_LEVEL: {cls.LOG_LEVEL}")


notification_cfg = NotificationConfig()
