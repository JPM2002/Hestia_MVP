import os
import re
import json
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any, List

import requests
import tempfile
import mimetypes

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
import threading

# ----------------------------- Config -----------------------------

# Recepción: a quién notificar cuando queda PENDIENTE_APROBACION
# Ej: "+56911111111,+56922222222"
RECEPTION_PHONES = os.getenv("RECEPTION_PHONES", "+56996107169")

# --- DEMO HK confirm flow (no DB writes) ---
DEMO_MODE_HK = os.getenv("DEMO_MODE_HK", "on").lower()   # "on" | "off"
DEMO_HK_DELAY_SECS = int(os.getenv("DEMO_HK_DELAY_SECS", "40"))

# Hardcoded demo payload shown to Housekeeping
DEMO_HK_TICKET_ID = os.getenv("DEMO_HK_TICKET_ID", "HK-1042")
DEMO_HK_ROOM = os.getenv("DEMO_HK_ROOM", "312")
DEMO_HK_ITEM = os.getenv("DEMO_HK_ITEM", "toallas adicionales")
DEMO_HK_PRIORITY = os.getenv("DEMO_HK_PRIORITY", "MEDIA")
DEMO_HK_GUEST = os.getenv("DEMO_HK_GUEST", "Luis Miguel")
DEMO_HK_TIEMPO_ESPERADO = os.getenv("DEMO_HK_TIEMPO_ESPERADO", "10–15 minutos")

# Keyword that the HK chat must send to confirm
DEMO_HK_CONFIRM_KEYWORD = os.getenv("DEMO_HK_CONFIRM_KEYWORD", "confirmar ticket").lower()

# Hardcoded HK worker phones (Housekeeping staff)
HARDCODED_HK_PHONES: List[str] = [
    "+56983001018",  # Pedro (example)
    "+56956326272",  # Andrés (example)
]


# ----------------------------- Copy (5-star tone) -----------------------------
COPY = {
    "greet":
        "¡Hola! 👋 Soy tu asistente. Puedo ayudarte con mantención, housekeeping o room service.\n"
        "Para empezar, ¿me dices *tu nombre*? 🙂",
    "ask_room":
        "Gracias, *{name}*. ¿Cuál es tu *número de habitación*? 🏨",
    "ask_detail":
        "Perfecto. Ahora cuéntame qué ocurrió. Puedes *enviar un audio* o escribir el detalle. 🎤✍️",
    "ask_name":
        "🌟 ¡Bienvenido/a! ¿Con quién tengo el gusto? 😊\n"
        "Indícame *tu nombre* y luego *número de habitación* para poder ayudarte.",
    "need_more_for_ticket":
        "🙏 Me faltan algunos datos para crear el ticket. ¿Podrías enviarme el *detalle* o *habitación*, por favor?",
    "confirm_draft":
        "📝 Voy a registrar tu solicitud, ¿es correcto?\n\n{summary}\n\n"
        "Responde *SI* para confirmar o *NO* para editar.\n"
        "_Comandos rápidos_: AREA / PRIORIDAD / HAB / DETALLE …",
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
        "Detalle: {detalle}\n{link}",
    "ticket_pending_approval":
        "✅ ¡Gracias, {guest}! He registrado tu solicitud como *pendiente de aprobación* (ticket #{ticket_id}). "
        "Recepción la revisará en breve. 🛎️",
    "reception_new_pending":
        "📥 Ticket para *revisión/edición* #{ticket_id}\n"
        "Área: {area}\nPrioridad: {prioridad}\nHabitación: {habitacion}\n"
        "Detalle: {detalle}\n{link}\n\nAcción en sistema: Aprobar / Editar."
}


def txt(key: str, **kwargs) -> str:
    s = COPY.get(key, "")
    try:
        return s.format(**kwargs)
    except Exception:
        return s


# ---- Runtime persistence flags/fallbacks ----
RUNTIME_DB_OK = False          # flipped to True after tables are created successfully
FALLBACK_WAMIDS = set()        # in-memory dedupe if table missing

# In-memory conversational state for WhatsApp confirmation (legacy fallback)
PENDING: Dict[str, Dict[str, Any]] = {}

SESSION_TTL = 15 * 60  # seconds


def _only_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def is_hk_phone(phone: str) -> bool:
    digits = _only_digits(phone)
    for p in HARDCODED_HK_PHONES:
        if _only_digits(p) == digits:
            return True
    return False


def _compose_demo_hk_text(ticket_id: str, room: str, item: str, prioridad: str, guest: str) -> str:
    """
    Housekeeping message (no fecha/hora, uses 'Tiempo esperado', no 'en curso en la app'),
    ends asking for confirmation.
    """
    return (
        "🧹 Housekeeping — Ticket Entrante\n"
        f"Ticket: {ticket_id}\n"
        f"Área: HOUSEKEEPING | Prioridad: {prioridad}\n"
        f"Habitación: {room}\n"
        f"Solicitud: {item} (hab. {room})\n"
        "Instrucciones: Llevar 4 toallas (2 extra por si acaso), revisar amenities y reponer si faltan.\n"
        f"Tiempo esperado: {DEMO_HK_TIEMPO_ESPERADO}\n"
        f"Huésped: {guest}\n\n"
        "¿Está bien el ticket? Responde *CONFIRMAR TICKET* para continuar."
    )


def wamid_seen_before(wamid: str) -> bool:
    if RUNTIME_DB_OK:
        try:
            if using_pg():
                row = fetchone("SELECT 1 FROM runtime_wamids WHERE id=%s", (wamid,))
            else:
                row = fetchone("SELECT 1 FROM runtime_wamids WHERE id=?", (wamid,))
            return bool(row)
        except Exception as e:
            print(f"[WARN] wamid_seen_before failed: {e}", flush=True)
    # fallback
    return wamid in FALLBACK_WAMIDS


def mark_wamid_seen(wamid: str):
    if RUNTIME_DB_OK:
        try:
            if using_pg():
                execute(
                    "INSERT INTO runtime_wamids(id, seen_at) VALUES (%s, NOW()) "
                    "ON CONFLICT (id) DO NOTHING",
                    (wamid,),
                )
            else:
                execute(
                    "INSERT OR IGNORE INTO runtime_wamids(id, seen_at) VALUES (?, ?)",
                    (wamid, datetime.now().isoformat()),
                )
            return
        except Exception as e:
            print(f"[WARN] mark_wamid_seen failed: {e}", flush=True)
    # fallback
    FALLBACK_WAMIDS.add(wamid)
    if len(FALLBACK_WAMIDS) > 5000:
        FALLBACK_WAMIDS.clear()


# ----------------------------- Stage helpers -----------------------------
def _stage(s: dict) -> str:
    # Legacy guest DFA
    return s.get("stage") or "need_name"


def _set_stage(s: dict, stage: str):
    s["stage"] = stage
    s["ts"] = time.time()


PROMPT_COOLDOWN = 2  # seconds


def _should_prompt(s: dict, key: str) -> bool:
    last = s.get("last_prompt") or {}
    lp_key = last.get("key")
    lp_at = last.get("at", 0)
    if lp_key == key and (time.time() - lp_at) < PROMPT_COOLDOWN:
        return False
    s["last_prompt"] = {"key": key, "at": time.time()}
    return True


# ----------------------------- Conversation helpers (guest) -----------------------------
GREETING_WORDS = {
    "hola", "holi", "hello", "hi", "buenas", "buen dia", "buen día",
    "buenas tardes", "buenas noches", "que tal", "qué tal", "ayuda",
    "necesito ayuda", "consulta", "hey"
}


def is_smalltalk(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    # Only treat as smalltalk if the ENTIRE message is just a greeting
    return any(t == w for w in GREETING_WORDS)



def looks_like_command(s: str) -> bool:
    u = (s or "").strip().upper()
    return any(u.startswith(p) for p in COMMAND_PREFIXES)


def extract_name(text: str) -> Optional[str]:
    """
    Extract a likely name.
    Accepts:
      - plain: "Javier", "Luis Miguel"
      - with intro: "soy Javier", "me llamo Javier", "mi nombre es Javier"
      - with greeting: "hola soy Javier", "buenas, me llamo Javier"
    Rejects:
      - commands
      - messages that are only greetings
      - strings with digits or too many tokens
    """
    t_original = (text or "").strip()
    if not t_original or looks_like_command(t_original):
        return None

    t = t_original.lower()

    # If it's only a greeting, don't treat as name
    if is_smalltalk(t_original):
        return None

    # Strip common intros
    intro_patterns = [
        "soy ",
        "me llamo ",
        "mi nombre es ",
    ]

    candidate = t_original
    for p in intro_patterns:
        if p in t:
            idx = t.index(p) + len(p)
            candidate = t_original[idx:].strip()
            break

    # Strip leading greeting if present: "hola Javier", "buenas Javier"
    for gw in GREETING_WORDS:
        gw_l = gw.lower()
        if candidate.lower().startswith(gw_l + " "):
            candidate = candidate[len(gw_l):].strip()
            break

    # Now validate candidate as "1–4 alphabetic words, no digits"
    if any(ch.isdigit() for ch in candidate):
        return None

    parts = candidate.split()
    if not (1 <= len(parts) <= 4):
        return None

    for p in parts:
        if not re.match(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+$", p):
            return None

    # Normalize capitalization
    return " ".join(w.capitalize() for w in parts)



def _render_summary(area: str, prio: str, room: Optional[str], detail: str) -> str:
    return f"Área: {area}\nPrioridad: {prio}\nHabitación: {room or '—'}\nDetalle: {detail}"


def ensure_summary_in_session(s: Dict[str, Any]) -> str:
    area = s.get("area") or "MANTENCION"
    prio = s.get("prioridad") or "MEDIA"
    room = s.get("room")
    detalle = s.get("detalle") or ""
    return _render_summary(area, prio, room, detalle)


# Internal A→B auth (optional, used by /notify/*)
INTERNAL_NOTIFY_TOKEN = os.getenv("INTERNAL_NOTIFY_TOKEN", "")

# --- Auto-asignación / Notificaciones a técnicos ---
ASSIGNEE_MANTENCION_PHONE = os.getenv("ASSIGNEE_MANTENCION_PHONE", "+56956326272")  # Andrés
ASSIGNEE_HOUSEKEEPING_PHONE = os.getenv("ASSIGNEE_HOUSEKEEPING_PHONE", "+56983001018")  # Pedro
ASSIGNEE_ROOMSERVICE_PHONE = os.getenv("ASSIGNEE_ROOMSERVICE_PHONE", "")  # opcional

# Si quieres pegar link al ticket en el mensaje:
APP_BASE_URL = os.getenv("APP_BASE_URL", "")  # ej: "https://hestia-mvp.onrender.com"

# (Opcional) asignar en DB al crear (además de notificar)
AUTO_ASSIGN_ON_CREATE = os.getenv("AUTO_ASSIGN_ON_CREATE", "false").lower() in ("1", "true", "yes", "y")

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

# ----------------------------- DB helpers -----------------------------


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
        except Exception as e:
            print(f"[WARN] JSON codec register failed: {e}", flush=True)
        return conn
    conn = sqlite.connect(SQLITE_PATH, check_same_thread=False)
    conn.row_factory = sqlite.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
    except Exception:
        pass
    return conn


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
        try:
            conn.close()
        except Exception:
            pass


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
        try:
            conn.close()
        except Exception:
            pass


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
        try:
            conn.close()
        except Exception:
            pass


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
        try:
            conn.close()
        except Exception:
            pass


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


def _find_user_id_by_phone(phone: str) -> Optional[int]:
    """
    Try to find a users.id by matching digits-only phone.
    Works in both PG/SQLite (we normalize in Python).
    """
    try:
        rows = fetchall(
            "SELECT id, telefono FROM users WHERE activo = TRUE"
            if using_pg()
            else "SELECT id, telefono FROM users WHERE activo = 1",
            ()
        )
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


def _phones_from_env(s: str) -> List[str]:
    if not s:
        return []
    return [p.strip() for p in re.split(r"[,\s;]+", s) if p.strip()]


def _notify_reception_pending(ticket_id: int, area: str, prioridad: str, detalle: str, ubicacion: Optional[str]):
    recips = _phones_from_env(RECEPTION_PHONES)
    if not recips:
        return
    link = _ticket_link(ticket_id)
    body = txt(
        "reception_new_pending",
        ticket_id=ticket_id,
        area=area or "—",
        prioridad=prioridad or "—",
        habitacion=ubicacion or "—",
        detalle=detalle or "—",
        link=(f"Abrir: {link}" if link else "")
    )
    for ph in recips:
        send_whatsapp(ph, body)


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

    assigned_user_id = None
    if AUTO_ASSIGN_ON_CREATE:
        uid = _find_user_id_by_phone(to_phone)
        if uid:
            try:
                if using_pg():
                    execute("UPDATE tickets SET assigned_to=%s WHERE id=%s", (uid, ticket_id))
                    execute(
                        "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        (ticket_id, None, "ASIGNADO_AUTO", f"area={area_u}", datetime.now().isoformat())
                    )
                else:
                    execute("UPDATE tickets SET assigned_to=? WHERE id=?", (uid, ticket_id))
                    execute(
                        "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) "
                        "VALUES (?,?,?,?,?)",
                        (ticket_id, None, "ASIGNADO_AUTO", f"area={area_u}", datetime.now().isoformat())
                    )
                assigned_user_id = uid
            except Exception as e:
                print(f"[WARN] auto-assign failed: {e}", flush=True)

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


# Initialize runtime tables early (import-time; needed for gunicorn workers)
try:
    ensure_runtime_tables()
except Exception as _e:
    print(f"[WARN] ensure_runtime_tables at import failed: {_e}", flush=True)


# ----------------------------- NLP-ish parsing helpers -----------------------------
AREA_KEYWORDS = {
    "MANTENCION": ["ducha", "baño", "grifo", "llave", "aire", "ac", "fuga", "luz", "enchufe", "televisor", "tv",
                   "puerta", "ventana", "calefaccion", "calefacción"],
    "HOUSEKEEPING": ["toalla", "sábana", "sabana", "almohada", "limpieza", "aseo", "basura", "amenities",
                     "shampoo", "jabón", "sabanas"],
    "ROOMSERVICE": ["pedido", "hamburguesa", "sandwich", "desayuno", "cena", "comida", "room service", "cerveza",
                    "vino", "agua"],
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


def is_yes(text: str) -> bool:
    """
    Accept common confirmations with accents/casings: si, sí, yes, y, ok, dale, vale.
    Only if the message is basically just that word (optionally with punctuation/emoji).
    """
    t = (text or "").strip().lower()
    t = re.sub(r"[!.,;:()\[\]\-—_*~·•«»\"'`´]+$", "", t).strip()
    return t in {"si", "sí", "s", "y", "yes", "ok", "vale", "dale", "de acuerdo"}


def _gh_wants_handoff(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    patterns = [
        "hablar con alguien",
        "hablar con una persona",
        "hablar con humano",
        "humano",
        "recepcion",
        "recepción",
        "recepcionista",
        "quiero hablar con alguien",
        "llamar a recepción",
        "llamar a recepcion",
    ]
    return any(p in t for p in patterns)


# ----------------------------- SLA helpers -----------------------------
def sla_minutes(area: str, prioridad: str) -> Optional[int]:
    try:
        if using_pg():
            r = fetchone("SELECT max_minutes FROM slarules WHERE area=%s AND prioridad=%s",
                         (area, prioridad))
        else:
            r = fetchone("SELECT max_minutes FROM slarules WHERE area=? AND prioridad=?",
                         (area, prioridad))
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

    headers = {}
    if META_TOKEN:
        headers["Authorization"] = f"Bearer {META_TOKEN}"

    tmp_path = None
    try:
        r = requests.get(audio_url, headers=headers, timeout=60)
        if r.status_code in (401, 403):
            print(f"[WARN] media download unauthorized ({r.status_code}) -> {audio_url}", flush=True)
            return ""
        r.raise_for_status()
        content = r.content
        mime = (r.headers.get("Content-Type") or "audio/ogg").lower()

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

        client = OpenAI()
        with open(tmp_path, "rb") as fh:
            resp = client.audio.transcriptions.create(
                model="whisper-1",
                file=fh,
                temperature=0,
            )
        txt_out = getattr(resp, "text", "") or ""
        return txt_out.strip()
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
    # NEW: guard against empty recipient
    to = (to or "").strip()
    if not to:
        print(f"[WARN] send_whatsapp called with empty 'to'. Skipping. body={body!r}", flush=True)
        return

    to_clean = to.replace("whatsapp:", "").lstrip("+")
    msg = f"[OUT → {to_clean}] {body}"
    print(msg, flush=True)

    if not (META_TOKEN and META_PHONE_ID):
        return

    try:
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


def session_get(phone: str) -> Dict[str, Any]:
    s: Dict[str, Any] = {}
    if RUNTIME_DB_OK:
        try:
            if using_pg():
                row = fetchone("SELECT data FROM runtime_sessions WHERE phone=%s", (phone,))
                if row and row.get("data") is not None:
                    val = row["data"]
                    if isinstance(val, dict):
                        s = val
                    else:
                        if isinstance(val, (bytes, bytearray, memoryview)):
                            val = bytes(val).decode("utf-8", "ignore")
                        s = json.loads(val or "{}")
        except Exception as e:
            print(f"[WARN] session_get failed: {e}", flush=True)
    else:
        s = PENDING.get(phone) or {}

    if s and (time.time() - s.get("ts", 0) > SESSION_TTL):
        s = {}
    s["ts"] = time.time()

    session_set(phone, s)
    return s


def session_set(phone: str, data: Dict[str, Any]):
    data["ts"] = time.time()
    if RUNTIME_DB_OK:
        try:
            if using_pg():
                execute(
                    """
                    INSERT INTO runtime_sessions(phone, data, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (phone) DO UPDATE SET data=EXCLUDED.data, updated_at=EXCLUDED.updated_at
                """,
                    (phone, pg_extras.Json(data)),
                )
            else:
                execute(
                    """
                    INSERT OR REPLACE INTO runtime_sessions(phone, data, updated_at)
                    VALUES (?, ?, ?)
                """,
                    (phone, json.dumps(data), datetime.now().isoformat()),
                )
            return
        except Exception as e:
            print(f"[WARN] session_set failed: {e}", flush=True)

    PENDING[phone] = data


def session_clear(phone: str):
    if RUNTIME_DB_OK:
        try:
            if using_pg():
                execute("DELETE FROM runtime_sessions WHERE phone=%s", (phone,))
            else:
                execute("DELETE FROM runtime_sessions WHERE phone=?", (phone,))
            return
        except Exception as e:
            print(f"[WARN] session_clear failed: {e}", flush=True)
    if phone in PENDING:
        del PENDING[phone]


# ----------------------------- Ticket creation -----------------------------
def create_ticket(payload: Dict[str, Any], initial_status: str = "PENDIENTE_APROBACION") -> int:
    now = datetime.now()
    due_dt = compute_due(now, payload["area"], payload["prioridad"])
    due_at = due_dt.isoformat() if due_dt else None

    new_id = insert_and_get_id(
        """
        INSERT INTO tickets(org_id, hotel_id, area, prioridad, estado, detalle, canal_origen,
                            ubicacion, huesped_id, created_at, due_at,
                            assigned_to, created_by, confidence_score, qr_required)
        VALUES (%s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s)
        """ if using_pg() else
        """
        INSERT INTO tickets(org_id, hotel_id, area, prioridad, estado, detalle, canal_origen,
                            ubicacion, huesped_id, created_at, due_at,
                            assigned_to, created_by, confidence_score, qr_required)
        VALUES (?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?)
        """,
        (
            payload.get("org_id", ORG_ID_DEFAULT),
            payload.get("hotel_id", HOTEL_ID_DEFAULT),
            payload["area"],
            payload["prioridad"],
            initial_status,
            payload["detalle"],
            payload.get("canal_origen", "huesped_whatsapp"),
            payload.get("ubicacion"),
            payload.get("huesped_id"),
            now.isoformat(),
            due_at,
            None,
            None,
            float(payload.get("confidence_score", 0.85)),
            bool(payload.get("qr_required", False)),
        )
    )

    guest_phone = payload.get("huesped_phone") or payload.get("huesped_id")
    guest_name = payload.get("huesped_nombre")
    try:
        sets, params = [], []
        if guest_phone and table_has_column("tickets", "huesped_phone"):
            sets.append("huesped_phone=%s" if using_pg() else "huesped_phone=?")
            params.append(guest_phone)
        if guest_name and table_has_column("tickets", "huesped_nombre"):
            sets.append("huesped_nombre=%s" if using_pg() else "huesped_nombre=?")
            params.append(guest_name)
        if sets:
            params.append(new_id)
            sql = f"UPDATE tickets SET {', '.join(sets)} WHERE id=%s" if using_pg() else \
                f"UPDATE tickets SET {', '.join(sets)} WHERE id=?"
            execute(sql, tuple(params))
    except Exception as e:
        print(f"[WARN] could not persist guest phone/name: {e}", flush=True)

    execute(
        "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (%s, %s, %s, %s, %s)"
        if using_pg() else
        "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (?, ?, ?, ?, ?)",
        (new_id, None, "CREADO", "via whatsapp", now.isoformat())
    )
    if initial_status == "PENDIENTE_APROBACION":
        execute(
            "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (%s, %s, %s, %s, %s)"
            if using_pg() else
            "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (?, ?, ?, ?, ?)",
            (new_id, None, "PENDIENTE_APROBACION", "esperando aprobación de recepción", now.isoformat())
        )

    return new_id


# ----------------------------- Meta inbound helpers -----------------------------
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


def _normalize_inbound(req) -> Tuple[str, str, Optional[str]]:
    """
    Returns (from_phone, text, audio_url?)
    Supports:
      - Meta Cloud JSON
      - Twilio-form (if you ever test with it)
      - Raw JSON: {"from": "...", "text": "...", "audio_url": "..."}
    """
    ctype = (req.headers.get("Content-Type") or "").lower()

    if "application/x-www-form-urlencoded" in ctype:
        form = req.form
        from_ = clean_text(form.get("From"))
        body = clean_text(form.get("Body"))
        audio = None
        try:
            n = int(form.get("NumMedia", "0"))
        except Exception:
            n = 0
        if n > 0 and "audio" in (form.get("MediaContentType0") or ""):
            audio = form.get("MediaUrl0")
        return from_, body, audio

    data = {}
    try:
        data = req.get_json(force=True, silent=True) or {}
    except Exception:
        pass

    # Meta Cloud JSON
    try:
        entry = (data.get("entry") or [])[0]
        change = (entry.get("changes") or [])[0]
        msg = (change["value"].get("messages") or [])[0]
        from_ = msg.get("from", "")
        text = ""
        audio_url = None

        if msg.get("type") == "text":
            text = clean_text(msg.get("text", {}).get("body"))
        elif msg.get("type") == "audio":
            aud = msg.get("audio", {}) or {}
            audio_url = aud.get("link")
            if not audio_url and aud.get("id"):
                audio_url, _ = _meta_get_media_url(aud["id"])
        elif msg.get("type") == "interactive":
            try:
                text = msg["interactive"]["list_reply"]["title"]
            except Exception:
                text = ""

        if from_:
            return from_, text, audio_url
    except Exception:
        pass

    if any(k in data for k in ("from", "text", "audio_url")):
        return clean_text(data.get("from", "")), clean_text(data.get("text", "")), \
            clean_text(data.get("audio_url")) or None

    return "", "", None


# ----------------------------- DEMO HK flow (guest-side demo only) -----------------------------
def _demo_hk_schedule_to_same_chat(chat_phone: str):
    """
    Schedules a delayed HK message to the SAME chat (chat_phone) after DEMO_HK_DELAY_SECS.
    Uses hardcoded demo fields. Marks session as 'pending' for confirmation.
    """
    s = session_get(chat_phone)
    if s.get("demo_hk_scheduled"):
        return False

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
            if not payload:
                payload = {
                    "ticket_id": DEMO_HK_TICKET_ID,
                    "room": DEMO_HK_ROOM,
                    "item": DEMO_HK_ITEM,
                    "prioridad": DEMO_HK_PRIORITY,
                    "guest": DEMO_HK_GUEST,
                }
            body = _compose_demo_hk_text(
                payload["ticket_id"], payload["room"], payload["item"], payload["prioridad"], payload["guest"]
            )
            send_whatsapp(chat_phone, body)
            ss["demo_hk_prompt_sent"] = True
            session_set(chat_phone, ss)
        except Exception as e:
            print(f"[WARN] demo HK scheduler failed: {e}", flush=True)

    threading.Thread(target=_run, daemon=True).start()
    return True


def _demo_hk_handle_confirm(chat_phone: str, text: str) -> bool:
    """
    If the SAME chat is in pending state and message matches confirm keyword,
    send confirmation and mark as not pending. Returns True if handled.
    """
    if DEMO_MODE_HK != "on":
        return False
    t = (text or "").strip().lower()
    s = session_get(chat_phone)
    if s.get("demo_hk_pending") and DEMO_HK_CONFIRM_KEYWORD in t:
        send_whatsapp(
            chat_phone,
            "✅ Ticket confirmado. El tiempo ha comenzado a correr. Avisaremos al huésped."
        )
        s["demo_hk_pending"] = False
        s["demo_hk_confirmed_at"] = datetime.now().isoformat()
        session_set(chat_phone, s)
        return True
    return False


def _demo_hk_try_handle_or_schedule(chat_phone: str, text: str) -> Optional[Dict[str, Any]]:
    """
    DEMO router (only for guest chats, not HK workers):
      - If message is '.', schedule the prompt to SAME chat after DEMO_HK_DELAY_SECS.
      - Else if message is 'confirmar ticket', confirm.
      - Returns a small dict when consumed; None to continue normal flow.
    """
    if DEMO_MODE_HK != "on":
        return None
    if is_hk_phone(chat_phone):
        return None

    if _demo_hk_handle_confirm(chat_phone, text):
        return {"ok": True, "demo_hk": "confirmed"}

    if (text or "").strip() == ".":
        scheduled = _demo_hk_schedule_to_same_chat(chat_phone)
        return {"ok": True, "demo_hk": "scheduled" if scheduled else "already_scheduled"}

    return None


# ----------------------------- HK helpers (workers DFA) -----------------------------
def _resolve_hk_context(from_phone: str, s: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if s.get("hk_context"):
        return s["hk_context"]

    phone_digits = _only_digits(from_phone)
    try:
        rows = fetchall(
            """
            SELECT u.id AS user_id,
                   u.area,
                   u.telefono,
                   u.username,
                   ou.org_id,
                   ou.default_hotel_id AS hotel_id
            FROM users u
            LEFT JOIN orgusers ou ON u.id = ou.user_id
            WHERE u.activo = TRUE
            """,
            ()
        )
        for r in rows or []:
            tel = r.get("telefono") or ""
            if _only_digits(tel) == phone_digits:
                ctx = {
                    "user_id": r.get("user_id"),
                    "area": r.get("area") or "HOUSEKEEPING",
                    "telefono": tel,
                    "username": r.get("username") or "",
                    "org_id": r.get("org_id") or ORG_ID_DEFAULT,
                    "hotel_id": r.get("hotel_id") or HOTEL_ID_DEFAULT,
                }
                s["hk_context"] = ctx
                session_set(from_phone, s)
                return ctx
    except Exception as e:
        print(f"[WARN] _resolve_hk_context failed: {e}", flush=True)
    return None


def _hk_send_main_menu(phone: str):
    body = (
        "🏨 Menú Housekeeping\n"
        "1) Mis tareas abiertas\n"
        "2) Aceptar tareas\n"
        "3) Tareas por habitación / área\n"
        "4) Mi resumen de hoy\n"
        "5) Ayuda / contactar supervisor"
    )
    send_whatsapp(phone, body)


def _hk_show_my_open_tasks(from_phone: str, s: Dict[str, Any]):
    ctx = _resolve_hk_context(from_phone, s)
    if not ctx:
        send_whatsapp(
            from_phone,
            "No encontré un usuario activo asociado a tu número. "
            "Pide al administrador que registre tu teléfono en el sistema."
        )
        return

    user_id = ctx["user_id"]
    try:
        sql = (
            "SELECT id, area, prioridad, ubicacion, detalle, estado "
            "FROM tickets "
            "WHERE assigned_to=%s "
            "  AND estado IN ('ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO') "
            "  AND deleted_at IS NULL "
            "ORDER BY due_at NULLS LAST, created_at DESC"
            if using_pg() else
            "SELECT id, area, prioridad, ubicacion, detalle, estado "
            "FROM tickets "
            "WHERE assigned_to=? "
            "  AND estado IN ('ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO') "
            "  AND deleted_at IS NULL "
            "ORDER BY created_at DESC"
        )
        rows = fetchall(sql, (user_id,))
    except Exception as e:
        print(f"[WARN] _hk_show_my_open_tasks failed: {e}", flush=True)
        rows = []

    if not rows:
        send_whatsapp(
            from_phone,
            "No tienes tareas abiertas asignadas en este momento.\n"
            "Escribe *M* para volver al menú."
        )
        return

    lines = ["Estas son tus tareas abiertas:"]
    for r in rows:
        detalle = (r.get("detalle") or "")[:120]
        lines.append(
            f"- #{r['id']} [{r.get('estado')}] hab. {r.get('ubicacion')}: {detalle}"
        )
    lines.append("\nEscribe *M* para volver al menú.")
    send_whatsapp(from_phone, "\n".join(lines))


def _hk_show_available_tasks(from_phone: str, s: Dict[str, Any]):
    ctx = _resolve_hk_context(from_phone, s)
    if not ctx:
        send_whatsapp(
            from_phone,
            "No encontré un usuario activo asociado a tu número. "
            "Pide al administrador que registre tu teléfono en el sistema."
        )
        return

    hotel_id = ctx["hotel_id"]
    area = "HOUSEKEEPING"
    try:
        sql = (
            "SELECT id, prioridad, ubicacion, detalle, estado "
            "FROM tickets "
            "WHERE hotel_id=%s "
            "  AND area=%s "
            "  AND estado IN ('PENDIENTE','ASIGNADO','PENDIENTE_APROBACION') "
            "  AND deleted_at IS NULL "
            "ORDER BY created_at ASC LIMIT 10"
            if using_pg() else
            "SELECT id, prioridad, ubicacion, detalle, estado "
            "FROM tickets "
            "WHERE hotel_id=? "
            "  AND area=? "
            "  AND estado IN ('PENDIENTE','ASIGNADO','PENDIENTE_APROBACION') "
            "  AND deleted_at IS NULL "
            "ORDER BY created_at ASC LIMIT 10"
        )
        rows = fetchall(sql, (hotel_id, area))
    except Exception as e:
        print(f"[WARN] _hk_show_available_tasks failed: {e}", flush=True)
        rows = []

    if not rows:
        send_whatsapp(
            from_phone,
            "No hay tareas disponibles para aceptar en este momento.\n"
            "Escribe *M* para volver al menú."
        )
        s["hk_available_ticket_ids"] = []
        session_set(from_phone, s)
        return

    s["hk_available_ticket_ids"] = [int(r["id"]) for r in rows]
    session_set(from_phone, s)

    lines = ["Tareas disponibles para aceptar:"]
    for r in rows:
        detalle = (r.get("detalle") or "")[:120]
        lines.append(
            f"- #{r['id']} [{r.get('prioridad')}] hab. {r.get('ubicacion')}: {detalle}"
        )
    lines.append(
        "\nResponde con el número de *ticket* para seleccionarlo (por ejemplo `1042`), "
        "o escribe *M* para volver al menú."
    )
    send_whatsapp(from_phone, "\n".join(lines))


def _hk_load_ticket(ticket_id: int) -> Optional[Dict[str, Any]]:
    try:
        sql = (
            "SELECT id, area, prioridad, ubicacion, detalle, estado "
            "FROM tickets WHERE id=%s"
            if using_pg() else
            "SELECT id, area, prioridad, ubicacion, detalle, estado "
            "FROM tickets WHERE id=?"
        )
        return fetchone(sql, (ticket_id,))
    except Exception as e:
        print(f"[WARN] _hk_load_ticket failed: {e}", flush=True)
        return None


def _hk_accept_ticket(ctx: Dict[str, Any], ticket_id: int):
    user_id = ctx["user_id"]
    now_iso = datetime.now().isoformat()
    try:
        if using_pg():
            execute(
                "UPDATE tickets "
                "SET assigned_to=%s, estado='ACEPTADO', accepted_at=NOW() "
                "WHERE id=%s",
                (user_id, ticket_id),
            )
            execute(
                "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) "
                "VALUES (%s,%s,%s,%s,%s)",
                (ticket_id, user_id, "ACEPTADO_HK", "aceptado via WhatsApp HK", now_iso),
            )
        else:
            execute(
                "UPDATE tickets "
                "SET assigned_to=?, estado='ACEPTADO', accepted_at=datetime('now') "
                "WHERE id=?",
                (user_id, ticket_id),
            )
            execute(
                "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) "
                "VALUES (?,?,?,?,?)",
                (ticket_id, user_id, "ACEPTADO_HK", "aceptado via WhatsApp HK", now_iso),
            )
    except Exception as e:
        print(f"[WARN] _hk_accept_ticket failed: {e}", flush=True)


def _hk_reject_ticket(ctx: Dict[str, Any], ticket_id: int):
    user_id = ctx["user_id"]
    now_iso = datetime.now().isoformat()
    try:
        execute(
            "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) "
            "VALUES (%s,%s,%s,%s,%s)"
            if using_pg() else
            "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) "
            "VALUES (?,?,?,?,?)",
            (ticket_id, user_id, "RECHAZADO_HK", "rechazado via WhatsApp HK", now_iso),
        )
    except Exception as e:
        print(f"[WARN] _hk_reject_ticket failed: {e}", flush=True)


def _hk_send_room_area_menu(from_phone: str):
    send_whatsapp(
        from_phone,
        "Búsqueda de tareas:\n"
        "1) Buscar por habitación\n"
        "2) Buscar por área\n\n"
        "Responde con 1 o 2, o escribe *M* para volver al menú."
    )


def _hk_list_tasks_by_room(from_phone: str, s: Dict[str, Any], room: str):
    ctx = _resolve_hk_context(from_phone, s)
    if not ctx:
        send_whatsapp(
            from_phone,
            "No encontré un usuario activo asociado a tu número. "
            "Pide al administrador que registre tu teléfono en el sistema."
        )
        return

    hotel_id = ctx["hotel_id"]
    try:
        sql = (
            "SELECT id, area, prioridad, detalle, estado "
            "FROM tickets "
            "WHERE hotel_id=%s AND ubicacion=%s AND deleted_at IS NULL "
            "ORDER BY created_at DESC LIMIT 10"
            if using_pg() else
            "SELECT id, area, prioridad, detalle, estado "
            "FROM tickets "
            "WHERE hotel_id=? AND ubicacion=? AND deleted_at IS NULL "
            "ORDER BY created_at DESC LIMIT 10"
        )
        rows = fetchall(sql, (hotel_id, room))
    except Exception as e:
        print(f"[WARN] _hk_list_tasks_by_room failed: {e}", flush=True)
        rows = []

    if not rows:
        send_whatsapp(
            from_phone,
            f"No encontré tickets para la habitación {room}.\n"
            "Puedes enviar otro número de habitación o escribir *M* para volver al menú."
        )
        return

    lines = [f"Tickets para la habitación {room}:"]
    for r in rows:
        detalle = (r.get("detalle") or "")[:120]
        lines.append(
            f"- #{r['id']} [{r.get('estado')}] ({r.get('prioridad')}) {detalle}"
        )
    lines.append("\nEnvía otro número de habitación o escribe *M* para volver al menú.")
    send_whatsapp(from_phone, "\n".join(lines))


def _hk_list_areas(from_phone: str):
    areas = ["HOUSEKEEPING", "MANTENCION", "ROOMSERVICE"]
    lines = [
        "Áreas disponibles:",
    ]
    for a in areas:
        lines.append(f"- {a}")
    lines.append(
        "\nEscribe el *código exacto* del área (por ejemplo HOUSEKEEPING) "
        "o *M* para volver al menú."
    )
    send_whatsapp(from_phone, "\n".join(lines))


def _hk_list_tasks_by_area(from_phone: str, s: Dict[str, Any], area_code: str):
    ctx = _resolve_hk_context(from_phone, s)
    if not ctx:
        send_whatsapp(
            from_phone,
            "No encontré un usuario activo asociado a tu número. "
            "Pide al administrador que registre tu teléfono en el sistema."
        )
        return

    hotel_id = ctx["hotel_id"]
    area_u = area_code.upper()
    try:
        sql = (
            "SELECT id, prioridad, ubicacion, detalle, estado "
            "FROM tickets "
            "WHERE hotel_id=%s AND area=%s AND deleted_at IS NULL "
            "ORDER BY created_at DESC LIMIT 10"
            if using_pg() else
            "SELECT id, prioridad, ubicacion, detalle, estado "
            "FROM tickets "
            "WHERE hotel_id=? AND area=? AND deleted_at IS NULL "
            "ORDER BY created_at DESC LIMIT 10"
        )
        rows = fetchall(sql, (hotel_id, area_u))
    except Exception as e:
        print(f"[WARN] _hk_list_tasks_by_area failed: {e}", flush=True)
        rows = []

    if not rows:
        send_whatsapp(
            from_phone,
            f"No encontré tickets para el área {area_u}.\n"
            "Puedes enviar otro área válida o escribir *M* para volver al menú."
        )
        return

    lines = [f"Tickets para el área {area_u}:"]
    for r in rows:
        detalle = (r.get("detalle") or "")[:120]
        lines.append(
            f"- #{r['id']} [{r.get('estado')}] hab. {r.get('ubicacion')} ({r.get('prioridad')}): {detalle}"
        )
    lines.append("\nEnvía otro área o escribe *M* para volver al menú.")
    send_whatsapp(from_phone, "\n".join(lines))


def _hk_show_today_summary(from_phone: str, s: Dict[str, Any]):
    ctx = _resolve_hk_context(from_phone, s)
    if not ctx:
        send_whatsapp(
            from_phone,
            "No encontré un usuario activo asociado a tu número. "
            "Pide al administrador que registre tu teléfono en el sistema."
        )
        return

    user_id = ctx["user_id"]
    today_str = datetime.now().date().isoformat()

    try:
        if using_pg():
            resolved_rows = fetchall(
                "SELECT id, area, prioridad, ubicacion, detalle, finished_at "
                "FROM tickets "
                "WHERE assigned_to=%s AND finished_at >= CURRENT_DATE AND deleted_at IS NULL",
                (user_id,),
            )
        else:
            # For SQLite we filter by date in Python
            resolved_rows_raw = fetchall(
                "SELECT id, area, prioridad, ubicacion, detalle, finished_at "
                "FROM tickets "
                "WHERE assigned_to=? AND finished_at IS NOT NULL AND deleted_at IS NULL",
                (user_id,),
            )
            resolved_rows = []
            for r in resolved_rows_raw:
                fa = r.get("finished_at")
                if fa and str(fa)[:10] == today_str:
                    resolved_rows.append(r)
    except Exception as e:
        print(f"[WARN] _hk_show_today_summary resolved query failed: {e}", flush=True)
        resolved_rows = []

    try:
        active_rows = fetchall(
            "SELECT id, area, prioridad, ubicacion, detalle, estado "
            "FROM tickets "
            "WHERE assigned_to=%s "
            "  AND estado IN ('ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO') "
            "  AND deleted_at IS NULL"
            if using_pg() else
            "SELECT id, area, prioridad, ubicacion, detalle, estado "
            "FROM tickets "
            "WHERE assigned_to=? "
            "  AND estado IN ('ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO') "
            "  AND deleted_at IS NULL",
            (user_id,),
        )
    except Exception as e:
        print(f"[WARN] _hk_show_today_summary active query failed: {e}", flush=True)
        active_rows = []

    worker_name = ctx.get("username") or ctx.get("name") or "tu usuario"
    lines: list[str] = [f"Resumen de hoy para {worker_name}:"]

    if resolved_rows:
        lines.append("")
        lines.append("Tickets resueltos hoy:")
        for r in resolved_rows:
            lines.append(
                f"- #{r.get('id')} "
                f"[{(r.get('area') or '—')} · {(r.get('prioridad') or '—')}] "
                f"hab. {(r.get('ubicacion') or '—')} – {(r.get('detalle') or '')}"
            )

    if active_rows:
        lines.append("")
        lines.append("Tickets activos:")
        for r in active_rows:
            lines.append(
                f"- #{r.get('id')} "
                f"[{(r.get('estado') or '—')} · {(r.get('prioridad') or '—')}] "
                f"hab. {(r.get('ubicacion') or '—')} – {(r.get('detalle') or '')}"
            )

    if not resolved_rows and not active_rows:
        lines.append("")
        lines.append("Hoy no se registran tickets resueltos ni activos a tu nombre.")

    send_whatsapp(from_phone, "\n".join(lines))

@app.route("/webhook/whatsapp", methods=["GET", "POST"])
def whatsapp_webhook():
    # 1) Verification (Meta calls GET once when you set up webhook)
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
            # Return the challenge so Meta accepts the webhook
            return challenge, 200
        return "Verification failed", 403

    # 2) Incoming messages (Meta calls POST for each message)
    from_phone, text, audio_url = _normalize_inbound(request)

    # NEW: ignore status / malformed webhooks that don't have a real user message
    if not from_phone and not text and not audio_url:
        print("[INFO] Webhook without user message (status or malformed). Ignoring.", flush=True)
        return jsonify({"status": "ignored", "reason": "no_message"}), 200

    # Optional: dedupe by WhatsApp message id (wamid) if present
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}

    wamid = None
    try:
        entry = (data.get("entry") or [])[0]
        change = (entry.get("changes") or [])[0]
        msg = (change["value"].get("messages") or [])[0]
        wamid = msg.get("id")
    except Exception:
        pass

    if wamid:
        if wamid_seen_before(wamid):
            # Already processed this message, acknowledge again
            return jsonify({"status": "duplicate"}), 200
        mark_wamid_seen(wamid)

    # If demo HK flow wants to consume this message, handle it
    demo_result = _demo_hk_try_handle_or_schedule(from_phone, text)
    if demo_result is not None:
        # Already handled by demo flow
        return jsonify({"status": "ok", "demo": demo_result}), 200

    # Decide if this is HK worker or guest
    if is_hk_phone(from_phone):
        _handle_hk_message(from_phone, text)
    else:
        _handle_guest_message(from_phone, text, audio_url)

    return jsonify({"status": "ok"}), 200


def _handle_hk_message(from_phone: str, text: str):
    s = session_get(from_phone)
    t = (text or "").strip().upper()

    # Basic menu navigation
    if t in {"M", "MENU"}:
        _hk_send_main_menu(from_phone)
        s["hk_state"] = "MENU"
        session_set(from_phone, s)
        return

    state = s.get("hk_state") or "MENU"

    if state == "MENU":
        if t == "1":
            _hk_show_my_open_tasks(from_phone, s)
        elif t == "2":
            _hk_show_available_tasks(from_phone, s)
        elif t == "3":
            _hk_send_room_area_menu(from_phone)
            s["hk_state"] = "ROOM_AREA_MENU"
            session_set(from_phone, s)
        elif t == "4":
            _hk_show_today_summary(from_phone, s)
        elif t == "5":
            send_whatsapp(
                from_phone,
                "Si necesitas apoyo del supervisor, por favor comunícate por el canal interno habitual."
            )
        else:
            _hk_send_main_menu(from_phone)
        return

    if state == "ROOM_AREA_MENU":
        if t == "1":
            send_whatsapp(from_phone, "Envía el número de habitación (por ejemplo 312).")
            s["hk_state"] = "ASK_ROOM"
            session_set(from_phone, s)
            return
        elif t == "2":
            _hk_list_areas(from_phone)
            s["hk_state"] = "ASK_AREA"
            session_set(from_phone, s)
            return
        else:
            _hk_send_main_menu(from_phone)
            s["hk_state"] = "MENU"
            session_set(from_phone, s)
            return

    if state == "ASK_ROOM":
        room = re.sub(r"\D", "", text or "")
        if not room:
            send_whatsapp(from_phone, "No entendí la habitación. Envía solo el número, por ejemplo 312.")
            return
        _hk_list_tasks_by_room(from_phone, s, room)
        # Stay in ASK_ROOM so they can query again
        return

    if state == "ASK_AREA":
        area = (text or "").strip().upper()
        if area in {"HOUSEKEEPING", "MANTENCION", "ROOMSERVICE"}:
            _hk_list_tasks_by_area(from_phone, s, area)
            # Stay in ASK_AREA so they can query again
            return
        send_whatsapp(
            from_phone,
            "Área no válida. Usa HOUSEKEEPING, MANTENCION o ROOMSERVICE, o escribe *M* para volver al menú."
        )
        return

    # Fallback: if state unknown, show menu
    _hk_send_main_menu(from_phone)
    s["hk_state"] = "MENU"
    session_set(from_phone, s)


def _handle_guest_message(from_phone: str, text: str, audio_url: str | None):
    s = session_get(from_phone)

    # If audio, optionally transcribe and treat as text
    if audio_url and not text:
        transcript = transcribe_audio(audio_url)
        text = transcript or ""

    t = (text or "").strip()

    # Very simple guest flow example:
    # You can replace this with your full DFA (need_name → need_room → need_detail → confirm, etc.)
    stage = s.get("stage") or "need_name"

    if stage == "need_name":
        name = extract_name(t)
        if not name:
            if _should_prompt(s, "ask_name"):
                send_whatsapp(from_phone, txt("ask_name"))
            session_set(from_phone, s)
            return
        s["guest_name"] = name
        s["stage"] = "need_room"
        session_set(from_phone, s)
        send_whatsapp(from_phone, txt("ask_room", name=name))
        return

    if stage == "need_room":
        room = guess_room(t)
        if not room:
            if _should_prompt(s, "ask_room"):
                send_whatsapp(from_phone, txt("ask_room", name=s.get("guest_name", "")))
            session_set(from_phone, s)
            return
        s["room"] = room
        s["stage"] = "need_detail"
        session_set(from_phone, s)
        if _should_prompt(s, "ask_detail"):
            send_whatsapp(from_phone, txt("ask_detail"))
        return

    if stage == "need_detail":
        detalle = t
        if not detalle:
            if _should_prompt(s, "ask_detail"):
                send_whatsapp(from_phone, txt("ask_detail"))
            session_set(from_phone, s)
            return

        s["detalle"] = detalle
        s["area"] = guess_area(detalle)
        s["prioridad"] = guess_priority(detalle)

        summary = ensure_summary_in_session(s)
        s["stage"] = "confirm"
        session_set(from_phone, s)

        send_whatsapp(from_phone, txt("confirm_draft", summary=summary))
        return

    if stage == "confirm":
        if is_yes(t):
            payload = {
                "org_id": ORG_ID_DEFAULT,
                "hotel_id": HOTEL_ID_DEFAULT,
                "area": s.get("area", "MANTENCION"),
                "prioridad": s.get("prioridad", "MEDIA"),
                "detalle": s.get("detalle", ""),
                "canal_origen": "huesped_whatsapp",
                "ubicacion": s.get("room"),
                "huesped_id": from_phone,
                "huesped_phone": from_phone,
                "huesped_nombre": s.get("guest_name", ""),
            }
            ticket_id = create_ticket(payload, initial_status="PENDIENTE_APROBACION")
            send_whatsapp(
                from_phone,
                txt("ticket_created", guest=s.get("guest_name", "Huésped"), ticket_id=ticket_id)
            )
            _notify_reception_pending(
                ticket_id,
                payload["area"],
                payload["prioridad"],
                payload["detalle"],
                payload.get("ubicacion"),
            )
            session_clear(from_phone)
            return
        else:
            send_whatsapp(from_phone, txt("edit_help"))
            # You could add parsing of AREA/PRIORIDAD/HAB/DETALLE commands here
            return

    # Fallback if stage unknown
    session_clear(from_phone)
    send_whatsapp(from_phone, txt("greet"))

if __name__ == "__main__":
    ensure_runtime_tables()  # safe to call again
    print(f"[BOOT] WhatsApp webhook starting on port {PORT} (DB={'PG' if using_pg() else 'SQLite'})", flush=True)
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)