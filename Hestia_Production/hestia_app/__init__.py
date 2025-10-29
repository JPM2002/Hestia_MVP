import os
from flask import Flask

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")

    # Config básica
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-me-in-env")
    app.config["ENABLE_TECH_DEMO"] = os.getenv("ENABLE_TECH_DEMO", "0") == "1"

    # Filtros Jinja
    try:
        from filters import init_app as init_filters
        init_filters(app)
    except Exception:
        pass

    # Hooks de device detection (si los tienes en core/device.py)
    try:
        from core.device import init_app as init_device
        init_device(app)
    except Exception:
        pass

    # Blueprints
    from blueprints.auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    # Registra también el resto (si ya existen):
    try:
        from blueprints.admin import bp as admin_bp
        app.register_blueprint(admin_bp)
    except Exception:
        pass

    try:
        from blueprints.dashboard import bp as dashboard_bp
        app.register_blueprint(dashboard_bp)
    except Exception:
        pass

    try:
        from blueprints.tickets import bp as tickets_bp
        app.register_blueprint(tickets_bp)
    except Exception:
        pass

    @app.get("/healthz")
    def healthz():
        return "ok", 200

    return app
