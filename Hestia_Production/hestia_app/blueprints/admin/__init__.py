# hestia_app/blueprints/admin/__init__.py
from flask import Blueprint

# Keep your templates where they are:
# hestia_app/blueprints/admin/templates/admin/*.html
# Using template_folder="templates/admin" lets you keep render_template("admin_super.html") unchanged.
bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
    template_folder="templates/admin",
)

# Register routes
from . import routes  # noqa: E402,F401
