# DNS help for dsn.py
# --- add for DSN normalization ---
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from db import DATABASE_URL

# --- DSN helpers & pooler detection ---
IS_SUPABASE_POOLER = bool(DATABASE_URL and "pooler.supabase.com" in DATABASE_URL)

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
    if IS_SUPABASE_POOLER:
        q.setdefault("keepalives", "1")
        q.setdefault("keepalives_idle", "30")
        q.setdefault("keepalives_interval", "10")
        q.setdefault("keepalives_count", "3")
        q.setdefault("target_session_attrs", "read-write")
        # Optional, if you want a server-side query timeout (ms):
        # (works even behind pgbouncer because it's a server GUC)
        if "PG_STMT_TIMEOUT_MS" in os.environ:
            q["options"] = f"-c statement_timeout={os.environ['PG_STMT_TIMEOUT_MS']}"

    if extra:
        q.update(extra)

    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))
