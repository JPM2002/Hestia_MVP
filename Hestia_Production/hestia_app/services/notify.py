import json
import urllib.request
from flask import current_app
import os

# --- WhatsApp notify service (the webhook app you shared) ---
WA_NOTIFY_BASE  = os.getenv('WA_NOTIFY_BASE', 'https://hestia-whatsapp-webhook.onrender.com/').rstrip('/')   # ej: https://hestia-wa.onrender.com
WA_NOTIFY_TOKEN = os.getenv('WA_NOTIFY_TOKEN', '200220022002')              # must match INTERNAL_NOTIFY_TOKEN there


def _wa_post(path: str, payload: dict):
    """Best-effort call to WA notify service; safe no-op if not configured."""
    if not WA_NOTIFY_BASE:
        print(f"[WA] (dry-run) POST {path} {payload}", flush=True)
        return
    try:
        url = f"{WA_NOTIFY_BASE}{path}"
        headers = {'Content-Type': 'application/json'}
        if WA_NOTIFY_TOKEN:
            headers['Authorization'] = f'Bearer {WA_NOTIFY_TOKEN}'
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        if r.status_code >= 300:
            print(f"[WA] notify {path} failed {r.status_code}: {r.text}", flush=True)
    except Exception as e:
        print(f"[WA] notify exception {path}: {e}", flush=True)

def _notify_tech_assignment(to_phone: str, ticket_id: int, area: str, prioridad: str, detalle: str, ubicacion: str | None):
    _wa_post('/notify/tech/assignment', {
        "to_phone": to_phone,
        "ticket_id": ticket_id,
        "area": area,
        "prioridad": prioridad,
        "detalle": detalle or "",
        "ubicacion": ubicacion
    })

def _notify_guest_final(to_phone: str, ticket_id: int, huesped_nombre: str | None):
    _wa_post('/notify/guest/final', {
        "to_phone": to_phone,
        "ticket_id": ticket_id,
        "huesped_nombre": huesped_nombre or ""
    })