from flask import Blueprint

# No url_prefix so your paths remain exactly:
# /api/gerencia/summary, /api/gerencia/sin_asignar, /api/gerencia/performance
bp = Blueprint(
    "gerencia",
    __name__,
    url_prefix="",
    template_folder="templates",
)

from . import routes  # noqa: E402,F401
