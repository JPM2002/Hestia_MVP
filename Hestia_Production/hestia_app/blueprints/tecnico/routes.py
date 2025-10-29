# app/routes.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from flask import (
    request, session, jsonify, redirect, url_for,
    render_template, abort
)

from . import app
 # ---------------------------- Technician mobile routes ----------------------------
from werkzeug.exceptions import NotFound

def _area_or_404(slug: str) -> str:
    area = area_from_slug(slug)
    if not area:
        raise NotFound()
    return area

@app.get('/tecnico/<slug>/my')
def tech_my(slug):
    if 'user' not in session:
        return redirect(url_for('login'))
    area = _area_or_404(slug)
    tickets = get_assigned_tickets_for_area(session['user']['id'], area)
    template_order = ["tecnico_mobile_list.html", "tickets_mobile.html", "tickets.html"]
    return render_best(template_order,
                       section="my", area=area, slug=slug, user=session['user'],
                       device=g.device, view=g.view_mode, tickets=tickets)

@app.get('/tecnico/<slug>/in-progress')
def tech_in_progress(slug):
    if 'user' not in session:
        return redirect(url_for('login'))
    area = _area_or_404(slug)
    tickets = get_in_progress_tickets_for_user(session['user']['id'], area)
    template_order = ["tecnico_mobile_list.html", "tickets_mobile.html", "tickets.html"]
    return render_best(template_order,
                       section="in_progress", area=area, slug=slug, user=session['user'],
                       device=g.device, view=g.view_mode, tickets=tickets)

@app.get('/tecnico/<slug>/list')
def tech_available(slug):
    if 'user' not in session:
        return redirect(url_for('login'))
    area = _area_or_404(slug)
    only_unassigned = (request.args.get('unassigned', '1') == '1')
    tickets = get_area_available_tickets(area, only_unassigned=only_unassigned)
    template_order = ["tecnico_mobile_list.html", "tickets_mobile.html", "tickets.html"]
    return render_best(template_order,
                       section="available", area=area, slug=slug, user=session['user'],
                       device=g.device, view=g.view_mode, tickets=tickets)

@app.get('/tecnico/<slug>/history')
def tech_history(slug):
    if 'user' not in session:
        return redirect(url_for('login'))
    area = _area_or_404(slug)
    days = request.args.get('days', type=int) or 7
    tickets = get_history_tickets_for_user(session['user']['id'], area, days=days)
    template_order = ["tecnico_mobile_list.html", "tickets_mobile.html", "tickets.html"]
    return render_best(template_order,
                       section="history", area=area, slug=slug, user=session['user'],
                       device=g.device, view=g.view_mode, tickets=tickets, days=days)

@app.get('/tecnico/<slug>/tools')
def tech_tools(slug):
    if 'user' not in session:
        return redirect(url_for('login'))
    area = _area_or_404(slug)

    # Contenido “tools” por área (puedes reemplazar por datos desde DB)
    tools = []
    if area == "HOUSEKEEPING":
        tools = [
            ("Checklist de salida", "#"),
            ("Mapa de carros / pisos", "#"),
            ("Protocolo de textiles", "#"),
            ("Señalética & Seguridad", "#"),
            ("Reportes de pérdida", "#"),
            ("Guía de amenities", "#"),
        ]
    elif area == "MANTENCION":
        tools = [
            ("Guía de circuitos eléctricos", "#"),
            ("Planos y tableros", "#"),
            ("Protocolo lock-out/tag-out", "#"),
            ("Manual de calderas / bombas", "#"),
            ("Inventario de repuestos", "#"),
            ("Ficha de herramientas", "#"),
        ]
    elif area == "ROOMSERVICE":
        tools = [
            ("Menú actual & alérgenos", "#"),
            ("Checklist de bandeja", "#"),
            ("Rutas de entrega por piso", "#"),
            ("Menú nocturno", "#"),
            ("Stock de amenities/extras", "#"),
            ("Protocolos de higiene", "#"),
        ]

    template_order = ["tecnico_mobile_tools.html", "tickets_mobile.html", "tickets.html"]
    return render_best(template_order,
                       area=area, slug=slug, user=session['user'],
                       device=g.device, view=g.view_mode, tools=tools)


@app.post('/api/tech/shift')
def api_tech_shift():
    if 'user' not in session:
        return jsonify({"error": "unauthorized"}), 401
    action = (request.form.get('action') or '').lower()
    now = datetime.now().isoformat()

    if action == 'start':
        session['shift_active'] = True
        session.setdefault('shift_started_at', now)
    elif action == 'pause':
        session['shift_active'] = False
    elif action == 'stop':
        session['shift_active'] = False
        session.pop('shift_started_at', None)
    else:
        return jsonify({"ok": False, "error": "acción inválida"}), 400

    return jsonify({
        "ok": True,
        "active": bool(session.get('shift_active')),
        "started_at": session.get('shift_started_at')
    })

# Housekeeping

# -------------------- HK: Shift (MVP, session-based) --------------------
from datetime import datetime, timezone, timedelta

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

@app.get('/api/hk/shift')
def api_hk_shift_status():
    s = session.get('hk_shift') or {}
    # compute elapsed (not counting paused time for MVP simplicity)
    started = s.get('started_at')
    paused  = s.get('paused', False)
    if started:
        try:
            dt = datetime.fromisoformat(started)
            elapsed = int((datetime.now(timezone.utc) - dt).total_seconds())
        except Exception:
            elapsed = 0
    else:
        elapsed = 0
    return jsonify({
        "active": bool(started) and not s.get('ended_at'),
        "started_at": started,
        "paused": paused,
        "ended_at": s.get('ended_at'),
        "elapsed": elapsed
    })

@app.post('/hk/shift/start')
def hk_shift_start():
    # Al iniciar nuevo turno, limpiamos el log anterior (visible hasta el próximo inicio).
    session['hk_shift_log'] = []
    started = _shift_log_append('START')
    session['hk_shift'] = {
        "started_at": started,
        "paused": False,
        "ended_at": None
    }
    session.modified = True
    return ('', 204)

@app.post('/hk/shift/pause')
def hk_shift_pause():
    s = session.get('hk_shift') or {}
    # Si no hay turno iniciado, nos mantenemos no-op (204) para no romper UI.
    if not s.get('started_at') or s.get('ended_at'):
        return ('', 204)

    s['paused'] = not s.get('paused', False)  # toggle
    _shift_log_append('PAUSE' if s['paused'] else 'RESUME')
    session['hk_shift'] = s
    session.modified = True
    return ('', 204)

@app.post('/hk/shift/end')
def hk_shift_end():
    s = session.get('hk_shift') or {}
    if not s.get('started_at') or s.get('ended_at'):
        return ('', 204)

    ended = _shift_log_append('END')
    s['ended_at'] = ended           # <-- esto es lo que verá el front para "— HH:MM hrs"
    s['paused'] = False
    session['hk_shift'] = s
    session.modified = True
    return ('', 204)

@app.get('/api/hk/shift')
def hk_shift_status():
    state = _shift_state()
    # opcional: exponer el log de sesión por si deseas mostrarlo luego
    state['log'] = session.get('hk_shift_log', [])
    return jsonify(state)

@app.context_processor
def inject_hk_flags():
    return {"HK_SHIFT_ACTIVE": _shift_state()["active"]}



# ---- SHIFT GUARDS ----------------------------------------------------------

def _hk_shift_active() -> bool:
    s = session.get('hk_shift') or {}
    return bool(s.get('started_at')) and not s.get('ended_at') and not s.get('paused', False)

def _shift_active_for_area(area: str | None) -> bool:
    a = (area or '').upper()
    if a == 'HOUSEKEEPING':
        # Turno específico de Housekeeping (vista móvil)
        return _hk_shift_active()
    # Fallback genérico (tecnicos fuera de HK usan /api/tech/shift)
    return bool(session.get('shift_active'))

def _guard_active_shift(area: str | None):
    """Bloquea cualquier operación de ticket si el turno del área no está activo."""
    if not _shift_active_for_area(area):
        return _err_or_redirect(
            'Tu turno está inactivo o en pausa. Inicia tu turno para operar tickets.',
            code=403
        )
    return None



# Maintenance
# Room Service