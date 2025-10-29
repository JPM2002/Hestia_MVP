from __future__ import annotations
from datetime import datetime, timedelta
import os

from flask import jsonify, request, session
from . import bp

# --- your original imports, fixed to correct packages/levels ---
from ...core.status import OPEN_STATES
from ...services.sla import is_critical
from ...services.db import fetchall, fetchone, USE_PG
from ...core.scope import current_scope

# Avoid circular blueprint imports by importing current_scope from auth via absolute import.
# (auth.routes does not import gerencia, so this is safe.)


# --- tiny helper used by your code (local, to avoid NameError) ---
def date_key(iso_str):
    """Return YYYY-MM-DD for an ISO timestamp; None if parse fails."""
    try:
        return datetime.fromisoformat(str(iso_str)).date().isoformat()
    except Exception:
        return None


def get_global_kpis():
    """KPIs para GERENTE (visión por ORG)."""
    now = datetime.now()
    org_id, _hotel_id = current_scope()
    if not org_id:
        return {"critical": 0, "active": 0, "resolved_today": 0, "by_area": {}}, {"resolved_last7": []}

    active = fetchall(
        f"SELECT id, due_at FROM Tickets WHERE org_id=? AND estado IN ({','.join(['?']*len(OPEN_STATES))})",
        (org_id, *OPEN_STATES)
    )
    total_active = len(active)
    critical = sum(1 for r in active if is_critical(now, r['due_at']))

    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    resolved_today = fetchone(
        "SELECT COUNT(1) c FROM Tickets WHERE org_id=? AND estado='RESUELTO' AND finished_at >= ?",
        (org_id, start_of_day)
    )['c']

    by_area = fetchall("""
        SELECT area, COUNT(1) c
        FROM Tickets
        WHERE org_id=? AND estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO','RESUELTO')
        GROUP BY area
    """, (org_id,))
    kpis = {
        "critical": critical,
        "active": total_active,
        "resolved_today": resolved_today,
        "by_area": {r["area"]: r["c"] for r in by_area}
    }

    # Serie de resueltos últimos 7 días (DB-agnóstico: calculado en Python)
    cutoff = (now - timedelta(days=7)).isoformat()
    rows = fetchall("""
        SELECT finished_at
        FROM Tickets
        WHERE org_id=? AND estado='RESUELTO' AND finished_at >= ?
    """, (org_id, cutoff))

    from collections import Counter
    cnt = Counter()
    for r in rows or []:
        key = date_key(r["finished_at"])
        if key:
            cnt[key] += 1

    charts = {
        "resolved_last7": [{"date": d, "count": cnt[d]} for d in sorted(cnt.keys())]
    }
    return kpis, charts


def get_area_data(area: str | None):
    """KPIs + tickets abiertos para SUPERVISOR (scoped by ORG; filter by area si viene)."""
    org_id, hotel_id = current_scope()
    if not org_id:
        return {"area": area, "critical": 0, "active": 0, "resolved_24h": 0}, []

    params = [org_id]
    where = ["org_id=?"]
    # If you want to limit by hotel, uncomment:
    # if hotel_id: where.append("hotel_id=?"); params.append(hotel_id)
    if area:
        where.append("area=?"); params.append(area)

    now = datetime.now()
    active = fetchall(
        f"""
        SELECT id, due_at
        FROM Tickets
        WHERE {' AND '.join(where)}
          AND estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')
        """, params
    )
    total_active = len(active)
    critical = sum(1 for r in active if is_critical(now, r['due_at']))

    cut24 = (datetime.now() - timedelta(days=1)).isoformat()
    resolved_24 = fetchone(
        f"""
        SELECT COUNT(1) c
        FROM Tickets
        WHERE {' AND '.join(where)} AND estado='RESUELTO'
        AND finished_at >= ?
        """, params + [cut24]
    )['c']

    kpis = {
        "area": area,
        "critical": critical,
        "active": total_active,
        "resolved_24h": resolved_24
    }

    rows = fetchall(
        f"""
        SELECT id, area, prioridad, estado, detalle, ubicacion, created_at, due_at, assigned_to, canal_origen
        FROM Tickets
        WHERE {' AND '.join(where)}
          AND estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')
        ORDER BY created_at DESC
        """, params
    )
    tickets = [{
        "id": r["id"], "area": r["area"], "prioridad": r["prioridad"], "estado": r["estado"],
        "detalle": r["detalle"], "ubicacion": r["ubicacion"], "created_at": r["created_at"],
        "due_at": r["due_at"], "is_critical": is_critical(datetime.now(), r["due_at"]),
        "assigned_to": r["assigned_to"],
        "canal": r["canal_origen"],
    } for r in rows]
    return kpis, tickets


def get_assigned_tickets_for_area(user_id: int, area: str | None):
    now = datetime.now()
    org_id, _ = current_scope()
    if not org_id:
        return []
    params = [org_id, user_id]
    where = ["org_id=?", "assigned_to=?",
             "estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')"]
    if area:
        where.append("area=?"); params.append(area)

    rows = fetchall(f"""
        SELECT id, area, prioridad, estado, detalle, ubicacion, created_at, due_at
        FROM Tickets
        WHERE {' AND '.join(where)}
        ORDER BY
          CASE estado
            WHEN 'EN_CURSO' THEN 0
            WHEN 'ACEPTADO' THEN 1
            WHEN 'ASIGNADO' THEN 2
            WHEN 'PAUSADO'  THEN 3
            WHEN 'DERIVADO' THEN 4
            ELSE 9
          END ASC,
          CASE prioridad
            WHEN 'URGENTE' THEN 0
            WHEN 'ALTA'    THEN 1
            WHEN 'MEDIA'   THEN 2
            WHEN 'BAJA'    THEN 3
            ELSE 9
          END ASC,
          created_at ASC
    """, tuple(params))

    return [{
        "id": r["id"], "area": r["area"], "prioridad": r["prioridad"], "estado": r["estado"],
        "detalle": r["detalle"], "ubicacion": r["ubicacion"], "created_at": r["created_at"],
        "due_at": r["due_at"], "is_critical": is_critical(now, r["due_at"])
    } for r in rows]


def get_in_progress_tickets_for_user(user_id: int, area: str | None):
    """Tickets del usuario en ACEPTADO/EN_CURSO (scoped by ORG, optional área)."""
    now = datetime.now()
    org_id, _ = current_scope()
    if not org_id:
        return []
    where = ["org_id=?", "assigned_to=?", "estado IN ('ACEPTADO','EN_CURSO')"]
    params = [org_id, user_id]
    if area:
        where.append("area=?")
        params.append(area)

    rows = fetchall(f"""
        SELECT id, area, prioridad, estado, detalle, ubicacion, created_at, due_at
        FROM Tickets
        WHERE {' AND '.join(where)}
        ORDER BY
            CASE estado WHEN 'EN_CURSO' THEN 0 ELSE 1 END ASC,
            CASE prioridad
                WHEN 'URGENTE' THEN 0
                WHEN 'ALTA'    THEN 1
                WHEN 'MEDIA'   THEN 2
                WHEN 'BAJA'    THEN 3
                ELSE 9
            END ASC,
            created_at ASC
    """, tuple(params))

    return [{
        "id": r["id"], "area": r["area"], "prioridad": r["prioridad"], "estado": r["estado"],
        "detalle": r["detalle"], "ubicacion": r["ubicacion"], "created_at": r["created_at"],
        "due_at": r["due_at"], "is_critical": is_critical(now, r["due_at"])
    } for r in rows]


def get_area_available_tickets(area: str, only_unassigned: bool = False):
    """
    Tickets del área en estado PENDIENTE.
    - only_unassigned=True => solo los sin asignar.
    Compatible con SQLite (a veces guarda ''), y Postgres (NULL).
    """
    org_id, _ = current_scope()
    if not org_id:
        return []

    where = ["org_id=?", "area=?", "estado='PENDIENTE'"]
    params = [org_id, area]

    if only_unassigned:
        if USE_PG:
            where.append("(assigned_to IS NULL)")
        else:
            # SQLite legacy: algunos registros pueden tener '' en vez de NULL
            where.append("(assigned_to IS NULL OR assigned_to='')")

    rows = fetchall(f"""
        SELECT id, area, prioridad, estado, detalle, ubicacion, created_at, due_at, assigned_to
        FROM Tickets
        WHERE {' AND '.join(where)}
        ORDER BY
        CASE prioridad
            WHEN 'URGENTE' THEN 0
            WHEN 'ALTA'    THEN 1
            WHEN 'MEDIA'   THEN 2
            WHEN 'BAJA'    THEN 3
            ELSE 9
        END ASC,
        created_at ASC
    """, tuple(params))

    now = datetime.now()
    return [{
        "id": r["id"], "area": r["area"], "prioridad": r["prioridad"], "estado": r["estado"],
        "detalle": r["detalle"], "ubicacion": r["ubicacion"], "created_at": r["created_at"],
        "due_at": r["due_at"], "is_critical": is_critical(now, r["due_at"])
    } for r in rows]


def get_history_tickets_for_user(user_id: int, area: str | None, days: int = 7):
    """Tickets resueltos por el usuario en los últimos N días (scoped by ORG, opcional área)."""
    now = datetime.now()
    cutoff = (now - timedelta(days=max(1, int(days)))).isoformat()
    org_id, _ = current_scope()
    if not org_id:
        return []
    params = [org_id, user_id, cutoff]
    where = ["org_id=?", "assigned_to=?", "estado='RESUELTO'", "finished_at >= ?"]
    if area:
        where.append("area=?")
        params.append(area)
    rows = fetchall(f"""
        SELECT id, area, prioridad, estado, detalle, ubicacion, created_at, due_at, finished_at
        FROM Tickets
        WHERE {' AND '.join(where)}
        ORDER BY finished_at DESC
    """, tuple(params))
    return [{
        "id": r["id"], "area": r["area"], "prioridad": r["prioridad"], "estado": r["estado"],
        "detalle": r["detalle"], "ubicacion": r["ubicacion"], "created_at": r["created_at"],
        "due_at": r["due_at"], "finished_at": r.get("finished_at"),
        "is_critical": False
    } for r in rows]


def get_assigned_tickets(user_id: int):
    """Tickets asignados a un técnico/operador (scoped by ORG)."""
    now = datetime.now()
    org_id, _hotel_id = current_scope()
    if not org_id:
        return []
    rows = fetchall("""
        SELECT id, area, prioridad, estado, detalle, ubicacion, created_at, due_at
        FROM Tickets
        WHERE org_id=? AND assigned_to = ?
          AND estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')
        ORDER BY created_at DESC
    """, (org_id, user_id))
    return [{
        "id": r["id"], "area": r["area"], "prioridad": r["prioridad"], "estado": r["estado"],
        "detalle": r["detalle"], "ubicacion": r["ubicacion"], "created_at": r["created_at"],
        "due_at": r["due_at"], "is_critical": is_critical(now, r["due_at"])
    } for r in rows]


# ---------------------------- Gerencia summary API (30d window) ----------------------------

from math import isfinite
from collections import defaultdict, Counter  # used in summary

def _minutes_between(a_iso, b_iso):
    try:
        a = datetime.fromisoformat(str(a_iso))
        b = datetime.fromisoformat(str(b_iso))
        return max(0, int((b - a).total_seconds() // 60))
    except Exception:
        return None


@bp.get('/api/gerencia/summary')
def api_gerencia_summary():
    """Org-level metrics for last 30 days + open snapshot (+ type metrics + per-scope SLA targets)."""
    if 'user' not in session:
        return jsonify({"error": "unauthorized"}), 401
    org_id, _hotel_id = current_scope()
    if not org_id:
        return jsonify({"error": "no org"}), 400

    now = datetime.now()
    since_dt = now - timedelta(days=30)
    since = since_dt.isoformat()

    # --- Open snapshot
    open_rows = fetchall("""
        SELECT t.id, t.area, t.prioridad, t.estado, t.detalle, t.ubicacion, t.canal_origen,
               t.created_at, t.due_at, t.assigned_to,
               u.username AS assigned_name
        FROM Tickets t
        LEFT JOIN Users u ON u.id = t.assigned_to
        WHERE t.org_id=? AND t.estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')
        ORDER BY t.created_at DESC
    """, (org_id,))

    snapshot = {
        "open_total": len(open_rows),
        "open_unassigned": sum(1 for r in open_rows if not r.get("assigned_to")),
        "by_tech": {},
    }
    by_tech = defaultdict(int)
    for r in open_rows:
        tech = r.get("assigned_name") or "(sin asignar)"
        by_tech[tech] += 1
    snapshot["by_tech"] = dict(sorted(by_tech.items(), key=lambda kv: kv[1], reverse=True))

    # --- Resolved last 30d
    resolved = fetchall("""
        SELECT id, area, prioridad, canal_origen, created_at, finished_at, due_at, ubicacion
        FROM Tickets
        WHERE org_id=? AND estado='RESUELTO' AND finished_at >= ?
    """, (org_id, since))

    # ---- Aggregations
    ttr_sum_area = Counter(); ttr_n_area = Counter()
    ttr_sum_tipo = Counter(); ttr_n_tipo = Counter()
    sla_hit_area = Counter(); sla_n_area = Counter()
    sla_hit_tipo = Counter(); sla_n_tipo = Counter()
    by_loc = Counter()  # for reincidentes (ubicacion)

    def safe_tipo(row):
        # We treat "tipo" as canal_origen for now.
        return (row.get("canal_origen") or "OTROS").upper()

    for r in resolved:
        area = r.get("area") or "GENERAL"
        tipo = safe_tipo(r)
        if r.get("ubicacion"):
            by_loc[r["ubicacion"]] += 1

        # TTR
        ttr = _minutes_between(r.get("created_at"), r.get("finished_at"))
        if ttr is not None:
            ttr_sum_area[area] += ttr;  ttr_n_area[area] += 1
            ttr_sum_tipo[tipo] += ttr;  ttr_n_tipo[tipo] += 1

        # SLA hit if finished_at <= due_at
        da = r.get("due_at")
        if da:
            sla_n_area[area] += 1
            sla_n_tipo[tipo] += 1
            try:
                finished = datetime.fromisoformat(str(r.get("finished_at")))
                due      = datetime.fromisoformat(str(da))
                if finished <= due:
                    sla_hit_area[area] += 1
                    sla_hit_tipo[tipo] += 1
            except Exception:
                pass

    ttr_by_area = {a: int(round(ttr_sum_area[a] / ttr_n_area[a])) for a in ttr_n_area if ttr_n_area[a] > 0}
    ttr_by_type = {t: int(round(ttr_sum_tipo[t] / ttr_n_tipo[t])) for t in ttr_n_tipo if ttr_n_tipo[t] > 0}

    sla_rate_by_area = {
        a: round(100.0 * (sla_hit_area[a] / sla_n_area[a]), 1) if sla_n_area[a] > 0 else 0.0
        for a in set(list(sla_n_area.keys()) + list(sla_hit_area.keys()))
    }
    sla_rate_by_tipo = {
        t: round(100.0 * (sla_hit_tipo[t] / sla_n_tipo[t]), 1) if sla_n_tipo[t] > 0 else 0.0
        for t in set(list(sla_n_tipo.keys()) + list(sla_hit_tipo.keys()))
    }

    # Reincidents (rooms with >1 tickets in 30d)
    recent_rows = fetchall("""
        SELECT canal_origen, ubicacion, MAX(created_at) AS last_seen, COUNT(1) AS c
        FROM Tickets
        WHERE org_id=? AND created_at >= ? AND ubicacion IS NOT NULL
        GROUP BY canal_origen, ubicacion
        HAVING COUNT(1) > 1
        ORDER BY c DESC, last_seen DESC
        LIMIT 50
    """, (org_id, since))
    recurrentes = [{
        "tipo": (r.get("canal_origen") or "OTROS").upper(),
        "ubicacion": r.get("ubicacion"),
        "count": r.get("c"),
        "last_seen": r.get("last_seen"),
    } for r in recent_rows]

    reincidents_total = sum(1 for _ in by_loc.items() if _[1] > 1)

    # Mix by area (counts, last 30d, any estado)
    mix_rows = fetchall("""
        SELECT area, COUNT(1) c
        FROM Tickets
        WHERE org_id=? AND created_at >= ?
        GROUP BY area
    """, (org_id, since))
    mix_by_area = {(r["area"] or "GENERAL"): r["c"] for r in mix_rows}

    # Tickets per day (last 30d, any estado)
    ts_rows = fetchall("""
        SELECT created_at FROM Tickets
        WHERE org_id=? AND created_at >= ?
    """, (org_id, since))
    by_day = Counter()
    for r in ts_rows:
        k = date_key(r.get("created_at"))
        if k:
            by_day[k] += 1
    ts = [{"date": d, "count": by_day[d]} for d in sorted(by_day.keys())]

    # Overall avg resolution (TTR) last 30d
    all_ttr_vals = []
    for r in resolved:
        t = _minutes_between(r.get("created_at"), r.get("finished_at"))
        if t is not None:
            all_ttr_vals.append(t)
    avg_ttr_30d = int(round(sum(all_ttr_vals) / len(all_ttr_vals))) if all_ttr_vals else 0

    # ---- SLA targets (per area / per tipo) from optional table slarules
    # Fallback to env SLA_TARGET if no rule.
    def _get_sla_target(area=None, tipo=None):
        # Try (area,tipo) -> area -> tipo -> env default
        args = []
        clauses = []
        # We'll append org_id at the end to match the WHERE composition below.
        if area is not None and tipo is not None:
            clauses.append("(scope='area_tipo' AND area=? AND tipo=?)")
            args.extend([area, tipo])
        if area is not None:
            clauses.append("(scope='area' AND area=?)")
            args.append(area)
        if tipo is not None:
            clauses.append("(scope='tipo' AND tipo=?)")
            args.append(tipo)

        try:
            rows = fetchall(f"""
                SELECT scope, area, tipo, target
                FROM slarules
                WHERE ({' OR '.join(clauses)}) AND org_id=?
                ORDER BY CASE scope
                    WHEN 'area_tipo' THEN 1
                    WHEN 'area' THEN 2
                    WHEN 'tipo' THEN 3
                    ELSE 9
                END
                LIMIT 1
            """, tuple(args + [org_id]))
            if rows:
                return float(rows[0]["target"]) * 100.0
        except Exception:
            pass
        return float(os.getenv("SLA_TARGET", "0.90")) * 100.0

    # sla_vs_target by area
    areas_sorted = sorted(sla_rate_by_area.keys())
    sla_vs_target_area = [{
        "area": a,
        "real": sla_rate_by_area.get(a, 0.0),
        "objetivo": round(_get_sla_target(area=a), 1)
    } for a in areas_sorted]

    # sla_vs_target by tipo
    tipos_sorted = sorted(sla_rate_by_tipo.keys())
    sla_vs_target_tipo = [{
        "tipo": t,
        "real": sla_rate_by_tipo.get(t, 0.0),
        "objetivo": round(_get_sla_target(tipo=t), 1)
    } for t in tipos_sorted]

    # Open items (with elapsed)
    open_items = [{
        "id": r["id"],
        "area": r["area"],
        "prioridad": r["prioridad"],
        "estado": r["estado"],
        "detalle": r["detalle"],
        "ubicacion": r["ubicacion"],
        "tipo": (r.get("canal_origen") or "OTROS").upper(),
        "assigned_to": r.get("assigned_to"),
        "assigned_name": r.get("assigned_name"),
        "created_at": r["created_at"],
        "due_at": r["due_at"],
        "elapsed_min": _minutes_between(r["created_at"], now.isoformat())
    } for r in open_rows]

    return jsonify({
        "at": now.isoformat(),
        "snapshot": snapshot,
        "ttr_by_area": ttr_by_area,
        "ttr_by_type": ttr_by_type,
        "sla_by_area": sla_rate_by_area,
        "sla_by_type_tipo": sla_rate_by_tipo,
        "reincidents_total": reincidents_total,
        "recurrentes": recurrentes,
        "mix_by_area": mix_by_area,
        "tickets_per_day": ts,
        "avg_ttr_30d": avg_ttr_30d,
        "sla_vs_target_area": sla_vs_target_area,
        "sla_vs_target_tipo": sla_vs_target_tipo,
        "open_items": open_items
    })


@bp.get('/api/gerencia/sin_asignar')
def api_gerencia_sin_asignar():
    if 'user' not in session:
        return jsonify({"error": "unauthorized"}), 401
    org_id, _hotel_id = current_scope()
    if not org_id:
        return jsonify({"error": "no org"}), 400

    rows = fetchall("""
        SELECT t.id, t.area, t.prioridad, t.estado, t.detalle, t.ubicacion, t.created_at, t.due_at
        FROM Tickets t
        WHERE t.org_id=? AND t.assigned_to IS NULL
          AND t.estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')
        ORDER BY
          CASE t.prioridad
            WHEN 'URGENTE' THEN 1
            WHEN 'ALTA'    THEN 2
            WHEN 'MEDIA'   THEN 3
            ELSE 4
          END ASC,
          t.created_at ASC
        LIMIT 200
    """, (org_id,))
    now = datetime.now().isoformat()
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "area": r["area"],
            "prioridad": r["prioridad"],
            "estado": r["estado"],
            "detalle": r["detalle"],
            "ubicacion": r["ubicacion"],
            "created_at": r["created_at"],
            "due_at": r["due_at"],
            "elapsed_min": _minutes_between(r["created_at"], now)
        })
    return jsonify({"items": out, "count": len(out)})


@bp.get('/api/gerencia/performance')
def api_gerencia_performance():
    if 'user' not in session:
        return jsonify({"error": "unauthorized"}), 401
    org_id, _hotel_id = current_scope()
    if not org_id:
        return jsonify({"error": "no org"}), 400

    group_by = (request.args.get('group_by') or 'area').lower()
    if group_by not in ('user', 'supervisor', 'area'):
        return jsonify({"error": "bad group_by"}), 400

    since = (datetime.now() - timedelta(days=30)).isoformat()

    # Base resolved set (last 30d)
    base = fetchall("""
        SELECT t.id, t.area, t.assigned_to, t.created_at, t.finished_at, t.due_at,
               u.username AS user_name,
               u.supervisor_id,
               s.username AS supervisor_name
        FROM Tickets t
        LEFT JOIN Users u ON u.id = t.assigned_to
        LEFT JOIN Users s ON s.id = u.supervisor_id
        WHERE t.org_id=? AND t.estado='RESUELTO' AND t.finished_at >= ?
    """, (org_id, since))

    # buckets
    from collections import defaultdict, Counter
    agg = defaultdict(lambda: {
        "count": 0, "ttr_sum": 0, "ttr_n": 0, "sla_n": 0, "sla_hit": 0
    })

    def key_of(row):
        if group_by == 'user':
            return row.get("user_name") or "(sin asignar)"
        if group_by == 'supervisor':
            return row.get("supervisor_name") or "(sin supervisor)"
        return row.get("area") or "GENERAL"

    for r in base:
        k = key_of(r)
        a = agg[k]
        a["count"] += 1

        # TTR
        ttr = _minutes_between(r.get("created_at"), r.get("finished_at"))
        if ttr is not None:
            a["ttr_sum"] += ttr; a["ttr_n"] += 1

        # SLA
        if r.get("due_at"):
            a["sla_n"] += 1
            try:
                finished = datetime.fromisoformat(str(r.get("finished_at")))
                due      = datetime.fromisoformat(str(r.get("due_at")))
                if finished <= due:
                    a["sla_hit"] += 1
            except Exception:
                pass

    # Convert to rows
    rows = []
    for k, a in agg.items():
        ttr = int(round(a["ttr_sum"] / a["ttr_n"])) if a["ttr_n"] > 0 else 0
        sla = round(100.0 * a["sla_hit"] / a["sla_n"], 1) if a["sla_n"] > 0 else 0.0
        rows.append({"key": k, "tickets": a["count"], "ttr_avg_min": ttr, "sla_pct": sla})

    # Sort: SLA desc, then TTR asc, then tickets desc
    rows.sort(key=lambda r: (-r["sla_pct"], r["ttr_avg_min"], -r["tickets"]))
    return jsonify({"group_by": group_by, "rows": rows, "since": since})
