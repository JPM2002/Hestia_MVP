# app/__init__.py
import os
from datetime import datetime
from flask import Flask, session

# App simple (sin factory) para que coincida con url_for en tus templates
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'change-me-in-env')

# ---------- Jinja filters & helpers ----------
# Usar el nice_state que ya tienes en hestia_app.core.status
try:
    from hestia_app.core.status import nice_state  # <- TU función
except Exception:
    # Fallback por si el import falla en local: devolver algo razonable
    def nice_state(value: str) -> str:
        return "—" if not value else str(value).title()

def _to_dt(obj):
    if obj is None or obj == "":
        return None
    if isinstance(obj, datetime):
        return obj
    try:
        # Soporta ISO con 'Z'
        return datetime.fromisoformat(str(obj).replace("Z", "+00:00"))
    except Exception:
        return None

def short_dt(value) -> str:
    """Formatea 'DD/MM HH:mm' o devuelve texto crudo si no es fecha."""
    dt = _to_dt(value)
    if not dt:
        return "-" if value in (None, "") else str(value)
    return dt.strftime("%d/%m %H:%M")

# Registra filtros en Jinja
app.jinja_env.filters["nice_state"] = nice_state
app.jinja_env.filters["short_dt"]  = short_dt

# ---------- Context: expone flag de turno HK a todas las plantillas ----------
@app.context_processor
def inject_flags():
    hk = session.get("hk_shift") or {}
    active = bool(hk.get("started_at") and not hk.get("ended_at"))
    return dict(HK_SHIFT_ACTIVE=active)

# Importa rutas al final para que exista 'app'
from . import routes  # noqa: E402,F401
