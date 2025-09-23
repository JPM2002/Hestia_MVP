import os, csv, hashlib, sqlite3 as sql
from datetime import datetime

DB_NAME = "hestia.db"
DATA_DIR = os.path.join(os.path.dirname(__file__), "HestiaDataset")

def hp(p):  # hash password
    return hashlib.sha256(p.encode("utf-8")).hexdigest()

def run(sql_text, params=None):
    cur.execute(sql_text, params or ())

with sql.connect(DB_NAME) as con:
    con.execute("PRAGMA foreign_keys = ON;")
    cur = con.cursor()

    # -------------------- Tables --------------------
    run("""
    CREATE TABLE IF NOT EXISTS Users(
      id INTEGER PRIMARY KEY,
      username TEXT UNIQUE NOT NULL,
      email TEXT UNIQUE,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL CHECK(role IN ('GERENTE','SUPERVISOR','RECEPCION','MANTENCION','HOUSEKEEPING')),
      turno TEXT,
      telefono TEXT,
      activo INTEGER NOT NULL DEFAULT 1
    );
    """)

    run("""
    CREATE TABLE IF NOT EXISTS SLARules(
      area TEXT NOT NULL CHECK(area IN ('MANTENCION','HOUSEKEEPING','MANTENCION')),
      prioridad TEXT NOT NULL CHECK(prioridad IN ('BAJA','MEDIA','ALTA','URGENTE')),
      max_minutes INTEGER NOT NULL,
      PRIMARY KEY(area, prioridad)
    );
    """)

    run("""
    CREATE TABLE IF NOT EXISTS Tickets(
      id INTEGER PRIMARY KEY,
      area TEXT NOT NULL CHECK(area IN ('MANTENCION','HOUSEKEEPING','MANTENCION')),
      prioridad TEXT NOT NULL CHECK(prioridad IN ('BAJA','MEDIA','ALTA','URGENTE')),
      estado TEXT NOT NULL CHECK(estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO','RESUELTO','CANCELADO')),
      detalle TEXT,
      canal_origen TEXT CHECK(canal_origen IN ('recepcion','huesped_whatsapp','housekeeping_whatsapp','mantenimiento_app')),
      ubicacion TEXT,
      huesped_id TEXT,
      created_at TEXT NOT NULL,
      accepted_at TEXT,
      started_at TEXT,
      finished_at TEXT,
      due_at TEXT,
      assigned_to INTEGER,
      created_by INTEGER,
      confidence_score REAL,
      qr_required INTEGER DEFAULT 0,
      FOREIGN KEY(assigned_to) REFERENCES Users(id) ON UPDATE CASCADE,
      FOREIGN KEY(created_by)  REFERENCES Users(id) ON UPDATE CASCADE
    );
    """)

    run("""
    CREATE TABLE IF NOT EXISTS TicketHistory(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ticket_id INTEGER NOT NULL,
      actor_user_id INTEGER,
      action TEXT NOT NULL, -- e.g., CREADO, ACEPTADO, EN_CURSO, PAUSADO, DERIVADO, RESUELTO
      motivo TEXT,
      at TEXT NOT NULL,
      FOREIGN KEY(ticket_id) REFERENCES Tickets(id) ON DELETE CASCADE,
      FOREIGN KEY(actor_user_id) REFERENCES Users(id)
    );
    """)

    run("""
    CREATE TABLE IF NOT EXISTS Attachments(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ticket_id INTEGER NOT NULL,
      url TEXT NOT NULL,
      kind TEXT CHECK(kind IN ('photo','audio')),
      at TEXT NOT NULL,
      uploaded_by INTEGER,
      FOREIGN KEY(ticket_id) REFERENCES Tickets(id) ON DELETE CASCADE,
      FOREIGN KEY(uploaded_by) REFERENCES Users(id)
    );
    """)

    run("""
    CREATE TABLE IF NOT EXISTS PMSGuests(
      huesped_id TEXT PRIMARY KEY,
      nombre TEXT,
      habitacion TEXT,
      checkin_at TEXT,
      checkout_at TEXT,
      status TEXT
    );
    """)

    con.commit()

    # -------------------- Seed from CSV --------------------
    def load_csv(name):
        with open(os.path.join(DATA_DIR, name), newline='', encoding='utf-8') as f:
            return list(csv.DictReader(f))

    # Users (hash passwords)
    for r in load_csv("users.csv"):
        run("""INSERT OR IGNORE INTO Users(id,username,email,password_hash,role,turno,telefono,activo)
               VALUES(?,?,?,?,?,?,?,?);""",
            (int(r["id"]), r["username"].strip(), r["email"].strip(),
             hp(r["password"].strip()), r["role"].strip(),
             (r["turno"] or None), (r["telefono"] or None), int(r["activo"])))
    con.commit()

    # SLA
    for r in load_csv("sla_rules.csv"):
        run("""INSERT OR IGNORE INTO SLARules(area,prioridad,max_minutes)
               VALUES(?,?,?);""",
            (r["area"].strip(), r["prioridad"].strip(), int(r["max_minutes"])))
    con.commit()

    # Tickets
    def nz(v): return v if v else None
    for r in load_csv("tickets.csv"):
        run("""INSERT OR IGNORE INTO Tickets(
            id,area,prioridad,estado,detalle,canal_origen,ubicacion,huesped_id,
            created_at,accepted_at,started_at,finished_at,due_at,
            assigned_to,created_by,confidence_score,qr_required
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);""",
        (int(r["id"]), r["area"], r["prioridad"], r["estado"], r["detalle"],
         r["canal_origen"], r["ubicacion"], nz(r["huesped_id"]),
         r["created_at"], nz(r["accepted_at"]), nz(r["started_at"]),
         nz(r["finished_at"]), nz(r["due_at"]),
         int(r["assigned_to"]) if r["assigned_to"] else None,
         int(r["created_by"]) if r["created_by"] else None,
         float(r["confidence_score"]) if r["confidence_score"] else None,
         int(r["qr_required"]) if r["qr_required"] else 0))
    con.commit()

    # Ticket history
    for r in load_csv("ticket_history.csv"):
        run("""INSERT OR IGNORE INTO TicketHistory(id,ticket_id,actor_user_id,action,motivo,at)
               VALUES(?,?,?,?,?,?);""",
            (int(r["id"]), int(r["ticket_id"]), int(r["actor_user_id"]) if r["actor_user_id"] else None,
             r["action"], nz(r["motivo"]), r["at"]))
    con.commit()

    # Attachments
    for r in load_csv("attachments.csv"):
        run("""INSERT OR IGNORE INTO Attachments(id,ticket_id,url,kind,at,uploaded_by)
               VALUES(?,?,?,?,?,?);""",
            (int(r["id"]), int(r["ticket_id"]), r["url"], r["kind"], r["at"],
             int(r["uploaded_by"]) if r["uploaded_by"] else None))
    con.commit()

    # PMS cache
    for r in load_csv("pms_guests.csv"):
        run("""INSERT OR IGNORE INTO PMSGuests(huesped_id,nombre,habitacion,checkin_at,checkout_at,status)
               VALUES(?,?,?,?,?,?);""",
            (r["huesped_id"], r["nombre"], r["habitacion"], r["checkin_at"], r["checkout_at"], r["status"]))
    con.commit()

print(f"✅ DB created and seeded: {DB_NAME}")
