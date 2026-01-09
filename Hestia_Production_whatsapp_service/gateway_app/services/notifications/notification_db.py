"""
Servicio de Base de Datos para Notification Service

Reutiliza la misma lógica que gateway_app/services/db.py
Soporta PostgreSQL y SQLite con la misma interfaz.
"""

import logging
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional

from gateway_app.config import Config

logger = logging.getLogger(__name__)

# psycopg2 es opcional; si falta usamos SQLite
try:
    import psycopg2
    import psycopg2.extras
except Exception:
    psycopg2 = None


def _is_postgres_url(url: str) -> bool:
    """Detecta si la URL es de PostgreSQL"""
    if not url:
        return False
    lower = url.lower()
    return lower.startswith("postgres://") or lower.startswith("postgresql://")


def _sqlite_path_from_url(url: str) -> str:
    """Extrae el path de SQLite desde DATABASE_URL"""
    if not url:
        return "./hestia_V2.db"

    lower = url.lower()
    if lower.startswith("sqlite:///"):
        return url[10:]
    if lower.startswith("sqlite:////"):
        return url[11:]
    return url


def _connect_postgres(dsn: str):
    """Conecta a PostgreSQL"""
    if psycopg2 is None:
        raise RuntimeError("psycopg2 no está instalado; no se puede usar Postgres.")
    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.DictCursor)


def _connect_sqlite(path: str):
    """Conecta a SQLite"""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _get_connection():
    """Obtiene conexión según DATABASE_URL"""
    url = getattr(Config, 'DATABASE_URL', '') or ""
    if _is_postgres_url(url) and psycopg2 is not None:
        logger.debug("Usando conexión PostgreSQL")
        return _connect_postgres(url)

    sqlite_path = _sqlite_path_from_url(url or "./hestia_V2.db")
    logger.debug(f"Usando conexión SQLite en {sqlite_path}")
    return _connect_sqlite(sqlite_path)


@contextmanager
def _cursor(commit: bool = False):
    """Context manager que provee cursor de BD"""
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


def using_pg() -> bool:
    """Retorna True si estamos usando PostgreSQL"""
    url = getattr(Config, 'DATABASE_URL', '') or ""
    return psycopg2 is not None and _is_postgres_url(url)


def execute(sql: str, params: Optional[Iterable[Any]] = None, *, commit: bool = False) -> None:
    """
    Ejecuta un statement que no retorna filas.

    Ejemplo:
        execute("UPDATE tickets SET notified=? WHERE id=?", [True, 123], commit=True)
    """
    logger.debug(f"DB execute: {sql} | params={params}")
    with _cursor(commit=commit) as (_conn, cur):
        cur.execute(sql, tuple(params or []))


def fetchone(sql: str, params: Optional[Iterable[Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Ejecuta un SELECT y retorna una fila o None.

    Retorna un dict con los campos de la fila.
    """
    logger.debug(f"DB fetchone: {sql} | params={params}")
    with _cursor(commit=False) as (_conn, cur):
        cur.execute(sql, tuple(params or []))
        row = cur.fetchone()
        if row is None:
            return None
        return dict(row)


def fetchall(sql: str, params: Optional[Iterable[Any]] = None) -> List[Dict[str, Any]]:
    """
    Ejecuta un SELECT y retorna todas las filas como lista de dicts.
    """
    logger.debug(f"DB fetchall: {sql} | params={params}")
    with _cursor(commit=False) as (_conn, cur):
        cur.execute(sql, tuple(params or []))
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def insert_and_get_id(sql: str, params: Optional[Iterable[Any]] = None) -> Any:
    """
    Inserta una fila y retorna el ID generado.

    Para Postgres: usa RETURNING id
    Para SQLite: usa cursor.lastrowid
    """
    logger.debug(f"DB insert_and_get_id: {sql} | params={params}")
    url = getattr(Config, 'DATABASE_URL', '') or ""
    use_postgres = _is_postgres_url(url) and psycopg2 is not None

    effective_sql = sql
    if use_postgres:
        if "returning" not in sql.lower():
            effective_sql = sql.rstrip().rstrip(";") + " RETURNING id"

    with _cursor(commit=True) as (_conn, cur):
        cur.execute(effective_sql, tuple(params or []))

        if use_postgres:
            row = cur.fetchone()
            if not row:
                return None
            if isinstance(row, dict):
                return row.get("id")
            try:
                return row["id"]
            except Exception:
                return row[0]
        else:
            return getattr(cur, "lastrowid", None)
