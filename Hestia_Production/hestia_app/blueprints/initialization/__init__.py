from flask import Blueprint

bp = Blueprint(
    "initialization",
    __name__,
    url_prefix="/init",
    template_folder="templates",  # uses hestia_app/blueprints/initialization/templates
)

from . import routes  # noqa: F401
