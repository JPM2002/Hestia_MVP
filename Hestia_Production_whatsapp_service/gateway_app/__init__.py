# gateway_app/__init__.py
"""
Application factory for the Hestia WhatsApp gateway service.
"""

from __future__ import annotations

import logging

from flask import Flask

from .config import cfg
from .filters import register_filters
from .logging_cfg import configure_logging


def create_app() -> Flask:
    """
    Create and configure the Flask application.

    Used by:
      - run.py (local dev)
      - wsgi.py / gunicorn (production)
    """
    # Configure Python logging first
    configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("Creating Hestia WhatsApp gateway app")

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # Basic config surface (so you can inspect from `app.config`)
    app.config.update(
        DATABASE_URL=cfg.DATABASE_URL,
        OPENAI_API_KEY=cfg.OPENAI_API_KEY,
        TRANSCRIBE_PROVIDER=cfg.TRANSCRIBE_PROVIDER,
        WHATSAPP_CLOUD_PHONE_ID=cfg.WHATSAPP_CLOUD_PHONE_ID,
        WHATSAPP_CLOUD_TOKEN=cfg.WHATSAPP_CLOUD_TOKEN,
        WHATSAPP_VERIFY_TOKEN=cfg.WHATSAPP_VERIFY_TOKEN,
        INTERNAL_NOTIFY_TOKEN=cfg.INTERNAL_NOTIFY_TOKEN,
        ENV="production" if not cfg.DEBUG else "development",
        DEBUG=cfg.DEBUG,
        TESTING=cfg.TESTING,
    )

    # Register Jinja filters
    register_filters(app)

    # Register blueprints
    from .blueprints.webhook import bp as webhook_bp
    app.register_blueprint(webhook_bp)

    # Error handlers (404/500 JSON + HTML)
    from .core.errors import register_error_handlers
    register_error_handlers(app)

    logger.info("Hestia WhatsApp gateway app created")
    return app


__all__ = ("create_app",)
