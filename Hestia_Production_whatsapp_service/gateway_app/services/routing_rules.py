"""
Rules-based routing for guest messages (Layer 1: Pre-LLM).

This module provides deterministic, zero-cost routing based on keyword pattern matching
before falling back to LLM analysis. Designed to handle 50%+ of common hotel requests
with <100ms latency and $0 API cost.

Based on test cases from: tests/expected_responses.md
"""

import re
from typing import Optional, Dict, Any
import unicodedata


def _normalize_text(text: str) -> str:
    """
    Normalize text for pattern matching:
    - Convert to lowercase
    - Remove accents/diacritics (é → e, ñ → n preserved)
    - Strip extra whitespace
    """
    if not text:
        return ""

    # Lowercase
    text = text.lower().strip()

    # Normalize Unicode (NFD = decompose accents)
    # Then filter out combining marks, BUT preserve ñ/Ñ
    # We'll handle Spanish characters specially
    text = text.replace('á', 'a').replace('é', 'e').replace('í', 'i')
    text = text.replace('ó', 'o').replace('ú', 'u')
    text = text.replace('ü', 'u')
    # Keep ñ as-is (it's important in Spanish)

    return text


# ============================================================================
# ROUTING PATTERNS (ordered by priority: most specific first)
# ============================================================================

# Pattern format: (regex_pattern, reason_description, confidence)
# Confidence: 0.95 for very specific keywords, 0.90 for slightly broader

HOUSEKEEPING_PATTERNS = [
    # Cleaning & Towels
    (r'\b(toalla|toallas)\b', "Towels request", 0.95),
    (r'\b(sabana|sabanas|ropa\s+de\s+cama)\b', "Bed linen request", 0.95),
    (r'\b(limpi|limpiar|limpieza|limpie|limpio|aseo)\b', "Cleaning request", 0.92),
    (r'\b(basura|botar.*basura|retirar.*basura)\b', "Trash removal", 0.93),

    # Amenities
    (r'\b(papel\s*(higienico|ba[nñ]o)|confort)\b', "Toilet paper request", 0.95),
    (r'\b(jabon|shampoo|acondicionador|amenities)\b', "Amenities request", 0.93),
    # NOTE: "almohadas" is intentionally NOT included here - it should fall to LLM
    # as per Caso 5 in tests/expected_responses.md

    # General housekeeping
    (r'\b(sucio|sucia|olor|huele|mal\s+olor)\b', "Cleanliness issue", 0.88),
]

MANTENCION_PATTERNS = [
    # Climate control (MUST be before generic malfunction keywords)
    (r'\b(aire\s*acondicionado|a/c|ac\b|climatizacion|calefaccion)\b', "Climate control issue", 0.95),
    # "aire" by itself when followed by malfunction words
    (r'\baire\b.{0,30}\b(no\s+(funciona|sirve|anda)|descompuesto|da[nñ]ado|roto)', "AC malfunction", 0.93),

    # Water/plumbing
    (r'\b(agua\s+caliente|no\s+tengo\s+agua|no\s+hay\s+agua|sin\s+agua)\b', "Hot water issue", 0.96),
    (r'\b(ducha|regadera|ba[nñ]o|inodoro|llave|canilla|grifo|fuga)\b', "Plumbing issue", 0.90),

    # Electrical
    (r'\b(luz|luces|lampara|ampolleta|foco|bombilla|enchufe|electricidad)\b', "Lighting/electrical issue", 0.90),

    # Electronics
    (r'\b(tv|television|televisor|control\s+remoto)\b', "TV issue", 0.92),
    (r'\b(wifi|internet|conexion|red|se[nñ]al)\b', "WiFi/internet issue", 0.93),

    # Structural
    (r'\b(puerta|ventana|cerradura|llave.*habitacion|chapa)\b', "Door/lock issue", 0.88),
]

RECEPCION_PATTERNS = [
    # Check-in/out
    (r'\b(check\s*out|checkout|late\s+checkout|salida|dejar.*habitacion)\b', "Checkout inquiry", 0.94),
    (r'\b(check\s*in|checkin|llegada|entrada)\b', "Check-in inquiry", 0.93),

    # Reservations & payments
    (r'\b(reserva|reservacion|cambiar.*reserva|booking)\b', "Reservation inquiry", 0.90),
    (r'\b(pago|factura|cuenta|cobro)\b', "Payment inquiry", 0.91),
    (r'\b(cambiar\s+habitacion|otra\s+habitacion)\b', "Room change request", 0.92),

    # General info
    (r'\b(horario|hora\s+de|cuando\s+(abre|cierra))\b', "Schedule inquiry", 0.87),
    (r'\b(caja.*seguridad|fuerte|safe)\b', "Safe box inquiry", 0.93),
    (r'\b(estacionamiento|parqueo|parking|garage)\b', "Parking inquiry", 0.92),
    (r'\b(llave.*perdida|perdi.*llave|no\s+tengo\s+llave)\b', "Lost key", 0.94),
]

GERENCIA_PATTERNS = [
    # Formal complaints & escalations
    (r'\b(queja\s+formal|presentar.*queja|reclamo\s+formal)\b', "Formal complaint", 0.97),
    (r'\b(inaceptable|intoler|intolerable|vergonzoso|pesimo|horrible)\b', "Strong complaint language", 0.92),
    (r'\b(gerente|manager|hablar.*gerente|ver.*gerente)\b', "Manager request", 0.94),
    (r'\b(reembolso|devol|compensacion|descuento)\b', "Refund/compensation request", 0.90),
    (r'\b(abogado|legal|denuncia|rese[nñ]a\s+negativa)\b', "Legal threat/review", 0.95),
    (r'\b(queja|reclamo)\b', "General complaint", 0.88),
]


def route_by_rules(text: str) -> Optional[Dict[str, Any]]:
    """
    Attempt to route a message to a department based on keyword pattern matching.

    This is Layer 1 (pre-LLM) routing: fast, deterministic, zero-cost.
    Designed to handle 50%+ of common requests (cases 1-4, 10 in test suite).

    Args:
        text: The guest message to analyze (plain text)

    Returns:
        Dict with:
            - area: Department code (HOUSEKEEPING | MANTENCION | RECEPCION | GERENCIA)
            - confidence: Float 0.85-0.97 (rule-based matches are high confidence)
            - reason: Human-readable description of why this area was chosen
        Returns None if no patterns match (falls back to LLM).

    Examples:
        >>> route_by_rules("Necesito toallas limpias")
        {'area': 'HOUSEKEEPING', 'confidence': 0.95, 'reason': 'Towels request'}

        >>> route_by_rules("No funciona el aire acondicionado")
        {'area': 'MANTENCION', 'confidence': 0.95, 'reason': 'Climate control issue'}

        >>> route_by_rules("Quiero hacer late checkout")
        {'area': 'RECEPCION', 'confidence': 0.94, 'reason': 'Checkout inquiry'}

        >>> route_by_rules("Pueden traerme almohadas")
        None  # No exact match → falls back to LLM

        >>> route_by_rules("Necesito toallas y el aire no funciona")
        None  # Multi-department → falls back to LLM for clarification
    """
    if not text or not text.strip():
        return None

    # Normalize text for matching
    normalized = _normalize_text(text)

    # =========================================================================
    # STEP 1: Detect multi-department requests (Caso 8)
    # =========================================================================
    # If message contains keywords from 2+ departments, fall to LLM immediately
    # This ensures messages like "toallas y aire" trigger clarification flow

    all_pattern_groups = [
        ("GERENCIA", GERENCIA_PATTERNS),
        ("RECEPCION", RECEPCION_PATTERNS),
        ("MANTENCION", MANTENCION_PATTERNS),
        ("HOUSEKEEPING", HOUSEKEEPING_PATTERNS),
    ]

    matches_per_area = {}
    for area_code, patterns in all_pattern_groups:
        for pattern, reason, confidence in patterns:
            if re.search(pattern, normalized):
                if area_code not in matches_per_area:
                    matches_per_area[area_code] = []
                matches_per_area[area_code].append((reason, confidence))

    # If 2+ different areas matched, it's a multi-department request
    if len(matches_per_area) >= 2:
        # Fall to LLM - it will classify as SUPERVISION with low confidence,
        # triggering the clarification flow
        return None

    # =========================================================================
    # STEP 2: Single-department routing (priority order)
    # =========================================================================
    # Order matters: GERENCIA > RECEPCION > MANTENCION > HOUSEKEEPING
    # (complaints should be caught before generic keywords)

    for area_code, patterns in all_pattern_groups:
        for pattern, reason, confidence in patterns:
            if re.search(pattern, normalized):
                # Found a match!
                return {
                    "area": area_code,
                    "confidence": confidence,
                    "reason": reason,
                }

    # No patterns matched → return None (will fall back to LLM)
    return None
