# hestia_app/services/dsn.py
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import os


# Single source of truth for the base DSN: read from environment
# (Render → Environment → DATABASE_URL)
BASE_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

def is_supabase_pooler(dsn: str) -> bool:
    if not dsn:
        return False
    host = urlsplit(dsn).hostname or ""
    return host.endswith("pooler.supabase.com")

# Public constant for quick checks elsewhere
IS_SUPABASE_POOLER = is_supabase_pooler(BASE_DATABASE_URL)

def _dsn_with_params(dsn: str, extra: dict | None = None) -> str:
    """
    Ensure sslmode/connect_timeout exist in the DSN query string and,
    when using Supabase pooler (pgbouncer on 6543), add TCP keepalives
    to survive brief network hiccups.
    """
    if not dsn:
        return dsn
    parts = urlsplit(dsn)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))

    # Always enforce SSL + short connect timeout
    q.setdefault("sslmode", "require")
    q.setdefault("connect_timeout", "5")  # seconds

    # For pooler, add libpq keepalives and mark read-write target
    if is_supabase_pooler(dsn):
        q.setdefault("keepalives", "1")
        q.setdefault("keepalives_idle", "30")
        q.setdefault("keepalives_interval", "10")
        q.setdefault("keepalives_count", "3")
        q.setdefault("target_session_attrs", "read-write")
        # Optional server-side statement timeout (ms)
        if "PG_STMT_TIMEOUT_MS" in os.environ:
            q["options"] = f"-c statement_timeout={os.environ['PG_STMT_TIMEOUT_MS']}"

    if extra:
        q.update(extra)

    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))

# Public helper with the expected name (db.py imports this)
def dsn_with_params(dsn: str, extra: dict | None = None) -> str:
    return _dsn_with_params(dsn, extra)
