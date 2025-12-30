"""
Message parsing utilities.
"""
import re

from gateway_app.core.conversation.utils.constants import CANCEL_PATTERNS, MENU_SHORTCUTS


def looks_like_global_cancel(msg: str) -> bool:
    """
    Best-effort, LLM-independent check for cancellation messages.

    Args:
        msg: User message

    Returns:
        True if message matches cancel patterns
    """
    if not msg:
        return False

    lower = msg.lower()
    for pattern in CANCEL_PATTERNS:
        if re.search(pattern, lower):
            return True

    return False


def is_menu_shortcut(msg: str) -> bool:
    """
    Check if message is a menu shortcut.

    Args:
        msg: User message

    Returns:
        True if message is 'menu', 'inicio', or 'start'
    """
    if not msg:
        return False

    return msg.lower() in MENU_SHORTCUTS
