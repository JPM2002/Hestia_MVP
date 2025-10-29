from flask import Blueprint

# Match the same pattern you used elsewhere
bp = Blueprint(
    "pms",
    __name__,
    url_prefix="",
    template_folder="templates",
)

from . import routes  # noqa: E402,F401
