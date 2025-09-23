from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, get_flashed_messages, session, jsonify
)
import sqlite3 as sql
from datetime import datetime, timedelta
import hashlib

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-me-in-env'
DATABASE = 'hestia.db'

# ---------------------------- helpers ----------------------------
def hp(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def db():
    conn = sql.connect(DATABASE)
    conn.row_factory = sql.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def fetchone(query, params=()):
    with db() as conn:
        cur = conn.execute(query, params)
        return cur.fetchone()

def fetchall(query, params=()):
    with db() as conn:
        cur = conn.execute(query, params)
        return cur.fetchall()

def execute(query, params=()):
    with db() as conn:
        conn.execute(query, params)
        conn.commit()

def sla_minutes(area, prioridad) -> int | None:
    row = fetchone("SELECT max_minutes FROM SLARules WHERE area=? AND prioridad=?",
                   (area, prioridad))
    return int(row["max_minutes"]) if row else None

def compute_due(created_at: datetime, area: str, prioridad: str) -> datetime | None:
    mins = sla_minutes(area, prioridad)
    return created_at + timedelta(minutes=mins) if mins else None

def is_critical(now: datetime, due_at: str | None) -> bool:
    if not due_at:
        return False
    try:
        due = datetime.fromisoformat(due_at)
    except Exception:
        return False
    return now >= (due - timedelta(minutes=10))

# ---------------------------- base routes ----------------------------
@app.route('/')
def index():
    if 'user' in session:
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
        ident = request.form.get('email')  # email or username
        password = request.form.get('password')

        row = fetchone(
            """
            SELECT id, username, email, password_hash, role, area, telefono, activo
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
                'role': row['role'],
                'area': row['area']  # may be None for GERENTE
            }
            return redirect(url_for('dashboard'))
        else:
            message = 'Invalid credentials or inactive user.'

    return render_template('login.html', message=message, success=success)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ---------------------------- role data helpers ----------------------------
def get_global_kpis():
    """KPIs for GERENTE."""
    now = datetime.now()
    active_states = ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')
    active = fetchall(
        f"SELECT id, due_at FROM Tickets WHERE estado IN ({','.join(['?']*len(active_states))})",
        active_states
    )
    total_active = len(active)
    critical = sum(1 for r in active if is_critical(now, r['due_at']))

    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    resolved_today = fetchone(
        "SELECT COUNT(1) c FROM Tickets WHERE estado='RESUELTO' AND finished_at >= ?",
        (start_of_day,)
    )['c']

    by_area = fetchall("""
        SELECT area, COUNT(1) c
        FROM Tickets
        WHERE estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO','RESUELTO')
        GROUP BY area
    """)
    kpis = {
        "critical": critical,
        "active": total_active,
        "resolved_today": resolved_today,
        "by_area": {r["area"]: r["c"] for r in by_area}
    }

    # trend: last 7 days resolved per day
    trend = fetchall("""
        SELECT substr(finished_at,1,10) d, COUNT(1) c
        FROM Tickets
        WHERE estado='RESUELTO' AND finished_at >= date('now','-7 day')
        GROUP BY substr(finished_at,1,10)
        ORDER BY d
    """)
    charts = {
        "resolved_last7": [{"date": r["d"], "count": r["c"]} for r in trend]
    }
    return kpis, charts

def get_area_data(area: str | None):
    """KPIs + open tickets for SUPERVISOR (area-scoped)."""
    if not area:
        # fallback: nothing filtered
        area = None
    params = []
    where = ["1=1"]
    if area:
        where.append("area=?")
        params.append(area)

    now = datetime.now()
    active = fetchall(
        f"SELECT id, due_at FROM Tickets WHERE {' AND '.join(where)} AND estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')",
        params
    )
    total_active = len(active)
    critical = sum(1 for r in active if is_critical(now, r['due_at']))

    resolved_24 = fetchone(
        f"""
        SELECT COUNT(1) c FROM Tickets
        WHERE {' AND '.join(where)} AND estado='RESUELTO'
          AND finished_at >= datetime('now','-1 day')
        """, params
    )['c']

    kpis = {"critical": critical, "active": total_active, "resolved_24h": resolved_24}

    rows = fetchall(
        f"""
        SELECT id, area, prioridad, estado, detalle, ubicacion, created_at, due_at, assigned_to
        FROM Tickets
        WHERE {' AND '.join(where)} AND estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')
        ORDER BY created_at DESC
        """, params
    )
    tickets = [{
        "id": r["id"], "area": r["area"], "prioridad": r["prioridad"], "estado": r["estado"],
        "detalle": r["detalle"], "ubicacion": r["ubicacion"], "created_at": r["created_at"],
        "due_at": r["due_at"], "is_critical": is_critical(now, r["due_at"])
    } for r in rows]
    return kpis, tickets

def get_assigned_tickets(user_id: int):
    """Tickets assigned to a TECH/OP role."""
    now = datetime.now()
    rows = fetchall("""
        SELECT id, area, prioridad, estado, detalle, ubicacion, created_at, due_at
        FROM Tickets
        WHERE assigned_to = ? AND estado IN ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')
        ORDER BY created_at DESC
    """, (user_id,))
    return [{
        "id": r["id"], "area": r["area"], "prioridad": r["prioridad"], "estado": r["estado"],
        "detalle": r["detalle"], "ubicacion": r["ubicacion"], "created_at": r["created_at"],
        "due_at": r["due_at"], "is_critical": is_critical(now, r["due_at"])
    } for r in rows]

# ---------------------------- dashboard ----------------------------
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']
    role = user.get('role')

    if role == 'GERENTE':
        kpis, charts = get_global_kpis()
        # If you have a specific gerente template, use it. Otherwise fall back:
        try:
            return render_template('dashboard_gerente.html', user=user, kpis=kpis, charts=charts)
        except:
            return render_template('dashboard.html', user=user, kpis=kpis)

    elif role == 'SUPERVISOR':
        kpis, tickets = get_area_data(user.get('area'))
        try:
            return render_template('dashboard_supervisor.html', user=user, kpis=kpis, tickets=tickets)
        except:
            # fallback to generic dashboard KPIs
            return render_template('dashboard.html', user=user, kpis=kpis)

    else:  # TECNICO / other ops roles
        tickets = get_assigned_tickets(user['id'])
        try:
            return render_template('dashboard_tecnico.html', user=user, tickets=tickets)
        except:
            # fallback generic KPIs
            kpis, _ = get_area_data(user.get('area'))
            return render_template('dashboard.html', user=user, kpis=kpis)

# ---------------------------- tickets list & filters ----------------------------
@app.route('/tickets')
def tickets():
    if 'user' not in session:
        return redirect(url_for('login'))

    q = request.args.get('q', '').strip()
    area = request.args.get('area')
    prioridad = request.args.get('prioridad')
    estado = request.args.get('estado')
    period = request.args.get('period', 'today')  # today|yesterday|7d|30d|all

    where, params = ["1=1"], []
    if q:
        where.append("(detalle LIKE ? OR ubicacion LIKE ? OR huesped_id LIKE ?)")
        like = f"%{q}%"; params += [like, like, like]
    if area: where += ["area=?"]; params += [area] if area else []
    if prioridad: where += ["prioridad=?"]; params += [prioridad] if prioridad else []
    if estado: where += ["estado=?"]; params += [estado] if estado else []

    now = datetime.now()
    sod = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == 'today':
        where += ["created_at >= ?"]; params += [sod.isoformat()]
    elif period == 'yesterday':
        y0 = (sod - timedelta(days=1)).isoformat()
        where += ["created_at >= ? AND created_at < ?"]; params += [y0, sod.isoformat()]
    elif period == '7d':
        where += ["created_at >= ?"]; params += [(sod - timedelta(days=7)).isoformat()]
    elif period == '30d':
        where += ["created_at >= ?"]; params += [(sod - timedelta(days=30)).isoformat()]

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

# ---------------------------- create ticket ----------------------------
@app.route('/tickets/create', methods=['GET', 'POST'])
def ticket_create():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
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
            execute("""
                INSERT INTO Tickets(id, area, prioridad, estado, detalle, canal_origen, ubicacion,
                                    huesped_id, created_at, due_at, assigned_to, created_by,
                                    confidence_score, qr_required)
                VALUES (NULL, ?, ?, 'PENDIENTE', ?, ?, ?, ?, ?, ?, NULL, ?, NULL, ?)
            """, (area, prioridad, detalle, canal, ubicacion, huesped_id,
                  created_at.isoformat(), due_at, session['user']['id'], qr_required))

            # history
            execute("""
                INSERT INTO TicketHistory(ticket_id, actor_user_id, action, motivo, at)
                VALUES ((SELECT last_insert_rowid()), ?, 'CREADO', NULL, ?)
            """, (session['user']['id'], created_at.isoformat()))

            flash('Ticket creado.', 'success')
            return redirect(url_for('tickets'))
        except Exception as e:
            flash(f'Error creando ticket: {e}', 'error')

    # GET
    areas = ['MANTENCION','HOUSEKEEPING','ROOMSERVICE']
    prioridades = ['BAJA','MEDIA','ALTA','URGENTE']
    canales = ['recepcion','huesped_whatsapp','housekeeping_whatsapp','mantenimiento_app']
    return render_template('ticket_create.html', user=session['user'],
                           areas=areas, prioridades=prioridades, canales=canales)

# ---------------------------- transitions ----------------------------
def _update_ticket(id, fields: dict, action: str, motivo: str | None = None):
    sets = ", ".join([f"{k}=?" for k in fields.keys()])
    params = list(fields.values()) + [id]
    execute(f"UPDATE Tickets SET {sets} WHERE id=?", params)
    execute("""INSERT INTO TicketHistory(ticket_id, actor_user_id, action, motivo, at)
               VALUES (?,?,?,?,?)""",
            (id, session['user']['id'], action, motivo, datetime.now().isoformat()))

@app.post('/tickets/<int:id>/accept')
def ticket_accept(id):
    if 'user' not in session: return redirect(url_for('login'))
    _update_ticket(id, {"estado":"ACEPTADO", "accepted_at": datetime.now().isoformat(),
                        "assigned_to": session['user']['id']}, "ACEPTADO")
    flash('Ticket aceptado.', 'success')
    return redirect(url_for('tickets'))

@app.post('/tickets/<int:id>/start')
def ticket_start(id):
    if 'user' not in session: return redirect(url_for('login'))
    _update_ticket(id, {"estado":"EN_CURSO", "started_at": datetime.now().isoformat()}, "INICIADO")
    flash('Ticket iniciado.', 'success')
    return redirect(url_for('tickets'))

@app.post('/tickets/<int:id>/pause')
def ticket_pause(id):
    if 'user' not in session: return redirect(url_for('login'))
    motivo = request.form.get('motivo') or ''
    _update_ticket(id, {"estado":"PAUSADO"}, "PAUSADO", motivo)
    flash('Ticket en pausa.', 'success')
    return redirect(url_for('tickets'))

@app.post('/tickets/<int:id>/resume')
def ticket_resume(id):
    if 'user' not in session: return redirect(url_for('login'))
    _update_ticket(id, {"estado":"EN_CURSO"}, "REANUDADO")
    flash('Ticket reanudado.', 'success')
    return redirect(url_for('tickets'))

@app.post('/tickets/<int:id>/reassign')
def ticket_reassign(id):
    if 'user' not in session: return redirect(url_for('login'))
    to_user = request.form.get('assigned_to')
    _update_ticket(id, {"assigned_to": int(to_user), "estado":"ASIGNADO"}, "REASIGNADO",
                   request.form.get('motivo') or '')
    flash('Ticket reasignado.', 'success')
    return redirect(url_for('tickets'))

@app.post('/tickets/<int:id>/finish')
def ticket_finish(id):
    if 'user' not in session: return redirect(url_for('login'))
    _update_ticket(id, {"estado":"RESUELTO", "finished_at": datetime.now().isoformat()}, "RESUELTO")
    flash('Ticket resuelto.', 'success')
    return redirect(url_for('tickets'))

# ---------------------------- PMS (read) ----------------------------
@app.get('/pms/guest')
def pms_guest():
    """Simple read-only validation: /pms/guest?room=1203"""
    room = request.args.get('room')
    if not room:
        return jsonify({"error":"missing room"}), 400
    row = fetchone("SELECT huesped_id, nombre, habitacion, status FROM PMSGuests WHERE habitacion=? AND status='IN_HOUSE'", (room,))
    if not row:
        return jsonify({"found": False})
    return jsonify({"found": True, "huesped_id": row["huesped_id"], "nombre": row["nombre"], "habitacion": row["habitacion"]})

OPEN_STATES = ('PENDIENTE','ASIGNADO','ACEPTADO','EN_CURSO','PAUSADO','DERIVADO')

def _must_login_json():
    return jsonify({"error": "unauthorized"}), 401

@app.get('/api/supervisor/backlog_by_tech')
def api_sup_backlog_by_tech():
    if 'user' not in session:
        return _must_login_json()
    user = session['user']
    area = user.get('area')  # <-- read from session['user']

    # Build WHERE dynamically: if area is None we show all areas
    where = ["t.estado IN (" + ",".join(["?"]*len(OPEN_STATES)) + ")"]
    params = [*OPEN_STATES]
    if area:
        where.insert(0, "t.area = ?")
        params.insert(0, area)

    rows = fetchall(
        f"""
        SELECT COALESCE(u.username,'(sin asignar)') AS tech, COUNT(1) AS c
        FROM Tickets t
        LEFT JOIN Users u ON u.id = t.assigned_to
        WHERE {' AND '.join(where)}
        GROUP BY tech
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
    if 'user' not in session:
        return _must_login_json()
    user = session['user']
    area = user.get('area')  # <-- read from session['user']

    where = ["estado IN (" + ",".join(["?"]*len(OPEN_STATES)) + ")"]
    params = [*OPEN_STATES]
    if area:
        where.insert(0, "area = ?")
        params.insert(0, area)

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


# ---------------------------- run ----------------------------
if __name__ == '__main__':
    app.run(debug=True)
