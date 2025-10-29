from flask import render_template, request, redirect, url_for, flash, session
from . import bp

# Intentamos usar tu capa de datos real; si no está disponible aún, seguimos con stubs seguros.
try:
    # Ajusta si tu app se llama distinto
    from hestia_app.services.db import get_db  # debe devolver una conexión sqlite3/psycopg2
except Exception:
    get_db = None  # fallback

# -----------------------------
# Helpers de contexto (SUDO)
# -----------------------------
def get_current_context():
    """Lee el contexto actual (SUDO) desde sesión."""
    return {
        "org_id": session.get("sudo_org_id"),
        "hotel_id": session.get("sudo_hotel_id"),
    }

def set_current_context(org_id, hotel_id):
    session["sudo_org_id"] = int(org_id) if org_id else None
    session["sudo_hotel_id"] = int(hotel_id) if hotel_id else None


# -----------------------------
# Helpers de datos (DB o stubs)
# -----------------------------
def _safe_query(query, params=()):
    """Ejecuta una query si hay DB; si no, devuelve [] sin romper la UI."""
    if get_db is None:
        return []
    try:
        con = get_db()
        cur = con.execute(query, params)
        rows = cur.fetchall()
        # Normaliza a lista de dicts
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in rows]
    except Exception as e:
        flash(f"DB error: {e}", "warning")
        return []

def _safe_exec(query, params=()):
    if get_db is None:
        flash("DB no configurada aún (operación simulada).", "info")
        return
    try:
        con = get_db()
        con.execute(query, params)
        con.commit()
    except Exception as e:
        flash(f"DB error: {e}", "warning")

def list_orgs_with_stats():
    """
    Devuelve organizaciones con stats mínimos para admin_super.
    Estructura esperada por la plantilla: id, name, hotels, members, tickets
    """
    # Si no hay DB, devolvemos datos vacíos pero válidos
    if get_db is None:
        return []
    # Ajusta nombres de tablas/joins según tu esquema real
    q = """
    SELECT o.id, o.name,
           COALESCE(h.cnt, 0)  AS hotels,
           COALESCE(m.cnt, 0)  AS members,
           COALESCE(t.cnt, 0)  AS tickets
    FROM orgs o
    LEFT JOIN (
        SELECT org_id, COUNT(*) cnt FROM hotels GROUP BY org_id
    ) h ON h.org_id = o.id
    LEFT JOIN (
        SELECT org_id, COUNT(*) cnt FROM org_users GROUP BY org_id
    ) m ON m.org_id = o.id
    LEFT JOIN (
        SELECT org_id, COUNT(*) cnt FROM tickets GROUP BY org_id
    ) t ON t.org_id = o.id
    ORDER BY o.id DESC
    """
    return _safe_query(q)

def list_recent_hotels_with_org():
    """
    Devuelve hoteles recientes: name, org_name, org_id
    Estructura usada en admin_super.html
    """
    if get_db is None:
        return []
    q = """
    SELECT h.id, h.name, h.org_id, o.name AS org_name
    FROM hotels h
    JOIN orgs o ON o.id = h.org_id
    ORDER BY h.id DESC
    LIMIT 25
    """
    return _safe_query(q)

def list_orgs():
    if get_db is None:
        return []
    return _safe_query("SELECT id, name, created_at FROM orgs ORDER BY id DESC")

def create_org(name):
    _safe_exec("INSERT INTO orgs(name) VALUES(?)", (name,))

def list_hotels():
    if get_db is None:
        return []
    q = """
    SELECT h.id, h.name, o.name AS org, h.org_id
    FROM hotels h
    JOIN orgs o ON o.id = h.org_id
    ORDER BY h.id DESC
    """
    return _safe_query(q)

def create_hotel(org_id, name):
    _safe_exec("INSERT INTO hotels(org_id, name) VALUES(?,?)", (org_id, name))

def get_org(org_id: int):
    if get_db is None:
        return None
    rows = _safe_query("SELECT id, name FROM orgs WHERE id = ?", (org_id,))
    return rows[0] if rows else None

def list_members_by_org(org_id: int):
    """
    Estructura esperada por la plantilla:
    username, email, role (base_role), org_role, default_area, default_hotel
    y org_user_id (para eliminar)
    """
    if get_db is None:
        return []
    q = """
    SELECT ou.id AS org_user_id,
           u.username,
           u.email,
           u.base_role AS role,
           ou.org_role,
           ou.default_area,
           h.name       AS default_hotel
    FROM org_users ou
    JOIN users u   ON u.id = ou.user_id
    LEFT JOIN hotels h ON h.id = ou.default_hotel_id
    WHERE ou.org_id = ?
    ORDER BY u.username
    """
    return _safe_query(q, (org_id,))

def add_or_update_member(org_id, email, username, base_role, org_role,
                         default_hotel_id, default_area, password):
    """
    Inserta/actualiza user + org_user (simplificado). Ajusta a tus constraints reales.
    """
    if get_db is None:
        flash("Operación simulada (sin DB).", "info")
        return

    con = get_db()
    try:
        cur = con.execute("SELECT id FROM users WHERE email = ?", (email,))
        row = cur.fetchone()
        if row:
            user_id = row[0]
            # Actualiza usuario básico
            con.execute(
                "UPDATE users SET username=?, base_role=? WHERE id=?",
                (username, base_role, user_id),
            )
        else:
            # Crea usuario (password plano sólo para demo; usa hash real en tu app)
            cur = con.execute(
                "INSERT INTO users (email, username, base_role, password) VALUES (?,?,?,?)",
                (email, username, base_role, password or "demo123"),
            )
            user_id = cur.lastrowid

        # Upsert org_user
        cur = con.execute(
            "SELECT id FROM org_users WHERE org_id=? AND user_id=?",
            (org_id, user_id),
        )
        row = cur.fetchone()
        dh_id = int(default_hotel_id) if default_hotel_id else None
        if row:
            con.execute(
                "UPDATE org_users SET org_role=?, default_area=?, default_hotel_id=? WHERE id=?",
                (org_role, default_area or None, dh_id, row[0]),
            )
        else:
            con.execute(
                "INSERT INTO org_users (org_id, user_id, org_role, default_area, default_hotel_id) VALUES (?,?,?,?,?)",
                (org_id, user_id, org_role, default_area or None, dh_id),
            )
        con.commit()
        flash("Miembro agregado/actualizado.", "success")
    except Exception as e:
        con.rollback()
        flash(f"DB error: {e}", "warning")

def remove_member(org_id, org_user_id):
    if get_db is None:
        flash("Operación simulada (sin DB).", "info")
        return
    _safe_exec("DELETE FROM org_users WHERE id=? AND org_id=?", (org_user_id, org_id))


# -----------------------------
# Rutas ADMIN (coinciden con url_for en plantillas)
# -----------------------------

@bp.route("/super", methods=["GET", "POST"], endpoint="admin_super")
def admin_super():
    if request.method == "POST":
        org_name = request.form.get("org_name", "").strip()
        if org_name:
            create_org(org_name)
            flash("Organización creada.", "success")
        else:
            flash("Nombre de organización requerido.", "warning")
        return redirect(url_for("admin_super"))

    orgs = list_orgs_with_stats()
    hotels = list_recent_hotels_with_org()
    return render_template("admin/admin_super.html", orgs=orgs, hotels=hotels)


@bp.route("/orgs", methods=["GET", "POST"], endpoint="admin_orgs")
def admin_orgs():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            create_org(name)
            flash("Organización creada.", "success")
            return redirect(url_for("admin_orgs"))
        flash("Nombre requerido.", "warning")

    orgs = list_orgs()
    return render_template("admin/admin_orgs.html", orgs=orgs)


@bp.route("/hotels", methods=["GET", "POST"], endpoint="admin_hotels")
def admin_hotels():
    if request.method == "POST":
        org_id = request.form.get("org_id")
        name = request.form.get("name", "").strip()
        if org_id and name:
            create_hotel(org_id, name)
            flash("Hotel creado.", "success")
            return redirect(url_for("admin_hotels"))
        flash("Selecciona una organización y nombre del hotel.", "warning")

    orgs = list_orgs()
    hotels = list_hotels()
    return render_template("admin/admin_hotels.html", orgs=orgs, hotels=hotels)


@bp.route("/org/<int:org_id>/members", methods=["GET"], endpoint="admin_org_members")
def admin_org_members(org_id: int):
    org = get_org(org_id)
    if not org:
        flash("Organización no encontrada.", "warning")
        return redirect(url_for("admin_orgs"))
    hotels = list_hotels()
    members = list_members_by_org(org_id)
    return render_template("admin/admin_org_members.html",
                           org=org, hotels=hotels, members=members)


@bp.route("/org/<int:org_id>/members/add", methods=["POST"], endpoint="admin_org_members_add")
def admin_org_members_add(org_id: int):
    # Campos del formulario (ver plantilla)
    email = request.form.get("email")
    username = request.form.get("username")
    base_role = request.form.get("base_role")
    org_role = request.form.get("org_role")
    default_hotel_id = request.form.get("default_hotel_id")
    default_area = request.form.get("default_area")
    password = request.form.get("password") or "demo123"

    if not (email and username and base_role and org_role):
        flash("Campos requeridos incompletos.", "warning")
        return redirect(url_for("admin_org_members", org_id=org_id))

    add_or_update_member(org_id, email, username, base_role, org_role,
                         default_hotel_id, default_area, password)
    return redirect(url_for("admin_org_members", org_id=org_id))


@bp.route("/org/<int:org_id>/members/<int:org_user_id>/remove", methods=["POST"], endpoint="admin_org_members_remove")
def admin_org_members_remove(org_id: int, org_user_id: int):
    remove_member(org_id, org_user_id)
    return redirect(url_for("admin_org_members", org_id=org_id))


@bp.route("/sudo", methods=["GET", "POST"], endpoint="sudo_form")
def sudo_form():
    if request.method == "POST":
        org_id = request.form.get("org_id") or None
        hotel_id = request.form.get("hotel_id") or None
        set_current_context(org_id, hotel_id)
        flash("Contexto actualizado.", "success")
        return redirect(url_for("sudo_form"))

    current = get_current_context()
    orgs = list_orgs()
    hotels = list_hotels()
    return render_template("admin/sudo.html", orgs=orgs, hotels=hotels, current=current)
