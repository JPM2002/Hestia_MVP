from datetime import datetime
from typing import Any, Dict

from gateway_app.config import cfg
from gateway_app.services.db import (
    execute,
    insert_and_get_id,
    using_pg,
    table_has_column,
)
from gateway_app.services.sla import compute_due
from gateway_app.services.notify import _auto_assign_and_notify


def create_ticket(
    payload: Dict[str, Any],
    initial_status: str = "PENDIENTE_APROBACION",
) -> int:
    """
    Crea un ticket en la tabla `tickets` usando el payload proveniente del gateway
    y devuelve el id del ticket creado.
    """
    now = datetime.now()

    # SLA: prioridad + created_at
    try:
        due_dt = compute_due(priority=payload.get("prioridad"), created_at=now)
        due_at = due_dt.isoformat()
    except Exception as e:
        print(f"[WARN] compute_due failed: {e}", flush=True)
        due_at = None

    org_id = int(payload.get("org_id", getattr(cfg, "ORG_ID_DEFAULT", 2)))
    hotel_id = int(payload.get("hotel_id", getattr(cfg, "HOTEL_ID_DEFAULT", 1)))

    is_pg = using_pg()
    ph = "%s" if is_pg else "?"

    # Inserción principal en tickets
    sql = f"""
        INSERT INTO tickets(
            org_id,
            hotel_id,
            area,
            prioridad,
            estado,
            detalle,
            canal_origen,
            ubicacion,
            huesped_id,
            created_at,
            due_at,
            assigned_to,
            created_by,
            confidence_score,
            qr_required
        )
        VALUES (
            {ph}, {ph}, {ph}, {ph}, {ph},
            {ph}, {ph}, {ph}, {ph}, {ph},
            {ph}, {ph}, {ph}, {ph}, {ph}
        )
    """

    params = (
        org_id,
        hotel_id,
        payload.get("area"),
        payload.get("prioridad"),
        initial_status,
        payload.get("detalle"),
        payload.get("canal_origen", "huesped_whatsapp"),
        payload.get("ubicacion"),
        payload.get("huesped_id"),
        now.isoformat(),
        due_at,
        None,  # assigned_to
        None,  # created_by
        float(payload.get("confidence_score", 0.85)),
        bool(payload.get("qr_required", False)),
    )

    ticket_id = insert_and_get_id(sql, params)

    # Actualizar opcionalmente teléfono/nombre del huésped si las columnas existen
    guest_phone = payload.get("huesped_phone") or payload.get("huesped_id")
    guest_name = payload.get("huesped_nombre")

    try:
        sets = []
        upd_params = []
        if guest_phone and table_has_column("tickets", "huesped_phone"):
            sets.append(f"huesped_phone={ph}")
            upd_params.append(guest_phone)
        if guest_name and table_has_column("tickets", "huesped_nombre"):
            sets.append(f"huesped_nombre={ph}")
            upd_params.append(guest_name)

        if sets:
            upd_params.append(ticket_id)
            update_sql = f"UPDATE tickets SET {', '.join(sets)} WHERE id={ph}"
            execute(update_sql, upd_params, commit=True)
    except Exception as e:
        print(f"[WARN] could not persist guest phone/name: {e}", flush=True)

    # Historial inicial
    hph = "%s" if is_pg else "?"
    history_sql = (
        f"INSERT INTO tickethistory("
        f"ticket_id, actor_user_id, action, motivo, at"
        f") VALUES ({hph}, {hph}, {hph}, {hph}, {hph})"
    )

    execute(
        history_sql,
        (ticket_id, None, "CREADO", "via whatsapp", now.isoformat()),
        commit=True,
    )

    if initial_status == "PENDIENTE_APROBACION":
        execute(
            history_sql,
            (
                ticket_id,
                None,
                "PENDIENTE_APROBACION",
                "esperando aprobación de recepción",
                now.isoformat(),
            ),
            commit=True,
        )

    # Auto-asignación y notificación (best effort)
    try:
        _auto_assign_and_notify(
            ticket_id=ticket_id,
            area=payload.get("area"),
            prioridad=payload.get("prioridad"),
            detalle=payload.get("detalle"),
            ubicacion=payload.get("ubicacion"),
            org_id=org_id,
            hotel_id=hotel_id,
        )
    except Exception as e:
        print(f"[WARN] auto-assign/notify failed: {e}", flush=True)

    return ticket_id
