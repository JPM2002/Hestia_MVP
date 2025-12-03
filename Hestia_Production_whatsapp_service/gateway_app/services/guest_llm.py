# gateway_app/services/guest_llm.py
"""
Guest NLU module for the WhatsApp assistant (Hestia).

Responsibilities:
- Call OpenAI to interpret short WhatsApp messages.
- Return a normalized dict with intent, area, priority, room, detail and flags.
- Provide a helper to render the confirmation draft message.

The LLM is instructed to ALWAYS output a strict JSON object with this shape:

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
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

_client = OpenAI()
LLM_MODEL = os.getenv("GUEST_LLM_MODEL", "gpt-4.1-mini")


_BASE_SYSTEM_PROMPT = """



You are the NLU module for Hestia, a WhatsApp assistant for hotel guests.
Messages are mostly in Spanish, sometimes English or German.
Your job is to interpret SHORT WhatsApp messages and return a JSON object with this exact shape:

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

You MUST return valid JSON only. No explanations, no extra keys, no trailing commas.

INTENT RULES AND FLAGS

1) ticket_request
- The guest is reporting a problem or asking for something related to the hotel stay.
- Example: "necesito toallas", "no funciona el aire", "quiero pedir cena", "faltan almohadas".
- intent = "ticket_request".
- Fill area / priority / room / detail when you can infer them.

2) general_chat / smalltalk / closing
Use intent = "general_chat" and is_smalltalk = true when the message is mainly:
- greeting,
- thanking,
- friendly chit-chat,
- or a polite way of saying they do NOT need more help right now.

Typical examples of general_chat / closing (and close variations, even with typos, emojis or extra letters):
- "gracias", "muchas gracias",
- "no gracias", "no muchas gracias", "no, muchas gracias",
- "todo bien", "todo bien gracias", "todo ok", "todo bn gracias",
- "estoy bien", "estoy bien, gracias",
- "listo, muchas gracias", "perfecto, gracias", "gracias por la ayuda",
- "no por ahora, gracias", "por ahora estoy bien".

For ALL these cases:
- intent = "general_chat"
- is_smalltalk = true
- is_cancel = false   ← IMPORTANT: do NOT treat them as cancellation.

3) handoff_request (wants human / reception)
- The guest clearly wants to talk to a person (reception, staff, human agent).
- Examples: "quiero hablar con alguien", "pásame con recepción", "human please", "can I talk to a real person?".
- intent = "handoff_request"
- wants_handoff = true
- is_cancel = false (unless they also explicitly say they want to cancel a ticket).

4) cancel
Use intent = "cancel" and is_cancel = true ONLY when the guest clearly wants to cancel
a previous request / ticket / order, for example:
- "cancela el ticket",
- "cancela la solicitud",
- "quiero cancelar el pedido",
- "olvídalo, ya no lo necesito",
- "anula ese pedido",
- "ya no quiero eso / ya no hace falta, cancela".

Important:
- Polite closing phrases like "no gracias", "no muchas gracias", "todo bien, gracias"
  are NOT cancellations. For them: intent = "general_chat", is_smalltalk = true, is_cancel = false.

5) help
- The guest asks what the assistant can do, or explicitly asks for help with the bot.
- Examples: "ayuda", "help", "qué puedes hacer", "como funcionas", "no entiendo cómo usar esto".
- intent = "help"
- is_help = true

6) not_understood
- The message is unclear, random, or you cannot classify it.
- Example: a long unrelated story, or just random characters.
- intent = "not_understood"
- All other flags should be false unless clearly indicated.

AREA HINTS

Infer area when possible (otherwise use null):
- HOUSEKEEPING → towels, sheets, pillows, cleaning, trash, amenities, soap, shampoo.
- MANTENCION → shower, bathroom, toilet, sink, AC, heating, lights, power, plugs, TV, doors, windows, leaks.
- ROOMSERVICE → food, drinks, breakfast, dinner, snacks, orders to the room, beverages.

PRIORITY HINTS

Infer priority when possible (otherwise null):
- URGENTE → emergency, flooding, fire, strong leak, dangerous electrical issue, guest cannot stay in room.
- ALTA → important problem that should be fixed soon.
- MEDIA → normal request, "cuando puedan".
- BAJA → low-impact, minor issues, nice-to-have.

ROOM AND DETAIL

- room: extract a clear room number if present (e.g., from "312", "hab 312", "cuarto 127").
- detail: short natural-language description of the issue or request.
  If the message is only smalltalk / greeting, use null for detail.

If something is not clearly present, use null for that field.
Always follow the schema exactly and output ONLY the JSON object.
"""


def _call_json_llm(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 256,
) -> Optional[Dict[str, Any]]:
    """
    Helper that uses the Responses API in JSON mode (text.format = {"type": "json_object"})
    and parses the result into a Python dict.
    """
    try:
        resp = _client.responses.create(
            model=LLM_MODEL,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            # JSON mode is now configured via text.format, not response_format
            text={
                "format": {
                    "type": "json_object"
                }
            },
            max_output_tokens=max_tokens,
        )

        # Responses API: JSON text is in output[0].content[0].text
        content = resp.output[0].content[0].text
        return json.loads(content)

    except Exception as e:
        logger.warning("[WARN] guest_llm json call failed: %s", e, exc_info=True)
        return None


def analyze_guest_message(text: str, session: dict, state: str) -> dict:
    """
    Main NLU entry point.

    Args:
        text: Inbound guest message (plain text).
        session: Per-guest session dict (for future personalization, currently unused).
        state: Current DFA/state machine label (string), passed as context to the LLM.

    Returns:
        A dict with the normalized fields as described in _BASE_SYSTEM_PROMPT.
        If parsing fails, returns {}.
    """
    if not text or not text.strip():
        return {}

    prompt = (
        f"Estado DFA actual: {state}\n\n"
        f"Mensaje del huésped:\n{text}"
    )

    data = _call_json_llm(_BASE_SYSTEM_PROMPT, prompt)
    if not data or not isinstance(data, dict):
        return {}

    # --------- Guardrails / clamping ---------
    allowed_intents = {
        "ticket_request",
        "general_chat",
        "handoff_request",
        "cancel",
        "help",
        "not_understood",
    }
    allowed_areas = {"MANTENCION", "HOUSEKEEPING", "ROOMSERVICE"}
    allowed_priorities = {"URGENTE", "ALTA", "MEDIA", "BAJA"}

    intent = data.get("intent")
    if intent == "unknown":
        intent = "not_understood"
    if intent not in allowed_intents:
        intent = "not_understood"

    area = data.get("area")
    if area not in allowed_areas:
        area = None

    priority = data.get("priority")
    if priority not in allowed_priorities:
        priority = None

    room = data.get("room")
    if room is not None:
        room = str(room).strip() or None

    detail = data.get("detail")
    if detail is not None:
        detail = str(detail).strip() or None

    return {
        "intent": intent,
        "area": area,
        "priority": priority,
        "room": room,
        "detail": detail,
        "is_smalltalk": bool(data.get("is_smalltalk")),
        "wants_handoff": bool(data.get("wants_handoff")),
        "is_cancel": bool(data.get("is_cancel")),
        "is_help": bool(data.get("is_help")),
    }



_CONFIRM_SYSTEM_PROMPT = """
You help write short, friendly WhatsApp replies for a hotel guest assistant (Hestia).
Always answer in Spanish, using a warm but concise tone.
You will receive the context and must return a single string (no JSON).
"""


def render_confirm_draft(summary: str, session: dict) -> str:
    """
    Render the confirmation message sent to the guest before creating a ticket.

    Currently this is a template-based function (no LLM call), but it is kept
    here so you can later swap to an LLM-based variant using _CONFIRM_SYSTEM_PROMPT
    if desired.
    """
    name = (session.get("guest_name") or "Huésped").strip()
    return (
        f"📝 {name}, este es el resumen de tu solicitud:\n\n"
        f"{summary}\n\n"
        "Si todo está correcto responde *SI* para crear el ticket.\n"
        "Si quieres cambiar algo responde *NO* y podrás editar área, prioridad, "
        "habitación o detalle."
    )
