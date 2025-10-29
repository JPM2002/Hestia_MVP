from flask import render_template
from . import bp

@bp.get("/login")
def login():
    return render_template("auth/login.html")
