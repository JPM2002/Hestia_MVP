# hestia_app/__init__.py
from flask import Flask
from .config import get_config
from .filters import register_jinja_filters
from .logging_cfg import configure_logging  # optional
# If you already have error handlers in core/errors.py, import and use:
# from .core.errors import register_error_handlers

# Import blueprints that already have routes
from .blueprints.tickets import tickets_bp
from .blueprints.admin import admin_bp
from .blueprints.auth import auth_bp
from .blueprints.dashboard import dashboard_bp

def create_app(env: str | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # Config
    app.config.from_object(get_config(env))

    # Logging (optional)
    try:
        configure_logging(app)
    except Exception:
        pass

    # Jinja filters
    register_jinja_filters(app)

    # Blueprints (only register ones that have routes/templates now)
    app.register_blueprint(tickets_bp,   url_prefix="/tickets")
    app.register_blueprint(admin_bp,     url_prefix="/admin")
    app.register_blueprint(auth_bp,      url_prefix="/auth")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboards")

    # Error handlers (uncomment if you have them)
    # register_error_handlers(app)

    return app
