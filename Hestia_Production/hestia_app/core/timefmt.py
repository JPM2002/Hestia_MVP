# hestia_app/core/timefmt.py
from datetime import datetime, timezone

def register_jinja_filters(app):
    def round2(x):
        try:
            return round(float(x), 2)
        except Exception:
            return x

    def short_dt(dt):
        if not dt:
            return ""
        if isinstance(dt, (int, float)):
            dt = datetime.fromtimestamp(dt, tz=timezone.utc)
        # Example: 2025-10-28 14:05
        try:
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(dt)

    def ago(dt, now=None):
        """Return Spanish-like 'hace X' strings using ASCII only."""
        if not dt:
            return ""
        if isinstance(dt, (int, float)):
            dt = datetime.fromtimestamp(dt, tz=timezone.utc)

        # Align tz awareness
        if now is None:
            now = datetime.now(tz=dt.tzinfo) if dt.tzinfo else datetime.utcnow()

        delta = now - dt
        s = int(delta.total_seconds())
        if s < 60:
            return "hace segundos"
        m = s // 60
        if m < 60:
            return f"hace {m} min"
        h = m // 60
        if h < 24:
            return f"hace {h} h"
        d = h // 24
        if d < 30:
            return f"hace {d} d"
        mo = d // 30
        if mo < 12:
            return f"hace {mo} mes" + ("" if mo == 1 else "es")
        y = mo // 12
        # Use 'anio' instead of 'a\u00f1o' to keep ASCII-only
        return f"hace {y} anio" + ("" if y == 1 else "s")

    app.jinja_env.filters["round2"] = round2
    app.jinja_env.filters["short_dt"] = short_dt
    app.jinja_env.filters["ago"] = ago
