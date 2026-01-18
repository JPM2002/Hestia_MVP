from flask import Blueprint

# Metrics blueprint
bp = Blueprint(
    "metrics",
    __name__,
    url_prefix="",
)

from . import routes  
