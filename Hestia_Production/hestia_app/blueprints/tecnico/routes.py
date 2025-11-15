from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from ...blueprints.gerencia.routes import (
    get_assigned_tickets_for_area,
    get_in_progress_tickets_for_user,
    get_area_available_tickets,
    get_history_tickets_for_user,
)
from ...blueprints.dashboard.routes import render_best
from ...core.area import area_from_slug
from ...core.errors import _err_or_redirect
from ...core.shift import _shift_log_append, _shift_state

from flask import (
    request, session, jsonify, redirect, url_for,
    render_template, abort, g
)

from . import bp
from werkzeug.exceptions import NotFound


# ---------------------------- Helpers ----------------------------

def _area_or_404(slug: str) -> str:
    area = area_from_slug(slug)
    if not area:
        raise NotFound()
    return area


def _tech_template_order(section: str, slug: str) -> list[str]:
    """
    Returns a list of candidate templates for a technician view.

    Example for slug="housekeeping", section="my":
      1) tecnico_housekeeping_my.html        (area-specific view, with shift bar)
      2) tecnico_mobile_list.html            (generic mobile list)
      3) tickets_mobile.html                 (generic mobile tickets)
      4) tickets.html                        (desktop fallback)
    """
    slug = (slug or "").lower()
    return [
        f"tecnico_{slug}_{section}.html",  # e.g. tecnico_housekeeping_my.html
        "tecnico_mobile_list.html",
        "tickets_mobile.html",
        "tickets.html",
    ]


# ---------------------------- Technician mobile routes ----------------------------

@bp.get('/tecnico/<slug>/my')
def tech_my(slug):
    if 'user' not in session:
        return redirect(url_for('auth.login'))

    area = _area_or_404(slug)
    tickets = get_assigned_tickets_for_area(session['user']['id'], area)

    template_order = _tech_template_order("my", slug)
    return render_best(
        template_order,
        section="my",
        area=area,
        slug=slug,
        user=session['user'],
        device=g.device,
        view=g.view_mode,
        tickets=tickets,
    )


@bp.get('/tecnico/<slug>/in-progress')
def tech_in_progress(slug):
    if 'user' not in session:
        return redirect(url_for('auth.login'))

    area = _area_or_404(slug)
    tickets = get_in_progress_tickets_for_user(session['user']['id'], area)

    template_order = _tech_template_order("in_progress", slug)
    return render_best(
        template_order,
        section="in_progress",
        area=area,
        slug=slug,
        user=session['user'],
        device=g.device,
        view=g.view_mode,
        tickets=tickets,
    )


@bp.get('/tecnico/<slug>/list')
def tech_available(slug):
    if 'user' not in session:
        return redirect(url_for('auth.login'))

    area = _area_or_404(slug)
    only_unassigned = (request.args.get('unassigned', '1') == '1')
    tickets = get_area_available_tickets(area, only_unassigned=only_unassigned)

    template_order = _tech_template_order("available", slug)
    return render_best(
        template_order,
        section="available",
        area=area,
        slug=slug,
        user=session['user'],
        device=g.device,
        view=g.view_mode,
        tickets=tickets,
    )


@bp.get('/tecnico/<slug>/history')
def tech_history(slug):
    if 'user' not in session:
        return redirect(url_for('auth.login'))

    area = _area_or_404(slug)
    days = request.args.get('days', type=int) or 7
    tickets = get_history_tickets_for_user(session['user']['id'], area, days=days)

    template_order = _tech_template_order("history", slug)
    return render_best(
        template_order,
        section="history",
        area=area,
        slug=slug,
        user=session['user'],
        device=g.device,
        view=g.view_mode,
        tickets=tickets,
        days=days,
    )


@bp.get('/tecnico/<slug>/tools')
def tech_tools(slug):
    if 'user' not in session:
        return redirect(url_for('auth.login'))

    area = _area_or_404(slug)

    # Tools list (can stay as you had it)
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

    template_order = _tech_template_order("tools", slug)
    return render_best(
        template_order,
        area=area,
        slug=slug,
        user=session['user'],
        device=g.device,
        view=g.view_mode,
        tools=tools,
    )
