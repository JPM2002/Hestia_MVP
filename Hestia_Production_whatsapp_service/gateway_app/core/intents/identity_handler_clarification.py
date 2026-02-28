"""
Area clarification handler - Procesa respuesta del usuario cuando pide aclaración de área.

Extracted to separate file for clarity.
"""
from __future__ import annotations
import re
import logging
from typing import Any, Dict, List, Tuple
from gateway_app.services.i18n import get_phrase, normalize_lang, area_name
from gateway_app.core.conversation.utils.area_utils import build_area_options_text


logger = logging.getLogger(__name__)


def handle_detail_clarification_response(
    msg: str,
    session: Dict[str, Any]
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Procesa la respuesta del usuario cuando proporciona detalles específicos del problema.

    Args:
        msg: Descripción del problema proporcionada por el usuario
        session: Sesión actual

    Returns:
        (handled: bool, actions: list)
    """
    from gateway_app.core.intents.base import text_action

    # Actualizar el detalle en ticket_draft
    if "ticket_draft" in session:
        session["ticket_draft"]["detail"] = msg.strip()

    draft = session.get("ticket_draft", {})
    area = draft.get("area", "MANTENCION")
    guest_name = draft.get("guest_name")
    room = draft.get("room")

    logger.info(
        "[ROUTING] ✅ User provided specific details",
        extra={
            "area": area,
            "detail": msg.strip(),
            "has_guest_name": bool(guest_name),
            "has_room": bool(room)
        }
    )

    # Si falta identidad, pedirla ahora
    if not guest_name or not room:
        session["state"] = "GH_IDENTIFY"

        lang = normalize_lang(session.get("language"))
        return True, [text_action(get_phrase("identity_request", lang))]


    # Si ya tenemos identidad, ir directo a confirmación
    area_map = {
        "MANTENCION": "Mantenimiento",
        "HOUSEKEEPING": "Housekeeping",
        "RECEPCION": "Recepción",
        "GERENCIA": "Gerencia",
    }
    # area_name = area_map.get(area, area)

    session["state"] = "GH_TICKET_CONFIRM"

    lang = normalize_lang(session.get("language"))
    area_local = area_name(area, lang)

    confirm_text = get_phrase(
        "ticket_confirm",
        lang,
        name=guest_name,
        area=area_local,
        detail=msg.strip(),
        room=room,
    )


    logger.info(
        "[ROUTING] 📋 Details received, moving to confirmation",
        extra={
            "area": area,
            "detail": msg.strip(),
            "guest_name": guest_name,
            "room": room,
            "next_state": "GH_TICKET_CONFIRM"
        }
    )

    return True, [text_action(confirm_text)]


def handle_area_clarification_response(
    msg: str,
    session: Dict[str, Any]
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Procesa la respuesta del usuario a la pregunta de aclaración de área.

    Args:
        msg: Respuesta del usuario (ej: "1", "mantenimiento", "housekeeping", etc.)
        session: Sesión actual

    Returns:
        (handled: bool, actions: list)
        - handled=True si se procesó correctamente
        - handled=False si no se entendió la respuesta
    """
    from gateway_app.core.intents.base import text_action

    msg_lower = msg.lower().strip()

    # Mapeo: respuesta → (área_code, área_nombre)
    area_map = {
        "1": ("MANTENCION", "Mantenimiento"),
        "2": ("HOUSEKEEPING", "Housekeeping"),
        "3": ("RECEPCION", "Recepción"),
        "4": ("GERENCIA", "Gerencia"),
    }

    # También aceptar palabras clave
    choice = None
    if re.search(r'\b(mantencion|mantenimiento|tecnico|mantenci[oó]n)\b', msg_lower):
        choice = "1"
    elif re.search(r'\b(housekeeping|limpieza|aseo|toallas)\b', msg_lower):
        choice = "2"
    elif re.search(r'\b(recepcion|recepci[oó]n|pago|reserva)\b', msg_lower):
        choice = "3"
    elif re.search(r'\b(gerencia|queja|reclamo|gerente)\b', msg_lower):
        choice = "4"
    else:
        # Intentar parsear como número directo
        choice = msg_lower.strip()

    if choice not in area_map:
        logger.warning(
            f"[ROUTING] ⚠️ Invalid clarification response: '{msg}'",
            extra={"user_response": msg}
        )
        lang = normalize_lang(session.get("language"))
        options = build_area_options_text(lang=lang)
        text_map = {
            "es": "No entendí tu respuesta. Por favor responde con un número:\n\n{opts}",
            "en": "I didn’t understand your reply. Please respond with a number:\n\n{opts}",
            "pt": "Não entendi sua resposta. Por favor responda com um número:\n\n{opts}",
        }
        return False, [text_action(text_map[lang].format(opts=options))]


    area, area_name = area_map[choice]

    # ⭐ NEW: Handle multiple requests if present
    pending_requests = session.get("pending_requests", [])
    remaining_requests = []
    selected_request = None

    if pending_requests and isinstance(pending_requests, list):
        # Find the request matching the selected area
        for req in pending_requests:
            if req.get("area") == area:
                if not selected_request:
                    selected_request = req  # Use first match
                else:
                    remaining_requests.append(req)  # Save duplicates for later
            else:
                remaining_requests.append(req)  # Save other departments for later

        # Use detail and priority from selected request
        detail = selected_request.get("detail", session.get("pending_detail", "Sin detalles")) if selected_request else session.get("pending_detail", "Sin detalles")
        priority = selected_request.get("priority", "MEDIA") if selected_request else "MEDIA"

        # Store remaining requests for later (after this ticket is done)
        if remaining_requests:
            session["remaining_requests"] = remaining_requests
            logger.info(
                f"[ROUTING] 📋 Stored {len(remaining_requests)} remaining requests for later",
                extra={"remaining_count": len(remaining_requests)}
            )
        else:
            session.pop("remaining_requests", None)

        # Clear pending_requests now that we've processed them
        session.pop("pending_requests", None)
    else:
        # Original single-request flow
        detail = session.pop("pending_detail", "Sin detalles")
        priority = "MEDIA"

    room = session.pop("pending_room", None)
    guest_name = session.pop("pending_guest_name", None)

    # Crear draft con área clarificada
    session["ticket_draft"] = {
        "area": area,
        "priority": priority,
        "room": room,
        "detail": detail,
        "guest_name": guest_name,
        # Metadata de routing
        "routing_source": "clarification",
        "routing_reason": f"User chose option {choice}: {area}",
        "routing_confidence": 1.0,  # 100% - usuario confirmó explícitamente
        "routing_version": "v1",
    }

    logger.info(
        f"[ROUTING] ✅ User clarified → {area} (choice={choice})",
        extra={
            "area": area,
            "user_choice": choice,
            "routing_source": "clarification",
            "confidence": 1.0,
            "has_remaining_requests": bool(remaining_requests)
        }
    )

    # ⭐ NUEVO FLUJO: Primero pedir detalles específicos del problema
    # Verificar si el detalle es vago (mensajes genéricos que no describen el problema real)
    vague_details = [
        "tengo un problema",
        "necesito ayuda",
        "hay un problema",
        "sin detalles",
        "solicitud",
        "problema en",
    ]

    is_vague = any(vague in detail.lower() for vague in vague_details) if detail else True

    if is_vague:
        # Pedir detalles específicos antes de pedir identidad
        session["state"] = "GH_DETAIL_CLARIFICATION"

        # Mensajes específicos por área
        area_prompts = {
            "MANTENCION": "¿Qué problema de mantenimiento tienes? (ej: AC no funciona, fuga de agua, luz no enciende, etc.)",
            "HOUSEKEEPING": "¿Qué necesitas de limpieza? (ej: toallas limpias, cambio de sábanas, amenities, etc.)",
            "RECEPCION": "¿Con qué puedo ayudarte? (ej: información de cuenta, cambio de reserva, etc.)",
            "GERENCIA": "¿Cuál es tu consulta o comentario?",
        }

        detail_prompt = area_prompts.get(area, "¿Puedes darme más detalles sobre tu solicitud?")

        logger.info(
            "[ROUTING] 📋 Requesting specific problem details",
            extra={
                "area": area,
                "vague_detail": detail,
                "next_state": "GH_DETAIL_CLARIFICATION"
            }
        )

        lang = normalize_lang(session.get("language"))
        area_local = area_name(area, lang)

        prefix_map = {
            "es": "Perfecto, {area}.\n\n{prompt}",
            "en": "Perfect — {area}.\n\n{prompt}",
            "pt": "Perfeito — {area}.\n\n{prompt}",
        }

        # Localize the prompt itself per area
        prompts = {
            "es": {
                "MANTENCION": "¿Qué problema de mantenimiento tienes? (ej: el aire no funciona, fuga de agua, la luz no enciende, etc.)",
                "HOUSEKEEPING": "¿Qué necesitas de housekeeping? (ej: toallas limpias, cambio de sábanas, amenities, etc.)",
                "RECEPCION": "¿Con qué puedo ayudarte? (ej: información de cuenta, cambio de reserva, etc.)",
                "GERENCIA": "¿Cuál es tu comentario o reclamo?",
            },
            "en": {
                "MANTENCION": "What maintenance issue is it? (e.g., AC not working, water leak, lights won’t turn on, etc.)",
                "HOUSEKEEPING": "What do you need from housekeeping? (e.g., clean towels, sheet change, amenities, etc.)",
                "RECEPCION": "How can the front desk help? (e.g., billing question, reservation change, etc.)",
                "GERENCIA": "What’s your comment or complaint?",
            },
            "pt": {
                "MANTENCION": "Qual é o problema de manutenção? (ex.: ar não funciona, vazamento, luz não acende, etc.)",
                "HOUSEKEEPING": "O que você precisa do housekeeping? (ex.: toalhas limpas, troca de lençóis, amenities, etc.)",
                "RECEPCION": "Como a recepção pode ajudar? (ex.: conta, alteração de reserva, etc.)",
                "GERENCIA": "Qual é o seu comentário ou reclamação?",
            },
        }[lang]

        detail_prompt_local = prompts.get(area, prompts.get("MANTENCION"))
        text = prefix_map[lang].format(area=area_local, prompt=detail_prompt_local)

        return True, [text_action(text)]


    # Si ya tenemos detalles específicos, continuar con el flujo normal
    # Si falta identidad, pedirla ahora
    if not guest_name or not room:
        session["state"] = "GH_IDENTIFY"

        lang = normalize_lang(session.get("language"))

        logger.info(
            "[ROUTING] 📋 Area clarified, now requesting identity",
            extra={
                "area": area,
                "next_state": "GH_IDENTIFY"
            }
        )

        return True, [text_action(get_phrase("identity_request", lang))]

    # Si ya tenemos identidad, ir directo a confirmación
    session["state"] = "GH_TICKET_CONFIRM"

    lang = normalize_lang(session.get("language"))
    area_local = area_name(area, lang)

    confirm_text = get_phrase(
        "ticket_confirm",
        lang,
        name=guest_name,
        area=area_local,
        detail=detail,
        room=room,
    )

    return True, [text_action(confirm_text)]

