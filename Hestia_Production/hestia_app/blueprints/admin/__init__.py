from flask import Blueprint

bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",          # <- clave: NO tomar "/"
    template_folder="templates"
)

from . import routes  # noqa
