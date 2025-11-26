# gateway_app/core/errors.py
"""
Error types and global error handlers for the WhatsApp gateway app.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from flask import jsonify, render_template, request

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base application error with an HTTP status code."""

    status_code: int = 400

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        payload: Dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload or {}

    @property
    def message(self) -> str:
        return str(self)


class WebhookError(AppError):
    """Raised when a WhatsApp webhook payload is invalid or cannot be processed."""

    status_code = 400


def _wants_json() -> bool:
    """
    Heuristic: return JSON if the request is JSON or clearly API-like.
    """
    if request.is_json:
        return True
    accept = (request.headers.get("Accept") or "").lower()
    if "application/json" in accept:
        return True
    # Simple path-based heuristic for future API endpoints
    if request.path.startswith("/api/"):
        return True
    return False


def register_error_handlers(app) -> None:
    """
    Register global error handlers on the Flask app.

    This uses:
      - JSON responses for API-style requests.
      - HTML error.html for normal browser visits.
    """

    @app.errorhandler(AppError)
    def handle_app_error(exc: AppError):
        logger.warning("AppError: %s", exc, exc_info=True)
        status = getattr(exc, "status_code", 400) or 400
        payload = dict(exc.payload)
        payload.setdefault("error", exc.message)

        if _wants_json():
            return jsonify(payload), status

        return (
            render_template(
                "error.html",
                code=status,
                message=exc.message,
            ),
            status,
        )

    @app.errorhandler(404)
    def handle_404(exc):
        logger.info("404 Not Found: %s %s", request.method, request.path)
        if _wants_json():
            return jsonify({"error": "Recurso no encontrado"}), 404
        return (
            render_template(
                "error.html",
                code=404,
                message="Recurso no encontrado",
            ),
            404,
        )

    @app.errorhandler(500)
    def handle_500(exc):
        logger.exception("Unhandled server error")
        if _wants_json():
            return jsonify({"error": "Error interno del servidor"}), 500
        return (
            render_template(
                "error.html",
                code=500,
                message="Error interno del servidor",
            ),
            500,
        )
