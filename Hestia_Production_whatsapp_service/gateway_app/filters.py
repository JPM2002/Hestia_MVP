# gateway_app/filters.py
"""
Jinja2 template filters for the WhatsApp gateway service.

Right now this is very small, but having a separate module keeps
things organized and easier to extend later.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Flask


def format_datetime(value: Any, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """
    Format a datetime or ISO8601 string for display.

    If parsing fails, returns the original value as string.
    """
    if value is None:
        return ""

    if isinstance(value, datetime):
        dt = value
    else:
        # Try to parse string-like values
        try:
            dt = datetime.fromisoformat(str(value))
        except Exception:
            return str(value)

    return dt.strftime(fmt)


def nl2br(value: str | None) -> str:
    """
    Replace newlines with <br> tags for HTML rendering.
    """
    if not value:
        return ""
    return value.replace("\n", "<br>")


def register_filters(app: Flask) -> None:
    """
    Register all custom filters on the given Flask app.
    """
    app.jinja_env.filters["datetime"] = format_datetime
    app.jinja_env.filters["nl2br"] = nl2br
