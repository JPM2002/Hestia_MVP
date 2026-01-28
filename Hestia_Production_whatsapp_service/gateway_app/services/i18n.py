# gateway_app/services/i18n.py
from __future__ import annotations

import re
from typing import Literal, Optional

Lang = Literal["es", "en", "pt"]

# ---------------------------------------------------------------------
# Phrase table (used by FAQ handler + other hardcoded messages)
# ---------------------------------------------------------------------

_PHRASES: dict[str, dict[Lang, str]] = {
    "faq_more_help": {
        "es": "¿Puedo ayudarte con algo más durante tu estadía?",
        "en": "Can I help you with anything else during your stay?",
        "pt": "Posso ajudar com mais alguma coisa durante a sua estadia?",
    },
    "reception_fallback": {
        "es": (
            "Para resolver esta duda te pedimos llamar a recepción al *100 o 101+OK* "
            "desde el teléfono de tu habitación.\n\n"
            "Si necesitas que gestionemos algo (ej. pedir algo a la habitación), "
            "dime 'Necesito...' y lo registramos. 😊"
        ),
        "en": (
            "To clarify this, please call Reception at *100 or 101+OK* from your room phone.\n\n"
            "If you need us to arrange something (e.g., bring something to your room), "
            "tell me “I need…” and I’ll log it. 😊"
        ),
        "pt": (
            "Para esclarecer esta dúvida, pedimos que ligue para a Recepção no *100 ou 101+OK* "
            "usando o telefone do seu quarto.\n\n"
            "Se precisar que a gente organize algo (ex.: levar algo ao quarto), "
            "diga “Preciso...” e nós registramos. 😊"
        ),
    },
}

def normalize_lang(lang: Optional[str]) -> Lang:
    if not lang:
        return "es"
    l = lang.strip().lower()
    if l.startswith("en"):
        return "en"
    if l.startswith("pt"):
        return "pt"
    return "es"

def get_phrase(key: str, lang: Optional[str]) -> str:
    l = normalize_lang(lang)
    return _PHRASES.get(key, {}).get(l) or _PHRASES.get(key, {}).get("es") or ""

# ---------------------------------------------------------------------
# Language detection (heuristic, no external deps)
# ---------------------------------------------------------------------

_EN_MARKERS = {
    "how", "what", "where", "when", "why", "please", "thanks", "thank",
    "room", "key", "password", "wifi", "tv", "remote", "does", "doesn't", "not",
}
_ES_MARKERS = {
    "¿", "¡", "qué", "que", "cómo", "como", "dónde", "donde", "cuándo", "cuando",
    "cuál", "cual", "habitación", "habitacion", "clave", "prendo", "enciende",
    "recepción", "recepcion", "gracias",
}
_PT_MARKERS = {
    "como", "quarto", "senha", "ligo", "ligar", "desligar", "recepção", "recepcao",
    "você", "voce", "não", "nao", "obrigado", "obrigada", "por favor",
}

_PT_DIACRITICS_RE = re.compile(r"[ãõç]")   # strong PT hints
_ES_DIACRITICS_RE = re.compile(r"[ñ¡¿]")   # strong ES hints

def detect_language(text: str, default: Lang = "es") -> Lang:
    """
    Best-effort language detection for ES/EN/PT.
    Used to:
    - store session['language']
    - force FAQ LLM response language
    """
    if not text:
        return default

    t = text.strip().lower()

    # strong diacritic signals first
    if _PT_DIACRITICS_RE.search(t):
        return "pt"
    if _ES_DIACRITICS_RE.search(t):
        return "es"

    # count marker hits
    en_score = sum(1 for w in _EN_MARKERS if w in t)
    es_score = sum(1 for w in _ES_MARKERS if w in t)
    pt_score = sum(1 for w in _PT_MARKERS if w in t)

    # question mark + English structure often
    if "?" in t and any(w in t for w in ("how", "what", "where", "when")):
        en_score += 2

    # Portuguese “do/da/no/na” combined with “quarto/senha/ligar” hints
    if any(w in t for w in ("quarto", "senha", "lig")) and any(w in t.split() for w in ("do", "da", "no", "na")):
        pt_score += 2

    best = max((("en", en_score), ("es", es_score), ("pt", pt_score)), key=lambda x: x[1])
    if best[1] == 0:
        return default

    # tie-breaker: default to session language later; here prefer ES
    return best[0]  # type: ignore[return-value]

def is_language_match(text: str, target: Optional[str]) -> bool:
    """
    Returns True if `text` appears to be in target language OR is too ambiguous to be confident.
    """
    tgt = normalize_lang(target)
    detected = detect_language(text, default=tgt)

    # If detection is weak/ambiguous, we accept (avoid over-triggering extra LLM calls).
    # Heuristic: very short answers can be ambiguous; accept them.
    if len((text or "").strip()) < 12:
        return True

    return detected == tgt
