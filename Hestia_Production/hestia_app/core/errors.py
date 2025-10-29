def register_error_handlers(app):
    @app.errorhandler(500)
    def _e500(e): return ('server error', 500)
