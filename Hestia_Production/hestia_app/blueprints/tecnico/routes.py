# app/routes.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from flask import (
    request, session, jsonify, redirect, url_for,
    render_template, abort
)

from . import bp as app

# =========================================================
# Area/Slug helpers
# =========================================================
SLUG_TO_AREA = {
    "housekeeping": "HOUSEKEEPING",
    "mantencion": "MANTENCION",
    "roomservice": "ROOMSERVICE",
    "general": "GENERAL",
}

AREA_TO_SLUG = {v: k for k, v in SLUG_TO_AREA.items()}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _prefer_json() -> bool:
    return request.headers.get("X-Requested-With") == "XMLHttpRequest" or \
           "application/json" in request.headers.get("Accept", "")


def _redirect_back(default_endpoint: str = "dashboard"):
    nxt = request.args.get("next")
    if nxt:
        return redirect(nxt)
    try:
        return redirect(request.referrer or url_for(default_endpoint))
    except Exception:
        return redirect(url_for(default_endpoint))


# =========================================================
# DB / Data hooks (replace with your persistence)
# =========================================================
def get_current_user() -> Dict[str, Any]:
    """
    Minimal user stub. Replace with your auth/session user.
    We keep an 'id' and 'role' to match your templates' checks.
    """
    u = session.get("user")
    if not u:
        # Dev default
        u = {"id": 1, "name": "Demo", "role": "TECNICO"}
        session["user"] = u
    return u


def _compute_is_critical(t: Dict[str, Any]) -> bool:
    """
    Decide whether a ticket is critical:
    - urgente priority
    - OR due_at is past
    Adapt this to your business logic.
    """
    prio = (t.get("prioridad") or "").upper()
    if prio == "URGENTE":
        return True
    due = t.get("due_at")
    if due:
        try:
            d = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
            return d < datetime.now(d.tzinfo or timezone.utc)
        except Exception:
            pass
    return False


def _decorate_tickets(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure fields exist and align with templates (dot access works on dicts)."""
    out = []
    for r in rows:
        t = dict(r)  # copy
        t.setdefault("id", 0)
        t.setdefault("area", "GENERAL")
        t.setdefault("prioridad", "MEDIA")
        t.setdefault("estado", "PENDIENTE")
        t.setdefault("detalle", "")
        t.setdefault("ubicacion", "")
        t.setdefault("created_at", _now_iso())
        # Optional timestamps
        t.setdefault("due_at", None)
        t.setdefault("started_at", None)
        t.setdefault("finished_at", None)
        # Derived
        t["is_critical"] = bool(r.get("is_critical", _compute_is_critical(t)))
        out.append(t)
    return out


# Import database functions
try:
    from hestia_app.services.tickets import get_tickets_by_user, update_ticket_state, assign_ticket, get_tickets as get_tickets_from_db
except ImportError:
    # Fallback functions if database is not available
    def get_tickets_by_user(user_id, area=None):
        return []
    def update_ticket_state(ticket_id, new_state, motivo=None, user_id=None):
        return True
    def assign_ticket(ticket_id, user_id, assigned_by=None):
        return True
    def get_tickets_from_db(filters=None):
        return []

# ---------- Replace these with real DB calls ----------
def get_tickets(area: Optional[str] = None,
                estado: Optional[str] = None,
                assigned_to_user_id: Optional[int] = None,
                in_progress_only: bool = False,
                available_only: bool = False,
                history_days: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Load tickets according to filters.
    """
    if assigned_to_user_id:
        rows = get_tickets_by_user(assigned_to_user_id, area)
    else:
        # Use the general get_tickets function
        filters = {}
        if area:
            filters["area"] = area
        if estado:
            filters["estado"] = estado
        rows = get_tickets_from_db(filters)
    
    return _decorate_tickets(rows)
# -------------------------------------------------------


# =========================================================
# Dashboard & generic list
# =========================================================
@app.route("/")
def dashboard():
    # Minimal dashboard – you can replace with your own template
    return render_template("tecnico/tecnico_mobile.html", tickets=get_tickets())


@app.route("/tickets")
def tickets():
    """
    Generic list used by several links in templates: /tickets?estado=PENDIENTE&area=MANTENCION
    We render it with the generic mobile list view.
    """
    estado = request.args.get("estado") or None
    area = request.args.get("area") or None
    slug = AREA_TO_SLUG.get((area or "GENERAL").upper(), "general")

    # Choose section based on estado if you want:
    # - If they ask for 'PENDIENTE' with no user, it's "available"
    # - Otherwise, default to 'available'
    section = "available" if (estado in (None, "", "PENDIENTE", "ASIGNADO")) else "my"

    rows = get_tickets(area=area, estado=estado)
    return render_template(
        "tecnico_mobile_list.html",
        tickets=rows,
        area=(area or "GENERAL").upper(),
        slug=slug,
        section=section
    )


# =========================================================
# Technician views (desktop & mobile hubs)
# =========================================================
@app.route("/tech")
def tech_mobile():
    rows = get_tickets(assigned_to_user_id=get_current_user()["id"])
    return render_template("tecnico/tecnico_mobile.html", tickets=rows)

@app.route("/tech/desktop")
def tech_desktop():
    rows = get_tickets(assigned_to_user_id=get_current_user()["id"])
    return render_template("tecnico/tecnico_desktop.html", tickets=rows)

# Specialized mobile pages
@app.route("/tech/housekeeping")
def tech_housekeeping():
    rows = get_tickets(area="HOUSEKEEPING", assigned_to_user_id=get_current_user()["id"])
    return render_template("tecnico/tecnico_housekeeping_mobile.html", tickets=rows)

@app.route("/tech/mantencion")
def tech_mantencion():
    rows = get_tickets(area="MANTENCION", assigned_to_user_id=get_current_user()["id"])
    return render_template("tecnico/tecnico_mantencion_mobile.html", tickets=rows)

@app.route("/tech/roomservice")
def tech_roomservice():
    rows = get_tickets(area="ROOMSERVICE", assigned_to_user_id=get_current_user()["id"])
    return render_template("tecnico/tecnico_roomservice_mobile.html", tickets=rows)


# =========================================================
# Generic list/tools/history sections per area slug
# (used by links inside the specialized pages)
# =========================================================
def _area_from_slug_or_abort(slug: str) -> str:
    area = SLUG_TO_AREA.get(slug.lower())
    if not area:
        abort(404)
    return area

@app.route("/tech/<slug>/in-progress")
def tech_in_progress(slug: str):
    area = _area_from_slug_or_abort(slug)
    tickets = get_tickets(area=area, in_progress_only=True, assigned_to_user_id=get_current_user()["id"])
    return render_template("tecnico/tecnico_mobile_list.html",
                           tickets=tickets, area=area, slug=slug, section="in_progress")

@app.route("/tech/<slug>/my")
def tech_my(slug: str):
    area = _area_from_slug_or_abort(slug)
    tickets = get_tickets(area=area, assigned_to_user_id=get_current_user()["id"])
    return render_template("tecnico/tecnico_mobile_list.html",
                           tickets=tickets, area=area, slug=slug, section="my")

@app.route("/tech/<slug>/available")
def tech_available(slug: str):
    area = _area_from_slug_or_abort(slug)
    tickets = get_tickets(area=area, available_only=True)
    return render_template("tecnico/tecnico_mobile_list.html",
                           tickets=tickets, area=area, slug=slug, section="available")

@app.route("/tech/<slug>/history")
def tech_history(slug: str):
    area = _area_from_slug_or_abort(slug)
    days = request.args.get("days", type=int) or 7
    tickets = get_tickets(area=area, history_days=days, assigned_to_user_id=get_current_user()["id"])
    return render_template("tecnico/tecnico_mobile_list.html",
                           tickets=tickets, area=area, slug=slug, section="history", days=days)

@app.route("/tech/<slug>/tools")
def tech_tools(slug: str):
    area = _area_from_slug_or_abort(slug)
    # TODO: Replace these with real tool links
    tools = [
        ("Checklist semanal", "#"),
        ("Procedimientos del área", "#"),
        ("Reportes recientes", "#"),
    ]
    return render_template("tecnico/tecnico_mobile_tools.html",
                           tools=tools, area=area, slug=slug)


# =========================================================
# Ticket actions (accept/start/pause/finish/resume)
# =========================================================
def _action_message(endpoint: str) -> str:
    if endpoint.endswith("ticket_accept"): return "✅ Has tomado este ticket."
    if endpoint.endswith("ticket_start"):  return "▶️ Has iniciado el ticket."
    if endpoint.endswith("ticket_pause"):  return "⏸️ Has pausado el ticket."
    if endpoint.endswith("ticket_finish"): return "🏁 Has finalizado el ticket."
    if endpoint.endswith("ticket_resume"): return "⏯️ Has reanudado el ticket."
    return "✔️ Acción realizada."

def _json_or_back(success: bool, msg_ok: str, msg_err: str):
    if _prefer_json():
        if success:
            return jsonify({"ok": True, "message": msg_ok}), 200
        return jsonify({"ok": False, "message": msg_err}), 409
    # Non-AJAX fallback
    return _redirect_back()

@app.post("/ticket/<int:ticket_id>/accept")
def ticket_accept(ticket_id: int):
    ok = update_ticket_state(ticket_id, "ACEPTADO", user_id=get_current_user()["id"])
    return _json_or_back(ok, _action_message("ticket_accept"), "No se pudo tomar el ticket.")

@app.post("/ticket/<int:ticket_id>/start")
def ticket_start(ticket_id: int):
    # Optional: enforce HK shift active for housekeeping
    ok = update_ticket_state(ticket_id, "EN_CURSO", user_id=get_current_user()["id"])
    return _json_or_back(ok, _action_message("ticket_start"), "No se pudo iniciar el ticket.")

@app.post("/ticket/<int:ticket_id>/pause")
def ticket_pause(ticket_id: int):
    motivo = request.form.get("motivo") or ""
    ok = update_ticket_state(ticket_id, "PAUSADO", motivo=motivo, user_id=get_current_user()["id"])
    return _json_or_back(ok, _action_message("ticket_pause"), "No se pudo pausar el ticket.")

@app.post("/ticket/<int:ticket_id>/finish")
def ticket_finish(ticket_id: int):
    ok = update_ticket_state(ticket_id, "RESUELTO", user_id=get_current_user()["id"])
    return _json_or_back(ok, _action_message("ticket_finish"), "No se pudo finalizar el ticket.")

@app.post("/ticket/<int:ticket_id>/resume")
def ticket_resume(ticket_id: int):
    ok = update_ticket_state(ticket_id, "EN_CURSO", user_id=get_current_user()["id"])
    return _json_or_back(ok, _action_message("ticket_resume"), "No se pudo reanudar el ticket.")


# =========================================================
# Housekeeping shift API (used by HK mobile page)
# =========================================================
def _get_hk_shift() -> Dict[str, Any]:
    return session.get("hk_shift") or {}

def _set_hk_shift(data: Dict[str, Any]):
    session["hk_shift"] = data

@app.get("/api/hk/shift")
def api_hk_shift():
    data = _get_hk_shift()
    # Normalize booleans & presence
    active = bool(data.get("started_at") and not data.get("ended_at"))
    paused = bool(data.get("paused"))
    return jsonify({
        "active": active and not paused,
        "paused": paused,
        "started_at": data.get("started_at"),
        "ended_at": data.get("ended_at"),
    })

@app.post("/hk/shift/start")
def hk_shift_start():
    data = _get_hk_shift()
    # Start if not already active; overwrite timestamps for simplicity
    data["started_at"] = _now_iso()
    data["ended_at"] = None
    data["paused"] = False
    _set_hk_shift(data)
    # return 204 (no json body expected by fetch)
    return ("", 204)

@app.post("/hk/shift/pause")
def hk_shift_pause():
    data = _get_hk_shift()
    if not data.get("started_at") or data.get("ended_at"):
        # Can't pause if not active; still return 409 to let UI show warning if needed
        return ("", 409)
    data["paused"] = True
    _set_hk_shift(data)
    return ("", 204)

@app.post("/hk/shift/end")
def hk_shift_end():
    data = _get_hk_shift()
    if not data.get("started_at"):
        return ("", 409)
    data["ended_at"] = _now_iso()
    data["paused"] = False
    _set_hk_shift(data)
    return ("", 204)


# =========================================================
# Ticket creation (placeholder so links don't 404)
# =========================================================
@app.route("/ticket/new")
def ticket_create():
    # You can replace with your form page/template.
    return render_template("tecnico/blank.html") if _template_exists("tecnico/blank.html") else (
        "<h3>Crear ticket</h3><p>(Implementa aquí tu formulario)</p>", 200
    )


# =========================================================
# Small util to check optional templates
# =========================================================
def _template_exists(name: str) -> bool:
    try:
        render_template(name)
        return True
    except Exception:
        return False
