"""
Area-related utilities.
"""
from typing import List, Optional

from gateway_app.core.conversation.utils.constants import AREA_MAP
from gateway_app.services.i18n import normalize_lang, area_name



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


def build_area_options_text(
    detected_areas: Optional[List[str]] = None,
    lang: Optional[str] = None,
) -> str:
    """
    Build area selection options text in the correct language.

    Output format:
      1️⃣ *Maintenance* (technical/AC/water/lights)
      2️⃣ *Housekeeping* (cleaning/towels/amenities)
      3️⃣ *Front Desk* (billing/reservations/info)
      4️⃣ *Management* (complaint/management)
    """
    l = normalize_lang(lang)

    desc_map = {
        "es": {
            "MANTENCION": "técnico/AC/agua/luz",
            "HOUSEKEEPING": "limpieza/toallas/amenities",
            "RECEPCION": "pagos/reservas/info",
            "GERENCIA": "queja/gerencia",
        },
        "en": {
            "MANTENCION": "technical/AC/water/lights",
            "HOUSEKEEPING": "cleaning/towels/amenities",
            "RECEPCION": "billing/reservations/info",
            "GERENCIA": "complaint/management",
        },
        "pt": {
            "MANTENCION": "técnico/ar/água/luz",
            "HOUSEKEEPING": "limpeza/toalhas/amenities",
            "RECEPCION": "pagamentos/reservas/info",
            "GERENCIA": "reclamação/gerência",
        },
    }[l]

    number_map = {
        "MANTENCION": "1",
        "HOUSEKEEPING": "2",
        "RECEPCION": "3",
        "GERENCIA": "4",
    }

    def _line(area_code: str) -> str:
        num = number_map.get(area_code) or (AREA_MAP.get(area_code, ("", "", ""))[1] if area_code in AREA_MAP else "")
        name_local = area_name(area_code, l)
        desc = desc_map.get(area_code, "")
        return f"{num}️⃣ *{name_local}* ({desc})" if desc else f"{num}️⃣ *{name_local}*"

    # stable order (1→4)
    order = ["MANTENCION", "HOUSEKEEPING", "RECEPCION", "GERENCIA"]

    if detected_areas:
        filtered = [a for a in order if a in set(detected_areas)]
        return "\n".join(_line(a) for a in filtered)

    return "\n".join(_line(a) for a in order)
