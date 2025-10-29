# hestia_app/__init__.py
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

    # 👇 DEBUG: imprime rutas al arrancar (se verá en los logs de Render)
    for rule in app.url_map.iter_rules():
        print("ROUTE:", rule, "→ endpoint:", rule.endpoint)
        # o si prefieres:
        # app.logger.info("ROUTE: %s → endpoint: %s", rule, rule.endpoint)

    return app
