from flask import render_template
from . import bp

@bp.get("/")
def admin_home():
    return render_template("admin/admin_super.html")
