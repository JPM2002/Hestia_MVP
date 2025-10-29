from .core.timefmt import nice_state, short_dt, ago, round2

def register_filters(app):
    app.jinja_env.filters["nice_state"] = nice_state
    app.jinja_env.filters["short_dt"]   = short_dt
    app.jinja_env.filters["ago"]        = ago
    app.jinja_env.filters["round2"]     = round2
