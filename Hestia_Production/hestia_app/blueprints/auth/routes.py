from flask import render_template, request, redirect, url_for, session, flash
from . import bp

@bp.get("/login")
def login():
    return render_template("auth/login.html")

@bp.post("/login")
def login_post():
    email = request.form.get("email")
    role = request.form.get("role", "RECEPCION")
    session["user"] = {
        "name": (email.split("@")[0] if email else "Usuario"),
        "role": role,
        "is_superadmin": False,
    }
    flash("Bienvenido 👋", "success")
    return redirect(url_for("dashboard.home"))

@bp.get("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada", "success")
    return redirect(url_for("auth.login"))
