from flask import render_template
from . import bp

@bp.get("/")
def dashboard_home():
    # Buscará exactamente este archivo:
    return render_template("dashboards/dashboard_gerente.html")
