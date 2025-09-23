import sqlite3 as sql
from datetime import datetime, timedelta
import random, os, csv, hashlib

DB = "hestia.db"
random.seed(42)

# ---------- helpers ----------
def hp(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()
def now(): return datetime.now()
def iso(dt): return dt.isoformat(timespec="seconds")

AREAS = ["MANTENCION","HOUSEKEEPING","ROOMSERVICE"]
PRIOS = ["BAJA","MEDIA","ALTA","URGENTE"]
ESTADOS_OPEN = ["PENDIENTE","ASIGNADO","ACEPTADO","EN_CURSO","PAUSADO","DERIVADO"]
ESTADOS_ALL  = ESTADOS_OPEN + ["RESUELTO","CANCELADO"]
CANALES = ["recepcion","huesped_whatsapp","housekeeping_whatsapp","mantenimiento_app"]

N_USERS_GERENTE = 2
N_USERS_SUP = 4
N_USERS_TEC = 19
N_TICKETS_MIN, N_TICKETS_MAX = 300, 600

# SLA minutes
SLA = {
  ("MANTENCION","BAJA"):  24*60,
  ("MANTENCION","MEDIA"):  8*60,
  ("MANTENCION","ALTA"):   4*60,
  ("MANTENCION","URGENTE"):90,
  ("HOUSEKEEPING","BAJA"):  6*60,
  ("HOUSEKEEPING","MEDIA"): 3*60,
  ("HOUSEKEEPING","ALTA"):  90,
  ("HOUSEKEEPING","URGENTE"):45,
  ("ROOMSERVICE","BAJA"):  90,
  ("ROOMSERVICE","MEDIA"): 60,
  ("ROOMSERVICE","ALTA"):  30,
  ("ROOMSERVICE","URGENTE"):20,
}

def compute_due(created_at, area, prioridad):
    mins = SLA.get((area, prioridad))
    return created_at + timedelta(minutes=mins) if mins else None

# ---------- schema ----------
SCHEMA = """
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS TicketHistory;
DROP TABLE IF EXISTS Tickets;
DROP TABLE IF EXISTS PMSGuests;
DROP TABLE IF EXISTS SLARules;
DROP TABLE IF EXISTS Users;

CREATE TABLE Users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL,           -- GERENTE|SUPERVISOR|TECNICO
  area TEXT,                    -- NULL for GERENTE; set for SUPERVISOR/TECNICO
  telefono TEXT,
  activo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE SLARules(
  area TEXT NOT NULL,
  prioridad TEXT NOT NULL,
  max_minutes INTEGER NOT NULL,
  PRIMARY KEY(area, prioridad)
);

CREATE TABLE Tickets(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  area TEXT NOT NULL,
  prioridad TEXT NOT NULL,
  estado TEXT NOT NULL,
  detalle TEXT NOT NULL,
  canal_origen TEXT NOT NULL,
  ubicacion TEXT NOT NULL,
  huesped_id TEXT,
  created_at TEXT NOT NULL,
  due_at TEXT,
  accepted_at TEXT,
  started_at TEXT,
  paused_at TEXT,
  finished_at TEXT,
  assigned_to INTEGER,
  created_by INTEGER,
  confidence_score REAL,
  qr_required INTEGER DEFAULT 0,
  FOREIGN KEY(assigned_to) REFERENCES Users(id),
  FOREIGN KEY(created_by) REFERENCES Users(id)
);

CREATE TABLE TicketHistory(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id INTEGER NOT NULL,
  actor_user_id INTEGER NOT NULL,
  action TEXT NOT NULL,
  motivo TEXT,
  at TEXT NOT NULL,
  FOREIGN KEY(ticket_id) REFERENCES Tickets(id) ON DELETE CASCADE,
  FOREIGN KEY(actor_user_id) REFERENCES Users(id)
);

CREATE TABLE PMSGuests(
  huesped_id TEXT PRIMARY KEY,
  nombre TEXT NOT NULL,
  habitacion TEXT NOT NULL,
  status TEXT NOT NULL
);
"""

def db():
    conn = sql.connect(DB)
    conn.row_factory = sql.Row
    return conn

def execmany(conn, q, rows):
    conn.executemany(q, rows)

def write_csv(name, rows, header):
    os.makedirs("seed_csv", exist_ok=True)
    path = os.path.join("seed_csv", f"{name}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"CSV -> {path}")

# ---------- seed users ----------
def seed_users(conn):
    rows = []

    # GERENTES (no area)
    for i in range(1, N_USERS_GERENTE+1):
        u = f"gerente{i}"
        rows.append((u, f"{u}@hotel.test", hp("demo123"), "GERENTE", None,
                     f"+56 9 7{random.randint(1000000,9999999)}", 1))

    # SUPERVISORES (each tied to an area, round-robin)
    for i in range(1, N_USERS_SUP+1):
        u = f"supervisor{i}"
        area = AREAS[(i-1) % len(AREAS)]
        rows.append((u, f"{u}@hotel.test", hp("demo123"), "SUPERVISOR", area,
                     f"+56 9 7{random.randint(1000000,9999999)}", 1))

    # TECNICOS (also tied to areas)
    for i in range(1, N_USERS_TEC+1):
        u = f"tecnico{i}"
        area = AREAS[(i-1) % len(AREAS)]
        rows.append((u, f"{u}@hotel.test", hp("demo123"), "TECNICO", area,
                     f"+56 9 7{random.randint(1000000,9999999)}", 1))

    execmany(conn, """
      INSERT INTO Users(username,email,password_hash,role,area,telefono,activo)
      VALUES(?,?,?,?,?,?,?)
    """, rows)

    # export
    cur = conn.execute("SELECT id,username,email,role,area,telefono,activo FROM Users ORDER BY id")
    urows = [tuple(r) for r in cur.fetchall()]
    write_csv("Users", urows, ["id","username","email","role","area","telefono","activo"])
    return [r[0] for r in conn.execute("SELECT id FROM Users").fetchall()]

# ---------- seed SLA ----------
def seed_sla(conn):
    rows = [(a,p,SLA[(a,p)]) for a in AREAS for p in PRIOS]
    execmany(conn, "INSERT INTO SLARules(area,prioridad,max_minutes) VALUES(?,?,?)", rows)
    write_csv("SLARules", rows, ["area","prioridad","max_minutes"])

# ---------- seed PMS guests ----------
def seed_pms(conn):
    rows=[]
    for room in range(101, 140):
        inhouse = random.random() < 0.65
        rows.append((
            f"G{room}",
            f"Huésped {room}",
            str(room),
            "IN_HOUSE" if inhouse else "CHECKED_OUT"
        ))
    execmany(conn, "INSERT INTO PMSGuests(huesped_id,nombre,habitacion,status) VALUES(?,?,?,?)", rows)
    write_csv("PMSGuests", rows, ["huesped_id","nombre","habitacion","status"])

# ---------- seed tickets + history ----------
# ---------- per-area phrases for 'detalle' ----------
AREA_LOREM = {
    "MANTENCION": [
        "Sin aire acondicionado",
        "Fuga de agua en baño",
        "TV no enciende",
        "Luz parpadea",
        "Cerradura no responde",
        "Ruido en aire",
        "Wifi inestable",
        "Baño con poca presión de agua",
        "Enchufe suelto",
        "Ventana no cierra bien",
    ],
    "HOUSEKEEPING": [
        "Toallas adicionales",
        "Reponer amenities",
        "Pedido de almohadas extra",
        "Cambio de sábanas",
        "Limpieza adicional",
        "Reposición de papel higiénico",
        "Kit dental solicitado",
        "Cuna para bebé",
        "Plancha solicitada",
        "Batas de baño adicionales",
    ],
    "ROOMSERVICE": [
        "Pedido de hamburguesa y papas",
        "Desayuno a la habitación",
        "Bebidas frías (2 aguas, 1 gaseosa)",
        "Cena tardía: pasta y ensalada",
        "Café y té para dos",
        "Postre: cheesecake y fruta",
        "Tabla de quesos con vino",
        "Sándwich club y jugo natural",
        "Sopa caliente y pan",
        "Pedido de hielo adicional",
    ],
}

DEFAULT_LOREM = ["Solicitud del huésped"]


def seed_tickets(conn, user_ids):
    sup_ids = [r[0] for r in conn.execute("SELECT id FROM Users WHERE role='SUPERVISOR'").fetchall()]
    tec_rows = conn.execute("SELECT id, area FROM Users WHERE role='TECNICO'").fetchall()
    tec_ids = [r["id"] for r in tec_rows]
    creador_ids = sup_ids or user_ids

    n = random.randint(N_TICKETS_MIN, N_TICKETS_MAX)
    base = now() - timedelta(days=60)

    cur = conn.cursor()
    for _ in range(n):
        area = random.choice(AREAS)
        prio = random.choices(PRIOS, weights=[0.25,0.35,0.25,0.15], k=1)[0]
        estado = random.choices(ESTADOS_ALL, weights=[0.15,0.12,0.12,0.18,0.08,0.10,0.22,0.03], k=1)[0]
        detalle = random.choice(AREA_LOREM.get(area, DEFAULT_LOREM))
        canal = random.choice(CANALES)
        room = str(random.randint(101, 139))
        huesped_id = f"G{room}" if random.random() < 0.50 else None
        created = base + timedelta(minutes=random.randint(0, 60*24*60))
        due = compute_due(created, area, prio)
        creador = random.choice(creador_ids)

        # assign a tech from same area if possible
        tech_pool = [r["id"] for r in tec_rows if r["area"] == area] or tec_ids
        assigned = None
        accepted_at = started_at = paused_at = finished_at = None

        history = [("CREADO", None, created)]
        if estado in ("ASIGNADO","ACEPTADO","EN_CURSO","PAUSADO","DERIVADO","RESUELTO"):
            assigned = random.choice(tech_pool) if tech_pool else None
            history.append(("ASIGNADO", None, created + timedelta(minutes=5)))

        if estado in ("ACEPTADO","EN_CURSO","PAUSADO","RESUELTO"):
            accepted_at = created + timedelta(minutes=random.randint(10,60))
            history.append(("ACEPTADO", None, accepted_at))

        if estado in ("EN_CURSO","PAUSADO","RESUELTO"):
            started_at = accepted_at + timedelta(minutes=random.randint(5,60)) if accepted_at else None
            if started_at: history.append(("INICIADO", None, started_at))

        if estado == "PAUSADO":
            paused_at = started_at + timedelta(minutes=random.randint(5,40)) if started_at else None
            if paused_at: history.append(("PAUSADO", "Falta repuesto", paused_at))

        if estado == "RESUELTO":
            finished_at = (started_at or accepted_at or created) + timedelta(minutes=random.randint(15, 6*60))
            history.append(("RESUELTO", None, finished_at))

        cur.execute("""
          INSERT INTO Tickets(area,prioridad,estado,detalle,canal_origen,ubicacion,huesped_id,
                              created_at,due_at,accepted_at,started_at,paused_at,finished_at,
                              assigned_to,created_by,confidence_score,qr_required)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (area, prio, estado, detalle, canal, room, huesped_id,
              iso(created), iso(due) if due else None,
              iso(accepted_at) if accepted_at else None,
              iso(started_at) if started_at else None,
              iso(paused_at) if paused_at else None,
              iso(finished_at) if finished_at else None,
              assigned, creador, round(random.uniform(0.65, 0.99), 2), int(random.random()<0.2)))
        tid = cur.lastrowid

        for action, motivo, at in history:
            cur.execute("""
              INSERT INTO TicketHistory(ticket_id, actor_user_id, action, motivo, at)
              VALUES (?,?,?,?,?)
            """, (tid, assigned or creador, action, motivo, iso(at)))
    conn.commit()

    # export CSVs
    tr = conn.execute("""
      SELECT id,area,prioridad,estado,detalle,canal_origen,ubicacion,huesped_id,
             created_at,due_at,accepted_at,started_at,paused_at,finished_at,
             assigned_to,created_by,confidence_score,qr_required
      FROM Tickets
      ORDER BY id
    """).fetchall()
    write_csv("Tickets", [tuple(r) for r in tr], [
        "id","area","prioridad","estado","detalle","canal_origen","ubicacion","huesped_id",
        "created_at","due_at","accepted_at","started_at","paused_at","finished_at",
        "assigned_to","created_by","confidence_score","qr_required"
    ])

    hr = conn.execute("""
      SELECT id,ticket_id,actor_user_id,action,motivo,at
      FROM TicketHistory ORDER BY ticket_id, id
    """).fetchall()
    write_csv("TicketHistory", [tuple(r) for r in hr],
              ["id","ticket_id","actor_user_id","action","motivo","at"])

# ---------- main ----------
if __name__ == "__main__":
    if os.path.exists(DB):
        os.remove(DB)
        print("Removed old hestia.db")

    with db() as conn:
        conn.executescript(SCHEMA)
        print("Schema created.")
        user_ids = seed_users(conn)
        seed_sla(conn)
        seed_pms(conn)
        seed_tickets(conn, user_ids)
        print("Seed complete.")
