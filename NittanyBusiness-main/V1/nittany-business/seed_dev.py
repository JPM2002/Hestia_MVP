# seed_dev.py
# Multi-tenant + RBAC seeder for hestia_V2.db
# Usage:
#   python seed_dev.py --reset
#   python seed_dev.py --tickets 150 --days 14 --orgs 2 --hotels-per-org 2

import argparse
import os
import random
import sqlite3 as sql
from datetime import datetime, timedelta
import hashlib

DB_PATH = "hestia_V2.db"
RNG = random.Random(42)  # deterministic

# Operational areas that own work (Recepción triages, not an ops area)
AREAS = ["MANTENCION", "HOUSEKEEPING", "ROOMSERVICE"]
PRIOS = ["BAJA", "MEDIA", "ALTA", "URGENTE"]
OPEN_STATES = ("PENDIENTE", "ASIGNADO", "ACEPTADO", "EN_CURSO", "PAUSADO", "DERIVADO")
ALL_STATES = OPEN_STATES + ("RESUELTO",)

# ---------- helpers ----------
def hp(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def db():
    conn = sql.connect(DB_PATH)
    conn.row_factory = sql.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def execmany(conn, q, rows):
    if not rows:
        return
    conn.executemany(q, rows)

# ---------- schema ----------
SCHEMA_SQL = """
-- Users (with is_superadmin)
CREATE TABLE IF NOT EXISTS Users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE,
  email TEXT UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL,                  -- base role hint (GERENTE|SUPERVISOR|RECEPCION|TECNICO)
  area TEXT,                           -- legacy single-area hint
  telefono TEXT,
  activo INTEGER NOT NULL DEFAULT 1,
  is_superadmin INTEGER NOT NULL DEFAULT 0
);

-- Orgs / Hotels (multi-tenant)
CREATE TABLE IF NOT EXISTS Orgs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS Hotels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  org_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(org_id) REFERENCES Orgs(id) ON DELETE CASCADE
);

-- Membership in org
CREATE TABLE IF NOT EXISTS OrgUsers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  org_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  role TEXT NOT NULL,           -- org-scoped role: SUPERADMIN (implicit), GERENTE, SUPERVISOR, RECEPCION, TECNICO
  default_area TEXT,
  default_hotel_id INTEGER,
  UNIQUE(org_id, user_id),
  FOREIGN KEY(org_id) REFERENCES Orgs(id) ON DELETE CASCADE,
  FOREIGN KEY(user_id) REFERENCES Users(id) ON DELETE CASCADE,
  FOREIGN KEY(default_hotel_id) REFERENCES Hotels(id) ON DELETE SET NULL
);

-- Multi-area assignment per org member
CREATE TABLE IF NOT EXISTS OrgUserAreas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  org_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  area_code TEXT NOT NULL,            -- e.g., 'MANTENCION', 'HOUSEKEEPING', 'ROOMSERVICE'
  UNIQUE(org_id, user_id, area_code),
  FOREIGN KEY(org_id) REFERENCES Orgs(id) ON DELETE CASCADE,
  FOREIGN KEY(user_id) REFERENCES Users(id) ON DELETE CASCADE
);

-- RBAC: roles, permissions, mapping
CREATE TABLE IF NOT EXISTS Roles (
  code TEXT PRIMARY KEY,              -- SUPERADMIN, GERENTE, SUPERVISOR, RECEPCION, TECNICO
  name TEXT NOT NULL,
  inherits_code TEXT NULL             -- simple single-parent inheritance
);

CREATE TABLE IF NOT EXISTS Permissions (
  code TEXT PRIMARY KEY,              -- e.g., 'ticket.create'
  name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS RolePermissions (
  role_code TEXT NOT NULL,
  perm_code TEXT NOT NULL,
  allow INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY(role_code, perm_code),
  FOREIGN KEY(role_code) REFERENCES Roles(code) ON DELETE CASCADE,
  FOREIGN KEY(perm_code) REFERENCES Permissions(code) ON DELETE CASCADE
);

-- Tickets scoped by org/hotel
CREATE TABLE IF NOT EXISTS Tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  org_id INTEGER NOT NULL,
  hotel_id INTEGER NOT NULL,
  area TEXT NOT NULL,
  prioridad TEXT NOT NULL,
  estado TEXT NOT NULL,
  detalle TEXT NOT NULL,
  canal_origen TEXT NOT NULL,
  ubicacion TEXT NOT NULL,
  huesped_id TEXT,
  created_at TEXT NOT NULL,
  due_at TEXT,
  assigned_to INTEGER,
  created_by INTEGER,
  confidence_score REAL,
  qr_required INTEGER NOT NULL DEFAULT 0,
  accepted_at TEXT,
  started_at TEXT,
  finished_at TEXT,
  FOREIGN KEY(org_id) REFERENCES Orgs(id) ON DELETE CASCADE,
  FOREIGN KEY(hotel_id) REFERENCES Hotels(id) ON DELETE CASCADE
);

-- Ticket history (append-only log)
CREATE TABLE IF NOT EXISTS TicketHistory (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id INTEGER NOT NULL,
  actor_user_id INTEGER,
  action TEXT NOT NULL,
  motivo TEXT,
  at TEXT NOT NULL,
  FOREIGN KEY(ticket_id) REFERENCES Tickets(id) ON DELETE CASCADE
);

-- SLA Rules (global for MVP)
CREATE TABLE IF NOT EXISTS SLARules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  area TEXT NOT NULL,
  prioridad TEXT NOT NULL,
  max_minutes INTEGER NOT NULL
);

-- PMS cache (global MVP)
CREATE TABLE IF NOT EXISTS PMSGuests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  huesped_id TEXT NOT NULL,
  nombre TEXT NOT NULL,
  habitacion TEXT NOT NULL,
  status TEXT NOT NULL,                -- IN_HOUSE / CHECKED_OUT / ...
  checkin TEXT,
  checkout TEXT
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_tickets_state ON Tickets(estado);
CREATE INDEX IF NOT EXISTS idx_tickets_created ON Tickets(created_at);
CREATE INDEX IF NOT EXISTS idx_tickets_scope ON Tickets(org_id, hotel_id);
CREATE INDEX IF NOT EXISTS idx_tickets_assigned ON Tickets(assigned_to);
CREATE INDEX IF NOT EXISTS idx_ticket_history_ticket ON TicketHistory(ticket_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sla_unique ON SLARules(area, prioridad);
"""

# ---------- SLA helpers ----------
def sla_minutes(area: str, prioridad: str) -> int | None:
    with db() as conn:
        r = conn.execute(
            "SELECT max_minutes FROM SLARules WHERE area=? AND prioridad=?",
            (area, prioridad)
        ).fetchone()
        return int(r["max_minutes"]) if r else None

def compute_due(created_at: datetime, area: str, prioridad: str) -> datetime | None:
    mins = sla_minutes(area, prioridad)
    return created_at + timedelta(minutes=mins) if mins else None

# ---------- seed routines ----------
def reset_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    with db() as conn:
        conn.executescript(SCHEMA_SQL)
    print("✓ Database created and schema applied.")

def seed_rbac():
    roles = [
        ("SUPERADMIN", "Super Admin", None),
        ("GERENTE", "Gerente", None),
        ("SUPERVISOR", "Supervisor", None),
        ("RECEPCION", "Recepción", None),
        ("TECNICO", "Técnico", None),
    ]
    perms = [
        ("ticket.view.all", "Ver todos los tickets de la organización"),
        ("ticket.view.area", "Ver tickets de mis áreas"),
        ("ticket.view.assigned", "Ver tickets asignados a mí"),
        ("ticket.create", "Crear tickets"),
        ("ticket.confirm", "Confirmar tickets (triage)"),
        ("ticket.assign", "Asignar/Reasignar tickets"),
        ("ticket.transition.accept", "Aceptar ticket"),
        ("ticket.transition.start", "Iniciar ticket"),
        ("ticket.transition.pause", "Pausar ticket"),
        ("ticket.transition.resume", "Reanudar ticket"),
        ("ticket.transition.finish", "Finalizar ticket"),
    ]
    # Default policy:
    rp = []
    # SUPERADMIN: full access (grant all listed perms)
    for p in perms:
        rp.append(("SUPERADMIN", p[0], 1))
    # GERENTE: full org visibility + create/confirm/assign + all transitions
    for code in [
        "ticket.view.all", "ticket.create", "ticket.confirm", "ticket.assign",
        "ticket.transition.accept", "ticket.transition.start",
        "ticket.transition.pause", "ticket.transition.resume", "ticket.transition.finish"
    ]:
        rp.append(("GERENTE", code, 1))
    # SUPERVISOR: area visibility + confirm/assign + all transitions
    for code in [
        "ticket.view.area", "ticket.confirm", "ticket.assign",
        "ticket.transition.accept", "ticket.transition.start",
        "ticket.transition.pause", "ticket.transition.resume", "ticket.transition.finish"
    ]:
        rp.append(("SUPERVISOR", code, 1))
    # RECEPCION: area visibility + create + confirm
    for code in ["ticket.view.area", "ticket.create", "ticket.confirm"]:
        rp.append(("RECEPCION", code, 1))
    # TECNICO: assigned visibility + own transitions
    for code in [
        "ticket.view.assigned",
        "ticket.transition.accept", "ticket.transition.start",
        "ticket.transition.pause", "ticket.transition.resume", "ticket.transition.finish"
    ]:
        rp.append(("TECNICO", code, 1))

    with db() as conn:
        execmany(conn, "INSERT OR IGNORE INTO Roles(code,name,inherits_code) VALUES(?,?,?)", roles)
        execmany(conn, "INSERT OR IGNORE INTO Permissions(code,name) VALUES(?,?)", perms)
        execmany(conn, """
            INSERT OR IGNORE INTO RolePermissions(role_code, perm_code, allow)
            VALUES (?,?,?)
        """, rp)
    print("✓ Seeded RBAC roles, permissions and mappings.")

def seed_orgs_hotels(num_orgs=2, hotels_per_org=2):
    """Returns lists: org_rows, hotel_rows"""
    now = datetime.now().isoformat(timespec="seconds")
    org_rows = [(f"Org {i+1}", now) for i in range(num_orgs)]
    with db() as conn:
        execmany(conn, "INSERT INTO Orgs(name, created_at) VALUES(?,?)", org_rows)
        orgs = conn.execute("SELECT id, name FROM Orgs ORDER BY id").fetchall()

        hotels_rows = []
        for o in orgs:
            for j in range(hotels_per_org):
                hotels_rows.append((o["id"], f"{o['name']} - Hotel {j+1}", now))
        execmany(conn, "INSERT INTO Hotels(org_id, name, created_at) VALUES(?,?,?)", hotels_rows)
        hotels = conn.execute(
            "SELECT id, org_id, name FROM Hotels ORDER BY org_id, id"
        ).fetchall()

    print(f"✓ Seeded {len(orgs)} orgs and {len(hotels)} hotels")
    return orgs, hotels

def seed_users(superadmin_email="sudo@demo.local"):
    # Superadmin
    users = [("sudo", superadmin_email, hp("demo123"), "GERENTE", None, "+51-900000000", 1, 1)]
    with db() as conn:
        execmany(conn, """INSERT INTO Users(username,email,password_hash,role,area,telefono,activo,is_superadmin)
                          VALUES(?,?,?,?,?,?,?,?)""", users)
        sudo = conn.execute("SELECT id FROM Users WHERE email=?", (superadmin_email,)).fetchone()

    print("✓ Seeded superadmin (sudo@demo.local / demo123)")
    return sudo["id"]

def seed_org_memberships(orgs, hotels):
    """
    Create per org:
      - 1 gerente
      - 1 supervisor per area
      - 2 recepcionistas (cover all areas via OrgUserAreas)
      - 4 técnicos per area
    """
    with db() as conn:
        new_users = []
        for o in orgs:
            org_ix = o["id"]
            # gerente
            new_users.append((f"gerente_o{org_ix}", f"gerente_o{org_ix}@demo.local", hp("demo123"), "GERENTE", None, f"+51-90000{org_ix:03d}", 1, 0))
            # supervisors (one per area)
            for a in AREAS:
                uname = f"sup_{a.lower()}_o{org_ix}"
                new_users.append((uname, f"{uname}@demo.local", hp("demo123"), "SUPERVISOR", a, f"+51-9{org_ix:02d}10{AREAS.index(a)}", 1, 0))
            # recepcion (2 per org)
            for r in range(1, 3):
                uname = f"rcpt{r}_o{org_ix}"
                new_users.append((uname, f"{uname}@demo.local", hp("demo123"), "RECEPCION", None, f"+51-9{org_ix:02d}20{r}", 1, 0))
            # technicians
            for a in AREAS:
                for t in range(1, 5):
                    uname = f"tech{t}_{a.lower()}_o{org_ix}"
                    new_users.append((uname, f"{uname}@demo.local", hp("demo123"), "TECNICO", a, f"+51-9{org_ix:02d}{AREAS.index(a)}{t:02d}", 1, 0))

        execmany(conn, """INSERT INTO Users(username,email,password_hash,role,area,telefono,activo,is_superadmin)
                          VALUES(?,?,?,?,?,?,?,?)""", new_users)

        users = conn.execute("SELECT id, username, email, role, area FROM Users WHERE is_superadmin=0").fetchall()
        users_by_role = {
            "GERENTE": [u for u in users if u["role"] == "GERENTE"],
            "SUPERVISOR": [u for u in users if u["role"] == "SUPERVISOR"],
            "RECEPCION": [u for u in users if u["role"] == "RECEPCION"],
            "TECNICO": [u for u in users if u["role"] == "TECNICO"],
        }

        # Memberships & areas
        org_users_rows = []
        ou_areas_rows = []
        for o in orgs:
            org_id = o["id"]
            org_hotels = [h for h in hotels if h["org_id"] == org_id]
            default_hotel_id = org_hotels[0]["id"] if org_hotels else None

            # gerente
            g = users_by_role["GERENTE"].pop(0)
            org_users_rows.append((org_id, g["id"], "GERENTE", None, default_hotel_id))

            # supervisors (bind to their area)
            for a in AREAS:
                s = next(u for u in users_by_role["SUPERVISOR"] if u["area"] == a)
                users_by_role["SUPERVISOR"].remove(s)
                org_users_rows.append((org_id, s["id"], "SUPERVISOR", a, default_hotel_id))
                ou_areas_rows.append((org_id, s["id"], a))

            # recepcion (multi-area: grant all ops areas for triage)
            for _ in range(2):
                rcpt = users_by_role["RECEPCION"].pop(0)
                org_users_rows.append((org_id, rcpt["id"], "RECEPCION", None, default_hotel_id))
                for a in AREAS:
                    ou_areas_rows.append((org_id, rcpt["id"], a))

            # technicians (bind to their area)
            for a in AREAS:
                techs = [u for u in users_by_role["TECNICO"] if u["area"] == a][:4]
                for t in techs:
                    users_by_role["TECNICO"].remove(t)
                    org_users_rows.append((org_id, t["id"], "TECNICO", a, default_hotel_id))
                    ou_areas_rows.append((org_id, t["id"], a))

        execmany(conn, """
            INSERT INTO OrgUsers(org_id, user_id, role, default_area, default_hotel_id)
            VALUES(?,?,?,?,?)
        """, org_users_rows)
        execmany(conn, """
            INSERT OR IGNORE INTO OrgUserAreas(org_id, user_id, area_code)
            VALUES(?,?,?)
        """, ou_areas_rows)

    print(f"✓ Seeded {len(org_users_rows)} org memberships and {len(ou_areas_rows)} area links")
    return True

def seed_sla():
    rows = []
    default = {"BAJA": 240, "MEDIA": 180, "ALTA": 90, "URGENTE": 45}
    for area in AREAS:
        for p, m in default.items():
            tweak = m + (0 if area == "MANTENCION" else (10 if area == "HOUSEKEEPING" else 20))
            rows.append((area, p, tweak))
    with db() as conn:
        execmany(conn, "INSERT OR IGNORE INTO SLARules(area,prioridad,max_minutes) VALUES(?,?,?)", rows)
    print(f"✓ Seeded SLA rules ({len(rows)} rows)")

def seed_pms(num_rooms=60):
    rooms = []
    today = datetime.now().date()
    for r in range(101, 101 + num_rooms):
        in_house = RNG.random() < 0.75
        status = "IN_HOUSE" if in_house else "CHECKED_OUT"
        checkin = datetime.combine(today - timedelta(days=RNG.randint(0, 3)), datetime.min.time())
        checkout = datetime.combine(today + timedelta(days=RNG.randint(0, 3)), datetime.min.time())
        rooms.append((
            f"PMS{r}", f"Huesped {r}", str(r),
            status, checkin.isoformat(timespec="seconds"), checkout.isoformat(timespec="seconds")
        ))
    with db() as conn:
        execmany(conn, """INSERT INTO PMSGuests(huesped_id,nombre,habitacion,status,checkin,checkout)
                          VALUES(?,?,?,?,?,?)""", rooms)
    print(f"✓ Seeded PMSGuests ({len(rooms)} rooms)")

def random_ticket_times(base: datetime, estado: str, area: str, prioridad: str):
    created_at = base
    due_dt = compute_due(created_at, area, prioridad)

    accepted_at = None
    started_at = None
    finished_at = None

    if estado in ("ASIGNADO", "ACEPTADO", "EN_CURSO", "PAUSADO", "DERIVADO", "RESUELTO"):
        accepted_at = created_at + timedelta(minutes=RNG.randint(3, 30))
    if estado in ("EN_CURSO", "PAUSADO", "DERIVADO", "RESUELTO"):
        started_at = (accepted_at or created_at) + timedelta(minutes=RNG.randint(5, 40))
    if estado == "RESUELTO":
        jitter = RNG.randint(-30, 120)
        finished_at = (started_at or created_at) + timedelta(minutes=max(10, RNG.randint(10, 90) + jitter))

    fmt = lambda dt: dt.isoformat(timespec="seconds") if dt else None
    return {
        "created_at": fmt(created_at),
        "due_at": fmt(due_dt),
        "accepted_at": fmt(accepted_at),
        "started_at": fmt(started_at),
        "finished_at": fmt(finished_at),
    }

def seed_tickets(total=150, days_back=10):
    with db() as conn:
        creators = conn.execute("""
            SELECT u.id, u.role, ou.org_id, ou.default_hotel_id AS hotel_id
            FROM Users u
            JOIN OrgUsers ou ON ou.user_id = u.id
            WHERE ou.role IN ('GERENTE','SUPERVISOR','RECEPCION')
        """).fetchall()

        techs = conn.execute("""
            SELECT u.id, u.area, ou.org_id, ou.default_hotel_id AS hotel_id
            FROM Users u
            JOIN OrgUsers ou ON ou.user_id = u.id
            WHERE ou.role = 'TECNICO'
        """).fetchall()

        rooms_in = conn.execute(
            "SELECT huesped_id, habitacion FROM PMSGuests WHERE status='IN_HOUSE'"
        ).fetchall()

    rows_t = []
    rows_h = []
    now = datetime.now()

    for _ in range(total):
        creator = RNG.choice(creators)
        org_id = creator["org_id"]
        hotel_id = creator["hotel_id"]

        area = RNG.choice(AREAS)
        prioridad = RNG.choices(PRIOS, weights=[2, 3, 3, 2], k=1)[0]
        estado = RNG.choices(ALL_STATES, weights=[2, 2, 2, 2, 1, 1, 3], k=1)[0]

        created_at = now - timedelta(days=RNG.uniform(0, days_back), minutes=RNG.randint(0, 600))
        timeline = random_ticket_times(created_at, estado, area, prioridad)

        canal = RNG.choices(
            ["recepcion", "huesped_whatsapp", "housekeeping_whatsapp", "mantenimiento_app", "roomservice_llamada"],
            weights=[4, 3, 2, 1, 1],
            k=1
        )[0]

        if RNG.random() < 0.7 and rooms_in:
            rr = RNG.choice(rooms_in)
            huesped_id = rr["huesped_id"]
            ubicacion = rr["habitacion"]
        else:
            huesped_id = None
            ubicacion = RNG.choice(["Lobby", "Piscina", "Gimnasio", "Spa", "Restaurante", "Pasillo 2F"])

        detalle = RNG.choice([
            "Aire acondicionado no funciona",
            "No hay toallas",
            "Fuga de agua en el lavatorio",
            "Luz parpadea",
            "Ruido de ventilación",
            "Televisor sin señal",
            "Solicitud de sábanas adicionales",
            "Pedido de room service: café y sándwich",
        ])

        # choose an assignee (prefer same org/hotel + area)
        assigned_to = None
        if estado in ("ASIGNADO", "ACEPTADO", "EN_CURSO", "PAUSADO", "DERIVADO", "RESUELTO"):
            candidates = [t for t in techs if t["org_id"] == org_id and t["hotel_id"] == hotel_id and t["area"] == area]
            if not candidates:
                candidates = [t for t in techs if t["org_id"] == org_id and t["area"] == area] or techs
            assigned_to = RNG.choice(candidates)["id"]

        rows_t.append((
            org_id, hotel_id, area, prioridad, estado, detalle, canal, ubicacion, huesped_id,
            timeline["created_at"], timeline["due_at"], assigned_to, creator["id"], None,
            RNG.choice([0, 1]),
            timeline["accepted_at"], timeline["started_at"], timeline["finished_at"]
        ))

    with db() as conn:
        execmany(conn, """
            INSERT INTO Tickets(
              org_id, hotel_id, area, prioridad, estado, detalle, canal_origen, ubicacion, huesped_id,
              created_at, due_at, assigned_to, created_by, confidence_score,
              qr_required, accepted_at, started_at, finished_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows_t)

        cur = conn.execute("""
            SELECT id, created_by, accepted_at, started_at, finished_at, created_at
            FROM Tickets
        """)
        for row in cur.fetchall():
            tid = row["id"]
            creator = row["created_by"]
            rows_h.append((tid, creator, "CREADO", None, row["created_at"]))
            if row["accepted_at"]:
                rows_h.append((tid, creator, "ACEPTADO", None, row["accepted_at"]))
            if row["started_at"]:
                rows_h.append((tid, creator, "INICIADO", None, row["started_at"]))
            if row["finished_at"]:
                rows_h.append((tid, creator, "RESUELTO", None, row["finished_at"]))

        execmany(conn, """
            INSERT INTO TicketHistory(ticket_id, actor_user_id, action, motivo, at)
            VALUES(?,?,?,?,?)
        """, rows_h)

    print(f"✓ Seeded {len(rows_t)} tickets and {len(rows_h)} history rows")

def seed_summaries():
    print("\nLogins:")
    print("  Superadmin  -> sudo@demo.local / demo123")
    with db() as conn:
        any_gerente = conn.execute("SELECT email FROM Users WHERE role='GERENTE' AND is_superadmin=0 LIMIT 3").fetchall()
        any_sup = conn.execute("SELECT email FROM Users WHERE role='SUPERVISOR' LIMIT 3").fetchall()
        any_rcpt = conn.execute("SELECT email FROM Users WHERE role='RECEPCION' LIMIT 3").fetchall()
        any_tech = conn.execute("SELECT email FROM Users WHERE role='TECNICO' LIMIT 3").fetchall()
    print("  Gerentes    -> " + ", ".join([r["email"] for r in any_gerente]))
    print("  Recepción   -> " + ", ".join([r["email"] for r in any_rcpt]))
    print("  Supervisores-> " + ", ".join([r["email"] for r in any_sup]))
    print("  Técnicos    -> " + ", ".join([r["email"] for r in any_tech]))

# ---------- main ----------
def main():
    p = argparse.ArgumentParser(description="Seed Hestia multi-tenant dev database (RBAC-ready)")
    p.add_argument("--reset", action="store_true", help="drop existing DB file first")
    p.add_argument("--tickets", type=int, default=150, help="how many tickets to create")
    p.add_argument("--days", type=int, default=10, help="spread ticket creation over last N days")
    p.add_argument("--orgs", type=int, default=2, help="number of orgs")
    p.add_argument("--hotels-per-org", type=int, default=2, help="hotels per org")
    p.add_argument("--superadmin-email", type=str, default="sudo@demo.local", help="superadmin email")
    args = p.parse_args()

    if args.reset or not os.path.exists(DB_PATH):
        reset_db()
    else:
        with db() as conn:
            conn.executescript(SCHEMA_SQL)

    # 0) RBAC primitives
    seed_rbac()

    # 1) Tenants
    orgs, hotels = seed_orgs_hotels(args.orgs, args.hotels_per_org)

    # 2) Users (superadmin + org membership)
    seed_users(args.superadmin_email)
    seed_org_memberships(orgs, hotels)

    # 3) SLA + PMS
    seed_sla()
    seed_pms(num_rooms=60)

    # 4) Tickets scoped by org/hotel
    seed_tickets(total=args.tickets, days_back=args.days)

    seed_summaries()
    print("\n✅ Done. You can now run:  python app.py")
    print("   Superadmin lands on /admin. Use /sudo to switch org/hotel context.")

if __name__ == "__main__":
    main()
