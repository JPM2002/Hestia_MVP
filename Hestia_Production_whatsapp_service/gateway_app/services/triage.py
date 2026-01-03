# gateway_app/services/triage.py
"""
Triage notification module for the WhatsApp gateway.

Responsibilities:
- Format ticket information into a WhatsApp-friendly message
- Send ticket notifications to triage phone numbers
- Provide immediate visibility for manual routing

Environment:
- TRIAGE_PHONE_NUMBERS: comma-separated list of phone numbers (e.g., "56912345678,56987654321")
- TRIAGE_ENABLED: enable/disable triage notifications (default: True)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from gateway_app.config import cfg
from gateway_app.services import whatsapp_api

logger = logging.getLogger(__name__)


def _get_triage_numbers() -> List[str]:
    """
    Parse TRIAGE_PHONE_NUMBERS env var into a list of phone numbers.
    
    Expected format: "56912345678,56987654321"
    """
    raw = (cfg.TRIAGE_PHONE_NUMBERS or "").strip()
    if not raw:
        return []
    
    numbers = []
    for num in raw.split(","):
        cleaned = num.strip()
        if cleaned:
            numbers.append(cleaned)
    
    return numbers


def _format_area_emoji(area: Optional[str]) -> str:
    """Return emoji for the ticket area."""
    area_emojis = {
        "HOUSEKEEPING": "🧹",
        "MANTENCION": "🔧",
        "ROOMSERVICE": "🍽️",
        "RECEPCION": "🛎️",
    }
    return area_emojis.get(area or "", "📋")


def _format_priority_indicator(priority: Optional[str]) -> str:
    """Return visual indicator for priority."""
    priority_indicators = {
        "URGENTE": "🔴 URGENTE",
        "ALTA": "🟠 Alta",
        "MEDIA": "🟡 Media",
        "BAJA": "🟢 Baja",
    }
    return priority_indicators.get(priority or "", "⚪ Sin prioridad")


def _format_timestamp(ts: Optional[datetime] = None) -> str:
    """Format timestamp for display."""
    if ts is None:
        ts = datetime.now(timezone.utc)
    # Format: "03/01/2026 14:30 UTC"
    return ts.strftime("%d/%m/%Y %H:%M UTC")


def format_triage_message(
    ticket_id: int,
    payload: Dict[str, Any],
    *,
    hotel_name: Optional[str] = None,
) -> str:
    """
    Format a ticket into a WhatsApp-friendly triage message.
    
    Args:
        ticket_id: The created ticket ID
        payload: The ticket payload dict with all fields
        hotel_name: Optional hotel name override
    
    Returns:
        Formatted string ready to send via WhatsApp
    """
    area = payload.get("area")
    area_emoji = _format_area_emoji(area)
    priority = payload.get("prioridad")
    priority_indicator = _format_priority_indicator(priority)
    
    # Build hotel identifier
    hotel_id = payload.get("hotel_id", cfg.HOTEL_ID_DEFAULT if hasattr(cfg, 'HOTEL_ID_DEFAULT') else 1)
    hotel_display = hotel_name or f"Hotel #{hotel_id}"
    
    room = payload.get("ubicacion") or "No especificada"
    detail = payload.get("detalle") or "Sin detalle"
    guest_name = payload.get("huesped_nombre") or "No identificado"
    guest_phone = payload.get("huesped_phone") or payload.get("huesped_id") or "No disponible"
    canal = payload.get("canal_origen", "whatsapp")
    timestamp = _format_timestamp()
    
    # Area display name
    area_names = {
        "HOUSEKEEPING": "Housekeeping",
        "MANTENCION": "Mantención",
        "ROOMSERVICE": "Room Service",
        "RECEPCION": "Recepción",
    }
    area_display = area_names.get(area, area or "No clasificada")
    
    # Build the message
    lines = [
        f"🧾 *Ticket #{ticket_id}* — {hotel_display}",
        "",
        f"{area_emoji} *Área:* {area_display}",
        f"🚨 *Prioridad:* {priority_indicator}",
        f"🚪 *Habitación:* {room}",
        "",
        f"👤 *Huésped:* {guest_name}",
        f"📱 *Teléfono:* {guest_phone}",
        "",
        f"📝 *Detalle:*",
        f"_{detail}_",
        "",
        f"⏰ {timestamp}",
        f"📡 Canal: {canal}",
        f"📌 Estado: PENDIENTE",
    ]
    
    return "\n".join(lines)


def notify_triage(
    ticket_id: int,
    payload: Dict[str, Any],
    *,
    hotel_name: Optional[str] = None,
) -> bool:
    """
    Send ticket notification to all triage phone numbers.
    
    Args:
        ticket_id: The created ticket ID
        payload: The ticket payload dict
        hotel_name: Optional hotel name for display
    
    Returns:
        True if at least one message was sent successfully, False otherwise
    """
    if not cfg.TRIAGE_ENABLED:
        logger.info(
            "[TRIAGE] Triage notifications disabled",
            extra={"ticket_id": ticket_id}
        )
        return False
    
    triage_numbers = _get_triage_numbers()
    
    if not triage_numbers:
        logger.warning(
            "[TRIAGE] No triage phone numbers configured (TRIAGE_PHONE_NUMBERS is empty)",
            extra={"ticket_id": ticket_id}
        )
        return False
    
    message = format_triage_message(ticket_id, payload, hotel_name=hotel_name)
    
    logger.info(
        "[TRIAGE] 📤 Sending ticket to triage channel",
        extra={
            "ticket_id": ticket_id,
            "triage_numbers_count": len(triage_numbers),
            "area": payload.get("area"),
            "room": payload.get("ubicacion"),
        }
    )
    
    success_count = 0
    
    for phone in triage_numbers:
        try:
            whatsapp_api.send_text_message(
                to=phone,
                text=message,
                preview_url=False,
            )
            logger.info(
                "[TRIAGE] ✅ Ticket sent to triage number",
                extra={
                    "ticket_id": ticket_id,
                    "phone": phone[-4:].rjust(len(phone), '*'),  # Mask phone for logs
                }
            )
            success_count += 1
            
        except Exception as e:
            logger.error(
                "[TRIAGE] ❌ Failed to send ticket to triage number",
                extra={
                    "ticket_id": ticket_id,
                    "phone": phone[-4:].rjust(len(phone), '*'),
                    "error": str(e),
                },
                exc_info=True,
            )
    
    if success_count > 0:
        logger.info(
            "[TRIAGE] ✅ Ticket notification complete",
            extra={
                "ticket_id": ticket_id,
                "success_count": success_count,
                "total_numbers": len(triage_numbers),
            }
        )
        return True
    
    logger.error(
        "[TRIAGE] ❌ Failed to notify any triage number",
        extra={"ticket_id": ticket_id}
    )
    return False    