from flask import Blueprint

bp = Blueprint(
    "dashboard",
    __name__,
    url_prefix="/home",
    template_folder="templates",
)

from . import routes  # noqa: F401
