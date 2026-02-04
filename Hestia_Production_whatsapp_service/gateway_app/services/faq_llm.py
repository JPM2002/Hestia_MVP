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
from typing import Iterable, List, Mapping, Optional, Any, Tuple, Dict


from openai import OpenAI
from gateway_app.services.ai.prompt_loader import get_faq_system_prompt
from gateway_app.services.data.faq_loader import load_faq_items
from gateway_app.services.token_tracker import extract_token_usage, TokenUsage
from gateway_app.services.i18n import detect_language, is_language_match, normalize_lang, detect_language_command


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


# Load FAQ items from external JSON file for easier maintenance
# This replaces the hardcoded list that was previously here (240 items)
# Now FAQs can be updated without modifying code
try:
    FAQ_ITEMS: List[Dict[str, str]] = load_faq_items()
    logger.info(f"[FAQ] Successfully loaded {len(FAQ_ITEMS)} FAQ items from JSON")
except Exception as e:
    logger.error(f"[FAQ] Failed to load FAQ items from JSON: {e}")
    # Fallback to empty list if loading fails
    FAQ_ITEMS: List[Dict[str, str]] = []


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


def _get_field(item: Any, field: str, default: str = "") -> str:
    """
    Safely read a field ('key', 'q', 'a') from either:
    - a dict with that key, or
    - a dataclass/obj with that attribute.
    """
    if isinstance(item, Mapping):
        return str(item.get(field, default) or "")
    return str(getattr(item, field, default) or "")


# ---------------------------------------------------------------------------
# Static matching (no LLM)
# ---------------------------------------------------------------------------

def _best_static_match(
    user_text: str,
    faq_items: Iterable[Any],
) -> tuple[Optional[Any], float]:
    """
    Very simple token-overlap matcher between the normalized user text and each FAQ question.

    - Computes overlap = |tokens_user ∩ tokens_question| / |tokens_question|.
    - Returns (best_item, best_score).
    """
    norm_user = _normalize(user_text)
    if not norm_user:
        logger.debug(
            "[FAQ STATIC] 🔍 Empty user text after normalization",
            extra={
                "user_text": user_text,
                "location": "gateway_app/services/faq_llm.py::_best_static_match"
            }
        )
        return None, 0.0

    user_tokens = set(norm_user.split())
    if not user_tokens:
        logger.debug(
            "[FAQ STATIC] 🔍 No tokens after splitting",
            extra={
                "user_text": user_text,
                "normalized": norm_user,
                "location": "gateway_app/services/faq_llm.py::_best_static_match"
            }
        )
        return None, 0.0

    logger.info(
        "[FAQ STATIC] 🔍 Starting static matching",
        extra={
            "user_text": user_text,
            "normalized": norm_user,
            "user_tokens": list(user_tokens),
            "token_count": len(user_tokens),
            "location": "gateway_app/services/faq_llm.py::_best_static_match"
        }
    )

    best_item: Optional[Any] = None
    best_score = 0.0
    matches_found = []

    for item in faq_items:
        q_text = _get_field(item, "q")
        if not q_text:
            continue

        norm_q = _normalize(q_text)
        q_tokens = set(norm_q.split())
        if not q_tokens:
            continue

        overlap = len(user_tokens & q_tokens) / float(len(q_tokens))

        # Track top matches for logging
        if overlap > 0.3:  # Only log matches above 30%
            matches_found.append({
                "key": _get_field(item, "key"),
                "question": q_text,
                "score": overlap,
                "overlapping_tokens": list(user_tokens & q_tokens)
            })

        if overlap > best_score:
            best_score = overlap
            best_item = item

    # Log all significant matches
    if matches_found:
        matches_found.sort(key=lambda x: x["score"], reverse=True)
        logger.info(
            "[FAQ STATIC] 📊 Found potential matches",
            extra={
                "user_text": user_text,
                "top_3_matches": matches_found[:3],
                "total_matches": len(matches_found),
                "location": "gateway_app/services/faq_llm.py::_best_static_match"
            }
        )

    if best_item:
        logger.info(
            "[FAQ STATIC] ✅ Best static match found",
            extra={
                "key": _get_field(best_item, "key"),
                "question": _get_field(best_item, "q"),
                "answer_preview": _get_field(best_item, "a")[:100],
                "score": best_score,
                "user_text": user_text,
                "location": "gateway_app/services/faq_llm.py::_best_static_match"
            },
        )
    else:
        logger.info(
            "[FAQ STATIC] ❌ No static match found",
            extra={
                "user_text": user_text,
                "best_score": best_score,
                "location": "gateway_app/services/faq_llm.py::_best_static_match"
            }
        )

    return best_item, best_score


# ---------------------------------------------------------------------------
# LLM-based matching as fallback
# ---------------------------------------------------------------------------

# Load prompt from external file for easier maintenance and versioning
_FAQ_SYSTEM_PROMPT = get_faq_system_prompt(version="v1")


def _call_faq_llm(user_text: str, faq_items: Iterable[Any], target_lang: str) -> Tuple[Optional[str], Optional[TokenUsage]]:
    """
    Ask the LLM to pick or synthesize an answer from the FAQ list.

    Returns:
        Tuple of (answer, token_usage):
        - answer: A short answer as string, or None if the LLM decides there is no relevant FAQ (NO_MATCH or error)
        - token_usage: TokenUsage object with input/output tokens, or None if extraction fails
    """
    faq_block_lines = []
    for item in faq_items:
        key = _get_field(item, "key")
        q = _get_field(item, "q")
        a = _get_field(item, "a")
        if not q or not a:
            continue
        faq_block_lines.append(f"- [{key}] Q: {q}\n  A: {a}")
    faq_block = "\n".join(faq_block_lines)

    if not faq_block:
        logger.warning(
            "[FAQ LLM] ⚠️ No FAQ items to process",
            extra={
                "user_text": user_text,
                "location": "gateway_app/services/faq_llm.py::_call_faq_llm"
            }
        )
        return None, None
    
    tgt = normalize_lang(target_lang)
    lang_label = {"es": "Spanish (ES)", "en": "English (EN)", "pt": "Portuguese (PT)"}.get(tgt, "English (EN)")



    user_prompt = (
        f"Guest language: {lang_label}. IMPORTANT: Respond ONLY in {lang_label}.\n\n"
        f"FAQs:\n{faq_block}\n\n"
        f"Mensaje del huésped:\n{user_text}\n\n"
        "Responde solo con la respuesta final o NO_MATCH."
        
    )

    logger.info(
        "[FAQ LLM] 🤖 Sending request to LLM",
        extra={
            "model": FAQ_LLM_MODEL,
            "user_text": user_text,
            "faq_count": len(faq_block_lines),
            "prompt_length": len(user_prompt),
            "location": "gateway_app/services/faq_llm.py::_call_faq_llm"
        }
    )

    try:
        resp = _client.responses.create(
            model=FAQ_LLM_MODEL,
            input=[
                {"role": "system", "content": _FAQ_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_output_tokens=256,
        )
        text = resp.output[0].content[0].text.strip()

        # Extract token usage from response
        token_usage = extract_token_usage(resp)

        # Debug: Log response structure (changed to INFO for visibility)
        if hasattr(resp, 'usage'):
            usage_dict = {k: getattr(resp.usage, k, None) for k in dir(resp.usage) if not k.startswith('_')}
            logger.info(
                "[FAQ LLM] 🔍 Debug response structure",
                extra={
                    "has_usage": True,
                    "has_output": hasattr(resp, 'output'),
                    "usage_type": type(resp.usage).__name__,
                    "usage_dict": usage_dict,
                    "location": "gateway_app/services/faq_llm.py::_call_faq_llm"
                }
            )

        logger.info(
            "[FAQ LLM] 📥 LLM response received",
            extra={
                "model": FAQ_LLM_MODEL,
                "user_text": user_text,
                "llm_response": text,
                "response_length": len(text),
                "token_usage": str(token_usage) if token_usage else None,
                "location": "gateway_app/services/faq_llm.py::_call_faq_llm"
            }
        )
    except Exception as e:
        logger.exception(
            "[FAQ LLM] ❌ LLM call failed with exception",
            extra={
                "model": FAQ_LLM_MODEL,
                "user_text": user_text,
                "error": str(e),
                "location": "gateway_app/services/faq_llm.py::_call_faq_llm"
            }
        )
        return None, None

    if not text or text.upper().startswith("NO_MATCH"):
        logger.info(
            "[FAQ LLM] 🚫 LLM returned NO_MATCH",
            extra={
                "user_text": user_text,
                "llm_response": text,
                "token_usage": str(token_usage) if token_usage else None,
                "location": "gateway_app/services/faq_llm.py::_call_faq_llm"
            }
        )
        return None, token_usage  # Still return token usage even if no match

    logger.info(
        "[FAQ LLM] ✅ LLM found valid answer",
        extra={
            "user_text": user_text,
            "llm_response": text,
            "token_usage": str(token_usage) if token_usage else None,
            "location": "gateway_app/services/faq_llm.py::_call_faq_llm"
        }
    )
    return text, token_usage


def _translate_answer(text: str, target_lang: str) -> Optional[str]:
    """
    Best-effort translation (used only when the FAQ answer is not in guest language).
    Uses the same model and strict instructions: translate only, no new facts.
    """
    if not text:
        return None
    tgt = normalize_lang(target_lang)
    lang_label = {"es": "Spanish", "en": "English", "pt": "Portuguese"}[tgt]

    system = (
        "You are a precise translation engine.\n"
        "Translate the user-provided text to {LANG}.\n"
        "Rules:\n"
        "- Preserve meaning and facts exactly.\n"
        "- Do NOT add new information.\n"
        "- Keep numbers, times, and names unchanged.\n"
        "- Return ONLY the translated text.\n"
    ).replace("{LANG}", lang_label)

    try:
        resp = _client.responses.create(
            model=FAQ_LLM_MODEL,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            max_output_tokens=256,
        )
        out = resp.output[0].content[0].text.strip()
        return out or None
    except Exception:
        logger.exception("[FAQ TRANSLATE] Translation failed")
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def answer_faq(
    user_text: str,
    faq_items: Optional[Iterable[FAQItem]] = None,
    use_llm_fallback: bool = True,
    session_lang: Optional[str] = None,
) -> Tuple[Optional[str], Optional[TokenUsage]]:

    """
    Try to answer `user_text` using the FAQ list.

    Strategy:
    1) Try a very strict static token-overlap matching (only for near-identical questions).
    2) If no strong static match and use_llm_fallback=True, ask the LLM to reason over the FAQ list.

    Returns:
        Tuple of (answer, token_usage):
        - answer: The answer text (string) if a relevant FAQ was found, or None if no FAQ applies
        - token_usage: TokenUsage object if LLM was called, or None if static match or no LLM call
    """
    logger.info(
        "[FAQ] 🔍 Starting FAQ search",
        extra={
            "user_text": user_text,
            "use_llm_fallback": use_llm_fallback,
            "location": "gateway_app/services/faq_llm.py"
        }
    )

    # ✅ Guard: language preference commands are NOT FAQ queries
    if detect_language_command(user_text):
        return None, None

    target_lang = normalize_lang(session_lang or detect_language(user_text))

    logger.info(
    "[FAQ] 🌍 Language decision",
    extra={
        "user_text": user_text,
        "session_lang": session_lang,
        "detected_lang_raw": detect_language(user_text),
        "target_lang_normalized": target_lang,
        "location": "gateway_app/services/faq_llm.py::answer_faq"
    }
)


    items = list(faq_items) if faq_items is not None else FAQ_ITEMS

    # 1) Static match (ONLY if almost identical).
    static_item, static_score = _best_static_match(user_text, items)

    # threshold can be tuned; 0.85–0.9 means "very similar"
    STATIC_STRONG_THRESHOLD = 0.85

    if static_item and static_score >= STATIC_STRONG_THRESHOLD:
        logger.info(
            "[FAQ] ✅ Static match ACCEPTED (high similarity)",
            extra={
                "decision": "FAQ_STATIC_MATCH",
                "key": _get_field(static_item, "key"),
                "score": static_score,
                "user": user_text,
                "location": "gateway_app/services/faq_llm.py"
            },
        )
        answer = static_item.get("a") if isinstance(static_item, dict) else getattr(static_item, "a", None)
        # If guest is EN/PT but static answer is ES (from JSON), translate.
        if answer and target_lang != "es":
            translated = _translate_answer(answer, target_lang)
            if translated:
                answer = translated
        return answer, None  # No token usage for static match

    logger.info(
        "[FAQ] ⚠️ Static match REJECTED (low similarity), trying LLM fallback",
        extra={
            "decision": "FAQ_STATIC_REJECTED",
            "static_score": static_score,
            "user": user_text,
            "location": "gateway_app/services/faq_llm.py"
        },
    )

    # 2) LLM fallback for all fuzzy / paraphrased / misspelled cases.
    if use_llm_fallback:
        llm_answer, token_usage = _call_faq_llm(user_text, items, target_lang)

        if llm_answer:
            logger.info(
                "[FAQ] 🧪 Language match check",
                extra={
                    "target_lang": target_lang,
                    "answer_preview": llm_answer[:120],
                    "is_language_match": is_language_match(llm_answer, target_lang),
                    "location": "gateway_app/services/faq_llm.py::answer_faq"
                }
            )


        # Safety net: if model answered in wrong language, translate-only fix.
        if llm_answer and not is_language_match(llm_answer, target_lang):
            logger.warning(
                "[FAQ] LLM answered in wrong language; applying translate-only fix",
                extra={"target_lang": target_lang, "answer_preview": llm_answer[:80]},
            )
            fixed = _translate_answer(llm_answer, target_lang)
            if fixed:
                llm_answer = fixed
        if llm_answer:
            logger.info(
                "[FAQ] ✅ LLM fallback FOUND answer",
                extra={
                    "decision": "FAQ_LLM_MATCH",
                    "user": user_text,
                    "answer_preview": llm_answer[:100] if llm_answer else None,
                    "token_usage": str(token_usage) if token_usage else None,
                    "location": "gateway_app/services/faq_llm.py"
                }
            )
        else:
            logger.info(
                "[FAQ] ❌ LLM fallback found NO answer",
                extra={
                    "decision": "FAQ_NO_MATCH",
                    "user": user_text,
                    "token_usage": str(token_usage) if token_usage else None,
                    "location": "gateway_app/services/faq_llm.py"
                }
            )
        return llm_answer, token_usage

    logger.info(
        "[FAQ] ❌ NO FAQ match (LLM fallback disabled)",
        extra={
            "decision": "FAQ_NO_MATCH_NO_LLM",
            "user": user_text,
            "location": "gateway_app/services/faq_llm.py"
        }
    )
    return None, None


def has_faq_match(user_text: str, faq_items: Optional[Iterable[FAQItem]] = None) -> bool:
    """
    Convenience helper: returns True if `answer_faq` finds any match.
    """
    answer, _ = answer_faq(user_text, faq_items=faq_items, use_llm_fallback=False)
    return answer is not None
