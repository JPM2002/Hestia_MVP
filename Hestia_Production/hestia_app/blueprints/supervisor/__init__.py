from flask import Blueprint

# Keep URLs unchanged (no prefix)
bp = Blueprint(
    "supervisor",
    __name__,
    url_prefix="",
    template_folder="templates",
)

from . import routes  # noqa: E402,F401
