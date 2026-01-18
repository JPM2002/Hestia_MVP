# gateway_app/services/notifications/supervisor_notify.py
from __future__ import annotations

import os
import re
import logging
from typing import Any, Dict, List, Optional

from gateway_app.services.whatsapp_api import send_whatsapp_text
from gateway_app.services.workers_db import buscar_worker_por_telefono

logger = logging.getLogger(__name__)


def _normalize_phone(phone: str) -> str:
    # keep digits only (matches your workers_db normalization + WhatsApp "to" usage)
    return re.sub(r"\D", "", (phone or "").strip())


def _get_supervisor_phones() -> List[str]:
    raw = os.getenv("SUPERVISOR_PHONES", "") or ""
    phones = [_normalize_phone(p) for p in raw.split(",")]
    phones = [p for p in phones if p]
    return phones


def _priority_emoji(prioridad: Optional[str]) -> str:
    p = (prioridad or "").upper().strip()
    return {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(p, "🟡")


def notify_supervisors_ticket_created(ticket_id: int, payload: Dict[str, Any]) -> None:
    """
    Best-effort: send WhatsApp message to supervisors when a ticket is created.

    Expected payload keys (best):
      - creado_por OR from_phone OR worker_phone (phone)
      - ubicacion (string)
      - detalle (string)
      - prioridad (ALTA/MEDIA/BAJA)
      - area (HOUSEKEEPING/AREAS_COMUNES/MANTENIMIENTO/...)
    """
    supervisors = _get_supervisor_phones()
    if not supervisors:
        logger.info("SUP_NOTIFY skipped: no SUPERVISOR_PHONES configured")
        return

    creado_por = (
        payload.get("creado_por")
        or payload.get("from_phone")
        or payload.get("worker_phone")
        # guest fields are fallback-only; not ideal for worker lookup
        or payload.get("huesped_phone")
        or payload.get("huesped_id")
    )
    creado_por_n = _normalize_phone(creado_por) if isinstance(creado_por, str) else ""

    worker_nombre = "Trabajador"
    if creado_por_n:
        try:
            # buscar_worker_por_telefono already normalizes too, but we pass normalized anyway
            worker = buscar_worker_por_telefono(creado_por_n)
            if worker:
                worker_nombre = (
                    worker.get("nombre_completo")
                    or worker.get("nombre")
                    or worker_nombre
                )
        except Exception as e:
            # never block notifications
            logger.warning("SUP_NOTIFY worker lookup failed phone=%s err=%s", creado_por_n, e)

    ubicacion = payload.get("ubicacion") or payload.get("habitacion") or "—"
    detalle = payload.get("detalle") or ""
    prioridad = payload.get("prioridad") or "MEDIA"
    area = payload.get("area") or "HOUSEKEEPING"
    emoji = _priority_emoji(prioridad)

    message_text = (
        f"📋 Nuevo reporte de {worker_nombre}\n\n"
        f"#{ticket_id} · {ubicacion}\n"
        f"{detalle}\n"
        f"{emoji} Prioridad: {str(prioridad).upper()}\n"
        f"🧩 Área: {str(area).upper()}\n\n"
        f"💡 Di 'asignar {ticket_id} a [nombre]' para derivar"
    )

    logger.info("SUP_NOTIFY targets=%s ticket_id=%s", supervisors, ticket_id)

    for sup_phone in supervisors:
        try:
            # ✅ FIX: whatsapp_api.send_whatsapp_text expects (to, text)
            send_whatsapp_text(to=sup_phone, text=message_text)
            logger.info("SUP_NOTIFY sent ticket_id=%s to=%s", ticket_id, sup_phone)
        except Exception as e:
            logger.warning("SUP_NOTIFY failed ticket_id=%s to=%s err=%s", ticket_id, sup_phone, e)
