# gateway_app/blueprints/webhook/__init__.py
from flask import Blueprint

bp = Blueprint("webhook", __name__, url_prefix="/webhook")

from . import routes  # noqa
