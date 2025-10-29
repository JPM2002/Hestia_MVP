from flask import Blueprint

# Keep url_prefix="" so your existing URLs don't change
bp = Blueprint(
    "tecnico",
    __name__,
    url_prefix="",
    template_folder="templates",
)

# Import routes so their decorators register on this blueprint
from . import routes  # noqa: E402,F401
