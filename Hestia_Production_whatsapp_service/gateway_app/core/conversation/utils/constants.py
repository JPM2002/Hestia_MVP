"""
Centralized constants for conversation handling.
"""

# ============================================================================
# STATES
# ============================================================================

STATE_NEW = "GH_S0"
STATE_INIT = "GH_S0_INIT"
STATE_GUEST_IDENTIFY = "GH_IDENTIFY"
STATE_TICKET_CONFIRM = "GH_TICKET_CONFIRM"
STATE_AREA_CLARIFICATION = "GH_AREA_CLARIFICATION"
STATE_DETAIL_CLARIFICATION = "GH_DETAIL_CLARIFICATION"
STATE_FAQ = "GH_FAQ"
STATE_NEXT_TICKET_CONFIRM = "GH_NEXT_TICKET_CONFIRM"
STATE_HANDOFF = "GH_HANDOFF"

# ============================================================================
# AREAS
# ============================================================================

AREA_MANTENCION = "MANTENCION"
AREA_HOUSEKEEPING = "HOUSEKEEPING"
AREA_RECEPCION = "RECEPCION"
AREA_GERENCIA = "GERENCIA"

# Area mapping: (friendly_name, number, description)
AREA_MAP = {
    "MANTENCION": ("Mantenimiento", "1", "técnico/AC/agua/luz"),
    "HOUSEKEEPING": ("Housekeeping", "2", "limpieza/toallas/amenities"),
    "RECEPCION": ("Recepción", "3", "pagos/reservas/info"),
    "GERENCIA": ("Gerencia", "4", "queja/gerencia")
}

# ============================================================================
# CONFIDENCE
# ============================================================================

CONFIDENCE_THRESHOLD = 0.65

# ============================================================================
# PATTERNS
# ============================================================================

CANCEL_PATTERNS = [
    r"\bcancela\b",
    r"\bcancelar\b",
    r"\banula\b",
    r"\banular\b",
    r"\bolvídalo\b",
    r"\bolvida eso\b",
    r"\bya no lo necesito\b",
    r"\bya no hace falta\b",
    r"\bya no quiero eso\b",
]

MENU_SHORTCUTS = {"menu", "inicio", "start"}
