# rbac.py
from __future__ import annotations
from functools import wraps
from typing import Callable, Optional, Set
from flask import session, redirect, url_for, flash, abort

# --- Injected DB/accessors (set by init_rbac_helpers) ---
_fetchone: Optional[Callable] = None
_fetchall: Optional[Callable] = None
_get_scope: Optional[Callable[[], tuple[int | None, int | None]]] = None  # returns (org_id, hotel_id)

# ---------------------------- RBAC defaults (safe fallback) ----------------------------
DEFAULT_PERMS = {
    "SUPERADMIN": {"*"},
    "GERENTE": {
        "ticket.view.all", "ticket.assign", "ticket.confirm", "ticket.create",
        "ticket.transition.accept", "ticket.transition.start", "ticket.transition.pause",
        "ticket.transition.resume", "ticket.transition.finish",
    },
    "SUPERVISOR": {
        "ticket.view.area", "ticket.assign", "ticket.confirm", "ticket.create",
        "ticket.transition.accept", "ticket.transition.start", "ticket.transition.pause",
        "ticket.transition.resume", "ticket.transition.finish",
    },
    "RECEPCION": {
        "ticket.view.area", "ticket.create", "ticket.confirm", "ticket.update",
    },
    "TECNICO": {
        "ticket.transition.accept", "ticket.transition.start", "ticket.transition.pause",
        "ticket.transition.resume", "ticket.transition.finish",
    },
}

def init_rbac_helpers(app=None,
                      fetchone_fn: Callable | None = None,
                      fetchall_fn: Callable | None = None,
                      current_scope_fn: Callable[[], tuple[int | None, int | None]] | None = None):
    """
    Wire DB helpers so RBAC can read roles/permissions if tables exist.
    Keep 'app' optional to satisfy `from .core.rbac import init_rbac_helpers`.
    """
    global _fetchone, _fetchall, _get_scope
    _fetchone = fetchone_fn
    _fetchall = fetchall_fn
    _get_scope = current_scope_fn

    # Optional: expose has_perm in templates
    if app is not None:
        app.jinja_env.globals.setdefault("has_perm", has_perm)

# --------------- Core resolvers ---------------

def current_org_role() -> str | None:
    u = session.get('user')
    if not u:
        return None
    if u.get('is_superadmin'):
        return "SUPERADMIN"
    if _get_scope is None or _fetchone is None:
        # No DB wiring yet
        return u.get('role')
    org_id, _ = _get_scope()
    if not org_id:
        return None
    r = _fetchone("SELECT role FROM OrgUsers WHERE org_id=? AND user_id=?", (org_id, u['id']))
    return r['role'] if r else None

def role_effective_perms(role_code: str | None) -> Set[str]:
    if not role_code:
        return set()
    base = set(DEFAULT_PERMS.get(role_code, set()))
    # If DB is not wired, stick to defaults
    if _fetchall is None:
        return base
    try:
        perms = set()
        seen = set()
        rc = role_code
        while rc and rc not in seen:
            seen.add(rc)
            for r in _fetchall("SELECT perm_code, allow FROM RolePermissions WHERE role_code=?", (rc,)):
                if bool(r.get("allow", 1)):
                    perms.add(r["perm_code"])
            parent = _fetchone("SELECT inherits_code FROM Roles WHERE code=?", (rc,))
            rc = parent["inherits_code"] if parent else None
        return base | perms
    except Exception:
        return base

def user_area_codes(org_id: int, user_id: int) -> set[str]:
    # Return multi-area mapping if table exists, else fallback
    if _fetchall is None or _fetchone is None:
        # Fall back to user single-area in session
        u = session.get("user") or {}
        return {u.get("area")} if u.get("area") else set()
    try:
        rows = _fetchall("SELECT area_code FROM OrgUserAreas WHERE org_id=? AND user_id=?", (org_id, user_id))
        if rows:
            return {r['area_code'] for r in rows}
    except Exception:
        pass
    r = _fetchone("SELECT default_area FROM OrgUsers WHERE org_id=? AND user_id=?", (org_id, user_id))
    return {r['default_area']} if r and r['default_area'] else set()

def has_perm(code: str) -> bool:
    role = current_org_role()
    if not role:
        return False
    eff = role_effective_perms(role)
    return ("*" in eff) or (code in eff)

def require_perm(code: str):
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

def _require_area_manage(area: str):
    """
    Supervisors may only act within their own area (exact match).
    Gerentes/Superadmin pass through.
    """
    u = session.get('user') or {}
    role = (u.get('role') or '').upper()
    if role != 'SUPERVISOR':
        return
    allowed = (u.get('area') or u.get('team_area') or '').strip().upper()
    incoming = (area or '').strip().upper()
    if not incoming and allowed:
        return
    if not allowed or incoming != allowed:
        abort(403)

def ensure_ticket_area_scope(ticket_row) -> bool:
    """
    True if the current user is allowed to operate on ticket's area.
    """
    role = current_org_role()
    if role in ("SUPERADMIN", "GERENTE"):
        return True
    if role == "SUPERVISOR":
        if _get_scope is None:
            return False
        org_id, _ = _get_scope()
        if org_id is None:
            return False
        areas = user_area_codes(org_id, session['user']['id'])
        return ticket_row['area'] in areas
    return False
