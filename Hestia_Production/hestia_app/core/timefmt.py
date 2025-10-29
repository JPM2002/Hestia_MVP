def register_jinja_filters(app):
    app.jinja_env.filters['round2'] = lambda x: round(x,2)
    app.jinja_env.filters['short_dt'] = lambda d: d
    app.jinja_env.filters['ago'] = lambda d: 'hace…'
