from __future__ import annotations
from datetime import datetime, timedelta
from random import randint, choice
from flask import render_template, jsonify, request
from . import bp

# --- Opcional: integra tu capa DB real si ya existe (cae a mocks si falla) ---
try:
    from hestia_app.services.db import get_db
except Exception:
    get_db = None


# =============================================================================
# Helpers de datos "seguros" (mocks) para no romper mientras conectas la DB
# =============================================================================
AREAS = ["MANTENCION", "HOUSEKEEPING", "ROOMSERVICE"]
PRIOS = ["URGENTE", "ALTA", "MEDIA", "BAJA"]

def _now_str(delta_min: int = 0) -> str:
    return (datetime.now() + timedelta(minutes=delta_min)).strftime("%Y-%m-%d %H:%M")

def _mk_ticket(i: int, area: str | None = None) -> dict:
    ar = area or choice(AREAS)
    pr = choice(PRIOS)
    created = _now_str(-randint(10, 600))
    due = _now_str(randint(10, 300)) if pr in ("URGENTE", "ALTA") else None
    return {
        "id": i,
        "area": ar,
        "prioridad": pr,
        "estado": choice(["PENDIENTE", "EN_CURSO", "ACEPTADO", "PAUSADO"]),
        "detalle": f"Incidencia {ar.lower()} #{i}",
        "ubicacion": choice(["101", "202", "302", "Lobby", "Spa"]),
        "created_at": created,
        "due_at": due,
        "is_critical": pr == "URGENTE",
        "assigned_name": choice(["Ana Pérez", "Luis Soto", "María Díaz", "(sin asignar)"]),
        "elapsed_min": randint(5, 720),
    }

def _mock_kpis_global() -> dict:
    by_area = {a: randint(3, 12) for a in AREAS}
    return {
        "critical": randint(1, 6),
        "active": sum(by_area.values()),
        "resolved_today": randint(4, 18),
        "by_area": by_area,
        # Extras para supervisor
        "area": choice(AREAS),
        "sla_rate": round(randint(75, 97) + randint(0, 9)/10, 1),
        "critical_area": randint(0, 5),
        "active_area": randint(4, 20),
    }

def _mock_charts() -> dict:
    last7 = [{"date": (datetime.now() - timedelta(days=d)).strftime("%Y-%m-%d"),
              "count": randint(3, 18)} for d in range(6, -1, -1)]
    by_pri_labels = PRIOS
    by_pri_vals = [randint(1, 8) for _ in by_pri_labels]
    return {
        "resolved_last7": last7,
        "critical_by_priority": {"labels": by_pri_labels, "values": by_pri_vals},
    }


# =============================================================================
# Vistas de página (HTML)
# =============================================================================

# Raíz del dashboard. Tenlo también en /dashboard para conveniencia.
@bp.get("/", endpoint="dashboard")
@bp.get("/dashboard")
def dashboard_home():
    kpis = _mock_kpis_global()
    return render_template("dashboards/dashboard.html", kpis=kpis)

@bp.get("/gerente")
def dashboard_gerente():
    kpis = _mock_kpis_global()
    charts = _mock_charts()
    # Tabla de críticos reciente
    kpis["last_critical"] = [_mk_ticket(1000 + i) for i in range(1, 7)]
    return render_template("dashboards/dashboard_gerente.html", kpis=kpis, charts=charts)

@bp.get("/recepcion")
def dashboard_recepcion():
    # La página consume APIs vía fetch; no requiere mucho contexto
    return render_template("dashboards/dashboard_recepcion.html")

@bp.get("/supervisor")
def dashboard_supervisor():
    kpis = _mock_kpis_global()
    area = request.args.get("area") or kpis["area"]
    kpis["area"] = area
    # Tabla de abiertos inicial
    tickets = [_mk_ticket(i, area=area) for i in range(1, 23)]
    # Lista de técnicos para el select de reasignación
    techs = [{"id": i, "username": n} for i, n in enumerate(["Ana", "Luis", "María", "Jorge"], start=1)]
    return render_template("dashboards/dashboard_supervisor.html", kpis=kpis, tickets=tickets, techs=techs)

@bp.get("/tecnico")
def dashboard_tecnico():
    # Lista de tickets del técnico (mock)
    tickets = [_mk_ticket(i) for i in range(1, 16)]
    return render_template("dashboards/dashboard_tecnico.html", tickets=tickets)


# =============================================================================
# APIs consumidas por las vistas (JSON)
# =============================================================================

# ---------- Gerencia ----------
@bp.get("/api/gerencia/summary")
def api_gerencia_summary():
    # Estructura esperada por dashboard_gerente.html
    areas = AREAS
    # SLA por área
    sla_by_area = {a: round(randint(80, 98) + randint(0, 9)/10, 1) for a in areas}
    # SLA vs objetivo (por área)
    sla_vs_target = [{"area": a, "real": sla_by_area[a], "objetivo": 90.0} for a in areas]
    # TTR por área
    ttr_by_area = {a: randint(20, 90) for a in areas}
    # Mix por área (counts)
    mix_by_area = {a: randint(5, 20) for a in areas}
    # Tickets por día (30d)
    ts = [{"date": (datetime.now() - timedelta(days=d)).strftime("%Y-%m-%d"),
           "count": randint(4, 18)} for d in range(29, -1, -1)]
    # Abiertos (tabla)
    open_items = [_mk_ticket(2000 + i) for i in range(1, 25)]
    # Recurrentes (30d)
    recurrentes = [{
        "tipo": choice(["AGUA", "ELECTRICIDAD", "LIMPIEZA", "GAS"]),
        "ubicacion": choice(["101", "202", "302", "401", "Lobby"]),
        "count": randint(2, 8),
        "last_seen": _now_str(-randint(60, 600)),
    } for _ in range(10)]
    # SLA por tipo (30d)
    sla_by_type_tipo = {t: round(randint(80, 98) + randint(0, 9)/10, 1)
                        for t in ["AGUA", "ELECTRICIDAD", "LIMPIEZA", "GAS", "OTROS"]}
    # TTR por tipo (min)
    ttr_by_type = {t: randint(20, 120) for t in ["AGUA", "ELECTRICIDAD", "LIMPIEZA", "GAS", "OTROS"]}
    # SLA vs objetivo por tipo (para gráfico agrupado)
    sla_vs_target_tipo = [{"tipo": t, "real": sla_by_type_tipo[t], "objetivo": 90.0}
                          for t in sla_by_type_tipo.keys()]

    return jsonify({
        "avg_ttr_30d": randint(30, 80),
        "snapshot": {"open_total": randint(20, 80), "open_unassigned": randint(0, 10)},
        "sla_by_area": sla_by_area,
        "sla_vs_target": sla_vs_target,
        "ttr_by_area": ttr_by_area,
        "mix_by_area": mix_by_area,
        "tickets_per_day": ts,
        "open_items": open_items,
        "recurrentes": recurrentes,
        "sla_by_type_tipo": sla_by_type_tipo,
        "ttr_by_type": ttr_by_type,
        "sla_vs_target_tipo": sla_vs_target_tipo,
    })

@bp.get("/api/gerencia/sin_asignar")
def api_gerencia_sin_asignar():
    # Tabla "No asignados"
    items = []
    for i in range(10):
        t = _mk_ticket(3000 + i)
        t["assigned_name"] = "(sin asignar)"
        items.append(t)
    return jsonify({"items": items})


# ---------- Recepción ----------
@bp.get("/api/recepcion/kpis")
def api_recepcion_kpis():
    return jsonify({
        "pending": randint(5, 20),
        "in_progress": randint(3, 15),
        "resolved_today": randint(5, 25),
    })

@bp.get("/api/recepcion/list")
def api_recepcion_list():
    estado = (request.args.get("estado") or "").upper()
    limit = int(request.args.get("limit") or 50)
    items = []
    for i in range(limit):
        t = _mk_ticket(4000 + i)
        if estado in {"PENDIENTE", "EN_CURSO", "RESUELTO"}:
            t["estado"] = estado
        # Simula algunos en "PENDIENTE_APROBACION"
        if estado == "PENDIENTE" and i % 5 == 0:
            t["estado"] = "PENDIENTE_APROBACION"
        items.append(t)
    return jsonify({"items": items})

@bp.get("/api/feed/recent")
def api_feed_recent():
    items = []
    verbs = ["creado", "aceptado", "pausado", "resuelto", "reasignado"]
    for i in range(12):
        items.append({
            "at": _now_str(-randint(1, 180)),
            "ticket_id": randint(100, 999),
            "action": choice(verbs),
            "actor": choice(["sistema", "Ana", "Luis", "María"]),
            "area": choice(AREAS),
            "ubicacion": choice(["101", "202", "302", "Lobby", "Spa"]),
            "motivo": choice(["", "", "Pausa operativa", "Duplicado"]),
        })
    return jsonify({"items": items})


# ---------- Supervisor ----------
@bp.get("/api/supervisor/backlog_by_tech")
def api_sup_backlog_by_tech():
    techs = ["Ana", "Luis", "María", "(sin asignar)"]
    vals = [randint(1, 8) for _ in techs]
    return jsonify({"labels": techs, "values": vals})

@bp.get("/api/supervisor/open_by_priority")
def api_sup_open_by_priority():
    labels = PRIOS
    vals = [randint(1, 10) for _ in labels]
    return jsonify({"labels": labels, "values": vals})

@bp.get("/api/supervisor/open_by_type")
def api_sup_open_by_type():
    labels = ["AGUA", "ELECTRICIDAD", "LIMPIEZA", "GAS", "OTROS"]
    vals = [randint(3, 14) for _ in labels]
    return jsonify({"labels": labels, "values": vals})

@bp.get("/api/supervisor/performance_by_user")
def api_sup_performance_by_user():
    rows = [
        {"user": "Ana Pérez", "open_now": 3, "resolved": 18, "sla_pct": 92.5, "ttr_avg_min": 38},
        {"user": "Luis Soto", "open_now": 2, "resolved": 15, "sla_pct": 88.0, "ttr_avg_min": 44},
        {"user": "M. Díaz", "open_now": 4, "resolved": 12, "sla_pct": 79.3, "ttr_avg_min": 51},
        {"user": "(sin asignar)", "open_now": 5, "resolved": 0, "sla_pct": 0.0, "ttr_avg_min": 0},
    ]
    return jsonify({"rows": rows})

@bp.get("/api/supervisor/team_stats")
def api_supervisor_team_stats():
    rows = [
        {"username": "Ana Pérez", "assigned_open": 3, "in_progress": 1, "resolved_30d": 18, "avg_ttr_min": 38, "sla_rate": 92.5},
        {"username": "Luis Soto", "assigned_open": 2, "in_progress": 2, "resolved_30d": 15, "avg_ttr_min": 44, "sla_rate": 88.0},
        {"username": "M. Díaz", "assigned_open": 4, "in_progress": 1, "resolved_30d": 12, "avg_ttr_min": 51, "sla_rate": 79.3},
        {"username": "(sin asignar)", "assigned_open": 5, "in_progress": 0, "resolved_30d": 0, "avg_ttr_min": 0, "sla_rate": 0.0},
    ]
    prio = {"labels": PRIOS, "values": [randint(2, 10) for _ in PRIOS]}
    return jsonify({"rows": rows, "prio": prio})
