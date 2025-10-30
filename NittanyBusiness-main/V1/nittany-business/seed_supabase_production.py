# seed_supabase_production.py
# Build & seed your (new) Supabase Postgres with Hestia Ops schema + demo data.
# Safe to run multiple times; uses IF NOT EXISTS and upserts where appropriate.
#
# Usage examples:
#   set DATABASE_URL=postgresql://postgres:...@aws-1-...pooler.supabase.com:6543/postgres?sslmode=require
#   python seed_supabase_production.py --reset
#   python seed_supabase_production.py --tickets 200 --days 14 --orgs 2 --hotels-per-org 2

import argparse
import os
import random
import hashlib
from datetime import datetime, timedelta, date
from collections import defaultdict

import psycopg2
from psycopg2 import extras

# ---------- Config / Constants ----------

RNG = random.Random(42)  # deterministic
DB_DSN = os.getenv("DATABASE_URL")
if not DB_DSN:
    raise SystemExit("Missing DATABASE_URL env var (Supabase connection string).")

AREAS = ["MANTENCION", "HOUSEKEEPING", "ROOMSERVICE"]
PRIOS = ["BAJA", "MEDIA", "ALTA", "URGENTE"]
OPEN_STATES = ("PENDIENTE", "ASIGNADO", "ACEPTADO", "EN_CURSO", "PAUSADO", "DERIVADO")
ALL_STATES = OPEN_STATES + ("RESUELTO",)

DEFAULT_SLA_MIN = {"BAJA": 240, "MEDIA": 180, "ALTA": 90, "URGENTE": 45}

TICKET_TYPES_SEED = [
    ("AGUA_FUGA", "Fuga de agua", "MANTENCION"),
    ("ELECT_LUZ", "Luz sin funcionar", "MANTENCION"),
    ("HK_TOALLAS", "Toallas faltantes", "HOUSEKEEPING"),
    ("RS_PEDIDO", "Pedido de room service", "ROOMSERVICE"),
]

TAGS_SEED = ["recurrente", "vip", "seguridad", "pico", "auditoria"]

ASSET_CATEGORIES = ["HVAC", "ELECTRICO", "SANITARIO", "ILUMINACION", "COCINA"]

# ---------- Helpers ----------

def hp(p: str) -> str:
    return hashlib.sha256(p.encode("utf-8")).hexdigest()

def connect():
    # sslmode is typically in DSN (?sslmode=require)
    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = True
    return conn

def exec_sql(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())

def execmany(conn, sql, rows):
    if not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(sql, rows)

def q_all(conn, sql, params=None):
    with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()

def q_one(conn, sql, params=None):
    with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()

# ---------- Schema (new, back-compatible) ----------

SCHEMA_SQL = """
-- ========== RBAC ==========
CREATE TABLE IF NOT EXISTS roles (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  inherits_code TEXT REFERENCES roles(code)
);

CREATE TABLE IF NOT EXISTS permissions (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rolepermissions (
  role_code TEXT NOT NULL REFERENCES roles(code) ON DELETE CASCADE,
  perm_code TEXT NOT NULL REFERENCES permissions(code) ON DELETE CASCADE,
  allow BOOLEAN NOT NULL DEFAULT TRUE,
  PRIMARY KEY (role_code, perm_code)
);

-- ========== CORE ENTITIES ==========
CREATE TABLE IF NOT EXISTS orgs (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hotels (
  id BIGSERIAL PRIMARY KEY,
  org_id BIGINT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
  id BIGSERIAL PRIMARY KEY,
  username TEXT UNIQUE,
  email TEXT UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL,
  area TEXT,
  telefono TEXT,
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  is_superadmin BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS orgusers (
  id BIGSERIAL PRIMARY KEY,
  org_id BIGINT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  default_area TEXT,
  default_hotel_id BIGINT REFERENCES hotels(id) ON DELETE SET NULL,
  UNIQUE (org_id, user_id)
);

CREATE TABLE IF NOT EXISTS orguserareas (
  org_id BIGINT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  area_code TEXT NOT NULL,
  PRIMARY KEY (org_id, user_id, area_code)
);

-- ========== SLA RULES (allows overrides by org/hotel, all nullable) ==========
CREATE TABLE IF NOT EXISTS slarules (
  area TEXT NOT NULL,
  prioridad TEXT NOT NULL,
  max_minutes INTEGER NOT NULL,
  org_id BIGINT REFERENCES orgs(id) ON DELETE CASCADE,
  hotel_id BIGINT REFERENCES hotels(id) ON DELETE CASCADE,
  PRIMARY KEY (area, prioridad, org_id, hotel_id)
);

-- ========== PMS CACHE ==========
CREATE TABLE IF NOT EXISTS pmsguests (
  id BIGSERIAL PRIMARY KEY,
  huesped_id TEXT NOT NULL,
  nombre TEXT NOT NULL,
  habitacion TEXT NOT NULL,
  status TEXT NOT NULL,
  checkin TIMESTAMP,
  checkout TIMESTAMP
);

-- ========== LOCATIONS ==========
CREATE TABLE IF NOT EXISTS location_types (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS locations (
  id BIGSERIAL PRIMARY KEY,
  hotel_id BIGINT NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
  type_code TEXT NOT NULL REFERENCES location_types(code),
  code TEXT,
  name TEXT NOT NULL,
  parent_id BIGINT REFERENCES locations(id) ON DELETE CASCADE,
  UNIQUE(hotel_id, type_code, code)
);

-- ========== ASSETS ==========
CREATE TABLE IF NOT EXISTS assets (
  id BIGSERIAL PRIMARY KEY,
  hotel_id BIGINT NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
  location_id BIGINT REFERENCES locations(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  category TEXT,
  serial TEXT,
  status TEXT,
  qr_code TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  retired_at TIMESTAMP
);

-- ========== TICKETS ==========
CREATE TABLE IF NOT EXISTS tickets (
  id BIGSERIAL PRIMARY KEY,
  org_id BIGINT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  hotel_id BIGINT NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
  area TEXT NOT NULL,
  prioridad TEXT NOT NULL,
  estado TEXT NOT NULL,
  detalle TEXT NOT NULL,
  canal_origen TEXT NOT NULL,
  ubicacion TEXT NOT NULL,
  huesped_id TEXT,
  created_at TIMESTAMP NOT NULL,
  due_at TIMESTAMP,
  assigned_to BIGINT REFERENCES users(id),
  created_by BIGINT REFERENCES users(id),
  confidence_score NUMERIC,
  qr_required BOOLEAN NOT NULL DEFAULT FALSE,
  accepted_at TIMESTAMP,
  started_at TIMESTAMP,
  finished_at TIMESTAMP,

  -- new (back-compatible)
  approved BOOLEAN,
  approved_by BIGINT REFERENCES users(id),
  approved_at TIMESTAMP,
  deleted_at TIMESTAMP,
  deleted_by BIGINT REFERENCES users(id),
  delete_reason TEXT,
  tipo TEXT,
  external_ref TEXT,
  location_id BIGINT REFERENCES locations(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS ticket_assets (
  ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  asset_id BIGINT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  PRIMARY KEY(ticket_id, asset_id)
);

CREATE INDEX IF NOT EXISTS idx_tickets_state    ON tickets(estado);
CREATE INDEX IF NOT EXISTS idx_tickets_created  ON tickets(created_at);
CREATE INDEX IF NOT EXISTS idx_tickets_scope    ON tickets(org_id, hotel_id);
CREATE INDEX IF NOT EXISTS idx_tickets_assigned ON tickets(assigned_to);
CREATE INDEX IF NOT EXISTS idx_tickets_estado_area ON tickets(estado, area);
CREATE INDEX IF NOT EXISTS idx_tickets_hotel_created_desc ON tickets(hotel_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_critical ON tickets(due_at)
  WHERE estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO') AND due_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tickets_guest_fields ON tickets(ubicacion, huesped_id);

-- ========== HISTORY / COMMENTS / ATTACHMENTS / VOICE ==========
CREATE TABLE IF NOT EXISTS tickethistory (
  id BIGSERIAL PRIMARY KEY,
  ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  actor_user_id BIGINT REFERENCES users(id),
  action TEXT NOT NULL,
  motivo TEXT,
  at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ticket_history_ticket ON tickethistory(ticket_id);

CREATE TABLE IF NOT EXISTS ticket_attachments (
  id BIGSERIAL PRIMARY KEY,
  ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  kind TEXT,
  url TEXT NOT NULL,
  mime TEXT,
  size_bytes BIGINT,
  created_by BIGINT REFERENCES users(id),
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ticket_comments (
  id BIGSERIAL PRIMARY KEY,
  ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  author_id BIGINT REFERENCES users(id),
  body TEXT NOT NULL,
  is_internal BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ticket_voice_notes (
  id BIGSERIAL PRIMARY KEY,
  ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  audio_url TEXT NOT NULL,
  transcript TEXT,
  lang TEXT,
  duration_sec INTEGER,
  created_by BIGINT REFERENCES users(id),
  created_at TIMESTAMP DEFAULT NOW()
);

-- ========== TAGS / TYPES / APPROVALS ==========
CREATE TABLE IF NOT EXISTS ticket_tags (
  tag TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS ticket_tag_map (
  ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  tag TEXT NOT NULL REFERENCES ticket_tags(tag) ON DELETE CASCADE,
  PRIMARY KEY (ticket_id, tag)
);

CREATE TABLE IF NOT EXISTS ticket_types (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  area TEXT
);

CREATE TABLE IF NOT EXISTS ticket_approvals (
  id BIGSERIAL PRIMARY KEY,
  ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  requested_by BIGINT REFERENCES users(id),
  approver_id BIGINT REFERENCES users(id),
  status TEXT NOT NULL DEFAULT 'PENDING',
  reason TEXT,
  decided_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW()
);

-- ========== KPI / NOTIFICATIONS / WEBHOOKS ==========
CREATE TABLE IF NOT EXISTS kpi_daily (
  id BIGSERIAL PRIMARY KEY,
  org_id BIGINT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  hotel_id BIGINT REFERENCES hotels(id) ON DELETE CASCADE,
  day DATE NOT NULL,
  open_total INTEGER NOT NULL DEFAULT 0,
  resolved_total INTEGER NOT NULL DEFAULT 0,
  sla_rate NUMERIC,
  ttr_avg_min NUMERIC,
  by_area JSONB,
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(org_id, hotel_id, day)
);

CREATE TABLE IF NOT EXISTS notifications (
  id BIGSERIAL PRIMARY KEY,
  ticket_id BIGINT REFERENCES tickets(id) ON DELETE CASCADE,
  channel TEXT NOT NULL,
  payload JSONB,
  status TEXT,
  error TEXT,
  sent_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS webhooks (
  id BIGSERIAL PRIMARY KEY,
  org_id BIGINT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  event TEXT NOT NULL,
  url TEXT NOT NULL,
  secret TEXT,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT NOW()
);

-- helpful index for SLA overrides
CREATE INDEX IF NOT EXISTS idx_sla_scope ON slarules(org_id, hotel_id, area, prioridad);
"""

def reset_db(conn):
    # Drop in FK-safe order
    to_drop = [
        "ticket_tag_map",
        "ticket_assets",
        "ticket_attachments",
        "ticket_comments",
        "ticket_voice_notes",
        "ticket_approvals",
        "notifications",
        "tickethistory",
        "kpi_daily",
        "tickets",
        "assets",
        "locations",
        "location_types",
        "orguserareas",
        "orgusers",
        "pmsguests",
        "slarules",
        "webhooks",
        "hotels",
        "orgs",
        "rolepermissions",
        "permissions",
        "roles",
        "ticket_tags",
        "ticket_types",
        "users"
    ]
    for t in to_drop:
        exec_sql(conn, f"DROP TABLE IF EXISTS {t} CASCADE;")
    exec_sql(conn, SCHEMA_SQL)

def ensure_schema(conn):
    exec_sql(conn, SCHEMA_SQL)

# ---------- Seeders ----------

def seed_rbac(conn):
    roles = [
        ("SUPERADMIN","Super Admin", None),
        ("GERENTE","Gerente", None),
        ("SUPERVISOR","Supervisor", None),
        ("RECEPCION","Recepción", None),
        ("TECNICO","Técnico", None),
    ]
    perms = [
        ("ticket.view.all","Ver todos los tickets"),
        ("ticket.view.area","Ver tickets de mis áreas"),
        ("ticket.view.assigned","Ver tickets asignados"),
        ("ticket.create","Crear tickets"),
        ("ticket.confirm","Confirmar tickets"),
        ("ticket.assign","Asignar/Reasignar"),
        ("ticket.transition.accept","Aceptar"),
        ("ticket.transition.start","Iniciar"),
        ("ticket.transition.pause","Pausar"),
        ("ticket.transition.resume","Reanudar"),
        ("ticket.transition.finish","Finalizar"),
    ]

    rp = []
    for p in perms: rp.append(("SUPERADMIN", p[0], True))
    for c in ["ticket.view.all","ticket.create","ticket.confirm","ticket.assign",
              "ticket.transition.accept","ticket.transition.start","ticket.transition.pause",
              "ticket.transition.resume","ticket.transition.finish"]:
        rp.append(("GERENTE", c, True))
    for c in ["ticket.view.area","ticket.confirm","ticket.assign",
              "ticket.transition.accept","ticket.transition.start","ticket.transition.pause",
              "ticket.transition.resume","ticket.transition.finish"]:
        rp.append(("SUPERVISOR", c, True))
    for c in ["ticket.view.area","ticket.create","ticket.confirm"]:
        rp.append(("RECEPCION", c, True))
    for c in ["ticket.view.assigned","ticket.transition.accept","ticket.transition.start",
              "ticket.transition.pause","ticket.transition.resume","ticket.transition.finish"]:
        rp.append(("TECNICO", c, True))

    execmany(conn, "INSERT INTO roles(code,name,inherits_code) VALUES(%s,%s,%s) ON CONFLICT (code) DO NOTHING", roles)
    execmany(conn, "INSERT INTO permissions(code,name) VALUES(%s,%s) ON CONFLICT (code) DO NOTHING", perms)
    execmany(conn, """
        INSERT INTO rolepermissions(role_code,perm_code,allow)
        VALUES (%s,%s,%s)
        ON CONFLICT (role_code,perm_code) DO NOTHING
    """, rp)

def seed_orgs_hotels(conn, num_orgs=2, hotels_per_org=2):
    now = datetime.now()
    execmany(conn, "INSERT INTO orgs(name, created_at) VALUES(%s,%s)", [(f"Org {i+1}", now) for i in range(num_orgs)])
    orgs = q_all(conn, "SELECT id, name FROM orgs ORDER BY id")
    rows = []
    for o in orgs:
        for j in range(hotels_per_org):
            rows.append((o["id"], f'{o["name"]} - Hotel {j+1}', now))
    execmany(conn, "INSERT INTO hotels(org_id,name,created_at) VALUES(%s,%s,%s)", rows)
    hotels = q_all(conn, "SELECT id, org_id, name FROM hotels ORDER BY org_id, id")
    return orgs, hotels

def seed_users(conn, superadmin_email="sudo@demo.local"):
    execmany(conn, """
        INSERT INTO users(username,email,password_hash,role,area,telefono,activo,is_superadmin)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (email) DO NOTHING
    """, [("sudo", superadmin_email, hp("demo123"), "GERENTE", None, "+51-900000000", True, True)])
    sudo = q_one(conn, "SELECT id FROM users WHERE email=%s", (superadmin_email,))
    return sudo["id"]

def seed_org_memberships(conn, orgs, hotels):
    new_users = []
    for o in orgs:
        org_ix = o["id"]
        new_users.append((f"gerente_o{org_ix}", f"gerente_o{org_ix}@demo.local", hp("demo123"), "GERENTE", None, f"+51-90000{org_ix:03d}", True, False))
        for a in AREAS:
            uname = f"sup_{a.lower()}_o{org_ix}"
            new_users.append((uname, f"{uname}@demo.local", hp("demo123"), "SUPERVISOR", a, f"+51-9{org_ix:02d}10{AREAS.index(a)}", True, False))
        for r in range(1, 3):
            uname = f"rcpt{r}_o{org_ix}"
            new_users.append((uname, f"{uname}@demo.local", hp("demo123"), "RECEPCION", None, f"+51-9{org_ix:02d}20{r}", True, False))
        for a in AREAS:
            for t in range(1, 5):
                uname = f"tech{t}_{a.lower()}_o{org_ix}"
                new_users.append((uname, f"{uname}@demo.local", hp("demo123"), "TECNICO", a, f"+51-9{org_ix:02d}{AREAS.index(a)}{t:02d}", True, False))
    execmany(conn, """
        INSERT INTO users(username,email,password_hash,role,area,telefono,activo,is_superadmin)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (email) DO NOTHING
    """, new_users)

    users = q_all(conn, "SELECT id, username, email, role, area FROM users WHERE is_superadmin=false ORDER BY id")
    by_role = {
        "GERENTE":   [u for u in users if u["role"]=="GERENTE"],
        "SUPERVISOR":[u for u in users if u["role"]=="SUPERVISOR"],
        "RECEPCION": [u for u in users if u["role"]=="RECEPCION"],
        "TECNICO":   [u for u in users if u["role"]=="TECNICO"],
    }
    org_users_rows, ou_areas_rows = [], []
    for o in orgs:
        org_id = o["id"]
        org_hotels = [h for h in hotels if h["org_id"]==org_id]
        default_hotel_id = org_hotels[0]["id"] if org_hotels else None

        g = by_role["GERENTE"].pop(0)
        org_users_rows.append((org_id, g["id"], "GERENTE", None, default_hotel_id))

        for a in AREAS:
            s = next(u for u in by_role["SUPERVISOR"] if u["area"]==a)
            by_role["SUPERVISOR"].remove(s)
            org_users_rows.append((org_id, s["id"], "SUPERVISOR", a, default_hotel_id))
            ou_areas_rows.append((org_id, s["id"], a))

        for _ in range(2):
            rcpt = by_role["RECEPCION"].pop(0)
            org_users_rows.append((org_id, rcpt["id"], "RECEPCION", None, default_hotel_id))
            for a in AREAS:
                ou_areas_rows.append((org_id, rcpt["id"], a))

        for a in AREAS:
            techs = [u for u in by_role["TECNICO"] if u["area"]==a][:4]
            for t in techs:
                by_role["TECNICO"].remove(t)
                org_users_rows.append((org_id, t["id"], "TECNICO", a, default_hotel_id))
                ou_areas_rows.append((org_id, t["id"], a))

    execmany(conn, """
        INSERT INTO orgusers(org_id,user_id,role,default_area,default_hotel_id)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (org_id,user_id) DO NOTHING
    """, org_users_rows)

    execmany(conn, """
        INSERT INTO orguserareas(org_id,user_id,area_code)
        VALUES (%s,%s,%s)
        ON CONFLICT (org_id,user_id,area_code) DO NOTHING
    """, ou_areas_rows)

def seed_sla(conn):
    """
    Seed SLA rules per (org_id, hotel_id, area, prioridad).
    Assumes slarules has NOT NULL org_id, hotel_id and a unique/PK on
    (org_id, hotel_id, area, prioridad).
    """
    # pull all hotels with their org
    hotels = q_all(conn, "SELECT id AS hotel_id, org_id FROM hotels ORDER BY org_id, id")
    if not hotels:
        print("[seed_sla] No hotels found; skipping SLA seed.")
        return

    # base minutes by priority; tweak by area
    base = {"BAJA": 240, "MEDIA": 180, "ALTA": 90, "URGENTE": 45}
    rows = []
    for h in hotels:
        for area in AREAS:
            for prio, mins in base.items():
                tweak = mins + (0 if area == "MANTENCION" else (10 if area == "HOUSEKEEPING" else 20))
                rows.append((h["org_id"], h["hotel_id"], area, prio, tweak))

    execmany(conn, """
        INSERT INTO slarules (org_id, hotel_id, area, prioridad, max_minutes)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """, rows)

    print(f"✓ Seeded SLA rules for {len(hotels)} hotel(s) × {len(AREAS)} áreas × 4 prioridades")

def seed_location_types(conn):
    execmany(conn, """
        INSERT INTO location_types(code,name) VALUES(%s,%s)
        ON CONFLICT (code) DO NOTHING
    """, [
        ("HOTEL","Hotel"),
        ("FLOOR","Piso"),
        ("ROOM","Habitación"),
        ("AREA","Área")
    ])

def seed_locations(conn, hotels, floors_per_hotel=3, rooms_per_floor=20):
    # returns map: hotel_id -> { 'floors': [loc_id], 'rooms': [loc_id], 'any': [loc_id] }
    mapping = {}
    for h in hotels:
        hid = h["id"]
        # Create floor nodes
        floor_rows = []
        for f in range(1, floors_per_hotel+1):
            floor_rows.append((hid, "FLOOR", f"{f}F", f"Piso {f}", None))
        execmany(conn, """
            INSERT INTO locations(hotel_id,type_code,code,name,parent_id) VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (hotel_id,type_code,code) DO NOTHING
        """, floor_rows)

        floors = q_all(conn, "SELECT id, code FROM locations WHERE hotel_id=%s AND type_code='FLOOR' ORDER BY code", (hid,))
        # Create room nodes under each floor
        room_rows = []
        for fl in floors:
            fnum = int(fl["code"].replace("F",""))
            start = fnum*100 + 1
            for r in range(start, start + rooms_per_floor):
                room_rows.append((hid, "ROOM", str(r), f"Habitación {r}", fl["id"]))
        execmany(conn, """
            INSERT INTO locations(hotel_id,type_code,code,name,parent_id) VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (hotel_id,type_code,code) DO NOTHING
        """, room_rows)

        rooms = q_all(conn, "SELECT id, code FROM locations WHERE hotel_id=%s AND type_code='ROOM' ORDER BY code", (hid,))
        mapping[hid] = {"floors": [fl["id"] for fl in floors], "rooms": [rm["id"] for rm in rooms]}
    return mapping

def seed_assets(conn, hotels, loc_map, assets_per_hotel=25):
    rows = []
    for h in hotels:
        hid = h["id"]
        rooms = loc_map[hid]["rooms"]
        for i in range(assets_per_hotel):
            loc_id = RNG.choice(rooms) if rooms else None
            cat = RNG.choice(ASSET_CATEGORIES)
            rows.append((
                hid, loc_id, f"Equipo {i+1} ({cat})", cat,
                f"S{hid}-{i+1:04d}", RNG.choice(["ACTIVO","FUERA_DE_SERVICIO","MANTENCION"]),
                f"QR-{hid}-{i+1:04d}"
            ))
    execmany(conn, """
        INSERT INTO assets(hotel_id,location_id,name,category,serial,status,qr_code)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """, rows)

def seed_pms(conn, hotels, rooms_per_hotel=60):
    # Create synthetic in-house / checked-out guests per hotel
    for h in hotels:
        today = datetime.now().date()
        rows = []
        base_room = 101
        for r in range(base_room, base_room + rooms_per_hotel):
            in_house = RNG.random() < 0.75
            status = "IN_HOUSE" if in_house else "CHECKED_OUT"
            checkin = datetime.combine(today - timedelta(days=RNG.randint(0,3)), datetime.min.time())
            checkout = datetime.combine(today + timedelta(days=RNG.randint(0,3)), datetime.min.time())
            rows.append((f"PMS{h['id']}-{r}", f"Huesped {r} ({h['name']})", str(r), status, checkin, checkout))
        execmany(conn, """
            INSERT INTO pmsguests(huesped_id,nombre,habitacion,status,checkin,checkout)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, rows)

def seed_taxonomies(conn):
    execmany(conn, "INSERT INTO ticket_tags(tag) VALUES(%s) ON CONFLICT (tag) DO NOTHING", [(t,) for t in TAGS_SEED])
    execmany(conn, """
        INSERT INTO ticket_types(code,name,area) VALUES (%s,%s,%s)
        ON CONFLICT (code) DO NOTHING
    """, TICKET_TYPES_SEED)

def sla_minutes_pg(conn, area, prioridad, org_id=None, hotel_id=None):
    # Resolution order: exact match -> org override -> global
    r = q_one(conn, "SELECT max_minutes FROM slarules WHERE area=%s AND prioridad=%s AND org_id=%s AND hotel_id=%s",
              (area, prioridad, org_id, hotel_id))
    if r: return int(r["max_minutes"])
    r = q_one(conn, "SELECT max_minutes FROM slarules WHERE area=%s AND prioridad=%s AND org_id=%s AND hotel_id IS NULL",
              (area, prioridad, org_id))
    if r: return int(r["max_minutes"])
    r = q_one(conn, "SELECT max_minutes FROM slarules WHERE area=%s AND prioridad=%s AND org_id IS NULL AND hotel_id IS NULL",
              (area, prioridad))
    return int(r["max_minutes"]) if r else None

def compute_due(conn, created_at, org_id, hotel_id, area, prioridad):
    mins = sla_minutes_pg(conn, area, prioridad, org_id, hotel_id)
    return created_at + timedelta(minutes=mins) if mins else None

def random_ticket_times(conn, base, org_id, hotel_id, estado, area, prioridad):
    created_at = base
    due_dt = compute_due(conn, created_at, org_id, hotel_id, area, prioridad)
    accepted_at = started_at = finished_at = None
    if estado in ("ASIGNADO","ACEPTADO","EN_CURSO","PAUSADO","DERIVADO","RESUELTO"):
        accepted_at = created_at + timedelta(minutes=RNG.randint(3, 30))
    if estado in ("EN_CURSO","PAUSADO","DERIVADO","RESUELTO"):
        started_at = (accepted_at or created_at) + timedelta(minutes=RNG.randint(5, 40))
    if estado == "RESUELTO":
        jitter = RNG.randint(-30, 120)
        finished_at = (started_at or created_at) + timedelta(minutes=max(10, RNG.randint(10, 90) + jitter))
    return created_at, due_dt, accepted_at, started_at, finished_at

def seed_tickets(conn, total=150, days_back=10, hotels=None, loc_map=None):
    # creators: GERENTE/SUPERVISOR/RECEPCION
    creators = q_all(conn, """
        SELECT u.id, u.role, ou.org_id, ou.default_hotel_id AS hotel_id
        FROM users u JOIN orgusers ou ON ou.user_id=u.id
        WHERE ou.role IN ('GERENTE','SUPERVISOR','RECEPCION')
    """)
    techs = q_all(conn, """
        SELECT u.id, u.area, ou.org_id, ou.default_hotel_id AS hotel_id
        FROM users u JOIN orgusers ou ON ou.user_id=u.id
        WHERE ou.role='TECNICO'
    """)
    rooms_in = q_all(conn, "SELECT huesped_id, habitacion FROM pmsguests WHERE status='IN_HOUSE'")

    # load types for nicer seeding
    types = q_all(conn, "SELECT code, name, area FROM ticket_types")
    type_by_area = defaultdict(list)
    for t in types:
        type_by_area[t["area"]].append(t["code"])

    rows_t = []
    rows_h = []
    rows_tagmap = []
    rows_attach = []
    rows_comment = []
    rows_voice = []
    rows_tassets = []

    now = datetime.now()

    # pick some assets per hotel for linking
    assets_by_hotel_area = defaultdict(list)
    aset = q_all(conn, """
        SELECT a.id, a.hotel_id, l.id as loc_id
        FROM assets a LEFT JOIN locations l ON l.id=a.location_id
    """)
    for a in aset:
        assets_by_hotel_area[(a["hotel_id"], "ANY")].append(a["id"])

    for _ in range(total):
        creator = RNG.choice(creators)
        org_id = creator["org_id"]; hotel_id = creator["hotel_id"]
        area = RNG.choice(AREAS)
        prioridad = RNG.choices(PRIOS, weights=[2,3,3,2], k=1)[0]
        estado = RNG.choices(ALL_STATES, weights=[2,2,2,2,1,1,3], k=1)[0]

        created_at = now - timedelta(days=RNG.uniform(0, days_back), minutes=RNG.randint(0, 600))
        created_at, due_at, accepted_at, started_at, finished_at = random_ticket_times(conn, created_at, org_id, hotel_id, estado, area, prioridad)

        canal = RNG.choices(["recepcion","huesped_whatsapp","housekeeping_whatsapp","mantenimiento_app","roomservice_llamada"],
                            weights=[4,3,2,1,1], k=1)[0]

        # Optional: guest + ubicacion
        if RNG.random() < 0.7 and rooms_in:
            rr = RNG.choice(rooms_in)
            huesped_id = rr["huesped_id"]; ubicacion = rr["habitacion"]
        else:
            huesped_id = None; ubicacion = RNG.choice(["Lobby","Piscina","Gimnasio","Spa","Restaurante","Pasillo 2F"])

        # Choose a location_id if hotel has rooms
        location_id = None
        if hotel_id and loc_map and hotel_id in loc_map and loc_map[hotel_id]["rooms"]:
            location_id = RNG.choice(loc_map[hotel_id]["rooms"])

        # tipo from catalog where area matches (fallback None)
        tipo = RNG.choice(type_by_area.get(area, [None]))

        detalle = RNG.choice([
            "Aire acondicionado no enfría",
            "No hay toallas en la habitación",
            "Fuga de agua en el lavatorio",
            "Luz parpadea en el pasillo",
            "Ruido de ventilación",
            "Televisor sin señal",
            "Sábanas adicionales solicitadas",
            "Room service: café y sándwich",
        ])

        assigned_to = None
        if estado in ("ASIGNADO","ACEPTADO","EN_CURSO","PAUSADO","DERIVADO","RESUELTO"):
            candidates = [t for t in techs if t["org_id"]==org_id and t["hotel_id"]==hotel_id and t["area"]==area]
            if not candidates:
                candidates = [t for t in techs if t["org_id"]==org_id and t["area"]==area] or techs
            assigned_to = RNG.choice(candidates)["id"]

        # Approval (simulate recepcion auto-approved ~60%)
        approved = RNG.random() < 0.6
        approved_by = assigned_to if approved else None
        approved_at = (created_at + timedelta(minutes=RNG.randint(1,10))) if approved else None

        rows_t.append((org_id, hotel_id, area, prioridad, estado, detalle, canal, ubicacion, huesped_id,
                       created_at, due_at, assigned_to, creator["id"], None,
                       RNG.choice([False, True]), accepted_at, started_at, finished_at,
                       approved, approved_by, approved_at, None, None, None, tipo, None, location_id))

    execmany(conn, """
        INSERT INTO tickets(
          org_id, hotel_id, area, prioridad, estado, detalle, canal_origen, ubicacion, huesped_id,
          created_at, due_at, assigned_to, created_by, confidence_score,
          qr_required, accepted_at, started_at, finished_at,
          approved, approved_by, approved_at, deleted_at, deleted_by, delete_reason,
          tipo, external_ref, location_id
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
          %s,%s,%s,%s,%s,%s,%s,%s,%s
        )
    """, rows_t)

    # History + tags + attachments + comments + voice + asset links
    all_t = q_all(conn, "SELECT id, created_by, accepted_at, started_at, finished_at, created_at, hotel_id FROM tickets ORDER BY id")
    for r in all_t:
        tid = r["id"]; creator = r["created_by"]
        rows_h.append((tid, creator, "CREADO", None, r["created_at"]))
        if r["accepted_at"]: rows_h.append((tid, creator, "ACEPTADO", None, r["accepted_at"]))
        if r["started_at"]:  rows_h.append((tid, creator, "INICIADO", None, r["started_at"]))
        if r["finished_at"]: rows_h.append((tid, creator, "RESUELTO", None, r["finished_at"]))

        # random tag(s)
        for t in RNG.sample(TAGS_SEED, k=RNG.randint(0,2)):
            rows_tagmap.append((tid, t))

        # optionally attach 0-2 fake attachments (URLs are placeholders)
        for _ in range(RNG.randint(0,2)):
            rows_attach.append((tid, RNG.choice(["IMAGE","PDF","OTHER"]), f"https://example.com/ticket/{tid}/file{RNG.randint(1,9)}.jpg",
                                "image/jpeg", RNG.randint(50_000, 900_000), creator, datetime.now()))

        # 0-2 comments
        for _ in range(RNG.randint(0,2)):
            rows_comment.append((tid, creator, RNG.choice([
                "Revisar con priorización alta.",
                "Cliente indica que es urgente.",
                "Se solicitó confirmación del huésped.",
                "Se coordinó con mantenimiento."
            ]), RNG.random() < 0.2, datetime.now()))

        # occasional voice notes
        if RNG.random() < 0.15:
            rows_voice.append((tid, f"https://example.com/ticket/{tid}/voice.mp3", "Transcripción pendiente...",
                               "es", RNG.randint(5, 90), creator, datetime.now()))

        # link a random asset from hotel
        aset_pool = assets_by_hotel_area.get((r["hotel_id"], "ANY"), [])
        if aset_pool and RNG.random() < 0.4:
            rows_tassets.append((tid, RNG.choice(aset_pool)))

    execmany(conn, """
        INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at)
        VALUES (%s,%s,%s,%s,%s)
    """, rows_h)

    execmany(conn, """
        INSERT INTO ticket_tag_map(ticket_id, tag)
        VALUES (%s,%s)
        ON CONFLICT DO NOTHING
    """, rows_tagmap)

    execmany(conn, """
        INSERT INTO ticket_attachments(ticket_id, kind, url, mime, size_bytes, created_by, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """, rows_attach)

    execmany(conn, """
        INSERT INTO ticket_comments(ticket_id, author_id, body, is_internal, created_at)
        VALUES (%s,%s,%s,%s,%s)
    """, rows_comment)

    execmany(conn, """
        INSERT INTO ticket_voice_notes(ticket_id, audio_url, transcript, lang, duration_sec, created_by, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """, rows_voice)

    execmany(conn, """
        INSERT INTO ticket_assets(ticket_id, asset_id)
        VALUES (%s,%s)
        ON CONFLICT DO NOTHING
    """, rows_tassets)

def seed_kpis(conn, days_back=10):
    # recompute simple daily KPIs from tickets
    today = date.today()
    for d in range(days_back, -1, -1):
        day = today - timedelta(days=d)
        # group by org/hotel
        rows = q_all(conn, """
            WITH day_t AS (
              SELECT * FROM tickets
              WHERE created_at::date <= %s
            )
            SELECT
              org_id, hotel_id
            FROM day_t
            GROUP BY org_id, hotel_id
        """, (day,))
        for r in rows:
            org_id, hotel_id = r["org_id"], r["hotel_id"]
            open_total = q_one(conn, """
                SELECT COUNT(*) AS c FROM tickets
                WHERE org_id=%s AND hotel_id=%s AND created_at::date <= %s
                  AND (estado != 'RESUELTO' OR finished_at::date > %s OR finished_at IS NULL)
            """, (org_id, hotel_id, day, day))["c"]

            resolved_total = q_one(conn, """
                SELECT COUNT(*) AS c FROM tickets
                WHERE org_id=%s AND hotel_id=%s AND finished_at::date = %s
            """, (org_id, hotel_id, day))["c"]

            # compute SLA rate for day: proportion of tickets finished *on time* that day
            sla_row = q_one(conn, """
                SELECT
                  COUNT(*) FILTER (WHERE due_at IS NOT NULL AND finished_at IS NOT NULL AND finished_at <= due_at AND finished_at::date=%s)::float
                  /
                  NULLIF(COUNT(*) FILTER (WHERE finished_at IS NOT NULL AND finished_at::date=%s),0)::float
                  AS rate
                FROM tickets
                WHERE org_id=%s AND hotel_id=%s
            """, (day, day, org_id, hotel_id))
            sla_rate = round((sla_row["rate"] or 0.0)*100, 2) if sla_row and sla_row["rate"] is not None else None

            # TTR average (min) for tickets resolved that day
            ttr_row = q_one(conn, """
                SELECT AVG(EXTRACT(EPOCH FROM (finished_at - created_at))/60.0) AS ttr
                FROM tickets
                WHERE org_id=%s AND hotel_id=%s AND finished_at::date=%s
            """, (org_id, hotel_id, day))
            ttr_avg = round(float(ttr_row["ttr"]), 2) if ttr_row and ttr_row["ttr"] is not None else None

            # Distribution by area (all tickets created that day)
            by_area = q_all(conn, """
                SELECT area, COUNT(*) AS c
                FROM tickets
                WHERE org_id=%s AND hotel_id=%s AND created_at::date=%s
                GROUP BY area
            """, (org_id, hotel_id, day))
            by_area_json = {row["area"]: int(row["c"]) for row in by_area}

            exec_sql(conn, """
                INSERT INTO kpi_daily(org_id, hotel_id, day, open_total, resolved_total, sla_rate, ttr_avg_min, by_area)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (org_id, hotel_id, day) DO UPDATE
                SET open_total=EXCLUDED.open_total,
                    resolved_total=EXCLUDED.resolved_total,
                    sla_rate=EXCLUDED.sla_rate,
                    ttr_avg_min=EXCLUDED.ttr_avg_min,
                    by_area=EXCLUDED.by_area
            """, (org_id, hotel_id, day, open_total, resolved_total, sla_rate, ttr_avg, extras.Json(by_area_json)))

def seed_webhooks_sample(conn, orgs):
    # Example inactive webhook entries (no side effects)
    rows = []
    for o in orgs:
        rows.append((o["id"], "ticket.created", "https://example.com/webhooks/ticket-created", None, False))
        rows.append((o["id"], "ticket.resolved", "https://example.com/webhooks/ticket-resolved", None, False))
    execmany(conn, """
        INSERT INTO webhooks(org_id, event, url, secret, active)
        VALUES (%s,%s,%s,%s,%s)
    """, rows)

def seed_summaries(conn):
    print("\nLogins (demo users):")
    print("  Superadmin  -> sudo@demo.local / demo123")
    gs = q_all(conn, "SELECT email FROM users WHERE role='GERENTE' AND is_superadmin=false LIMIT 3")
    ss = q_all(conn, "SELECT email FROM users WHERE role='SUPERVISOR' LIMIT 3")
    rs = q_all(conn, "SELECT email FROM users WHERE role='RECEPCION' LIMIT 3")
    ts = q_all(conn, "SELECT email FROM users WHERE role='TECNICO' LIMIT 3")
    def fmt(lst): return ", ".join([r["email"] for r in lst])
    print("  Gerentes    -> " + fmt(gs))
    print("  Recepción   -> " + fmt(rs))
    print("  Supervisores-> " + fmt(ss))
    print("  Técnicos    -> " + fmt(ts))

# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser(description="Seed Supabase (Postgres) with Hestia Ops schema + data")
    ap.add_argument("--reset", action="store_true", help="drop tables and recreate schema")
    ap.add_argument("--tickets", type=int, default=150)
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--orgs", type=int, default=2)
    ap.add_argument("--hotels-per-org", type=int, default=2)
    ap.add_argument("--superadmin-email", type=str, default="sudo@demo.local")
    ap.add_argument("--floors", type=int, default=3)
    ap.add_argument("--rooms-per-floor", type=int, default=20)
    ap.add_argument("--assets-per-hotel", type=int, default=25)
    ap.add_argument("--skip-kpis", action="store_true", help="skip KPI snapshot computation")
    args = ap.parse_args()

    conn = connect()
    try:
        if args.reset:
            reset_db(conn)
            print("✓ Reset schema")
        else:
            ensure_schema(conn)
            print("✓ Ensured schema")

        seed_rbac(conn)
        orgs, hotels = seed_orgs_hotels(conn, args.orgs, args.hotels_per_org)
        sudo_id = seed_users(conn, args.superadmin_email)
        seed_org_memberships(conn, orgs, hotels)
        seed_sla(conn)
        seed_location_types(conn)
        loc_map = seed_locations(conn, hotels, floors_per_hotel=args.floors, rooms_per_floor=args.rooms_per_floor)
        seed_assets(conn, hotels, loc_map, assets_per_hotel=args.assets_per_hotel)
        seed_pms(conn, hotels, rooms_per_hotel=min(60, args.rooms_per_floor * args.floors))
        seed_taxonomies(conn)
        seed_tickets(conn, total=args.tickets, days_back=args.days, hotels=hotels, loc_map=loc_map)
        if not args.skip_kpis:
            seed_kpis(conn, days_back=args.days)
        seed_webhooks_sample(conn, orgs)
        seed_summaries(conn)
        print("\n✅ Done. Your new Supabase is ready.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
