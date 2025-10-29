# hestia_app/filters.py
from .core.status import nice_state
from .core.timefmt import short_dt, ago

def round2(value):
    try:
        return round(float(value), 2)
    except Exception:
        return value

def register_jinja_filters(app):
    """Register all custom Jinja filters on the given Flask app."""
    app.add_template_filter(nice_state, "nice_state")
    app.add_template_filter(short_dt,  "short_dt")
    app.add_template_filter(ago,       "ago")
    app.add_template_filter(round2,    "round2")
