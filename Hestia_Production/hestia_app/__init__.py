# hestia_app/__init__.py
import os
import pkgutil, importlib
from flask import Flask, Blueprint, redirect, url_for   # ← NEW: redirect, url_for
from .config import get_config
from .filters import register_jinja_filters

def create_app(env: str | None = None):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(get_config(env or os.getenv("FLASK_ENV") or "production"))

    # Registrar filtros Jinja DESPUÉS de crear la app
    register_jinja_filters(app)

    # Auto-registrar blueprints: hestia_app/blueprints/*/routes.py con 'bp'
    _register_blueprints(app)

    # ← NEW: raíz redirige al login del blueprint 'auth'
    @app.get("/")
    def root():
        return redirect(url_for("auth.login"))

    # ← NEW opcional: healthcheck simple para Render/monitoreo
    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}, 200

    return app


def _register_blueprints(app: Flask) -> None:
    base_pkg = "hestia_app.blueprints"
    base_path = os.path.join(os.path.dirname(__file__), "blueprints")
    if not os.path.isdir(base_path):
        return

    for _finder, pkg_name, is_pkg in pkgutil.iter_modules([base_path]):
        if not is_pkg:
            continue

        # Espera un módulo routes.py por blueprint: hestia_app/blueprints/<pkg_name>/routes.py
        mod_name = f"{base_pkg}.{pkg_name}.routes"
        try:
            routes = importlib.import_module(mod_name)
        except ModuleNotFoundError:
            continue

        # Debe existir 'bp' (o 'blueprint') en el módulo routes.py
        bp = getattr(routes, "bp", None) or getattr(routes, "blueprint", None)
        if isinstance(bp, Blueprint):
            app.register_blueprint(bp)
