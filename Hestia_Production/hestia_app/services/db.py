# hestia_app/services/db.py
from __future__ import annotations
import sqlite3 as sql
from contextlib import suppress
from datetime import datetime
import time
import os
from urllib.parse import urlsplit


# ✅ FIX: use a relative import; do NOT import top-level "dsn"
from .dsn import dsn_with_params, is_supabase_pooler, IS_SUPABASE_POOLER, BASE_DATABASE_URL

from flask import current_app

# --- Supabase/Postgres setup (robust, lazy-init, with clear logs) ---
# Prefer env for runtime (Render), but your Config also exposes DATABASE_URL if you need it elsewhere.
DATABASE_URL = BASE_DATABASE_URL  # e.g. postgresql://...:6543/postgres?sslmode=require
DATABASE = os.getenv('DATABASE_PATH', 'hestia_V2.db')  # local fallback for dev
USE_PG = bool(DATABASE_URL)

# Try to import psycopg2; don't crash if missing (local SQLite dev may not need it)
pg = None
pg_pool = None
pg_extras = None
if USE_PG:
    try:
        import psycopg2 as pg
        import psycopg2.pool as pg_pool
        import psycopg2.extras as pg_extras
    except Exception as e:
        print(f"[BOOT] psycopg2 import failed: {e}", flush=True)

PG_POOL = None  # created lazily on first use

FALLBACK_DATABASE_URL = os.getenv('DATABASE_URL_DIRECT', '').strip()


def _init_pg_pool():
    """Create the global pool once. Keep pool tiny when using Supabase pgbouncer (6543)."""
    global PG_POOL
    if not USE_PG:
        return None
    if PG_POOL is not None:
        return PG_POOL
    if pg is None or pg_pool is None:
        raise RuntimeError("DATABASE_URL is set but psycopg2 isn't available (check requirements).")
    try:
        dsn = dsn_with_params(DATABASE_URL)
        p = urlsplit(dsn)
        masked = f"{p.scheme}://{p.hostname}:{p.port}{p.path}?{p.query}"
        print(f"[BOOT] DB target host={p.hostname} port={p.port} pooler={IS_SUPABASE_POOLER} DSN={masked}", flush=True)

        maxconn_default = '2' if IS_SUPABASE_POOLER else '5'
        maxconn = int(os.getenv('PG_POOL_MAX', maxconn_default))
        PG_POOL = pg_pool.SimpleConnectionPool(minconn=1, maxconn=maxconn, dsn=dsn)
        print(f"[BOOT] Postgres pool initialized (maxconn={maxconn}, pooler={IS_SUPABASE_POOLER}).", flush=True)
        return PG_POOL
    except Exception as e:
        print(f"[BOOT] Primary DSN failed: {e}", flush=True)
        if FALLBACK_DATABASE_URL:
            try:
                dsn_fb = dsn_with_params(FALLBACK_DATABASE_URL)
                pf = urlsplit(dsn_fb)
                print(f"[BOOT] Trying fallback host={pf.hostname} port={pf.port}", flush=True)
                PG_POOL = pg_pool.SimpleConnectionPool(minconn=1, maxconn=5, dsn=dsn_fb)
                print("[BOOT] Fallback Postgres pool initialized.", flush=True)
                return PG_POOL
            except Exception as e2:
                print(f"[BOOT] Fallback DSN failed: {e2}", flush=True)
        raise



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

def _db_conn_with_retry(tries: int = 3, backoff: float = 0.35):
    """Retry on transient pooler hiccups with exponential backoff."""
    last = None
    for i in range(tries):
        try:
            pool = _init_pg_pool()
            conn = pool.getconn()
            # quick ping to ensure it's alive (cheap and safe behind pgbouncer)
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return conn
        except Exception as e:
            last = e
            # if we got a conn but ping failed, close it before retrying
            with suppress(Exception):
                if 'conn' in locals():
                    PG_POOL.putconn(conn, close=True)
            time.sleep(backoff * (2 ** i))
    raise last

def using_pg() -> bool:
    return bool(current_app.config.get("DATABASE_URL"))

def db():
    """
    Get a DB connection:
      - Postgres (Supabase) when DATABASE_URL is set (with tiny retry)
      - SQLite local file otherwise
    """
    if USE_PG:
        return _db_conn_with_retry(tries=2)
    conn = sql.connect(DATABASE, check_same_thread=False)
    conn.row_factory = sql.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def _execute(conn, query, params=()):
    """Run a query on either backend. Converts '?' -> '%s' for Postgres."""
    if USE_PG:
        cur = conn.cursor(cursor_factory=pg_extras.RealDictCursor)
        cur.execute(query.replace('?', '%s'), params)
        return cur
    else:
        return conn.execute(query, params)

def fetchone(query, params=()):
    conn = db()
    try:
        if USE_PG:
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
        if USE_PG:
            try: PG_POOL.putconn(conn)
            except Exception: pass
        else:
            try: conn.close()
            except Exception: pass

def fetchall(query, params=()):
    conn = db()
    try:
        if USE_PG:
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
        if USE_PG:
            try: PG_POOL.putconn(conn)
            except Exception: pass
        else:
            try: conn.close()
            except Exception: pass

def execute(query, params=()):
    conn = db()
    try:
        if USE_PG:
            cur = _execute(conn, query, params)
            cur.close()
            conn.commit()
        else:
            with conn:
                _ = _execute(conn, query, params)
                conn.commit()
    finally:
        if USE_PG:
            try: PG_POOL.putconn(conn)
            except Exception: pass
        else:
            try: conn.close()
            except Exception: pass

def insert_and_get_id(query, params=()):
    """
    Run an INSERT and return the new primary key id on both backends.
    For Postgres, appends 'RETURNING id' if not already present.
    For SQLite, uses cursor.lastrowid.
    """
    conn = db()
    try:
        if USE_PG:
            sql_text = query
            if 'RETURNING' not in sql_text.upper():
                sql_text = sql_text.rstrip().rstrip(';') + ' RETURNING id'
            cur = _execute(conn, sql_text, params)
            row = cur.fetchone()
            cur.close()
            conn.commit()
            # RealDictCursor returns dict-like rows
            return row['id'] if isinstance(row, dict) else row[0]
        else:
            with conn:
                cur = _execute(conn, query, params)
                conn.commit()
                return cur.lastrowid
    finally:
        if USE_PG:
            try: PG_POOL.putconn(conn)
            except Exception: pass
        else:
            try: conn.close()
            except Exception: pass

