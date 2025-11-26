# gateway_app/services/dsn.py
"""
Small helpers for manipulating DSN / URL query parameters.

Typical use:
- Ensure required parameters (e.g. sslmode=require) are present in a DB URL.
- Add or override arbitrary query parameters in a URL.

These utilities are generic and can be reused for DATABASE_URL or any other URL.
"""

from __future__ import annotations

from typing import Mapping
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


def _merge_query(original_query: str, extra: Mapping[str, str]) -> str:
    """
    Merge `extra` parameters into an existing query string.

    - Existing keys are overridden by values from `extra`.
    - Keys with None values in `extra` are ignored.
    """
    params = dict(parse_qsl(original_query, keep_blank_values=True))

    for k, v in extra.items():
        if v is None:
            continue
        params[str(k)] = str(v)

    return urlencode(params)


def add_query_params(url: str, extra: Mapping[str, str]) -> str:
    """
    Return `url` with the query parameters in `extra` added/overridden.

    Example:
        add_query_params(
            "postgres://user:pass@host/db?sslmode=require",
            {"connect_timeout": "5"},
        )
    """
    if not url:
        return url

    parts = urlsplit(url)
    new_query = _merge_query(parts.query, extra)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, new_query, parts.fragment)
    )


def with_db_defaults(dsn: str) -> str:
    """
    Ensure sensible default parameters for database URLs.

    Currently:
    - For postgres:// / postgresql:// URLs, ensure sslmode=require if not set.

    You can call this before using the DSN in your DB layer, e.g.:

        from gateway_app.services.dsn import with_db_defaults
        normalized = with_db_defaults(cfg.DATABASE_URL)
    """
    if not dsn:
        return dsn

    lower = dsn.lower()
    if not (lower.startswith("postgres://") or lower.startswith("postgresql://")):
        return dsn

    parts = urlsplit(dsn)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))

    # Only set defaults if not already present
    params.setdefault("sslmode", "require")

    new_query = urlencode(params)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, new_query, parts.fragment)
    )
