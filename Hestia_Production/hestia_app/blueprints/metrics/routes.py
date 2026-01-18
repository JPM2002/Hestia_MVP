from __future__ import annotations

from flask import jsonify
from . import bp

# --- Scope and permissions ---
try:
    from ...core.scope import current_scope
except Exception:
    from hestia_app.core.scope import current_scope  # type: ignore

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

# --- Metrics service ---
try:
    from ...services.metrics_service import compute_summary, compute_quality
except Exception:
    from hestia_app.services.metrics_service import compute_summary, compute_quality  # type: ignore


# ---------- Metrics: Summary ----------
@bp.get('/api/metrics/summary')
@require_perm('ticket.view.all')
def api_metrics_summary():
    """
    Return summary metrics for dashboard:
    - open_count: tickets currently open
    - overdue_count: tickets past due_at
    - at_risk_count: tickets close to due_at (within 1 hour)
    - resolved_7d: tickets resolved in last 7 days
    - avg_resolution_minutes_7d: average resolution time in last 7 days
    - critical_by_priority: breakdown by priority
    - resolved_trend_7d: daily resolution counts
    
    Filters by org_id and hotel_id from current_scope().
    """
    org_id, hotel_id = current_scope()
    if not org_id:
        return jsonify({"error": "no org"}), 400

    try:
        result = compute_summary()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- Metrics: Quality Breakdown ----------
@bp.get('/api/metrics/quality')
@require_perm('ticket.view.all')
def api_metrics_quality():
    """
    Return quality metrics breakdown by area:
    - area: MANTENCION | HOUSEKEEPING | ROOMSERVICE
    - open: tickets currently open
    - overdue: tickets past due_at
    - avg_resolution_minutes_7d: average resolution time for this area
    - resolved_7d: tickets resolved in last 7 days
    - sla_pct: percentage of tickets finished before due_at
    
    Filters by org_id and hotel_id from current_scope().
    """
    org_id, hotel_id = current_scope()
    if not org_id:
        return jsonify({"error": "no org"}), 400

    try:
        result = compute_quality()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
