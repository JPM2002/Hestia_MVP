# area.py
from __future__ import annotations
from functools import wraps
from typing import Callable, Optional
from flask import session, redirect, url_for, flash
from .rbac import user_area_codes, current_org_role  # uses rbac wiring
from ..services.db import fetchone
from ..core.rbac import role_effective_perms
from .scope import current_scope

_fetchone: Optional[Callable] = None
_get_scope: Optional[Callable[[], tuple[int | None, int | None]]] = None

AREA_SLUGS = {
    "MANTENCION": "mantencion",
    "HOUSEKEEPING": "housekeeping",
    "ROOMSERVICE": "roomservice",
}

# What does this do?
def init_area(fetchone_fn: Callable | None = None,
              current_scope_fn: Callable[[], tuple[int | None, int | None]] | None = None):
    global _fetchone, _get_scope
    _fetchone = fetchone_fn
    _get_scope = current_scope_fn

def area_slug(area: str | None) -> str:
    if not area: return "general"
    return AREA_SLUGS.get(area.upper(), area.lower().replace(" ", "_"))

def area_from_slug(slug: str | None) -> str | None:
    if not slug:
        return None
    s = slug.strip().lower()
    if s in ("mantencion", "maintenance"):
        return "MANTENCION"
    if s in ("housekeeping", "hk"):
        return "HOUSEKEEPING"
    if s in ("roomservice", "rs", "room_service"):
        return "ROOMSERVICE"
    return None

def default_area_for_user() -> str | None:
    """Prefer OrgUsers.default_area, else first from OrgUserAreas, else Users.area."""
    u = session.get("user"); org_id = session.get("org_id")
    if not u:
        return None
    # explicit default on membership
    r = fetchone("SELECT default_area FROM OrgUsers WHERE org_id=? AND user_id=?", (org_id, u["id"]))
    if r and r.get("default_area"): return r["default_area"]
    # multi-area table
    areas = user_area_codes(org_id, u["id"])
    if areas: return sorted(list(areas))[0]
    # legacy single-area on Users
    return u.get("area")


def _user_has_area(area: str) -> bool:
    if not area:
        return False
    if _get_scope is None:
        return False
    org_id, _ = _get_scope()
    if not org_id:
        return False
    u = session.get('user') or {}
    areas = user_area_codes(org_id, u.get('id'))
    return (area in areas)

def has_perm(code: str) -> bool:
    role = current_org_role()
    if not role:
        return False
    eff = role_effective_perms(role)
    return ("*" in eff) or (code in eff)

def require_perm(code):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not session.get('user'):
                return redirect(url_for('login'))
            if not has_perm(code):
                flash('No tienes permisos para esta acción.', 'error')
                return redirect(url_for('dashboard'))
            return fn(*a, **kw)
        return wrapper
    return deco

def ensure_ticket_area_scope(ticket_row) -> bool:
    """
    Supervisor sólo puede operar si el ticket es de su(s) área(s).
    Gerente y superadmin siempre pueden.
    Técnico no pasa por aquí (tiene sus límites por assigned_to).
    """
    role = current_org_role()
    if role in ("SUPERADMIN", "GERENTE"):
        return True
    if role == "SUPERVISOR":
        org_id, _ = current_scope()
        my_areas = user_area_codes(org_id, session['user']['id'])
        return ticket_row['area'] in my_areas
    # recepcion / tecnico no deberían llegar a acciones restringidas por área aquí
    return False


@app.context_processor
def inject_shift_flags():
    s = session.get('hk_shift') or {}
    hk_active = bool(s.get('started_at')) and not s.get('ended_at') and not s.get('paused', False)
    return {"HK_SHIFT_ACTIVE": hk_active}

