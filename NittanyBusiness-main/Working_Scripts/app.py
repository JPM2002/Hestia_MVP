import os, re, json, time
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any

import requests, tempfile, mimetypes, os
from openai import OpenAI


from flask import Flask, request, jsonify

# ----------------------------- DB: Postgres with SQLite fallback -----------------------------
import sqlite3 as sqlite
pg = None
pg_extras = None
try:
    import psycopg2 as pg
    import psycopg2.extras as pg_extras
except Exception:
    pg = None

from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# ----------------------------- Config -----------------------------

# ----------------------------- Copy (5-star tone) -----------------------------
COPY = {
    "greet":
        "¡Hola! 👋 Soy tu asistente. Puedo ayudarte con mantención, housekeeping o room service.\n"
        "Para empezar, ¿me dices *tu nombre*? 🙂",
    "ask_room":
        "Gracias, *{name}*. ¿Cuál es tu *número de habitación*? 🏨",
    "ask_detail_after_room":
        "Perfecto. Ahora cuéntame qué ocurrió. Puedes *enviar un audio* o escribir el detalle. 🎤✍️",
    "nudge_detail_no_name":
        "¡Hola! Antes de atenderte, ¿me dices *tu nombre*? Luego me envías un audio o texto con el detalle. 🙂",
    "nudge_detail_no_room":
        "Gracias, *{name}*. Me falta el *número de habitación*. ¿Cuál es? 🏨",
    "ack_smalltalk":
        "¡Aquí estoy! 🙌 Para ayudarte, primero necesito *tu nombre* y *habitación*.",
    "ack_got_detail_wait_confirm":
        "📝 Voy a registrar tu solicitud, ¿es correcto?\n\n{summary}\n\n"
        "Responde *SI* para confirmar o *NO* para editar.\n"
        "_Comandos rápidos_: AREA / PRIORIDAD / HAB / DETALLE …",
    "ask_name":
        "🌟 ¡Bienvenido/a! ¿Con quién tengo el gusto? 😊\n"
        "Indícame *tu nombre* y luego *número de habitación* para poder ayudarte.",
    "confirm_draft":
        "📝 Voy a registrar tu solicitud, ¿es correcto?\n\n{summary}\n\n"
        "Responde *SI* para confirmar o *NO* para editar.\n"
        "_Comandos rápidos_: AREA / PRIORIDAD / HAB / DETALLE …",
    "need_more_for_ticket":
        "🙏 Me faltan algunos datos para crear el ticket. ¿Podrías enviarme el *detalle* o *habitación*, por favor?",
    "edit_help":
        "Perfecto ✍️ Puedes corregir usando:\n"
        "• AREA <mantención | housekeeping | roomservice>\n"
        "• PRIORIDAD <urgente | alta | media | baja>\n"
        "• HAB <número>\n"
        "• DETALLE <texto>\n"
        "Cuando esté listo, responde *SI* para confirmarlo.",
    "ticket_created":
        "✅ ¡Gracias, {guest}! Hemos registrado el ticket #{ticket_id}.\n"
        "Nuestro equipo ya está atendiendo tu solicitud. 🌟",
    "guest_final":
        "✨ ¡Listo, {name}! Tu solicitud (ticket #{ticket_id}) ha sido *resuelta*.\n"
        "Gracias por confiar en nosotros. Si necesitas algo más, aquí estaré. 💫",
    "tech_assignment":
        "{prefix}🔔 Nuevo ticket #{ticket_id}\n"
        "Área: {area}\nPrioridad: {prioridad}\nHabitación: {habitacion}\n"
        "Detalle: {detalle}\n{link}"
}



def txt(key: str, **kwargs) -> str:
    s = COPY.get(key, "")
    try:
        return s.format(**kwargs)
    except Exception:
        return s
    

# Internal A→B auth (optional, used by /notify/*)
INTERNAL_NOTIFY_TOKEN = os.getenv("INTERNAL_NOTIFY_TOKEN", "")

# --- Auto-asignación / Notificaciones a técnicos ---
ASSIGNEE_MANTENCION_PHONE = os.getenv("ASSIGNEE_MANTENCION_PHONE", "+56956326272")  # Andrés
ASSIGNEE_HOUSEKEEPING_PHONE = os.getenv("ASSIGNEE_HOUSEKEEPING_PHONE", "+56983001018")  # Pedro
ASSIGNEE_ROOMSERVICE_PHONE = os.getenv("ASSIGNEE_ROOMSERVICE_PHONE", "")  # opcional

# Si quieres pegar link al ticket en el mensaje:
APP_BASE_URL = os.getenv("APP_BASE_URL", "")  # ej: "https://hestia-mvp.onrender.com"

# (Opcional) asignar en DB al crear (además de notificar)
AUTO_ASSIGN_ON_CREATE = os.getenv("AUTO_ASSIGN_ON_CREATE", "false").lower() in ("1","true","yes","y")


PORT = int(os.getenv("PORT", "5000"))  # <- default 5000
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SQLITE_PATH = os.getenv("DATABASE_PATH", "hestia_V2.db")

# Org/Hotel fallback (used when creating tickets)
ORG_ID_DEFAULT = int(os.getenv("DEMO_ORG_ID", "1"))
HOTEL_ID_DEFAULT = int(os.getenv("DEMO_HOTEL_ID", "1"))

# WhatsApp Cloud (outbound)
META_TOKEN = os.getenv("WHATSAPP_CLOUD_TOKEN", "")
META_PHONE_ID = os.getenv("WHATSAPP_CLOUD_PHONE_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "my-verify-token")

# Optional: transcription provider (stub unless set)
TRANSCRIBE_PROVIDER = os.getenv("TRANSCRIBE_PROVIDER", "none").lower()

# SLA mins fallback (used if SLARules table missing)
SLA_FALLBACK = {
    ("MANTENCION", "URGENTE"): 30, ("MANTENCION", "ALTA"): 90, ("MANTENCION", "MEDIA"): 240, ("MANTENCION", "BAJA"): 480,
    ("HOUSEKEEPING", "URGENTE"): 20, ("HOUSEKEEPING", "ALTA"): 60, ("HOUSEKEEPING", "MEDIA"): 120, ("HOUSEKEEPING", "BAJA"): 240,
    ("ROOMSERVICE", "URGENTE"): 20, ("ROOMSERVICE", "ALTA"): 45, ("ROOMSERVICE", "MEDIA"): 60, ("ROOMSERVICE", "BAJA"): 90,
}

# Idempotency cache for WhatsApp message IDs (cleared on process restart)
PROCESSED_WAMIDS = set()

# In-memory conversational state for WhatsApp confirmation
PENDING: Dict[str, Dict[str, Any]] = {}
SESSION_TTL = 15 * 60  # seconds

app = Flask(__name__)

def _meta_get_media_url(media_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Given a WhatsApp media id, return a downloadable URL and mime_type.
    Requires Authorization: Bearer <WHATSAPP_CLOUD_TOKEN>.
    """
    try:
        url = f"https://graph.facebook.com/v19.0/{media_id}"
        headers = {"Authorization": f"Bearer {META_TOKEN}"}
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
        return data.get("url"), data.get("mime_type")
    except Exception as e:
        print(f"[WARN] _meta_get_media_url failed: {e}", flush=True)
        return None, None

# ----------------------------- Conversation helpers -----------------------------
GREETING_WORDS = [
    "hola", "buenas", "buen día", "buen dia", "buenas tardes", "buenas noches",
    "hey", "hi", "hello", "qué tal", "que tal", "necesito ayuda", "ayuda", "consulta"
]

def is_greeting_or_help(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    return any(w in t for w in GREETING_WORDS)

def maybe_name(text: str) -> Optional[str]:
    """
    Very naive: if user writes 1–4 words without digits and without a command,
    treat it as a possible name (“Juan Pérez”, “Carla”).
    """
    t = (text or "").strip()
    if not t or looks_like_command(t) or any(ch.isdigit() for ch in t):
        return None
    parts = t.split()
    if 1 <= len(parts) <= 4:
        return t
    return None

def maybe_room(text: str) -> Optional[str]:
    """Find 3–4 digit room number anywhere in the text."""
    return guess_room(text or "")

def ensure_summary_in_session(s: Dict[str, Any]) -> str:
    """Render confirmation summary from session “draft”."""
    area = s.get("area") or "MANTENCION"
    prio = s.get("prioridad") or "MEDIA"
    room = s.get("room")
    detalle = s.get("detalle") or ""
    return _render_summary(area, prio, room, detalle)


# ----------------------------- DB helpers -----------------------------
def _only_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")

def _find_user_id_by_phone(phone: str) -> Optional[int]:
    """
    Try to find a users.id by matching digits-only phone.
    Works in both PG/SQLite (we normalize in Python).
    """
    try:
        # pull minimal set
        rows = []
        if using_pg():
            rows = fetchall("SELECT id, telefono FROM users WHERE activo = TRUE", ())
        else:
            rows = fetchall("SELECT id, telefono FROM users WHERE activo = 1", ())

        target = _only_digits(phone)
        for r in rows or []:
            if _only_digits(r.get("telefono")) == target:
                return int(r["id"])
    except Exception as e:
        print(f"[WARN] _find_user_id_by_phone failed: {e}", flush=True)
    return None

def _ticket_link(ticket_id: int) -> str:
    if APP_BASE_URL:
        base = APP_BASE_URL.rstrip("/")
        return f"{base}/tickets/{ticket_id}"
    return ""

def _notify_tech(phone: str, ticket_id: int, area: str, prioridad: str, detalle: str, ubicacion: Optional[str]):
    summary = (
        f"🔔 Nuevo ticket #{ticket_id}\n"
        f"Área: {area}\n"
        f"Prioridad: {prioridad}\n"
        f"Ubicación: {ubicacion or '—'}\n"
        f"Detalle: {detalle or '—'}"
    )
    link = _ticket_link(ticket_id)
    if link:
        summary += f"\nAbrir: {link}"
    send_whatsapp(phone, summary)

def _auto_assign_and_notify(ticket_id: int, area: str, prioridad: str, detalle: str, ubicacion: Optional[str]):
    """
    - Choose a technician by area (phones from env).
    - (Optional) Assign in DB to that user if we can match by phone.
    - Always WhatsApp the technician with summary.
    - Log TicketHistory 'ASIGNADO_AUTO' when assigned.
    """
    area_u = (area or "").upper()
    to_phone = None

    if area_u == "MANTENCION":
        to_phone = ASSIGNEE_MANTENCION_PHONE or None
    elif area_u == "HOUSEKEEPING":
        to_phone = ASSIGNEE_HOUSEKEEPING_PHONE or None
    elif area_u == "ROOMSERVICE":
        to_phone = ASSIGNEE_ROOMSERVICE_PHONE or None

    if not to_phone:
        return  # no mapping → do nothing

    # Optional DB assignment
    assigned_user_id = None
    if AUTO_ASSIGN_ON_CREATE:
        uid = _find_user_id_by_phone(to_phone)
        if uid:
            try:
                if using_pg():
                    execute("UPDATE Tickets SET assigned_to=%s WHERE id=%s", (uid, ticket_id))
                    execute(
                        "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (%s,%s,%s,%s,%s)",
                        (ticket_id, None, "ASIGNADO_AUTO", f"area={area_u}", datetime.now().isoformat())
                    )
                else:
                    execute("UPDATE Tickets SET assigned_to=? WHERE id=?", (uid, ticket_id))
                    execute(
                        "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (?,?,?,?,?)",
                        (ticket_id, None, "ASIGNADO_AUTO", f"area={area_u}", datetime.now().isoformat())
                    )
                assigned_user_id = uid
            except Exception as e:
                print(f"[WARN] auto-assign failed: {e}", flush=True)

    # Notify tech by WhatsApp
    prefix = "📌 Asignado a ti.\n" if assigned_user_id else ""
    body = (
        f"{prefix}🔔 Nuevo ticket #{ticket_id}\n"
        f"Área: {area}\n"
        f"Prioridad: {prioridad}\n"
        f"Ubicación: {ubicacion or '—'}\n"
        f"Detalle: {detalle or '—'}"
    )
    link = _ticket_link(ticket_id)
    if link:
        body += f"\nAbrir: {link}"
    send_whatsapp(to_phone, body)


def _dsn_with_params(dsn: str, extra: dict | None = None) -> str:
    if not dsn:
        return dsn
    parts = urlsplit(dsn)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q.setdefault("sslmode", "require")
    q.setdefault("connect_timeout", "5")
    if extra:
        q.update(extra)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))

def using_pg() -> bool:
    return bool(DATABASE_URL and pg is not None)

def db_conn():
    if using_pg():
        dsn = _dsn_with_params(DATABASE_URL)
        return pg.connect(dsn)
    conn = sqlite.connect(SQLITE_PATH, check_same_thread=False)
    conn.row_factory = sqlite.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
    except Exception:
        pass
    return conn

def fetchone(sql: str, params=()):
    conn = db_conn()
    try:
        if using_pg():
            cur = conn.cursor(cursor_factory=pg_extras.RealDictCursor)
            cur.execute(sql, params)
            row = cur.fetchone()
            conn.commit()
            cur.close()
            return row
        else:
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else None
    finally:
        try: conn.close()
        except Exception: pass

def execute(sql: str, params=()):
    conn = db_conn()
    try:
        if using_pg():
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            cur.close()
        else:
            conn.execute(sql, params)
            conn.commit()
    finally:
        try: conn.close()
        except Exception: pass

def insert_and_get_id(sql: str, params=()):
    conn = db_conn()
    try:
        if using_pg():
            sql2 = sql if "RETURNING" in sql.upper() else sql.rstrip().rstrip(";") + " RETURNING id"
            cur = conn.cursor()
            cur.execute(sql2, params)
            new_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
            return int(new_id)
        else:
            cur = conn.execute(sql, params)
            conn.commit()
            return int(cur.lastrowid)
    finally:
        try: conn.close()
        except Exception: pass

def _table_has_column_sqlite(table: str, col: str) -> bool:
    try:
        conn = db_conn()
        cur = conn.execute(f"PRAGMA table_info({table});")
        cols = [row[1].lower() for row in cur.fetchall()]
        conn.close()
        return col.lower() in cols
    except Exception:
        return False

def _table_has_column_pg(table: str, col: str) -> bool:
    try:
        r = fetchone(
            "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
            (table.lower(), col.lower())
        ) if using_pg() else None
        return bool(r)
    except Exception:
        return False

def table_has_column(table: str, col: str) -> bool:
    return _table_has_column_pg(table, col) if using_pg() else _table_has_column_sqlite(table, col)


# ----------------------------- NLP-ish parsing helpers -----------------------------
AREA_KEYWORDS = {
    "MANTENCION": ["ducha", "baño", "grifo", "llave", "aire", "ac", "fuga", "luz", "enchufe", "televisor", "tv", "puerta", "ventana", "calefaccion", "calefacción"],
    "HOUSEKEEPING": ["toalla", "sábana", "sabana", "almohada", "limpieza", "aseo", "basura", "amenities", "shampoo", "jabón", "sabanas"],
    "ROOMSERVICE": ["pedido", "hamburguesa", "sandwich", "desayuno", "cena", "comida", "room service", "cerveza", "vino", "agua"],
}
ROOM_RE = re.compile(r"\b(\d{3,4})\b")

def guess_area(text: str) -> str:
    t = (text or "").lower()
    for area, kws in AREA_KEYWORDS.items():
        if any(k in t for k in kws):
            return area
    return "MANTENCION"

def guess_priority(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ["urgente", "rápido", "rapido", "inundación", "fuga", "incendio", "peligro"]):
        return "URGENTE"
    if any(k in t for k in ["alto", "grave", "importante"]):
        return "ALTA"
    if any(k in t for k in ["normal", "cuando puedan", "si pueden"]):
        return "MEDIA"
    return "MEDIA"

def guess_room(text: str) -> Optional[str]:
    m = ROOM_RE.search(text or "")
    return m.group(1) if m else None

def clean_text(s: Optional[str]) -> str:
    return (s or "").strip()

# ----------------------------- Command detection -----------------------------
COMMAND_PREFIXES = ("AREA ", "PRIORIDAD ", "HAB ", "ROOM ", "DETALLE ", "SI", "SÍ", "YES", "Y", "NO", "N")

def looks_like_command(s: str) -> bool:
    u = (s or "").strip().upper()
    return any(u.startswith(p) for p in COMMAND_PREFIXES)


# ----------------------------- SLA helpers -----------------------------
def sla_minutes(area: str, prioridad: str) -> Optional[int]:
    try:
        if using_pg():
            r = fetchone("SELECT max_minutes FROM SLARules WHERE area=%s AND prioridad=%s", (area, prioridad))
        else:
            r = fetchone("SELECT max_minutes FROM SLARules WHERE area=? AND prioridad=?", (area, prioridad))
        if r and r.get("max_minutes") is not None:
            return int(r["max_minutes"])
    except Exception:
        pass
    return SLA_FALLBACK.get((area, prioridad))

def compute_due(created_at: datetime, area: str, prioridad: str) -> Optional[datetime]:
    mins = sla_minutes(area, prioridad)
    return created_at + timedelta(minutes=mins) if mins else None

# ----------------------------- Transcription (stub) -----------------------------
def transcribe_audio(audio_url: str) -> str:
    """
    Downloads WhatsApp audio (auth header required), sends it to OpenAI Whisper,
    returns transcript text. Falls back to "" if anything fails.
    """
    if TRANSCRIBE_PROVIDER != "openai":
        return f"[audio recibido: {audio_url}]"

    if not audio_url:
        return ""

    # always attach Meta token if we have it; Cloud media links require it
    headers = {}
    if META_TOKEN:
        headers["Authorization"] = f"Bearer {META_TOKEN}"

    tmp_path = None
    try:
        # --- download audio ---
        r = requests.get(audio_url, headers=headers, timeout=60)
        if r.status_code == 401 or r.status_code == 403:
            print(f"[WARN] media download unauthorized ({r.status_code}) -> {audio_url}", flush=True)
            return ""  # nothing to transcribe

        r.raise_for_status()
        content = r.content
        mime = (r.headers.get("Content-Type") or "audio/ogg").lower()

        # choose a safe extension for Whisper
        ext = ".ogg"
        if "mp4" in mime or "aac" in mime or "m4a" in mime:
            ext = ".m4a"
        elif "mpeg" in mime or "mp3" in mime:
            ext = ".mp3"
        elif "wav" in mime:
            ext = ".wav"

        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as f:
            f.write(content)
            tmp_path = f.name

        # --- transcribe with OpenAI Whisper ---
        client = OpenAI()  # uses OPENAI_API_KEY
        with open(tmp_path, "rb") as fh:
            resp = client.audio.transcriptions.create(
                model="whisper-1",
                file=fh,
                temperature=0,
                # language="es",  # uncomment if you want to force Spanish
            )
        txt = getattr(resp, "text", "") or ""
        return txt.strip()

    except Exception as e:
        print(f"[WARN] transcription failed: {e}", flush=True)
        return ""
    finally:
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

# ----------------------------- WhatsApp outbound (Cloud API) -----------------------------
def send_whatsapp(to: str, body: str):
    """
    If META creds are missing, just print to console.
    Cloud API expects 'to' in E.164 digits, no leading '+'.
    """
    to_clean = to.replace("whatsapp:", "").lstrip("+")
    msg = f"[OUT → {to_clean}] {body}"
    print(msg, flush=True)

    if not (META_TOKEN and META_PHONE_ID):
        return

    try:
        import requests
        url = f"https://graph.facebook.com/v19.0/{META_PHONE_ID}/messages"
        headers = {"Authorization": f"Bearer {META_TOKEN}", "Content-Type": "application/json"}
        payload = {
            "messaging_product": "whatsapp",
            "to": to_clean,
            "type": "text",
            "text": {"body": body}
        }
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=15)
        if r.status_code >= 300:
            print(f"[WARN] WhatsApp send failed {r.status_code}: {r.text}", flush=True)
    except Exception as e:
        print(f"[WARN] WhatsApp send exception: {e}", flush=True)

# ----------------------------- Session helpers -----------------------------
def session_get(phone: str) -> Dict[str, Any]:
    s = PENDING.get(phone) or {}
    if s and (time.time() - s.get("ts", 0) > SESSION_TTL):
        s = {}
    s["ts"] = time.time()
    PENDING[phone] = s
    return s

def session_set(phone: str, data: Dict[str, Any]):
    data["ts"] = time.time()
    PENDING[phone] = data

def session_clear(phone: str):
    if phone in PENDING:
        del PENDING[phone]

def create_ticket(payload: Dict[str, Any]) -> int:
    now = datetime.now()
    due_dt = compute_due(now, payload["area"], payload["prioridad"])
    due_at = due_dt.isoformat() if due_dt else None

    new_id = insert_and_get_id(
        """
        INSERT INTO Tickets(org_id, hotel_id, area, prioridad, estado, detalle, canal_origen,
                            ubicacion, huesped_id, created_at, due_at,
                            assigned_to, created_by, confidence_score, qr_required)
        VALUES (%s, %s, %s, %s, 'PENDIENTE', %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s)
        """ if using_pg() else
        """
        INSERT INTO Tickets(org_id, hotel_id, area, prioridad, estado, detalle, canal_origen,
                            ubicacion, huesped_id, created_at, due_at,
                            assigned_to, created_by, confidence_score, qr_required)
        VALUES (?, ?, ?, ?, 'PENDIENTE', ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?)
        """,
        (
            payload.get("org_id", ORG_ID_DEFAULT),
            payload.get("hotel_id", HOTEL_ID_DEFAULT),
            payload["area"],
            payload["prioridad"],
            payload["detalle"],
            payload.get("canal_origen", "huesped_whatsapp"),
            payload.get("ubicacion"),
            payload.get("huesped_id"),
            now.isoformat(),
            due_at,
            None,   # assigned_to
            None,   # created_by
            float(payload.get("confidence_score", 0.85)),
            bool(payload.get("qr_required", False)),  # BOOLEAN, not 0/1
        )
    )

    # --- best-effort persist guest phone/name if columns exist ---
    guest_phone = payload.get("huesped_phone") or payload.get("huesped_id")  # use WA phone
    guest_name  = payload.get("huesped_nombre")

    try:
        sets = []
        params = []
        if guest_phone and table_has_column("Tickets", "huesped_phone"):
            sets.append("huesped_phone=%s" if using_pg() else "huesped_phone=?")
            params.append(guest_phone)
        if guest_name and table_has_column("Tickets", "huesped_nombre"):
            sets.append("huesped_nombre=%s" if using_pg() else "huesped_nombre=?")
            params.append(guest_name)

        if sets:
            params.append(new_id)
            sql = f"UPDATE Tickets SET {', '.join(sets)} WHERE id=%s" if using_pg() else \
                  f"UPDATE Tickets SET {', '.join(sets)} WHERE id=?"
            execute(sql, tuple(params))
    except Exception as e:
        print(f"[WARN] could not persist guest phone/name: {e}", flush=True)

    execute(
        "INSERT INTO TicketHistory(ticket_id, actor_user_id, action, motivo, at) VALUES (%s, %s, %s, %s, %s)"
        if using_pg() else
        "INSERT INTO TicketHistory(ticket_id, actor_user_id, action, motivo, at) VALUES (?, ?, ?, ?, ?)",
        (new_id, None, "CREADO", "via whatsapp", now.isoformat())
    )
    return new_id



# ----------------------------- Inbound normalization -----------------------------
def _normalize_inbound(req) -> Tuple[str, str, Optional[str]]:
    """
    Returns (from_phone, text, audio_url?)
    Supports:
      - Meta Cloud JSON
      - Twilio-form (if you ever test with it)
      - Raw JSON: {"from": "...", "text": "...", "audio_url": "..."}
    """
    ctype = (req.headers.get("Content-Type") or "").lower()

    # Twilio form
    if "application/x-www-form-urlencoded" in ctype:
        form = req.form
        from_ = clean_text(form.get("From"))
        body  = clean_text(form.get("Body"))
        audio = None
        try:
            n = int(form.get("NumMedia", "0"))
        except Exception:
            n = 0
        if n > 0 and "audio" in (form.get("MediaContentType0") or ""):
            audio = form.get("MediaUrl0")
        return (from_, body, audio)

    # JSON
    data = {}
    try:
        data = req.get_json(force=True, silent=True) or {}
    except Exception:
        pass

        # Meta Cloud (simplified)
    try:
        entry = data.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        msg = change["value"]["messages"][0]
        from_ = msg.get("from", "")
        text = ""
        audio_url = None

        if msg.get("type") == "text":
            text = clean_text(msg.get("text", {}).get("body"))
        elif msg.get("type") == "audio":
            aud = msg.get("audio", {}) or {}
            audio_url = aud.get("link")
            if not audio_url and aud.get("id"):
                audio_url, _ = _meta_get_media_url(aud["id"])  # requires Bearer token

            # Cloud sometimes gives a 'link', sometimes only an 'id'
            audio_url = aud.get("link")
            if not audio_url and aud.get("id"):
                audio_url, _ = _meta_get_media_url(aud["id"])
        elif msg.get("type") == "interactive":
            try:
                text = msg["interactive"]["list_reply"]["title"]
            except Exception:
                text = ""

        if from_:
            return (from_, text, audio_url)
    except Exception:
        pass


    # Raw JSON
    if any(k in data for k in ("from", "text", "audio_url")):
        return (clean_text(data.get("from", "")),
                clean_text(data.get("text", "")),
                clean_text(data.get("audio_url")) or None)

    return ("", "", None)

def _render_summary(area: str, prio: str, room: Optional[str], detail: str) -> str:
    return f"Área: {area}\nPrioridad: {prio}\nHabitación: {room or '—'}\nDetalle: {detail}"

# ----------------------------- Core processing -----------------------------
def process_message(from_phone: str, text: str, audio_url: Optional[str]) -> Dict[str, Any]:
    s = session_get(from_phone)

    # Normalize inputs
    text = (text or "").strip()
    cmd_upper = text.upper()

    # Inline quick edits always available
    if cmd_upper.startswith("AREA "):
        s["area"] = cmd_upper.split(" ", 1)[1].strip()
        session_set(from_phone, s)
        # If we already have name+room+detalle, go to confirm
        if s.get("guest_name") and s.get("room") and s.get("detalle"):
            send_whatsapp(from_phone, txt("confirm_draft", summary=ensure_summary_in_session(s)))
        else:
            # Nudge for the next missing piece
            if not s.get("guest_name"):
                send_whatsapp(from_phone, txt("ask_name"))
            elif not s.get("room"):
                send_whatsapp(from_phone, txt("ask_room", name=s.get("guest_name","")))
            else:
                send_whatsapp(from_phone, txt("ask_detail_after_room"))
        return {"ok": True, "pending": True}

    if cmd_upper.startswith("PRIORIDAD "):
        s["prioridad"] = cmd_upper.split(" ", 1)[1].strip().upper()
        session_set(from_phone, s)
        if s.get("guest_name") and s.get("room") and s.get("detalle"):
            send_whatsapp(from_phone, txt("confirm_draft", summary=ensure_summary_in_session(s)))
        else:
            if not s.get("guest_name"):
                send_whatsapp(from_phone, txt("ask_name"))
            elif not s.get("room"):
                send_whatsapp(from_phone, txt("ask_room", name=s.get("guest_name","")))
            else:
                send_whatsapp(from_phone, txt("ask_detail_after_room"))
        return {"ok": True, "pending": True}

    if cmd_upper.startswith("HAB ") or cmd_upper.startswith("ROOM "):
        s["room"] = re.sub(r"\D", "", text.split(" ", 1)[1])
        session_set(from_phone, s)
        if not s.get("guest_name"):
            send_whatsapp(from_phone, txt("ask_name"))
        elif not s.get("detalle"):
            send_whatsapp(from_phone, txt("ask_detail_after_room", name=s.get("guest_name","")))
        else:
            send_whatsapp(from_phone, txt("confirm_draft", summary=ensure_summary_in_session(s)))
        return {"ok": True, "pending": True}

    if cmd_upper.startswith("DETALLE "):
        s["detalle"] = text.split(" ", 1)[1] if " " in text else ""
        # If we don’t have area/prioridad yet, guess
        s.setdefault("area", guess_area(s["detalle"]))
        s.setdefault("prioridad", guess_priority(s["detalle"]))
        session_set(from_phone, s)
        if not s.get("guest_name"):
            send_whatsapp(from_phone, txt("nudge_detail_no_name"))
        elif not s.get("room"):
            send_whatsapp(from_phone, txt("nudge_detail_no_room", name=s["guest_name"]))
        else:
            send_whatsapp(from_phone, txt("confirm_draft", summary=ensure_summary_in_session(s)))
        return {"ok": True, "pending": True}

    # Confirm / cancel
    if cmd_upper in ("SI", "SÍ", "YES", "Y"):
        if not all(k in s for k in ("guest_name", "room", "detalle")):
            # Ask for missing pieces
            if not s.get("guest_name"):
                send_whatsapp(from_phone, txt("ask_name"))
            elif not s.get("room"):
                send_whatsapp(from_phone, txt("ask_room", name=s.get("guest_name","")))
            else:
                send_whatsapp(from_phone, txt("need_more_for_ticket"))
            return {"ok": True, "pending": True}

        # Ensure area/prioridad present
        s.setdefault("area", guess_area(s["detalle"]))
        s.setdefault("prioridad", guess_priority(s["detalle"]))
        session_set(from_phone, s)

        payload = {
            "org_id": s.get("org_id", ORG_ID_DEFAULT),
            "hotel_id": s.get("hotel_id", HOTEL_ID_DEFAULT),
            "area": s["area"],
            "prioridad": s["prioridad"],
            "detalle": s["detalle"],
            "ubicacion": s.get("room"),
            "huesped_id": from_phone,
            "canal_origen": "huesped_whatsapp",
            "confidence_score": s.get("confidence", 0.85),
            "qr_required": False,
            "huesped_phone": from_phone,
            "huesped_nombre": s.get("guest_name"),
        }
        ticket_id = create_ticket(payload)

        # Auto-asignación + notificación (si procede)
        try:
            _auto_assign_and_notify(
                ticket_id=ticket_id,
                area=s["area"],
                prioridad=s["prioridad"],
                detalle=s["detalle"],
                ubicacion=s.get("room"),
            )
        except Exception as e:
            print(f"[WARN] notify/assign failed: {e}", flush=True)

        send_whatsapp(from_phone, txt("ticket_created", guest=s.get("guest_name"), ticket_id=ticket_id))
        session_clear(from_phone)
        return {"ok": True, "ticket_id": ticket_id}

    if cmd_upper in ("NO", "N"):
        send_whatsapp(from_phone, txt("edit_help"))
        session_set(from_phone, s)
        return {"ok": True, "pending": True}

    # --------- Natural free text / audio flow ----------
    # If audio provided, transcribe; store as detalle if we already have name+room
    if audio_url:
        transcript = transcribe_audio(audio_url)
        if transcript:
            s["detalle"] = transcript
            s.setdefault("area", guess_area(transcript))
            s.setdefault("prioridad", guess_priority(transcript))
            session_set(from_phone, s)

            if not s.get("guest_name"):
                send_whatsapp(from_phone, txt("nudge_detail_no_name"))
                return {"ok": True, "pending": True}
            if not s.get("room"):
                send_whatsapp(from_phone, txt("nudge_detail_no_room", name=s["guest_name"]))
                return {"ok": True, "pending": True}

            # We have everything → confirm
            summary = ensure_summary_in_session(s)
            send_whatsapp(from_phone, txt("ack_got_detail_wait_confirm", summary=summary))
            return {"ok": True, "pending": True}

    # If text looks like greeting/smalltalk → greet and ask name
    if is_greeting_or_help(text):
        if not s.get("guest_name"):
            send_whatsapp(from_phone, txt("greet"))
        elif not s.get("room"):
            send_whatsapp(from_phone, txt("ask_room", name=s["guest_name"]))
        else:
            send_whatsapp(from_phone, txt("ask_detail_after_room"))
        session_set(from_phone, s)
        return {"ok": True, "pending": True}

    # Try to capture name/room opportunistically from free text
    if not s.get("guest_name"):
        n = maybe_name(text)
        if n:
            s["guest_name"] = n
            session_set(from_phone, s)
            send_whatsapp(from_phone, txt("ask_room", name=s["guest_name"]))
            return {"ok": True, "pending": True}

    if not s.get("room"):
        rm = maybe_room(text)
        if rm:
            s["room"] = rm
            session_set(from_phone, s)
            if not s.get("guest_name"):
                send_whatsapp(from_phone, txt("ask_name"))
            else:
                send_whatsapp(from_phone, txt("ask_detail_after_room"))
            return {"ok": True, "pending": True}

    # If we get a longer text and still missing detalle → treat as detalle
    if text and not s.get("detalle") and not looks_like_command(text):
        s["detalle"] = text
        s.setdefault("area", guess_area(text))
        s.setdefault("prioridad", guess_priority(text))
        session_set(from_phone, s)

        if not s.get("guest_name"):
            send_whatsapp(from_phone, txt("nudge_detail_no_name"))
            return {"ok": True, "pending": True}
        if not s.get("room"):
            send_whatsapp(from_phone, txt("nudge_detail_no_room", name=s["guest_name"]))
            return {"ok": True, "pending": True}

        # Confirm draft
        summary = ensure_summary_in_session(s)
        send_whatsapp(from_phone, txt("confirm_draft", summary=summary))
        return {"ok": True, "pending": True}

    # Default nudge depending on what’s missing
    if not s.get("guest_name"):
        send_whatsapp(from_phone, txt("ask_name"))
    elif not s.get("room"):
        send_whatsapp(from_phone, txt("ask_room", name=s["guest_name"]))
    else:
        send_whatsapp(from_phone, txt("ask_detail_after_room"))
    session_set(from_phone, s)
    return {"ok": True, "pending": True}



def _auth_ok(req) -> bool:
    if not INTERNAL_NOTIFY_TOKEN:
        return True  # allow when not configured (demo)
    auth = req.headers.get("Authorization", "")
    return auth == f"Bearer {INTERNAL_NOTIFY_TOKEN}"


# ----------------------------- Routes -----------------------------
@app.get("/")
def index():
    outbound = "meta-cloud" if (META_TOKEN and META_PHONE_ID) else "console-only"
    db = "postgres" if using_pg() else f"sqlite:{SQLITE_PATH}"
    return (
        "WhatsApp webhook is running.<br>"
        f"DB: {db} · Outbound: {outbound}<br>"
        "Try: <code>GET /healthz</code> · <code>POST /webhook/whatsapp</code> (JSON)<br>"
        "Local test: <code>POST /_simulate</code>"
    ), 200

@app.get("/healthz")
def healthz():
    return "ok", 200

# Meta webhook verification (Step: Verify and save)
@app.get("/webhook/whatsapp")
def whatsapp_verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN and challenge:
        return challenge, 200
    return "forbidden", 403

# Inbound messages
@app.post("/webhook/whatsapp")
def webhook():
    # Fast-path: Meta delivery statuses
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        try:
            change = payload.get("entry", [])[0].get("changes", [])[0]
            value = change.get("value", {})
            if "statuses" in value:
                return jsonify({"ok": True, "kind": "status"}), 200
            if "messages" in value:
                wamid = value["messages"][0].get("id")
                if wamid:
                    if wamid in PROCESSED_WAMIDS:
                        return jsonify({"ok": True, "duplicate": True}), 200
                    PROCESSED_WAMIDS.add(wamid)
        except Exception:
            pass

    from_phone, text, audio_url = _normalize_inbound(request)
    if not from_phone:
        return jsonify({"ok": True, "ignored": True}), 200

    s = session_get(from_phone)

    # If we receive audio as first interaction: greet & ask name (don’t force immediate detail-processing)
    if audio_url and not text:
        if not s.get("guest_name"):
            send_whatsapp(from_phone, txt("ask_name"))
            return jsonify({"ok": True, "pending": True}), 200
        # If we do know the guest, let the main processor handle transcription/flow
        # (we pass audio_url; process_message will transcribe & proceed)
    try:
        result = process_message(from_phone, text, audio_url)
        return jsonify(result), 200
    except Exception as e:
        print(f"[ERR] webhook processing: {e}", flush=True)
        send_whatsapp(from_phone, f"❌ Error procesando el mensaje: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500



# Simple local simulator (no Meta)
@app.post("/_simulate")
def simulate():
    """
    curl -XPOST localhost:5000/_simulate -H 'Content-Type: application/json' \
      -d '{"from":"+56900000000","text":"Se rompió la ducha en 1203, urgente"}'
    Then confirm:
      -d '{"from":"+56900000000","text":"SI"}'
    """
    data = request.get_json(force=True)
    from_phone = clean_text(data.get("from"))
    text = clean_text(data.get("text"))
    audio_url = clean_text(data.get("audio_url")) or None
    if not from_phone:
        return jsonify({"ok": False, "error": "missing from"}), 400
    try:
        result = process_message(from_phone, text, audio_url)
        return jsonify(result)
    except Exception as e:
        print(f"[ERR] simulate: {e}", flush=True)
        return jsonify({"ok": False, "error": str(e)}), 500
    

@app.post("/notify/guest/final")
def notify_guest_final():
    if not _auth_ok(request):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    data = request.get_json(force=True)
    to_phone = clean_text(data.get("to_phone"))
    ticket_id = data.get("ticket_id")
    guest_name = clean_text(data.get("huesped_nombre")) or "¡gracias!"
    if not (to_phone and ticket_id):
        return jsonify({"ok": False, "error": "missing fields"}), 400
    body = txt("guest_final", name=guest_name, ticket_id=ticket_id)
    send_whatsapp(to_phone, body)
    return jsonify({"ok": True})

@app.post("/notify/tech/assignment")
def notify_tech_assignment():
    if not _auth_ok(request):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    data = request.get_json(force=True)
    to_phone = clean_text(data.get("to_phone"))
    ticket_id = int(data.get("ticket_id", 0))
    area = data.get("area") or ""
    prioridad = data.get("prioridad") or ""
    detalle = data.get("detalle") or ""
    ubicacion = data.get("ubicacion")
    if not (to_phone and ticket_id):
        return jsonify({"ok": False, "error": "missing fields"}), 400

    # Reuse existing formatter logic
    link = _ticket_link(ticket_id)
    body = txt(
        "tech_assignment",
        prefix="📌 Asignado a ti.\n",
        ticket_id=ticket_id,
        area=area,
        prioridad=prioridad,
        habitacion=ubicacion or "—",
        detalle=detalle or "—",
        link=(f"Abrir: {link}" if link else "")
    )
    send_whatsapp(to_phone, body)
    return jsonify({"ok": True})




# ----------------------------- Main -----------------------------
if __name__ == "__main__":
    print(f"[BOOT] WhatsApp webhook starting on port {PORT} (DB={'PG' if using_pg() else 'SQLite'})", flush=True)
    app.run(host="0.0.0.0", port=PORT, debug=True)
