from flask import Blueprint, render_template, request, redirect, url_for, session

bp = Blueprint("auth", __name__, template_folder="templates")

@bp.get("/login")
def login():
    return render_template("auth/login.html")

@bp.post("/login", endpoint="login_post")
def login_post():
    # Stub simple: guarda rol y entra
    role = request.form.get("role", "RECEPCION")
    session["user"] = {"name": "Demo", "role": role}
    return redirect(url_for("dashboard"))  # usa alias definido abajo

@bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
