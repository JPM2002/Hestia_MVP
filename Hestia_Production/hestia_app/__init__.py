from flask import Flask
from .config import load_config
from .core.timefmt import register_jinja_filters
from .core.errors import register_error_handlers
from .core.device import register_device_hooks
from .core.rbac import init_rbac_helpers
from .core.shift import register_shift_context

from .blueprints.auth import bp as auth_bp
from .blueprints.dashboard import bp as dashboard_bp
from .blueprints.tickets import bp as tickets_bp