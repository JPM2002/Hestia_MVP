from flask import Blueprint

bp = Blueprint("tickets", __name__, template_folder="templates")

# Register routes
from . import routes  # noqa: E402,F401
