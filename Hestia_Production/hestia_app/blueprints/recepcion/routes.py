from __future__ import annotations
from ...core.scope import current_scope

from datetime import datetime, timedelta
from flask import (
    render_template, jsonify, request, redirect, url_for,
    session, flash, g
)

from . import bp

# --- DB helpers ---
try:
    from ...services.db import fetchall, fetchone
except Exception:
    # Fallback import if relative pathing differs at runtime
    from hestia_app.services.db import fetchall, fetchone  # type: ignore

# --- Optional SLA helper (only used via _safe_is_critical) ---
try:
    from ...services.sla import is_critical  # type: ignore
except Exception:
    is_critical = None  # type: ignore


# --- Permission decorator (no-op fallback if not available) ---
try:
    from ...core.authz import require_perm  # type: ignore
except Exception:
    try:
        from ..auth.routes import require_perm  # type: ignore
    except Exception:
        def require_perm(_perm: str):
            def _decorator(fn):
                return fn
            return _decorator

# --- Template chooser helper (fallback picks first) ---
try:
    from ...utils.rendering import render_best  # type: ignore
except Exception:
    def render_best(candidates: list[str], **ctx):
        return render_template(candidates[0], **ctx)


# ---------------------------- Recepción inbox (triage) ----------------------------
@bp.route('/recepcion/inbox')
@require_perm('ticket.view.area')
def recepcion_inbox():
    org_id, _ = current_scope()
    if not org_id:
        flash('Sin contexto de organización.', 'error')
        return redirect(url_for('dashboard.index'))

    # Inbox: pendientes (típicamente WA huésped o recepcion)
    rows = fetchall("""
        SELECT id, area, prioridad, estado, detalle, ubicacion, canal_origen, created_at
        FROM Tickets
        WHERE org_id=? AND estado IN ('PENDIENTE_APROBACION','PENDIENTE')
        ORDER BY created_at DESC
    """, (org_id,))

    view = g.view_mode
    return render_best(
        [f"tickets_{view}.html", "tickets.html"],
        user=session['user'],
        tickets=[{
            "id": r["id"], "area": r["area"], "prioridad": r["prioridad"], "estado": r["estado"],
            "detalle": r["detalle"], "ubicacion": r["ubicacion"],
            "created_at": r["created_at"], "due_at": None, "is_critical": False,
            "assigned_to": None, "canal": r["canal_origen"]
        } for r in rows],
        filters={"q":"", "area":"", "prioridad":"", "estado":"PENDIENTE", "period":"today"},
        device=g.device, view=view
    )


# ---------- Recepción: helpers ----------
def _safe_is_critical(now, due_at):
    # Uses your is_critical() if present; else simple fallback
    try:
        if is_critical is not None:
            return is_critical(now, due_at)  # type: ignore
    except Exception:
        pass

    if not due_at:
        return False
    try:
        dt = datetime.fromisoformat(str(due_at))
    except Exception:
        return False
    return dt <= now


def _period_bounds(period: str):
    now = datetime.now()
    sod = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == 'today':
        return (sod.isoformat(), None)
    if period == 'yesterday':
        y0 = (sod - timedelta(days=1)).isoformat()
        return (y0, sod.isoformat())
    if period == '7d':
        return ((sod - timedelta(days=7)).isoformat(), None)
    if period == '30d':
        return ((sod - timedelta(days=30)).isoformat(), None)
    return (None, None)


# ---------- Recepción: page ----------
@bp.route('/recepcion/dashboard', endpoint='recepcion_dashboard')
@require_perm('ticket.view.area')
def recepcion_dashboard():
    # Bare page; data is fetched via JS
    return render_template('dashboard_recepcion.html', user=session.get('user'), device=g.device, view=g.view_mode)


# ---------- Recepción: KPIs ----------
@bp.get('/api/recepcion/kpis')
@require_perm('ticket.view.area')
def api_recepcion_kpis():
    org_id, _ = current_scope()
    if not org_id:
        return jsonify({"error": "no org"}), 400

    now = datetime.now()
    sod = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    c1 = fetchall("SELECT COUNT(*) c FROM Tickets WHERE org_id=? AND estado IN ('PENDIENTE_APROBACION','PENDIENTE')", (org_id,))
    c2 = fetchall("SELECT COUNT(*) c FROM Tickets WHERE org_id=? AND estado='EN_CURSO'", (org_id,))
    c3 = fetchall("SELECT COUNT(*) c FROM Tickets WHERE org_id=? AND estado='RESUELTO' AND (finished_at>=?)", (org_id, sod))
    rows_due = fetchall("""
        SELECT due_at FROM Tickets
        WHERE org_id=? AND estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO') AND due_at IS NOT NULL
    """, (org_id,))
    critical = sum(1 for r in rows_due if _safe_is_critical(now, r.get('due_at')))

    return jsonify({
        "pending": (c1[0]["c"] if c1 else 0),
        "in_progress": (c2[0]["c"] if c2 else 0),
        "resolved_today": (c3[0]["c"] if c3 else 0),
        "critical": critical,
        "at": now.isoformat()
    })


# ---------- Recepción: list ----------
@bp.get('/api/recepcion/list')
@require_perm('ticket.view.area')
def api_recepcion_list():
    org_id, _ = current_scope()
    if not org_id:
        return jsonify({"items": []})

    estado = (request.args.get('estado') or '').upper()      # PENDIENTE|EN_CURSO|RESUELTO
    period = request.args.get('period', 'today')             # today|yesterday|7d|30d|all
    limit  = int(request.args.get('limit', '50'))

    where, params = ["org_id=?"], [org_id]
    if estado == 'PENDIENTE':
        where.append("estado IN ('PENDIENTE_APROBACION','PENDIENTE')")
    elif estado:
        where.append("estado=?"); params.append(estado)

    start, end = _period_bounds(period)
    if start and end:
        where.append("created_at>=? AND created_at<?"); params += [start, end]
    elif start:
        where.append("created_at>=?"); params.append(start)

    rows = fetchall(f"""
        SELECT id, area, prioridad, estado, detalle, ubicacion, created_at, due_at, finished_at, canal_origen
        FROM Tickets
        WHERE {' AND '.join(where)}
        ORDER BY created_at DESC
        LIMIT {limit}
    """, tuple(params))

    now = datetime.now()
    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "area": r["area"],
            "prioridad": r["prioridad"],
            "estado": r["estado"],
            "detalle": r["detalle"],
            "ubicacion": r["ubicacion"],
            "created_at": r["created_at"],
            "due_at": r["due_at"],
            "finished_at": r.get("finished_at"),
            "canal": r.get("canal_origen"),
            "is_critical": _safe_is_critical(now, r.get("due_at")),
        })
    return jsonify({"items": items, "count": len(items)})


# ---------- Feed (últimas acciones) ----------
@bp.get('/api/feed/recent')
@require_perm('ticket.view.area')
def api_feed_recent():
    org_id, _ = current_scope()
    if not org_id:
        return jsonify({"items": []})

    rows = fetchall("""
        SELECT
            th.ticket_id,
            th.action,
            th.motivo,
            th.at,
            t.area,
            t.ubicacion,
            COALESCE(
              u.username,
              u.email,
              'user#' || CAST(th.actor_user_id AS TEXT),
              'sistema'
            ) AS actor
        FROM tickethistory th
        LEFT JOIN tickets t ON t.id = th.ticket_id
        LEFT JOIN users   u ON u.id = th.actor_user_id
        WHERE t.org_id = ?
        ORDER BY th.at DESC
        LIMIT 12
    """, (org_id,))

    items = [{
        "ticket_id": r["ticket_id"],
        "action": r["action"],
        "motivo": r.get("motivo"),
        "at": r["at"],
        "area": r.get("area"),
        "ubicacion": r.get("ubicacion"),
        "actor": r.get("actor") or "sistema",
    } for r in rows]

    return jsonify({"items": items})
