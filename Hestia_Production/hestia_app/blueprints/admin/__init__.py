from flask import Blueprint

# Importante: template_folder apunta a la carpeta "templates" dentro del paquete admin
bp = Blueprint("admin", __name__, template_folder="templates")

# Mantén esta importación al final para registrar las rutas al cargar el blueprint.
from . import routes  # noqa: E402,F401
