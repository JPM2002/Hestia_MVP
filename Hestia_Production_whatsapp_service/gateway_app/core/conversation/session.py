# gateway_app/core/conversation/session.py
"""
Session management - Load, save, and manage conversation sessions.

Extracted from state.py to improve modularity.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from gateway_app.core.timefmt import utcnow

logger = logging.getLogger(__name__)

# Session TTL configuration
SESSION_TTL_SECONDS = 15 * 60  # 15 minutes

# In-memory session store: wa_id -> session dict
_SESSIONS: Dict[str, Dict[str, Any]] = {}


def load_session(wa_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve the session for a WhatsApp contact id (wa_id).
    Validates TTL and returns None if session expired.

    Returns:
        dict with session data, or None if not found/expired.
    """
    session = _SESSIONS.get(wa_id)

    if not session:
        return None

    # Validate TTL (15 minutes)
    last_message = session.get("last_message_at")
    if last_message:
        try:
            from datetime import datetime
            last_dt = datetime.fromisoformat(last_message)
            elapsed = (utcnow() - last_dt).total_seconds()

            if elapsed > SESSION_TTL_SECONDS:
                # Session expired, delete it
                _SESSIONS.pop(wa_id, None)
                logger.info(
                    "[SESSION] Session expired due to TTL",
                    extra={
                        "wa_id": wa_id,
                        "elapsed_seconds": int(elapsed),
                        "ttl_seconds": SESSION_TTL_SECONDS
                    }
                )
                return None
        except Exception as e:
            logger.warning(
                "[SESSION] TTL validation failed",
                extra={"wa_id": wa_id, "error": str(e)}
            )

    return session


def save_session(wa_id: str, session: Optional[Dict[str, Any]]) -> None:
    """
    Persist the session in the in-memory store.

    If session is None, the existing one (if any) is removed.
    """
    if session is None:
        _SESSIONS.pop(wa_id, None)
        return

    session.setdefault("wa_id", wa_id)
    session["updated_at"] = utcnow().isoformat()
    _SESSIONS[wa_id] = session


def new_session(
    *,
    wa_id: str,
    guest_phone: str,
    guest_name: Optional[str],
    timestamp,
) -> Dict[str, Any]:
    """
    Create a new session for a guest.

    Args:
        wa_id: WhatsApp contact ID
        guest_phone: Phone number
        guest_name: Guest name (if available)
        timestamp: Timestamp of first message

    Returns:
        New session dict
    """
    now_iso = utcnow().isoformat()
    session: Dict[str, Any] = {
        "wa_id": wa_id,
        "phone": guest_phone,
        "guest_name": guest_name or None,
        "state": "GH_S0_INIT",
        "language": None,
        "room": None,
        "created_at": now_iso,
        "updated_at": now_iso,
        "last_message_at": now_iso,
        "data": {},
    }

    logger.info(
        "[SESSION] New guest session created",
        extra={"wa_id": wa_id, "phone": guest_phone},
    )

    return session
