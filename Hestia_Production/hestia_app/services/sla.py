from datetime import datetime, timedelta
from .db import fetchone


def is_critical(now: datetime, due_at) -> bool:
    """
    Accepts either ISO string (SQLite) or datetime (Postgres) for due_at.
    crítico si faltan <=10 min o ya vencido
    """
    if not due_at:
        return False
    try:
        if isinstance(due_at, datetime):
            due = due_at
        else:
            due = datetime.fromisoformat(str(due_at))
    except Exception:
        return False
    return now >= (due - timedelta(minutes=10))

def sla_minutes(area: str, prioridad: str) -> int | None:
    r = fetchone("SELECT max_minutes FROM SLARules WHERE area=? AND prioridad=?", (area, prioridad))
    try:
        return int(r["max_minutes"]) if r and r.get("max_minutes") is not None else None
    except Exception:
        return None

def compute_due(created_at: datetime, area: str, prioridad: str) -> datetime | None:
    mins = sla_minutes(area, prioridad)
    return created_at + timedelta(minutes=mins) if mins else None

# --- ADD BELOW: SSR KPIs for gerente & supervisor, DB-backed ---
from datetime import datetime, timedelta
from .db import fetchall, fetchone
from ..core.status import OPEN_STATES
from ..core.scope import current_scope

def _date_key(iso_str):
    try:
        return datetime.fromisoformat(str(iso_str)).date().isoformat()
    except Exception:
        return None

def get_global_kpis():
    """
    Server-side KPIs + small charts for the top of dashboard_gerente.html.
    Returns (kpis, charts) shaped exactly as the template expects:
      kpis = {
        "critical": int,
        "active": int,
        "resolved_today": int,
        "by_area": { area: count, ... },
        "last_critical": [ {id, area, prioridad, detalle, created_at, due_at, is_critical}, ... ]
      }
      charts = {
        "resolved_last7": [{date, count}, ...],
        "critical_by_priority": {"labels":[...], "values":[...] }
      }
    """
    now = datetime.now()
    org_id, _ = current_scope()
    if not org_id:
        return {"critical": 0, "active": 0, "resolved_today": 0, "by_area": {}, "last_critical": []}, {
            "resolved_last7": [], "critical_by_priority": {"labels": [], "values": []}
        }

    # Active & critical (open and within org)
    active_rows = fetchall(
        f"SELECT id, due_at FROM Tickets WHERE org_id=? AND estado IN ({','.join(['?']*len(OPEN_STATES))})",
        (org_id, *OPEN_STATES)
    )
    total_active = len(active_rows)
    critical = 0
    for r in active_rows:
        try:
            due = r["due_at"]
        except Exception:
            due = None
        if is_critical(now, due):
            critical += 1

    # Resueltos hoy (by finished_at day)
    sod = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    resolved_today = fetchone(
        "SELECT COUNT(1) AS c FROM Tickets WHERE org_id=? AND estado='RESUELTO' AND finished_at >= ?",
        (org_id, sod)
    )["c"]

    # By area (open)
    by_area_rows = fetchall(
        f"""
        SELECT area, COUNT(1) AS c
        FROM Tickets
        WHERE org_id=? AND estado IN ({','.join(['?']*len(OPEN_STATES))})
        GROUP BY area
        """,
        (org_id, *OPEN_STATES)
    )
    by_area = { (r["area"] or "GENERAL"): r["c"] for r in by_area_rows }

    # Últimos críticos (open & due_at < now)
    last_critical = fetchall(
        f"""
        SELECT id, area, prioridad, detalle, created_at, due_at
        FROM Tickets
        WHERE org_id=? AND estado IN ({','.join(['?']*len(OPEN_STATES))})
          AND due_at IS NOT NULL
        ORDER BY due_at ASC
        LIMIT 12
        """,
        (org_id, *OPEN_STATES)
    )
    for r in last_critical:
        r["is_critical"] = is_critical(now, r.get("due_at"))

    # Serie de resueltos últimos 7 días
    cutoff7 = (now - timedelta(days=7)).isoformat()
    rows7 = fetchall("""
        SELECT finished_at FROM Tickets
        WHERE org_id=? AND estado='RESUELTO' AND finished_at >= ?
    """, (org_id, cutoff7))
    from collections import Counter
    C = Counter()
    for r in rows7 or []:
        dk = _date_key(r.get("finished_at"))
        if dk:
            C[dk] += 1
    resolved_last7 = [{"date": d, "count": C[d]} for d in sorted(C.keys())]

    # Críticos por prioridad (open & critical: due within 10m or overdue)
    boundary = now + timedelta(minutes=10)
    crit_rows = fetchall(
        f"""
        SELECT prioridad, COUNT(1) AS c
        FROM Tickets
        WHERE org_id=?
          AND estado IN ({','.join(['?']*len(OPEN_STATES))})
          AND due_at IS NOT NULL
          AND due_at <= ?
        GROUP BY prioridad
        ORDER BY prioridad
        """,
        (org_id, *OPEN_STATES, boundary.isoformat())
    )
    crit_labels = [r["prioridad"] for r in crit_rows]
    crit_values = [r["c"] for r in crit_rows]


    kpis = {
        "critical": int(critical),
        "active": int(total_active),
        "resolved_today": int(resolved_today or 0),
        "by_area": by_area,
        "last_critical": last_critical,
    }
    charts = {
        "resolved_last7": resolved_last7,
        "critical_by_priority": {"labels": crit_labels, "values": crit_values},
    }
    return kpis, charts


def get_area_data(area: str | None):
    """
    Supervisor SSR block: returns (kpis, tickets) for the selected area (or all).
    Mirrors your existing logic in gerencia blueprint so the supervisor page can SSR.
    """
    org_id, _ = current_scope()
    if not org_id:
        return {"area": area, "critical": 0, "active": 0, "resolved_24h": 0}, []

    params = [org_id]
    wh = ["org_id=?"]
    if area:
        wh.append("area=?"); params.append(area)

    now = datetime.now()
    open_rows = fetchall(
        f"SELECT id, due_at FROM Tickets WHERE {' AND '.join(wh)} AND estado IN ({','.join(['?']*len(OPEN_STATES))})",
        tuple(params + list(OPEN_STATES))
    )
    total_active = len(open_rows)
    critical = sum(1 for r in open_rows if is_critical(now, r.get("due_at")))

    cut24 = (now - timedelta(days=1)).isoformat()
    resolved_24 = fetchone(
        f"SELECT COUNT(1) AS c FROM Tickets WHERE {' AND '.join(wh)} AND estado='RESUELTO' AND finished_at >= ?",
        tuple(params + [cut24])
    )["c"]

    kpis = {"area": area, "critical": critical, "active": total_active, "resolved_24h": int(resolved_24 or 0)}

    rows = fetchall(
        f"""
        SELECT id, area, prioridad, estado, detalle, ubicacion, created_at, due_at, assigned_to, canal_origen
        FROM Tickets
        WHERE {' AND '.join(wh)} AND estado IN ({','.join(['?']*len(OPEN_STATES))})
        ORDER BY created_at DESC
        """,
        tuple(params + list(OPEN_STATES))
    )
    tickets = [{
        "id": r["id"], "area": r["area"], "prioridad": r["prioridad"], "estado": r["estado"],
        "detalle": r["detalle"], "ubicacion": r["ubicacion"], "created_at": r["created_at"],
        "due_at": r["due_at"], "is_critical": is_critical(datetime.now(), r["due_at"]),
        "assigned_to": r["assigned_to"], "canal": r["canal_origen"],
    } for r in rows]
    return kpis, tickets

