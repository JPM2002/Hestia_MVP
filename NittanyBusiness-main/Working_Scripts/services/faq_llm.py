# services/faq_llm.py
import os
import json
from typing import Any, Dict, Optional, List

from openai import OpenAI


_client = OpenAI()
FAQ_LLM_MODEL = os.getenv("FAQ_LLM_MODEL", "gpt-4.1-mini")

# Simple FAQ knowledge base – EDIT these entries to match your hotel.
# You can add/remove items, just keep the same keys ("key", "q", "a").
FAQ_ITEMS: List[Dict[str, str]] = [
    {
        "key": "checkin_time",
        "q": "¿A qué hora es el check-in?",
        "a": "El check-in es a partir de las 15:00.",
    },
    {
        "key": "checkout_time",
        "q": "¿A qué hora es el check-out?",
        "a": "El check-out es hasta las 12:00.",
    },
    {
        "key": "breakfast_time",
        "q": "¿En qué horario se sirve el desayuno?",
        "a": "El desayuno se sirve de 7:00 a 10:30 en el restaurante principal.",
    },
    {
        "key": "wifi",
        "q": "¿Cómo funciona el wifi del hotel?",
        "a": "La red Wi-Fi es gratuita; el nombre y la clave se encuentran en la tarjeta de la habitación.",
    },
    # Añade aquí todas las FAQs específicas del hotel...
]


_FAQ_SYSTEM_PROMPT = """
You are the FAQ brain for Hestia, a WhatsApp assistant for hotel guests.

Your job:
- Decide if the guest message can be answered using the hotel's FAQ knowledge.
- If yes, return a short, friendly answer based ONLY on that FAQ knowledge.
- Spanish is the default language, but you may answer in the guest's language
  if it is clearly English or German.

You will receive a JSON payload with this shape:

{
  "faq_items": [ {"key": "...", "q": "...", "a": "..."}, ... ],
  "message": "<guest message here>"
}

You must return a JSON object with EXACTLY this shape:

{
  "is_faq": true or false,
  "matched_key": string or null,
  "answer": string or null
}

Rules:
- If the message clearly matches any FAQ item (even paraphrased, with typos, or
  in English/German), set:
    is_faq = true
    matched_key = that item's "key"
    answer = a short, friendly version of that item's "a"
- If the message mixes an FAQ question with a clear maintenance / housekeeping /
  room-service problem, set is_faq = false so that another system can open a ticket.
- If you're not sure, or the question is not covered by faq_items, set:
    is_faq = false, matched_key = null, answer = null
- Never invent policies that are not present in faq_items.
- Output ONLY valid JSON. No extra text, no comments, no explanations.
"""

def _call_faq_llm(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Low-level LLM call that enforces JSON output.
    """
    try:
        resp = _client.responses.create(
            model=FAQ_LLM_MODEL,
            input=[
                {"role": "system", "content": _FAQ_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
            response_format={"type": "json_object"},
            max_output_tokens=256,
        )
        content = resp.output[0].content[0].text
        data = json.loads(content)
        if isinstance(data, dict):
            return data
        return None
    except Exception as e:
        print(f"[WARN] faq_llm json call failed: {e}", flush=True)
        return None


def maybe_answer_faq(text: str, session: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    High-level helper used by the DFA.

    Returns:
        {
          "handled": bool,          # True if this should be answered as FAQ
          "matched_key": str|None,
          "answer": str|None,
        }
    """
    t = (text or "").strip()
    if not t:
        return {"handled": False}

    payload = {
        "faq_items": FAQ_ITEMS,
        "message": t,
    }

    data = _call_faq_llm(payload) or {}
    is_faq = bool(data.get("is_faq"))
    answer = (data.get("answer") or "").strip()
    matched_key = data.get("matched_key")

    if not is_faq or not answer:
        return {"handled": False}

    return {
        "handled": True,
        "matched_key": matched_key,
        "answer": answer,
    }
