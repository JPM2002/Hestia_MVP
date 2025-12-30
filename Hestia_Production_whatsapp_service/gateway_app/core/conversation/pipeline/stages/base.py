"""
Base class para pipeline stages.
"""
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gateway_app.core.conversation.pipeline.context import PipelineContext


logger = logging.getLogger(__name__)


class PipelineStage(ABC):
    """
    Base class para todos los pipeline stages.

    Cada stage implementa process() y retorna el context modificado.
    """

    @abstractmethod
    def process(self, context: PipelineContext) -> PipelineContext:
        """
        Procesa el context y retorna el context modificado.

        Args:
            context: Pipeline context con mensaje, session, etc.

        Returns:
            Context modificado (puede ser el mismo objeto mutado)
        """
        raise NotImplementedError

    @property
    def name(self) -> str:
        """Nombre del stage para logging."""
        return self.__class__.__name__

    def should_skip(self, context: PipelineContext) -> bool:
        """
        Verifica si este stage debe ser saltado.

        Override en stages que tienen precondiciones.
        """
        return context.skip_remaining

    def log_entry(self, context: PipelineContext) -> None:
        """Log al entrar al stage."""
        logger.debug(
            f"[PIPELINE] Entering {self.name}",
            extra={
                "stage": self.name,
                "wa_id": context.wa_id,
                "state": context.session.get("state"),
                "handled": context.handled
            }
        )

    def log_exit(self, context: PipelineContext) -> None:
        """Log al salir del stage."""
        logger.debug(
            f"[PIPELINE] Exiting {self.name}",
            extra={
                "stage": self.name,
                "handled": context.handled,
                "skip_remaining": context.skip_remaining,
                "actions_count": len(context.actions)
            }
        )
