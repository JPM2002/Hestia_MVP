from __future__ import annotations
import sqlite3 as sql
from contextlib import suppress
from datetime import datetime
import time

from flask import current_app
from .dsn import is_supabase_pooler, dsn_with_params

# Optional psycopg2 import (only when DATABASE_URL is set)
try:
    import psycopg2 as pg
    import psycopg2.pool as pg_pool
    import psycopg2.extras as pg_extras
    from psycopg2 import OperationalError as PG_OperationalError
except Exception:  # local dev without psycopg2
    pg = pg_pool = pg_extras = None
    class PG_OperationalError(Exception):  # placeholder
        pass

PG_POOL = None  # created lazily

def _init_pg_pool():
    global PG_POOL
    if PG_POOL is not None:
        return PG_POOL

    cfg = current_app.config
    dsn_raw = cfg.get("DATABASE_URL")
    if not dsn_raw:
        return None

    if pg is None or pg_pool is None:
        raise RuntimeError("DATABASE_URL set but psycopg2 not installed. Add psycopg2-binary to requirements.")

    pooler = is_supabase_pooler(dsn_raw)
    dsn = dsn_with_params(dsn_raw, is_pooler=pooler, stmt_timeout_ms=cfg.get("PG_STMT_TIMEOUT_MS"))
    maxconn_default = 2 if pooler else 5
    maxconn = int(cfg.get("PG_POOL_MAX") or maxconn_default)
    PG_POOL = pg_pool.SimpleConnectionPool(minconn=1, maxconn=maxconn, dsn=dsn)
    current_app.logger.info(f"[DB] Postgres pool init (maxconn={maxconn}, pooler={pooler}).")
    return PG_POOL

def _pg_conn_with_retry(tries: int = 2, backoff: float = 0.35):
    last = None
    for i in range(tries):
        try:
            pool = _init_pg_pool()
            conn = pool.getconn()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return conn
        except Exception as e:
            last = e
            with suppress(Exception):
                if 'conn' in locals():
                    pool.putconn(conn, close=True)
            time.sleep(backoff * (2 ** i))
    raise last

def using_pg() -> bool:
    return bool(current_app.config.get("DATABASE_URL"))

def db():
    if using_pg():
        return _pg_conn_with_retry(tries=2)
    # SQLite
    path = current_app.config.get("DATABASE_PATH") or "hestia_V2.db"
    conn = sql.connect(path, check_same_thread=False)
    conn.row_factory = sql.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def _execute(conn, query, params=()):
    if using_pg():
        cur = conn.cursor(cursor_factory=pg_extras.RealDictCursor)
        cur.execute(query.replace('?', '%s'), params)
        return cur
    return conn.execute(query, params)

def fetchone(query, params=()):
    conn = db()
    try:
        if using_pg():
            cur = _execute(conn, query, params)
            row = cur.fetchone()
            cur.close()
            conn.commit()
            return row
        else:
            with conn:
                cur = _execute(conn, query, params)
                return cur.fetchone()
    finally:
        if using_pg():
            try: PG_POOL.putconn(conn)
            except Exception: pass
        else:
            with suppress(Exception):
                conn.close()

def fetchall(query, params=()):
    conn = db()
    try:
        if using_pg():
            cur = _execute(conn, query, params)
            rows = cur.fetchall()
            cur.close()
            conn.commit()
            return rows
        else:
            with conn:
                cur = _execute(conn, query, params)
                return cur.fetchall()
    finally:
        if using_pg():
            try: PG_POOL.putconn(conn)
            except Exception: pass
        else:
            with suppress(Exception):
                conn.close()

def execute(query, params=()):
    conn = db()
    try:
        if using_pg():
            cur = _execute(conn, query, params)
            cur.close()
            conn.commit()
        else:
            with conn:
                _ = _execute(conn, query, params)
                conn.commit()
    finally:
        if using_pg():
            try: PG_POOL.putconn(conn)
            except Exception: pass
        else:
            with suppress(Exception):
                conn.close()

def insert_and_get_id(query, params=()):
    conn = db()
    try:
        if using_pg():
            sql_text = query if "RETURNING" in query.upper() else query.rstrip().rstrip(';') + " RETURNING id"
            cur = _execute(conn, sql_text, params)
            row = cur.fetchone()
            cur.close(); conn.commit()
            return row["id"] if isinstance(row, dict) else row[0]
        else:
            with conn:
                cur = _execute(conn, query, params)
                conn.commit()
                return cur.lastrowid
    finally:
        if using_pg():
            try: PG_POOL.putconn(conn)
            except Exception: pass
        else:
            with suppress(Exception):
                conn.close()

def hp(password: str) -> str:
    import hashlib
    return hashlib.sha256(password.encode("utf-8")).hexdigest()
