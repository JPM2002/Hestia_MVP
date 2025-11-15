import os
import json
from typing import Any, Dict, Optional

from openai import OpenAI

_client = OpenAI()
LLM_MODEL = os.getenv("GUEST_LLM_MODEL", "gpt-4.1-mini")

_BASE_SYSTEM_PROMPT = """
You are the NLU module for Hestia, a WhatsApp assistant for hotel guests.
Messages are mostly in Spanish, sometimes English or German.
Your job is to interpret SHORT WhatsApp messages and return a JSON object with this shape:

{
  "intent": "ticket_request" | "general_chat" | "handoff_request" | "cancel" | "help" | "not_understood",
  "area": "MANTENCION" | "HOUSEKEEPING" | "ROOMSERVICE" | null,
  "priority": "URGENTE" | "ALTA" | "MEDIA" | "BAJA" | null,
  "room": string | null,
  "detail": string | null,
  "is_smalltalk": boolean,
  "wants_handoff": boolean,
  "is_cancel": boolean,
  "is_help": boolean
}

Notes:
- If the message is only greetings/thanks, set:
  - intent = "general_chat"
  - is_smalltalk = true
- If the guest clearly wants to talk to a human/agent/reception, set:
  - intent = "handoff_request"
  - wants_handoff = true
- If they ask to cancel or ignore a previous request, set:
  - intent = "cancel"
  - is_cancel = true
- If they ask what the assistant can do or say "help", set:
  - intent = "help"
  - is_help = true
- Area hints:
  - HOUSEKEEPING: towels, sheets, pillows, cleaning, trash, amenities.
  - MANTENCION: shower, bathroom, AC, heating, lights, plugs, TV, doors, windows.
  - ROOMSERVICE: food, drinks, breakfast, dinner, orders.

If something is not clearly present, use null for that field.
Always return VALID JSON ONLY. No explanations, no extra keys.
"""


def _call_json_llm(system_prompt: str, user_prompt: str, max_tokens: int = 256) -> Optional[Dict[str, Any]]:
    try:
        resp = _client.responses.create(
            model=LLM_MODEL,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            max_output_tokens=max_tokens,
        )
        content = resp.output[0].content[0].text
        return json.loads(content)
    except Exception as e:
        print(f"[WARN] guest_llm json call failed: {e}", flush=True)
        return None


def analyze_guest_message(text: str, session: Dict[str, Any], state: str) -> Dict[str, Any]:
    """
    Main NLU entrypoint.
    text   : incoming user message (already stripped).
    session: current session dict for this phone (may be empty).
    state  : DFA state ("GH_S0", "GH_S1", etc.) for context.
    """
    t = (text or "").strip()
    if not t:
        return {}

    ctx = {
        "state": state,
        "guest_name": session.get("guest_name"),
        "room": session.get("room"),
        "has_identification": bool(session.get("guest_name") and session.get("room")),
        "last_ticket_id": session.get("gh_last_ticket_id"),
    }

    user_prompt = (
        "Mensaje del huésped:\n"
        f"{t}\n\n"
        "Contexto de conversación (JSON):\n"
        f"{json.dumps(ctx, ensure_ascii=False)}\n\n"
        "Devuelve únicamente el JSON con la estructura especificada."
    )

    data = _call_json_llm(_BASE_SYSTEM_PROMPT, user_prompt)
    if not isinstance(data, dict):
        return {}

    intent = (data.get("intent") or "").strip().lower()
    valid_intents = {
        "ticket_request",
        "general_chat",
        "handoff_request",
        "cancel",
        "help",
        "not_understood",
    }
    if intent not in valid_intents:
        intent = "not_understood"

    area = (data.get("area") or "").strip().upper() or None
    if area not in {"MANTENCION", "HOUSEKEEPING", "ROOMSERVICE"}:
        area = None

    priority = (data.get("priority") or "").strip().upper() or None
    if priority not in {"URGENTE", "ALTA", "MEDIA", "BAJA"}:
        priority = None

    room = data.get("room")
    if room is not None:
        room = "".join(ch for ch in str(room) if ch.isdigit()) or None

    detail = data.get("detail")
    if detail is not None:
        detail = str(detail).strip() or None

    def _b(key: str) -> bool:
        return bool(data.get(key))

    return {
        "intent": intent,
        "area": area,
        "priority": priority,
        "room": room,
        "detail": detail,
        "is_smalltalk": _b("is_smalltalk"),
        "wants_handoff": _b("wants_handoff"),
        "is_cancel": _b("is_cancel"),
        "is_help": _b("is_help"),
    }


_CONFIRM_SYSTEM_PROMPT = """
You help write short, friendly WhatsApp replies for a hotel guest assistant (Hestia).
Always answer in Spanish, using a warm but concise tone.
You will receive the context and must return a single string (no JSON).
"""


def render_confirm_draft(summary: str, session: Dict[str, Any]) -> str:
    """
    Given a structured summary, ask the guest to confirm in a smooth way.
    If the LLM fails, fall back to a static template.
    """
    guest_name = session.get("guest_name") or ""
    room = session.get("room") or ""

    base = (
        "📝 Te resumo lo que entendí:\n\n"
        f"{summary}\n\n"
        "¿Lo dejo registrado así o quieres cambiar algo? "
        "Responde *SI* para confirmar o *NO* para corregir."
    )

    user_ctx = {
        "guest_name": guest_name,
        "room": room,
        "summary": summary,
    }

    prompt = (
        "Contexto (JSON):\n"
        f"{json.dumps(user_ctx, ensure_ascii=False)}\n\n"
        "Escribe un mensaje único, corto y amable para pedir confirmación de este resumen. "
        "Mantén el contenido clave pero puedes suavizar el tono."
    )

    try:
        resp = _client.responses.create(
            model=LLM_MODEL,
            input=[
                {"role": "system", "content": _CONFIRM_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_output_tokens=200,
        )
        text = resp.output[0].content[0].text.strip()
        if text:
            return text
    except Exception as e:
        print(f"[WARN] render_confirm_draft LLM failed: {e}", flush=True)

    return base
