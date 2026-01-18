# hestia_app/blueprints/auth/__init__.py
from flask import Blueprint

# Keep template at:
# hestia_app/blueprints/auth/templates/auth/login.html
bp = Blueprint(
    "auth",
    __name__,
    url_prefix="",
    template_folder="templates/auth",
)

from . import routes  # noqa: E402,F401
