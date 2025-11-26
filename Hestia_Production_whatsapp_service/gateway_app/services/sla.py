# gateway_app/services/sla.py
"""
SLA helpers for Hestia tickets.

Responsibility:
- Provide simple, centralized logic to compute due times for tickets
  based on their priority.
- Offer small utilities to check if something is overdue.

This module is intentionally small and independent so it can be reused
by the WhatsApp gateway or the core Hestia app.

Priorities we handle (case-insensitive):
- "URGENTE"
- "ALTA"
- "MEDIA"
- "BAJA"

You can adjust the SLA minutes in PRIORITY_SLA_MINUTES as needed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

# Default SLA durations in minutes per priority.
# Adjust these to match the rules you actually use in production.
PRIORITY_SLA_MINUTES: Dict[str, int] = {
    "URGENTE": 15,    # 15 minutes
    "ALTA": 60,       # 1 hour
    "MEDIA": 180,     # 3 hours
    "BAJA": 720,      # 12 hours
}

# Fallback SLA if priority is missing or unknown
DEFAULT_SLA_MINUTES: int = 240  # 4 hours


def get_sla_delta(priority: Optional[str]) -> timedelta:
    """
    Return a timedelta representing the SLA for the given priority.

    Args:
        priority: Priority string ("URGENTE", "ALTA", "MEDIA", "BAJA", etc.)

    Returns:
        timedelta for the SLA window.
    """
    if not priority:
        minutes = DEFAULT_SLA_MINUTES
    else:
        key = priority.strip().upper()
        minutes = PRIORITY_SLA_MINUTES.get(key, DEFAULT_SLA_MINUTES)
    return timedelta(minutes=minutes)


def compute_due(
    priority: Optional[str],
    created_at: datetime,
    *,
    tz: Optional[timezone] = timezone.utc,
) -> datetime:
    """
    Compute the due datetime for a ticket given its priority and creation time.

    Args:
        priority: Priority string ("URGENTE", "ALTA", "MEDIA", "BAJA", etc.)
        created_at: Datetime when the ticket/request was created.
                    Can be naive or timezone-aware.
        tz: Timezone to enforce if created_at is naive. Default: UTC.

    Returns:
        Datetime when the ticket is due.
    """
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=tz or timezone.utc)

    delta = get_sla_delta(priority)
    return created_at + delta


def is_overdue(due_at: datetime, *, now: Optional[datetime] = None) -> bool:
    """
    Check if a due datetime is in the past.

    Args:
        due_at: Deadline.
        now: Current time. If None, uses datetime.now(due_at.tzinfo or UTC).

    Returns:
        True if due_at < now, False otherwise.
    """
    if now is None:
        tzinfo = due_at.tzinfo or timezone.utc
        now = datetime.now(tz=tzinfo)
    return due_at < now


def remaining_time(due_at: datetime, *, now: Optional[datetime] = None) -> timedelta:
    """
    Get the remaining time until due_at (can be negative if already overdue).

    Args:
        due_at: Deadline.
        now: Current time. If None, uses datetime.now(due_at.tzinfo or UTC).

    Returns:
        A timedelta that may be negative if overdue.
    """
    if now is None:
        tzinfo = due_at.tzinfo or timezone.utc
        now = datetime.now(tz=tzinfo)
    return due_at - now
