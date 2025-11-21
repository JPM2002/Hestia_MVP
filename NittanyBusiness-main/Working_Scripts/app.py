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

from services.guest_llm import analyze_guest_message, render_confirm_draft
from services.faq_llm import maybe_answer_faq
#TODO
# Prefer a specific FAQ DSN; fall back to your existing ones.
FAQ_PG_DSN = os.getenv("FAQ_PG_DSN") or os.getenv("PG_DSN") or os.getenv("DATABASE_URL")


# ----------------------------- Config -----------------------------

# Recepción: a quién notificar cuando queda PENDIENTE_APROBACION
# Ej: "+56911111111,+56922222222"
RECEPTION_PHONES = os.getenv("RECEPTION_PHONES", "+56996107169")
# Housekeeping (Andrés): a quién notificar cuando hay ticket nuevo HK
HK_TECH_PHONES = os.getenv("HK_TECH_PHONES", "+56956326272")
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

# ----------------------------- Hardcoded roles by phone (temporary) -----------------------------
# NOTE: this is just a bootstrap mapping while we wire proper DB-based routing.
# Phones are in E.164 form with '+' for readability, but we always compare on digits-only.

# HARDCODED_ROLE_PHONES: Dict[str, List[str]] = {
#     # Front desk / reception
#     "RECEPCION": [
#         "+4915221317651",  # Javier
#     ],
#     # Supervisors
#     "SUPERVISOR": [
#         "+56996107169",    # Sebas
#     ],
#     # Management
#     "GERENTE": [
#         "+56983001018",    # Pedro
#     ],
#     # Housekeeping workers (mucamas)
#     "HOUSEKEEPING": [
#         "+56956326272",    # Andrés (mucama)
#         "+56975620537",    # Borisbo (mucama)
#     ],
# }

# Backward-compatibility for the existing HK flow:
#HARDCODED_HK_PHONES: List[str] = HARDCODED_ROLE_PHONES.get("HOUSEKEEPING", [])


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
        "Nuestro equipo ya está atendiendo tu solicitud.",
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
        "Detalle: {detalle}\n{link}\n\nAcción en sistema: Aprobar / Editar.",
        "onboarding_block":
        "Hola 👋. Para poder usar todas las funciones del sistema por WhatsApp, "
        "primero debes completar tu proceso de verificación en Hestia.\n\n"
        "Por favor continúa con el proceso de verificación de tu cuenta "
        "para poder utilizar todas las funciones del sistema.",
    # NEW: mensaje específico para HK (Andrés)
    "hk_new_pending":
        "🧹 Hola Andrés, hay un nuevo ticket de *{area}* #{ticket_id}.\n"
        "Prioridad: {prioridad}\n"
        "Habitación: {habitacion}\n"
        "Detalle: {detalle}\n"
        "{link}",
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


def resolve_role_by_phone(phone: str) -> Optional[str]:
    """
    Resolve role from the users table instead of hardcoded phones.
    Returns one of: RECEPCION, SUPERVISOR, GERENTE, HOUSEKEEPING, or None.
    """
    row = _get_user_by_phone(phone)
    if not row:
        return None
    role = (row.get("role") or "").strip().upper()
    # Optional: restrict to known internal roles
    if role in {"RECEPCION", "SUPERVISOR", "GERENTE", "HOUSEKEEPING"}:
        return role
    return None



def is_hk_phone(phone: str) -> bool:
    row = _get_user_by_phone(phone)
    if not row:
        return False
    return (row.get("role") or "").strip().upper() == "HOUSEKEEPING"




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
ASSIGNEE_MANTENCION_PHONE   = os.getenv("ASSIGNEE_MANTENCION_PHONE", "")  # legacy fallback
ASSIGNEE_HOUSEKEEPING_PHONE = os.getenv("ASSIGNEE_HOUSEKEEPING_PHONE", "")
ASSIGNEE_ROOMSERVICE_PHONE  = os.getenv("ASSIGNEE_ROOMSERVICE_PHONE", "")

# Si quieres pegar link al ticket en el mensaje:
APP_BASE_URL = os.getenv("APP_BASE_URL", "")  # ej: "https://hestia-mvp.onrender.com"

# (Opcional) asignar en DB al crear (además de notificar)
AUTO_ASSIGN_ON_CREATE = os.getenv("AUTO_ASSIGN_ON_CREATE", "false").lower() in ("1", "true", "yes", "y")

PORT = int(os.getenv("PORT", "5000"))  # <- default 5000
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SQLITE_PATH = os.getenv("DATABASE_PATH", "hestia_V2.db")

# Org/Hotel fallback (used when creating tickets)
ORG_ID_DEFAULT = int(os.getenv("DEMO_ORG_ID", "2"))
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

def _find_technician_for_area(area_u: str,
                              org_id: int,
                              hotel_id: int) -> Optional[Tuple[int, Optional[str]]]:
    """
    Return (user_id, telefono) for a TECNICO in the given area.
    For ahora se ignoran org_id / hotel_id (1 hotel); se deja la firma preparada.
    Preferimos técnicos con teléfono no nulo.
    """
    params = (area_u,)
    if using_pg():
        row = query_one(
            """
            SELECT u.id, u.telefono
            FROM users u
            WHERE u.role = 'TECNICO'
              AND UPPER(COALESCE(u.area, '')) = %s
              AND u.activo = TRUE
            ORDER BY (u.telefono IS NULL), u.id
            LIMIT 1
            """,
            params,
        )
    else:
        row = query_one(
            """
            SELECT u.id, u.telefono
            FROM users u
            WHERE u.role = 'TECNICO'
              AND UPPER(COALESCE(u.area, '')) = ?
              AND u.activo = 1
            ORDER BY (u.telefono IS NULL), u.id
            LIMIT 1
            """,
            params,
        )
    if not row:
        return None
    return row["id"], row["telefono"]



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

def _get_user_by_phone(phone: str) -> Optional[Dict[str, Any]]:
    """
    Returns the users.* row (including initialized) for this phone,
    matching by digits-only phone and only active users.
    """
    try:
        rows = fetchall(
            "SELECT id, username, role, area, telefono, activo, is_superadmin, "
            "       initialized, phone_verified, onboarding_step "
            "FROM users "
            "WHERE activo = TRUE"
            if using_pg()
            else
            "SELECT id, username, role, area, telefono, activo, is_superadmin, "
            "       initialized, phone_verified, onboarding_step "
            "FROM users "
            "WHERE activo = 1",
            ()
        )
        target = _only_digits(phone)
        for r in rows or []:
            tel = r.get("telefono") or ""
            if _only_digits(tel) == target:
                return r
    except Exception as e:
        print(f"[WARN] _get_user_by_phone failed: {e}", flush=True)
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

def _notify_hk_pending(ticket_id: int, area: str, prioridad: str, detalle: str, ubicacion: Optional[str]):
    """
    Notifica a housekeeping (Andrés) cuando se crea un ticket HK
    desde el flujo de huésped.
    """
    recips = _phones_from_env(HK_TECH_PHONES)
    if not recips:
        return

    link = _ticket_link(ticket_id)
    body = txt(
        "hk_new_pending",
        ticket_id=ticket_id,
        area=area or "—",
        prioridad=prioridad or "—",
        habitacion=ubicacion or "—",
        detalle=detalle or "—",
        link=(f"Abrir: {link}" if link else ""),
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


def _auto_assign_and_notify(
    ticket_id: int,
    area: str,
    prioridad: str,
    detalle: str,
    ubicacion: Optional[str],
    org_id: Optional[int] = None,
    hotel_id: Optional[int] = None,
):
    """
    - Seleccionar técnico según área (users.role='TECNICO', users.area, activo).
    - Opcionalmente asignar en BD (AUTO_ASSIGN_ON_CREATE).
    - Enviar siempre WhatsApp al técnico si tenemos teléfono.
    - Registrar TicketHistory 'ASIGNADO_AUTO' cuando se asigna.
    - Si no hay técnico en BD, usa los teléfonos legacy por área como fallback.
    """
    area_u = (area or "").upper()
    org_id = org_id or ORG_ID_DEFAULT
    hotel_id = hotel_id or HOTEL_ID_DEFAULT

    assigned_user_id: Optional[int] = None
    to_phone: Optional[str] = None

    # 1) Buscar técnico configurado en BD
    try:
        tech = _find_technician_for_area(area_u, org_id, hotel_id)
    except Exception as e:
        print(f"[WARN] _find_technician_for_area failed: {e}", flush=True)
        tech = None

    if tech:
        assigned_user_id, to_phone = tech

    # 2) Fallback legacy: teléfonos por área + búsqueda por teléfono
    if not to_phone:
        if area_u == "MANTENCION":
            to_phone = ASSIGNEE_MANTENCION_PHONE or None
        elif area_u == "HOUSEKEEPING":
            to_phone = ASSIGNEE_HOUSEKEEPING_PHONE or None
        elif area_u == "ROOMSERVICE":
            to_phone = ASSIGNEE_ROOMSERVICE_PHONE or None

        if to_phone and not assigned_user_id:
            try:
                uid = _find_user_id_by_phone(to_phone)
                if uid:
                    assigned_user_id = uid
            except Exception as e:
                print(f"[WARN] _find_user_id_by_phone failed: {e}", flush=True)

    # 3) Si está activado, asignar en tickets.assigned_to
    if AUTO_ASSIGN_ON_CREATE and assigned_user_id:
        try:
            if using_pg():
                execute(
                    "UPDATE tickets SET assigned_to=%s WHERE id=%s",
                    (assigned_user_id, ticket_id),
                )
                execute(
                    "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (ticket_id, None, "ASIGNADO_AUTO", f"area={area_u}", datetime.now().isoformat()),
                )
            else:
                execute(
                    "UPDATE tickets SET assigned_to=? WHERE id=?",
                    (assigned_user_id, ticket_id),
                )
                execute(
                    "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) "
                    "VALUES (?,?,?,?,?)",
                    (ticket_id, None, "ASIGNADO_AUTO", f"area={area_u}", datetime.now().isoformat()),
                )
        except Exception as e:
            print(f"[WARN] auto-assign failed: {e}", flush=True)
            assigned_user_id = None  # no marcar como asignado si la BD falló

    # 4) Si no tenemos teléfono aún pero sí user_id, intenta leerlo de users
    if not to_phone and assigned_user_id:
        try:
            if using_pg():
                row = query_one("SELECT telefono FROM users WHERE id=%s", (assigned_user_id,))
            else:
                row = query_one("SELECT telefono FROM users WHERE id=?", (assigned_user_id,))
            if row and row["telefono"]:
                to_phone = row["telefono"]
        except Exception as e:
            print(f"[WARN] could not fetch technician phone: {e}", flush=True)

    # Sin teléfono no podemos notificar por WhatsApp
    if not to_phone:
        return

    prefix = "📌 Asignado a ti.\n" if (assigned_user_id and AUTO_ASSIGN_ON_CREATE) else ""
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

def is_no(text: str) -> bool:
    """
    Accept common negative / rejection forms.
    """
    t = (text or "").strip().lower()
    t = re.sub(r"[!.,;:()\[\]\-—_*~·•«»\"'`´]+$", "", t).strip()
    return t in {
        "no", "n", "nop", "nope", "para nada",
        "no gracias", "no, gracias",
    }




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
def create_ticket(payload: Dict[str, Any],
                  initial_status: str = "PENDIENTE_APROBACION") -> int:
    now = datetime.now()
    due_dt = compute_due(now, payload["area"], payload["prioridad"])
    due_at = due_dt.isoformat() if due_dt else None

    # Normalizar org/hotel (usa defaults si no vienen en payload)
    org_id = int(payload.get("org_id", ORG_ID_DEFAULT))
    hotel_id = int(payload.get("hotel_id", HOTEL_ID_DEFAULT))

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
            org_id,
            hotel_id,
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

    # Persistir teléfono / nombre del huésped si existen las columnas
    guest_phone = payload.get("huesped_phone") or payload.get("huesped_id")
    guest_name  = payload.get("huesped_nombre")
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
            sql = (
                f"UPDATE tickets SET {', '.join(sets)} WHERE id=%s"
                if using_pg()
                else f"UPDATE tickets SET {', '.join(sets)} WHERE id=?"
            )
            execute(sql, tuple(params))
    except Exception as e:
        print(f"[WARN] could not persist guest phone/name: {e}", flush=True)

    # Historial de creación
    execute(
        "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (%s, %s, %s, %s, %s)"
        if using_pg() else
        "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (?, ?, ?, ?, ?)",
        (new_id, None, "CREADO", "via whatsapp", now.isoformat()),
    )
    if initial_status == "PENDIENTE_APROBACION":
        execute(
            "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (%s, %s, %s, %s, %s)"
            if using_pg() else
            "INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at) VALUES (?, ?, ?, ?, ?)",
            (new_id, None, "PENDIENTE_APROBACION", "esperando aprobación de recepción", now.isoformat()),
        )

    # Auto-asignar y notificar técnico según área / org / hotel
    try:
        _auto_assign_and_notify(
            ticket_id=new_id,
            area=payload["area"],
            prioridad=payload["prioridad"],
            detalle=payload.get("detalle"),
            ubicacion=payload.get("ubicacion"),
            org_id=org_id,
            hotel_id=hotel_id,
        )
    except Exception as e:
        print(f"[WARN] auto-assign/notify failed: {e}", flush=True)

    return new_id



def log_faq_history(
    guest_phone: str,
    question_text: str,
    answer_text: str,
    matched_key: str | None = None,
    asked_at: str | None = None,
    answered_at: str | None = None,
):
    """
    Insert a row into public.FAQhistory.

    Uses ORG_ID_DEFAULT / HOTEL_ID_DEFAULT as in create_ticket.
    Opens a short-lived connection; replace with your pool if desired.
    """
    if pg is None or not FAQ_PG_DSN:
        # No Postgres driver or DSN configured
        return

    q_time = asked_at or datetime.now().isoformat()
    a_time = answered_at or q_time

    try:
        conn = pg.connect(FAQ_PG_DSN)
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO public."FAQhistory"
                        (org_id, hotel_id, guest_phone, question_text,
                         answer_text, matched_key, asked_at, answered_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            ORG_ID_DEFAULT,
                            HOTEL_ID_DEFAULT,
                            guest_phone,
                            question_text,
                            answer_text,
                            matched_key,
                            q_time,
                            a_time,
                        ),
                    )
        finally:
            conn.close()
    except Exception as e:
        print(f"[WARN] FAQhistory insert failed: {e}", flush=True)




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

#checkpoint
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

    # Decide if this is an internal worker (by hardcoded role) or a guest
    role = resolve_role_by_phone(from_phone)

    # If it's an internal worker, check initialized flag in users table
    user_row = _get_user_by_phone(from_phone) if role else None
    if role and user_row:
        initialized_ok = bool(user_row.get("initialized"))
        if not initialized_ok:
            # User exists but has not finished onboarding → block and send generic message
            send_whatsapp(from_phone, txt("onboarding_block"))
            return jsonify({"status": "ok", "onboarding": "required"}), 200

    # If user is initialized (or we couldn't find DB row), route by role normally
    if role == "HOUSEKEEPING":
        _handle_hk_message(from_phone, text)
    elif role == "RECEPCION":
        _handle_recepcion_message(from_phone, text)
    elif role == "SUPERVISOR":
        _handle_supervisor_message(from_phone, text)
    elif role == "GERENTE":
        _handle_gerente_message(from_phone, text)
    else:
        # Not a known internal worker → treat as guest
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

def _handle_recepcion_message(from_phone: str, text: str):
    """
    Stub handler for reception staff.
    For now we just acknowledge that the channel exists.
    """
    send_whatsapp(
        from_phone,
        "🛎️ Canal de *Recepción* por WhatsApp está en construcción.\n"
        "Pronto podrás revisar y aprobar tickets desde aquí.\n"
        "Por ahora, usa la app web o el canal interno habitual."
    )


def _handle_supervisor_message(from_phone: str, text: str):
    """
    Stub handler for supervisors.
    """
    send_whatsapp(
        from_phone,
        "👷‍♂️ Canal de *Supervisor* por WhatsApp está en construcción.\n"
        "En la siguiente versión podrás ver KPIs y estado de tickets.\n"
        "Mientras tanto, usa la app web o el canal habitual."
    )


def _handle_gerente_message(from_phone: str, text: str):
    """
    Stub handler for managers/gerentes.
    """
    send_whatsapp(
        from_phone,
        "📊 Canal de *Gerencia* por WhatsApp está en construcción.\n"
        "Estamos trabajando para que puedas ver el estado del hotel desde aquí.\n"
        "Por ahora, revisa la plataforma web para más detalles."
    )



# ================================
# GH (Huésped) DFA helpers
# ================================


def _gh_get_state(s: Dict[str, Any]) -> str:
    """
    Devuelve el estado DFA del huésped, migrando si venimos del flujo legado.

    Estados principales:
      GH_S0        → primer mensaje
      GH_S0i       → pedir identificación (nombre + habitación)
      GH_S0c       → confirmar identificación
      GH_S1        → clasificación (intent)
      GH_S2        → slot filling (detalle / área / prioridad)
      GH_S2_CONFIRM→ confirmar borrador de ticket
      GH_S4        → cierre / '¿algo más?'
      GH_S5        → FIN ciclo
      GH_S6        → escalamiento humano
    """
    state = s.get("gh_state")
    if not state:
        # Migración desde los stages antiguos (por si hay sesiones viejas)
        legacy = s.get("stage")
        mapping = {
            "need_name": "GH_S0i",
            "need_room": "GH_S0i",
            "need_detail": "GH_S2",
            "confirm": "GH_S2_CONFIRM",
        }
        state = mapping.get(legacy, "GH_S0")
        s["gh_state"] = state
    return state


def _gh_set_state(s: Dict[str, Any], state: str):
    """
    Setea el estado DFA del huésped y refresca timestamp de la sesión.
    """
    s["gh_state"] = state
    s["ts"] = time.time()


def _gh_has_identification(s: Dict[str, Any]) -> bool:
    """
    Tenemos identificación suficiente del huésped (nombre + habitación).
    """
    return bool((s.get("guest_name") or "").strip()) and bool((s.get("room") or "").strip())


def _gh_reset_request_slots(s: Dict[str, Any], keep_id: bool = True):
    """
    Limpia solo los datos de la solicitud (área, prioridad, detalle, etc.),
    opcionalmente manteniendo la identificación del huésped.
    También resetea el cache de NLU.
    """
    for key in (
        "area",
        "prioridad",
        "detalle",
        "gh_pending_issue_text",
        "gh_last_intent",
        "_gh_last_nlu",
        "gh_last_ticket_id",
    ):
        s.pop(key, None)

    if not keep_id:
        s.pop("guest_name", None)
        s.pop("room", None)


def _gh_send_ask_identification(from_phone: str):
    """
    Pregunta por nombre + habitación en un solo mensaje.
    """
    send_whatsapp(
        from_phone,
        "👩🏼‍💼 Hola! soy su asistente virtual y para ayudarle necesito la siguiente información\n"
        "Por favor dime *tu nombre* y tu *número de habitación* "
        "(por ejemplo: `Soy Ana de la 312`)."
    )


def _gh_send_ask_name_only(from_phone: str):
    send_whatsapp(
        from_phone,
        "Genial. ¿*Cuál es tu nombre*? (Lo necesito para guardar tu solicitud). Aviso rápido: estamos en versión beta 😊"
    )


def _gh_send_ask_room_only(from_phone: str, guest_name: Optional[str] = None):
    if guest_name:
        msg = f"Gracias, *{guest_name}*. ¿Cuál es tu *número de habitación*? 🏨"
    else:
        msg = "¿Cuál es tu *número de habitación*? 🏨"
    send_whatsapp(from_phone, msg)


def _gh_build_id_confirmation_message(s: Dict[str, Any]) -> str:
    """
    Mensaje de confirmación de identificación (GH_S0c).
    """
    name = (s.get("guest_name") or "").strip()
    room = (s.get("room") or "").strip()
    if name and room:
        return (
            "Perfecto. Solo para confirmar:\n\n"
            f"👤 Huésped: *{name}*\n"
            f"🏨 Habitación: *{room}*\n\n"
            "¿Es correcto? Responde *SI* para continuar o *NO* para corregir."
        )
    return (
        "Solo necesito que me confirmes tus datos.\n"
        "Responde *SI* si son correctos o *NO* si quieres cambiarlos."
    )


def _gh_render_closing_question(s: Dict[str, Any]) -> str:
    """
    Texto para GH_S4 → '¿algo más?' con nombre si lo tenemos.
    """
    name = (s.get("guest_name") or "").strip()
    if name:
        return f"¿Hay *algo más* en lo que pueda ayudarte, {name}? 🙂"
    return "¿Hay *algo más* en lo que pueda ayudarte? 🙂"


def _gh_escalate_to_reception(from_phone: str, s: Dict[str, Any], last_text: str):
    """
    GH_S6: Escalamiento humano → mensaje al huésped + notificación a recepción.
    """
    # Avisar al huésped
    send_whatsapp(
        from_phone,
        "Te derivo con *recepción* para que un miembro del equipo pueda ayudarte "
        "directamente. Pueden contactarte por este mismo chat o por teléfono. 🛎️"
    )

    # Avisar a recepción (si hay teléfonos configurados)
    recips = _phones_from_env(RECEPTION_PHONES)
    if not recips:
        return

    guest_name = s.get("guest_name") or "Huésped"
    room = s.get("room") or "sin habitación registrada"
    summary = (
        "📲 *Escalamiento desde WhatsApp*\n\n"
        f"Huésped: {guest_name} ({from_phone})\n"
        f"Habitación: {room}\n"
        f"Mensaje: {last_text or '(sin texto)'}"
    )
    for ph in recips:
        send_whatsapp(ph, summary)


# ---------- NLU helpers (usan services.guest_nlu.analyze_guest_message) ----------

def _gh_get_nlu(s: Dict[str, Any], text: str, state: str) -> Dict[str, Any]:
    """
    Wrapper con cache para NLU: devuelve interpretación estructurada del mensaje.
    """
    t = (text or "").strip()
    if not t:
        return {}

    key = f"{state}:{t}"
    last = s.get("_gh_last_nlu") or {}
    if last.get("key") == key:
        return last.get("data") or {}

    data = analyze_guest_message(t, s, state)
    if not isinstance(data, dict):
        data = {}
    s["_gh_last_nlu"] = {"key": key, "data": data}
    return data


def _gh_slots_complete(s: Dict[str, Any]) -> bool:
    """
    Por ahora consideramos suficiente tener un 'detalle' no vacío.
    Área y prioridad se infieren automáticamente o por NLU.
    """
    detalle = (s.get("detalle") or "").strip()
    return bool(detalle)


def _gh_is_cancel(
    text: str,
    s: Optional[Dict[str, Any]] = None,
    state: str = "GLOBAL",
) -> bool:
    """
    Detecta si el huésped quiere cancelar la solicitud actual.

    Puede usarse como:
      _gh_is_cancel(text)
      _gh_is_cancel(text, s, state="GLOBAL")

    Primero intenta vía NLU; si no, cae a patrones simples.
    """
    if not text:
        return False

    # 1) Intento vía NLU
    if s is not None:
        try:
            nlu = _gh_get_nlu(s, text, state)
            if nlu.get("is_cancel"):
                return True
        except Exception as e:
            print(f"[WARN] _gh_is_cancel NLU failed: {e}", flush=True)

    # 2) Patrones simples
    t = (text or "").strip().lower()
    patterns = [
        "cancelar",
        "olvida",
        "olvídalo",
        "olvidalo",
        "ya no",
        "no importa",
        "da igual",
        "déjalo",
        "dejalo",
    ]
    return any(p in t for p in patterns)


def _gh_is_help(
    text: str,
    s: Optional[Dict[str, Any]] = None,
    state: str = "GLOBAL",
) -> bool:
    """
    El huésped pide ayuda / repetir durante slot filling.
    Se apoya en NLU si está disponible.
    """
    if not text:
        return False

    # 1) Intento vía NLU
    if s is not None:
        try:
            nlu = _gh_get_nlu(s, text, state)
            if nlu.get("is_help"):
                return True
        except Exception as e:
            print(f"[WARN] _gh_is_help NLU failed: {e}", flush=True)

    # 2) Patrones simples
    t = (text or "").strip().lower()
    patterns = [
        "ayuda",
        "no entiendo",
        "repiteme",
        "repite",
        "puedes repetir",
        "qué puedo hacer",
        "que puedo hacer",
        "help",
    ]
    return any(p in t for p in patterns)


def _gh_update_slots_from_text(
    s: Dict[str, Any],
    text: str,
    state: str = "GH_S2",
):
    """
    Usa NLU + heurísticas para rellenar/actualizar los slots de la solicitud:
      - detalle
      - área
      - prioridad
      - room (si viene en el mensaje)
    """
    t = (text or "").strip()
    if not t:
        return

    # 1) Interpretación vía NLU
    nlu = {}
    try:
        nlu = _gh_get_nlu(s, t, state)
    except Exception as e:
        print(f"[WARN] _gh_update_slots_from_text NLU failed: {e}", flush=True)

    slots_area = nlu.get("area")
    slots_prio = nlu.get("priority")
    slots_room = nlu.get("room")
    slots_detail = nlu.get("detail")

    # 2) detalle: si NLU no da 'detail', usamos el texto bruto
    if slots_detail:
        new_detail = slots_detail.strip()
    else:
        new_detail = t

    prev = (s.get("detalle") or "").strip()
    if prev and new_detail != prev:
        s["detalle"] = f"{prev}\n{new_detail}"
    else:
        s["detalle"] = new_detail

    # 3) área
    if slots_area:
        s["area"] = slots_area
    elif not (s.get("area") or "").strip():
        s["area"] = guess_area(t)

    # 4) prioridad
    if slots_prio:
        s["prioridad"] = slots_prio
    elif not (s.get("prioridad") or "").strip():
        s["prioridad"] = guess_priority(t)

    # 5) room (si no la teníamos aún)
    if slots_room and not (s.get("room") or "").strip():
        s["room"] = slots_room


def _gh_classify_intent(text: str) -> str:
    """
    Clasificación simple de intent basada en patrones:
      - 'handoff_request' → quiere hablar con alguien
      - 'cancel'          → cancelar solicitud
      - 'general_chat'    → gracias / smalltalk / cierre
      - 'ticket_request'  → algo que suena a problema/petición
      - 'unknown'         → vacío o no se puede clasificar

    (Si quieres, en el futuro se puede reescribir para usar NLU.)
    """
    t = (text or "").strip().lower()
    if not t:
        return "unknown"

    if _gh_wants_handoff(t):
        return "handoff_request"

    if _gh_is_cancel(t):
        return "cancel"

    if t in {"gracias", "muchas gracias", "no, gracias", "no gracias", "todo bien", "estoy bien"}:
        return "general_chat"

    if is_smalltalk(t):
        return "general_chat"

    return "ticket_request"



# ================================
# GH (Huésped) DFA – handler principal
# ================================

def _handle_guest_message(from_phone: str, text: str, audio_url: str | None):
    s = session_get(from_phone)

    # 1) Audio → texto si no vino texto
    if audio_url and not text:
        transcript = transcribe_audio(audio_url)
        text = transcript or ""

    t = (text or "").strip()

    # 2) Cancelación global de la solicitud actual (manteniendo identificación)
    if _gh_is_cancel(t, s, state="GLOBAL"):
        _gh_reset_request_slots(s, keep_id=True)
        _gh_set_state(s, "GH_S5")
        session_set(from_phone, s)
        send_whatsapp(
            from_phone,
            "He cancelado la solicitud actual. Si necesitas algo más para tu habitación, "
            "solo dime por aquí. 🙂"
        )
        return

    # 3) Estado actual del DFA; si no hay, asumimos que está en reposo (GH_S5)
    state = _gh_get_state(s) or "GH_S5"

    # 3.1 Capa FAQ previa cuando el bot está “en reposo”
    #     (nuevo ciclo o después de haber terminado uno anterior)
    if state == "GH_S5":
        if t:
            asked_at = datetime.now().isoformat()
            faq = maybe_answer_faq(t, s)

            if faq.get("handled"):
                answer = (faq.get("answer") or "").strip()
                if answer:
                    answered_at = datetime.now().isoformat()
                    # Guardar en FAQhistory
                    log_faq_history(
                        guest_phone=from_phone,
                        question_text=t,
                        answer_text=answer,
                        matched_key=faq.get("matched_key"),
                        asked_at=asked_at,
                        answered_at=answered_at,
                    )
                    send_whatsapp(from_phone, answer)
                    print(
                        f"[FAQ] handled message from {from_phone} "
                        f"key={faq.get('matched_key')}",
                        flush=True,
                    )

                # Tras contestar la FAQ volvemos a estado “idle”
                _gh_set_state(s, "GH_S5")
                session_set(from_phone, s)
                return

        # No es FAQ → entrar al DFA clásico con o sin identificación previa
        if _gh_has_identification(s):
            state = "GH_S1"
        else:
            state = "GH_S0"
        _gh_set_state(s, state)
        session_set(from_phone, s)

    # --------------------------------------------------
    # GH_S0: primer mensaje huésped (no hay identificación completa)
    # --------------------------------------------------
    if state == "GH_S0" and not _gh_has_identification(s):
        # Pedido explícito de humano → GH_S6 (uso patrón rápido)
        if _gh_wants_handoff(t):
            _gh_set_state(s, "GH_S6")
            session_set(from_phone, s)
            _gh_escalate_to_reception(from_phone, s, t)
            return

        # Mensaje vacío → pedir identificación
        if not t:
            _gh_set_state(s, "GH_S0i")
            session_set(from_phone, s)
            _gh_send_ask_identification(from_phone)
            return

        # Saludo / smalltalk simple → pedir identificación
        if is_smalltalk(t):
            _gh_set_state(s, "GH_S0i")
            session_set(from_phone, s)
            _gh_send_ask_identification(from_phone)
            return

        # Análisis NLU del primer mensaje
        nlu = _gh_get_nlu(s, t, "GH_S0")
        intent = nlu.get("intent") or "ticket_request"

        if intent == "handoff_request" or nlu.get("wants_handoff"):
            _gh_set_state(s, "GH_S6")
            session_set(from_phone, s)
            _gh_escalate_to_reception(from_phone, s, t)
            return

        # Intent con posible identificación incluida
        name_candidate = extract_name(t)
        room_candidate = nlu.get("room") or guess_room(t)

        if name_candidate:
            s["guest_name"] = name_candidate
        if room_candidate:
            s["room"] = room_candidate

        if _gh_has_identification(s):
            # Intent detectado + ID presente → guardar en buffer y confirmar ID
            s["gh_pending_issue_text"] = t
            _gh_set_state(s, "GH_S0c")
            session_set(from_phone, s)
            send_whatsapp(from_phone, _gh_build_id_confirmation_message(s))
            return

        # Intent detectado pero falta ID → GH_S0i (guardar requerimiento en buffer)
        s["gh_pending_issue_text"] = t
        _gh_set_state(s, "GH_S0i")
        session_set(from_phone, s)
        _gh_send_ask_identification(from_phone)
        return

    # --------------------------------------------------
    # GH_S0i: pedir identificación (nombre + habitación)
    # --------------------------------------------------
    if state == "GH_S0i":
        # Intentar capturar nombre si falta
        if not (s.get("guest_name") or "").strip():
            name = extract_name(t)
            if name:
                s["guest_name"] = name

        # Intentar capturar habitación si falta (NLU + regex)
        if not (s.get("room") or "").strip():
            nlu = _gh_get_nlu(s, t, "GH_S0i")
            room = nlu.get("room") or guess_room(t)
            if room:
                s["room"] = room

        # Si aún faltan datos, pedir específicamente lo que falta
        if not _gh_has_identification(s):
            if not (s.get("guest_name") or "").strip() and not (s.get("room") or "").strip():
                _gh_send_ask_identification(from_phone)
            elif not (s.get("guest_name") or "").strip():
                _gh_send_ask_name_only(from_phone)
            else:
                _gh_send_ask_room_only(from_phone, s.get("guest_name"))
            session_set(from_phone, s)
            return

        # Ya tenemos nombre + habitación → GH_S0c (confirmar identificación)
        _gh_set_state(s, "GH_S0c")
        session_set(from_phone, s)
        send_whatsapp(from_phone, _gh_build_id_confirmation_message(s))
        return

    # --------------------------------------------------
    # GH_S0c: confirmar identificación (confirm_yes / confirm_no)
    # --------------------------------------------------
    if state == "GH_S0c":
        if is_yes(t):
            # confirm_yes → GH_S1
            _gh_set_state(s, "GH_S1")
            session_set(from_phone, s)

            pending = (s.get("gh_pending_issue_text") or "").strip()
            if not pending:
                # No había requerimiento pendiente → preguntar en qué ayudar
                guest_name = s.get("guest_name") or ""
                room = s.get("room") or ""
                if guest_name and room:
                    msg = f"Gracias, *{guest_name}*. ¿En qué puedo ayudarte con tu habitación {room}?"
                else:
                    msg = "Gracias. ¿En qué puedo ayudarte con tu habitación?"
                send_whatsapp(from_phone, msg)
                return

            # Había requerimiento pendiente desde GH_S0 → usarlo como entrada a GH_S1
            t = pending
            s["gh_pending_issue_text"] = ""
            # Continuar más abajo como GH_S1 con ese texto

        elif is_no(t):
            # confirm_no → limpiar ID y volver a GH_S0i
            s.pop("guest_name", None)
            s.pop("room", None)
            _gh_set_state(s, "GH_S0i")
            session_set(from_phone, s)
            _gh_send_ask_identification(from_phone)
            return
        else:
            # Pedir explícitamente SI / NO
            send_whatsapp(
                from_phone,
                "Solo necesito que me confirmes si tus datos son correctos. "
                "Responde *SI* para continuar o *NO* si quieres cambiarlos."
            )
            return

    # Refrescar estado por si venimos de GH_S0c con confirm_yes
    state = _gh_get_state(s)

    # --------------------------------------------------
    # GH_S6: Escalamiento humano (el bot termina el ciclo)
    # --------------------------------------------------
    if state == "GH_S6":
        _gh_set_state(s, "GH_S5")
        session_set(from_phone, s)
        return

    # --------------------------------------------------
    # GH_S1: Clasificación (NLU → Σ)
    # --------------------------------------------------
    if state == "GH_S1":
        nlu = _gh_get_nlu(s, t, "GH_S1")
        intent = nlu.get("intent") or "ticket_request"

        if intent == "handoff_request" or nlu.get("wants_handoff"):
            _gh_set_state(s, "GH_S6")
            session_set(from_phone, s)
            _gh_escalate_to_reception(from_phone, s, t)
            return

        if intent == "general_chat" and nlu.get("is_smalltalk"):
            # Pequeña charla / agradecimientos → GH_S4 (cierre suave)
            send_whatsapp(from_phone, "Gracias por tu mensaje. 😊")
            _gh_set_state(s, "GH_S4")
            session_set(from_phone, s)
            send_whatsapp(from_phone, _gh_render_closing_question(s))
            return

        if intent == "cancel":
            # Cancelación de solicitud (manteniendo identificación) → GH_S5
            _gh_reset_request_slots(s, keep_id=True)
            _gh_set_state(s, "GH_S5")
            session_set(from_phone, s)
            send_whatsapp(
                from_phone,
                "Perfecto, no registraré ninguna solicitud. Si necesitas algo más, "
                "solo escríbeme por aquí."
            )
            return

        # Intent válido / not_understood → GH_S2 (init_form)
        _gh_reset_request_slots(s, keep_id=True)
        _gh_set_state(s, "GH_S2")
        _gh_update_slots_from_text(s, t, state="GH_S2")
        session_set(from_phone, s)

        if not _gh_slots_complete(s):
            if _should_prompt(s, "ask_detail"):
                send_whatsapp(from_phone, txt("ask_detail"))
            return

        # Slots completos desde el primer mensaje → GH_S2_CONFIRM (cumplimiento implícito)
        summary = ensure_summary_in_session(s)
        _gh_set_state(s, "GH_S2_CONFIRM")
        session_set(from_phone, s)
        confirm_msg = render_confirm_draft(summary, s)
        send_whatsapp(from_phone, confirm_msg)
        return

    # --------------------------------------------------
    # GH_S2: Recolección de datos (slot filling)
    # --------------------------------------------------
    if state == "GH_S2":
        # help / repeat / not_understood → escalamiento humano (GH_S6)
        if _gh_is_help(t, s, state="GH_S2"):
            _gh_set_state(s, "GH_S6")
            session_set(from_phone, s)
            _gh_escalate_to_reception(from_phone, s, t)
            return

        # provide_slot → seguimos en GH_S2 hasta completar
        _gh_update_slots_from_text(s, t, state="GH_S2")
        session_set(from_phone, s)

        if not _gh_slots_complete(s):
            if _should_prompt(s, "ask_detail"):
                send_whatsapp(from_phone, txt("ask_detail"))
            return

        # slots_complete → GH_S2_CONFIRM (confirmación de borrador)
        summary = ensure_summary_in_session(s)
        _gh_set_state(s, "GH_S2_CONFIRM")
        session_set(from_phone, s)
        confirm_msg = render_confirm_draft(summary, s)
        send_whatsapp(from_phone, confirm_msg)
        return

    # --------------------------------------------------
    # GH_S2_CONFIRM: Confirmar borrador de ticket (GH_S3 implícito)
    # --------------------------------------------------
    if state == "GH_S2_CONFIRM":
        if is_yes(t):
            # GH_S3: cumplimiento → creación de ticket
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
            s["gh_last_ticket_id"] = ticket_id
            _gh_set_state(s, "GH_S4")
            session_set(from_phone, s)

            # GH_S3 → GH_S4: avisar al huésped + notificar recepción
            send_whatsapp(
                from_phone,
                txt("ticket_created", guest=s.get("guest_name", "Huésped"), ticket_id=ticket_id)
            )
            
            # _notify_reception_pending(
            #     ticket_id,
            #     payload["area"],
            #     payload["prioridad"],
            #     payload["detalle"],
            #     payload.get("ubicacion"),
            # )
    
            # NEW: notificar a Andrés solo si es un ticket de housekeeping
            if payload["area"] == "HOUSEKEEPING":
                _notify_hk_pending(
                    ticket_id,
                    payload["area"],
                    payload["prioridad"],
                    payload["detalle"],
                    payload.get("ubicacion"),
                )

            send_whatsapp(from_phone, _gh_render_closing_question(s))
            return

        if is_no(t):
            # El huésped quiere editar → volver a GH_S2 (slot filling)
            _gh_set_state(s, "GH_S2")
            session_set(from_phone, s)
            send_whatsapp(from_phone, txt("edit_help"))
            return

        # Respuesta ambigua → recordar opciones
        send_whatsapp(
            from_phone,
            "Por favor responde *SI* si el resumen es correcto o *NO* si quieres cambiar "
            "el área, prioridad, habitación o detalle."
        )
        return

    # --------------------------------------------------
    # GH_S4: Confirmación / cierre ('¿algo más?')
    # --------------------------------------------------
    if state == "GH_S4":
        # yes | new_request → GH_S1 (nuevo ciclo con misma identificación)
        if is_yes(t):
            _gh_reset_request_slots(s, keep_id=True)
            _gh_set_state(s, "GH_S1")
            session_set(from_phone, s)
            send_whatsapp(
                from_phone,
                "Perfecto, cuéntame qué más necesitas y crearé una nueva solicitud. 📝"
            )
            return

        # no → GH_S5 (FIN)
        if is_no(t):
            _gh_set_state(s, "GH_S5")
            session_set(from_phone, s)
            send_whatsapp(
                from_phone,
                "Gracias por contactarnos. Que tengas una excelente estadía. 🌟"
            )
            return

        # Usar NLU para decidir si es agradecimiento o nueva solicitud
        nlu = _gh_get_nlu(s, t, "GH_S4")
        if nlu.get("intent") == "general_chat" and nlu.get("is_smalltalk"):
            _gh_set_state(s, "GH_S5")
            session_set(from_phone, s)
            send_whatsapp(
                from_phone,
                "Gracias por contactarnos. Que tengas una excelente estadía. 🌟"
            )
            return

        # Cualquier otra cosa se interpreta como nueva solicitud directa
        _gh_reset_request_slots(s, keep_id=True)
        _gh_set_state(s, "GH_S2")
        _gh_update_slots_from_text(s, t, state="GH_S2")
        session_set(from_phone, s)

        if not _gh_slots_complete(s):
            if _should_prompt(s, "ask_detail"):
                send_whatsapp(from_phone, txt("ask_detail"))
            return

        summary = ensure_summary_in_session(s)
        _gh_set_state(s, "GH_S2_CONFIRM")
        session_set(from_phone, s)
        confirm_msg = render_confirm_draft(summary, s)
        send_whatsapp(from_phone, confirm_msg)
        return

    # --------------------------------------------------
    # Fallback para estados desconocidos
    # --------------------------------------------------
    _gh_reset_request_slots(s, keep_id=False)
    _gh_set_state(s, "GH_S0")
    session_set(from_phone, s)
    _gh_send_ask_identification(from_phone)



if __name__ == "__main__":
    ensure_runtime_tables()  # safe to call again
    print(f"[BOOT] WhatsApp webhook starting on port {PORT} (DB={'PG' if using_pg() else 'SQLite'})", flush=True)
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False) 