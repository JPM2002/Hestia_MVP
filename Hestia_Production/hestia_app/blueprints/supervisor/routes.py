from __future__ import annotations

from datetime import datetime, timedelta
from flask import jsonify, request, session, abort
from . import bp

# DB & helpers
from ...services.db import fetchone, fetchall, USE_PG
from ...core.rbac import current_org_role
from ...core.scope import current_scope
from ...core.status import OPEN_STATES

# ---------------------------------------------------------------------
# Small shared helpers (module-level so multiple endpoints can use them)
# ---------------------------------------------------------------------
def _minutes_between(a_iso, b_iso):
    try:
        a = datetime.fromisoformat(str(a_iso))
        b = datetime.fromisoformat(str(b_iso))
        return max(0, int((b - a).total_seconds() // 60))
    except Exception:
        return None

def _must_login_json():
    return jsonify({"error": "unauthorized"}), 401

def _user_primary_area(org_id: int, user_id: int):
    row = fetchone("""
        SELECT area
        FROM OrgUserAreas
        WHERE org_id=? AND user_id=?
        ORDER BY COALESCE(is_primary, 0) DESC, area ASC
        LIMIT 1
    """, (org_id, user_id))
    if row and row.get("area"):
        return row["area"]

    if USE_PG:
        row = fetchone("""
            SELECT area
            FROM Tickets
            WHERE org_id=%s AND assigned_to=%s AND created_at >= NOW() - INTERVAL '90 days'
            GROUP BY area
            ORDER BY COUNT(1) DESC
            LIMIT 1
        """, (org_id, user_id))
    else:
        cutoff = (datetime.now() - timedelta(days=90)).isoformat()
        row = fetchone("""
            SELECT area
            FROM Tickets
            WHERE org_id=? AND assigned_to=? AND created_at >= ?
            GROUP BY area
            ORDER BY COUNT(1) DESC
            LIMIT 1
        """, (org_id, user_id, cutoff))

    return row["area"] if row else None

def _user_has_area(area: str) -> bool:
    """
    True if the current user can manage the given area.
    Managers can manage all. Supervisors must be mapped to the area.
    """
    if current_org_role() == 'GERENTE':
        return True
    if not area or area == 'None':
        return False
    org_id, _ = current_scope()
    uid = session['user']['id']
    row = fetchone("""
        FROM OrgUserAreas
        SELECT 1
        WHERE org_id=? AND user_id=? AND area=?
        LIMIT 1
    """, (org_id, uid, area))
    return bool(row)

def _require_area_manage(area: str):
    """Abort 403 if current user can't manage the area."""
    role = current_org_role()
    if role == 'GERENTE':
        return
    if role == 'SUPERVISOR' and area and _user_has_area(area):
        return
    abort(403)

# ---------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------
@bp.get('/api/supervisor/backlog_by_tech')
def api_sup_backlog_by_tech():
    user = session.get('user')
    if not user:
        return _must_login_json()
    org_id, _hotel_id = current_scope()
    where = ["t.org_id = ?", "t.estado IN (" + ",".join(["?"] * len(OPEN_STATES)) + ")"]
    params = [org_id, *OPEN_STATES]

    rows = fetchall(
        f"""
        SELECT COALESCE(u.username,'(sin asignar)') AS tech, COUNT(1) AS c
        FROM Tickets t
        LEFT JOIN Users u ON u.id = t.assigned_to
        WHERE {' AND '.join(where)}
        GROUP BY 1
        ORDER BY c DESC
        """,
        tuple(params)
    )
    return jsonify({
        "labels": [r['tech'] for r in rows],
        "values": [r['c'] for r in rows],
    })

@bp.get('/api/supervisor/open_by_priority')
def api_sup_open_by_priority():
    user = session.get('user')
    if not user:
        return _must_login_json()
    org_id, _hotel_id = current_scope()
    where = ["org_id = ?", "estado IN (" + ",".join(["?"] * len(OPEN_STATES)) + ")"]
    params = [org_id, *OPEN_STATES]

    rows = fetchall(
        f"""
        SELECT prioridad, COUNT(1) AS c
        FROM Tickets
        WHERE {' AND '.join(where)}
        GROUP BY prioridad
        ORDER BY CASE prioridad
            WHEN 'URGENTE' THEN 1
            WHEN 'ALTA'    THEN 2
            WHEN 'MEDIA'   THEN 3
            WHEN 'BAJA'    THEN 4
            ELSE 5 END
        """,
        tuple(params)
    )
    return jsonify({
        "labels": [r['prioridad'] for r in rows],
        "values": [r['c'] for r in rows],
    })

@bp.get('/api/supervisor/team_stats')
def api_supervisor_team_stats():
    """
    Team snapshot for a supervisor's area:
      - critical_open
      - open_by_priority
      - (extended) rows/ranking + prio mix for last 30d (folded from your dangling block)
    """
    if 'user' not in session:
        return jsonify({"ok": False}), 401

    org_id, _hotel_id = current_scope()
    area = request.args.get('area')
    if not area or area == 'None':
        area = _user_primary_area(org_id, session['user']['id'])

    if current_org_role() == 'SUPERVISOR' and area and not _user_has_area(area):
        return jsonify({"error": "forbidden"}), 403

    # Open tickets snapshot (priority mix + "critical" computed from due_at)
    open_rows = fetchall("""
        SELECT prioridad, due_at
        FROM Tickets
        WHERE org_id=? AND area=? AND estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')
    """, (org_id, area or ""))

    now = datetime.now()

    def _is_critical(due_at):
        if not due_at:
            return False
        try:
            return datetime.fromisoformat(str(due_at)) <= now
        except Exception:
            return False

    critical_open = sum(1 for r in open_rows if _is_critical(r.get("due_at")))
    prio_counts = {"URGENTE": 0, "ALTA": 0, "MEDIA": 0, "BAJA": 0}
    for r in open_rows:
        p = (r.get("prioridad") or "MEDIA").upper()
        prio_counts[p] = prio_counts.get(p, 0) + 1

    # -------- Extended section (30d aggregates) --------
    since_dt = datetime.now() - timedelta(days=30)
    since = since_dt.isoformat()

    # Open snapshot with assigned names
    open_rows_full = fetchall("""
        SELECT t.id, t.estado, t.prioridad, t.created_at, t.due_at,
               t.assigned_to, u.username AS assigned_name
        FROM Tickets t
        LEFT JOIN Users u ON u.id = t.assigned_to
        WHERE t.org_id=? AND t.area=? AND t.estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')
    """, (org_id, area or ""))

    # Resolved last 30d in this area
    res_rows = fetchall("""
        SELECT t.id, t.assigned_to, u.username AS assigned_name,
               t.created_at, t.finished_at, t.due_at, t.prioridad
        FROM Tickets t
        LEFT JOIN Users u ON u.id = t.assigned_to
        WHERE t.org_id=? AND t.area=? AND t.estado='RESUELTO' AND t.finished_at >= ?
    """, (org_id, area or "", since))

    # Aggregate per user
    from collections import Counter
    team = {}
    for r in open_rows_full + res_rows:
        uid = r.get('assigned_to')
        name = r.get('assigned_name') or '(sin asignar)'
        if uid is not None:
            team[uid] = name

    assigned_open = Counter()
    in_progress   = Counter()
    ttr_sum       = Counter()
    ttr_n         = Counter()
    sla_hit       = Counter()
    sla_n         = Counter()

    for r in open_rows_full:
        uid = r.get('assigned_to')
        if uid is None:
            continue
        assigned_open[uid] += 1
        if r.get('estado') == 'EN_CURSO':
            in_progress[uid] += 1

    for r in res_rows:
        uid = r.get('assigned_to')
        if uid is None:
            continue
        ttr = _minutes_between(r.get('created_at'), r.get('finished_at'))
        if ttr is not None:
            ttr_sum[uid] += ttr
            ttr_n[uid]   += 1

        if r.get('due_at'):
            sla_n[uid] += 1
            try:
                f = datetime.fromisoformat(str(r.get('finished_at')))
                d = datetime.fromisoformat(str(r.get('due_at')))
                if f <= d:
                    sla_hit[uid] += 1
            except Exception:
                pass

    rows = []
    for uid, name in sorted(team.items(), key=lambda kv: (kv[1] or '').lower()):
        avg_ttr = int(round(ttr_sum[uid]/ttr_n[uid])) if ttr_n[uid] else 0
        sla_pct = round(100.0 * (sla_hit[uid]/sla_n[uid]), 1) if sla_n[uid] else 0.0
        rows.append({
            "user_id": uid,
            "username": name,
            "assigned_open": assigned_open[uid],
            "in_progress": in_progress[uid],
            "resolved_30d": ttr_n[uid],
            "avg_ttr_min": avg_ttr,
            "sla_rate": sla_pct,
        })

    ranking = sorted(rows, key=lambda x: (-x["sla_rate"], x["avg_ttr_min"] or 10**9, -x["resolved_30d"]))

    # "Incidencias por tipo": use PRIORIDAD mix over last 30d resolved
    prio_mix = Counter()
    for r in res_rows:
        prio_mix[r.get('prioridad') or '—'] += 1
    labels_ext = ['URGENTE', 'ALTA', 'MEDIA', 'BAJA']
    values_ext = [prio_mix[l] for l in labels_ext]

    return jsonify({
        "area": area,
        "critical_open": critical_open,
        "open_by_priority": {
            "labels": list(prio_counts.keys()),
            "values": [prio_counts[k] for k in prio_counts.keys()]
        },
        # Extended (kept to preserve your added logic)
        "rows": rows,
        "ranking": ranking,
        "prio": {"labels": labels_ext, "values": values_ext},
        "since": since
    })

@bp.get('/api/sup/open_by_type')
def api_sup_open_by_type():
    """
    Open tickets grouped by 'tipo' (we'll approximate with canal_origen since you don't store 'tipo').
    Falls back to supervisor area from session if ?area is missing.
    """
    if 'user' not in session:
        return jsonify({"error": "unauthorized"}), 401

    org_id, _hotel_id = current_scope()
    if not org_id:
        return jsonify({"error": "no org"}), 400

    # Params and fallback
    area = (request.args.get('area') or '').strip()
    if not area:
        u = session.get('user') or {}
        area = (u.get('area') or u.get('team_area') or '').strip()

    # RBAC
    _require_area_manage(area)

    # Group by canal_origen as “tipo” proxy
    rows = fetchall("""
        SELECT COALESCE(t.canal_origen, 'DESCONOCIDO') AS tipo, COUNT(1) AS c
        FROM Tickets t
        WHERE t.org_id=? AND t.area=? AND t.estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')
        GROUP BY COALESCE(t.canal_origen, 'DESCONOCIDO')
        ORDER BY c DESC
    """, (org_id, area))

    labels = [r['tipo'] for r in rows]
    values = [r['c'] for r in rows]

    return jsonify({"area": area, "labels": labels, "values": values})

# ---------- Supervisor: performance by user (last N days) ----------
@bp.get('/api/sup/performance_by_user')
def api_sup_performance_by_user():
    """
    KPIs por usuario (técnico) dentro de un área, para los últimos N días.
    Devuelve: tickets totales (30d), resueltos (30d), %SLA (30d), TTR promedio (min).
    """
    if 'user' not in session:
        return jsonify({"error": "unauthorized"}), 401

    org_id, _hotel_id = current_scope()
    if not org_id:
        return jsonify({"error": "no org"}), 400

    # Parámetros
    area = (request.args.get('area') or '').strip()
    days = request.args.get('days', type=int) or 30

    # Si no llega área, intentamos inferirla del usuario (caso supervisor)
    if not area:
        u = session.get('user') or {}
        area = (u.get('area') or u.get('team_area') or '').strip()

    # RBAC: si es SUPERVISOR, sólo su(s) área(s)
    role = current_org_role()
    if role == 'SUPERVISOR':
        _require_area_manage(area)

    since_dt = datetime.now() - timedelta(days=days)
    since = since_dt.isoformat()

    # 1) Tickets creados en el periodo, por assigned_to (para "totales 30d")
    created_rows = fetchall("""
        SELECT t.assigned_to, u.username, COUNT(1) AS c
        FROM Tickets t
        LEFT JOIN Users u ON u.id = t.assigned_to
        WHERE t.org_id=? AND t.area=? AND t.created_at >= ?
        GROUP BY t.assigned_to, u.username
    """, (org_id, area, since))

    # 2) Tickets resueltos en el periodo, por assigned_to
    resolved_rows = fetchall("""
        SELECT t.assigned_to, u.username, COUNT(1) AS c
        FROM Tickets t
        LEFT JOIN Users u ON u.id = t.assigned_to
        WHERE t.org_id=? AND t.area=? AND t.estado='RESUELTO' AND t.finished_at >= ?
        GROUP BY t.assigned_to, u.username
    """, (org_id, area, since))

    # 3) SLA hits / count en resueltos (finished_at <= due_at)
    sla_rows = fetchall("""
        SELECT t.assigned_to, u.username,
               SUM(CASE WHEN t.due_at IS NOT NULL AND t.finished_at IS NOT NULL AND t.finished_at <= t.due_at THEN 1 ELSE 0 END) AS sla_hit,
               SUM(CASE WHEN t.due_at IS NOT NULL AND t.finished_at IS NOT NULL THEN 1 ELSE 0 END) AS sla_n
        FROM Tickets t
        LEFT JOIN Users u ON u.id = t.assigned_to
        WHERE t.org_id=? AND t.area=? AND t.estado='RESUELTO' AND t.finished_at >= ?
        GROUP BY t.assigned_to, u.username
    """, (org_id, area, since))

    # 4) TTR promedio de resueltos (minutos) por usuario (Python-side)
    ttr_rows = fetchall("""
        SELECT t.assigned_to, u.username, t.created_at, t.finished_at
        FROM Tickets t
        LEFT JOIN Users u ON u.id = t.assigned_to
        WHERE t.org_id=? AND t.area=? AND t.estado='RESUELTO' AND t.finished_at >= ?
    """, (org_id, area, since))

    # --- Agregación ---
    users = {}  # user_id -> metrics

    def ensure(uid, uname):
        if uid not in users:
            users[uid] = {
                "user_id": uid,
                "username": uname or "(sin asignar)",
                "total": 0,
                "resolved": 0,
                "sla_hit": 0,
                "sla_n": 0,
                "ttr_sum": 0,
                "ttr_n": 0
            }
        return users[uid]

    for r in created_rows:
        u = ensure(r["assigned_to"], r["username"])
        u["total"] += r["c"] or 0

    for r in resolved_rows:
        u = ensure(r["assigned_to"], r["username"])
        u["resolved"] += r["c"] or 0

    for r in sla_rows:
        u = ensure(r["assigned_to"], r["username"])
        u["sla_hit"] += r["sla_hit"] or 0
        u["sla_n"]   += r["sla_n"] or 0

    for r in ttr_rows:
        uid = r["assigned_to"]
        u = ensure(uid, r["username"])
        t = _minutes_between(r.get("created_at"), r.get("finished_at"))
        if t is not None:
            u["ttr_sum"] += t
            u["ttr_n"]   += 1

    # Compute rates/averages and arrays for charts
    rows_out = []
    labels, totals, resolved, sla, ttr = [], [], [], [], []

    def sort_key(item):
        return (-item[1]["resolved"], -item[1]["total"], (item[1]["username"] or ""))

    for uid, u in sorted(users.items(), key=sort_key):
        sla_rate = round(100.0 * u["sla_hit"]/u["sla_n"], 1) if u["sla_n"] > 0 else 0.0
        ttr_avg  = int(round(u["ttr_sum"]/u["ttr_n"])) if u["ttr_n"] > 0 else 0
        rows_out.append({
            "user_id": uid,
            "username": u["username"],
            "tickets_total": u["total"],
            "tickets_resueltos": u["resolved"],
            "sla_rate": sla_rate,
            "ttr_avg_min": ttr_avg
        })
        labels.append(u["username"])
        totals.append(u["total"])
        resolved.append(u["resolved"])
        sla.append(sla_rate)
        ttr.append(ttr_avg)

    return jsonify({
        "area": area,
        "period_days": days,
        "users": rows_out,
        "labels": labels,
        "totals": totals,
        "resolved": resolved,
        "sla": sla,
        "ttr": ttr
    })
