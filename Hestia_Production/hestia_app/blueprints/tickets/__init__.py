# app/__init__.py
import os
from datetime import datetime
from flask import Flask, session

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-me-in-env")

# ----- Jinja filters (reusar tu nice_state) -----
try:
    from hestia_app.core.status import nice_state  # tu función
except Exception:
    def nice_state(v: str) -> str:
        return "—" if not v else str(v).title()

def _to_dt(x):
    if x is None or x == "": return None
    if isinstance(x, datetime): return x
    try:
        return datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except Exception:
        return None

def short_dt(v) -> str:
    dt = _to_dt(v)
    if not dt:
        return "-" if v in (None, "") else str(v)
    return dt.strftime("%d/%m %H:%M")

app.jinja_env.filters["nice_state"] = nice_state
app.jinja_env.filters["short_dt"]  = short_dt

# ----- Contexto global para templates -----
@app.context_processor
def inject_globals():
    hk = session.get("hk_shift") or {}
    hk_active = bool(hk.get("started_at") and not hk.get("ended_at"))
    return {
        "HK_SHIFT_ACTIVE": hk_active,
        "user": session.get("user"),  # plantillas usan `user.role`
    }

# Importa rutas al final
from . import routes  # noqa: E402,F401
