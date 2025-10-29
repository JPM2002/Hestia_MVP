# hestia_app/blueprints/auth/routes.py
from flask import Blueprint, render_template
bp = Blueprint("auth", __name__, template_folder="templates")  # ✅
@bp.get("/login")
def login():
    return render_template("auth/login.html")
