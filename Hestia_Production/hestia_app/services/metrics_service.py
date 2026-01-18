# hestia_app/services/metrics_service.py
"""
Metrics service for React dashboard.
Wraps existing KPI functions (sla.py, gerencia/routes.py) and provides simplified JSON responses.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from collections import Counter

from .db import fetchall, fetchone
from .sla import is_critical, get_global_kpis
from ..core.scope import current_scope
from ..core.status import OPEN_STATES


def compute_summary(filters=None) -> dict:
    """
    Compute summary metrics for dashboard.
    Returns simplified KPIs compatible with React dashboard format.
    
    Uses existing get_global_kpis() and adds:
    - overdue_count: Tickets past due_at
    - at_risk_count: Tickets due within 1 hour
    - resolved_7d: Count from last 7 days
    - avg_resolution_minutes_7d: Average TTR last 7 days
    
    Filtered by org_id, hotel_id from current_scope().
    """
    org_id, hotel_id = current_scope()
    if not org_id:
        return {
            "open_count": 0,
            "overdue_count": 0,
            "at_risk_count": 0,
            "resolved_7d": 0,
            "avg_resolution_minutes_7d": 0,
            "at": datetime.now().isoformat()
        }

    # Get base KPIs from existing function
    kpis, charts = get_global_kpis()
    
    now = datetime.now()
    
    # Build WHERE clause considering hotel_id if present
    where_parts = ["org_id=?"]
    params = [org_id]
    if hotel_id:
        where_parts.append("hotel_id=?")
        params.append(hotel_id)
    base_where = " AND ".join(where_parts)

    # Calculate overdue vs at-risk
    open_rows = fetchall(
        f"""
        SELECT due_at
        FROM Tickets
        WHERE {base_where} AND estado IN ({','.join(['?'] * len(OPEN_STATES))})
          AND due_at IS NOT NULL
        """,
        tuple(params + list(OPEN_STATES))
    )
    
    overdue_count = 0
    at_risk_count = 0
    one_hour_threshold = now + timedelta(hours=1)
    
    for row in open_rows:
        if row.get("due_at"):
            try:
                due_dt = datetime.fromisoformat(str(row["due_at"]))
                if due_dt <= now:
                    overdue_count += 1
                elif due_dt <= one_hour_threshold:
                    at_risk_count += 1
            except:
                pass

    # Resolved last 7 days
    seven_days_ago = (now - timedelta(days=7)).isoformat()
    resolved_result = fetchone(
        f"""
        SELECT COUNT(1) AS c
        FROM Tickets
        WHERE {base_where} AND estado='RESUELTO' AND finished_at >= ?
        """,
        tuple(params + [seven_days_ago])
    )
    resolved_7d = resolved_result["c"] if resolved_result else 0

    # Average resolution time (TTR) last 7 days
    resolution_rows = fetchall(
        f"""
        SELECT created_at, finished_at
        FROM Tickets
        WHERE {base_where} AND estado='RESUELTO'
          AND finished_at >= ?
          AND created_at IS NOT NULL
          AND finished_at IS NOT NULL
        """,
        tuple(params + [seven_days_ago])
    )

    total_minutes = 0
    count = 0
    for row in resolution_rows:
        try:
            created = datetime.fromisoformat(str(row["created_at"]))
            finished = datetime.fromisoformat(str(row["finished_at"]))
            delta = finished - created
            total_minutes += delta.total_seconds() / 60
            count += 1
        except:
            pass

    avg_resolution_minutes_7d = int(total_minutes / count) if count > 0 else 0

    return {
        "open_count": kpis.get("active", 0),
        "overdue_count": overdue_count,
        "at_risk_count": at_risk_count,
        "resolved_7d": resolved_7d,
        "avg_resolution_minutes_7d": avg_resolution_minutes_7d,
        "critical_by_priority": charts.get("critical_by_priority", {"labels": [], "values": []}),
        "resolved_trend_7d": charts.get("resolved_last7", []),
        "at": now.isoformat()
    }


def compute_quality(filters=None) -> dict:
    """
    Compute quality metrics breakdown by area.
    
    For each area (MANTENCION, HOUSEKEEPING, ROOMSERVICE):
    - open: Current open tickets
    - overdue: Tickets past due_at
    - avg_resolution_minutes_7d: Average TTR last 7 days
    - resolved_7d: Count resolved last 7 days
    - sla_pct: Percentage of tickets finished before due_at
    
    Filtered by org_id, hotel_id from current_scope().
    """
    org_id, hotel_id = current_scope()
    if not org_id:
        return {
            "breakdown": [],
            "at": datetime.now().isoformat()
        }

    now = datetime.now()
    seven_days_ago = (now - timedelta(days=7)).isoformat()

    # Build WHERE clause
    where_parts = ["org_id=?"]
    params = [org_id]
    if hotel_id:
        where_parts.append("hotel_id=?")
        params.append(hotel_id)
    base_where = " AND ".join(where_parts)

    # Get all areas from database
    areas_result = fetchall(
        f"SELECT DISTINCT area FROM Tickets WHERE {base_where}",
        tuple(params)
    )
    areas = [row["area"] for row in areas_result if row.get("area")]
    
    # If no areas found, use defaults
    if not areas:
        areas = ["MANTENCION", "HOUSEKEEPING", "ROOMSERVICE"]

    breakdown = []

    for area in areas:
        area_params = params + [area]

        # Open count
        open_result = fetchall(
            f"""
            SELECT COUNT(1) AS c
            FROM Tickets
            WHERE {base_where} AND area=?
              AND estado IN ({','.join(['?'] * len(OPEN_STATES))})
            """,
            tuple(area_params + list(OPEN_STATES))
        )
        open_count = open_result[0]["c"] if open_result else 0

        # Overdue count
        overdue_rows = fetchall(
            f"""
            SELECT due_at
            FROM Tickets
            WHERE {base_where} AND area=?
              AND estado IN ({','.join(['?'] * len(OPEN_STATES))})
              AND due_at IS NOT NULL
            """,
            tuple(area_params + list(OPEN_STATES))
        )
        
        overdue_count = sum(
            1 for row in overdue_rows
            if row.get("due_at") and datetime.fromisoformat(str(row["due_at"])) <= now
        )

        # Resolved last 7 days
        resolved_result = fetchone(
            f"""
            SELECT COUNT(1) AS c
            FROM Tickets
            WHERE {base_where} AND area=? AND estado='RESUELTO' AND finished_at >= ?
            """,
            tuple(area_params + [seven_days_ago])
        )
        resolved_7d = resolved_result["c"] if resolved_result else 0

        # Average resolution time (TTR) last 7 days
        resolution_rows = fetchall(
            f"""
            SELECT created_at, finished_at
            FROM Tickets
            WHERE {base_where} AND area=?
              AND estado='RESUELTO'
              AND finished_at >= ?
              AND created_at IS NOT NULL
              AND finished_at IS NOT NULL
            """,
            tuple(area_params + [seven_days_ago])
        )

        total_minutes = 0
        count = 0
        for row in resolution_rows:
            try:
                created = datetime.fromisoformat(str(row["created_at"]))
                finished = datetime.fromisoformat(str(row["finished_at"]))
                delta = finished - created
                total_minutes += delta.total_seconds() / 60
                count += 1
            except:
                pass

        avg_resolution_minutes = int(total_minutes / count) if count > 0 else 0

        # SLA percentage (tickets finished before due_at)
        sla_rows = fetchall(
            f"""
            SELECT created_at, finished_at, due_at
            FROM Tickets
            WHERE {base_where} AND area=?
              AND estado='RESUELTO'
              AND finished_at >= ?
              AND due_at IS NOT NULL
            """,
            tuple(area_params + [seven_days_ago])
        )

        sla_hit = 0
        sla_total = len(sla_rows)
        for row in sla_rows:
            try:
                finished = datetime.fromisoformat(str(row["finished_at"]))
                due = datetime.fromisoformat(str(row["due_at"]))
                if finished <= due:
                    sla_hit += 1
            except:
                pass

        sla_pct = round(100.0 * sla_hit / sla_total, 1) if sla_total > 0 else 0.0

        breakdown.append({
            "area": area,
            "open": open_count,
            "overdue": overdue_count,
            "avg_resolution_minutes_7d": avg_resolution_minutes,
            "resolved_7d": resolved_7d,
            "sla_pct": sla_pct
        })

    return {
        "breakdown": breakdown,
        "at": now.isoformat()
    }
