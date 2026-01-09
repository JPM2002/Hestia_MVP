"""
Servicio de WhatsApp para Notification Service

Cliente simplificado para enviar mensajes vía WhatsApp Cloud API.
Reutiliza la lógica de gateway_app/services/whatsapp_api.py
"""

import logging
import os
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

WHATSAPP_API_BASE = "https://graph.facebook.com/v21.0"


class WhatsAppError(RuntimeError):
    """Error al comunicarse con WhatsApp Cloud API"""


def _get_config_value(key: str, default: str = "") -> str:
    """Obtiene valor de configuración desde env vars"""
    return os.getenv(key, default)


def _messages_url() -> str:
    """Construye la URL para enviar mensajes"""
    phone_id = _get_config_value("WHATSAPP_CLOUD_PHONE_ID", "").strip()
    if not phone_id:
        raise WhatsAppError("WHATSAPP_CLOUD_PHONE_ID no está configurado")
    return f"{WHATSAPP_API_BASE}/{phone_id}/messages"


def _headers() -> Dict[str, str]:
    """Headers para autenticación con WhatsApp API"""
    token = _get_config_value("WHATSAPP_CLOUD_TOKEN", "").strip()
    if not token:
        raise WhatsAppError("WHATSAPP_CLOUD_TOKEN no está configurado")

    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _post(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Envía POST a WhatsApp Cloud API"""
    url = _messages_url()
    logger.info(f"[WHATSAPP] Enviando mensaje: {payload}")

    try:
        resp = requests.post(url, headers=_headers(), json=payload, timeout=15)
        data = resp.json()

        if not resp.ok:
            logger.error(f"[WHATSAPP] Error {resp.status_code}: {data}")
            raise WhatsAppError(f"WhatsApp API error {resp.status_code}: {data}")

        logger.info(f"[WHATSAPP] Mensaje enviado exitosamente: {data}")
        return data

    except requests.RequestException as e:
        logger.exception(f"[WHATSAPP] Error de red: {e}")
        raise WhatsAppError(f"Error de red al enviar mensaje: {e}")


def send_text_message(to: str, text: str, preview_url: bool = False) -> Dict[str, Any]:
    """
    Envía un mensaje de texto a un número de WhatsApp.

    Args:
        to: Número de teléfono destino (formato: 521234567890)
        text: Contenido del mensaje
        preview_url: Si True, WhatsApp genera preview de URLs en el mensaje

    Returns:
        Respuesta de la API con message_id

    Raises:
        WhatsAppError: Si falla el envío
    """
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {
            "preview_url": preview_url,
            "body": text,
        },
    }

    return _post(payload)


def send_template_message(
    to: str,
    template_name: str,
    language: str = "es_MX",
    components: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Envía un mensaje de plantilla pre-aprobada.

    Args:
        to: Número de teléfono destino
        template_name: Nombre de la plantilla aprobada en Meta
        language: Código de idioma (por defecto es_MX)
        components: Componentes de la plantilla (parámetros, botones, etc.)

    Returns:
        Respuesta de la API con message_id

    Raises:
        WhatsAppError: Si falla el envío
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
        },
    }

    if components:
        payload["template"]["components"] = components

    return _post(payload)


def mark_as_read(message_id: str) -> Dict[str, Any]:
    """
    Marca un mensaje como leído.

    Args:
        message_id: ID del mensaje a marcar como leído

    Returns:
        Respuesta de la API
    """
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }

    return _post(payload)
