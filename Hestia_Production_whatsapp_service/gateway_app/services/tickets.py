# gateway_app/services/tickets.py

from __future__ import annotations

from datetime import datetime
import os
from typing import Any, Dict

from gateway_app.services.sla import compute_due      # AJUSTA si tu módulo tiene otro nombre
from gateway_app.services.db import (                 # AJUSTA estos imports a tu proyecto real
    execute,
    insert_and_get_id,
    using_pg,
    table_has_column,
)
from gateway_app.services.notify import _auto_assign_and_notify  # AJUSTA si está en otro módulo

# Defaults para org/hotel (puedes cambiarlos o ponerlos en env)
ORG_ID_DEFAULT = int(os.getenv("ORG_ID_DEFAULT", "1"))
HOTEL_ID_DEFAULT = int(os.getenv("HOTEL_ID_DEFAULT", "1"))


# ----------------------------- Ticket creation -----------------------------
def create_ticket(
    payload: Dict[str, Any],
    initial_status: str = "PENDIENTE_APROBACION",
) -> int:
    """
    Crea un ticket en la tabla tickets y registra el historial,
    imitando el comportamiento del código monolítico original.
    """
    now = datetime.now()
    due_dt = compute_due(payload["area"], payload["prioridad"])
    due_at = due_dt.isoformat() if due_dt else None

    # Normalizar org/hotel (usa defaults si no vienen en payload)
    org_id = int(payload.get("org_id", ORG_ID_DEFAULT))
    hotel_id = int(payload.get("hotel_id", HOTEL_ID_DEFAULT))

    new_id = insert_and_get_id(
        """
        INSERT INTO tickets(org_id, hotel_id, area, prioridad, estado, detalle, canal_origen,
                            ubicacion, huesped_id, created_at, due_at,
                            assigned_to, created_by, confidence_score, qr_required)
        VALUES (%s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s)
        """ if using_pg() else
        """
        INSERT INTO tickets(org_id, hotel_id, area, prioridad, estado, detalle, canal_origen,
                            ubicacion, huesped_id, created_at, due_at,
                            assigned_to, created_by, confidence_score, qr_required)
        VALUES (?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?)
        """,
        (
            org_id,
            hotel_id,
            payload["area"],
            payload["prioridad"],
            initial_status,
            payload["detalle"],
            payload.get("canal_origen", "huesped_whatsapp"),
            payload.get("ubicacion"),
            payload.get("huesped_id"),
            now.isoformat(),
            due_at,
            None,
            None,
            float(payload.get("confidence_score", 0.85)),
            bool(payload.get("qr_required", False)),
        )
    )

    # Persistir teléfono / nombre del huésped si existen las columnas
    guest_phone = payload.get("huesped_phone") or payload.get("huesped_id")
    guest_name = payload.get("huesped_nombre")
    try:
        sets, params = [], []
        if guest_phone and table_has_column("tickets", "huesped_phone"):
            sets.append("huesped_phone=%s" if using_pg() else "huesped_phone=?")
            params.append(guest_phone)
        if guest_name and table_has_column("tickets", "huesped_nombre"):
            sets.append("huesped_nombre=%s" if using_pg() else "huesped_nombre=?")
            params.append(guest_name)
        if sets:
            params.append(new_id)
            sql = (
                f"UPDATE tickets SET {', '.join(sets)} WHERE id=%s"
                if using_pg()
                else f"UPDATE tickets SET {', '.join(sets)} WHERE id=?"
            )
            execute(sql, tuple(params))
    except Exception as e:
        print(f"[WARN] could not persist guest phone/name: {e}", flush=True)

    # Historial de creación
    execute(
        "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (%s, %s, %s, %s, %s)"
        if using_pg() else
        "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (?, ?, ?, ?, ?)",
        (new_id, None, "CREADO", "via whatsapp", now.isoformat()),
    )
    if initial_status == "PENDIENTE_APROBACION":
        execute(
            "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (%s, %s, %s, %s, %s)"
            if using_pg() else
            "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (?, ?, ?, ?, ?)",
            (new_id, None, "PENDIENTE_APROBACION", "esperando aprobación de recepción", now.isoformat()),
        )

    # Auto-asignar y notificar técnico según área / org / hotel
    try:
        _auto_assign_and_notify(
            ticket_id=new_id,
            area=payload["area"],
            prioridad=payload["prioridad"],
            detalle=payload.get("detalle"),
            ubicacion=payload.get("ubicacion"),
            org_id=org_id,
            hotel_id=hotel_id,
        )
    except Exception as e:
        print(f"[WARN] auto-assign/notify failed: {e}", flush=True)

    return new_id
