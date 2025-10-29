# hestia_app/core/scope.py
from __future__ import annotations
from typing import Optional, Tuple
from flask import session

def current_scope() -> Tuple[Optional[int], Optional[int]]:
    """
    Return the current (org_id, hotel_id) from the Flask session.
    """
    org_id = session.get("org_id")
    hotel_id = session.get("hotel_id")

    # Normalize common stringy-nulls if they ever appear
    if org_id in ("", "null", "None"):
        org_id = None
    if hotel_id in ("", "null", "None"):
        hotel_id = None

    return org_id, hotel_id
