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
from gateway_app.services.ai.prompt_loader import (
    get_nlu_system_prompt,
    get_confirm_draft_prompt
)

logger = logging.getLogger(__name__)

_client = OpenAI()
LLM_MODEL = os.getenv("GUEST_LLM_MODEL", "gpt-4.1-mini")

# Load prompts from external files for easier maintenance and versioning
_BASE_SYSTEM_PROMPT = get_nlu_system_prompt(version="v1")
_CONFIRM_SYSTEM_PROMPT = get_confirm_draft_prompt(version="v1")


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
