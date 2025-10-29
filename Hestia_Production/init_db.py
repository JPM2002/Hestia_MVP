# Hestia_Production/init_db.py
"""
Database initialization script for Render deployment.
This creates the database schema and initial data.
"""
import os
import sqlite3
from datetime import datetime, timezone

def init_database():
    """Initialize the database with schema and basic data."""
    
    # Use environment variable for database path, fallback to default
    db_path = os.getenv("DATABASE_PATH", "hestia_V2.db")
    
    # Create database connection
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()
    
    # Create tables
    cur.execute("""
    CREATE TABLE IF NOT EXISTS Users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      email TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL CHECK(role IN ('GERENTE','SUPERVISOR','RECEPCION','TECNICO')),
      area TEXT,
      telefono TEXT,
      activo INTEGER NOT NULL DEFAULT 1
    );
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS SLARules(
      area TEXT NOT NULL CHECK(area IN ('MANTENCION','HOUSEKEEPING','ROOMSERVICE')),
      prioridad TEXT NOT NULL CHECK(prioridad IN ('BAJA','MEDIA','ALTA','URGENTE')),
      max_minutes INTEGER NOT NULL,
      PRIMARY KEY(area, prioridad)
    );
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS Tickets(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      area TEXT NOT NULL CHECK(area IN ('MANTENCION','HOUSEKEEPING','ROOMSERVICE')),
      prioridad TEXT NOT NULL CHECK(prioridad IN ('BAJA','MEDIA','ALTA','URGENTE')),
      estado TEXT NOT NULL CHECK(estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO','RESUELTO','CANCELADO')),
      detalle TEXT NOT NULL,
      canal_origen TEXT,
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
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS TicketHistory(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ticket_id INTEGER NOT NULL,
      actor_user_id INTEGER,
      action TEXT NOT NULL,
      motivo TEXT,
      at TEXT NOT NULL,
      FOREIGN KEY(ticket_id) REFERENCES Tickets(id) ON DELETE CASCADE,
      FOREIGN KEY(actor_user_id) REFERENCES Users(id)
    );
    """)
    
    cur.execute("""
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
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS PMSGuests(
      huesped_id TEXT PRIMARY KEY,
      nombre TEXT,
      habitacion TEXT,
      checkin_at TEXT,
      checkout_at TEXT,
      status TEXT
    );
    """)
    
    # Insert SLA rules
    sla_rules = [
        ('MANTENCION', 'BAJA', 24*60),
        ('MANTENCION', 'MEDIA', 8*60),
        ('MANTENCION', 'ALTA', 4*60),
        ('MANTENCION', 'URGENTE', 90),
        ('HOUSEKEEPING', 'BAJA', 6*60),
        ('HOUSEKEEPING', 'MEDIA', 3*60),
        ('HOUSEKEEPING', 'ALTA', 90),
        ('HOUSEKEEPING', 'URGENTE', 45),
        ('ROOMSERVICE', 'BAJA', 90),
        ('ROOMSERVICE', 'MEDIA', 60),
        ('ROOMSERVICE', 'ALTA', 30),
        ('ROOMSERVICE', 'URGENTE', 20),
    ]
    
    cur.executemany("""
    INSERT OR IGNORE INTO SLARules(area, prioridad, max_minutes)
    VALUES (?, ?, ?)
    """, sla_rules)
    
    # Insert default admin user
    import hashlib
    admin_password = hashlib.sha256("admin123".encode("utf-8")).hexdigest()
    
    cur.execute("""
    INSERT OR IGNORE INTO Users(username, email, password_hash, role, activo)
    VALUES (?, ?, ?, ?, ?)
    """, ("admin", "admin@hestia.com", admin_password, "GERENTE", 1))
    
    # Insert demo users
    demo_password = hashlib.sha256("demo123".encode("utf-8")).hexdigest()
    
    demo_users = [
        ("supervisor1", "supervisor1@hestia.com", demo_password, "SUPERVISOR", "MANTENCION"),
        ("tecnico1", "tecnico1@hestia.com", demo_password, "TECNICO", "MANTENCION"),
        ("recepcion1", "recepcion1@hestia.com", demo_password, "RECEPCION", None),
    ]
    
    cur.executemany("""
    INSERT OR IGNORE INTO Users(username, email, password_hash, role, area, activo)
    VALUES (?, ?, ?, ?, ?, ?)
    """, [(user[0], user[1], user[2], user[3], user[4], 1) for user in demo_users])
    
    # Insert some sample tickets
    now = datetime.now(timezone.utc).isoformat()
    
    sample_tickets = [
        ("MANTENCION", "ALTA", "PENDIENTE", "Fuga de agua en baño", "recepcion", "1203", None, now, None, None, None, None, None, None, 1, 0.95, 0),
        ("HOUSEKEEPING", "MEDIA", "ASIGNADO", "Toallas adicionales", "recepcion", "1205", "G1205", now, None, None, None, None, None, 2, 1, 0.85, 0),
        ("ROOMSERVICE", "URGENTE", "EN_CURSO", "Pedido de comida urgente", "recepcion", "1207", "G1207", now, None, None, now, None, None, 3, 1, 0.90, 0),
    ]
    
    cur.executemany("""
    INSERT OR IGNORE INTO Tickets(
        area, prioridad, estado, detalle, canal_origen, ubicacion, huesped_id,
        created_at, due_at, accepted_at, started_at, paused_at, finished_at,
        assigned_to, created_by, confidence_score, qr_required
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, sample_tickets)
    
    conn.commit()
    conn.close()
    
    print(f"Database initialized successfully: {db_path}")

if __name__ == "__main__":
    init_database()
