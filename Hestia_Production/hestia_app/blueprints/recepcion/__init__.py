from flask import Blueprint

# Keep paths exactly the same (no prefix). Name is "recepcion".
bp = Blueprint(
    "recepcion",
    __name__,
    url_prefix="",
    template_folder="templates",
)

from . import routes  # noqa: E402,F401
