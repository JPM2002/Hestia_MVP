import os, pkgutil, importlib
from flask import Flask, Blueprint, redirect, url_for
from .config import get_config
from .filters import register_jinja_filters

def create_app(env: str | None = None):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(get_config(env or os.getenv("FLASK_ENV") or "production"))

    register_jinja_filters(app)
    _register_blueprints(app)

    @app.get("/")
    def root():
        return redirect(url_for("auth.login"))

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}, 200

    # Útil para depurar endpoints en logs
    if app.config.get("DEBUG") or os.getenv("PRINT_ROUTES") == "1":
        for rule in app.url_map.iter_rules():
            print("ROUTE:", rule, "→ endpoint:", rule.endpoint)

    return app

def _register_blueprints(app: Flask) -> None:
    base_pkg = "hestia_app.blueprints"
    base_path = os.path.join(os.path.dirname(__file__), "blueprints")
    if not os.path.isdir(base_path):
        return
    for _finder, pkg_name, is_pkg in pkgutil.iter_modules([base_path]):
        if not is_pkg:
            continue
        mod_name = f"{base_pkg}.{pkg_name}.routes"
        try:
            routes = importlib.import_module(mod_name)
        except ModuleNotFoundError:
            continue
        bp = getattr(routes, "bp", None) or getattr(routes, "blueprint", None)
        if isinstance(bp, Blueprint):
            app.register_blueprint(bp)
