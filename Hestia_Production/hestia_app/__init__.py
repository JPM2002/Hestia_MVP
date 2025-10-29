# hestia_app/__init__.py
from flask import Flask, redirect, url_for, session, request

def create_app():
    app = Flask(
        __name__,
        template_folder="templates",  # hestia_app/templates
        static_folder="static",       # hestia_app/static
    )

    # Load config (must include SECRET_KEY for sessions)
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

    # --- Blueprints ---
    # Register AUTH FIRST so "/" maps to auth.index (which redirects to login if not logged in)
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
            "auth.demo_tecnico", # demo route (optional)
            "healthz",           # health check
        }
        # Allow static/* and explicitly whitelisted endpoints
        if ep in public or ep.startswith("static"):
            return
        # Redirect unauthenticated users to login
        if not session.get("user"):
            nxt = request.full_path if request.query_string else request.path
            return redirect(url_for("auth.login", next=nxt))

    # Health check for Render
    @app.get("/healthz")
    def healthz():
        return {"ok": True}, 200

    return app
