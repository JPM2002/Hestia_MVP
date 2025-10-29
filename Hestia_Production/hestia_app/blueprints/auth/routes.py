from datetime import datetime
import hashlib

from flask import (
    render_template, request, redirect, url_for, flash, session,
    get_flashed_messages, current_app
)

from . import bp

# ---- DB helpers (adjust to your actual module) ----
from hestia_app.services.db import fetchone  # and execute/fetchall if you later need them

# Optional: user-agent parsing (not required here)
try:
    from user_agents import parse as parse_ua  # noqa: F401
except Exception:
    parse_ua = None  # noqa: F401


def hp(password: str) -> str:
    """Simple SHA-256 hash — replace with your real hasher if available."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# ---------------------------- auth & base ----------------------------
@bp.route("/")
def index():
    if session.get("user"):
        # Adjust endpoint name if your dashboard uses a different one (e.g., "dashboard.dashboard")
        return redirect(url_for("dashboard.index"))
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    message, success = None, False

    flashed = get_flashed_messages(with_categories=True)
    if flashed:
        cat, msg = flashed[0]
        message = msg
        success = (cat == "success")

    if request.method == "POST":
        ident = request.form.get("email")  # email o username
        password = request.form.get("password") or ""

        row = fetchone(
            """
            SELECT id, username, email, password_hash, role, area, telefono, activo, is_superadmin
            FROM Users
            WHERE (email = ? OR username = ?)
            """,
            (ident, ident),
        )

        is_active = bool(row["activo"]) if row else False
        is_super = bool(row["is_superadmin"]) if row else False

        if row and hp(password) == row["password_hash"] and is_active:
            session["user"] = {
                "id": row["id"],
                "name": row["username"],
                "email": row["email"],
                "role": row["role"],
                "area": row["area"],
                "is_superadmin": is_super,
            }

            # Scope: from first membership or first org/hotel if superadmin
            ou = fetchone(
                """
                SELECT org_id,
                       COALESCE(
                         default_hotel_id,
                         (SELECT id FROM Hotels WHERE org_id = OrgUsers.org_id LIMIT 1)
                       ) AS hotel_id
                FROM OrgUsers
                WHERE user_id = ?
                LIMIT 1
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
                    h = fetchone(
                        "SELECT id FROM Hotels WHERE org_id=? ORDER BY id LIMIT 1",
                        (org["id"],),
                    )
                    session["hotel_id"] = h["id"] if h else None

            if session["user"]["is_superadmin"]:
                return redirect(url_for("admin.admin_super"))
            return redirect(url_for("dashboard.index"))
        else:
            message = "Credenciales inválidas o usuario inactivo."

    return render_template(
        "login.html",
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
    # Guard: only if explicitly enabled
    if not current_app.config.get("ENABLE_TECH_DEMO"):
        flash("Demo deshabilitada.", "error")
        return redirect(url_for("auth.login"))

    area = (request.args.get("area") or "MANTENCION").upper()
    if area not in ("MANTENCION", "HOUSEKEEPING", "ROOMSERVICE"):
        area = "MANTENCION"

    # Optional force view: 'mobile' | 'desktop' | 'auto'
    view = (request.args.get("view") or "").lower()
    if view not in ("mobile", "desktop", "auto"):
        view = "auto"

    # Create a demo session user (no DB write)
    session["user"] = {
        "id": -9999,
        "name": "Demo Tech",
        "email": "demo@local",
        "role": "TECNICO",
        "area": area,
        "is_superadmin": False,
    }

    # Set org/hotel scope to the first available rows (if exist)
    org = fetchone("SELECT id FROM Orgs ORDER BY id LIMIT 1")
    session["org_id"] = org["id"] if org else None
    if org:
        h = fetchone("SELECT id FROM Hotels WHERE org_id=? ORDER BY id LIMIT 1", (org["id"],))
        session["hotel_id"] = h["id"] if h else None
    else:
        session["hotel_id"] = None

    flash(f"Demo técnico — Área: {area} (vista: {view or 'auto'})", "success")

    # If 'view' provided, pass it as query param; otherwise omit it
    if view:
        return redirect(url_for("dashboard.index", view=view))
    return redirect(url_for("dashboard.index"))


def is_superadmin():
    return bool(session.get("user", {}).get("is_superadmin"))
