from functools import wraps
from flask import session, redirect, url_for, flash, abort
from ..services.db import fetchone, fetchall
from .status import OPEN_STATES

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
    "RECEPCION": {"ticket.view.area", "ticket.create", "ticket.confirm", "ticket.update"},
    "TECNICO": {
        "ticket.transition.accept", "ticket.transition.start", "ticket.transition.pause",
        "ticket.transition.resume", "ticket.transition.finish",
    },
}

def current_org_role() -> str | None:
    u = session.get("user"); org_id = session.get("org_id")
    if not u: return None
    if u.get("is_superadmin"): return "SUPERADMIN"
    if not org_id: return None
    r = fetchone("SELECT role FROM OrgUsers WHERE org_id=? AND user_id=?", (org_id, u["id"]))
    return r["role"] if r else None

def role_effective_perms(role_code: str) -> set[str]:
    if not role_code: return set()
    base = set(DEFAULT_PERMS.get(role_code, set()))
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
        return base

def has_perm(code: str) -> bool:
    role = current_org_role()
    if not role: return False
    eff = role_effective_perms(role)
    return ("*" in eff) or (code in eff)

def require_perm(code):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not session.get('user'):
                return redirect(url_for('auth.login'))
            if not has_perm(code):
                flash('No tienes permisos para esta acción.', 'error')
                return redirect(url_for('dashboard.dashboard'))
            return fn(*a, **kw)
        return wrapper
    return deco

def is_superadmin() -> bool:
    return bool(session.get('user', {}).get('is_superadmin'))

def user_area_codes(org_id: int, user_id: int) -> set[str]:
    try:
        rows = fetchall("SELECT area_code FROM OrgUserAreas WHERE org_id=? AND user_id=?", (org_id, user_id))
        if rows: return {r['area_code'] for r in rows}
    except Exception:
        pass
    r = fetchone("SELECT default_area FROM OrgUsers WHERE org_id=? AND user_id=?", (org_id, user_id))
    return {r['default_area']} if r and r['default_area'] else set()

def _require_area_manage(area: str):
    u = session.get('user') or {}
    role = (u.get('role') or '').upper()
    if role != 'SUPERVISOR': return
    allowed = (u.get('area') or u.get('team_area') or '').strip().upper()
    incoming = (area or '').strip().upper()
    if not incoming and allowed: return
    if not allowed or incoming != allowed:
        abort(403)
