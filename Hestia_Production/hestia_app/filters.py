
from datetime import datetime, timezone
from hestia_app.core.status import ESTADO_NICE

def _to_dt(x):
    if not x:
        return None
    if isinstance(x, datetime):
        return x
    try:
        # tolera strings sqlite/pg
        return datetime.fromisoformat(str(x))
    except Exception:
        return None

def nice_state(value: str) -> str:
    if not value:
        return ""
    return ESTADO_NICE.get(value.upper(), value.replace("_", " ").title())

def short_dt(value) -> str:
    """
    Devuelve HH:MM si es hoy; 'DD/MM HH:MM' si es este año; de lo contrario 'DD/MM/YYYY'.
    """
    dt = _to_dt(value)
    if not dt:
        return ""
    now = datetime.now()
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    if dt.year == now.year:
        return dt.strftime("%d/%m %H:%M")
    return dt.strftime("%d/%m/%Y")

def ago(value) -> str:
    """
    'hace 5 min', 'hace 2 h', 'ayer', 'hace 3 d'
    """
    dt = _to_dt(value)
    if not dt:
        return ""
    now = datetime.now(timezone.utc).astimezone() if dt.tzinfo else datetime.now()
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
    if d == 1:
        return "ayer"
    return f"hace {d} d"

def round2(value):
    try:
        return f"{float(value):.2f}"
    except Exception:
        return value

# Registrar filtros en Jinja
app.jinja_env.filters["nice_state"] = nice_state
app.jinja_env.filters["short_dt"]   = short_dt
app.jinja_env.filters["ago"]        = ago
app.jinja_env.filters["round2"]     = round2