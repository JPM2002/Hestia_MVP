# gateway_app/services/notifications/supervisor_notify.py
from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional

from gateway_app.services.whatsapp_api import send_whatsapp_text
from gateway_app.services.workers_db import buscar_worker_por_telefono

logger = logging.getLogger(__name__)


def _get_supervisor_phones() -> List[str]:
    raw = os.getenv("SUPERVISOR_PHONES", "") or ""
    phones = [p.strip() for p in raw.split(",") if p.strip()]
    return phones


def _priority_emoji(prioridad: Optional[str]) -> str:
    p = (prioridad or "").upper().strip()
    return {"ALTA": "🔴", "MEDIA": "🟡", "BAJA": "🟢"}.get(p, "🟡")


def notify_supervisors_ticket_created(ticket_id: int, payload: Dict[str, Any]) -> None:
    """
    Best-effort: send WhatsApp message to supervisors when a ticket is created.

    Expects payload keys (best):
      - creado_por OR from_phone OR worker_phone  (worker phone)
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
        or payload.get("huesped_phone")
        or payload.get("huesped_id")
    )

    worker_nombre = "Trabajador"
    if isinstance(creado_por, str) and creado_por.strip():
        try:
            worker = buscar_worker_por_telefono(creado_por)
            if worker:
                worker_nombre = worker.get("nombre_completo") or worker.get("nombre") or worker_nombre
        except Exception as e:
            logger.warning("SUP_NOTIFY worker lookup failed phone=%s err=%s", creado_por, e)

    ubicacion = payload.get("ubicacion") or payload.get("habitacion") or "—"
    detalle = payload.get("detalle") or ""
    prioridad = payload.get("prioridad") or "MEDIA"
    area = payload.get("area") or "HOUSEKEEPING"
    emoji = _priority_emoji(prioridad)

    # If you want fancy formatting, you can plug your helper here later.
    # Keeping it simple avoids coupling tickets service to bot-flow helpers.
    body = (
        f"📋 Nuevo reporte de {worker_nombre}\n\n"
        f"#{ticket_id} · {ubicacion}\n"
        f"{detalle}\n"
        f"{emoji} Prioridad: {str(prioridad).upper()}\n"
        f"🧩 Área: {str(area).upper()}\n\n"
        f"💡 Di 'asignar {ticket_id} a [nombre]' para derivar"
    )

    for sup_phone in supervisors:
        try:
            send_whatsapp_text(to=sup_phone, body=body)
            logger.info("SUP_NOTIFY sent ticket_id=%s to=%s", ticket_id, sup_phone)
        except Exception as e:
            logger.warning("SUP_NOTIFY failed ticket_id=%s to=%s err=%s", ticket_id, sup_phone, e)
