"""
Area-related utilities.
"""
from typing import List, Optional

from gateway_app.core.conversation.utils.constants import AREA_MAP


def get_area_name(area_code: str) -> str:
    """
    Get friendly area name.

    Args:
        area_code: Area code (e.g., "MANTENCION")

    Returns:
        Friendly name (e.g., "Mantenimiento") or empty string
    """
    info = AREA_MAP.get(area_code)
    return info[0] if info else ""


def get_area_number(area_code: str) -> str:
    """
    Get area number (1-4).

    Args:
        area_code: Area code

    Returns:
        Number string or empty string
    """
    info = AREA_MAP.get(area_code)
    return info[1] if info else ""


def get_area_description(area_code: str) -> str:
    """
    Get area description.

    Args:
        area_code: Area code

    Returns:
        Description or empty string
    """
    info = AREA_MAP.get(area_code)
    return info[2] if info else ""


def build_area_options_text(detected_areas: Optional[List[str]] = None) -> str:
    """
    Build area selection options text.

    Args:
        detected_areas: List of detected area codes (optional)
                       If provided, only show these areas

    Returns:
        Formatted area options text
    """
    if detected_areas:
        # Show only detected areas
        options = []
        for area in detected_areas:
            info = AREA_MAP.get(area)
            if info:
                name, number, desc = info
                options.append(f"{number}️⃣ *{name}* ({desc})")
        return "\n".join(options)
    else:
        # Show all areas
        return (
            "1️⃣ *Mantenimiento* (técnico/AC/agua/luz)\n"
            "2️⃣ *Housekeeping* (limpieza/toallas/amenities)\n"
            "3️⃣ *Recepción* (pagos/reservas/info)\n"
            "4️⃣ *Otro* (queja/gerencia)"
        )
