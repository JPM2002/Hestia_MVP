# hestia_app/blueprints/tickets/routes.py
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
    current_app,
    g,
    abort,
)
from werkzeug.utils import secure_filename

from ...core.area import require_perm
from ...core.scope import current_scope
from ...services.db import execute, insert_and_get_id, fetchone, fetchall, using_pg
from ...services.sla import compute_due
from ...core.rbac import current_org_role, _require_area_manage
from ...services.notify import _notify_tech_assignment, _notify_guest_final
from ...core.errors import _err_or_redirect, _ok_or_redirect
from ...core.status import nice_state
from ...blueprints.tecnico.routes import _guard_active_shift

from . import bp


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------

def _period_bounds(period: str):
    """
    Returns (start_iso, end_iso or None) for filter periods.
    """
    now = datetime.now()
    sod = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if period == "today":
        return (sod.isoformat(), None)
    if period == "yesterday":
        y0 = (sod - timedelta(days=1)).isoformat()
        return (y0, sod.isoformat())
    if period == "7d":
        return ((sod - timedelta(days=7)).isoformat(), None)
    if period == "30d":
        return ((sod - timedelta(days=30)).isoformat(), None)
    return (None, None)


def _safe_is_critical(now, due_at):
    """
    Uses services.sla.is_critical() if present; falls back to due_at <= now.
    """
    try:
        from ...services.sla import is_critical  # type: ignore
        return is_critical(now, due_at)
    except Exception:
        pass

    if not due_at:
        return False
    try:
        dt = datetime.fromisoformat(str(due_at))
    except Exception:
        return False
    return dt <= now


# ----------------- Estados abiertos reutilizables -----------------
try:
    from hestia_app.core.status import OPEN_STATES
except Exception:  # pragma: no cover
    OPEN_STATES = ("PENDIENTE", "ASIGNADO", "ACEPTADO", "EN_CURSO", "PAUSADO", "DERIVADO")


# --------------------------------------------------------------------
# Editar ticket (Recepción/Supervisor/Gerente)
# --------------------------------------------------------------------

@bp.post("/tickets/<int:ticket_id>/edit")
@require_perm("tickets:change_state")  # permiso genérico para edición
def ticket_edit(ticket_id: int):
    if "user" not in session:
        return jsonify({"ok": False, "error": "No autenticado"}), 401

    # Respeta multi-tenant y devuelve None si no corresponde a la org actual
    t = _get_ticket_or_abort(ticket_id)
    if t is None:
        return jsonify({"ok": False, "error": "Ticket no encontrado"}), 404

    # RBAC extra: un SUPERVISOR solo puede editar su área
    role = current_org_role()
    if role == "SUPERVISOR":
        _require_area_manage(t["area"])

    detalle = (request.form.get("detalle") or "").strip()
    prioridad = (request.form.get("prioridad") or "").strip().upper() or None
    ubicacion = (request.form.get("ubicacion") or "").strip() or None

    # sanitize prioridad
    valid_prios = {"URGENTE", "ALTA", "MEDIA", "BAJA"}
    if prioridad and prioridad not in valid_prios:
        return jsonify({"ok": False, "error": "Prioridad inválida"}), 400

    fields: Dict[str, Any] = {
        "detalle": detalle or None,
        "prioridad": prioridad,
        "ubicacion": ubicacion,
    }

    # Usa el helper común: hace UPDATE + TicketHistory("EDITADO")
    _update_ticket(ticket_id, fields, "EDITADO")

    # El frontend de recepción solo mira r.ok, así que basta con 200 + JSON
    return jsonify({"ok": True})



# --------------------------------------------------------------------
# Listado de tickets (vista clásica)
# --------------------------------------------------------------------

@bp.get("/tickets", endpoint="tickets")
@require_perm("tickets:view_all")  # listado global por organización
def ticket_list():
    """
    Canonical list/landing for Tickets.
    Endpoint name = 'tickets.tickets' so the navbar link in base.html works.
    Renders templates/tickets.html (or tickets/tickets.html depending on blueprint config).
    """
    org_id, _ = current_scope()
    if not org_id:
        flash("Sin contexto de organización.", "error")
        return redirect(url_for("dashboard.index"))

    # --- Filters (match your tickets.html form) ---
    q         = (request.args.get("q") or "").strip()
    area      = (request.args.get("area") or "").strip().upper()
    prioridad = (request.args.get("prioridad") or "").strip().upper()
    estado    = (request.args.get("estado") or "").strip().upper()
    period    = (request.args.get("period") or "today").strip()

    where, params = ["org_id=?"], [org_id]

    if q:
        where.append("(detalle LIKE ? OR ubicacion LIKE ?)")
        like = f"%{q}%"
        params += [like, like]
    if area:
        where.append("area=?")
        params.append(area)
    if prioridad:
        where.append("prioridad=?")
        params.append(prioridad)
    if estado:
        where.append("estado=?")
        params.append(estado)

    start, end = _period_bounds(period)
    if start and end:
        where.append("created_at>=? AND created_at<?")
        params += [start, end]
    elif start:
        where.append("created_at>=?")
        params.append(start)

    rows = fetchall(
        f"""
        SELECT id, area, prioridad, estado, detalle, ubicacion, canal_origen,
               created_at, due_at, finished_at
        FROM Tickets
        WHERE {' AND '.join(where)}
        ORDER BY created_at DESC
        LIMIT 200
        """,
        tuple(params),
    )

    now = datetime.now()
    tickets = [
        {
            "id": r["id"],
            "area": r["area"],
            "prioridad": r["prioridad"],
            "estado": r["estado"],
            "detalle": r["detalle"],
            "ubicacion": r["ubicacion"],
            "canal": r.get("canal_origen"),
            "created_at": r["created_at"],
            "due_at": r.get("due_at"),
            "finished_at": r.get("finished_at"),
            "is_critical": _safe_is_critical(now, r.get("due_at")),
        }
        for r in rows
    ]

    filters = {
        "q": q,
        "area": area,
        "prioridad": prioridad,
        "estado": estado,
        "period": period,
    }

    return render_template(
        "tickets.html",
        user=session.get("user"),
        tickets=tickets,
        filters=filters,
        device=getattr(g, "device", None),
        view=getattr(g, "view_mode", "auto"),
    )


# --------------------------------------------------------------------
# Crear ticket
# --------------------------------------------------------------------

@bp.route("/tickets/create", methods=["GET", "POST"])
@require_perm("tickets:create")
def ticket_create():
    if "user" not in session:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        org_id, hotel_id = current_scope()
        if not org_id or not hotel_id:
            flash("Falta contexto de organización/hotel.", "error")
            nxt = (
                request.args.get("next")
                or request.form.get("next")
                or request.referrer
            )
            return redirect(nxt or url_for("tickets"))

        area       = (request.form.get("area") or "").strip().upper()
        prioridad  = (request.form.get("prioridad") or "").strip().upper()
        detalle    = (request.form.get("detalle") or "").strip()
        ubicacion  = (request.form.get("ubicacion") or "").strip()
        canal      = (request.form.get("canal_origen") or "recepcion").strip()
        huesped_id = (request.form.get("huesped_id") or "").strip() or None
        qr_required = 1 if request.form.get("qr_required") else 0

        created_at = datetime.now()
        due_dt = compute_due(created_at, area, prioridad)
        due_at = due_dt.isoformat() if due_dt else None

        try:
            # Alinear con la nueva tabla tickets (ver SCHEMA_SQL)
            new_id = insert_and_get_id(
                """
                INSERT INTO Tickets(
                    org_id, hotel_id,
                    area, prioridad, estado, detalle,
                    canal_origen, ubicacion, huesped_id,
                    created_at, due_at,
                    assigned_to, created_by,
                    confidence_score, qr_required
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    org_id,
                    hotel_id,
                    area,
                    prioridad,
                    "PENDIENTE",
                    detalle,
                    canal,
                    ubicacion,
                    huesped_id,
                    created_at.isoformat(),
                    due_at,
                    None,                         # assigned_to
                    session["user"]["id"],        # created_by
                    None,                         # confidence_score
                    qr_required,
                ),
            )

            execute(
                """
                INSERT INTO TicketHistory(ticket_id, actor_user_id, action, motivo, at)
                VALUES (?,?,?,?,?)
                """,
                (
                    new_id,
                    session["user"]["id"],
                    "CREADO",
                    None,
                    created_at.isoformat(),
                ),
            )

            flash(f"Ticket #{new_id} creado.", "success")

            # redirige de vuelta a la pantalla que originó la creación (si es interna)
            nxt = (
                request.args.get("next")
                or request.form.get("next")
                or request.referrer
            )
            if nxt and str(nxt).startswith("/"):
                return redirect(nxt)
            return redirect(url_for("tickets"))

        except Exception as e:
            current_app.logger.exception("Error creando ticket")
            flash(f"Error creando ticket: {e}", "error")
            nxt = (
                request.args.get("next")
                or request.form.get("next")
                or request.referrer
            )
            return redirect(nxt or url_for("tickets"))

    # GET
    areas = ["MANTENCION", "HOUSEKEEPING", "ROOMSERVICE"]
    prioridades = ["BAJA", "MEDIA", "ALTA", "URGENTE"]
    canales = [
        "recepcion",
        "huesped_whatsapp",
        "housekeeping_whatsapp",
        "mantenimiento_app",
        "roomservice_llamada",
    ]
    return render_template(
        "ticket_create.html",
        user=session["user"],
        areas=areas,
        prioridades=prioridades,
        canales=canales,
    )


# --------------------------------------------------------------------
# Confirm / aprobar ticket
# --------------------------------------------------------------------

@bp.post("/tickets/<int:id>/confirm")
@require_perm("tickets:approve")  # código nuevo: GERENTE (y SUPERADMIN)
def ticket_confirm(id: int):
    """
    Recepción/Supervisor/Gerente confirman o aprueban (incluye PENDIENTE_APROBACION),
    auto-asignan y notifican por WA.

    Además:
    - Marca approved / approved_by / approved_at
    """
    if "user" not in session:
        return redirect(url_for("auth.login"))

    user = session["user"]
    org_id, _ = current_scope()

    t = fetchone(
        """
        SELECT id, org_id, area, prioridad, estado, detalle, ubicacion, assigned_to
        FROM Tickets
        WHERE id=?
        """,
        (id,),
    )
    if not t or (org_id and t["org_id"] != org_id):
        flash("Ticket no encontrado.", "error")
        return redirect(url_for("tickets"))

    if t["estado"] not in ("PENDIENTE_APROBACION", "PENDIENTE"):
        flash("Solo puedes confirmar/aprobar tickets pendientes.", "error")
        return redirect(url_for("tickets"))

    role = current_org_role()

    # SUPERVISOR: solo su área
    if role == "SUPERVISOR":
        _require_area_manage(t["area"])

    # Asignación simple (menor backlog del área)
    assignee = pick_assignee(t["org_id"], t["area"])

    # Approval metadata
    approved_val = True if using_pg() else 1
    now_iso = (
        datetime.now(timezone.utc).isoformat()
        if using_pg()
        else datetime.now().isoformat()
    )

    fields: Dict[str, Any] = {
        "estado": "ASIGNADO",
        "approved": approved_val,
        "approved_by": user["id"],
        "approved_at": now_iso,
    }
    if assignee:
        fields["assigned_to"] = assignee

    _update_ticket(id, fields, "CONFIRMADO")

    # Notificar técnico por WhatsApp si hay teléfono
    if assignee:
        tech = fetchone("SELECT telefono FROM Users WHERE id=?", (assignee,))
        to_phone = (tech.get("telefono") if tech else None) or ""
        if to_phone.strip():
            try:
                _notify_tech_assignment(
                    to_phone=to_phone,
                    ticket_id=id,
                    area=t["area"],
                    prioridad=t["prioridad"],
                    detalle=t["detalle"],
                    ubicacion=t["ubicacion"],
                )
            except Exception as e:
                print(f"[WA] notify tech assignment failed: {e}", flush=True)

    msg = (
        "Ticket confirmado y asignado."
        if assignee
        else "Ticket confirmado (sin asignar)."
    )
    flash(msg, "success")
    return redirect(url_for("tickets"))

@bp.post("/tickets/<int:id>/reassign")
@require_perm("tickets:change_state")  # o un permiso más fino si quieres, p.ej. "tickets:reassign"
def ticket_reassign(id: int):
    """
    Reasignar ticket a otro técnico desde el dashboard de supervisor/gerente.
    Solo toca assigned_to y registra el movimiento en TicketHistory.
    """
    if "user" not in session:
        return _err_or_redirect("No autenticado.", 401)

    t = _get_ticket_or_abort(id)
    if t is None:
        return _err_or_redirect("Ticket no encontrado.", 404)

    role = current_org_role()
    # Supervisor solo puede gestionar su área
    if role == "SUPERVISOR":
        _require_area_manage(t["area"])

    assigned_raw = (request.form.get("assigned_to") or "").strip()
    if not assigned_raw.isdigit():
        return _err_or_redirect("Técnico inválido.", 400)

    new_assignee = int(assigned_raw)

    # Actualiza assigned_to y registra REASIGNADO
    _update_ticket(
        id,
        {"assigned_to": new_assignee},
        "REASIGNADO",
    )

    # (Opcional) Notificar por WhatsApp al nuevo técnico igual que en confirm()
    try:
        tech = fetchone("SELECT telefono FROM Users WHERE id=?", (new_assignee,))
        to_phone = (tech.get("telefono") if tech else None) or ""
        if to_phone.strip():
            _notify_tech_assignment(
                to_phone=to_phone,
                ticket_id=id,
                area=t["area"],
                prioridad=t["prioridad"],
                detalle=t["detalle"],
                ubicacion=t["ubicacion"],
            )
    except Exception as e:
        print(f"[WA] notify tech reassignment failed: {e}", flush=True)

    # Devuelve JSON si es XHR/HX, o redirige con flash si viene de un <form>
    return _ok_or_redirect("Ticket reasignado.", ticket_id=id)



# --------------------------------------------------------------------
# Asignación automática MVP
# --------------------------------------------------------------------

def pick_assignee(org_id: int, area: str) -> int | None:
    """
    MVP assignment:
    - Busca técnicos del área en la org (via OrgUsers.role='TECNICO' + OrgUserAreas)
    - Elige el de menor backlog abierto
    """
    try:
        techs = fetchall(
            """
            SELECT u.id
            FROM Users u
            JOIN OrgUsers ou ON ou.user_id = u.id AND ou.org_id = ?
            LEFT JOIN OrgUserAreas oa
                ON oa.org_id = ou.org_id AND oa.user_id = ou.user_id
            WHERE ou.role = 'TECNICO' AND (oa.area_code = ? OR u.area = ?)
            """,
            (org_id, area, area),
        )
        if not techs:
            return None

        best = None
        best_count = 10**9
        for r in techs:
            c = fetchone(
                """
                SELECT COUNT(1) AS c
                FROM Tickets
                WHERE org_id=? AND assigned_to=? AND estado IN
                    ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')
                """,
                (org_id, r["id"]),
            )["c"]
            if c < best_count:
                best = r["id"]
                best_count = c
        return best
    except Exception:
        return None


# --------------------------------------------------------------------
# Logical state guards
# --------------------------------------------------------------------

ALLOWED_TRANSITIONS = {
    "accept": {"PENDIENTE", "ASIGNADO", "DERIVADO"},
    "start": {"ACEPTADO"},  # must have been explicitly accepted
    "pause": {"EN_CURSO"},
    "resume": {"PAUSADO"},
    "finish": {"EN_CURSO"},
}


def _guard_transition(t, allowed: set, verb_es: str):
    """
    If current ticket state is not allowed for this transition, return an error/redirect.
    Use 409 (conflict) to signal invalid state flow to the UI.
    """
    estado = (t.get("estado") or "").upper()
    if estado not in allowed:
        return _err_or_redirect(
            f"No puedes {verb_es} un ticket en estado {nice_state(estado)}.",
            code=409,
        )
    return None


# --------------------------------------------------------------------
# Update helper
# --------------------------------------------------------------------

def _update_ticket(id: int, fields: Dict[str, Any], action: str, motivo: str | None = None):
    """
    Small helper: update Tickets with `fields` and write a line in TicketHistory.
    Works on both SQLite and Postgres.
    """
    now = (
        datetime.now(timezone.utc).isoformat()
        if using_pg()
        else datetime.now().isoformat()
    )

    if using_pg():
        sets = ", ".join([f"{k}=%s" for k in fields.keys()])
        params = list(fields.values()) + [id]
        execute(f"UPDATE tickets SET {sets} WHERE id=%s", params)
        execute(
            """
            INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at)
            VALUES (%s,%s,%s,%s,%s)
            """,
            (id, session["user"]["id"], action, motivo, now),
        )
    else:
        sets = ", ".join([f"{k}=?" for k in fields.keys()])
        params = list(fields.values()) + [id]
        execute(f"UPDATE Tickets SET {sets} WHERE id=?", params)
        execute(
            """
            INSERT INTO TicketHistory(ticket_id, actor_user_id, action, motivo, at)
            VALUES (?,?,?,?,?)
            """,
            (id, session["user"]["id"], action, motivo, now),
        )


def _get_ticket_or_abort(id: int):
    t = fetchone("SELECT * FROM Tickets WHERE id=?", (id,))
    if not t:
        flash("Ticket no encontrado.", "error")
        return None
    org_id, _ = current_scope()
    if not org_id or t["org_id"] != org_id:
        flash("Fuera de tu organización.", "error")
        return None
    return t


# --------------------------------------------------------------------
# Transitions: accept / start / pause / resume / finish
# --------------------------------------------------------------------

@bp.post("/tickets/<int:id>/accept")
@require_perm("tickets:change_state")
def ticket_accept(id: int):
    if "user" not in session:
        return _err_or_redirect("No autenticado.", 401)

    t = _get_ticket_or_abort(id)
    if t is None:
        return _err_or_redirect("Ticket no encontrado.", 404)

    bad_shift = _guard_active_shift(t.get("area"))
    if bad_shift:
        return bad_shift

    # Enforce logical flow
    bad = _guard_transition(t, ALLOWED_TRANSITIONS["accept"], "aceptar")
    if bad:
        return bad

    role = current_org_role()

    # Técnico: solo si es el asignado (o se autoasigna si no hay asignado)
    if (
        role == "TECNICO"
        and t["assigned_to"]
        and t["assigned_to"] != session["user"]["id"]
    ):
        return _err_or_redirect("Solo puedes aceptar tus tickets.", 403)

    # Supervisor: solo su área
    if role == "SUPERVISOR":
        _require_area_manage(t["area"])

    _update_ticket(
        id,
        {
            "estado": "ACEPTADO",
            "accepted_at": datetime.now().isoformat(),
            "assigned_to": t["assigned_to"] or session["user"]["id"],
        },
        "ACEPTADO",
    )
    return _ok_or_redirect("Ticket aceptado.", ticket_id=id, new_estado="ACEPTADO")


@bp.post("/tickets/<int:id>/start")
@require_perm("tickets:change_state")
def ticket_start(id: int):
    if "user" not in session:
        return _err_or_redirect("No autenticado.", 401)

    t = _get_ticket_or_abort(id)
    if t is None:
        return _err_or_redirect("Ticket no encontrado.", 404)

    bad_shift = _guard_active_shift(t.get("area"))
    if bad_shift:
        return bad_shift

    bad = _guard_transition(t, ALLOWED_TRANSITIONS["start"], "iniciar")
    if bad:
        return bad

    role = current_org_role()
    if role == "TECNICO" and t["assigned_to"] != session["user"]["id"]:
        return _err_or_redirect("Solo puedes iniciar tus tickets.", 403)
    if role == "SUPERVISOR":
        _require_area_manage(t["area"])

    _update_ticket(
        id,
        {"estado": "EN_CURSO", "started_at": datetime.now().isoformat()},
        "INICIADO",
    )
    return _ok_or_redirect("Ticket iniciado.", ticket_id=id, new_estado="EN_CURSO")


@bp.post("/tickets/<int:id>/pause")
@require_perm("tickets:change_state")
def ticket_pause(id: int):
    if "user" not in session:
        return _err_or_redirect("No autenticado.", 401)

    t = _get_ticket_or_abort(id)
    if t is None:
        return _err_or_redirect("Ticket no encontrado.", 404)

    bad_shift = _guard_active_shift(t.get("area"))
    if bad_shift:
        return bad_shift

    bad = _guard_transition(t, ALLOWED_TRANSITIONS["pause"], "pausar")
    if bad:
        return bad

    role = current_org_role()
    if role == "TECNICO" and t["assigned_to"] != session["user"]["id"]:
        return _err_or_redirect("Solo puedes pausar tus tickets.", 403)
    if role == "SUPERVISOR":
        _require_area_manage(t["area"])

    motivo = (request.form.get("motivo") or "").strip()
    _update_ticket(id, {"estado": "PAUSADO"}, "PAUSADO", motivo)
    return _ok_or_redirect("Ticket en pausa.", ticket_id=id, new_estado="PAUSADO")


@bp.post("/tickets/<int:id>/resume")
@require_perm("tickets:change_state")
def ticket_resume(id: int):
    if "user" not in session:
        return _err_or_redirect("No autenticado.", 401)

    t = _get_ticket_or_abort(id)
    if t is None:
        return _err_or_redirect("Ticket no encontrado.", 404)

    bad_shift = _guard_active_shift(t.get("area"))
    if bad_shift:
        return bad_shift

    bad = _guard_transition(t, ALLOWED_TRANSITIONS["resume"], "reanudar")
    if bad:
        return bad

    role = current_org_role()
    if role == "TECNICO" and t["assigned_to"] != session["user"]["id"]:
        return _err_or_redirect("Solo puedes reanudar tus tickets.", 403)
    if role == "SUPERVISOR":
        _require_area_manage(t["area"])

    _update_ticket(id, {"estado": "EN_CURSO"}, "REANUDADO")
    return _ok_or_redirect("Ticket reanudado.", ticket_id=id, new_estado="EN_CURSO")


@bp.post("/tickets/<int:id>/finish")
@require_perm("tickets:change_state")
def ticket_finish(id: int):
    if "user" not in session:
        return _err_or_redirect("No autenticado.", 401)

    t = _get_ticket_or_abort(id)
    if t is None:
        return _err_or_redirect("Ticket no encontrado.", 404)

    bad_shift = _guard_active_shift(t.get("area"))
    if bad_shift:
        return bad_shift

    role = current_org_role()

    if role == "TECNICO" and t["assigned_to"] != session["user"]["id"]:
        return _err_or_redirect("Solo puedes finalizar tus tickets.", 403)

    if role == "SUPERVISOR":
        _require_area_manage(t["area"])

    _update_ticket(
        id,
        {"estado": "RESUELTO", "finished_at": datetime.now().isoformat()},
        "RESUELTO",
    )

    # Avisar al huésped por WhatsApp si tenemos algo en huesped_id.
    # En el nuevo esquema solo tenemos huesped_id; lo usamos como identificador / teléfono.
    try:
        t2 = fetchone(
            """
            SELECT huesped_id
            FROM Tickets
            WHERE id=?
            """,
            (id,),
        )
        to_phone = (t2["huesped_id"] if t2 and t2.get("huesped_id") else "") or ""
        if to_phone.strip():
            _notify_guest_final(
                to_phone=to_phone,
                ticket_id=id,
                huesped_nombre=None,  # nombre no está en el schema actual
            )
    except Exception as e:
        print(f"[WA] notify guest final failed: {e}", flush=True)

    return _ok_or_redirect("Ticket resuelto.", ticket_id=id, new_estado="RESUELTO")

@bp.post("/tickets/<int:id>/delete")
@require_perm("tickets:delete")  # nuevo permiso específico para baja lógica
def ticket_delete(id: int):
    """
    Baja lógica (soft delete) de un ticket.
    - Marca estado = 'ELIMINADO'
    - Marca deleted_at con timestamp actual
    - Registra motivo en TicketHistory.motivo
    """
    if "user" not in session:
        return _err_or_redirect("No autenticado.", 401)

    t = _get_ticket_or_abort(id)
    if t is None:
        return _err_or_redirect("Ticket no encontrado.", 404)

    motivo = (request.form.get("motivo") or "").strip() or None

    deleted_now = (
        datetime.now(timezone.utc).isoformat()
        if using_pg()
        else datetime.now().isoformat()
    )

    fields: Dict[str, Any] = {
        "estado": "ELIMINADO",
        "deleted_at": deleted_now,
    }

    _update_ticket(id, fields, "ELIMINADO", motivo)

    # Desde el dashboard de recepción se llama vía fetch() y solo se mira r.ok
    return jsonify({"ok": True})
