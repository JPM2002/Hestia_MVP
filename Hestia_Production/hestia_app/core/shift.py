def register_shift_context(app):
    @app.context_processor
    def _ctx(): return dict(hk_shift_active=False)
