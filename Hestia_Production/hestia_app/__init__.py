import os
from flask import Flask

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")

    # Config básica
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-me-in-env")
    app.config["ENABLE_TECH_DEMO"] = os.getenv("ENABLE_TECH_DEMO", "0") == "1"

    # Filtros Jinja (import relativo)
    try:
        from .filters import init_app as init_filters
        init_filters(app)
    except Exception:
        pass

    # Hooks de device detection (import relativo)
    try:
        from .core.device import init_app as init_device
        init_device(app)
    except Exception:
        pass

    # Blueprints (imports relativos a la ruta del paquete)
    from .blueprints.auth.routes import bp as auth_bp
    app.register_blueprint(auth_bp)

    try:
        from .blueprints.admin.routes import bp as admin_bp
        app.register_blueprint(admin_bp)
    except Exception:
        pass

    try:
        from .blueprints.dashboard.routes import bp as dashboard_bp
        app.register_blueprint(dashboard_bp)
    except Exception:
        pass

    try:
        from .blueprints.tickets.routes import bp as tickets_bp
        app.register_blueprint(tickets_bp)
    except Exception:
        pass

    @app.get("/healthz")
    def healthz():
        return "ok", 200

    return app
