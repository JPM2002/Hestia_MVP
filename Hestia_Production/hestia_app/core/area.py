# area.py
from __future__ import annotations
from typing import Callable, Optional
from flask import session
from .rbac import user_area_codes, current_org_role  # uses rbac wiring

_fetchone: Optional[Callable] = None
_get_scope: Optional[Callable[[], tuple[int | None, int | None]]] = None

AREA_SLUGS = {
    "MANTENCION": "mantencion",
    "HOUSEKEEPING": "housekeeping",
    "ROOMSERVICE": "roomservice",
}

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
    """
    Prefer OrgUsers.default_area, then multi-area mapping, then Users.area (session).
    Requires init_area(fetchone_fn, current_scope_fn) if you want DB-based resolution.
    """
    u = session.get("user")
    if not u:
        return None
    if _fetchone is not None and _get_scope is not None:
        org_id, _ = _get_scope()
        if org_id:
            r = _fetchone("SELECT default_area FROM OrgUsers WHERE org_id=? AND user_id=?", (org_id, u["id"]))
            if r and r.get("default_area"):
                return r["default_area"]
            areas = user_area_codes(org_id, u["id"])
            if areas:
                return sorted(list(areas))[0]
    # fallback to legacy single-area in session
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
