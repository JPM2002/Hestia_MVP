from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

def is_supabase_pooler(dsn: str | None) -> bool:
    return bool(dsn and "pooler.supabase.com" in dsn)

def dsn_with_params(dsn: str | None, *, is_pooler: bool, stmt_timeout_ms: str | None) -> str | None:
    if not dsn:
        return dsn
    parts = urlsplit(dsn)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q.setdefault("sslmode", "require")
    q.setdefault("connect_timeout", "5")
    if is_pooler:
        q.setdefault("keepalives", "1")
        q.setdefault("keepalives_idle", "30")
        q.setdefault("keepalives_interval", "10")
        q.setdefault("keepalives_count", "3")
        q.setdefault("target_session_attrs", "read-write")
        if stmt_timeout_ms:
            q["options"] = f"-c statement_timeout={stmt_timeout_ms}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))
