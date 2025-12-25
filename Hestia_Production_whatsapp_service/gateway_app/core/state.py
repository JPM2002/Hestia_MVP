# gateway_app/core/state.py
"""
DEPRECATED: Este módulo ha sido refactorizado en una arquitectura modular.

NUEVO CÓDIGO:
- gateway_app/core/conversation/orchestrator.py - Orchestrator principal
- gateway_app/core/conversation/session.py - Session management
- gateway_app/core/intents/ - Intent handlers modulares

Este archivo mantiene compatibilidad hacia atrás delegando a los nuevos módulos.
"""

from __future__ import annotations

import logging

# Delegate to new modular architecture
from gateway_app.core.conversation.session import (
    load_session,
    save_session,
)
from gateway_app.core.conversation.orchestrator import (
    handle_incoming_text,
)

logger = logging.getLogger(__name__)

# Re-export public API for backward compatibility
__all__ = [
    "load_session",
    "save_session",
    "handle_incoming_text",
]

logger.info(
    "[REFACTOR] state.py now delegates to modular architecture",
    extra={
        "new_orchestrator": "gateway_app/core/conversation/orchestrator.py",
        "new_session": "gateway_app/core/conversation/session.py",
        "new_intents": "gateway_app/core/intents/",
    }
)
