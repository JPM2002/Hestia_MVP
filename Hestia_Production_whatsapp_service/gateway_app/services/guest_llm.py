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
  "name": string | null,
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
  "name": string | null,
  "is_smalltalk": boolean,
  "wants_handoff": boolean,
  "is_cancel": boolean,
  "is_help": boolean
}

You MUST return valid JSON only. No explanations, no extra keys, no trailing commas.

INTENT RULES AND FLAGS

0) FAQ TERRITORY (HOW-TO / BASIC USE QUESTIONS) → not_understood
If the guest is asking HOW TO use/operate something, or asking for instructions, and they are NOT clearly
reporting a confirmed malfunction, classify as not_understood so the FAQ module can answer.

Typical HOW-TO patterns (not_understood):
- "¿Cómo prendo/enciendo/apago el aire acondicionado?"
- "¿Cómo prendo/enciendo la luz?"
- "¿Cómo funciona la tarjeta de luz / el interruptor de tarjeta?"
- "¿Cómo uso el control remoto / la TV?"
- "¿Cuál es la clave del wifi?" / "¿Cómo conecto el wifi?"
- "¿Dónde está el interruptor?" / "¿Dónde está el control?"

IMPORTANT DISTINCTION:
- If the guest clearly says it is BROKEN / NOT WORKING / FAILED even after trying (e.g., "no funciona", "no prende",
  "no anda", "ya probé y no", "no me resulta"), THEN it becomes ticket_request.
- If it's ambiguous and can be solved by instructions (especially power/card-switch situations), prefer not_understood.

1) ticket_request (HIGHEST PRIORITY - This is the MAIN function of the bot)
The guest is reporting ANY problem, malfunction, or service request related to their hotel stay.
This includes BOTH explicit requests AND problem reports, even if phrased as questions.

Examples of ticket_request:
• Problems/Malfunctions (area=MANTENCION):
  - "no funciona el aire acondicionado" → ticket_request
  - "no tengo agua caliente" → ticket_request
  - "el wifi no anda" / "se cayó el wifi" → ticket_request
  - "la televisión no funciona" → ticket_request
  - "el control remoto está roto" → ticket_request
  - "hay una fuga de agua en el baño" → ticket_request

• Service Requests (area=HOUSEKEEPING):
  - "necesito toallas" → ticket_request
  - "faltan almohadas" → ticket_request
  - "pueden limpiar mi habitación" → ticket_request
  - "quiero más jabón" → ticket_request
  - "hay mal olor en la habitación" → ticket_request
  - "hay ruido" / "mucho ruido" → ticket_request

• Food/Beverage Requests (area=ROOMSERVICE):
  - "quiero pedir desayuno" → ticket_request
  - "pueden traer comida" → ticket_request

CRITICAL RULES:
✅ Even if phrased as a QUESTION, if it describes a PROBLEM or REQUEST, it's ticket_request:
   - "¿pueden revisar el aire acondicionado?" → ticket_request (it's a request)
   - "¿por qué no funciona el wifi?" → ticket_request (describes a problem)

✅ Mixed messages (greeting + problem):
   - "hola, no funciona el aire" → ticket_request (ignore greeting, focus on problem)
   - "gracias, pero necesito toallas" → ticket_request (ignore thanks, focus on request)

EXCEPTION (IMPORTANT):
If the message is primarily asking for instructions ("cómo prendo", "cómo enciendo", "cómo uso", "dónde está")
and does NOT clearly claim a malfunction after trying, DO NOT create a ticket. Use not_understood (FAQ).

Power/card-switch special case (FAQ-first):
- "No hay luz en mi habitación" → not_understood (FAQ first: suggest key-card power switch)
- "No hay luz en mi habitación, ya probé la tarjeta y no funciona" → ticket_request

For ticket_request:
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
The guest clearly wants to talk to a person (reception, staff, human agent).
Examples: "quiero hablar con alguien", "pásame con recepción", "human please", "can I talk to a real person?".
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
The guest asks what the assistant can do, or explicitly asks for help with the bot.
Examples: "ayuda", "help", "qué puedes hacer", "como funcionas", "no entiendo cómo usar esto".
- intent = "help"
- is_help = true

6) not_understood (FAQ territory: PURE INFO + HOW-TO)
Use not_understood when the message is:
- a PURE INFORMATION question (FAQ territory), OR
- a HOW-TO / usage question (FAQ territory),
OR it is unclear/random.

Examples:
• Pure info:
  - "¿a qué hora es el desayuno?" → not_understood
  - "¿tienen piscina?" → not_understood
  - "¿cuál es la clave del wifi?" → not_understood
  - "horario del restaurante" → not_understood

• How-to / usage:
  - "¿Cómo prendo el aire acondicionado?" → not_understood
  - "¿Cómo prendo la luz de la habitación?" → not_understood
  - "No hay luz en mi habitación" → not_understood (FAQ-first for card-switch)

- intent = "not_understood"
- All other flags should be false unless clearly indicated.

GOLDEN RULE (CRITICAL):
🔴 Confirmed Problem or Service Need → ticket_request
🔵 Pure Info / How-to / Basic instructions → not_understood (FAQ handles it)

Edge Cases to Handle Carefully:
- "hola, no funciona el aire" → ticket_request (ignore greeting, focus on problem)
- "gracias, pero necesito toallas" → ticket_request (ignore thanks, focus on request)
- "¿pueden revisar el AC?" → ticket_request (it's a request)
- "a qué hora desayunan" → not_understood (pure info, FAQ territory)
- "¿Cómo prendo el aire acondicionado?" → not_understood (how-to)
- "No hay luz en mi habitación" → not_understood first (card-switch FAQ), unless they confirm they tried and it failed

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

ROOM, NAME, AND DETAIL

- room: extract a clear room number if present (e.g., from "312", "hab 312", "cuarto 127").
- name: extract the guest's full name if they provide it (e.g., from "soy Juan Pérez", "mi nombre es María González").
  Only extract if clearly stated by the guest. Otherwise use null.
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
    logger.info(
        "[NLU LLM] 🤖 Sending request to LLM",
        extra={
            "model": LLM_MODEL,
            "user_prompt": user_prompt,
            "prompt_length": len(user_prompt),
            "max_tokens": max_tokens,
            "location": "gateway_app/services/guest_llm.py::_call_json_llm"
        }
    )

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

        logger.info(
            "[NLU LLM] 📥 LLM response received (raw JSON)",
            extra={
                "model": LLM_MODEL,
                "raw_json": content,
                "response_length": len(content),
                "location": "gateway_app/services/guest_llm.py::_call_json_llm"
            }
        )

        parsed = json.loads(content)

        logger.info(
            "[NLU LLM] ✅ JSON parsed successfully",
            extra={
                "model": LLM_MODEL,
                "parsed_data": parsed,
                "location": "gateway_app/services/guest_llm.py::_call_json_llm"
            }
        )

        return parsed

    except json.JSONDecodeError as e:
        logger.error(
            "[NLU LLM] ❌ JSON parsing failed",
            extra={
                "model": LLM_MODEL,
                "error": str(e),
                "raw_content": content if 'content' in locals() else None,
                "location": "gateway_app/services/guest_llm.py::_call_json_llm"
            },
            exc_info=True
        )
        return None
    except Exception as e:
        logger.error(
            "[NLU LLM] ❌ LLM call failed",
            extra={
                "model": LLM_MODEL,
                "error": str(e),
                "error_type": type(e).__name__,
                "location": "gateway_app/services/guest_llm.py::_call_json_llm"
            },
            exc_info=True
        )
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
    logger.info(
        "[NLU] 🧠 Starting NLU analysis",
        extra={
            "text": text,
            "state": state,
            "location": "gateway_app/services/guest_llm.py"
        }
    )

    if not text or not text.strip():
        logger.warning(
            "[NLU] ⚠️ Empty text received",
            extra={"location": "gateway_app/services/guest_llm.py"}
        )
        return {}

    prompt = (
        f"Estado DFA actual: {state}\n\n"
        f"Mensaje del huésped:\n{text}"
    )

    data = _call_json_llm(_BASE_SYSTEM_PROMPT, prompt)
    if not data or not isinstance(data, dict):
        logger.error(
            "[NLU] ❌ LLM returned invalid data",
            extra={
                "text": text,
                "raw_response": data,
                "location": "gateway_app/services/guest_llm.py"
            }
        )
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

    name = data.get("name")
    if name is not None:
        name = str(name).strip() or None

    result = {
        "intent": intent,
        "area": area,
        "priority": priority,
        "room": room,
        "detail": detail,
        "name": name,
        "is_smalltalk": bool(data.get("is_smalltalk")),
        "wants_handoff": bool(data.get("wants_handoff")),
        "is_cancel": bool(data.get("is_cancel")),
        "is_help": bool(data.get("is_help")),
    }

    logger.info(
        "[NLU] ✅ NLU analysis completed",
        extra={
            "text": text,
            "intent": intent,
            "area": area,
            "room": room,
            "detail": detail,
            "guest_name_extracted": name,
            "result": result,
            "location": "gateway_app/services/guest_llm.py"
        }
    )

    return result



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
