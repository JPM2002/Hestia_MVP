# gateway_app/logging_cfg.py
"""
Central logging configuration for the WhatsApp gateway service.

Use configure_logging() early in app startup (e.g., in gateway_app/__init__.py)
so that all modules share a consistent logging setup.
"""

from __future__ import annotations

import json
import logging
from logging.config import dictConfig

from gateway_app.config import cfg


class DetailedFormatter(logging.Formatter):
    """
    Custom formatter that includes the 'extra' dict fields in the log output.

    If a log record has extra fields (passed via logger.info(..., extra={})),
    they will be displayed as JSON after the main message.
    """

    # Standard log record attributes that shouldn't be treated as "extra"
    STANDARD_ATTRS = {
        'name', 'msg', 'args', 'created', 'filename', 'funcName', 'levelname',
        'levelno', 'lineno', 'module', 'msecs', 'message', 'pathname', 'process',
        'processName', 'relativeCreated', 'thread', 'threadName', 'exc_info',
        'exc_text', 'stack_info', 'asctime'
    }

    def format(self, record: logging.LogRecord) -> str:
        # First format the standard message
        base_message = super().format(record)

        # Extract any extra fields from the record
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in self.STANDARD_ATTRS and not key.startswith('_'):
                extra_fields[key] = value

        # If there are extra fields, append them as JSON
        if extra_fields:
            try:
                extra_json = json.dumps(extra_fields, indent=2, ensure_ascii=False, default=str)
                return f"{base_message}\n{extra_json}"
            except Exception:
                # If JSON serialization fails, just return the base message
                return base_message

        return base_message


def configure_logging() -> None:
    """
    Configure Python logging using dictConfig.

    - Log level is INFO by default, DEBUG when cfg.DEBUG is True.
    - All logs go to stdout (compatible with Render / container logs).
    - Uses DetailedFormatter to show 'extra' fields in JSON format.
    """
    level = "DEBUG" if cfg.DEBUG else "INFO"

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": DetailedFormatter,
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
