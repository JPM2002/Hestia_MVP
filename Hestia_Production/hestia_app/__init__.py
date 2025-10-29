# hestia_app/__init__.py
from flask import Flask, redirect, url_for, session, request

def create_app():
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # Config (SECRET_KEY must be present in Config)
    app.config.from_object("hestia_app.config.Config")
    app.config.setdefault("ENABLE_TECH_DEMO", False)

    # Jinja filters (optional)
    try:
        from .filters import register_filters
        register_filters(app)
    except Exception:
        pass

    # DB init (optional)
    try:
        from .services.db import init_app as db_init
        db_init(app)
    except Exception:
        pass

    # ✅ Device hooks (before/after request) via initializer
    try:
        from .core.device import init_device
        init_device(app)
    except Exception:
        pass

    # ✅ DB error handlers (optional but nice UX)
    try:
        from .core.errors import register_db_error_handlers
        register_db_error_handlers(app)
    except Exception:
        pass

    # If you prefer to centralize HK shift flags/endpoints:
    # from .core.shift import init_shift
    # init_shift(app)

    # --- Blueprints (auth FIRST so "/" routes correctly) ---
    from .blueprints.auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    from .blueprints.admin import bp as admin_bp
    from .blueprints.dashboard import bp as dashboard_bp
    from .blueprints.gerencia import bp as gerencia_bp
    from .blueprints.pms import bp as pms_bp
    from .blueprints.recepcion import bp as recepcion_bp
    from .blueprints.supervisor import bp as supervisor_bp
    from .blueprints.tecnico import bp as tecnico_bp
    from .blueprints.tickets import bp as tickets_bp

    app.register_blueprint(admin_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(gerencia_bp)
    app.register_blueprint(pms_bp)
    app.register_blueprint(recepcion_bp)
    app.register_blueprint(supervisor_bp)
    app.register_blueprint(tecnico_bp)
    app.register_blueprint(tickets_bp)

    # --- Require login globally (except public endpoints) ---
    @app.before_request
    def _require_login():
        ep = request.endpoint or ""
        public = {
            "static",            # Flask static files
            "auth.login",        # /login
            "auth.index",        # /
            "auth.demo_tecnico", # optional demo
            "healthz",           # health check
        }
        if ep in public or ep.startswith("static"):
            return
        if not session.get("user"):
            nxt = request.full_path if request.query_string else request.path
            return redirect(url_for("auth.login", next=nxt))

    # Health check for Render
    @app.get("/healthz")
    def healthz():
        return {"ok": True}, 200

    return app
