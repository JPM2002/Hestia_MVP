# gateway_app/logging_cfg.py
"""
Central logging configuration for the WhatsApp gateway service.

Use configure_logging() early in app startup (e.g., in gateway_app/__init__.py)
so that all modules share a consistent logging setup.
"""

from __future__ import annotations

import logging
from logging.config import dictConfig

from gateway_app.config import cfg


def configure_logging() -> None:
    """
    Configure Python logging using dictConfig.

    - Log level is INFO by default, DEBUG when cfg.DEBUG is True.
    - All logs go to stdout (compatible with Render / container logs).
    """
    level = "DEBUG" if cfg.DEBUG else "INFO"

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                },
            },
            "handlers": {
                "wsgi": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {
                "level": level,
                "handlers": ["wsgi"],
            },
            # Optionally tweak noisy libraries here
            "loggers": {
                "urllib3": {"level": "WARNING"},
                "requests": {"level": "WARNING"},
                "openai": {"level": "WARNING"},
            },
        }
    )

    logging.getLogger(__name__).info("Logging configured (level=%s)", level)
