# hestia_app/core/rbac.py
from functools import wraps
from flask import session, redirect, url_for, flash, abort
from ..services.db import fetchone, fetchall

DEFAULT_PERMS = {
    "SUPERADMIN": {"*"},
    "GERENTE": {
        "ticket.view.all", "ticket.assign", "ticket.confirm", "ticket.create",
        "ticket.transition.accept", "ticket.transition.start", "ticket.transition.pause",
        "ticket.transition.resume", "ticket.transition.finish",
    },
    "SUPERVISOR": {
        "ticket.view.all",
        "ticket.view.area", "ticket.assign", "ticket.confirm", "ticket.create",
        "ticket.transition.accept", "ticket.transition.start", "ticket.transition.pause",
        "ticket.transition.resume", "ticket.transition.finish",
    },
    "RECEPCION": {
        "ticket.view.area", "ticket.create", "ticket.confirm", "ticket.update"
    },
    "TECNICO": {
        "ticket.transition.accept", "ticket.transition.start", "ticket.transition.pause",
        "ticket.transition.resume", "ticket.transition.finish","ticket.view.area"
    },
}

# All of these values exist on the table called permissions in the DB

def current_org_role() -> str | None:
    """Return the OrgUsers.role for this user in current org, or SUPERADMIN."""
    u = session.get('user'); org_id = session.get('org_id')
    if not u:
        return None
    if u.get('is_superadmin'):
        return "SUPERADMIN"
    if not org_id:
        return None
    r = fetchone("SELECT role FROM OrgUsers WHERE org_id=? AND user_id=?", (org_id, u['id']))
    return r['role'] if r else None

def role_effective_perms(role_code: str) -> set[str]:
    """
    Resolve role -> permissions. We always include DEFAULT_PERMS as a base,
    and then union any DB-defined permissions (RolePermissions + Roles.inherits_code).
    """
    if not role_code:
        return set()

    base = set(c.get(role_code, set()))
    try:
        perms = set()
        seen = set()
        rc = role_code
        while rc and rc not in seen:
            seen.add(rc)
            for r in fetchall("SELECT perm_code, allow FROM RolePermissions WHERE role_code=?", (rc,)):
                if bool(r.get("allow", 1)):
                    perms.add(r["perm_code"])
            parent = fetchone("SELECT inherits_code FROM Roles WHERE code=?", (rc,))
            rc = parent["inherits_code"] if parent else None
        return base | perms
    except Exception:
        # If RBAC tables are missing, stick to defaults
        return base

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
                return redirect(url_for('auth.login'))
            if not has_perm(code):
                flash('No tienes permisos para esta acción.', 'error')
                return redirect(url_for('dashboard.index'))
            return fn(*a, **kw)
        return wrapper
    return deco

def is_superadmin() -> bool:
    return bool(session.get('user', {}).get('is_superadmin'))

def user_area_codes(org_id: int, user_id: int) -> set[str]:
    """
    Áreas asignadas al usuario en la org (multi-área).
    Fallback a OrgUsers.default_area si OrgUserAreas no existe.
    """
    try:
        rows = fetchall("SELECT area_code FROM OrgUserAreas WHERE org_id=? AND user_id=?", (org_id, user_id))
        if rows:
            return {r['area_code'] for r in rows}
    except Exception:
        pass
    # fallback
    r = fetchone("SELECT default_area FROM OrgUsers WHERE org_id=? AND user_id=?", (org_id, user_id))
    return {r['default_area']} if r and r['default_area'] else set()

def _require_area_manage(area: str):
    """
    Supervisors may only act within their own area. Raises 403 otherwise.
    Safe if area is None/empty; will try to infer from session.
    """
    u = session.get('user') or {}
    role = (u.get('role') or '').upper()

    # Only constrain supervisors
    if role != 'SUPERVISOR':
        return

    # Normalize allowed area from session (support several possible keys)
    allowed = (u.get('area') or u.get('team_area') or '').strip().upper()
    incoming = (area or '').strip().upper()

    # If no area was passed, assume supervisor’s own area
    if not incoming and allowed:
        return  # allow: the caller will use their own area

    if not allowed or incoming != allowed:
        abort(403)
