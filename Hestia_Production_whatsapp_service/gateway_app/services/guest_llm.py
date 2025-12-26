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
    Main NLU entry point con rules-first approach.

    Flow:
    1. Intenta routing por reglas (rápido, determinístico, gratis)
    2. Si reglas fallan, usa LLM (flexible pero más lento)
    3. Aplica guardrails de validación
    4. Retorna resultado con metadata de routing

    Args:
        text: Inbound guest message (plain text).
        session: Per-guest session dict (for future personalization, currently unused).
        state: Current DFA/state machine label (string), passed as context to the LLM.

    Returns:
        A dict with the normalized fields + routing metadata (_routing_*).
        If parsing fails, returns {}.
    """
    from gateway_app.services.routing_rules import route_by_rules

    logger.info(
        "[NLU] 🧠 Starting NLU analysis",
        extra={
            "text": text[:80] + "..." if len(text) > 80 else text,
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

    # =========================================================================
    # LAYER 1: RULES-FIRST (determinístico, 0ms extra, $0 costo)
    # =========================================================================
    rules_result = route_by_rules(text)

    if rules_result:
        logger.info(
            f"[NLU] ✅ RULES HIT → {rules_result['area']} (conf={rules_result['confidence']:.2f}) - LLM SKIPPED",
            extra={
                "area": rules_result["area"],
                "confidence": rules_result["confidence"],
                "source": "rules",
                "llm_call_saved": True,
                "location": "gateway_app/services/guest_llm.py"
            }
        )

        return {
            "intent": "ticket_request",
            "area": rules_result["area"],
            "confidence": rules_result["confidence"],
            "priority": None,
            "room": None,
            "detail": text,
            "name": None,
            "is_smalltalk": False,
            "wants_handoff": False,
            "is_cancel": False,
            "is_help": False,
            # Metadata de routing
            "_routing_source": "rules",
            "_routing_reason": rules_result["reason"],
            "_routing_confidence": rules_result["confidence"],
        }

    logger.info(
        "[NLU] ⚠️ Rules missed → LLM fallback",
        extra={"location": "gateway_app/services/guest_llm.py"}
    )

    # =========================================================================
    # LAYER 2: LLM con guardrails estrictos
    # =========================================================================
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
    allowed_areas = {"MANTENCION", "HOUSEKEEPING", "RECEPCION", "SUPERVISION", "GERENCIA"}
    allowed_priorities = {"URGENTE", "ALTA", "MEDIA", "BAJA"}

    intent = data.get("intent")
    if intent == "unknown":
        intent = "not_understood"
    if intent not in allowed_intents:
        intent = "not_understood"

    area = data.get("area")
    if area and area not in allowed_areas:
        logger.warning(
            f"[NLU] ⚠️ Invalid area '{area}' from LLM → setting to None",
            extra={"invalid_area": area, "location": "gateway_app/services/guest_llm.py"}
        )
        area = None

    # Extraer confidence del LLM (CRÍTICO para threshold checking)
    confidence = data.get("confidence", 0.75)
    if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
        logger.warning(
            f"[NLU] ⚠️ Invalid confidence '{confidence}' from LLM → default 0.75",
            extra={"invalid_confidence": confidence, "location": "gateway_app/services/guest_llm.py"}
        )
        confidence = 0.75

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
        "confidence": confidence,
        "priority": priority,
        "room": room,
        "detail": detail,
        "name": name,
        "is_smalltalk": bool(data.get("is_smalltalk")),
        "wants_handoff": bool(data.get("wants_handoff")),
        "is_cancel": bool(data.get("is_cancel")),
        "is_help": bool(data.get("is_help")),
        # Metadata de routing
        "_routing_source": "llm",
        "_routing_reason": "LLM classification",
        "_routing_confidence": confidence,
    }

    logger.info(
        f"[NLU] ✅ LLM result: intent={intent}, area={area}, conf={confidence:.2f}",
        extra={
            "text": text[:80] + "..." if len(text) > 80 else text,
            "intent": intent,
            "area": area,
            "confidence": confidence,
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
