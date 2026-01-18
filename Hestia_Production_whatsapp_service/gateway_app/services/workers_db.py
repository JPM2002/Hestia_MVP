"""
Consultas de workers desde Supabase.
"""
import logging
from typing import List, Dict, Any, Optional

from gateway_app.services.db import fetchall, fetchone, execute, using_pg

import os
from gateway_app.services.db import execute

import re
import unicodedata

logger = logging.getLogger(__name__)

def normalizar_area(area: str) -> str:
    a = (area or "").strip().upper()
    if a in ("MANTENCION", "MANTENCIÓN"):
        return "MANTENIMIENTO"
    if a in ("AREAS COMUNES", "ÁREAS COMUNES", "AREAS_COMUNES", "AC"):
        return "AREAS_COMUNES"
    if a == "HK":
        return "HOUSEKEEPING"
    return a or "HOUSEKEEPING"

def _normalize_phone(phone: str) -> str:
    # deja solo dígitos (ajusta si tú guardas con '+')
    return "".join(ch for ch in (phone or "").strip() if ch.isdigit())

def _norm(s: str) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")  # quita tildes
    s = re.sub(r"\s+", " ", s)
    return s

def activar_turno_por_telefono(phone: str) -> bool:
    if not using_pg():
        logger.warning("Turno no activado: no hay DATABASE_URL (modo SQLite).")
        return False

    phone_n = _normalize_phone(phone)
    if not phone_n:
        return False

    row = fetchone(
        """
        UPDATE public.users
        SET turno_activo = ?,
            turno_updated_at = now()
        WHERE telefono = ?
        RETURNING id;
        """,
        (True, phone_n),
    )

    if row:
        logger.info("✅ Turno activado: telefono=%s user_id=%s", phone_n, row["id"])
        return True

    logger.warning("⚠️ No se activó turno: no existe user con telefono=%s", phone_n)
    return False

def desactivar_turno_por_telefono(phone: str) -> bool:
    phone_n = _normalize_phone(phone)
    if not phone_n:
        return False

    execute(
        "UPDATE public.users SET turno_activo = ?, turno_updated_at = now() WHERE telefono = ?",
        (False, phone_n),
    )
    return True



def _get_pg_conn():
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL no está configurada")

    # Intentar psycopg2 primero, fallback a psycopg (v3).
    try:
        import psycopg2  # type: ignore
        return psycopg2.connect(dsn, sslmode="require")
    except Exception:
        try:
            import psycopg  # type: ignore
            return psycopg.connect(dsn, sslmode="require")
        except Exception as e:
            raise RuntimeError("No hay driver Postgres (psycopg2/psycopg)") from e


def obtener_runtime_sessions_por_telefonos(phones: list[str]) -> dict[str, dict]:
    """
    Devuelve phone -> {turno_activo, ocupada, pausada, area} desde runtime_sessions.
    Nunca debe botar la app: si falla, devuelve {}.
    """
    phones = [str(p).strip() for p in (phones or []) if p]
    if not phones:
        return {}

    sql = """
      SELECT
        phone,
        COALESCE((data->>'turno_activo')::boolean, NULL) AS turno_activo,
        COALESCE((data->>'ocupada')::boolean, NULL)      AS ocupada,
        COALESCE((data->>'pausada')::boolean, NULL)      AS pausada,
        NULLIF(UPPER(data->>'area'), '')                 AS area
      FROM runtime_sessions
      WHERE phone = ANY(%s)
    """

    try:
        conn = _get_pg_conn()
        try:
            cur = conn.cursor()
            cur.execute(sql, (phones,))
            rows = cur.fetchall()
            cur.close()
        finally:
            conn.close()

        out: dict[str, dict] = {}
        for phone, turno_activo, ocupada, pausada, area in rows:
            out[str(phone)] = {
                "turno_activo": turno_activo,  # puede venir None
                "ocupada": ocupada,
                "pausada": pausada,
                "area": area,
            }
        return out
    except Exception:
        logger.exception("Error leyendo runtime_sessions; devolviendo {}")
        return {}

logger = logging.getLogger(__name__)

def obtener_todos_workers() -> List[Dict[str, Any]]:
    """
    Obtiene todos los trabajadores activos.
    Incluye turno_activo desde users (fuente de verdad).
    """
    sql = """
        SELECT 
            id,
            username as nombre_completo,
            telefono,
            area,
            activo,
            turno_activo
        FROM public.users
        WHERE activo = true
        AND area IN ('HOUSEKEEPING', 'MANTENCION', 'MANTENIMIENTO', 'AREAS_COMUNES')
        ORDER BY username
    """

    try:
        workers = fetchall(sql)

        # Enriquecer con runtime_sessions SOLO para flags efímeros (no turno)
        phones = [w.get("telefono") for w in workers if w.get("telefono")]
        sessions = obtener_runtime_sessions_por_telefonos(phones) or {}  # <- blindaje

        for w in workers:
            phone = w.get("telefono")
            data = (sessions.get(phone, {}) or {})

            # ✅ Turno desde BD
            w["turno_activo"] = bool(w.get("turno_activo", False))

            # opcional: estado efímero desde runtime
            w["pausada"] = bool(data.get("pausada", False))
            w["ocupada"] = bool(data.get("ocupada", False))

            # Área normalizada
            w["area"] = normalizar_area(w.get("area") or data.get("area") or "HOUSEKEEPING")

        logger.info(
            f"👥 {len(workers)} workers; turno_activo={sum(1 for w in workers if w.get('turno_activo'))}; "
            f"areas_sample={[w.get('area') for w in workers[:5]]}"
        )
        return workers

    except Exception as e:
        logger.exception(f"❌ Error obteniendo workers: {e}")
        return []


def buscar_worker_por_nombre(nombre: str) -> Optional[Dict[str, Any]]:
    """
    Busca un worker por nombre (case-insensitive + sin tildes).
    Retorna el mejor match (no necesariamente el primero alfabético).
    """
    nombre_norm = _norm(nombre)
    if not nombre_norm:
        return None

    sql = """
        SELECT 
            id,
            username as nombre_completo,
            telefono,
            area,
            activo,
            turno_activo
        FROM public.users
        WHERE activo = true
        AND area IN ('HOUSEKEEPING', 'MANTENCION', 'MANTENIMIENTO', 'AREAS_COMUNES')
        AND LOWER(username) LIKE LOWER(?)
        LIMIT 1
    """

    try:
        workers = fetchall(sql, []) or []

        # Filtrar candidatos por nombre normalizado
        candidatos: List[Dict[str, Any]] = []
        for w in workers:
            w_norm = _norm(w.get("nombre_completo") or "")
            if nombre_norm in w_norm:
                candidatos.append(w)

        if not candidatos:
            logger.info(f"👥 0 workers encontrados con '{nombre}'")
            return None

        # Ranking: exact match > startswith > contains
        def score(w: Dict[str, Any]) -> int:
            w_norm = _norm(w.get("nombre_completo") or "")
            if w_norm == nombre_norm:
                return 3
            if w_norm.startswith(nombre_norm):
                return 2
            return 1

        candidatos.sort(key=lambda w: (score(w), (w.get("nombre_completo") or "").lower()), reverse=True)
        elegido = candidatos[0]

        logger.info(f"✅ Worker encontrado: {elegido.get('nombre_completo')}")
        return elegido

    except Exception as e:
        logger.exception(f"❌ Error buscando worker: {e}")
        return None


def buscar_workers_por_nombre(nombre: str) -> List[Dict[str, Any]]:
    """
    Busca múltiples workers que coincidan con el nombre (match sin tildes).
    """
    nombre_norm = _norm(nombre)
    if not nombre_norm:
        return []

    # OJO: como vamos a filtrar "accent-insensitive" en Python,
    # no usamos LIKE (?) en SQL para no depender de parámetros.
    sql = """
        SELECT 
            id,
            username as nombre_completo,
            telefono,
            area,
            activo,
            turno_activo
        FROM public.users
        WHERE activo = true
        AND area IN ('HOUSEKEEPING', 'MANTENCION', 'MANTENIMIENTO', 'AREAS_COMUNES')
        ORDER BY username
    """

    try:
        # 1) Traemos candidatos (activos + áreas válidas)
        workers = fetchall(sql)  # <- sin params

        # 2) Filtramos “accent-insensitive” en Python
        matches = []
        for w in (workers or []):
            nombre_worker = _norm(w.get("nombre_completo") or "")
            if nombre_norm in nombre_worker:
                # ✅ Normalizaciones clave para evitar "❓" y tener área consistente
                w["turno_activo"] = bool(w.get("turno_activo", False))
                w["area"] = normalizar_area(w.get("area") or "HOUSEKEEPING")
                matches.append(w)

        logger.info(f"👥 {len(matches)} workers encontrados con '{nombre}'")
        return matches

    except Exception as e:
        logger.exception(f"❌ Error buscando workers: {e}")
        return []


def buscar_worker_por_telefono(telefono: str):
    """
    Busca un worker por teléfono.
    Compatible con SQLite y Postgres.
    """
    from gateway_app.services.db import fetchone, using_pg

    if not telefono:
        return None

    is_pg = using_pg()
    ph = "%s" if is_pg else "?"

    sql = f"""
        SELECT
            id,
            nombre,
            apellido,
            nombre_completo,
            telefono,
            area
        FROM workers
        WHERE telefono = {ph}
        LIMIT 1
    """

    try:
        row = fetchone(sql, (telefono,))
        return row
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(
            "Error buscando worker por telefono=%s err=%s",
            telefono,
            e,
        )
        return None