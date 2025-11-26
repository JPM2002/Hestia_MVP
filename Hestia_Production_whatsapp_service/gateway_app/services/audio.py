# gateway_app/services/db.py
"""
Database helper layer with PostgreSQL + SQLite fallback.

Goals:
- Use DATABASE_URL from config.
- If it's a PostgreSQL URL (postgres:// or postgresql://) and psycopg2 is installed,
  use PostgreSQL.
- Otherwise, fall back to SQLite using a local file.
- Provide small helper functions:
    - using_pg()
    - execute(sql, params)
    - fetchone(sql, params)
    - fetchall(sql, params)
    - insert_and_get_id(sql, params)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterable, Optional, Sequence

import sqlite3 as sqlite

from gateway_app.config import cfg

logger = logging.getLogger(__name__)

# Optional PostgreSQL support
pg = None
pg_extras = None
try:
    import psycopg2 as pg
    import psycopg2.extras as pg_extras
except Exception:  # psycopg2 is optional
    pg = None
    pg_extras = None


_DB_URL = cfg.DATABASE_URL or ""
_DEFAULT_SQLITE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "gateway.db",
)


def _is_pg_dsn(dsn: str) -> bool:
    if not dsn:
        return False
    dsn_lower = dsn.lower()
    return dsn_lower.startswith("postgres://") or dsn_lower.startswith("postgresql://")


_USING_PG = _is_pg_dsn(_DB_URL) and pg is not None


def using_pg() -> bool:
    """Return True if we are using PostgreSQL, False if using SQLite."""
    return _USING_PG


def _sqlite_path_from_url(dsn: str) -> str:
    """
    Convert a sqlite URL (like sqlite:///path/to/db.sqlite3) or bare path
    into a filesystem path.
    """
    if not dsn:
        return _DEFAULT_SQLITE_PATH

    if dsn.startswith("sqlite:///"):
        return dsn.replace("sqlite:///", "", 1)
    if dsn.startswith("sqlite://"):
        # handle sqlite://relative/path.db
        return dsn.replace("sqlite://", "", 1)

    # If it doesn't look like a URL, treat as plain path.
    return dsn


_SQLITE_PATH = _sqlite_path_from_url(_DB_URL) if not _USING_PG else None


def _pg_connect():
    if not pg:
        raise RuntimeError("psycopg2 is not installed but PostgreSQL DSN was provided.")
    if not _DB_URL:
        raise RuntimeError("DATABASE_URL is empty; cannot connect to PostgreSQL.")
    return pg.connect(_DB_URL)


def _sqlite_connect():
    path = _SQLITE_PATH or _DEFAULT_SQLITE_PATH
    conn = sqlite.connect(
        path,
        detect_types=sqlite.PARSE_DECLTYPES | sqlite.PARSE_COLNAMES,
        check_same_thread=False,
    )
    return conn


def _get_conn_and_cursor(dict_cursor: bool = False):
    """
    Internal helper returning (conn, cursor).

    - For PostgreSQL + dict_cursor=True → RealDictCursor.
    - For SQLite + dict_cursor=True → row_factory = sqlite.Row.
    """
    if using_pg():
        conn = _pg_connect()
        if dict_cursor and pg_extras:
            cur = conn.cursor(cursor_factory=pg_extras.RealDictCursor)
        else:
            cur = conn.cursor()
        return conn, cur

    # SQLite
    conn = _sqlite_connect()
    if dict_cursor:
        conn.row_factory = sqlite.Row
        cur = conn.cursor()
    else:
        cur = conn.cursor()
    return conn, cur


# ------------------- Public helpers -------------------


def execute(
    sql: str,
    params: Optional[Sequence[Any]] = None,
    *,
    commit: bool = True,
) -> int:
    """
    Execute a statement (INSERT/UPDATE/DELETE/DDL). Returns rowcount.

    For SELECT queries prefer fetchone/fetchall.
    """
    params = params or ()
    logger.debug("DB execute", extra={"sql": sql, "params": params})

    conn, cur = _get_conn_and_cursor(dict_cursor=False)
    try:
        cur.execute(sql, params)
        if commit:
            conn.commit()
        return cur.rowcount
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def fetchone(
    sql: str,
    params: Optional[Sequence[Any]] = None,
) -> Optional[dict]:
    """
    Execute a SELECT and return a single row as dict-like (or None).

    For SQLite, this will be a sqlite.Row (indexable by column name).
    For PostgreSQL, a psycopg2 RealDictRow if psycopg2.extras is available.
    """
    params = params or ()
    logger.debug("DB fetchone", extra={"sql": sql, "params": params})

    conn, cur = _get_conn_and_cursor(dict_cursor=True)
    try:
        cur.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return None
        # Convert sqlite.Row / RealDictRow to plain dict to be safe:
        return dict(row)
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def fetchall(
    sql: str,
    params: Optional[Sequence[Any]] = None,
) -> list[dict]:
    """
    Execute a SELECT and return all rows as list of dict.
    """
    params = params or ()
    logger.debug("DB fetchall", extra={"sql": sql, "params": params})

    conn, cur = _get_conn_and_cursor(dict_cursor=True)
    try:
        cur.execute(sql, params)
        rows = cur.fetchall() or []
        return [dict(r) for r in rows]
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def insert_and_get_id(
    sql: str,
    params: Optional[Sequence[Any]] = None,
) -> Any:
    """
    Execute an INSERT and return the new primary key.

    PostgreSQL:
        - Your SQL *may* contain 'RETURNING id' (or similar); if it does,
          we will fetch that and return it.
        - If not, we will use cursor.lastrowid (usually None in psycopg2),
          so it's recommended to use RETURNING for PostgreSQL.

    SQLite:
        - Uses cursor.lastrowid.
    """
    params = params or ()
    logger.debug("DB insert_and_get_id", extra={"sql": sql, "params": params})

    conn, cur = _get_conn_and_cursor(dict_cursor=False)
    try:
        cur.execute(sql, params)

        returned_id = None
        try:
            row = cur.fetchone()
            if row is not None:
                returned_id = row[0]
        except Exception:
            # No RETURNING clause
            returned_id = None

        conn.commit()

        if returned_id is not None:
            return returned_id

        # Fallback for SQLite or non-RETURNING inserts
        return getattr(cur, "lastrowid", None)
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
