# hestia_app/services/bootstrap.py

from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any, List

from hestia_app.services.db import fetchone, fetchall, execute

try:
    # Hasher real (si existe)
    from hestia_app.blueprints.auth.routes import hp  # type: ignore
except Exception:
    # Fallback: sin hashing (solo para demo)
    def hp(s: str) -> str:
        return s


# ---------------------------------------------------------------------------
# Catálogos por defecto
# ---------------------------------------------------------------------------

ROLES = [
    {"code": "SUPERADMIN", "name": "Superadministrador", "inherits": "GERENTE"},
    {"code": "GERENTE", "name": "Gerente de operación", "inherits": "SUPERVISOR"},
    {"code": "SUPERVISOR", "name": "Supervisor de área", "inherits": "RECEPCION"},
    {"code": "RECEPCION", "name": "Recepción / Front Desk", "inherits": "TECNICO"},
    {"code": "TECNICO", "name": "Técnico de campo", "inherits": None},
]

PERMISSIONS = [
    ("dashboard:view", "Ver dashboard general"),
    ("tickets:view_all", "Ver todos los tickets del hotel/org"),
    ("tickets:view_own", "Ver tickets asignados al usuario"),
    ("tickets:create", "Crear nuevos tickets"),
    ("tickets:assign", "Asignar/derivar tickets"),
    ("tickets:change_state", "Cambiar estado de tickets"),
    ("tickets:approve", "Aprobar tickets"),
    ("tickets:delete", "Eliminar/cancelar tickets"),
    ("users:manage", "Gestionar usuarios"),
    ("orgs:manage", "Gestionar organizaciones"),
    ("hotels:manage", "Gestionar hoteles"),
    ("sla:manage", "Configurar reglas SLA"),
    ("locations:manage", "Configurar ubicaciones"),
    ("assets:manage", "Gestionar activos/equipos"),
    ("reports:view", "Ver reportes/KPIs"),
    ("integrations:manage", "Configurar integraciones externas"),
]

ALL_PERM_CODES = [code for code, _ in PERMISSIONS]

ROLE_PERMISSIONS = {
    # Tiene todos los permisos
    "SUPERADMIN": ALL_PERM_CODES,
    # Operación + gestión fuerte, pero no nivel plataforma
    "GERENTE": [
        "dashboard:view",
        "tickets:view_all",
        "tickets:view_own",
        "tickets:create",
        "tickets:assign",
        "tickets:change_state",
        "tickets:approve",
        "tickets:delete",
        "users:manage",
        "hotels:manage",
        "sla:manage",
        "locations:manage",
        "assets:manage",
        "reports:view",
        # podríamos añadir "integrations:manage" o "orgs:manage" si queremos
    ],
    # Operación diaria fuerte
    "SUPERVISOR": [
        "dashboard:view",
        "tickets:view_all",
        "tickets:view_own",
        "tickets:create",
        "tickets:assign",
        "tickets:change_state",
        "reports:view",
    ],
    # Recepción / front desk
    "RECEPCION": [
        "dashboard:view",
        "tickets:view_all",
        "tickets:view_own",
        "tickets:create",
    ],
    # Técnico de campo
    "TECNICO": [
        "dashboard:view",
        "tickets:view_own",
        "tickets:change_state",
    ],
}

LOCATION_TYPES = [
    ("HOTEL", "Hotel / Propiedad"),
    ("FLOOR", "Piso"),
    ("ROOM", "Habitación"),
    ("AREA", "Área común / Zona"),
    ("EQUIPMENT", "Equipo / Activo"),
]

TICKET_TAGS = [
    "URGENCIA",
    "VIP",
    "RECLAMO",
    "GARANTIA",
    "SEGURIDAD",
    "PMS_SYNC",
]

TICKET_TYPES = [
    ("GEN_MANT", "Genérico mantención", "MANTENCION"),
    ("GEN_HK", "Genérico housekeeping", "HOUSEKEEPING"),
    ("GEN_RS", "Genérico room service", "ROOMSERVICE"),
    ("RECLAMO", "Reclamo de huésped", "HOUSEKEEPING"),
    ("SEGURIDAD", "Incidente de seguridad", "MANTENCION"),
    ("OTROS", "Otros", None),
]

SLA_DEFAULTS = {
    "MANTENCION": {
        "BAJA": 1440,   # 24h
        "MEDIA": 480,   # 8h
        "ALTA": 120,    # 2h
        "CRITICA": 60,  # 1h
    },
    "HOUSEKEEPING": {
        "BAJA": 720,    # 12h
        "MEDIA": 240,   # 4h
        "ALTA": 60,     # 1h
        "CRITICA": 30,  # 30 min
    },
    "ROOMSERVICE": {
        "BAJA": 60,     # 1h
        "MEDIA": 30,    # 30 min
        "ALTA": 15,     # 15 min
        "CRITICA": 10,  # 10 min
    },
}


# ---------------------------------------------------------------------------
# Helpers de inserción idempotente
# ---------------------------------------------------------------------------

def _ensure_role(code: str, name: str, inherits: Optional[str]) -> None:
    row = fetchone("SELECT code FROM roles WHERE code=?", (code,))
    if row:
        # Opcionalmente podríamos actualizar nombre/herencia
        return
    execute(
        "INSERT INTO roles(code, name, inherits_code) VALUES (?,?,?)",
        (code, name, inherits),
    )


def _ensure_permission(code: str, name: str) -> None:
    row = fetchone("SELECT code FROM permissions WHERE code=?", (code,))
    if row:
        return
    execute(
        "INSERT INTO permissions(code, name) VALUES (?,?)",
        (code, name),
    )


def _ensure_role_permission(role_code: str, perm_code: str) -> None:
    row = fetchone(
        "SELECT 1 FROM rolepermissions WHERE role_code=? AND perm_code=?",
        (role_code, perm_code),
    )
    if row:
        return
    execute(
        "INSERT INTO rolepermissions(role_code, perm_code, allow) VALUES (?,?,?)",
        (role_code, perm_code, True),
    )


def _ensure_location_type(code: str, name: str) -> None:
    row = fetchone("SELECT code FROM location_types WHERE code=?", (code,))
    if row:
        return
    execute(
        "INSERT INTO location_types(code, name) VALUES (?,?)",
        (code, name),
    )


def _ensure_ticket_tag(tag: str) -> None:
    row = fetchone("SELECT tag FROM ticket_tags WHERE tag=?", (tag,))
    if row:
        return
    execute(
        "INSERT INTO ticket_tags(tag) VALUES (?)",
        (tag,),
    )


def _ensure_ticket_type(code: str, name: str, area: Optional[str]) -> None:
    row = fetchone("SELECT code FROM ticket_types WHERE code=?", (code,))
    if row:
        return
    execute(
        "INSERT INTO ticket_types(code, name, area) VALUES (?,?,?)",
        (code, name, area),
    )


def _ensure_sla_rule(
    area: str,
    prioridad: str,
    max_minutes: int,
    org_id: int,
    hotel_id: int,
) -> None:
    row = fetchone(
        """
        SELECT 1 FROM slarules
        WHERE area=? AND prioridad=? AND org_id=? AND hotel_id=?
        """,
        (area, prioridad, org_id, hotel_id),
    )
    if row:
        return
    execute(
        """
        INSERT INTO slarules(area, prioridad, max_minutes, org_id, hotel_id)
        VALUES (?,?,?,?,?)
        """,
        (area, prioridad, max_minutes, org_id, hotel_id),
    )


def _ensure_org_user_area(org_id: int, user_id: int, area_code: str) -> None:
    row = fetchone(
        """
        SELECT 1 FROM OrgUserAreas
        WHERE org_id=? AND user_id=? AND area_code=?
        """,
        (org_id, user_id, area_code),
    )
    if row:
        return
    execute(
        "INSERT INTO OrgUserAreas(org_id, user_id, area_code) VALUES (?,?,?)",
        (org_id, user_id, area_code),
    )


# ---------------------------------------------------------------------------
# API pública: bootstrap global + creación de Org+Hotel+Gerente
# ---------------------------------------------------------------------------

def bootstrap_global_catalogs() -> None:
    """
    Inicializa catálogos globales:
      - roles, permissions, rolepermissions
      - location_types
      - ticket_tags, ticket_types

    Es idempotente: se puede llamar varias veces sin duplicar datos.
    """
    # Roles
    for r in ROLES:
        _ensure_role(r["code"], r["name"], r["inherits"])

    # Permisos
    for code, name in PERMISSIONS:
        _ensure_permission(code, name)

    # Asignación de permisos por rol
    for role_code, perms in ROLE_PERMISSIONS.items():
        for perm_code in perms:
            _ensure_role_permission(role_code, perm_code)

    # Tipos de ubicación
    for code, name in LOCATION_TYPES:
        _ensure_location_type(code, name)

    # Tags de ticket
    for tag in TICKET_TAGS:
        _ensure_ticket_tag(tag)

    # Tipos de ticket
    for code, name, area in TICKET_TYPES:
        _ensure_ticket_type(code, name, area)


def create_org_with_defaults(
    org_name: str,
    hotel_name: str,
    gerente_email: str,
    gerente_username: str,
    gerente_password: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Crea una organización nueva + su primer hotel + vincula/crea un usuario GERENTE,
    e inicializa SLA y ubicaciones básicas.

    Devuelve:
      {
        "org_id": int,
        "hotel_id": int,
        "user_id": int,
        "org_user_id": int,
      }
    """
    now = datetime.now().isoformat()

    # ----------------------------------------------------------------------
    # 1) Org
    # ----------------------------------------------------------------------
    execute(
        "INSERT INTO Orgs(name, created_at) VALUES(?, ?)",
        (org_name.strip(), now),
    )
    org_row = fetchone(
        "SELECT id FROM Orgs WHERE name=? ORDER BY id DESC LIMIT 1",
        (org_name.strip(),),
    )
    if not org_row:
        raise RuntimeError("No se pudo crear la organización")
    org_id = int(org_row["id"])

    # ----------------------------------------------------------------------
    # 2) Hotel
    # ----------------------------------------------------------------------
    execute(
        "INSERT INTO Hotels(org_id, name, created_at) VALUES(?,?,?)",
        (org_id, hotel_name.strip(), now),
    )
    hotel_row = fetchone(
        """
        SELECT id FROM Hotels
        WHERE org_id=? AND name=?
        ORDER BY id DESC LIMIT 1
        """,
        (org_id, hotel_name.strip()),
    )
    if not hotel_row:
        raise RuntimeError("No se pudo crear el hotel")
    hotel_id = int(hotel_row["id"])

    # ----------------------------------------------------------------------
    # 3) Usuario GERENTE
    # ----------------------------------------------------------------------
    email = gerente_email.strip().lower()
    username = gerente_username.strip()

    user_row = fetchone("SELECT id FROM Users WHERE email=?", (email,))
    if not user_row:
        password = gerente_password or "demo123"
        execute(
            """
            INSERT INTO Users(username,email,password_hash,role,area,telefono,activo,is_superadmin)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (username, email, hp(password), "GERENTE", None, None, True, False),
        )
        user_row = fetchone("SELECT id FROM Users WHERE email=?", (email,))
        if not user_row:
            raise RuntimeError("No se pudo crear el usuario gerente")
    user_id = int(user_row["id"])

    # ----------------------------------------------------------------------
    # 4) OrgUsers (miembro de la org)
    # ----------------------------------------------------------------------
    org_user_row = fetchone(
        "SELECT id FROM OrgUsers WHERE org_id=? AND user_id=?",
        (org_id, user_id),
    )
    if org_user_row:
        execute(
            """
            UPDATE OrgUsers
            SET role=?, default_area=?, default_hotel_id=?
            WHERE id=?
            """,
            ("GERENTE", None, hotel_id, org_user_row["id"]),
        )
        org_user_id = int(org_user_row["id"])
    else:
        execute(
            """
            INSERT INTO OrgUsers(org_id,user_id,role,default_area,default_hotel_id)
            VALUES (?,?,?,?,?)
            """,
            (org_id, user_id, "GERENTE", None, hotel_id),
        )
        org_user_row = fetchone(
            "SELECT id FROM OrgUsers WHERE org_id=? AND user_id=?",
            (org_id, user_id),
        )
        if not org_user_row:
            raise RuntimeError("No se pudo crear la membresía OrgUsers")
        org_user_id = int(org_user_row["id"])

    # ----------------------------------------------------------------------
    # 5) SLA específicos para este org + hotel
    # ----------------------------------------------------------------------
    for area, by_priority in SLA_DEFAULTS.items():
        for prioridad, max_minutes in by_priority.items():
            _ensure_sla_rule(area, prioridad, max_minutes, org_id, hotel_id)

    # ----------------------------------------------------------------------
    # 6) Ubicaciones mínimas (HOTEL ROOT + ejemplo piso/habitación)
    # ----------------------------------------------------------------------
    # Nos aseguramos de que existan los tipos relevantes
    for code, name in LOCATION_TYPES:
        _ensure_location_type(code, name)

    # Raíz del hotel
    execute(
        """
        INSERT INTO locations(hotel_id, type_code, code, name, parent_id)
        VALUES (?,?,?,?,NULL)
        """,
        (hotel_id, "HOTEL", "ROOT", hotel_name.strip()),
    )
    root_row = fetchone(
        """
        SELECT id FROM locations
        WHERE hotel_id=? AND type_code=? AND code=?
        ORDER BY id DESC LIMIT 1
        """,
        (hotel_id, "HOTEL", "ROOT"),
    )
    root_id: Optional[int] = int(root_row["id"]) if root_row else None

    floor_id: Optional[int] = None
    if root_id is not None:
        # Piso 1
        execute(
            """
            INSERT INTO locations(hotel_id, type_code, code, name, parent_id)
            VALUES (?,?,?,?,?)
            """,
            (hotel_id, "FLOOR", "1", "Piso 1", root_id),
        )
        floor_row = fetchone(
            """
            SELECT id FROM locations
            WHERE hotel_id=? AND type_code=? AND code=?
            ORDER BY id DESC LIMIT 1
            """,
            (hotel_id, "FLOOR", "1"),
        )
        floor_id = int(floor_row["id"]) if floor_row else None

    if floor_id is not None:
        # Habitación 101 de ejemplo
        execute(
            """
            INSERT INTO locations(hotel_id, type_code, code, name, parent_id)
            VALUES (?,?,?,?,?)
            """,
            (hotel_id, "ROOM", "101", "Habitación 101", floor_id),
        )

    # ----------------------------------------------------------------------
    # 7) OrgUserAreas: el gerente tiene visibilidad en las áreas core
    # ----------------------------------------------------------------------
    for area_code in ("MANTENCION", "HOUSEKEEPING", "ROOMSERVICE"):
        _ensure_org_user_area(org_id, user_id, area_code)

    return {
        "org_id": org_id,
        "hotel_id": hotel_id,
        "user_id": user_id,
        "org_user_id": org_user_id,
    }
