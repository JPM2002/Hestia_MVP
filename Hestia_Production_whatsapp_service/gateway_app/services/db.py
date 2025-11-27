# gateway_app/services/db.py

"""
Simple DB helper with Postgres primary + SQLite fallback.

Usage pattern (synchronous, small gateway service):

    from gateway_app.services.db import execute, fetchone, fetchall, insert_and_get_id

This module expects:

    cfg.DATABASE_URL  (from gateway_app.config)

Typical values:

    - Postgres on Render:
        DATABASE_URL=postgres://user:pass@host:5432/dbname
      or
        DATABASE_URL=postgresql://user:pass@host:5432/dbname

    - SQLite (local dev):
        DATABASE_URL=sqlite:///./gateway.db
      or
        DATABASE_URL=./gateway.db  (path -> treated as SQLite file)

Design goals:

    - Prefer Postgres if URL scheme starts with "postgres".
    - If psycopg2 is unavailable or URL doesn't look Postgresy, use SQLite.
    - Keep API small and explicit: execute / fetchone / fetchall / insert_and_get_id.

This gateway is not high-throughput, so a simple connect-per-call design is fine.
If you ever need more throughput, you can add connection pooling for Postgres.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional

from gateway_app.config import cfg

logger = logging.getLogger(__name__)

# psycopg2 is optional; if missing we fall back to SQLite even for postgres-like URLs.
try:
    import psycopg2
    import psycopg2.extras
except Exception:  # psycopg2 is optional
    psycopg2 = None  # type: ignore[assignment]


# ---------- URL helpers ----------


def _is_postgres_url(url: str) -> bool:
    if not url:
        return False
    lower = url.lower()
    return lower.startswith("postgres://") or lower.startswith("postgresql://")


def _sqlite_path_from_url(url: str) -> str:
    """
    Convert DATABASE_URL into a filesystem path for SQLite.

    Accepts:
        - "sqlite:///./gateway.db" -> "./gateway.db"
        - "sqlite:////tmp/gateway.db" -> "/tmp/gateway.db"
        - "./gateway.db" -> "./gateway.db" (no scheme, treat as raw path)
    """
    if not url:
        return "./gateway.db"

    lower = url.lower()
    if lower.startswith("sqlite:///"):
        # relative or local path
        return url[10:]
    if lower.startswith("sqlite:////"):
        # absolute path
        return url[11:]
    # no explicit sqlite scheme -> treat as path
    return url


# ---------- Connection handling ----------


def _connect_postgres(dsn: str):
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is not installed; cannot use Postgres.")
    # Using DictCursor for ergonomic row access
    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.DictCursor)


def _connect_sqlite(path: str):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _get_connection():
    """
    Decide whether to connect to Postgres or SQLite based on DATABASE_URL.
    """
    url = cfg.DATABASE_URL or ""
    if _is_postgres_url(url) and psycopg2 is not None:
        logger.debug("Using Postgres connection for DATABASE_URL.")
        return _connect_postgres(url)

    # Fallback to SQLite
    sqlite_path = _sqlite_path_from_url(url or "./gateway.db")
    logger.debug("Using SQLite connection at %s", sqlite_path)
    return _connect_sqlite(sqlite_path)


@contextmanager
def _cursor(commit: bool = False):
    """
    Context manager yielding a DB cursor.

    Args:
        commit: Whether to commit the transaction on successful exit.

    Yields:
        (conn, cursor) pair.
    """
    conn = _get_connection()
    cur = conn.cursor()
    try:
        yield conn, cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


# ---------- Compatibility helpers for tickets.py / monolithic code ----------


def using_pg() -> bool:
    """
    Return True if we are configured to use Postgres (and psycopg2 is available),
    False if we are using SQLite.
    """
    url = cfg.DATABASE_URL or ""
    return psycopg2 is not None and _is_postgres_url(url)


def table_has_column(table_name: str, column_name: str) -> bool:
    """
    Check whether a given table has a given column.

    Used by create_ticket to decide whether optional guest_phone / guest_name
    columns exist. If this fails for any reason, we return False so the caller
    simply skips the optional UPDATE.
    """
    try:
        url = cfg.DATABASE_URL or ""
        use_postgres = _is_postgres_url(url) and psycopg2 is not None

        with _cursor(commit=False) as (_conn, cur):
            if use_postgres:
                cur.execute(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = %s AND column_name = %s
                    """,
                    (table_name, column_name),
                )
                return cur.fetchone() is not None
            else:
                # SQLite PRAGMA schema inspection
                cur.execute(f"PRAGMA table_info({table_name})")
                rows = cur.fetchall()
                for r in rows:
                    # sqlite3.Row -> mapping-like; "name" holds the column name
                    if dict(r).get("name") == column_name:
                        return True
                return False
    except Exception as e:
        logger.warning(
            "table_has_column(%s, %s) failed: %s", table_name, column_name, e
        )
        return False


def with_db_defaults(fn):
    """
    No-op decorator kept for compatibility with older monolithic code.
    Some legacy functions might be annotated with @with_db_defaults.
    """
    return fn


# ---------- Public helpers ----------


def execute(sql: str, params: Optional[Iterable[Any]] = None, *, commit: bool = False) -> None:
    """
    Execute a statement that does not need to return rows.

    Example:
        execute("UPDATE sessions SET state=%s WHERE wa_id=%s", [state, wa_id], commit=True)
    """
    logger.debug("DB execute: %s | params=%s", sql, params)
    with _cursor(commit=commit) as (_conn, cur):
        cur.execute(sql, tuple(params or []))


def fetchone(sql: str, params: Optional[Iterable[Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Execute a SELECT and return a single row or None.

    Row is returned as a dict-like object (for both Postgres and SQLite).
    """
    logger.debug("DB fetchone: %s | params=%s", sql, params)
    with _cursor(commit=False) as (_conn, cur):
        cur.execute(sql, tuple(params or []))
        row = cur.fetchone()
        if row is None:
            return None
        # psycopg2.extras.DictRow or sqlite3.Row both behave like mappings
        return dict(row)


def fetchall(sql: str, params: Optional[Iterable[Any]] = None) -> List[Dict[str, Any]]:
    """
    Execute a SELECT and return all rows as a list of dicts.
    """
    logger.debug("DB fetchall: %s | params=%s", sql, params)
    with _cursor(commit=False) as (_conn, cur):
        cur.execute(sql, tuple(params or []))
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def insert_and_get_id(sql: str, params: Optional[Iterable[Any]] = None) -> Any:
    """
    Insert a row and return its primary key.

    Behavior:

    - For Postgres:
        If the SQL already contains a RETURNING clause, it is used as-is.
        If not, we append "RETURNING id" automatically.

    - For SQLite:
        We rely on cursor.lastrowid and ignore any RETURNING clause.

    This makes it compatible with older monolithic code that called
    insert_and_get_id() with plain INSERT statements (no RETURNING) on Postgres.
    """
    logger.debug("DB insert_and_get_id: %s | params=%s", sql, params)
    url = cfg.DATABASE_URL or ""
    use_postgres = _is_postgres_url(url) and psycopg2 is not None

    effective_sql = sql
    if use_postgres:
        # If the caller didn't include RETURNING, add it.
        if "returning" not in sql.lower():
            effective_sql = sql.rstrip().rstrip(";") + " RETURNING id"

    with _cursor(commit=True) as (_conn, cur):
        cur.execute(effective_sql, tuple(params or []))

        if use_postgres:
            row = cur.fetchone()
            if not row:
                return None

            # Dict-like row
            if isinstance(row, dict):
                return row.get("id")
            try:
                return row["id"]
            except Exception:
                return row[0]
        else:
            # SQLite
            return getattr(cur, "lastrowid", None)
