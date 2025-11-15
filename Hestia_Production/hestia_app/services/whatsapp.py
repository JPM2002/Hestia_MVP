# hestia_app/services/whatsapp.py
import os
import json
import requests

META_TOKEN = os.getenv("WHATSAPP_CLOUD_TOKEN", "")
META_PHONE_ID = os.getenv("WHATSAPP_CLOUD_PHONE_ID", "")


def send_whatsapp(to: str, body: str, tag: str = "WA"):
    """
    Minimal WhatsApp Cloud sender shared by the app.

    - Expects E.164 phone (with or without leading '+').
    - Logs response from Meta so we can see errors in Render logs.
    """
    to = (to or "").strip()
    if not to:
        print(f"[{tag}] WARN: empty 'to'. body={body!r}", flush=True)
        return

    to_clean = to.replace("whatsapp:", "").lstrip("+")
    print(f"[{tag}] OUT → {to_clean}: {body}", flush=True)

    if not META_TOKEN or not META_PHONE_ID:
        print(
            f"[{tag}] WARN: WhatsApp env vars missing: "
            f"WHATSAPP_CLOUD_TOKEN={'set' if META_TOKEN else 'MISSING'}, "
            f"WHATSAPP_CLOUD_PHONE_ID={'set' if META_PHONE_ID else 'MISSING'}",
            flush=True,
        )
        return

    url = f"https://graph.facebook.com/v19.0/{META_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_clean,
        "type": "text",
        "text": {"body": body},
    }

    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=15)
        print(f"[{tag}] RESP {r.status_code}: {r.text}", flush=True)
        if r.status_code >= 300:
            print(f"[{tag}] WARN: WhatsApp send failed", flush=True)
    except Exception as e:
        print(f"[{tag}] EXC: WhatsApp send exception: {e}", flush=True)
