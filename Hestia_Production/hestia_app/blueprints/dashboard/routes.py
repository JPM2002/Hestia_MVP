from __future__ import annotations
from flask import render_template, session, redirect, url_for, g
from jinja2 import TemplateNotFound

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
    def get_assigned_tickets(user_id):  # fallback
        return []
    def get_assigned_tickets_for_area(user_id, area):  # fallback
        return []
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
        kpis, tickets = get_area_data(None)  # UI puede filtrar por área
        return render_template("dashboard_supervisor.html", user=user, kpis=kpis, tickets=tickets)

    if role == "RECEPCION":
        # Assumes your recepcion blueprint exposes an index at /recepcion -> endpoint "recepcion.index"
        # If your endpoint is different, adjust the url_for target accordingly.
        return redirect(url_for("recepcion.index"))

    # TECNICO / others
    if role == "TECNICO":
        area = default_area_for_user()  # e.g., 'MANTENCION' | 'HOUSEKEEPING' | 'ROOMSERVICE'
        slug = area_slug(area)
        view = getattr(g, "view_mode", "auto")  # 'mobile' | 'desktop' | 'auto'
        tickets = get_assigned_tickets_for_area(user["id"], area)

        # Try specialized templates first, then fall back.
        template_order = [
            f"tecnico_{slug}_{view}.html",  # e.g., tecnico_mantencion_mobile.html
            f"tecnico_{view}.html",         # tecnico_mobile.html / tecnico_desktop.html
            "dashboard_tecnico.html",       # generic fallback in dashboard templates
        ]
        return render_best(
            template_order,
            user=user,
            tickets=tickets,
            area=area,
            device=getattr(g, "device", None),
            view=view,
        )

    # default (non-recognized roles) => generic technician page for now
    tickets = get_assigned_tickets(user["id"])
    return render_template("dashboard_tecnico.html", user=user, tickets=tickets)
