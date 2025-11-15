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


def analyze_guest_message(text: str, session: dict, state: str) -> dict:
    if not text or not text.strip():
        return {}

    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un NLU para mensajes de huéspedes de hotel por WhatsApp. "
                        "Devuelves SIEMPRE un JSON con esta forma:\n\n"
                        "{\n"
                        '  "intent": "ticket_request | handoff_request | general_chat | cancel | unknown",\n'
                        '  "area": "MANTENCION | HOUSEKEEPING | ROOMSERVICE | null",\n'
                        '  "priority": "URGENTE | ALTA | MEDIA | BAJA | null",\n'
                        '  "room": "string o null",\n'
                        '  "detail": "string o null",\n'
                        '  "is_cancel": bool,\n'
                        '  "is_help": bool,\n'
                        '  "is_smalltalk": bool,\n'
                        '  "wants_handoff": bool\n'
                        "}\n\n"
                        "No incluyas texto fuera del JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Estado DFA actual: {state}\n\n"
                        f"Mensaje del huésped:\n{text}"
                    ),
                },
            ],
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        # Normaliza claves esperadas
        return {
            "intent": data.get("intent"),
            "area": data.get("area"),
            "priority": data.get("priority"),
            "room": data.get("room"),
            "detail": data.get("detail"),
            "is_cancel": bool(data.get("is_cancel")),
            "is_help": bool(data.get("is_help")),
            "is_smalltalk": bool(data.get("is_smalltalk")),
            "wants_handoff": bool(data.get("wants_handoff")),
        }
    except Exception as e:
        print(f"[WARN] guest_llm json call failed: {e}", flush=True)
        return {}


_CONFIRM_SYSTEM_PROMPT = """
You help write short, friendly WhatsApp replies for a hotel guest assistant (Hestia).
Always answer in Spanish, using a warm but concise tone.
You will receive the context and must return a single string (no JSON).
"""


def render_confirm_draft(summary: str, session: dict) -> str:
    name = (session.get("guest_name") or "Huésped").strip()
    return (
        f"📝 {name}, este es el resumen de tu solicitud:\n\n"
        f"{summary}\n\n"
        "Si todo está correcto responde *SI* para crear el ticket.\n"
        "Si quieres cambiar algo responde *NO* y podrás editar área, prioridad, "
        "habitación o detalle."
    )

