# seed_supabase.py
# Build & seed your schema directly in Supabase Postgres.
# Usage examples:
#   set DATABASE_URL=postgresql://postgres:...@db.<proj>.supabase.co:5432/postgres?sslmode=require
#   python seed_supabase.py --reset
#   python seed_supabase.py --tickets 150 --days 14 --orgs 2 --hotels-per-org 2

import argparse
import os
import random
import hashlib
from datetime import datetime, timedelta

import psycopg2
from psycopg2 import extras

RNG = random.Random(42)  # deterministic
DB_DSN = os.getenv("DATABASE_URL")
if not DB_DSN:
    raise SystemExit("Missing DATABASE_URL env var (Supabase connection string).")

AREAS = ["MANTENCION", "HOUSEKEEPING", "ROOMSERVICE"]
PRIOS = ["BAJA", "MEDIA", "ALTA", "URGENTE"]
OPEN_STATES = ("PENDIENTE","ASIGNADO","ACEPTADO","EN_CURSO","PAUSADO","DERIVADO")
ALL_STATES = OPEN_STATES + ("RESUELTO",)

def hp(p: str) -> str:
    return hashlib.sha256(p.encode("utf-8")).hexdigest()

def connect():
    # sslmode is usually already in the DSN (?sslmode=require)
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

SCHEMA_SQL = """
-- ROLES / PERMISSIONS
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

-- ORGS & HOTELS
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

-- USERS & MEMBERSHIP
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

-- SLA rules
CREATE TABLE IF NOT EXISTS slarules (
  area TEXT NOT NULL,
  prioridad TEXT NOT NULL,
  max_minutes INTEGER NOT NULL,
  PRIMARY KEY (area, prioridad)
);

-- PMS cache
CREATE TABLE IF NOT EXISTS pmsguests (
  id BIGSERIAL PRIMARY KEY,
  huesped_id TEXT NOT NULL,
  nombre TEXT NOT NULL,
  habitacion TEXT NOT NULL,
  status TEXT NOT NULL,
  checkin TIMESTAMP,
  checkout TIMESTAMP
);

-- Tickets
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
  finished_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tickets_state    ON tickets(estado);
CREATE INDEX IF NOT EXISTS idx_tickets_created  ON tickets(created_at);
CREATE INDEX IF NOT EXISTS idx_tickets_scope    ON tickets(org_id, hotel_id);
CREATE INDEX IF NOT EXISTS idx_tickets_assigned ON tickets(assigned_to);

-- Ticket history
CREATE TABLE IF NOT EXISTS tickethistory (
  id BIGSERIAL PRIMARY KEY,
  ticket_id BIGINT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  actor_user_id BIGINT REFERENCES users(id),
  action TEXT NOT NULL,
  motivo TEXT,
  at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ticket_history_ticket ON tickethistory(ticket_id);
"""

def reset_db(conn):
    # drop in FK-safe order
    exec_sql(conn, "DROP TABLE IF EXISTS tickethistory CASCADE;")
    exec_sql(conn, "DROP TABLE IF EXISTS tickets CASCADE;")
    exec_sql(conn, "DROP TABLE IF EXISTS orguserareas CASCADE;")
    exec_sql(conn, "DROP TABLE IF EXISTS orgusers CASCADE;")
    exec_sql(conn, "DROP TABLE IF EXISTS pmsguests CASCADE;")
    exec_sql(conn, "DROP TABLE IF EXISTS slarules CASCADE;")
    exec_sql(conn, "DROP TABLE IF EXISTS hotels CASCADE;")
    exec_sql(conn, "DROP TABLE IF EXISTS orgs CASCADE;")
    exec_sql(conn, "DROP TABLE IF EXISTS rolepermissions CASCADE;")
    exec_sql(conn, "DROP TABLE IF EXISTS permissions CASCADE;")
    exec_sql(conn, "DROP TABLE IF EXISTS roles CASCADE;")
    exec_sql(conn, "DROP TABLE IF EXISTS users CASCADE;")
    exec_sql(conn, SCHEMA_SQL)

def ensure_schema(conn):
    exec_sql(conn, SCHEMA_SQL)

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
    rows = []
    default = {"BAJA":240, "MEDIA":180, "ALTA":90, "URGENTE":45}
    for area in AREAS:
        for p, m in default.items():
            tweak = m + (0 if area=="MANTENCION" else (10 if area=="HOUSEKEEPING" else 20))
            rows.append((area, p, tweak))
    execmany(conn, """
        INSERT INTO slarules(area,prioridad,max_minutes)
        VALUES(%s,%s,%s)
        ON CONFLICT (area,prioridad) DO NOTHING
    """, rows)

def seed_pms(conn, num_rooms=60):
    today = datetime.now().date()
    rooms = []
    for r in range(101, 101 + num_rooms):
        in_house = RNG.random() < 0.75
        status = "IN_HOUSE" if in_house else "CHECKED_OUT"
        checkin = datetime.combine(today - timedelta(days=RNG.randint(0,3)), datetime.min.time())
        checkout = datetime.combine(today + timedelta(days=RNG.randint(0,3)), datetime.min.time())
        rooms.append((f"PMS{r}", f"Huesped {r}", str(r), status, checkin, checkout))
    execmany(conn, """
        INSERT INTO pmsguests(huesped_id,nombre,habitacion,status,checkin,checkout)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, rooms)

def sla_minutes_pg(conn, area, prioridad):
    r = q_one(conn, "SELECT max_minutes FROM slarules WHERE area=%s AND prioridad=%s", (area, prioridad))
    return int(r["max_minutes"]) if r else None

def compute_due(conn, created_at, area, prioridad):
    mins = sla_minutes_pg(conn, area, prioridad)
    return created_at + timedelta(minutes=mins) if mins else None

def random_ticket_times(conn, base, estado, area, prioridad):
    created_at = base
    due_dt = compute_due(conn, created_at, area, prioridad)
    accepted_at = started_at = finished_at = None
    if estado in ("ASIGNADO","ACEPTADO","EN_CURSO","PAUSADO","DERIVADO","RESUELTO"):
        accepted_at = created_at + timedelta(minutes=RNG.randint(3, 30))
    if estado in ("EN_CURSO","PAUSADO","DERIVADO","RESUELTO"):
        started_at = (accepted_at or created_at) + timedelta(minutes=RNG.randint(5, 40))
    if estado == "RESUELTO":
        jitter = RNG.randint(-30, 120)
        finished_at = (started_at or created_at) + timedelta(minutes=max(10, RNG.randint(10, 90) + jitter))
    return created_at, due_dt, accepted_at, started_at, finished_at

def seed_tickets(conn, total=150, days_back=10):
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

    rows_t = []
    rows_h = []
    now = datetime.now()

    for _ in range(total):
        creator = RNG.choice(creators)
        org_id = creator["org_id"]; hotel_id = creator["hotel_id"]
        area = RNG.choice(AREAS)
        prioridad = RNG.choices(PRIOS, weights=[2,3,3,2], k=1)[0]
        estado = RNG.choices(ALL_STATES, weights=[2,2,2,2,1,1,3], k=1)[0]

        created_at = now - timedelta(days=RNG.uniform(0, days_back), minutes=RNG.randint(0, 600))
        created_at, due_at, accepted_at, started_at, finished_at = random_ticket_times(conn, created_at, estado, area, prioridad)

        canal = RNG.choices(["recepcion","huesped_whatsapp","housekeeping_whatsapp","mantenimiento_app","roomservice_llamada"],
                            weights=[4,3,2,1,1], k=1)[0]
        if RNG.random() < 0.7 and rooms_in:
            rr = RNG.choice(rooms_in)
            huesped_id = rr["huesped_id"]; ubicacion = rr["habitacion"]
        else:
            huesped_id = None; ubicacion = RNG.choice(["Lobby","Piscina","Gimnasio","Spa","Restaurante","Pasillo 2F"])
        detalle = RNG.choice([
            "Aire acondicionado no funciona","No hay toallas","Fuga de agua en el lavatorio",
            "Luz parpadea","Ruido de ventilación","Televisor sin señal",
            "Solicitud de sábanas adicionales","Pedido de room service: café y sándwich",
        ])

        assigned_to = None
        if estado in ("ASIGNADO","ACEPTADO","EN_CURSO","PAUSADO","DERIVADO","RESUELTO"):
            candidates = [t for t in techs if t["org_id"]==org_id and t["hotel_id"]==hotel_id and t["area"]==area]
            if not candidates:
                candidates = [t for t in techs if t["org_id"]==org_id and t["area"]==area] or techs
            assigned_to = RNG.choice(candidates)["id"]

        rows_t.append((org_id, hotel_id, area, prioridad, estado, detalle, canal, ubicacion, huesped_id,
                       created_at, due_at, assigned_to, creator["id"], None, RNG.choice([False, True]),
                       accepted_at, started_at, finished_at))

    execmany(conn, """
        INSERT INTO tickets(
          org_id, hotel_id, area, prioridad, estado, detalle, canal_origen, ubicacion, huesped_id,
          created_at, due_at, assigned_to, created_by, confidence_score,
          qr_required, accepted_at, started_at, finished_at
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        )
    """, rows_t)

    for r in q_all(conn, "SELECT id, created_by, accepted_at, started_at, finished_at, created_at FROM tickets"):
        tid = r["id"]; creator = r["created_by"]
        rows_h.append((tid, creator, "CREADO", None, r["created_at"]))
        if r["accepted_at"]: rows_h.append((tid, creator, "ACEPTADO", None, r["accepted_at"]))
        if r["started_at"]:  rows_h.append((tid, creator, "INICIADO", None, r["started_at"]))
        if r["finished_at"]: rows_h.append((tid, creator, "RESUELTO", None, r["finished_at"]))

    execmany(conn, """
        INSERT INTO tickethistory(ticket_id, actor_user_id, action, motivo, at)
        VALUES (%s,%s,%s,%s,%s)
    """, rows_h)

def seed_summaries(conn):
    print("\nLogins:")
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

def main():
    ap = argparse.ArgumentParser(description="Seed Supabase (Postgres) with demo data")
    ap.add_argument("--reset", action="store_true", help="drop tables and recreate schema")
    ap.add_argument("--tickets", type=int, default=150)
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--orgs", type=int, default=2)
    ap.add_argument("--hotels-per-org", type=int, default=2)
    ap.add_argument("--superadmin-email", type=str, default="sudo@demo.local")
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
        seed_users(conn, args.superadmin_email)
        seed_org_memberships(conn, orgs, hotels)
        seed_sla(conn)
        seed_pms(conn, num_rooms=60)
        seed_tickets(conn, total=args.tickets, days_back=args.days)
        seed_summaries(conn)
        print("\n✅ Done. Your Supabase is ready.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
