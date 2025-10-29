from flask import Blueprint

# Usa el mismo nombre del blueprint para que funcione url_for("dashboard.dashboard")
bp = Blueprint("dashboard", __name__, template_folder="templates")

# Carga las rutas
from . import routes  # noqa: E402,F401
