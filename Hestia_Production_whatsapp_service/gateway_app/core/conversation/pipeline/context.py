"""
Pipeline context object que viaja por todos los stages.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from gateway_app.core.models import NLUResult


@dataclass
class PipelineContext:
    """
    Context object que se pasa entre stages del pipeline.

    Cada stage puede:
    - Leer datos del context
    - Modificar el context
    - Agregar actions
    - Marcar como handled (skip remaining stages)
    """

    # Input data (inmutable)
    wa_id: str
    guest_phone: str
    guest_name: Optional[str]
    message: str
    timestamp: Any
    raw_payload: Dict[str, Any]

    # Session (mutable)
    session: Dict[str, Any]

    # Processing results (acumulado por stages)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    nlu: Optional[NLUResult] = None

    # Control flags
    handled: bool = False
    skip_remaining: bool = False

    # Metadata (para debugging/logging)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_action(self, action: Dict[str, Any]) -> None:
        """Helper para agregar una acción."""
        self.actions.append(action)

    def mark_handled(self) -> None:
        """Marca el mensaje como manejado y skip remaining stages."""
        self.handled = True
        self.skip_remaining = True
