# app/routes.py
from __future__ import annotations
import re
from flask import render_template, request, redirect, url_for, flash, session, jsonify, current_app, g
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from ...core.area import require_perm
from ...core.scope import current_scope
from ...services.db import execute, insert_and_get_id, fetchone, fetchall, using_pg
from ...services.sla import compute_due
from ...core.rbac import current_org_role, _require_area_manage
from ...services.notify import _notify_tech_assignment, _notify_guest_final
from ...core.errors import _err_or_redirect, _ok_or_redirect
from ...core.status import nice_state
from ...blueprints.tecnico.routes import _guard_active_shift
#from ...blueprints.tickets.routes import _period_bounds, _safe_is_critical

from flask import (
    request, session, jsonify, render_template,
    redirect, url_for, abort
)
from werkzeug.utils import secure_filename

from . import bp

# If i change this in teh futuer will need to udpate here
# Helpers
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
        # helpers.py is under hestia_app.blueprints.tickets.helpers
        # three dots = go up to hestia_app, then .services.sla
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


# ----------------- Reutiliza tus estados -----------------
try:
    from hestia_app.core.status import OPEN_STATES
except Exception:
    OPEN_STATES = ("PENDIENTE","ASIGNADO","ACEPTADO","EN_CURSO","PAUSADO","DERIVADO")

# ---------- Editar ticket (Recepción/Supervisor/Gerente) ----------
@bp.post('/tickets/<int:ticket_id>/edit')
@require_perm('ticket.update')  # or a custom check for roles RECEPCION/SUPERVISOR/GERENTE
def ticket_edit(ticket_id):
    user = session.get('user') or {}
    org_id, _ = current_scope()
    if not org_id:
        return jsonify({"ok": False, "error": "Sin contexto de organización"}), 400

    detalle   = (request.form.get('detalle') or '').strip()
    prioridad = (request.form.get('prioridad') or '').strip().upper() or None
    ubicacion = (request.form.get('ubicacion') or '').strip() or None

    # sanitize prioridad
    valid_prios = {'URGENTE','ALTA','MEDIA','BAJA'}
    if prioridad and prioridad not in valid_prios:
        return jsonify({"ok": False, "error": "Prioridad inválida"}), 400

    # update
    execute(
        ("UPDATE Tickets SET detalle=%s, prioridad=%s, ubicacion=%s WHERE id=%s AND org_id=%s")
        if using_pg() else
        ("UPDATE Tickets SET detalle=?,  prioridad=?,  ubicacion=?  WHERE id=? AND org_id=?"),
        (detalle or None, prioridad, ubicacion, ticket_id, org_id)
    )

    # history
    execute(
        ("INSERT INTO TicketHistory(ticket_id, actor_user_id, action, motivo, at) VALUES (%s,%s,%s,%s,%s)")
        if using_pg() else
        ("INSERT INTO TicketHistory(ticket_id, actor_user_id, action, motivo, at) VALUES (?,?,?,?,?)"),
        (ticket_id, user.get('id'), "EDITADO", None, datetime.now().isoformat())
    )

    return jsonify({"ok": True})


@bp.get("/tickets", endpoint="tickets")
@require_perm("ticket.view.area")
def ticket_list():
    """
    Canonical list/landing for Tickets.
    Endpoint name = 'tickets.tickets' so the navbar link in base.html works.
    Renders templates/tickets.html
    """
    org_id, _ = current_scope()
    if not org_id:
        flash("Sin contexto de organización.", "error")
        return redirect(url_for("dashboard.index"))

    # --- Filters (match your tickets.html form) ---
    q        = (request.args.get("q") or "").strip()
    area     = (request.args.get("area") or "").strip().upper()
    prioridad= (request.args.get("prioridad") or "").strip().upper()
    estado   = (request.args.get("estado") or "").strip().upper()
    period   = (request.args.get("period") or "today").strip()

    where, params = ["org_id=?"], [org_id]
    if q:
        where.append("(detalle LIKE ? OR ubicacion LIKE ?)")
        like = f"%{q}%"
        params += [like, like]
    if area:
        where.append("area=?"); params.append(area)
    if prioridad:
        where.append("prioridad=?"); params.append(prioridad)
    if estado:
        where.append("estado=?"); params.append(estado)

    start, end = _period_bounds(period)
    if start and end:
        where.append("created_at>=? AND created_at<?"); params += [start, end]
    elif start:
        where.append("created_at>=?"); params.append(start)

    rows = fetchall(f"""
        SELECT id, area, prioridad, estado, detalle, ubicacion, canal_origen,
               created_at, due_at, finished_at
        FROM Tickets
        WHERE {' AND '.join(where)}
        ORDER BY created_at DESC
        LIMIT 200
    """, tuple(params))

    now = datetime.now()
    tickets = [{
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
    } for r in rows]

    filters = {
        "q": q, "area": area, "prioridad": prioridad,
        "estado": estado, "period": period
    }

    return render_template("tickets.html",
                           user=session.get("user"),
                           tickets=tickets,
                           filters=filters,
                           device=getattr(g, "device", None),
                           view=getattr(g, "view_mode", "auto"))

# ---------------------------- create & confirm ticket ----------------------------
@bp.route('/tickets/create', methods=['GET', 'POST'])
@require_perm('ticket.create')
def ticket_create():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        org_id, hotel_id = current_scope()
        if not org_id or not hotel_id:
            flash('Falta contexto de organización/hotel.', 'error')
            # intenta volver al referer si existe
            nxt = request.args.get('next') or request.form.get('next') or request.referrer
            return redirect(nxt or url_for('tickets'))

        area = request.form.get('area')
        prioridad = request.form.get('prioridad')
        detalle = request.form.get('detalle')
        ubicacion = request.form.get('ubicacion')
        canal = request.form.get('canal_origen') or 'recepcion'
        huesped_id = request.form.get('huesped_id') or None
        qr_required = int(request.form.get('qr_required', 0))

        created_at = datetime.now()
        due_dt = compute_due(created_at, area, prioridad)
        due_at = due_dt.isoformat() if due_dt else None

        try:
            new_id = insert_and_get_id("""
                INSERT INTO Tickets(org_id, hotel_id, area, prioridad, estado, detalle, canal_origen, ubicacion,
                                    huesped_id, created_at, due_at, assigned_to, created_by,
                                    confidence_score, qr_required)
                VALUES (?, ?, ?, ?, 'PENDIENTE', ?, ?, ?, ?, ?, NULL, ?, NULL, ?)
            """, (org_id, hotel_id, area, prioridad, detalle, canal, ubicacion, huesped_id,
                  created_at.isoformat(), due_at, session['user']['id'], qr_required))

            execute("""
                INSERT INTO TicketHistory(ticket_id, actor_user_id, action, motivo, at)
                VALUES (?, ?, 'CREADO', NULL, ?)
            """, (new_id, session['user']['id'], created_at.isoformat()))

            flash(f'Ticket #{new_id} creado.', 'success')

            # 👇 redirige de vuelta a la pantalla que originó la creación
            nxt = request.args.get('next') or request.form.get('next') or request.referrer
            # seguridad mínima: solo permite rutas locales (evitar open redirect)
            if nxt and str(nxt).startswith('/'):
                return redirect(nxt)
            return redirect(url_for('tickets'))

        except Exception as e:
            current_app.logger.exception("Error creando ticket")
            flash(f'Error creando ticket: {e}', 'error')
            nxt = request.args.get('next') or request.form.get('next') or request.referrer
            return redirect(nxt or url_for('tickets'))

    # GET (igual que ya tenías)
    areas = ['MANTENCION','HOUSEKEEPING','ROOMSERVICE']
    prioridades = ['BAJA','MEDIA','ALTA','URGENTE']
    canales = ['recepcion','huesped_whatsapp','housekeeping_whatsapp','mantenimiento_app','roomservice_llamada']
    return render_template('ticket_create.html', user=session['user'],
                           areas=areas, prioridades=prioridades, canales=canales)

@bp.post('/tickets/<int:id>/confirm')
@require_perm('ticket.confirm')
def ticket_confirm(id):
    """Recepción/Supervisor/Gerente confirman o aprueban (incluye PENDIENTE_APROBACION), auto-asignan y notifican por WA."""
    if 'user' not in session: 
        return redirect(url_for('login'))

    t = fetchone("""
        SELECT id, org_id, area, prioridad, estado, detalle, ubicacion, assigned_to
        FROM Tickets WHERE id=?
    """, (id,))
    if not t:
        flash('Ticket no encontrado.', 'error')
        return redirect(url_for('tickets'))

    if t['estado'] not in ('PENDIENTE_APROBACION', 'PENDIENTE'):
        flash('Solo puedes confirmar/aprobar tickets pendientes.', 'error')
        return redirect(url_for('tickets'))

    # SUPERVISOR: solo su área
    if current_org_role() == 'SUPERVISOR':
        _require_area_manage(t['area'])

    # Asignación simple (menor backlog del área)
    assignee = pick_assignee(t['org_id'], t['area'])
    fields = {"estado": "ASIGNADO"}
    if assignee:
        fields["assigned_to"] = assignee

    _update_ticket(id, fields, "CONFIRMADO")

    # Notificar técnico por WhatsApp si hay teléfono
    if assignee:
        tech = fetchone("SELECT telefono FROM Users WHERE id=?", (assignee,))
        to_phone = (tech.get('telefono') if tech else None) or ""
        if to_phone.strip():
            try:
                _notify_tech_assignment(
                    to_phone=to_phone,
                    ticket_id=id,
                    area=t['area'],
                    prioridad=t['prioridad'],
                    detalle=t['detalle'],
                    ubicacion=t['ubicacion']
                )
            except Exception as e:
                print(f"[WA] notify tech assignment failed: {e}", flush=True)

    flash('Ticket confirmado y asignado.' if assignee else 'Ticket confirmado (sin asignar).', 'success')
    return redirect(url_for('tickets'))

def pick_assignee(org_id: int, area: str) -> int | None:
    """
    MVP assignment:
    - Busca técnicos del área en la org (via OrgUsers.role='TECNICO' + OrgUserAreas)
    - Elige el de menor backlog abierto
    """
    try:
        techs = fetchall("""
            SELECT u.id
            FROM Users u
            JOIN OrgUsers ou ON ou.user_id=u.id AND ou.org_id=?
            LEFT JOIN OrgUserAreas oa ON oa.org_id=ou.org_id AND oa.user_id=ou.user_id
            WHERE ou.role='TECNICO' AND (oa.area_code=? OR u.area=?)
        """, (org_id, area, area))
        if not techs:
            return None
        # pick least loaded
        best = None
        best_count = 1e9
        for r in techs:
            c = fetchone("""
                SELECT COUNT(1) c FROM Tickets
                 WHERE org_id=? AND assigned_to=? AND estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')
            """, (org_id, r['id']))['c']
            if c < best_count:
                best = r['id']; best_count = c
        return best
    except Exception:
        return None
    
# --- Logical state guards for transitions (backend truth) ---
ALLOWED_TRANSITIONS = {
    "accept": {"PENDIENTE", "ASIGNADO", "DERIVADO"},
    "start":  {"ACEPTADO"},          # must have been explicitly started
    "pause":  {"EN_CURSO"},
    "resume": {"PAUSADO"},
    "finish": {"EN_CURSO"},
}

def _guard_transition(t, allowed: set, verb_es: str):
    """
    If current ticket state is not allowed for this transition, return an error/redirect.
    Use 409 (conflict) to signal invalid state flow to the UI.
    """
    estado = (t.get('estado') or '').upper()
    if estado not in allowed:
        return _err_or_redirect(
            f"No puedes {verb_es} un ticket en estado {nice_state(estado)}.",
            code=409
        )
    return None


# ---------------------------- transitions ----------------------------
def _update_ticket(id, fields: dict, action: str, motivo: str | None = None):
    sets = ", ".join([f"{k}=?" for k in fields.keys()])
    params = list(fields.values()) + [id]
    execute(f"UPDATE Tickets SET {sets} WHERE id=?", params)
    execute("""INSERT INTO TicketHistory(ticket_id, actor_user_id, action, motivo, at)
               VALUES (?,?,?,?,?)""",
            (id, session['user']['id'], action, motivo, datetime.now().isoformat()))

def _get_ticket_or_abort(id: int):
    t = fetchone("SELECT * FROM Tickets WHERE id=?", (id,))
    if not t:
        flash('Ticket no encontrado.', 'error')
        return None
    # org scope
    org_id, _ = current_scope()
    if not org_id or t['org_id'] != org_id:
        flash('Fuera de tu organización.', 'error')
        return None
    return t

@bp.post('/tickets/<int:id>/accept')
@require_perm('ticket.transition.accept')
def ticket_accept(id):
    if 'user' not in session:
        return _err_or_redirect('No autenticado.', 401)

    t = _get_ticket_or_abort(id)
    if t is None:
        return _err_or_redirect('Ticket no encontrado.', 404)
    
    bad_shift = _guard_active_shift(t.get('area'))
    if bad_shift: 
        return bad_shift

    # Enforce logical flow
    bad = _guard_transition(t, ALLOWED_TRANSITIONS["accept"], "aceptar")
    if bad: return bad

    role = current_org_role()

    # Técnico: solo si es el asignado (o se autoasigna si no hay asignado)
    if role == 'TECNICO' and t['assigned_to'] and t['assigned_to'] != session['user']['id']:
        return _err_or_redirect('Solo puedes aceptar tus tickets.', 403)

    # Supervisor: solo su área
    if role == 'SUPERVISOR':
        _require_area_manage(t['area'])

    _update_ticket(
        id,
        {
            "estado": "ACEPTADO",
            "accepted_at": datetime.now().isoformat(),
            "assigned_to": t['assigned_to'] or session['user']['id']
        },
        "ACEPTADO"
    )
    return _ok_or_redirect('Ticket aceptado.', ticket_id=id, new_estado='ACEPTADO')



@bp.post('/tickets/<int:id>/start')
@require_perm('ticket.transition.start')
def ticket_start(id):
    if 'user' not in session:
        return _err_or_redirect('No autenticado.', 401)

    t = _get_ticket_or_abort(id)
    if t is None:
        return _err_or_redirect('Ticket no encontrado.', 404)
    
    bad_shift = _guard_active_shift(t.get('area'))
    if bad_shift: 
        return bad_shift

    # Must be ACEPTADO (do not allow from PAUSADO; use /resume)
    bad = _guard_transition(t, ALLOWED_TRANSITIONS["start"], "iniciar")
    if bad: return bad

    role = current_org_role()
    if role == 'TECNICO' and t['assigned_to'] != session['user']['id']:
        return _err_or_redirect('Solo puedes iniciar tus tickets.', 403)
    if role == 'SUPERVISOR':
        _require_area_manage(t['area'])

    _update_ticket(
        id,
        {"estado": "EN_CURSO", "started_at": datetime.now().isoformat()},
        "INICIADO"
    )
    return _ok_or_redirect('Ticket iniciado.', ticket_id=id, new_estado='EN_CURSO')



@bp.post('/tickets/<int:id>/pause')
@require_perm('ticket.transition.pause')
def ticket_pause(id):
    if 'user' not in session:
        return _err_or_redirect('No autenticado.', 401)

    t = _get_ticket_or_abort(id)
    if t is None:
        return _err_or_redirect('Ticket no encontrado.', 404)
    
    bad_shift = _guard_active_shift(t.get('area'))
    if bad_shift: 
        return bad_shift

    # Only from EN_CURSO
    bad = _guard_transition(t, ALLOWED_TRANSITIONS["pause"], "pausar")
    if bad: return bad

    role = current_org_role()
    if role == 'TECNICO' and t['assigned_to'] != session['user']['id']:
        return _err_or_redirect('Solo puedes pausar tus tickets.', 403)
    if role == 'SUPERVISOR':
        _require_area_manage(t['area'])

    motivo = (request.form.get('motivo') or '').strip()
    _update_ticket(id, {"estado": "PAUSADO"}, "PAUSADO", motivo)
    return _ok_or_redirect('Ticket en pausa.', ticket_id=id, new_estado='PAUSADO')



@bp.post('/tickets/<int:id>/resume')
@require_perm('ticket.transition.resume')
def ticket_resume(id):
    if 'user' not in session:
        return _err_or_redirect('No autenticado.', 401)

    t = _get_ticket_or_abort(id)
    if t is None:
        return _err_or_redirect('Ticket no encontrado.', 404)
    
    bad_shift = _guard_active_shift(t.get('area'))
    if bad_shift: 
        return bad_shift

    # Only from PAUSADO
    bad = _guard_transition(t, ALLOWED_TRANSITIONS["resume"], "reanudar")
    if bad: return bad

    role = current_org_role()
    if role == 'TECNICO' and t['assigned_to'] != session['user']['id']:
        return _err_or_redirect('Solo puedes reanudar tus tickets.', 403)
    if role == 'SUPERVISOR':
        _require_area_manage(t['area'])

    _update_ticket(id, {"estado": "EN_CURSO"}, "REANUDADO")
    return _ok_or_redirect('Ticket reanudado.', ticket_id=id, new_estado='EN_CURSO')



@bp.post('/tickets/<int:id>/finish')
@require_perm('ticket.transition.finish')
def ticket_finish(id):
    if 'user' not in session:
        return _err_or_redirect('No autenticado.', 401)

    t = _get_ticket_or_abort(id)
    if t is None:
        return _err_or_redirect('Ticket no encontrado.', 404)
    
    bad_shift = _guard_active_shift(t.get('area'))
    if bad_shift: 
        return bad_shift

    role = current_org_role()

    if role == 'TECNICO' and t['assigned_to'] != session['user']['id']:
        return _err_or_redirect('Solo puedes finalizar tus tickets.', 403)

    if role == 'SUPERVISOR':
        _require_area_manage(t['area'])

    _update_ticket(
        id,
        {"estado": "RESUELTO", "finished_at": datetime.now().isoformat()},
        "RESUELTO"
    )

    # Avisar al huésped por WhatsApp si tenemos su número
    try:
        t2 = fetchone("""
            SELECT COALESCE(huesped_phone, huesped_id) AS to_phone,
                   COALESCE(huesped_nombre, '') AS guest_name
            FROM Tickets WHERE id=?
        """, (id,))
        to_phone = (t2.get('to_phone') if t2 else None) or ""
        if to_phone.strip():
            _notify_guest_final(
                to_phone=to_phone,
                ticket_id=id,
                huesped_nombre=(t2.get('guest_name') or None)
            )
    except Exception as e:
        print(f"[WA] notify guest final failed: {e}", flush=True)

    return _ok_or_redirect('Ticket resuelto.', ticket_id=id, new_estado='RESUELTO')




