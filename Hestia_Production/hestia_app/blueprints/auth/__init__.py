from flask import Blueprint

bp = Blueprint(
    "auth",                     # <-- blueprint name must be 'auth'
    __name__,
    url_prefix="/auth",         # <-- Option A: login lives at /auth/login
    template_folder="templates"
)

from . import routes  # noqa: F401
