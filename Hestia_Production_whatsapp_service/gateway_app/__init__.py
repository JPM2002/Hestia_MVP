# gateway_app/__init__.py
"""
Application factory for the Hestia WhatsApp gateway service.
"""

from __future__ import annotations

import logging

from flask import Flask

from gateway_app.config import cfg
from gateway_app.filters import register_filters
from gateway_app.logging_cfg import configure_logging

from .config import cfg


def create_app() -> Flask:
    """
    Create and configure the Flask application.

    This is used by:
      - run.py (for local dev)
      - wsgi.py / gunicorn (for production)
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
    app.config["DATABASE_URL"] = cfg.DATABASE_URL
    app.config["OPENAI_API_KEY"] = cfg.OPENAI_API_KEY
    app.config["TRANSCRIBE_PROVIDER"] = cfg.TRANSCRIBE_PROVIDER
    app.config["WHATSAPP_CLOUD_PHONE_ID"] = cfg.WHATSAPP_CLOUD_PHONE_ID
    app.config["WHATSAPP_CLOUD_TOKEN"] = cfg.WHATSAPP_CLOUD_TOKEN
    app.config["WHATSAPP_VERIFY_TOKEN"] = cfg.WHATSAPP_VERIFY_TOKEN
    app.config["INTERNAL_NOTIFY_TOKEN"] = cfg.INTERNAL_NOTIFY_TOKEN
    app.config["ENV"] = "production" if not cfg.DEBUG else "development"
    app.config["DEBUG"] = cfg.DEBUG
    app.config["TESTING"] = cfg.TESTING

    # Register Jinja filters
    register_filters(app)

    # Register blueprints
    from gateway_app.blueprints.webhook import bp as webhook_bp

    app.register_blueprint(webhook_bp)

    # Error handlers (404/500 JSON + HTML)
    from gateway_app.core.errors import register_error_handlers

    register_error_handlers(app)

    logger.info("Hestia WhatsApp gateway app created")
    return app


__all__ = ["create_app"]
