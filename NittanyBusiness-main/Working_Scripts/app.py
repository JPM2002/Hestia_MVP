# -*- coding: utf-8 -*-
import os, re, json, time, tempfile
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any, List

import requests
from flask import Flask, request, jsonify

# --------- DB: Postgres with SQLite fallback ---------
import sqlite3 as sqlite
pg = None
pg_extras = None
try:
    import psycopg2 as pg
    import psycopg2.extras as pg_extras
except Exception:
    pg = None

from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# ===================== Env / Config =====================
DATABASE_URL              = os.getenv("DATABASE_URL", "").strip()
SQLITE_PATH               = os.getenv("DATABASE_PATH", "hestia_V2.db")
INTERNAL_NOTIFY_TOKEN     = os.getenv("INTERNAL_NOTIFY_TOKEN", "")
OPENAI_API_KEY            = os.getenv("OPENAI_API_KEY", "")
TRANSCRIBE_PROVIDER       = os.getenv("TRANSCRIBE_PROVIDER", "none").lower()
WHATSAPP_CLOUD_TOKEN      = os.getenv("WHATSAPP_CLOUD_TOKEN", "").strip()
WHATSAPP_CLOUD_PHONE_ID   = os.getenv("WHATSAPP_CLOUD_PHONE_ID", "").strip()
WHATSAPP_VERIFY_TOKEN     = os.getenv("WHATSAPP_VERIFY_TOKEN", "my-verify-token")

# Optional product URLs
APP_BASE_URL              = os.getenv("APP_BASE_URL", "").strip()

# Who to alert when ticket is pending approval
RECEPTION_PHONES          = os.getenv("RECEPTION_PHONES", "").strip()

# Optional auto-assignment phones
ASSIGNEE_MANTENCION_PHONE = os.getenv("ASSIGNEE_MANTENCION_PHONE", "")
ASSIGNEE_HOUSEKEEPING_PHONE = os.getenv("ASSIGNEE_HOUSEKEEPING_PHONE", "")
ASSIGNEE_ROOMSERVICE_PHONE  = os.getenv("ASSIGNEE_ROOMSERVICE_PHONE", "")

# Optional flag to write assignment in DB when possible
AUTO_ASSIGN_ON_CREATE     = os.getenv("AUTO_ASSIGN_ON_CREATE", "false").lower() in ("1","true","yes","y")

# Default org/hotel for guest-created tickets
ORG_ID_DEFAULT  = int(os.getenv("DEMO_ORG_ID", "1"))
HOTEL_ID_DEFAULT= int(os.getenv("DEMO_HOTEL_ID", "1"))

# HK hardcoded phones. You can override with env HK_STAFF_PHONES="+569111;569222"
def _parse_phones_env(s: str) -> List[str]:
    if not s: return []
    return [re.sub(r"\D","",p) for p in re.split(r"[,; ]+", s) if p.strip()]

HK_STAFF_SET = set(_parse_phones_env(os.getenv("HK_STAFF_PHONES", "")))

HARDCODED_HK = {
    "56956326272",   # Andrés (CL)
    "56975620537",   # Borisbo (CL)
    "4915221317651", # Javier (DE: 015221317651 -> 49 15221317651)
}

if not HK_STAFF_SET:
    fallback = re.sub(r"\D", "", ASSIGNEE_HOUSEKEEPING_PHONE or "")
    HK_STAFF_SET = ({fallback} - {""}) | HARDCODED_HK
else:
    HK_STAFF_SET |= HARDCODED_HK

HK_STAFF_SET.discard("")  # safety


# Demo Housekeeping confirm flow (kept, but can be turned off)
DEMO_MODE_HK        = os.getenv("DEMO_MODE_HK", "off").lower()   # "on" | "off"
DEMO_HK_DELAY_SECS  = int(os.getenv("DEMO_HK_DELAY_SECS", "40"))
DEMO_HK_CONFIRM_KEYWORD = os.getenv("DEMO_HK_CONFIRM_KEYWORD", "confirmar ticket").lower()
DEMO_HK_TICKET_ID   = os.getenv("DEMO_HK_TICKET_ID", "HK-1042")
DEMO_HK_ROOM        = os.getenv("DEMO_HK_ROOM", "312")
DEMO_HK_ITEM        = os.getenv("DEMO_HK_ITEM", "toallas adicionales")
DEMO_HK_PRIORITY    = os.getenv("DEMO_HK_PRIORITY", "MEDIA")
DEMO_HK_GUEST       = os.getenv("DEMO_HK_GUEST", "Luis Miguel")
DEMO_HK_TIEMPO_ESPERADO = os.getenv("DEMO_HK_TIEMPO_ESPERADO", "10–15 minutos")

# SLA fallback if table missing
SLA_FALLBACK = {
    ("MANTENCION","URGENTE"):30, ("MANTENCION","ALTA"):90, ("MANTENCION","MEDIA"):240, ("MANTENCION","BAJA"):480,
    ("HOUSEKEEPING","URGENTE"):20, ("HOUSEKEEPING","ALTA"):60, ("HOUSEKEEPING","MEDIA"):120, ("HOUSEKEEPING","BAJA"):240,
    ("ROOMSERVICE","URGENTE"):20, ("ROOMSERVICE","ALTA"):45, ("ROOMSERVICE","MEDIA"):60, ("ROOMSERVICE","BAJA"):90,
}

# ===================== App =====================
app = Flask(__name__)

# ===================== Runtime store =====================
RUNTIME_DB_OK = False
FALLBACK_WAMIDS = set()
SESSION_TTL = 15 * 60  # seconds

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
        conn = pg.connect(dsn)
        try:
            pg_extras.register_default_json(conn, loads=json.loads)
            pg_extras.register_default_jsonb(conn, loads=json.loads)
        except Exception:
            pass
        return conn
    conn = sqlite.connect(SQLITE_PATH, check_same_thread=False)
    conn.row_factory = sqlite.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
    except Exception:
        pass
    return conn

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

def fetchall(sql: str, params=()):
    conn = db_conn()
    try:
        if using_pg():
            cur = conn.cursor(cursor_factory=pg_extras.RealDictCursor)
            cur.execute(sql, params)
            rows = cur.fetchall()
            conn.commit()
            cur.close()
            return rows
        else:
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
            conn.commit()
            return [dict(r) for r in rows]
    finally:
        try: conn.close()
        except Exception: pass

def ensure_runtime_tables():
    global RUNTIME_DB_OK
    try:
        if using_pg():
            execute("""
            CREATE TABLE IF NOT EXISTS runtime_sessions (
                phone TEXT PRIMARY KEY,
                data  JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )""")
            execute("""
            CREATE TABLE IF NOT EXISTS runtime_wamids (
                id TEXT PRIMARY KEY,
                seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )""")
        else:
            execute("""
            CREATE TABLE IF NOT EXISTS runtime_sessions (
                phone TEXT PRIMARY KEY,
                data  TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")
            execute("""
            CREATE TABLE IF NOT EXISTS runtime_wamids (
                id TEXT PRIMARY KEY,
                seen_at TEXT NOT NULL
            )""")
        RUNTIME_DB_OK = True
        print("[BOOT] runtime tables ready", flush=True)
    except Exception as e:
        RUNTIME_DB_OK = False
        print(f"[WARN] ensure_runtime_tables failed; using in-memory runtime: {e}", flush=True)

def wamid_seen_before(wamid: str) -> bool:
    if RUNTIME_DB_OK:
        try:
            row = fetchone("SELECT 1 FROM runtime_wamids WHERE id=%s" if using_pg() else
                           "SELECT 1 FROM runtime_wamids WHERE id=?", (wamid,))
            return bool(row)
        except Exception as e:
            print(f"[WARN] wamid_seen_before failed: {e}", flush=True)
    return wamid in FALLBACK_WAMIDS

def mark_wamid_seen(wamid: str):
    if RUNTIME_DB_OK:
        try:
            if using_pg():
                execute("INSERT INTO runtime_wamids(id, seen_at) VALUES (%s, NOW()) ON CONFLICT (id) DO NOTHING", (wamid,))
            else:
                execute("INSERT OR IGNORE INTO runtime_wamids(id, seen_at) VALUES (?, ?)", (wamid, datetime.now().isoformat()))
            return
        except Exception as e:
            print(f"[WARN] mark_wamid_seen failed: {e}", flush=True)
    FALLBACK_WAMIDS.add(wamid)
    if len(FALLBACK_WAMIDS) > 5000:
        FALLBACK_WAMIDS.clear()

# ===================== WhatsApp helpers =====================
GRAPH_VER = "v21.0"

def _clean_phone(s: str) -> str:
    return re.sub(r"\D", "", (s or "").replace("whatsapp:", ""))

def send_whatsapp(to: str, body: str):
    to_clean = _clean_phone(to)
    print(f"[OUT → {to_clean}] {body}", flush=True)
    if not (WHATSAPP_CLOUD_TOKEN and WHATSAPP_CLOUD_PHONE_ID):
        return
    try:
        url = f"https://graph.facebook.com/{GRAPH_VER}/{WHATSAPP_CLOUD_PHONE_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_CLOUD_TOKEN}",
            "Content-Type": "application/json"
        }
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

def _meta_get_media_url(media_id: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        url = f"https://graph.facebook.com/{GRAPH_VER}/{media_id}"
        headers = {"Authorization": f"Bearer {WHATSAPP_CLOUD_TOKEN}"}
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
        return data.get("url"), data.get("mime_type")
    except Exception as e:
        print(f"[WARN] _meta_get_media_url failed: {e}", flush=True)
        return None, None

# ===================== Copy =====================
COPY = {
    "greet":
        "¡Hola! 👋 Soy tu asistente. Puedo ayudarte con mantención, housekeeping o room service.\n"
        "Para empezar, ¿me dices *tu nombre*? 🙂",
    "ask_room": "Gracias, *{name}*. ¿Cuál es tu *número de habitación*? 🏨",
    "ask_detail":"Perfecto. Ahora cuéntame qué ocurrió. Puedes *enviar un audio* o escribir el detalle. 🎤✍️",
    "ask_name":
        "🌟 ¡Bienvenido/a! ¿Con quién tengo el gusto? 😊\n"
        "Indícame *tu nombre* y luego *número de habitación* para poder ayudarte.",
    "need_more_for_ticket":"🙏 Me faltan algunos datos para crear el ticket. ¿Podrías enviarme el *detalle* o *habitación*, por favor?",
    "confirm_draft":"📝 Voy a registrar tu solicitud, ¿es correcto?\n\n{summary}\n\nResponde *SI* para confirmar o *NO* para editar.\n_Comandos_: AREA/PRIORIDAD/HAB/DETALLE …",
    "edit_help":
        "Puedes corregir usando:\n"
        "• AREA <mantención | housekeeping | roomservice>\n"
        "• PRIORIDAD <urgente | alta | media | baja>\n"
        "• HAB <número>\n"
        "• DETALLE <texto>\n"
        "Cuando esté listo, responde *SI* para confirmarlo.",
    "ticket_created":"✅ ¡Gracias, {guest}! Hemos registrado el ticket #{ticket_id}.",
    "ticket_pending_approval":
        "✅ ¡Gracias, {guest}! He registrado tu solicitud como *pendiente de aprobación* (ticket #{ticket_id}). Recepción la revisará en breve. 🛎️",
    "guest_final":"✨ ¡Listo, {name}! Tu solicitud (ticket #{ticket_id}) ha sido *resuelta*.",
    "reception_new_pending":
        "📥 Ticket para *revisión/edición* #{ticket_id}\nÁrea: {area}\nPrioridad: {prioridad}\nHabitación: {habitacion}\nDetalle: {detalle}\n{link}\n\nAcción en sistema: Aprobar / Editar.",
    "hk_menu":
        "Opciones:\n• *ACEPTAR*\n• *DERIVAR* / *RECHAZAR*\n• *START_QR* / *START_NO_QR*\n• *PAUSA* / *RESUME*\n• *ADD_EVIDENCE* (envía foto/video/audio/doc)\n• *FINISH_QR* / *FINISH_NO_QR*",
}

# ===================== NLP / heuristics =====================
AREA_KEYWORDS = {
    "MANTENCION": ["ducha","baño","grifo","llave","aire","ac","fuga","luz","enchufe","televisor","tv","puerta","ventana","calefaccion","calefacción"],
    "HOUSEKEEPING": ["toalla","sábana","sabana","almohada","limpieza","aseo","basura","amenities","shampoo","jabón","sabanas"],
    "ROOMSERVICE": ["pedido","hamburguesa","sandwich","desayuno","cena","comida","room service","cerveza","vino","agua"],
}
ROOM_RE = re.compile(r"\b(\d{3,4})\b")

def guess_area(text: str) -> str:
    t = (text or "").lower()
    for area,kws in AREA_KEYWORDS.items():
        if any(k in t for k in kws):
            return area
    return "MANTENCION"

def guess_priority(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ["urgente","rápido","rapido","inundación","fuga","incendio","peligro"]): return "URGENTE"
    if any(k in t for k in ["alto","grave","importante"]): return "ALTA"
    if any(k in t for k in ["normal","cuando puedan","si pueden"]): return "MEDIA"
    return "MEDIA"

def guess_room(text: str) -> Optional[str]:
    m = ROOM_RE.search(text or "")
    return m.group(1) if m else None

# ===================== Session =====================
def session_get(phone: str) -> Dict[str, Any]:
    s: Dict[str, Any] = {}
    if RUNTIME_DB_OK:
        try:
            row = fetchone("SELECT data FROM runtime_sessions WHERE phone=%s" if using_pg() else
                           "SELECT data FROM runtime_sessions WHERE phone=?", (phone,))
            if row and row.get("data") is not None:
                val = row["data"]
                if isinstance(val, dict):
                    s = val
                else:
                    if isinstance(val, (bytes, bytearray, memoryview)):
                        val = bytes(val).decode("utf-8","ignore")
                    s = json.loads(val or "{}")
        except Exception as e:
            print(f"[WARN] session_get failed: {e}", flush=True)
    else:
        s = PENDING.get(phone) if 'PENDING' in globals() else {}

    # TTL
    if s and (time.time() - s.get("ts",0) > SESSION_TTL):
        s = {}
    s["ts"] = time.time()
    session_set(phone, s)
    return s

def session_set(phone: str, data: Dict[str, Any]):
    data["ts"] = time.time()
    if RUNTIME_DB_OK:
        try:
            if using_pg():
                execute("""
                    INSERT INTO runtime_sessions(phone, data, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (phone) DO UPDATE SET data=EXCLUDED.data, updated_at=EXCLUDED.updated_at
                """, (phone, pg_extras.Json(data)))
            else:
                execute("""
                    INSERT OR REPLACE INTO runtime_sessions(phone, data, updated_at)
                    VALUES (?, ?, ?)
                """, (phone, json.dumps(data), datetime.now().isoformat()))
            return
        except Exception as e:
            print(f"[WARN] session_set failed: {e}", flush=True)
    globals().setdefault("PENDING", {})
    PENDING[phone] = data

def session_clear(phone: str):
    if RUNTIME_DB_OK:
        try:
            execute("DELETE FROM runtime_sessions WHERE phone=%s" if using_pg() else
                    "DELETE FROM runtime_sessions WHERE phone=?", (phone,))
            return
        except Exception as e:
            print(f"[WARN] session_clear failed: {e}", flush=True)
    if 'PENDING' in globals() and phone in PENDING:
        del PENDING[phone]

# ===================== Role resolve =====================
def _only_digits(s: str) -> str:
    return re.sub(r"\D","", s or "")

def _db_is_hk_by_phone(digits_phone: str) -> bool:
    try:
        rows = fetchall("SELECT role, telefono FROM users WHERE activo = TRUE", ())
        for r in rows or []:
            tel = _only_digits(r.get("telefono") or "")
            if tel and tel == digits_phone:
                role = (r.get("role") or "").upper()
                return role in {"HOUSEKEEPING","HK","MUCAMA","MUCAMAS"}
    except Exception as e:
        print(f"[WARN] _db_is_hk_by_phone failed: {e}", flush=True)
    return False

def resolve_role(from_phone_digits: str) -> str:
    if from_phone_digits in HK_STAFF_SET:
        return "HK"
    if _db_is_hk_by_phone(from_phone_digits):
        return "HK"
    return "GUEST"

# ===================== SLA / due date =====================
def sla_minutes(area: str, prioridad: str) -> Optional[int]:
    try:
        r = fetchone(
            "SELECT max_minutes FROM slarules WHERE area=%s AND prioridad=%s AND org_id IS NULL AND hotel_id IS NULL"
            if using_pg() else
            "SELECT max_minutes FROM slarules WHERE area=? AND prioridad=? AND org_id IS NULL AND hotel_id IS NULL",
            (area, prioridad)
        )
        if r and r.get("max_minutes") is not None:
            return int(r["max_minutes"])
    except Exception:
        pass
    return SLA_FALLBACK.get((area, prioridad))

def compute_due(created_at: datetime, area: str, prioridad: str) -> Optional[datetime]:
    mins = sla_minutes(area, prioridad)
    return created_at + timedelta(minutes=mins) if mins else None

# ===================== Transcription =====================
def transcribe_audio(audio_url: str) -> str:
    if TRANSCRIBE_PROVIDER != "openai" or not OPENAI_API_KEY:
        return f"[audio recibido: {audio_url}]"
    if not audio_url:
        return ""
    headers = {}
    if WHATSAPP_CLOUD_TOKEN:
        headers["Authorization"] = f"Bearer {WHATSAPP_CLOUD_TOKEN}"
    tmp_path = None
    try:
        r = requests.get(audio_url, headers=headers, timeout=60)
        if r.status_code in (401,403):
            print(f"[WARN] media download unauthorized ({r.status_code}) -> {audio_url}", flush=True)
            return ""
        r.raise_for_status()
        content = r.content
        mime = (r.headers.get("Content-Type") or "audio/ogg").lower()
        ext = ".ogg"
        if "mp4" in mime or "aac" in mime or "m4a" in mime: ext = ".m4a"
        elif "mpeg" in mime or "mp3" in mime: ext = ".mp3"
        elif "wav" in mime: ext = ".wav"

        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as f:
            f.write(content)
            tmp_path = f.name

        # OpenAI Whisper
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        with open(tmp_path, "rb") as fh:
            resp = client.audio.transcriptions.create(
                model="whisper-1",
                file=fh,
                temperature=0,
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

# ===================== Ticket ops =====================
def _ticket_link(ticket_id: int) -> str:
    if APP_BASE_URL:
        base = APP_BASE_URL.rstrip("/")
        return f"{base}/tickets/{ticket_id}"
    return ""

def _notify_reception_pending(ticket_id: int, area: str, prioridad: str, detalle: str, ubicacion: Optional[str]):
    phones = _parse_phones_env(RECEPTION_PHONES)
    if not phones: return
    link = _ticket_link(ticket_id)
    body = COPY["reception_new_pending"].format(
        ticket_id=ticket_id, area=area or "—", prioridad=prioridad or "—",
        habitacion=ubicacion or "—", detalle=detalle or "—", link=(f"Abrir: {link}" if link else "")
    )
    for ph in phones:
        send_whatsapp(ph, body)

def create_ticket(payload: Dict[str, Any], initial_status: str = "PENDIENTE_APROBACION") -> int:
    now = datetime.now()
    due_dt = compute_due(now, payload["area"], payload["prioridad"])
    due_at = due_dt.isoformat() if due_dt else None
    new_id = insert_and_get_id(
        """
        INSERT INTO tickets(org_id, hotel_id, area, prioridad, estado, detalle, canal_origen,
                            ubicacion, huesped_id, created_at, due_at,
                            assigned_to, created_by, confidence_score, qr_required)
        VALUES (%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,
                %s,%s,%s,%s)
        """ if using_pg() else
        """
        INSERT INTO tickets(org_id, hotel_id, area, prioridad, estado, detalle, canal_origen,
                            ubicacion, huesped_id, created_at, due_at,
                            assigned_to, created_by, confidence_score, qr_required)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            payload.get("org_id", ORG_ID_DEFAULT),
            payload.get("hotel_id", HOTEL_ID_DEFAULT),
            payload["area"],
            payload["prioridad"],
            initial_status,
            payload["detalle"],
            payload.get("canal_origen","huesped_whatsapp"),
            payload.get("ubicacion") or "-",  # schema: NOT NULL
            payload.get("huesped_id"),
            now.isoformat(),
            due_at,
            None, None,
            float(payload.get("confidence_score", 0.85)),
            bool(payload.get("qr_required", False)),
        )
    )
    # History
    execute(
        "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (%s,%s,%s,%s,%s)"
        if using_pg() else
        "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (?,?,?,?,?)",
        (new_id, None, "CREADO", "via whatsapp", now.isoformat())
    )
    if initial_status == "PENDIENTE_APROBACION":
        execute(
            "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (%s,%s,%s,%s,%s)"
            if using_pg() else
            "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (?,?,?,?,?)",
            (new_id, None, "PENDIENTE_APROBACION", "esperando aprobación de recepción", now.isoformat())
        )
    return new_id

def add_attachment(ticket_id: int, url: str, mime: str, size_bytes: Optional[int] = None, created_by: Optional[int] = None):
    execute(
        "INSERT INTO ticket_attachments(ticket_id, kind, url, mime, size_bytes, created_by) VALUES (%s,%s,%s,%s,%s,%s)"
        if using_pg() else
        "INSERT INTO ticket_attachments(ticket_id, kind, url, mime, size_bytes, created_by) VALUES (?,?,?,?,?,?)",
        (ticket_id, "whatsapp", url, mime, size_bytes, created_by)
    )

def add_voice_note(ticket_id: int, audio_url: str, transcript: str):
    execute(
        "INSERT INTO ticket_voice_notes(ticket_id, audio_url, transcript, lang, duration_sec, created_by) VALUES (%s,%s,%s,%s,%s,%s)"
        if using_pg() else
        "INSERT INTO ticket_voice_notes(ticket_id, audio_url, transcript, lang, duration_sec, created_by) VALUES (?,?,?,?,?,?)",
        (ticket_id, audio_url, transcript, "es", None, None)
    )

def _auto_assign_and_notify(ticket_id: int, area: str, prioridad: str, detalle: str, ubicacion: Optional[str]):
    area_u = (area or "").upper()
    to_phone = None
    if area_u == "MANTENCION":
        to_phone = ASSIGNEE_MANTENCION_PHONE or None
    elif area_u == "HOUSEKEEPING":
        to_phone = ASSIGNEE_HOUSEKEEPING_PHONE or None
    elif area_u == "ROOMSERVICE":
        to_phone = ASSIGNEE_ROOMSERVICE_PHONE or None
    if not to_phone:
        return
    assigned_user_id = None
    if AUTO_ASSIGN_ON_CREATE:
        try:
            rows = fetchall("SELECT id, telefono FROM users WHERE activo = TRUE", ())
            target = _only_digits(to_phone)
            for r in rows or []:
                if _only_digits(r.get("telefono") or "") == target:
                    assigned_user_id = int(r["id"])
                    break
            if assigned_user_id:
                execute("UPDATE tickets SET assigned_to=%s WHERE id=%s" if using_pg() else
                        "UPDATE tickets SET assigned_to=? WHERE id=?", (assigned_user_id, ticket_id))
                execute(
                    "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (%s,%s,%s,%s,%s)"
                    if using_pg() else
                    "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (?,?,?,?,?)",
                    (ticket_id, None, "ASIGNADO_AUTO", f"area={area_u}", datetime.now().isoformat())
                )
        except Exception as e:
            print(f"[WARN] auto-assign failed: {e}", flush=True)

    body = f"{'📌 Asignado a ti.\n' if assigned_user_id else ''}🔔 Nuevo ticket #{ticket_id}\nÁrea: {area}\nPrioridad: {prioridad}\nUbicación: {ubicacion or '—'}\nDetalle: {detalle or '—'}"
    link = _ticket_link(ticket_id)
    if link: body += f"\nAbrir: {link}"
    send_whatsapp(to_phone, body)

# ===================== Inbound normalization =====================
def _normalize_inbound(req) -> Tuple[str, str, Optional[str], List[Dict[str,str]]]:
    """
    Returns (from_phone, text, audio_url, media_list[{'url','mime'}])
    Supports Meta Cloud JSON, Twilio-form, and raw JSON for local tests.
    """
    ctype = (req.headers.get("Content-Type") or "").lower()

    # Twilio form (optional dev)
    if "application/x-www-form-urlencoded" in ctype:
        form = req.form
        from_ = _clean_phone(form.get("From"))
        body  = (form.get("Body") or "").strip()
        audio = None
        media = []
        try:
            n = int(form.get("NumMedia","0"))
        except Exception:
            n = 0
        for i in range(n):
            mt = form.get(f"MediaContentType{i}") or ""
            mu = form.get(f"MediaUrl{i}") or ""
            if not mu: continue
            if "audio" in mt and not audio:
                audio = mu
            media.append({"url": mu, "mime": mt})
        return (from_, body, audio, media)

    data = {}
    try:
        data = req.get_json(force=True, silent=True) or {}
    except Exception:
        pass

    # Meta Cloud
    try:
        entry = data.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {}) or {}
        msgs  = value.get("messages") or []
        if msgs:
            msg = msgs[0]
            from_ = _clean_phone(msg.get("from") or "")
            text, audio_url = "", None
            media = []

            mtype = msg.get("type")
            if mtype == "text":
                text = (msg.get("text",{}).get("body") or "").strip()
            elif mtype == "audio":
                aud = msg.get("audio",{}) or {}
                audio_url = aud.get("link")
                if not audio_url and aud.get("id"):
                    audio_url,_ = _meta_get_media_url(aud["id"])
                if audio_url: media.append({"url": audio_url, "mime": "audio"})
            elif mtype in ("image","video","document","sticker"):
                node = msg.get(mtype,{}) or {}
                link = node.get("link")
                if not link and node.get("id"):
                    link,_mime = _meta_get_media_url(node["id"])
                    if link: media.append({"url": link, "mime": _mime or mtype})
                elif link:
                    media.append({"url": link, "mime": node.get("mime_type") or mtype})
            elif mtype == "interactive":
                try:
                    text = msg["interactive"]["list_reply"]["title"]
                except Exception:
                    text = msg.get("interactive",{}).get("button_reply",{}).get("title","")

            return (from_, text, audio_url, media)
    except Exception:
        pass

    # Raw JSON local
    if any(k in data for k in ("from","text","audio_url","media")):
        return (
            _clean_phone(data.get("from","")),
            (data.get("text") or "").strip(),
            data.get("audio_url"),
            data.get("media") or []
        )

    return ("","","",[])

# ===================== Guest DFA =====================
GREETING_WORDS = {
    "hola","holi","hello","hi","buenas","buen dia","buen día","buenas tardes","buenas noches","que tal","qué tal","ayuda","necesito ayuda","consulta","hey"
}
COMMAND_PREFIXES = ("AREA ","PRIORIDAD ","HAB ","ROOM ","DETALLE ","SI","SÍ","YES","Y","NO","N")

def looks_like_command(s: str) -> bool:
    u = (s or "").strip().upper()
    return any(u.startswith(p) for p in COMMAND_PREFIXES)

def is_smalltalk(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t: return False
    return any(t == w or t.startswith(w) for w in GREETING_WORDS)

def extract_name(text: str) -> Optional[str]:
    t = (text or "").strip()
    if not t or looks_like_command(t) or is_smalltalk(t):
        return None
    if any(ch.isdigit() for ch in t): return None
    parts = t.split()
    if not (1 <= len(parts) <= 4): return None
    for p in parts:
        if not re.match(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+$", p):
            return None
    return t.title()

def is_yes(text: str) -> bool:
    t = (text or "").strip().lower()
    t = re.sub(r"[!.,;:()\[\]_\"'`´~]+$","", t).strip()
    return t in {"si","sí","s","y","yes","ok","vale","dale","de acuerdo"}

def ensure_summary(s: Dict[str, Any]) -> str:
    area = s.get("area") or "MANTENCION"
    prio = s.get("prioridad") or "MEDIA"
    room = s.get("room") or "—"
    detalle = s.get("detalle") or ""
    return f"Área: {area}\nPrioridad: {prio}\nHabitación: {room}\nDetalle: {detalle}"

def guest_handle(phone: str, text: str, audio_url: Optional[str], media: List[Dict[str,str]]) -> Dict[str,Any]:
    s = session_get(phone)
    s["role"] = "GUEST"
    stage = s.get("guest_stage") or "need_name"

    cmd_raw = (text or "").strip()
    cmd_up  = cmd_raw.upper()

    # Inline edits
    if cmd_up.startswith("AREA "):
        s["area"] = cmd_up.split(" ",1)[1].strip().upper()
    elif cmd_up.startswith("PRIORIDAD "):
        s["prioridad"] = cmd_up.split(" ",1)[1].strip().upper()
    elif cmd_up.startswith("HAB ") or cmd_up.startswith("ROOM "):
        s["room"] = re.sub(r"\D","", cmd_up.split(" ",1)[1])
    elif cmd_up.startswith("DETALLE "):
        s["detalle"] = cmd_raw.split(" ",1)[1] if " " in cmd_raw else ""
        if s.get("guest_name") and s.get("room") and s.get("detalle"):
            s["guest_stage"] = "confirm"

    # === need_name ===
    if stage == "need_name":
        maybe = extract_name(cmd_raw)
        if maybe:
            s["guest_name"] = maybe
            s["guest_stage"] = "need_room"
            session_set(phone, s)
            send_whatsapp(phone, COPY["ask_room"].format(name=s["guest_name"]))
            return {"ok": True, "pending": True}
        else:
            send_whatsapp(phone, COPY["greet"])
            session_set(phone, s)
            return {"ok": True, "pending": True}

    # === need_room ===
    if stage == "need_room":
        room = s.get("room") or guess_room(cmd_raw)
        if room:
            s["room"] = room
            s["guest_stage"] = "need_detail"
            session_set(phone, s)
            send_whatsapp(phone, COPY["ask_detail"])
            return {"ok": True, "pending": True}
        else:
            send_whatsapp(phone, COPY["ask_room"].format(name=s.get("guest_name","")))
            session_set(phone, s)
            return {"ok": True, "pending": True}

    # === need_detail ===
    if stage == "need_detail":
        detail = s.get("detalle") or cmd_raw
        if is_yes(cmd_raw):
            if s.get("detalle") and s.get("room"):
                s["guest_stage"] = "confirm"
                session_set(phone, s)
                send_whatsapp(phone, COPY["confirm_draft"].format(summary=ensure_summary(s)))
                return {"ok": True, "pending": True}
            send_whatsapp(phone, COPY["ask_detail"])
            session_set(phone, s)
            return {"ok": True, "pending": True}

        # voice or media as detail
        if audio_url and not cmd_raw:
            detail = transcribe_audio(audio_url) or "[audio recibido]"

        # fallback to any media caption-less
        if not detail and media:
            detail = "[archivo recibido]"

        if detail and len(detail.strip()) >= 3:
            s["detalle"]   = detail.strip()
            s["area"]      = s.get("area") or guess_area(s["detalle"])
            s["prioridad"] = s.get("prioridad") or guess_priority(s["detalle"])
            s["guest_stage"] = "confirm"
            session_set(phone, s)
            send_whatsapp(phone, COPY["confirm_draft"].format(summary=ensure_summary(s)))
            return {"ok": True, "pending": True}
        else:
            send_whatsapp(phone, COPY["ask_detail"])
            session_set(phone, s)
            return {"ok": True, "pending": True}

    # === confirm ===
    if stage == "confirm":
        if is_yes(cmd_raw):
            if not all(k in s for k in ("area","prioridad","detalle")):
                send_whatsapp(phone, COPY["need_more_for_ticket"])
                return {"ok": True, "pending": True}

            payload = {
                "org_id": ORG_ID_DEFAULT,
                "hotel_id": HOTEL_ID_DEFAULT,
                "area": s["area"],
                "prioridad": s["prioridad"],
                "detalle": s["detalle"],
                "ubicacion": s.get("room") or "-",
                "huesped_id": phone,
                "canal_origen": "huesped_whatsapp",
                "confidence_score": s.get("confidence", 0.85),
                "qr_required": False,
            }
            ticket_id = create_ticket(payload, initial_status="PENDIENTE_APROBACION")

            # Optional media attachments after ticket creation
            for m in media or []:
                add_attachment(ticket_id, m.get("url",""), m.get("mime",""))
            if audio_url:
                transcript = transcribe_audio(audio_url) if TRANSCRIBE_PROVIDER == "openai" else ""
                add_voice_note(ticket_id, audio_url, transcript)

            # Notify reception
            try:
                _notify_reception_pending(ticket_id, s["area"], s["prioridad"], s["detalle"], s.get("room"))
            except Exception as e:
                print(f"[WARN] notify reception failed: {e}", flush=True)

            send_whatsapp(phone, COPY["ticket_pending_approval"].format(guest=s.get("guest_name",""), ticket_id=ticket_id))
            session_clear(phone)
            return {"ok": True, "ticket_id": ticket_id}

        # show edit help
        send_whatsapp(phone, COPY["edit_help"])
        session_set(phone, s)
        return {"ok": True, "pending": True}

    # fallback
    session_set(phone, s)
    return {"ok": True, "pending": True}

# ===================== HK DFA =====================
def hk_menu(phone: str):
    send_whatsapp(phone, COPY["hk_menu"])

def hk_handle(phone: str, text: str, audio_url: Optional[str], media: List[Dict[str,str]]) -> Dict[str,Any]:
    s = session_get(phone)
    s["role"] = "HK"
    stage = s.get("hk_stage") or "S0"     # S0 → waiting; S1 → in-progress; S2 → finishing
    cmd = (text or "").strip().upper()

    # Require a bound ticket in HK session for real actions
    ticket_id = s.get("ticket_id")

    # Basic router
    if stage == "S0":
        if cmd in {"ACEPTAR","ACCEPT","OK"} and ticket_id:
            # mark accepted_at
            execute("UPDATE tickets SET estado=%s, accepted_at=%s WHERE id=%s" if using_pg() else
                    "UPDATE tickets SET estado=?, accepted_at=? WHERE id=?",
                    ("ACEPTADO", datetime.now().isoformat(), ticket_id))
            execute("INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (%s,%s,%s,%s,%s)" if using_pg() else
                    "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (?,?,?,?,?)",
                    (ticket_id, None, "ACEPTADO", "", datetime.now().isoformat()))
            s["hk_stage"] = "S1"
            session_set(phone, s)
            hk_menu(phone)
            return {"ok": True, "ticket_id": ticket_id, "stage": "S1"}
        elif cmd in {"DERIVAR","RECHAZAR","FORWARD","REJECT","TIMEOUT"} and ticket_id:
            execute("UPDATE tickets SET estado=%s WHERE id=%s" if using_pg() else
                    "UPDATE tickets SET estado=? WHERE id=?", ("DERIVADO", ticket_id))
            execute("INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (%s,%s,%s,%s,%s)" if using_pg() else
                    "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (?,?,?,?,?)",
                    (ticket_id, None, "DERIVADO", cmd, datetime.now().isoformat()))
            session_clear(phone)
            send_whatsapp(phone, "✔️ Ticket derivado.")
            return {"ok": True, "ticket_id": ticket_id, "stage": "END"}
        else:
            hk_menu(phone)
            session_set(phone, s)
            return {"ok": True, "pending": True}

    if stage == "S1" and ticket_id:
        if cmd in {"START_QR","START_NO_QR"}:
            execute("UPDATE tickets SET estado=%s, started_at=%s WHERE id=%s" if using_pg() else
                    "UPDATE tickets SET estado=?, started_at=? WHERE id=?",
                    ("EN_CURSO", datetime.now().isoformat(), ticket_id))
            execute("INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (%s,%s,%s,%s,%s)" if using_pg() else
                    "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (?,?,?,?,?)",
                    (ticket_id, None, "EN_CURSO", cmd, datetime.now().isoformat()))
            send_whatsapp(phone, "⏱️ Trabajo iniciado.")
            session_set(phone, s)
            return {"ok": True, "ticket_id": ticket_id, "stage": "S1"}

        if cmd in {"PAUSA","PAUSE"}:
            execute("UPDATE tickets SET estado=%s WHERE id=%s" if using_pg() else
                    "UPDATE tickets SET estado=? WHERE id=?", ("PAUSADO", ticket_id))
            execute("INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (%s,%s,%s,%s,%s)" if using_pg() else
                    "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (?,?,?,?,?)",
                    (ticket_id, None, "PAUSADO", "", datetime.now().isoformat()))
            send_whatsapp(phone, "⏸️ Pausado.")
            return {"ok": True}

        if cmd in {"RESUME","REANUDAR"}:
            execute("UPDATE tickets SET estado=%s WHERE id=%s" if using_pg() else
                    "UPDATE tickets SET estado=? WHERE id=?", ("EN_CURSO", ticket_id))
            execute("INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (%s,%s,%s,%s,%s)" if using_pg() else
                    "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (?,?,?,?,?)",
                    (ticket_id, None, "REANUDADO", "", datetime.now().isoformat()))
            send_whatsapp(phone, "▶️ Reanudado.")
            return {"ok": True}

        if cmd in {"ADD_EVIDENCE","ADD EVIDENCE","EVIDENCIA"} or media or audio_url:
            # Attach media if present
            if media:
                for m in media:
                    add_attachment(ticket_id, m.get("url",""), m.get("mime",""))
            if audio_url:
                transcript = transcribe_audio(audio_url) if TRANSCRIBE_PROVIDER == "openai" else ""
                add_voice_note(ticket_id, audio_url, transcript)
            send_whatsapp(phone, "📎 Evidencia agregada.")
            return {"ok": True}

        if cmd in {"FINISH_QR","FINISH_NO_QR"}:
            execute("UPDATE tickets SET estado=%s, finished_at=%s WHERE id=%s" if using_pg() else
                    "UPDATE tickets SET estado=?, finished_at=? WHERE id=?",
                    ("RESUELTO", datetime.now().isoformat(), ticket_id))
            execute("INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (%s,%s,%s,%s,%s)" if using_pg() else
                    "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (?,?,?,?,?)",
                    (ticket_id, None, "FINALIZADO", cmd, datetime.now().isoformat()))
            send_whatsapp(phone, f"✅ Ticket #{ticket_id} resuelto.")
            session_clear(phone)
            return {"ok": True, "ticket_id": ticket_id, "stage": "END"}

        # Unrecognized → menu again
        hk_menu(phone)
        return {"ok": True, "pending": True}

    if stage == "S2" and ticket_id:
        # Not used deeply; S2 handles finish variants in S1 above
        hk_menu(phone)
        return {"ok": True, "pending": True}

    # If no ticket bound, show menu and exit
    hk_menu(phone)
    session_set(phone, s)
    return {"ok": True, "pending": True}

# ===================== DEMO: HK prompt in same chat =====================
import threading
def _compose_demo_hk_text(ticket_id: str, room: str, item: str, prioridad: str, guest: str) -> str:
    return (
        "🧹 Housekeeping — Ticket Entrante\n"
        f"Ticket: {ticket_id}\n"
        f"Área: HOUSEKEEPING | Prioridad: {prioridad}\n"
        f"Habitación: {room}\n"
        f"Solicitud: {item} (hab. {room})\n"
        "Instrucciones: Llevar 4 toallas (2 extra), revisar amenities.\n"
        f"Tiempo esperado: {DEMO_HK_TIEMPO_ESPERADO}\n"
        f"Huésped: {guest}\n\n"
        "¿Está bien el ticket? Responde *CONFIRMAR TICKET* para continuar."
    )

def _demo_hk_schedule_to_same_chat(chat_phone: str):
    s = session_get(chat_phone)
    if s.get("demo_hk_scheduled"): return False
    s["demo_hk_scheduled"] = True
    s["demo_hk_pending"] = True
    s["demo_hk_payload"] = {
        "ticket_id": DEMO_HK_TICKET_ID,
        "room": DEMO_HK_ROOM,
        "item": DEMO_HK_ITEM,
        "prioridad": DEMO_HK_PRIORITY,
        "guest": DEMO_HK_GUEST,
    }
    session_set(chat_phone, s)

    def _run():
        try:
            time.sleep(DEMO_HK_DELAY_SECS)
            ss = session_get(chat_phone)
            payload = (ss.get("demo_hk_payload") or {}).copy()
            body = _compose_demo_hk_text(payload["ticket_id"], payload["room"], payload["item"], payload["prioridad"], payload["guest"])
            send_whatsapp(chat_phone, body)
            ss["demo_hk_prompt_sent"] = True
            session_set(chat_phone, ss)
        except Exception as e:
            print(f"[WARN] demo HK scheduler failed: {e}", flush=True)

    threading.Thread(target=_run, daemon=True).start()
    return True

def _demo_hk_handle_confirm(chat_phone: str, text: str) -> bool:
    if DEMO_MODE_HK != "on": return False
    t = (text or "").strip().lower()
    s = session_get(chat_phone)
    if s.get("demo_hk_pending") and DEMO_HK_CONFIRM_KEYWORD in t:
        send_whatsapp(chat_phone, "✅ Ticket confirmado. El tiempo ha comenzado a correr.")
        s["demo_hk_pending"] = False
        s["demo_hk_confirmed_at"] = datetime.now().isoformat()
        # Bind a fake numeric ticket id in HK session for demo control
        s["hk_stage"] = "S1"
        s["ticket_id"] = 999999
        session_set(chat_phone, s)
        return True
    return False

def _demo_hk_try_handle_or_schedule(chat_phone: str, text: str) -> Optional[Dict[str,Any]]:
    if DEMO_MODE_HK != "on":
        return None
    if _demo_hk_handle_confirm(chat_phone, text):
        return {"ok": True, "demo_hk": "confirmed"}
    if (text or "").strip() == ".":
        scheduled = _demo_hk_schedule_to_same_chat(chat_phone)
        return {"ok": True, "demo_hk": "scheduled" if scheduled else "already_scheduled"}
    return None

# ===================== Routing =====================
@app.get("/")
def index():
    outbound = "meta-cloud" if (WHATSAPP_CLOUD_TOKEN and WHATSAPP_CLOUD_PHONE_ID) else "console-only"
    db = "postgres" if using_pg() else f"sqlite:{SQLITE_PATH}"
    return (
        "WhatsApp webhook is running.<br>"
        f"DB: {db} · Outbound: {outbound}<br>"
        "GET /healthz · GET /webhook/whatsapp (verify) · POST /webhook/whatsapp (messages) · POST /_simulate"
    ), 200

@app.get("/healthz")
def healthz():
    return "ok", 200

# Webhook verification
@app.get("/webhook/whatsapp")
def whatsapp_verify():
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN and challenge:
        return challenge, 200
    return "forbidden", 403

# Inbound messages
@app.post("/webhook/whatsapp")
def webhook():
    payload = request.get_json(silent=True) or {}

    # Meta boilerplate: ignore status callbacks
    try:
        entry   = (payload.get("entry") or [])[0]
        change  = (entry.get("changes") or [])[0]
        value   = change.get("value") or {}
        msgs    = value.get("messages") or []
        statuses= value.get("statuses") or []
    except Exception:
        msgs, statuses = [], []
    if statuses:
        return jsonify({"ok": True, "kind": "status"}), 200
    if not msgs:
        return jsonify({"ok": True, "ignored": True}), 200

    # Dedup
    wamid = msgs[0].get("id")
    if wamid:
        if wamid_seen_before(wamid):
            return jsonify({"ok": True, "duplicate": True}), 200
        mark_wamid_seen(wamid)

    # Normalize
    from_phone, text, audio_url, media = _normalize_inbound(request)
    if not from_phone:
        return jsonify({"ok": True, "ignored": True}), 200

    # DEMO HK same-chat prompt
    demo = _demo_hk_try_handle_or_schedule(from_phone, text)
    if demo is not None:
        return jsonify(demo), 200

    # Resolve role
    role = resolve_role(from_phone)

    # Ensure a session exists and set role persistently
    s = session_get(from_phone)
    s["role"] = role
    session_set(from_phone, s)

    # Dispatch
    try:
        if role == "HK":
            result = hk_handle(from_phone, text, audio_url, media)
        else:
            result = guest_handle(from_phone, text, audio_url, media)
        return jsonify(result), 200
    except Exception as e:
        print(f"[ERR] webhook processing: {e}", flush=True)
        send_whatsapp(from_phone, f"❌ Error procesando el mensaje.")
        return jsonify({"ok": False, "error": str(e)}), 500

# --------- Internal notify endpoints (guarded) ---------
def _auth_ok(req) -> bool:
    token = (req.headers.get("Authorization") or "").replace("Bearer ","").strip()
    return (INTERNAL_NOTIFY_TOKEN == "") or (token == INTERNAL_NOTIFY_TOKEN)

@app.post("/notify/guest/final")
def notify_guest_final():
    if not _auth_ok(request):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    data = request.get_json(force=True)
    to_phone = _clean_phone(data.get("to_phone"))
    ticket_id = data.get("ticket_id")
    guest_name = (data.get("huesped_nombre") or "¡gracias!").strip()
    if not (to_phone and ticket_id):
        return jsonify({"ok": False, "error": "missing fields"}), 400
    body = COPY["guest_final"].format(name=guest_name, ticket_id=ticket_id)
    send_whatsapp(to_phone, body)
    return jsonify({"ok": True})

@app.post("/notify/tech/assignment")
def notify_tech_assignment():
    if not _auth_ok(request):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    data = request.get_json(force=True)
    to_phone = _clean_phone(data.get("to_phone"))
    ticket_id = int(data.get("ticket_id", 0))
    area = data.get("area") or ""
    prioridad = data.get("prioridad") or ""
    detalle = data.get("detalle") or ""
    ubicacion = data.get("ubicacion")
    if not (to_phone and ticket_id):
        return jsonify({"ok": False, "error": "missing fields"}), 400
    link = _ticket_link(ticket_id)
    body = f"📌 Asignado a ti.\n🔔 Nuevo ticket #{ticket_id}\nÁrea: {area}\nPrioridad: {prioridad}\nHabitación: {ubicacion or '—'}\nDetalle: {detalle or '—'}"
    if link: body += f"\nAbrir: {link}"
    send_whatsapp(to_phone, body)

    # bind HK session for that phone so actions affect this ticket
    s = session_get(to_phone)
    s["role"] = "HK"
    s["hk_stage"] = "S0"
    s["ticket_id"] = ticket_id
    session_set(to_phone, s)
    return jsonify({"ok": True})

# --------- Local simulator ---------
@app.post("/_simulate")
def simulate():
    data = request.get_json(force=True)
    from_phone = _clean_phone(data.get("from"))
    text = (data.get("text") or "").strip()
    audio_url = data.get("audio_url")
    media = data.get("media") or []
    if not from_phone:
        return jsonify({"ok": False, "error": "missing from"}), 400
    role = resolve_role(from_phone)
    try:
        if role == "HK":
            result = hk_handle(from_phone, text, audio_url, media)
        else:
            result = guest_handle(from_phone, text, audio_url, media)
        return jsonify(result)
    except Exception as e:
        print(f"[ERR] simulate: {e}", flush=True)
        return jsonify({"ok": False, "error": str(e)}), 500

# ===================== Boot =====================
if __name__ == "__main__":
    ensure_runtime_tables()
    print(f"[BOOT] WhatsApp webhook starting (DB={'PG' if using_pg() else 'SQLite'})", flush=True)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","5000")), debug=False, use_reloader=False)
