from flask import Blueprint

# No url_prefix so your existing routes keep their exact paths
bp = Blueprint(
    "tickets",
    __name__,
    url_prefix="",
    template_folder="templates/tickets",  # ok even if the folder doesn't exist here
)

from . import routes  # noqa: E402,F401
