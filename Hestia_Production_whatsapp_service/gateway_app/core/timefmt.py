# gateway_app/core/timefmt.py
"""
Datetime helpers for the WhatsApp gateway.

Goals:
- Always store and log times in UTC.
- Provide simple helpers for ISO-8601 and short human-readable formats.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def utcnow() -> datetime:
    """
    Current time in UTC with tzinfo set.

    Use this instead of datetime.utcnow() so that all datetimes are tz-aware.
    """
    return datetime.now(timezone.utc)


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Normalize a datetime to UTC.

    - If dt is None → None.
    - If dt is naive (no tzinfo) → assume UTC and attach tzinfo.
    - If dt has tzinfo → convert to UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_iso(dt: Optional[datetime]) -> Optional[str]:
    """
    Convert a datetime to ISO-8601 string in UTC (seconds precision).

    Returns None if dt is None.
    """
    if dt is None:
        return None
    dt_utc = ensure_utc(dt)
    return dt_utc.isoformat(timespec="seconds")


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    """
    Parse an ISO-8601 datetime string into a tz-aware UTC datetime.

    Returns None if value is falsy or parsing fails.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return ensure_utc(dt)


def human_short(dt: Optional[datetime]) -> str:
    """
    Short human-readable representation in local style (UTC):

        '2025-11-26 14:30 UTC'

    If dt is None, returns '-'.
    """
    if dt is None:
        return "-"
    dt_utc = ensure_utc(dt)
    return dt_utc.strftime("%Y-%m-%d %H:%M UTC")
