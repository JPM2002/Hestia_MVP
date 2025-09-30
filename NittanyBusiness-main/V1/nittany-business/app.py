from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, get_flashed_messages, session, jsonify
)
import sqlite3 as sql
from datetime import datetime, timedelta
import hashlib
from functools import wraps
import os

# 👇 ADD THESE TWO LINES
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'change-me-in-env')

# --- Supabase/Postgres setup (robust, lazy-init, with clear logs) ---
DATABASE_URL = os.getenv('DATABASE_URL')  # e.g. postgresql://...:6543/postgres?sslmode=require
DATABASE = os.getenv('DATABASE_PATH', 'hestia_V2.db')  # local fallback for dev
USE_PG = bool(DATABASE_URL)

# Try to import psycopg2; don't crash if missing (local SQLite dev may not need it)
pg = None
pg_pool = None
pg_extras = None
if USE_PG:
    try:
        import psycopg2 as pg
        import psycopg2.pool as pg_pool
        import psycopg2.extras as pg_extras
    except Exception as e:
        print(f"[BOOT] psycopg2 import failed: {e}", flush=True)

PG_POOL = None  # created lazily on first use

def hp(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def _init_pg_pool():
    """Create the global pool once. Raise with the real reason if it fails."""
    global PG_POOL
    if not USE_PG:
        return None
    if PG_POOL is not None:
        return PG_POOL
    if pg is None or pg_pool is None:
        raise RuntimeError("DATABASE_URL is set but psycopg2 isn't available (check requirements.txt).")
    try:
        PG_POOL = pg_pool.SimpleConnectionPool(
            minconn=1,
            maxconn=int(os.getenv('PG_POOL_MAX', '5')),
            dsn=DATABASE_URL,
        )
        print("[BOOT] Postgres pool initialized.", flush=True)
        return PG_POOL
    except Exception as e:
        print(f"[BOOT] Postgres pool init failed: {e}", flush=True)
        raise

def db():
    """
    Get a DB connection:
      - Postgres (Supabase) when DATABASE_URL is set
      - SQLite local file otherwise
    """
    if USE_PG:
        pool = _init_pg_pool()  # will raise with true cause if it fails
        return pool.getconn()
    # SQLite path
    conn = sql.connect(DATABASE, check_same_thread=False)
    conn.row_factory = sql.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def _execute(conn, query, params=()):
    """Run a query on either backend. Converts '?' -> '%s' for Postgres."""
    if USE_PG:
        cur = conn.cursor(cursor_factory=pg_extras.RealDictCursor)
        cur.execute(query.replace('?', '%s'), params)
        return cur
    else:
        return conn.execute(query, params)

def fetchone(query, params=()):
    conn = db()
    try:
        if USE_PG:
            cur = _execute(conn, query, params)
            row = cur.fetchone()
            cur.close()
            conn.commit()
            return row
        else:
            with conn:
                cur = _execute(conn, query, params)
                return cur.fetchone()
    finally:
        if USE_PG:
            try: PG_POOL.putconn(conn)
            except Exception: pass
        else:
            try: conn.close()
            except Exception: pass

def fetchall(query, params=()):
    conn = db()
    try:
        if USE_PG:
            cur = _execute(conn, query, params)
            rows = cur.fetchall()
            cur.close()
            conn.commit()
            return rows
        else:
            with conn:
                cur = _execute(conn, query, params)
                return cur.fetchall()
    finally:
        if USE_PG:
            try: PG_POOL.putconn(conn)
            except Exception: pass
        else:
            try: conn.close()
            except Exception: pass

def execute(query, params=()):
    conn = db()
    try:
        if USE_PG:
            cur = _execute(conn, query, params)
            cur.close()
            conn.commit()
        else:
            with conn:
                _ = _execute(conn, query, params)
                conn.commit()
    finally:
        if USE_PG:
            try: PG_POOL.putconn(conn)
            except Exception: pass
        else:
            try: conn.close()
            except Exception: pass

def insert_and_get_id(query, params=()):
    """
    Run an INSERT and return the new primary key id on both backends.
    For Postgres, appends 'RETURNING id' if not already present.
    For SQLite, uses cursor.lastrowid.
    """
    conn = db()
    try:
        if USE_PG:
            sql_text = query
            if 'RETURNING' not in sql_text.upper():
                sql_text = sql_text.rstrip().rstrip(';') + ' RETURNING id'
            cur = _execute(conn, sql_text, params)
            row = cur.fetchone()
            cur.close()
            conn.commit()
            # RealDictCursor returns dict-like rows
            return row['id'] if isinstance(row, dict) else row[0]
        else:
            with conn:
                cur = _execute(conn, query, params)
                conn.commit()
                return cur.lastrowid
    finally:
        if USE_PG:
            try: PG_POOL.putconn(conn)
            except Exception: pass
        else:
            try: conn.close()
            except Exception: pass


def is_critical(now: datetime, due_at) -> bool:
    """
    Accepts either ISO string (SQLite) or datetime (Postgres) for due_at.
    crítico si faltan <=10 min o ya vencido
    """
    if not due_at:
        return False
    try:
        if isinstance(due_at, datetime):
            due = due_at
        else:
            due = datetime.fromisoformat(str(due_at))
    except Exception:
        return False
    return now >= (due - timedelta(minutes=10))

def sla_minutes(area: str, prioridad: str) -> int | None:
    r = fetchone("SELECT max_minutes FROM SLARules WHERE area=? AND prioridad=?", (area, prioridad))
    try:
        return int(r["max_minutes"]) if r and r.get("max_minutes") is not None else None
    except Exception:
        return None

def compute_due(created_at: datetime, area: str, prioridad: str) -> datetime | None:
    mins = sla_minutes(area, prioridad)
    return created_at + timedelta(minutes=mins) if mins else None





# ---- tenant helpers
def current_scope():
    return session.get('org_id'), session.get('hotel_id')

def is_superadmin():
    return bool(session.get('user', {}).get('is_superadmin'))

# ---------------------------- RBAC helpers ----------------------------
def role_effective_perms(role_code: str) -> set[str]:
    """
    Resolve role -> permissions following inheritance (Roles.inherits_code).
    If RBAC tables don't exist yet, return a permissive set for SUPERADMIN only.
    """
    if not role_code:
        return set()
    try:
        perms = set()
        seen = set()
        rc = role_code
        while rc and rc not in seen:
            seen.add(rc)
            for r in fetchall("SELECT perm_code FROM RolePermissions WHERE role_code=? AND allow=1", (rc,)):
                perms.add(r['perm_code'])
            parent = fetchone("SELECT inherits_code FROM Roles WHERE code=?", (rc,))
            rc = parent['inherits_code'] if parent else None
        return perms
    except Exception:
        # Fallback: allow everything if superadmin role, minimal otherwise (during migration)
        return {"*"} if role_code == "SUPERADMIN" else set()

def current_org_role() -> str | None:
    """Return the OrgUsers.role for this user in current org, or SUPERADMIN."""
    u = session.get('user'); org_id = session.get('org_id')
    if not u:
        return None
    if u.get('is_superadmin'):
        return "SUPERADMIN"
    if not org_id:
        return None
    r = fetchone("SELECT role FROM OrgUsers WHERE org_id=? AND user_id=?", (org_id, u['id']))
    return r['role'] if r else None

def user_area_codes(org_id: int, user_id: int) -> set[str]:
    """
    Areas asignadas al usuario en la org (multi-área).
    Fallback a OrgUsers.default_area si OrgUserAreas no existe.
    """
    try:
        rows = fetchall("SELECT area_code FROM OrgUserAreas WHERE org_id=? AND user_id=?", (org_id, user_id))
        if rows:
            return {r['area_code'] for r in rows}
    except Exception:
        pass
    # fallback
    r = fetchone("SELECT default_area FROM OrgUsers WHERE org_id=? AND user_id=?", (org_id, user_id))
    return {r['default_area']} if r and r['default_area'] else set()

def has_perm(code: str) -> bool:
    role = current_org_role()
    if not role:
        return False
    eff = role_effective_perms(role)
    return ("*" in eff) or (code in eff)

def require_perm(code):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not session.get('user'):
                return redirect(url_for('login'))
            if not has_perm(code):
                flash('No tienes permisos para esta acción.', 'error')
                return redirect(url_for('dashboard'))
            return fn(*a, **kw)
        return wrapper
    return deco

def ensure_ticket_area_scope(ticket_row) -> bool:
    """
    Supervisor sólo puede operar si el ticket es de su(s) área(s).
    Gerente y superadmin siempre pueden.
    Técnico no pasa por aquí (tiene sus límites por assigned_to).
    """
    role = current_org_role()
    if role in ("SUPERADMIN", "GERENTE"):
        return True
    if role == "SUPERVISOR":
        org_id, _ = current_scope()
        my_areas = user_area_codes(org_id, session['user']['id'])
        return ticket_row['area'] in my_areas
    # recepcion / tecnico no deberían llegar a acciones restringidas por área aquí
    return False

# ---------------------------- auth & base ----------------------------
@app.route('/')
def index():
    if session.get('user'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    message, success = None, False
    flashed = get_flashed_messages()
    if flashed:
        try:
            message, success = flashed[0]
        except Exception:
            message = flashed[0]

    if request.method == 'POST':
        ident = request.form.get('email')  # email o username
        password = request.form.get('password') or ''

        row = fetchone(
            """
            SELECT id, username, email, password_hash, role, area, telefono, activo, is_superadmin
            FROM Users
            WHERE (email = ? OR username = ?)
            """,
            (ident, ident)
        )

        if row and hp(password) == row["password_hash"] and int(row["activo"]) == 1:
            session['user'] = {
                'id': row['id'],
                'name': row['username'],
                'email': row['email'],
                'role': row['role'],        # base role (legacy)
                'area': row['area'],        # legacy single-area (we prefer OrgUserAreas)
                'is_superadmin': int(row['is_superadmin']) == 1
            }

            # Scope: from first membership or first org/hotel if superadmin
            ou = fetchone("""
                SELECT org_id,
                       COALESCE(default_hotel_id,(SELECT id FROM Hotels WHERE org_id=OrgUsers.org_id LIMIT 1)) AS hotel_id
                FROM OrgUsers WHERE user_id=? LIMIT 1
            """, (row['id'],))
            if ou:
                session['org_id'] = ou['org_id']
                session['hotel_id'] = ou['hotel_id']
            elif session['user']['is_superadmin']:
                org = fetchone("SELECT id FROM Orgs ORDER BY id LIMIT 1")
                if org:
                    session['org_id'] = org['id']
                    h = fetchone("SELECT id FROM Hotels WHERE org_id=? ORDER BY id LIMIT 1", (org['id'],))
                    session['hotel_id'] = h['id'] if h else None

            if session['user']['is_superadmin']:
                return redirect(url_for('admin_super'))
            return redirect(url_for('dashboard'))
        else:
            message = 'Credenciales inválidas o usuario inactivo.'

    return render_template('login.html', message=message, success=success)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

#CHeck status of the app
@app.get('/healthz')
def healthz():
    return 'ok', 200


# ---------------------------- role data helpers ----------------------------
OPEN_STATES = ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')

def get_global_kpis():
    """KPIs para GERENTE (visión por ORG)."""
    now = datetime.now()
    org_id, _hotel_id = current_scope()
    if not org_id:
        return {"critical": 0, "active": 0, "resolved_today": 0, "by_area": {}}, {"resolved_last7": []}

    active = fetchall(
        f"SELECT id, due_at FROM Tickets WHERE org_id=? AND estado IN ({','.join(['?']*len(OPEN_STATES))})",
        (org_id, *OPEN_STATES)
    )
    total_active = len(active)
    critical = sum(1 for r in active if is_critical(now, r['due_at']))

    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    resolved_today = fetchone(
        "SELECT COUNT(1) c FROM Tickets WHERE org_id=? AND estado='RESUELTO' AND finished_at >= ?",
        (org_id, start_of_day)
    )['c']

    by_area = fetchall("""
        SELECT area, COUNT(1) c
        FROM Tickets
        WHERE org_id=? AND estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO','RESUELTO')
        GROUP BY area
    """, (org_id,))
    kpis = {
        "critical": critical,
        "active": total_active,
        "resolved_today": resolved_today,
        "by_area": {r["area"]: r["c"] for r in by_area}
    }

    # Serie de resueltos últimos 7 días (DB-agnóstico: calculado en Python)
    cutoff = (now - timedelta(days=7)).isoformat()
    rows = fetchall("""
        SELECT finished_at
        FROM Tickets
        WHERE org_id=? AND estado='RESUELTO' AND finished_at >= ?
    """, (org_id, cutoff))

    from collections import Counter
    cnt = Counter()
    for r in rows or []:
        fa = r["finished_at"]
        if fa:
            cnt[fa[:10]] += 1
    charts = {
        "resolved_last7": [{"date": d, "count": cnt[d]} for d in sorted(cnt.keys())]
    }   
    return kpis, charts



def get_area_data(area: str | None):
    """KPIs + tickets abiertos para SUPERVISOR (scoped by ORG; filter by area si viene)."""
    org_id, hotel_id = current_scope()
    if not org_id:
        return {"area": area, "critical": 0, "active": 0, "resolved_24h": 0}, []

    params = [org_id]
    where = ["org_id=?"]
    # If you want to limit by hotel, uncomment:
    # if hotel_id: where.append("hotel_id=?"); params.append(hotel_id)
    if area:
        where.append("area=?"); params.append(area)

    now = datetime.now()
    active = fetchall(
        f"""
        SELECT id, due_at
        FROM Tickets
        WHERE {' AND '.join(where)}
          AND estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')
        """, params
    )
    total_active = len(active)
    critical = sum(1 for r in active if is_critical(now, r['due_at']))

    cut24 = (datetime.now() - timedelta(days=1)).isoformat()
    resolved_24 = fetchone(
        f"""
        SELECT COUNT(1) c
        FROM Tickets
        WHERE {' AND '.join(where)} AND estado='RESUELTO'
        AND finished_at >= ?
        """, params + [cut24]
    )['c']


    kpis = {
        "area": area,
        "critical": critical,
        "active": total_active,
        "resolved_24h": resolved_24
    }

    rows = fetchall(
        f"""
        SELECT id, area, prioridad, estado, detalle, ubicacion, created_at, due_at, assigned_to, canal_origen
        FROM Tickets
        WHERE {' AND '.join(where)}
          AND estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')
        ORDER BY created_at DESC
        """, params
    )
    tickets = [{
        "id": r["id"], "area": r["area"], "prioridad": r["prioridad"], "estado": r["estado"],
        "detalle": r["detalle"], "ubicacion": r["ubicacion"], "created_at": r["created_at"],
        "due_at": r["due_at"], "is_critical": is_critical(datetime.now(), r["due_at"]),
        "assigned_to": r["assigned_to"],
        "canal": r["canal_origen"],
    } for r in rows]
    return kpis, tickets

def get_assigned_tickets(user_id: int):
    """Tickets asignados a un técnico/operador (scoped by ORG)."""
    now = datetime.now()
    org_id, _hotel_id = current_scope()
    if not org_id:
        return []
    rows = fetchall("""
        SELECT id, area, prioridad, estado, detalle, ubicacion, created_at, due_at
        FROM Tickets
        WHERE org_id=? AND assigned_to = ?
          AND estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')
        ORDER BY created_at DESC
    """, (org_id, user_id))
    return [{
        "id": r["id"], "area": r["area"], "prioridad": r["prioridad"], "estado": r["estado"],
        "detalle": r["detalle"], "ubicacion": r["ubicacion"], "created_at": r["created_at"],
        "due_at": r["due_at"], "is_critical": is_critical(now, r["due_at"])
    } for r in rows]

# ---------------------------- dashboards ----------------------------
@app.route('/dashboard')
def dashboard():
    user = session.get('user')
    if not user:
        return redirect(url_for('login'))

    if user.get('is_superadmin'):
        return redirect(url_for('admin_super'))

    role = current_org_role() or user.get('role')
    if role == 'GERENTE':
        kpis, charts = get_global_kpis()
        return render_template('dashboard_gerente.html', user=user, kpis=kpis, charts=charts)

    if role == 'SUPERVISOR':
        kpis, tickets = get_area_data(None)  # UI puede filtrar por área
        return render_template('dashboard_supervisor.html', user=user, kpis=kpis, tickets=tickets)

    if role == 'RECEPCION':
        return redirect(url_for('recepcion_inbox'))

    # TECNICO / otros
    tickets = get_assigned_tickets(user['id'])
    return render_template('dashboard_tecnico.html', user=user, tickets=tickets)

# ---------------------------- tickets list & filters ----------------------------
@app.route('/tickets')
def tickets():
    if 'user' not in session:
        return redirect(url_for('login'))

    org_id, hotel_id = current_scope()
    if not org_id:
        flash('Sin contexto de organización. Pide acceso al admin.', 'error')
        return redirect(url_for('dashboard'))

    q = request.args.get('q', '').strip()
    area = request.args.get('area') or None
    prioridad = request.args.get('prioridad') or None
    estado = request.args.get('estado') or None
    period = request.args.get('period', 'today')  # today|yesterday|7d|30d|all

    # RBAC scoping
    where, params = ["org_id=?"], [org_id]
    role = current_org_role()

    # If you want hotel-level filtering by default, uncomment:
    # if hotel_id: where.append("hotel_id=?"); params.append(hotel_id)

    if not has_perm('ticket.view.all'):
        # area-scoped or assigned-only
        if has_perm('ticket.view.area'):
            my_areas = user_area_codes(org_id, session['user']['id'])
            if my_areas:
                where.append("area IN (%s)" % ",".join(["?"]*len(my_areas)))
                params += list(my_areas)
        else:
            # only my assigned
            where.append("assigned_to=?")
            params.append(session['user']['id'])

    if q:
        where.append("(detalle LIKE ? OR ubicacion LIKE ? OR huesped_id LIKE ?)")
        like = f"%{q}%"; params += [like, like, like]
    if area:
        where.append("area=?"); params.append(area)
    if prioridad:
        where.append("prioridad=?"); params.append(prioridad)
    if estado:
        where.append("estado=?"); params.append(estado)

    now = datetime.now()
    sod = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == 'today':
        where.append("created_at >= ?"); params.append(sod.isoformat())
    elif period == 'yesterday':
        y0 = (sod - timedelta(days=1)).isoformat()
        where.append("created_at >= ? AND created_at < ?"); params += [y0, sod.isoformat()]
    elif period == '7d':
        where.append("created_at >= ?"); params.append((sod - timedelta(days=7)).isoformat())
    elif period == '30d':
        where.append("created_at >= ?"); params.append((sod - timedelta(days=30)).isoformat())

    rows = fetchall(
        f"""SELECT id, area, prioridad, estado, detalle, ubicacion, created_at,
                   due_at, assigned_to, canal_origen
            FROM Tickets
            WHERE {' AND '.join(where)}
            ORDER BY created_at DESC
        """, params
    )

    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "area": r["area"],
            "prioridad": r["prioridad"],
            "estado": r["estado"],
            "detalle": r["detalle"],
            "ubicacion": r["ubicacion"],
            "created_at": r["created_at"],
            "due_at": r["due_at"],
            "is_critical": is_critical(now, r["due_at"]),
            "assigned_to": r["assigned_to"],
            "canal": r["canal_origen"],
        })

    return render_template('tickets.html',
                           user=session['user'],
                           tickets=items,
                           filters={"q": q, "area": area, "prioridad": prioridad, "estado": estado, "period": period})

# ---------------------------- Recepción inbox (triage) ----------------------------
@app.route('/recepcion/inbox')
@require_perm('ticket.view.area')
def recepcion_inbox():
    org_id, _ = current_scope()
    if not org_id:
        flash('Sin contexto de organización.', 'error')
        return redirect(url_for('dashboard'))

    # Inbox: pendientes (típicamente WA huésped o recepcion)
    rows = fetchall("""
        SELECT id, area, prioridad, estado, detalle, ubicacion, canal_origen, created_at
        FROM Tickets
        WHERE org_id=? AND estado='PENDIENTE'
        ORDER BY created_at DESC
    """, (org_id,))
    return render_template('tickets.html',
                           user=session['user'],
                           tickets=[{
                               "id": r["id"], "area": r["area"], "prioridad": r["prioridad"], "estado": r["estado"],
                               "detalle": r["detalle"], "ubicacion": r["ubicacion"],
                               "created_at": r["created_at"], "due_at": None, "is_critical": False,
                               "assigned_to": None, "canal": r["canal_origen"]
                           } for r in rows],
                           filters={"q":"", "area":"", "prioridad":"", "estado":"PENDIENTE", "period":"today"})

# ---------------------------- create & confirm ticket ----------------------------
@app.route('/tickets/create', methods=['GET', 'POST'])
@require_perm('ticket.create')
def ticket_create():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        org_id, hotel_id = current_scope()
        if not org_id or not hotel_id:
            flash('Falta contexto de organización/hotel.', 'error')
            return redirect(url_for('tickets'))

        area = request.form.get('area')
        prioridad = request.form.get('prioridad')
        detalle = request.form.get('detalle')
        ubicacion = request.form.get('ubicacion')
        canal = request.form.get('canal_origen') or 'recepcion'
        huesped_id = request.form.get('huesped_id') or None
        qr_required = int(request.form.get('qr_required', 0))

        created_at = datetime.now()
        due_dt = compute_due(created_at, area, prioridad)
        due_at = due_dt.isoformat() if due_dt else None

        try:
            new_id = insert_and_get_id("""
                INSERT INTO Tickets(org_id, hotel_id, area, prioridad, estado, detalle, canal_origen, ubicacion,
                                    huesped_id, created_at, due_at, assigned_to, created_by,
                                    confidence_score, qr_required)
                VALUES (?, ?, ?, ?, 'PENDIENTE', ?, ?, ?, ?, ?, NULL, ?, NULL, ?)
            """, (org_id, hotel_id, area, prioridad, detalle, canal, ubicacion, huesped_id,
                created_at.isoformat(), due_at, session['user']['id'], qr_required))

            # history
            execute("""
                INSERT INTO TicketHistory(ticket_id, actor_user_id, action, motivo, at)
                VALUES (?, ?, 'CREADO', NULL, ?)
            """, (new_id, session['user']['id'], created_at.isoformat()))


            flash('Ticket creado.', 'success')
            return redirect(url_for('tickets'))
        except Exception as e:
            flash(f'Error creando ticket: {e}', 'error')

    # GET
    areas = ['MANTENCION','HOUSEKEEPING','ROOMSERVICE']
    prioridades = ['BAJA','MEDIA','ALTA','URGENTE']
    canales = ['recepcion','huesped_whatsapp','housekeeping_whatsapp','mantenimiento_app','roomservice_llamada']
    return render_template('ticket_create.html', user=session['user'],
                           areas=areas, prioridades=prioridades, canales=canales)

@app.post('/tickets/<int:id>/confirm')
@require_perm('ticket.confirm')
def ticket_confirm(id):
    """Recepción confirma / Gerente/Supervisor también pueden confirmar; dispara asignación."""
    if 'user' not in session: return redirect(url_for('login'))
    t = fetchone("SELECT id, org_id, area, estado FROM Tickets WHERE id=?", (id,))
    if not t:
        flash('Ticket no encontrado.', 'error'); return redirect(url_for('tickets'))
    if t['estado'] != 'PENDIENTE':
        flash('Solo puedes confirmar tickets pendientes.', 'error'); return redirect(url_for('tickets'))

    # Scope: supervisor solo su(s) área(s)
    if current_org_role() == 'SUPERVISOR' and not ensure_ticket_area_scope(t):
        flash('Fuera de tu área.', 'error'); return redirect(url_for('tickets'))

    # Simple assignment engine MVP (técnicos del área en la org con menor backlog)
    assignee = pick_assignee(t['org_id'], t['area'])
    fields = {"estado":"ASIGNADO"}
    if assignee: fields["assigned_to"] = assignee
    _update_ticket(id, fields, "CONFIRMADO")
    flash('Ticket confirmado y asignado.' if assignee else 'Ticket confirmado (sin asignar).', 'success')
    return redirect(url_for('tickets'))

def pick_assignee(org_id: int, area: str) -> int | None:
    """
    MVP assignment:
    - Busca técnicos del área en la org (via OrgUsers.role='TECNICO' + OrgUserAreas)
    - Elige el de menor backlog abierto
    """
    try:
        techs = fetchall("""
            SELECT u.id
            FROM Users u
            JOIN OrgUsers ou ON ou.user_id=u.id AND ou.org_id=?
            LEFT JOIN OrgUserAreas oa ON oa.org_id=ou.org_id AND oa.user_id=ou.user_id
            WHERE ou.role='TECNICO' AND (oa.area_code=? OR u.area=?)
        """, (org_id, area, area))
        if not techs:
            return None
        # pick least loaded
        best = None
        best_count = 1e9
        for r in techs:
            c = fetchone("""
                SELECT COUNT(1) c FROM Tickets
                 WHERE org_id=? AND assigned_to=? AND estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')
            """, (org_id, r['id']))['c']
            if c < best_count:
                best = r['id']; best_count = c
        return best
    except Exception:
        return None

# ---------------------------- transitions ----------------------------
def _update_ticket(id, fields: dict, action: str, motivo: str | None = None):
    sets = ", ".join([f"{k}=?" for k in fields.keys()])
    params = list(fields.values()) + [id]
    execute(f"UPDATE Tickets SET {sets} WHERE id=?", params)
    execute("""INSERT INTO TicketHistory(ticket_id, actor_user_id, action, motivo, at)
               VALUES (?,?,?,?,?)""",
            (id, session['user']['id'], action, motivo, datetime.now().isoformat()))

def _get_ticket_or_abort(id: int):
    t = fetchone("SELECT * FROM Tickets WHERE id=?", (id,))
    if not t:
        flash('Ticket no encontrado.', 'error')
        return None
    # org scope
    org_id, _ = current_scope()
    if not org_id or t['org_id'] != org_id:
        flash('Fuera de tu organización.', 'error')
        return None
    return t

@app.post('/tickets/<int:id>/accept')
@require_perm('ticket.transition.accept')
def ticket_accept(id):
    if 'user' not in session: return redirect(url_for('login'))
    t = _get_ticket_or_abort(id); ifnot = (t is None)
    if ifnot: return redirect(url_for('tickets'))

    # Técnico solo si es el asignado
    if current_org_role() == 'TECNICO' and t['assigned_to'] != session['user']['id']:
        flash('Solo puedes aceptar tus tickets.', 'error'); return redirect(url_for('tickets'))

    # Supervisor debe estar en su área
    if current_org_role() == 'SUPERVISOR' and not ensure_ticket_area_scope(t):
        flash('Fuera de tu área.', 'error'); return redirect(url_for('tickets'))

    _update_ticket(id, {"estado":"ACEPTADO", "accepted_at": datetime.now().isoformat(),
                        "assigned_to": t['assigned_to'] or session['user']['id']}, "ACEPTADO")
    flash('Ticket aceptado.', 'success')
    return redirect(url_for('tickets'))

@app.post('/tickets/<int:id>/start')
@require_perm('ticket.transition.start')
def ticket_start(id):
    if 'user' not in session: return redirect(url_for('login'))
    t = _get_ticket_or_abort(id); ifnot = (t is None)
    if ifnot: return redirect(url_for('tickets'))

    if current_org_role() == 'TECNICO' and t['assigned_to'] != session['user']['id']:
        flash('Solo puedes iniciar tus tickets.', 'error'); return redirect(url_for('tickets'))

    if current_org_role() == 'SUPERVISOR' and not ensure_ticket_area_scope(t):
        flash('Fuera de tu área.', 'error'); return redirect(url_for('tickets'))

    _update_ticket(id, {"estado":"EN_CURSO", "started_at": datetime.now().isoformat()}, "INICIADO")
    flash('Ticket iniciado.', 'success')
    return redirect(url_for('tickets'))

@app.post('/tickets/<int:id>/pause')
@require_perm('ticket.transition.pause')
def ticket_pause(id):
    if 'user' not in session: return redirect(url_for('login'))
    t = _get_ticket_or_abort(id); ifnot = (t is None)
    if ifnot: return redirect(url_for('tickets'))

    if current_org_role() == 'TECNICO' and t['assigned_to'] != session['user']['id']:
        flash('Solo puedes pausar tus tickets.', 'error'); return redirect(url_for('tickets'))

    if current_org_role() == 'SUPERVISOR' and not ensure_ticket_area_scope(t):
        flash('Fuera de tu área.', 'error'); return redirect(url_for('tickets'))

    motivo = request.form.get('motivo') or ''
    _update_ticket(id, {"estado":"PAUSADO"}, "PAUSADO", motivo)
    flash('Ticket en pausa.', 'success')
    return redirect(url_for('tickets'))

@app.post('/tickets/<int:id>/resume')
@require_perm('ticket.transition.resume')
def ticket_resume(id):
    if 'user' not in session: return redirect(url_for('login'))
    t = _get_ticket_or_abort(id); ifnot = (t is None)
    if ifnot: return redirect(url_for('tickets'))

    if current_org_role() == 'TECNICO' and t['assigned_to'] != session['user']['id']:
        flash('Solo puedes reanudar tus tickets.', 'error'); return redirect(url_for('tickets'))

    if current_org_role() == 'SUPERVISOR' and not ensure_ticket_area_scope(t):
        flash('Fuera de tu área.', 'error'); return redirect(url_for('tickets'))

    _update_ticket(id, {"estado":"EN_CURSO"}, "REANUDADO")
    flash('Ticket reanudado.', 'success')
    return redirect(url_for('tickets'))

@app.post('/tickets/<int:id>/reassign')
@require_perm('ticket.assign')
def ticket_reassign(id):
    if 'user' not in session: return redirect(url_for('login'))
    t = _get_ticket_or_abort(id); ifnot = (t is None)
    if ifnot: return redirect(url_for('tickets'))

    # Gerente puede reasignar libre en la org; Supervisor sólo su(s) áreas
    if current_org_role() == 'SUPERVISOR' and not ensure_ticket_area_scope(t):
        flash('Fuera de tu área.', 'error'); return redirect(url_for('tickets'))

    to_user = request.form.get('assigned_to', type=int)
    if not to_user:
        flash('Falta destino.', 'error'); return redirect(url_for('tickets'))
    _update_ticket(id, {"assigned_to": int(to_user), "estado":"ASIGNADO"}, "REASIGNADO",
                   request.form.get('motivo') or '')
    flash('Ticket reasignado.', 'success')
    return redirect(url_for('tickets'))

@app.post('/tickets/<int:id>/finish')
@require_perm('ticket.transition.finish')
def ticket_finish(id):
    if 'user' not in session: return redirect(url_for('login'))
    t = _get_ticket_or_abort(id); ifnot = (t is None)
    if ifnot: return redirect(url_for('tickets'))

    if current_org_role() == 'TECNICO' and t['assigned_to'] != session['user']['id']:
        flash('Solo puedes finalizar tus tickets.', 'error'); return redirect(url_for('tickets'))

    if current_org_role() == 'SUPERVISOR' and not ensure_ticket_area_scope(t):
        flash('Fuera de tu área.', 'error'); return redirect(url_for('tickets'))

    _update_ticket(id, {"estado":"RESUELTO", "finished_at": datetime.now().isoformat()}, "RESUELTO")
    flash('Ticket resuelto.', 'success')
    return redirect(url_for('tickets'))

# ---------------------------- PMS (read) ----------------------------
@app.get('/pms/guest')
def pms_guest():
    """Validación simple: /pms/guest?room=1203"""
    room = request.args.get('room')
    if not room:
        return jsonify({"error":"missing room"}), 400
    row = fetchone(
        "SELECT huesped_id, nombre, habitacion, status FROM PMSGuests WHERE habitacion=? AND status='IN_HOUSE'",
        (room,)
    )
    if not row:
        return jsonify({"found": False})
    return jsonify({"found": True, "huesped_id": row["huesped_id"], "nombre": row["nombre"], "habitacion": row["habitacion"]})

# ---------------------------- Supervisor charts API ----------------------------
def _must_login_json():
    return jsonify({"error": "unauthorized"}), 401

@app.get('/api/supervisor/backlog_by_tech')
def api_sup_backlog_by_tech():
    user = session.get('user')
    if not user:
        return _must_login_json()
    org_id, _hotel_id = current_scope()
    where = ["t.org_id = ?","t.estado IN (" + ",".join(["?"]*len(OPEN_STATES)) + ")"]
    params = [org_id, *OPEN_STATES]

    rows = fetchall(
        f"""
        SELECT COALESCE(u.username,'(sin asignar)') AS tech, COUNT(1) AS c
        FROM Tickets t
        LEFT JOIN Users u ON u.id = t.assigned_to
        WHERE {' AND '.join(where)}
        GROUP BY 1
        ORDER BY c DESC
        """,
        tuple(params)
    )
    return jsonify({
        "labels": [r['tech'] for r in rows],
        "values": [r['c'] for r in rows],
    })

@app.get('/api/supervisor/open_by_priority')
def api_sup_open_by_priority():
    user = session.get('user')
    if not user:
        return _must_login_json()
    org_id, _hotel_id = current_scope()
    where = ["org_id = ?","estado IN (" + ",".join(["?"]*len(OPEN_STATES)) + ")"]
    params = [org_id, *OPEN_STATES]

    rows = fetchall(
        f"""
        SELECT prioridad, COUNT(1) AS c
        FROM Tickets
        WHERE {' AND '.join(where)}
        GROUP BY prioridad
        ORDER BY CASE prioridad
            WHEN 'URGENTE' THEN 1
            WHEN 'ALTA'    THEN 2
            WHEN 'MEDIA'   THEN 3
            WHEN 'BAJA'    THEN 4
            ELSE 5 END
        """,
        tuple(params)
    )
    return jsonify({
        "labels": [r['prioridad'] for r in rows],
        "values": [r['c'] for r in rows],
    })

# ---------------------------- Superadmin dashboard ----------------------------
@app.route('/admin', methods=['GET', 'POST'])
def admin_super():
    if not is_superadmin():
        return redirect(url_for('dashboard'))

    # quick-create org from this page
    if request.method == 'POST':
        name = (request.form.get('org_name') or '').strip()
        if name:
            execute("INSERT INTO Orgs(name, created_at) VALUES(?, ?)", (name, datetime.now().isoformat()))
            flash('Organización creada.', 'success')
            return redirect(url_for('admin_super'))

    # orgs with counts
    orgs = fetchall("""
        SELECT
          o.id, o.name, o.created_at,
          (SELECT COUNT(1) FROM Hotels h WHERE h.org_id=o.id) AS hotels,
          (SELECT COUNT(1) FROM OrgUsers ou WHERE ou.org_id=o.id) AS members,
          (SELECT COUNT(1) FROM Tickets t WHERE t.org_id=o.id) AS tickets
        FROM Orgs o
        ORDER BY o.id DESC
    """)

    # recent hotels list
    hotels = fetchall("""
        SELECT h.id, h.name, h.org_id, o.name AS org_name
        FROM Hotels h JOIN Orgs o ON o.id=h.org_id
        ORDER BY h.id DESC LIMIT 12
    """)

    return render_template('admin_super.html',
                           user=session['user'],
                           orgs=orgs, hotels=hotels)

# ---------------------------- Org members management (superadmin) ----------------------------
@app.get('/admin/org/<int:org_id>/members')
def admin_org_members(org_id):
    if not is_superadmin():
        return redirect(url_for('dashboard'))

    org = fetchone("SELECT id, name FROM Orgs WHERE id=?", (org_id,))
    if not org:
        flash('Org no encontrada.', 'error')
        return redirect(url_for('admin_super'))

    members = fetchall("""
        SELECT ou.id as org_user_id, u.id as user_id, u.username, u.email, u.role, u.area,
               ou.role AS org_role, ou.default_area, ou.default_hotel_id,
               (SELECT name FROM Hotels WHERE id = ou.default_hotel_id) AS default_hotel
        FROM OrgUsers ou
        JOIN Users u ON u.id = ou.user_id
        WHERE ou.org_id=?
        ORDER BY u.role, u.username
    """, (org_id,))

    hotels = fetchall("SELECT id, name FROM Hotels WHERE org_id=? ORDER BY id", (org_id,))
    return render_template('admin_org_members.html',
                           user=session['user'], org=org, members=members, hotels=hotels)

@app.post('/admin/org/<int:org_id>/members/add')
def admin_org_members_add(org_id):
    if not is_superadmin():
        return redirect(url_for('dashboard'))

    email = (request.form.get('email') or '').strip().lower()
    username = (request.form.get('username') or '').strip()
    password = request.form.get('password') or 'demo123'
    base_role = request.form.get('base_role') or 'GERENTE'      # Users.role
    org_role = request.form.get('org_role') or base_role        # OrgUsers.role
    default_area = request.form.get('default_area') or None
    default_hotel_id = request.form.get('default_hotel_id', type=int)

    if not email or not username:
        flash('Usuario requiere email y username.', 'error')
        return redirect(url_for('admin_org_members', org_id=org_id))

    # find or create user
    u = fetchone("SELECT id FROM Users WHERE email=?", (email,))
    if not u:
        execute("""INSERT INTO Users(username,email,password_hash,role,area,telefono,activo,is_superadmin)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (username, email, hp(password), base_role, default_area, None, 1, 0))
        u = fetchone("SELECT id FROM Users WHERE email=?", (email,))

    # upsert membership
    existing = fetchone("SELECT id FROM OrgUsers WHERE org_id=? AND user_id=?", (org_id, u['id']))
    if existing:
        execute("""UPDATE OrgUsers SET role=?, default_area=?, default_hotel_id=?
                   WHERE id=?""", (org_role, default_area, default_hotel_id, existing['id']))
        flash('Membresía actualizada.', 'success')
    else:
        execute("""INSERT INTO OrgUsers(org_id,user_id,role,default_area,default_hotel_id)
                   VALUES (?,?,?,?,?)""", (org_id, u['id'], org_role, default_area, default_hotel_id))
        flash('Miembro agregado.', 'success')

    return redirect(url_for('admin_org_members', org_id=org_id))

@app.post('/admin/org/<int:org_id>/members/<int:org_user_id>/remove')
def admin_org_members_remove(org_id, org_user_id):
    if not is_superadmin():
        return redirect(url_for('dashboard'))
    execute("DELETE FROM OrgUsers WHERE id=?", (org_user_id,))
    flash('Membresía removida.', 'success')
    return redirect(url_for('admin_org_members', org_id=org_id))

# ---------------------------- Superadmin: SUDO + Admin pages ----------------------------
@app.get('/sudo')
def sudo_form():
    if not is_superadmin():
        return redirect(url_for('dashboard'))
    orgs = fetchall("SELECT id, name FROM Orgs ORDER BY id DESC")
    hotels = []
    if session.get('org_id'):
        hotels = fetchall("SELECT id, name FROM Hotels WHERE org_id=? ORDER BY id DESC", (session['org_id'],))
    return render_template('sudo.html', user=session['user'], orgs=orgs, hotels=hotels,
                           current={'org_id': session.get('org_id'), 'hotel_id': session.get('hotel_id')})

@app.post('/sudo')
def sudo_set():
    if not is_superadmin():
        return redirect(url_for('dashboard'))
    org_id = request.form.get('org_id', type=int)
    hotel_id = request.form.get('hotel_id', type=int)
    if org_id:
        session['org_id'] = org_id
        if not hotel_id:
            h = fetchone("SELECT id FROM Hotels WHERE org_id=? ORDER BY id LIMIT 1", (org_id,))
            hotel_id = h['id'] if h else None
    if hotel_id:
        session['hotel_id'] = hotel_id
    flash('Contexto actualizado.', 'success')
    return redirect(url_for('admin_super'))

@app.route('/admin/orgs', methods=['GET','POST'])
def admin_orgs():
    if not is_superadmin(): return redirect(url_for('dashboard'))
    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            execute("INSERT INTO Orgs(name, created_at) VALUES(?, ?)", (name, datetime.now().isoformat()))
            flash('Org creada.', 'success')
            return redirect(url_for('admin_orgs'))
    orgs = fetchall("SELECT id,name,created_at FROM Orgs ORDER BY id DESC")
    return render_template('admin_orgs.html', orgs=orgs)

@app.route('/admin/hotels', methods=['GET','POST'])
def admin_hotels():
    if not is_superadmin(): return redirect(url_for('dashboard'))
    if request.method == 'POST':
        org_id = request.form.get('org_id', type=int)
        name = request.form.get('name')
        if org_id and name:
            execute("INSERT INTO Hotels(org_id,name,created_at) VALUES(?,?,?)",
                    (org_id, name, datetime.now().isoformat()))
            flash('Hotel creado.', 'success')
            return redirect(url_for('admin_hotels'))
    orgs = fetchall("SELECT id,name FROM Orgs ORDER BY name")
    hotels = fetchall("SELECT h.id, h.name, o.name AS org FROM Hotels h JOIN Orgs o ON o.id=h.org_id ORDER BY h.id DESC")
    return render_template('admin_hotels.html', orgs=orgs, hotels=hotels)

# ---------------------------- run ----------------------------
if __name__ == '__main__':
    app.run(debug=True)
