"""
Notification Services Module

Handles automated notifications for ticket assignments, resolutions,
and FAQ surveys.
"""

from .handlers import process_all_notifications

__all__ = ["process_all_notifications"]
