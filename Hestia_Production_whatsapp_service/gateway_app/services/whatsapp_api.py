# gateway_app/services/whatsapp_api.py
"""
Wrapper para la WhatsApp Cloud API.

Responsabilidades principales:
- Construir el endpoint correcto usando WHATSAPP_CLOUD_PHONE_ID.
- Adjuntar el token de acceso WHATSAPP_CLOUD_TOKEN.
- Proveer funciones sencillas para:
  - Enviar mensajes de texto.
  - Enviar plantillas.
  - Marcar mensajes como leídos.
  - Enviar reacciones.
  - (Opcional) enviar 'typing' / acción de escritura.

Este módulo NO sabe nada del negocio de Hestia; solo de hablar con la API.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests

from gateway_app.config import cfg

logger = logging.getLogger(__name__)

WHATSAPP_API_BASE = "https://graph.facebook.com/v21.0"


class WhatsAppAPIError(RuntimeError):
    """Errores de llamada a la WhatsApp Cloud API."""


def _messages_url() -> str:
    """
    Construye la URL base para POST /{phone-number-id}/messages.
    """
    phone_id = (cfg.WHATSAPP_CLOUD_PHONE_ID or "").strip()
    if not phone_id:
        logger.error("WHATSAPP_CLOUD_PHONE_ID no está configurado.")
        raise WhatsAppAPIError("WHATSAPP_CLOUD_PHONE_ID is missing.")
    return f"{WHATSAPP_API_BASE}/{phone_id}/messages"


def _headers(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Cabeceras comunes para todas las llamadas a la Cloud API.
    """
    token = (cfg.WHATSAPP_CLOUD_TOKEN or "").strip()
    if not token:
        logger.error("WHATSAPP_CLOUD_TOKEN no está configurado.")
        raise WhatsAppAPIError("WHATSAPP_CLOUD_TOKEN is missing.")

    headers: Dict[str, str] = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def _post(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Helper para enviar un POST a /{phone-number-id}/messages con manejo de errores.
    """
    url = _messages_url()
    logger.info("Enviando mensaje a WhatsApp Cloud API", extra={"payload": payload})

    resp = requests.post(url, headers=_headers(), json=payload, timeout=15)

    try:
        data = resp.json()
    except Exception:
        logger.exception("No se pudo decodificar la respuesta de WhatsApp como JSON")
        # Si no es JSON pero el status es OK, aún así fallamos controladamente
        if resp.ok:
            raise WhatsAppAPIError("WhatsApp response is not valid JSON.")
        resp.raise_for_status()
        raise WhatsAppAPIError("WhatsApp request failed and response is not JSON.")

    if not resp.ok:
        logger.error(
            "Error en WhatsApp API %s: %s", resp.status_code, data
        )
        raise WhatsAppAPIError(f"WhatsApp API error {resp.status_code}: {data}")

    return data


# ---------------------------------------------------------------------------
# Funciones públicas de envío
# ---------------------------------------------------------------------------


def send_whatsapp_text(
    to: str,
    text: str,
    *,
    preview_url: bool = False,
) -> Dict[str, Any]:
    """
    Enviar un mensaje de texto sencillo a un número de WhatsApp.

    Args:
        to: wa_id del destinatario (ej. '56998765432').
        text: cuerpo del mensaje.
        preview_url: si es True, permite previsualización de enlaces (si los hay).

    Returns:
        dict con el JSON de respuesta de la API.
    """
    payload: Dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {
            "body": text,
            "preview_url": preview_url,
        },
    }
    return _post(payload)


def send_whatsapp_template(
    to: str,
    template_name: str,
    *,
    lang: str = "es",
    components: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Enviar una plantilla de WhatsApp previamente aprobada.

    Args:
        to: wa_id del destinatario.
        template_name: nombre EXACTO de la plantilla en Meta.
        lang: código de idioma, por ejemplo 'es', 'es_CL', 'en_US'.
        components: lista opcional de 'components' para variables de la plantilla.

    Ejemplo components:
        [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": "Huésped"},
                    {"type": "text", "text": "123"},
                ],
            }
        ]
    """
    template: Dict[str, Any] = {
        "name": template_name,
        "language": {"code": lang},
    }
    if components:
        template["components"] = components

    payload: Dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": template,
    }
    return _post(payload)


def mark_whatsapp_message_read(message_id: str) -> Dict[str, Any]:
    """
    Marcar un mensaje entrante como 'read' en la Cloud API.

    Args:
        message_id: id del mensaje recibido (wamid...)

    Returns:
        dict con el JSON de respuesta.
    """
    payload: Dict[str, Any] = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    return _post(payload)


def send_whatsapp_reaction(
    to: str,
    message_id: str,
    emoji: str,
) -> Dict[str, Any]:
    """
    Enviar una reacción (emoji) a un mensaje.

    Args:
        to: wa_id del destinatario.
        message_id: id del mensaje al que reaccionamos.
        emoji: carácter emoji, por ejemplo "👍" o "✅".
    """
    payload: Dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "reaction",
        "reaction": {
            "message_id": message_id,
            "emoji": emoji,
        },
    }
    return _post(payload)


def send_whatsapp_typing(
    to: str,
    *,
    typing_on: bool = True,
) -> Dict[str, Any]:
    """
    Enviar señal de 'escribiendo' (typing).

    Nota: La estructura exacta puede variar según la versión de la API.
    Ajusta si Meta cambia el formato.

    Args:
        to: wa_id del destinatario.
        typing_on: True para "escribiendo", False para detener.

    Returns:
        dict con la respuesta de la API.
    """
    # Algunos ejemplos de documentación usan "typing" con valores "typing" / "stopped".
    state = "typing" if typing_on else "stopped"

    payload: Dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "typing",
        "typing": state,
    }
    return _post(payload)

# ---------------------------------------------------------------------------
# Backwards-compatible wrapper names used by routes.py
# ---------------------------------------------------------------------------


def send_text_message(
    to: str,
    text: str,
    *,
    preview_url: bool = False,
) -> Dict[str, Any]:
    """
    Backwards-compatible alias for send_whatsapp_text, so older code that calls
    whatsapp_api.send_text_message() keeps working.
    """
    return send_whatsapp_text(to=to, text=text, preview_url=preview_url)


def mark_message_as_read(message_id: str) -> Dict[str, Any]:
    """
    Backwards-compatible alias for mark_whatsapp_message_read, so older code
    that calls whatsapp_api.mark_message_as_read() keeps working.
    """
    return mark_whatsapp_message_read(message_id)

