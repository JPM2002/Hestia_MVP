# gateway_app/services/faq_llm.py
"""
FAQ helper module for the WhatsApp guest assistant.

Responsibilities:
- Define a simple FAQ data structure (key, question, answer).
- Provide a best-effort matcher from a user's short message to an FAQ entry.
- Optionally use an LLM to answer based on the FAQ list when lexical matching fails.

Typical usage from the state machine / webhook:

    from gateway_app.services import faq_llm

    answer = faq_llm.answer_faq(inbound_text)
    if answer:
        # send FAQ answer and optionally keep conversation in FAQ state
        ...

You can later:
- Replace FAQ_ITEMS with hotel-specific items loaded from a DB.
- Tune thresholds or completely replace matching logic.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, List, Mapping, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

_client = OpenAI()
FAQ_LLM_MODEL = os.getenv("FAQ_LLM_MODEL", "gpt-4.1-mini")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FAQItem:
    key: str
    q: str
    a: str


#: Default, generic FAQ set. Replace/extend per hotel as needed.
FAQ_ITEMS: List[FAQItem] = [
    FAQItem(
        key="checkin_time",
        q="¿A qué hora es el check-in?",
        a="El check-in es a partir de las 15:00.",
    ),
    FAQItem(
        key="checkout_time",
        q="¿A qué hora es el check-out?",
        a="El check-out es hasta las 12:00.",
    ),
    FAQItem(
        key="breakfast_time",
        q="¿En qué horario se sirve el desayuno?",
        a="El desayuno se sirve de 7:00 a 10:30 en el restaurante principal.",
    ),
    FAQItem(
        key="wifi",
        q="¿Cómo funciona el wifi del hotel?",
        a="La red Wi-Fi es gratuita; el nombre y la clave se encuentran en la tarjeta de la habitación.",
    ),
    # Añade aquí FAQs genéricas; para producción, carga desde DB o configuración.
]


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """
    Normalize text for rough matching:
    - Lowercase
    - Strip accents
    - Remove punctuation except spaces
    - Collapse whitespace
    """
    if not text:
        return ""

    text = text.strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9ñáéíóúü ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Static matching (no LLM)
# ---------------------------------------------------------------------------


def _best_static_match(
    user_text: str,
    faq_items: Iterable[FAQItem],
    min_overlap: float = 0.5,
) -> Optional[FAQItem]:
    """
    Very simple token-overlap matcher between the normalized user text and each FAQ question.

    - Computes overlap = |tokens_user ∩ tokens_question| / |tokens_question|.
    - Returns the FAQ with highest overlap, if >= min_overlap.
    """
    norm_user = _normalize(user_text)
    if not norm_user:
        return None

    user_tokens = set(norm_user.split())
    if not user_tokens:
        return None

    best_item: Optional[FAQItem] = None
    best_score = 0.0

    for item in faq_items:
        norm_q = _normalize(item.q)
        q_tokens = set(norm_q.split())
        if not q_tokens:
            continue

        overlap = len(user_tokens & q_tokens) / float(len(q_tokens))
        if overlap > best_score:
            best_score = overlap
            best_item = item

    if best_item and best_score >= min_overlap:
        logger.debug(
            "FAQ static match",
            extra={"key": best_item.key, "score": best_score, "user": user_text},
        )
        return best_item

    return None


# ---------------------------------------------------------------------------
# LLM-based matching as fallback
# ---------------------------------------------------------------------------

_FAQ_SYSTEM_PROMPT = """
You are an FAQ assistant for a hotel WhatsApp bot (Hestia).

You receive:
- A list of FAQs (question + answer).
- A short guest message.

Your job:
1) Decide if the guest message matches one of the existing FAQs.
2) If it matches, answer using ONLY the information in the FAQ list.
3) If it does NOT match any FAQ, answer with exactly: NO_MATCH

Constraints:
- Always answer in the same language as the guest (mostly Spanish).
- Be concise and friendly when answering.
"""


def _call_faq_llm(user_text: str, faq_items: Iterable[FAQItem]) -> Optional[str]:
    """
    Ask the LLM to pick or synthesize an answer from the FAQ list.

    Returns:
        - A short answer as string, or
        - None if the LLM decides there is no relevant FAQ (NO_MATCH or error).
    """
    faq_block_lines = []
    for item in faq_items:
        faq_block_lines.append(f"- [{item.key}] Q: {item.q}\n  A: {item.a}")
    faq_block = "\n".join(faq_block_lines)

    try:
        resp = _client.responses.create(
            model=FAQ_LLM_MODEL,
            input=[
                {"role": "system", "content": _FAQ_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"FAQs:\n{faq_block}\n\n"
                        f"Mensaje del huésped:\n{user_text}\n\n"
                        "Responde solo con la respuesta final o NO_MATCH."
                    ),
                },
            ],
            max_output_tokens=256,
        )
        text = resp.output[0].content[0].text.strip()
    except Exception:
        logger.exception("FAQ LLM call failed")
        return None

    if not text or text.upper().startswith("NO_MATCH"):
        return None
    return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def answer_faq(
    user_text: str,
    faq_items: Optional[Iterable[FAQItem]] = None,
    use_llm_fallback: bool = True,
) -> Optional[str]:
    """
    Try to answer `user_text` using the FAQ list.

    Strategy:
    1) Try static token-overlap matching (fast, deterministic).
    2) If no static match and use_llm_fallback=True, ask the LLM to reason over the FAQ list.

    Returns:
        - The answer text (string) if a relevant FAQ was found.
        - None if no FAQ applies.
    """
    items = list(faq_items) if faq_items is not None else FAQ_ITEMS

    # 1) Static match first
    static_item = _best_static_match(user_text, items)
    if static_item:
        return static_item.a

    # 2) Optional LLM fallback
    if use_llm_fallback:
        llm_answer = _call_faq_llm(user_text, items)
        return llm_answer

    return None


def has_faq_match(user_text: str, faq_items: Optional[Iterable[FAQItem]] = None) -> bool:
    """
    Convenience helper: returns True if `answer_faq` finds any match.
    """
    return answer_faq(user_text, faq_items=faq_items, use_llm_fallback=False) is not None
