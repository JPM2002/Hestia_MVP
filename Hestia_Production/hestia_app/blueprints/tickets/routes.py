# app/routes.py
from __future__ import annotations
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from flask import (
    request, session, jsonify, render_template,
    redirect, url_for, abort
)
from werkzeug.utils import secure_filename

from . import app

# ----------------- Reutiliza tus estados -----------------
try:
    from hestia_app.core.status import OPEN_STATES
except Exception:
    OPEN_STATES = ("PENDIENTE","ASIGNADO","ACEPTADO","EN_CURSO","PAUSADO","DERIVADO")

# ----------------- Helpers -----------------
AREAS        = ["MANTENCION","HOUSEKEEPING","ROOMSERVICE"]
PRIORIDADES  = ["BAJA","MEDIA","ALTA","URGENTE"]
CANALES      = ["recepcion","telefono","whatsapp","app","web"]

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _prefer_json() -> bool:
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("Accept") or "")
    )

def _redirect_back(default_ep="tickets"):
    nxt = request.args.get("next")
    if nxt: return redirect(nxt)
    try:
        return redirect(request.referrer or url_for(default_ep))
    except Exception:
        return redirect(url_for(default_ep))

def _is_mobile() -> bool:
    # override manual: ?view=mobile / ?view=desktop
    v = (request.args.get("view") or "").lower()
    if v == "mobile": return True
    if v == "desktop": return False
    ua = request.headers.get("User-Agent","")
    return "Mobi" in ua or "Android" in ua or "iPhone" in ua

def _get_user() -> Dict[str, Any]:
    u = session.get("user")
    if not u:
        u = {"id": 1, "name": "Demo", "role": "RECEPCION"}  # cambia por tu auth real
        session["user"] = u
    return u

# ----------------- Stubs de datos (reemplaza por tu DB) -----------------
def _compute_is_critical(t: Dict[str, Any]) -> bool:
    prio = (t.get("prioridad") or "").upper()
    if prio == "URGENTE": return True
    due = t.get("due_at")
    if due:
        try:
            d = datetime.fromisoformat(str(due).replace("Z","+00:00"))
            return d < datetime.now(d.tzinfo or timezone.utc)
        except Exception:
            pass
    return False

def _decorate(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        t = {
            "id": r.get("id", 0),
            "area": r.get("area", "GENERAL"),
            "prioridad": r.get("prioridad","MEDIA"),
            "estado": r.get("estado","PENDIENTE"),
            "detalle": r.get("detalle",""),
            "ubicacion": r.get("ubicacion",""),
            "canal": r.get("canal"),
            "created_at": r.get("created_at", _now_iso()),
            "due_at": r.get("due_at"),
            "started_at": r.get("started_at"),
            "finished_at": r.get("finished_at"),
        }
        t["is_critical"] = bool(r.get("is_critical", _compute_is_critical(t)))
        out.append(t)
    return out

def get_tickets(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    TODO: reemplazar con tu consulta real.
    Respeta filtros: q, area, prioridad, estado, period.
    """
    rows: List[Dict[str, Any]] = []
    # ejemplo de fixture si quieres ver algo en UI:
    # rows = [{
    #   "id": 101, "area":"MANTENCION", "prioridad":"ALTA", "estado":"PENDIENTE",
    #   "detalle":"Fuga en baño", "ubicacion":"1203", "canal":"recepcion",
    #   "created_at": _now_iso(), "due_at": (datetime.now(timezone.utc)+timedelta(hours=3)).isoformat()
    # }]
    return _decorate(rows)

def create_ticket(data: Dict[str, Any]) -> int:
    """
    TODO: insert en DB. Retorna ID del ticket.
    """
    return int(datetime.now().timestamp())  # stub

def update_ticket_state(ticket_id: int, new_state: str, **kw) -> bool:
    """
    TODO: update en DB (estado, timestamps, motivo, user_id, etc.)
    """
    return True

# ----------------- Dashboard simple (redirige a tickets móvil/desktop) -----------------
@app.route("/")
def dashboard():
    return redirect(url_for("tickets"))

# ----------------- Tickets: listado (elige mobile/desktop automáticamente) -----------------
@app.route("/tickets", methods=["GET"])
def tickets():
    filters = {
        "q": (request.args.get("q") or "").strip(),
        "area": request.args.get("area") or "",
        "prioridad": request.args.get("prioridad") or "",
        "estado": request.args.get("estado") or "",
        "period": request.args.get("period") or "today",
    }

    rows = get_tickets(filters=filters)
    tpl = "tickets_mobile.html" if _is_mobile() else "tickets.html"
    return render_template(tpl, tickets=rows, filters=filters)

# ----------------- Crear ticket (form) -----------------
@app.route("/ticket/new", methods=["GET","POST"])
def ticket_create():
    if request.method == "GET":
        return render_template(
            "ticket_create.html",
            areas=AREAS,
            prioridades=PRIORIDADES,
            canales=CANALES,
        )

    # POST
    form = request.form
    payload = {
        "area": form.get("area"),
        "prioridad": form.get("prioridad"),
        "canal": form.get("canal_origen") or None,
        "huesped_id": form.get("huesped_id") or None,
        "ubicacion": form.get("ubicacion"),
        "detalle": form.get("detalle"),
        "qr_required": 1 if form.get("qr_required") else 0,
        "estado": "PENDIENTE",
        "created_at": _now_iso(),
        "due_at": None,  # si tienes SLAs, calcúlalo aquí
    }
    # validaciones mínimas
    if not payload["area"] or payload["area"] not in AREAS:
        return render_template("ticket_create.html",
                               areas=AREAS, prioridades=PRIORIDADES, canales=CANALES,
                               error="Área inválida."), 400
    if not payload["prioridad"] or payload["prioridad"] not in PRIORIDADES:
        return render_template("ticket_create.html",
                               areas=AREAS, prioridades=PRIORIDADES, canales=CANALES,
                               error="Prioridad inválida."), 400
    if not payload["ubicacion"] or not payload["detalle"]:
        return render_template("ticket_create.html",
                               areas=AREAS, prioridades=PRIORIDADES, canales=CANALES,
                               error="Ubicación y detalle son obligatorios."), 400

    tid = create_ticket(payload)
    return redirect(url_for("tickets", created=str(tid)))

# ----------------- Acciones de ticket (POST) -----------------
def _json_or_back(ok: bool, ok_msg: str, bad_msg: str):
    if _prefer_json():
        return (jsonify({"ok": ok, "message": ok_msg if ok else bad_msg}),
                200 if ok else 409)
    return _redirect_back("tickets")

@app.post("/ticket/<int:id>/confirm")
def ticket_confirm(id: int):
    ok = update_ticket_state(id, "ASIGNADO", user_id=_get_user()["id"])
    return _json_or_back(ok, "✅ Ticket confirmado.", "No se pudo confirmar el ticket.")

@app.post("/ticket/<int:id>/accept")
def ticket_accept(id: int):
    ok = update_ticket_state(id, "ACEPTADO", user_id=_get_user()["id"])
    return _json_or_back(ok, "✅ Has tomado este ticket.", "No se pudo tomar el ticket.")

@app.post("/ticket/<int:id>/start")
def ticket_start(id: int):
    ok = update_ticket_state(id, "EN_CURSO", user_id=_get_user()["id"])
    return _json_or_back(ok, "▶️ Has iniciado el ticket.", "No se pudo iniciar el ticket.")

@app.post("/ticket/<int:id>/pause")
def ticket_pause(id: int):
    motivo = request.form.get("motivo") or "Pausa"
    ok = update_ticket_state(id, "PAUSADO", motivo=motivo, user_id=_get_user()["id"])
    return _json_or_back(ok, "⏸️ Has pausado el ticket.", "No se pudo pausar el ticket.")

@app.post("/ticket/<int:id>/resume")
def ticket_resume(id: int):
    ok = update_ticket_state(id, "EN_CURSO", user_id=_get_user()["id"])
    return _json_or_back(ok, "⏯️ Has reanudado el ticket.", "No se pudo reanudar el ticket.")

@app.post("/ticket/<int:id>/finish")
def ticket_finish(id: int):
    ok = update_ticket_state(id, "RESUELTO", user_id=_get_user()["id"])
    return _json_or_back(ok, "🏁 Has finalizado el ticket.", "No se pudo finalizar el ticket.")

# ----------------- Página y APIs de Ticket por Voz -----------------
@app.get("/voice")
def voice_page():
    # Renderiza el prototipo de voz
    return render_template("voice_ticket.html")

@app.post("/api/stt")
def api_stt():
    """
    Prototipo: finge transcripción. Reemplaza por integración STT real.
    """
    f = request.files.get("audio")
    if not f:
        return jsonify({"error":"audio requerido"}), 400
    _ = secure_filename(f.filename or "audio.webm")  # podrías guardarlo si quieres
    # Devuelve texto dummy
    return jsonify({"text": "Habitación 1203, la ducha gotea, por favor enviar mantención. Prioridad alta."})

@app.post("/api/extract")
def api_extract():
    """
    Heurística simple para extraer campos desde texto transcrito.
    Reemplaza con LLM cuando quieras.
    """
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").lower()

    area = "MANTENCION"
    if "limpieza" in text or "sabanas" in text or "toallas" in text:
        area = "HOUSEKEEPING"
    elif "menu" in text or "comida" in text or "desayuno" in text:
        area = "ROOMSERVICE"

    prioridad = "MEDIA"
    if "urgente" in text or "inundable" in text or "peligro" in text:
        prioridad = "URGENTE"
    elif "alta" in text:
        prioridad = "ALTA"

    ubic = None
    m = re.search(r"(hab(itaci[oó]n)?\s*)?(\d{3,4})", text)
    if m: ubic = m.group(3)

    detalle = text.strip().capitalize()

    return jsonify({
        "fields": {
            "area": area,
            "prioridad": prioridad,
            "ubicacion": ubic or "",
            "detalle": detalle,
            "canal_origen": "recepcion",
        },
        "confidence_score": 0.72
    })

@app.post("/api/submit")
def api_submit():
    """
    Crea ticket desde payload JSON del prototipo de voz.
    """
    data = request.get_json(force=True, silent=True) or {}
    required = ["area","prioridad","ubicacion","detalle"]
    for k in required:
        if not data.get(k):
            return jsonify({"ok": False, "error": f"Falta {k}"}), 400

    if data["area"] not in AREAS:
        return jsonify({"ok": False, "error": "Área inválida"}), 400
    if data["prioridad"] not in PRIORIDADES:
        return jsonify({"ok": False, "error": "Prioridad inválida"}), 400

    payload = {
        "area": data["area"],
        "prioridad": data["prioridad"],
        "ubicacion": data["ubicacion"],
        "detalle": data["detalle"],
        "canal": data.get("canal_origen"),
        "qr_required": 1 if data.get("qr_required") else 0,
        "huesped_id": data.get("huesped_id"),
        "estado": "PENDIENTE",
        "created_at": _now_iso(),
        "due_at": None,
        "confidence_score": float(data.get("confidence_score") or 0.0),
    }
    tid = create_ticket(payload)
    return jsonify({"ok": True, "ticket_id": tid})
