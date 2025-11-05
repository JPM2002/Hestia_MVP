from __future__ import annotations
from flask import render_template, session, redirect, url_for, g
from jinja2 import TemplateNotFound
from ...blueprints.gerencia import get_assigned_tickets_for_area, get_assigned_tickets

from . import bp

# ---- optional imports from your codebase; safe fallbacks if missing ----
try:
    from hestia_app.core.rbac import current_org_role  # your tenant/role helper
except Exception:
    def current_org_role():
        u = session.get("user") or {}
        return u.get("role")

try:
    from hestia_app.services.sla import get_global_kpis  # your KPI provider
except Exception:
    def get_global_kpis():
        return {}, {}  # (kpis, charts)

try:
    # Whatever module holds your area/ticket helpers
    from hestia_app.services.assign import (
        get_assigned_tickets, get_assigned_tickets_for_area, default_area_for_user
    )
except Exception:
    def default_area_for_user():  # fallback
        u = session.get("user") or {}
        return (u.get("area") or "MANTENCION").upper()

try:
    from hestia_app.core.area import area_slug  # if you have a canonical slugger
except Exception:
    def area_slug(area: str) -> str:
        return (area or "").strip().lower().replace(" ", "")

try:
    # If you have a data source for supervisor area data
    from hestia_app.services.sla import get_area_data
except Exception:
    def get_area_data(_):
        return {}, []  # (kpis, tickets)


def render_best(template_order: list[str], **ctx):
    """
    Try templates in order; fall back to generic technician dashboard.
    This lets you keep tecnico_* templates living under the 'tecnico' blueprint folder.
    Jinja searches all registered template folders, so cross-blueprint render is OK.
    """
    for name in template_order:
        try:
            return render_template(name, **ctx)
        except TemplateNotFound:
            continue
    return render_template("dashboard_tecnico.html", **ctx)


# ---------------------------- /dashboard ----------------------------
@bp.get("/")
def index():
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login"))

    if user.get("is_superadmin"):
        return redirect(url_for("admin.admin_super"))

    role = (current_org_role() or user.get("role") or "").upper()

    if role == "GERENTE":
        kpis, charts = get_global_kpis()
        return render_template("dashboard_gerente.html", user=user, kpis=kpis, charts=charts)

    if role == "SUPERVISOR":
        kpis, tickets = get_area_data(None)
        return render_template("dashboard_supervisor.html", user=user, kpis=kpis, tickets=tickets)

    if role == "RECEPCION":
        # Canonical Recepción landing handled by recepcion blueprint
        return redirect(url_for("recepcion.recepcion_dashboard"))

    if role == "TECNICO":
        # Canonical Técnico landing handled by tecnico blueprint
        try:
            area = default_area_for_user() or "MANTENCION"
        except Exception:
            area = "MANTENCION"
        slug = area_slug(area)  # "mantencion" | "housekeeping" | "roomservice"
        return redirect(url_for("tecnico.tech_my", slug=slug))

    # Fallback (unknown role) → generic tech page
    tickets = get_assigned_tickets(user["id"])
    return render_template("dashboard_tecnico.html", user=user, tickets=tickets)
