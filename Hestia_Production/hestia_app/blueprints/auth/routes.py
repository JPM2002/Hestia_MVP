from flask import render_template, request, redirect, url_for, flash, session, current_app
from . import bp
from services.db import fetchone  # usa tu capa de DB ya modularizada
import hashlib

def hp(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

@bp.route("/login", methods=["GET", "POST"])
def login():
    # Mensaje opcional (flash) + props explícitas del template
    message, success = None, False

    if request.method == "POST":
        ident = (request.form.get("email") or "").strip()   # email o username
        password = request.form.get("password") or ""

        row = fetchone(
            """
            SELECT id, username, email, password_hash, role, area, telefono, activo, is_superadmin
            FROM Users
            WHERE (email = ? OR username = ?)
            """,
            (ident, ident),
        )

        if row and bool(row.get("activo")) and hp(password) == row.get("password_hash"):
            session["user"] = {
                "id": row["id"],
                "name": row["username"],
                "email": row["email"],
                "role": row["role"],
                "area": row["area"],
                "is_superadmin": bool(row.get("is_superadmin")),
            }

            # fijar alcance (org/hotel) desde la primera membresía
            ou = fetchone(
                """
                SELECT org_id,
                       COALESCE(default_hotel_id,
                         (SELECT id FROM Hotels WHERE org_id=OrgUsers.org_id LIMIT 1)
                       ) AS hotel_id
                FROM OrgUsers WHERE user_id=? LIMIT 1
                """,
                (row["id"],),
            )
            if ou:
                session["org_id"] = ou["org_id"]
                session["hotel_id"] = ou["hotel_id"]
            elif session["user"]["is_superadmin"]:
                org = fetchone("SELECT id FROM Orgs ORDER BY id LIMIT 1")
                if org:
                    session["org_id"] = org["id"]
                    h = fetchone("SELECT id FROM Hotels WHERE org_id=? ORDER BY id LIMIT 1", (org["id"],))
                    session["hotel_id"] = h["id"] if h else None

            # redirecciones por rol
            if session["user"]["is_superadmin"]:
                return redirect(url_for("admin.admin_super"))
            # dashboard general (tu blueprint de dashboard debe exponer 'dashboard')
            return redirect(url_for("dashboard.dashboard"))

        # fallo de login
        message = "Credenciales inválidas o usuario inactivo."
        success = False

    return render_template(
        "auth/login.html",
        message=message,
        success=success,
        enable_demo=current_app.config.get("ENABLE_TECH_DEMO", False),
    )

@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))

@bp.get("/demo/tecnico")
def demo_tecnico():
    if not current_app.config.get("ENABLE_TECH_DEMO", False):
        flash("Demo deshabilitada.", "error")
        return redirect(url_for("auth.login"))

    area = (request.args.get("area") or "MANTENCION").upper()
    if area not in ("MANTENCION", "HOUSEKEEPING", "ROOMSERVICE"):
        area = "MANTENCION"

    view = (request.args.get("view") or "auto").lower()
    if view not in ("mobile", "desktop", "auto"):
        view = "auto"

    # Usuario de demo (sin escribir en DB)
    session["user"] = {
        "id": -9999,
        "name": "Demo Tech",
        "email": "demo@local",
        "role": "TECNICO",
        "area": area,
        "is_superadmin": False,
    }

    # Contexto org/hotel mínimo para poder entrar a dashboards
    org = fetchone("SELECT id FROM Orgs ORDER BY id LIMIT 1")
    session["org_id"] = org["id"] if org else None
    if org:
        h = fetchone("SELECT id FROM Hotels WHERE org_id=? ORDER BY id LIMIT 1", (org["id"],))
        session["hotel_id"] = h["id"] if h else None
    else:
        session["hotel_id"] = None

    flash(f"Demo técnico — Área: {area} (vista: {view})", "success")
    # tu blueprint de dashboard debería resolver este endpoint
    return redirect(url_for("dashboard.dashboard", view=None if view == "auto" else view))
