# hestia_app/__init__.py
from flask import Flask

# Optional logging setup
try:
    from .logging_cfg import setup_logging
except ImportError:
    def setup_logging(*args, **kwargs):
        pass

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")

    # Config
    app.config.from_object("hestia_app.config.Config")

    # Logging (opcional)
    try:
        setup_logging(app)
    except Exception:
        pass

    # Jinja filters (si tienes filters.register_filters)
    try:
        from .filters import register_filters
        register_filters(app)
    except Exception:
        pass

    # Blueprints
    from .blueprints.admin import bp as admin_bp
    from .blueprints.auth import bp as auth_bp
    from .blueprints.dashboard import bp as dash_bp
    from .blueprints.tickets import bp as tickets_bp
    from .blueprints.tecnico import bp as tecnico_bp

    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(dash_bp, url_prefix="/dashboard")
    app.register_blueprint(tickets_bp, url_prefix="/tickets")
    app.register_blueprint(tecnico_bp, url_prefix="/tecnico")

    return app
