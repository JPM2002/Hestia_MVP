# hestia_app/__init__.py
import os
import pkgutil
import importlib
from flask import Flask
from flask import Blueprint  # for isinstance check
from .config import get_config
from .filters import register_jinja_filters  # make sure this exists

def create_app(env: str | None = None):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(get_config(env))

    # Jinja filters
    register_jinja_filters(app)

    # (Optional) if you added a context globals registrar:
    # from .context import register_template_globals
    # register_template_globals(app)

    # Auto-register blueprints under hestia_app/blueprints/*/routes.py
    _register_blueprints(app)

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
            # No routes.py in that package; skip
            continue

        # Accept common attribute names: bp or blueprint
        bp = getattr(routes, "bp", None) or getattr(routes, "blueprint", None)
        if isinstance(bp, Blueprint):
            app.register_blueprint(bp)
