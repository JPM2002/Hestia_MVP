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
