# hestia_app/__init__.py
import os
from datetime import datetime, timezone
from flask import Flask, session

# ---- Optional logging: import if present, else no-op ----
try:
    from logging_cfg import setup_logging  # your custom logger (optional)
except Exception:  # pragma: no cover
    def setup_logging(*_args, **_kwargs):
        return None

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-me-in-env")

# Initialize logging (accept both signatures: with or without app)
try:
    setup_logging(app)  # type: ignore[arg-type]
except TypeError:
    setup_logging()     # type: ignore[misc]

# ---- Jinja filters: use your existing nice_state from core.status ----
try:
    from core.status import nice_state  # reuses your mapping
except Exception:
    def nice_state(v: str) -> str:
        return "—" if not v else str(v).title()

def _to_dt(x):
    if x is None or x == "":
        return None
    if isinstance(x, datetime):
        return x
    try:
        # allow ISO with Z
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

# ---- Global template context (user + HK shift flag) ----
@app.context_processor
def inject_globals():
    hk = session.get("hk_shift") or {}
    hk_active = bool(hk.get("started_at") and not hk.get("ended_at"))
    return {
        "HK_SHIFT_ACTIVE": hk_active,
        "user": session.get("user"),  # templates use user.role
    }

# ---- Routes (kept as module-level @app.route) ----
from . import routes  # noqa: E402,F401
