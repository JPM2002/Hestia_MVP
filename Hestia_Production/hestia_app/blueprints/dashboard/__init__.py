from flask import Blueprint, render_template

bp = Blueprint(
    "dashboard",
    __name__,
    url_prefix="/home",
    template_folder="templates"
)

@bp.get("/", endpoint="dashboard")   # ← alias: ahora existe endpoint 'dashboard'
def dashboard_home():
    return render_template("dashboards/dashboard_gerente.html")
