import json
import urllib.request
from flask import current_app

def _wa_post(path: str, payload: dict):
    base = current_app.config.get("WA_NOTIFY_BASE")
    token = current_app.config.get("WA_NOTIFY_TOKEN")
    if not base:
        current_app.logger.info(f"[WA] dry-run POST {path} {payload}")
        return
    url = f"{base}{path}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as _:
            pass
    except Exception as e:
        current_app.logger.warning(f"[WA] notify failed {path}: {e}")

def notify_tech_assignment(to_phone: str, ticket_id: int, area: str, prioridad: str, detalle: str, ubicacion: str | None):
    _wa_post('/notify/tech/assignment', {
        "to_phone": to_phone, "ticket_id": ticket_id, "area": area,
        "prioridad": prioridad, "detalle": detalle or "", "ubicacion": ubicacion
    })

def notify_guest_final(to_phone: str, ticket_id: int, huesped_nombre: str | None):
    _wa_post('/notify/guest/final', {
        "to_phone": to_phone, "ticket_id": ticket_id, "huesped_nombre": huesped_nombre or ""
    })
