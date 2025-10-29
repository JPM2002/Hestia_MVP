from flask import Blueprint

bp = Blueprint(
    "dashboard",
    __name__,
    url_prefix="/dashboard",
    # Your files live at blueprints/dashboard/templates/dashboards/*.html
    template_folder="templates/dashboards",
)

from . import routes  # noqa: E402,F401
