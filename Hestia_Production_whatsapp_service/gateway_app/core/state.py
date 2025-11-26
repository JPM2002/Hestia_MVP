# gateway_app/core/status.py
"""
Human-friendly labels for internal states and statuses.

This module is intentionally small. It is used mainly by:
- HTML debug views (e.g., webhook_debug.html)
- Logging / admin tools that want readable labels.

If a state / status code is unknown, we just return it unchanged.
"""

from __future__ import annotations

from typing import Dict

# Conversation (WhatsApp gateway) states
CONV_STATE_LABELS: Dict[str, str] = {
    "GH_S0": "Conversación nueva",
    "GH_S0i": "Inicio de conversación",
    "GH_TICKET_DRAFT": "Borrador de ticket",
    "GH_TICKET_CONFIRM": "Confirmación de ticket",
    "GH_FAQ": "Consulta de información (FAQ)",
    "GH_HANDOFF": "Derivado a recepción",
}

# Ticket / workflow statuses that may come from the main Hestia app.
# This is just a small, extensible mapping; unknown codes are shown as-is.
TICKET_STATUS_LABELS: Dict[str, str] = {
    "NUEVO": "Nuevo",
    "EN_CURSO": "En curso",
    "RESUELTO": "Resuelto",
    "CERRADO": "Cerrado",
    "PENDIENTE_APROBACION": "Pendiente de aprobación",
    "CANCELADO": "Cancelado",
}


def nice_state(code: str | None) -> str:
    """
    Map an internal state / status code to a human-friendly Spanish label.

    Fallbacks:
    - If the code is None, return "Desconocido".
    - If the code is not in our mapping, return it unchanged.
    """
    if code is None:
        return "Desconocido"

    return (
        CONV_STATE_LABELS.get(code)
        or TICKET_STATUS_LABELS.get(code)
        or code
    )
