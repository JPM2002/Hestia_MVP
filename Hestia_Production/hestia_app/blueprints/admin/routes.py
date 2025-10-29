from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, session

from . import bp

# ---- Adjust these imports to your actual helpers/modules ----
from hestia_app.core.rbac import is_superadmin
from hestia_app.services.db import fetchall, fetchone, execute
try:
    # if you have a real password hasher
    from hestia_app.blueprints.auth.routes import hp  # noqa: F401
except Exception:
    # fallback stub; replace with your real hash function
    def hp(s: str) -> str:  # noqa: E305
        return s


# ---------------------------- Superadmin dashboard ----------------------------
@bp.route("/", methods=["GET", "POST"])
def admin_super():
    if not is_superadmin():
        # Adjust endpoint if your dashboard uses a different name, e.g. "dashboard.dashboard"
        return redirect(url_for("dashboard.index"))

    # quick-create org from this page
    if request.method == "POST":
        name = (request.form.get("org_name") or "").strip()
        if name:
            execute("INSERT INTO Orgs(name, created_at) VALUES(?, ?)", (name, datetime.now().isoformat()))
            flash("Organización creada.", "success")
            return redirect(url_for("admin.admin_super"))

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

    return render_template(
        "admin_super.html",
        user=session["user"],
        orgs=orgs,
        hotels=hotels,
    )


# ---------------------------- Org members management (superadmin) ----------------------------
@bp.get("/org/<int:org_id>/members")
def admin_org_members(org_id):
    if not is_superadmin():
        return redirect(url_for("dashboard.index"))

    org = fetchone("SELECT id, name FROM Orgs WHERE id=?", (org_id,))
    if not org:
        flash("Org no encontrada.", "error")
        return redirect(url_for("admin.admin_super"))

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
    return render_template(
        "admin_org_members.html",
        user=session["user"],
        org=org,
        members=members,
        hotels=hotels,
    )


@bp.post("/org/<int:org_id>/members/add")
def admin_org_members_add(org_id):
    if not is_superadmin():
        return redirect(url_for("dashboard.index"))

    email = (request.form.get("email") or "").strip().lower()
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or "demo123"
    base_role = request.form.get("base_role") or "GERENTE"      # Users.role
    org_role = request.form.get("org_role") or base_role        # OrgUsers.role
    default_area = request.form.get("default_area") or None
    default_hotel_id = request.form.get("default_hotel_id", type=int)

    if not email or not username:
        flash("Usuario requiere email y username.", "error")
        return redirect(url_for("admin.admin_org_members", org_id=org_id))

    # find or create user
    u = fetchone("SELECT id FROM Users WHERE email=?", (email,))
    if not u:
        # Use real booleans for Postgres; SQLite will coerce them to 1/0.
        execute("""
            INSERT INTO Users(username,email,password_hash,role,area,telefono,activo,is_superadmin)
            VALUES (?,?,?,?,?,?,?,?)
        """, (username, email, hp(password), base_role, default_area, None, True, False))

        u = fetchone("SELECT id FROM Users WHERE email=?", (email,))

    # upsert membership
    existing = fetchone("SELECT id FROM OrgUsers WHERE org_id=? AND user_id=?", (org_id, u["id"]))
    if existing:
        execute("""
            UPDATE OrgUsers SET role=?, default_area=?, default_hotel_id=?
            WHERE id=?
        """, (org_role, default_area, default_hotel_id, existing["id"]))
        flash("Membresía actualizada.", "success")
    else:
        execute("""
            INSERT INTO OrgUsers(org_id,user_id,role,default_area,default_hotel_id)
            VALUES (?,?,?,?,?)
        """, (org_id, u["id"], org_role, default_area, default_hotel_id))
        flash("Miembro agregado.", "success")

    return redirect(url_for("admin.admin_org_members", org_id=org_id))


@bp.post("/org/<int:org_id>/members/<int:org_user_id>/remove")
def admin_org_members_remove(org_id, org_user_id):
    if not is_superadmin():
        return redirect(url_for("dashboard.index"))
    execute("DELETE FROM OrgUsers WHERE id=?", (org_user_id,))
    flash("Membresía removida.", "success")
    return redirect(url_for("admin.admin_org_members", org_id=org_id))


# ---------------------------- Superadmin: SUDO + Admin pages ----------------------------
# Note: now lives at /admin/sudo (normalized under the admin blueprint)
@bp.get("/sudo")
def sudo_form():
    if not is_superadmin():
        return redirect(url_for("dashboard.index"))
    orgs = fetchall("SELECT id, name FROM Orgs ORDER BY id DESC")
    hotels = []
    if session.get("org_id"):
        hotels = fetchall("SELECT id, name FROM Hotels WHERE org_id=? ORDER BY id DESC", (session["org_id"],))
    return render_template(
        "sudo.html",
        user=session["user"],
        orgs=orgs,
        hotels=hotels,
        current={"org_id": session.get("org_id"), "hotel_id": session.get("hotel_id")},
    )


@bp.post("/sudo")
def sudo_set():
    if not is_superadmin():
        return redirect(url_for("dashboard.index"))
    org_id = request.form.get("org_id", type=int)
    hotel_id = request.form.get("hotel_id", type=int)
    if org_id:
        session["org_id"] = org_id
        if not hotel_id:
            h = fetchone("SELECT id FROM Hotels WHERE org_id=? ORDER BY id LIMIT 1", (org_id,))
            hotel_id = h["id"] if h else None
    if hotel_id:
        session["hotel_id"] = hotel_id
    flash("Contexto actualizado.", "success")
    return redirect(url_for("admin.admin_super"))


@bp.route("/orgs", methods=["GET", "POST"])
def admin_orgs():
    if not is_superadmin():
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        name = request.form.get("name")
        if name:
            execute("INSERT INTO Orgs(name, created_at) VALUES(?, ?)", (name, datetime.now().isoformat()))
            flash("Org creada.", "success")
            return redirect(url_for("admin.admin_orgs"))
    orgs = fetchall("SELECT id,name,created_at FROM Orgs ORDER BY id DESC")
    return render_template("admin_orgs.html", orgs=orgs)


@bp.route("/hotels", methods=["GET", "POST"])
def admin_hotels():
    if not is_superadmin():
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        org_id = request.form.get("org_id", type=int)
        name = request.form.get("name")
        if org_id and name:
            execute(
                "INSERT INTO Hotels(org_id,name,created_at) VALUES(?,?,?)",
                (org_id, name, datetime.now().isoformat()),
            )
            flash("Hotel creado.", "success")
            return redirect(url_for("admin.admin_hotels"))
    orgs = fetchall("SELECT id,name FROM Orgs ORDER BY name")
    hotels = fetchall("""
        SELECT h.id, h.name, o.name AS org
        FROM Hotels h JOIN Orgs o ON o.id=h.org_id
        ORDER BY h.id DESC
    """)
    return render_template("admin_hotels.html", orgs=orgs, hotels=hotels)
