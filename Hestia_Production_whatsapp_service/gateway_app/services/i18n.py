# gateway_app/services/i18n.py
from __future__ import annotations

import re
from typing import Literal, Optional

Lang = Literal["es", "en", "pt"]

# ---------------------------------------------------------------------
# Phrase table
# ---------------------------------------------------------------------

_PHRASES: dict[str, dict[Lang, str]] = {
    # --- FAQ flow ---
    "faq_more_help": {
        "es": "¿Puedo ayudarte con algo más durante tu estadía?",
        "en": "Can I help you with anything else during your stay?",
        "pt": "Posso ajudar com mais alguma coisa durante a sua estadia?",
    },
    "reception_fallback": {
        "es": (
            "Para resolver esta duda te pedimos llamar a recepción al *0 o 1* "
            "desde el teléfono de tu habitación.\n\n"
            "Si necesitas que gestionemos algo (ej. pedir algo a la habitación), "
            "dime 'Necesito...' y lo registramos. 😊"
        ),
        "en": (
            "To clarify this, please call Reception at *0 or 1* from your room phone.\n\n"
            "If you need us to arrange something (e.g., bring something to your room), "
            "tell me “I need…” and I’ll log it. 😊"
        ),
        "pt": (
            "Para esclarecer esta dúvida, pedimos que ligue para a Recepção no *0 ou 1* "
            "usando o telefone do seu quarto.\n\n"
            "Se precisar que a gente organize algo (ex.: levar algo ao quarto), "
            "diga “Preciso...” e nós registramos. 😊"
        ),
    },

    # --- Language switch confirmation (NO FAQ) ---
    "language_switch_confirm": {
        "es": "Perfecto — puedo ayudarte en español. ¿En qué te puedo ayudar?",
        "en": "Perfect — I can help you in English. How can I help you?",
        "pt": "Perfeito — posso ajudar em português. Em que posso ajudar?",
    },

    # --- Welcome / smalltalk / help / menu ---
    "initial_greeting": {
        "es": (
            "Hola{name_part} Te damos la bienvenida a nuestro servicio de asistencia digital.\n"
            "Para poder ayudarte rápidamente, por favor indícame tu número de habitación y cuál es tu consulta o solicitud."
        ),
        "en": (
            "Hi{name_part} Welcome to our digital guest assistant.\n"
            "To help you quickly, please tell me your room number and what you need."
        ),
        "pt": (
            "Olá{name_part} Bem-vindo(a) ao nosso assistente digital.\n"
            "Para ajudar mais rápido, por favor informe o número do quarto e o que você precisa."
        ),
    },
    "smalltalk_greeting": {
        "es": "Hola, ¿en qué puedo ayudarte?",
        "en": "Hi — how can I help you?",
        "pt": "Olá — em que posso ajudar?",
    },
    "smalltalk_thanks": {
        "es": "Con gusto. Estoy aquí para ayudarte durante tu estadía. ¿Algo más?",
        "en": "You’re welcome. I’m here to help during your stay. Anything else?",
        "pt": "De nada. Estou aqui para ajudar durante a sua estadia. Mais alguma coisa?",
    },
    "smalltalk_ok": {
        "es": "Perfecto. Si necesitas algo más, escríbeme por aquí.",
        "en": "Perfect. If you need anything else, just message me here.",
        "pt": "Perfeito. Se precisar de mais alguma coisa, é só me chamar aqui.",
    },
    "smalltalk_default": {
        "es": "Entendido. Cualquier cosa que necesites, solo escríbeme por aquí.",
        "en": "Got it. If you need anything, just message me here.",
        "pt": "Entendido. Se precisar de algo, é só me chamar aqui.",
    },
    "help_message": {
        "es": (
            "Puedo ayudarte con:\n"
            "• Reportar problemas en tu habitación (aire, ducha, luz, limpieza, etc.).\n"
            "• Pedir toallas, almohadas u otros artículos.\n"
            "• Responder dudas típicas: desayuno, wifi, check-in / check-out.\n\n"
            "Escríbeme en una frase qué necesitas y me encargo del resto."
        ),
        "en": (
            "I can help you with:\n"
            "• Reporting room issues (AC, shower, lights, cleaning, etc.).\n"
            "• Requesting items (towels, pillows, amenities).\n"
            "• Answering common questions: breakfast, Wi-Fi, check-in / check-out.\n\n"
            "Tell me in one sentence what you need and I’ll take care of it."
        ),
        "pt": (
            "Posso ajudar com:\n"
            "• Problemas no quarto (ar, chuveiro, luz, limpeza, etc.).\n"
            "• Pedidos (toalhas, travesseiros, amenities).\n"
            "• Dúvidas comuns: café da manhã, Wi-Fi, check-in / check-out.\n\n"
            "Me diga em uma frase o que você precisa e eu resolvo."
        ),
    },
    "menu_message": {
        "es": (
            "Menú de ayuda Hestia:\n"
            "1️⃣ Reportar un problema en la habitación.\n"
            "2️⃣ Pedir algo (toallas, amenities, etc.).\n"
            "3️⃣ Preguntar información (desayuno, wifi, horarios, etc.).\n\n"
            "Cuéntame brevemente qué necesitas y te ayudo."
        ),
        "en": (
            "Hestia help menu:\n"
            "1️⃣ Report a room issue.\n"
            "2️⃣ Request something (towels, amenities, etc.).\n"
            "3️⃣ Ask for information (breakfast, Wi-Fi, hours, etc.).\n\n"
            "Tell me briefly what you need and I’ll help."
        ),
        "pt": (
            "Menu de ajuda Hestia:\n"
            "1️⃣ Reportar um problema no quarto.\n"
            "2️⃣ Pedir algo (toalhas, amenities, etc.).\n"
            "3️⃣ Perguntar informações (café da manhã, Wi-Fi, horários, etc.).\n\n"
            "Me diga rapidamente o que você precisa e eu ajudo."
        ),
    },

    # --- Generic system replies ---
    "cancel_confirm": {
        "es": "He cancelado la solicitud actual. Si necesitas algo más, escríbeme por aquí.",
        "en": "I’ve cancelled the current request. If you need anything else, message me here.",
        "pt": "Cancelei a solicitação atual. Se precisar de mais alguma coisa, me chame aqui.",
    },
    "handoff_confirm": {
        "es": "De acuerdo, te pongo en contacto con recepción humana. Un momento por favor.",
        "en": "Alright — I’ll connect you with the front desk. One moment, please.",
        "pt": "Certo — vou te colocar em contato com a recepção. Um momento, por favor.",
    },
    "fallback_generic": {
        "es": (
            "Gracias por tu mensaje. Si quieres, cuéntame si necesitas reportar un problema, "
            "pedir algo a la habitación o hacer una pregunta sobre el hotel."
        ),
        "en": (
            "Thanks for your message. Tell me if you want to report an issue, request something, "
            "or ask a question about the hotel."
        ),
        "pt": (
            "Obrigado(a) pela mensagem. Me diga se você quer reportar um problema, pedir algo, "
            "ou fazer uma pergunta sobre o hotel."
        ),
    },

    # --- Identity / ticket confirmations (used in core flows) ---
    "identity_request": {
        "es": (
            "Para poder ayudarte mejor, necesito confirmar algunos datos:\n\n"
            "📝 ¿Cuál es tu nombre completo?\n"
            "🏨 ¿En qué número de habitación te encuentras?"
        ),
        "en": (
            "To help you, I just need to confirm:\n\n"
            "📝 Your full name\n"
            "🏨 Your room number"
        ),
        "pt": (
            "Para ajudar, preciso confirmar:\n\n"
            "📝 Seu nome completo\n"
            "🏨 Número do seu quarto"
        ),
    },
    "identity_missing_fields": {
        "es": "Gracias, pero aún necesito tu {missing}. ¿Puedes proporcionarlo?",
        "en": "Thanks — I still need your {missing}. Could you provide it?",
        "pt": "Obrigado(a) — ainda preciso do(a) seu(sua) {missing}. Você pode informar?",
    },
    "ticket_confirm": {
        "es": (
            "Perfecto, {name}. Voy a notificar al equipo de {area} sobre:\n\n"
            "📝 {detail}\n"
            "🏨 Habitación {room}\n\n"
            "¿Confirmas? (Sí/No)"
        ),
        "en": (
            "Perfect, {name}. I’ll notify {area} about:\n\n"
            "📝 {detail}\n"
            "🏨 Room {room}\n\n"
            "Please confirm (Yes/No)"
        ),
        "pt": (
            "Perfeito, {name}. Vou avisar a equipe de {area} sobre:\n\n"
            "📝 {detail}\n"
            "🏨 Quarto {room}\n\n"
            "Confirma? (Sim/Não)"
        ),
    },
    "ticket_created_success": {
        "es": "¡Listo! Ya notifiqué al equipo de {area} sobre tu solicitud en la habitación {room}. Te avisaré cuando esté resuelto. ✅",
        "en": "All set! I notified {area} about your request in room {room}. I’ll message you when it’s resolved. ✅",
        "pt": "Pronto! Avisei {area} sobre sua solicitação no quarto {room}. Vou te avisar quando estiver resolvido. ✅",
    },
    "ticket_created_error": {
        "es": "Intenté crear tu ticket, pero hubo un problema con el sistema interno. Recepción ha sido notificada.",
        "en": "I tried to create your ticket, but there was an internal system issue. The front desk has been notified.",
        "pt": "Tentei criar seu ticket, mas houve um problema interno. A recepção foi avisada.",
    },
}

_AREA_NAMES: dict[str, dict[Lang, str]] = {
    "MANTENCION": {"es": "Mantenimiento", "en": "Maintenance", "pt": "Manutenção"},
    "HOUSEKEEPING": {"es": "Housekeeping", "en": "Housekeeping", "pt": "Housekeeping"},
    "RECEPCION": {"es": "Recepción", "en": "Front Desk", "pt": "Recepção"},
    "GERENCIA": {"es": "Gerencia", "en": "Management", "pt": "Gerência"},
    "SUPERVISION": {"es": "Supervisión", "en": "Supervision", "pt": "Supervisão"},
    "ROOMSERVICE": {"es": "Recepción", "en": "Front Desk", "pt": "Recepção"},  # schema compatibility
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

def get_phrase(key: str, lang: Optional[str], **kwargs) -> str:
    l = normalize_lang(lang)
    template = _PHRASES.get(key, {}).get(l) or _PHRASES.get(key, {}).get("es") or ""
    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template

def area_name(area_code: Optional[str], lang: Optional[str]) -> str:
    l = normalize_lang(lang)
    code = (area_code or "").strip().upper()
    return (_AREA_NAMES.get(code, {}).get(l) or _AREA_NAMES.get(code, {}).get("es") or (area_code or ""))

# ---------------------------------------------------------------------
# Language commands (explicit override)
# ---------------------------------------------------------------------

_LANG_CMD_EN = re.compile(
    r"^\s*(?:in\s+)?(?:english|en)\s*(?:please|pls)?\s*$|^\s*speak\s+english\s*$",
    re.IGNORECASE,
)
_LANG_CMD_ES = re.compile(
    r"^\s*(?:en\s+)?(?:espanol|español|spanish|es)\s*(?:por\s+favor|please|pls)?\s*$|^\s*habla\s+espa(?:n|ñ)ol\s*$",
    re.IGNORECASE,
)
_LANG_CMD_PT = re.compile(
    r"^\s*(?:em\s+)?(?:portugues|português|portuguese|pt)\s*(?:por\s+favor|please|pls)?\s*$|^\s*fala\s+portugu(?:e|ê)s\s*$",
    re.IGNORECASE,
)

def detect_language_command(text: str) -> Optional[Lang]:
    """
    Returns "en" / "es" / "pt" if the message is primarily a language preference command.
    Otherwise returns None.
    """
    if not text:
        return None
    t = (text or "").strip()
    # strip trailing punctuation
    t = re.sub(r"[!?\.]+$", "", t).strip()

    if _LANG_CMD_EN.match(t):
        return "en"
    if _LANG_CMD_ES.match(t):
        return "es"
    if _LANG_CMD_PT.match(t):
        return "pt"
    return None

# ---------------------------------------------------------------------
# Language detection (heuristic, no external deps)
# ---------------------------------------------------------------------
_EN_MARKERS = {
    # greetings / common
    "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
    "please", "thanks", "thank",

    # common assistant / hotel words
    "how", "what", "where", "when", "why",
    "room", "key", "password", "wifi", "tv", "remote",
    "hotel", "breakfast", "check-in", "check-out",
    "allowed", "allow", "pet", "pets", "pet-friendly",

    # common model answer words (IMPORTANT for your bug)
    "you", "your", "can",
    "pay", "payment", "card", "cards",
    "bank", "transfer", "transfers",
    "dollar", "dollars",
    "possible", "split", "between", "among",
    "several", "people", "also", "yes",
}

_ES_MARKERS = {
    "¿", "¡",
    "qué", "que", "cómo", "como", "dónde", "donde", "cuándo", "cuando",
    "cuál", "cual",
    "habitación", "habitacion",
    "clave",
    "recepción", "recepcion",
    "gracias", "hola", "buenos dias", "buenas tardes", "buenas noches",
    "mascota", "mascotas", "aceptan",
    "pago", "pagos", "pagar", "tarjeta", "tarjetas", "transferencia",
}

_PT_MARKERS = {
    "oi", "olá", "ola", "bom dia", "boa tarde", "boa noite",
    "você", "voce", "não", "nao", "obrigado", "obrigada", "por favor",
    "quarto", "senha", "ligo", "ligar", "desligar",
    "recepção", "recepcao",

    # IMPORTANT: words from your failing PT question
    "quais", "qual", "forma", "formas",
    "pagamento", "pagar",
    "aceita", "aceitam", "aceitar",
    "cartão", "cartao", "cartões", "cartoes",
    "transferência", "transferencia",
    "dólar", "dolar", "dividir", "entre", "pessoas",
    "hotel",
}

_PT_DIACRITICS_RE = re.compile(r"[ãõç]")   # strong PT hints
_ES_DIACRITICS_RE = re.compile(r"[ñ¡¿]")   # strong ES hints

_EN_START_RE = re.compile(r"^\s*(is|are|do|does|can|could|would|should|may|might)\b", re.IGNORECASE)

def detect_language_strict(text: str) -> Optional[Lang]:
    """
    Returns detected Lang if there is evidence; otherwise None.
    (Same heuristics as detect_language, but does NOT fall back to a default.)
    """
    if not text:
        return None

    t = text.strip().lower()

    # Strong diacritic signals first
    if _PT_DIACRITICS_RE.search(t):
        return "pt"
    if _ES_DIACRITICS_RE.search(t):
        return "es"

    # Single-word greeting heuristics
    t_simple = re.sub(r"[^a-záéíóúñãõç\s\-]", "", t).strip()
    if t_simple in {"hi", "hello", "good morning", "good afternoon", "good evening"}:
        return "en"
    if t_simple in {"oi", "olá", "ola", "bom dia", "boa tarde", "boa noite"}:
        return "pt"
    if t_simple in {"hola", "buenos dias", "buenas tardes", "buenas noches"}:
        return "es"

    # count marker hits (substring-based, consistent with your existing approach)
    en_score = sum(1 for w in _EN_MARKERS if w in t)
    es_score = sum(1 for w in _ES_MARKERS if w in t)
    pt_score = sum(1 for w in _PT_MARKERS if w in t)

    # English question structure
    if "?" in t and _EN_START_RE.search(t):
        en_score += 3

    best_lang, best_score = max(
        (("en", en_score), ("es", es_score), ("pt", pt_score)),
        key=lambda x: x[1],
    )

    if best_score == 0:
        return None

    return best_lang  # type: ignore[return-value]


def detect_language(text: str, default: Lang = "es") -> Lang:
    """
    Backwards-compatible: returns ES/EN/PT, falls back to default when uncertain.
    """
    detected = detect_language_strict(text)
    return detected or default


def is_language_match(text: str, target: Optional[str]) -> bool:
    """
    True if `text` appears to be in target language OR too ambiguous.
    Fix: avoid using default=tgt in detection because it hides unknowns.
    """
    tgt = normalize_lang(target)
    if len((text or "").strip()) < 12:
        return True

    detected = detect_language_strict(text)
    if detected is None:
        return True  # ambiguous => don't force translate

    return detected == tgt
