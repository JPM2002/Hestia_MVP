# gateway_app/core/intents/ticket_status_handler.py
"""
Ticket Status Handler - Handles guest queries about ticket status.

Extracted from monolithic state.py to improve modularity.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Tuple

from gateway_app.core.intents.base import text_action
from gateway_app.services.db import fetchall, fetchone, using_pg
from gateway_app.services.i18n import normalize_lang, area_name


logger = logging.getLogger(__name__)

# 📌 MAPEO DE ESTADOS (solo PENDIENTE_APROBACION por ahora)
STATUS_MESSAGES = {
    "PENDIENTE_APROBACION": "aún no ha sido asignado",
    # 🔜 Agregar después cuando existan en el sistema:
    # "ACEPTADO": "ya fue aceptado y está siendo gestionado",
    # "EN_CURSO": "el equipo ya lo está gestionando",
    # "PAUSADO": "está pausado temporalmente",
    # "FINALIZADO": "ya está resuelto ✅",
    # "COMPLETADO": "ya está completado ✅",
    # "CANCELADO": "fue cancelado",
}

# Localized templates (ES/EN/PT)
_T = {
    "not_found_specific": {
        "es": "No encontré la solicitud #{ticket_id} asociada a tu cuenta. ¿Seguro que ese es el número correcto?",
        "en": "I couldn’t find ticket #{ticket_id} linked to your account. Are you sure that’s the correct number?",
        "pt": "Não encontrei o ticket #{ticket_id} associado à sua conta. Tem certeza de que esse é o número correto?",
    },
    "no_tickets": {
        "es": "No encontré solicitudes anteriores asociadas a tu cuenta. Si necesitas reportar algo, solo cuéntame qué necesitas.",
        "en": "I couldn’t find previous requests linked to your account. If you need something, tell me what you need.",
        "pt": "Não encontrei solicitações anteriores associadas à sua conta. Se precisar de algo, me diga o que você precisa.",
    },
    "single_ticket": {
        "es": "Tu solicitud \"{detail}\" {status_msg}.\n\nTe notificaremos cuando haya novedades.",
        "en": "Your request \"{detail}\" {status_msg}.\n\nI’ll message you when there’s an update.",
        "pt": "Sua solicitação \"{detail}\" {status_msg}.\n\nVou te avisar quando houver novidades.",
    },
    "specific_ticket": {
        "es": "Tu solicitud #{ticket_id} ({detail}) {status_msg}.\n\nTe avisaremos cuando sea aprobada y asignada al equipo.",
        "en": "Your ticket #{ticket_id} ({detail}) {status_msg}.\n\nI’ll message you when it’s approved and assigned to the team.",
        "pt": "Seu ticket #{ticket_id} ({detail}) {status_msg}.\n\nVou te avisar quando for aprovado e atribuído à equipe.",
    },
    "multi_header": {
        "es": "Tienes {n} solicitudes pendientes de aprobación:\n\n",
        "en": "You have {n} requests pending approval:\n\n",
        "pt": "Você tem {n} solicitações pendentes de aprovação:\n\n",
    },
    "multi_footer": {
        "es": "\nTodas están esperando ser aprobadas y asignadas. Te avisaremos cuando haya novedades.",
        "en": "\nAll of them are waiting to be approved and assigned. I’ll message you when there’s an update.",
        "pt": "\nTodas estão aguardando aprovação e atribuição. Vou te avisar quando houver novidades.",
    },
    "more_count": {
        "es": "\n... y {more} más.\n",
        "en": "\n... and {more} more.\n",
        "pt": "\n... e mais {more}.\n",
    },
}

def _lang(session: Dict[str, Any]) -> str:
    return normalize_lang(session.get("language"))

def _status_msg(status: str, lang: str) -> str:
    # Current STATUS_MESSAGES are Spanish; we localize the text.
    # Only PENDIENTE_APROBACION exists now.
    if status == "PENDIENTE_APROBACION":
        return {
            "es": "aún no ha sido asignado",
            "en": "has not been assigned yet",
            "pt": "ainda não foi atribuído",
        }[lang]
    # fallback
    return {
        "es": "está en revisión",
        "en": "is under review",
        "pt": "está em revisão",
    }[lang]



def get_guest_tickets(wa_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Obtiene los tickets del huésped ordenados por más recientes.

    Args:
        wa_id: WhatsApp ID del huésped (huesped_id en BD)
        limit: Cantidad máxima de tickets a retornar

    Returns:
        Lista de tickets con campos: id, detalle, estado, area, ubicacion, created_at
    """
    # Usar placeholder correcto según BD (Postgres vs SQLite)
    ph = "%s" if using_pg() else "?"

    sql = f"""
        SELECT
            id,
            detalle,
            estado,
            area,
            ubicacion,
            created_at,
            approved
        FROM tickets
        WHERE huesped_id = {ph}
          AND deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT {ph}
    """

    tickets = fetchall(sql, [wa_id, limit])

    logger.info(
        "[TICKET_STATUS] Found tickets for guest",
        extra={
            "wa_id": wa_id,
            "ticket_count": len(tickets),
            "location": "gateway_app/core/intents/ticket_status_handler.py"
        }
    )

    return tickets


def handle_ticket_status_query(
    msg: str,
    session: Dict[str, Any]
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Maneja consultas de estado de tickets.

    Lógica simplificada para estado PENDIENTE_APROBACION:
    1. Si menciona #ID específico → consultar ese ticket
    2. Si no menciona ID → usar el último ticket
    3. Si no hay tickets → informar
    4. Si hay múltiples tickets → listar

    Args:
        msg: Mensaje del usuario
        session: Sesión actual

    Returns:
        (handled: bool, actions: list)
    """
    wa_id = session.get("wa_id")

    if not wa_id:
        logger.warning(
            "[TICKET_STATUS] No wa_id in session, cannot query tickets",
            extra={"location": "gateway_app/core/intents/ticket_status_handler.py"}
        )
        return False, []

    logger.info(
        "[TICKET_STATUS] Processing status query",
        extra={
            "wa_id": wa_id,
            "user_message": msg,
            "location": "gateway_app/core/intents/ticket_status_handler.py"
        }
    )

    # 1️⃣ Detectar si menciona un ID específico (ej: "ticket #257" o "257")
    ticket_id_match = re.search(r'#?(\d{3,})', msg)

    ph = "%s" if using_pg() else "?"

    if ticket_id_match:
        # Usuario pregunta por ticket específico
        ticket_id = ticket_id_match.group(1)

        sql = f"""
            SELECT
                id,
                detalle,
                estado,
                area,
                ubicacion,
                created_at,
                approved
            FROM tickets
            WHERE id = {ph}
              AND huesped_id = {ph}
              AND deleted_at IS NULL
        """
        ticket = fetchone(sql, [ticket_id, wa_id])

        if not ticket:
            logger.warning(
                "[TICKET_STATUS] Ticket not found for guest",
                extra={
                    "wa_id": wa_id,
                    "ticket_id": ticket_id,
                    "location": "gateway_app/core/intents/ticket_status_handler.py"
                }
            )

            lang = _lang(session)
            actions = [text_action(_T["not_found_specific"][lang].format(ticket_id=ticket_id))]
            return True, actions


        # Responder con estado del ticket específico
        estado_msg = STATUS_MESSAGES.get(ticket["estado"], "en revisión")
        detalle_corto = ticket['detalle'][:60] + "..." if len(ticket['detalle']) > 60 else ticket['detalle']

        response = f"Tu solicitud #{ticket['id']} ({detalle_corto}) {estado_msg}."

        # 📌 Como solo hay PENDIENTE_APROBACION, siempre es el mismo mensaje
        response += "\n\nTe avisaremos cuando sea aprobada y asignada al equipo."

        logger.info(
            "[TICKET_STATUS] Responded with specific ticket status",
            extra={
                "wa_id": wa_id,
                "ticket_id": ticket['id'],
                "estado": ticket['estado'],
                "location": "gateway_app/core/intents/ticket_status_handler.py"
            }
        )

        actions = [text_action(response)]
        return True, actions

    # 2️⃣ No menciona ID → consultar tickets recientes
    tickets = get_guest_tickets(wa_id, limit=5)

    if not tickets:
        logger.info(
            "[TICKET_STATUS] No tickets found for guest",
            extra={
                "wa_id": wa_id,
                "location": "gateway_app/core/intents/ticket_status_handler.py"
            }
        )

        lang = _lang(session)
        actions = [text_action(_T["no_tickets"][lang])]
        return True, actions


    # 3️⃣ Si solo hay 1 ticket → responder directamente
    if len(tickets) == 1:
        ticket = tickets[0]
        estado_msg = STATUS_MESSAGES.get(ticket["estado"], "en revisión")
        detalle_corto = ticket['detalle'][:60] + "..." if len(ticket['detalle']) > 60 else ticket['detalle']

        lang = _lang(session)
        response = _T["specific_ticket"][lang].format(
            ticket_id=ticket["id"],
            detail=detalle_corto,
            status_msg=_status_msg(ticket["estado"], lang),
        )

        logger.info(
            "[TICKET_STATUS] Responded with single ticket status",
            extra={
                "wa_id": wa_id,
                "ticket_id": ticket['id'],
                "estado": ticket['estado'],
                "location": "gateway_app/core/intents/ticket_status_handler.py"
            }
        )

        actions = [text_action(response)]
        return True, actions

    # 4️⃣ Si hay múltiples tickets → listar
    # 📌 Como todos están en PENDIENTE_APROBACION, simplemente listarlos
    lang = _lang(session)
    response = _T["multi_header"][lang].format(n=len(tickets))

    for i, t in enumerate(tickets[:3], 1):
        detalle_corto = t['detalle'][:40] + "..." if len(t['detalle']) > 40 else t['detalle']
        response += f"{i}. {detalle_corto}\n"

    if len(tickets) > 3:
        response += _T["more_count"][lang].format(more=(len(tickets) - 3))

    response += _T["multi_footer"][lang]

    logger.info(
        "[TICKET_STATUS] Responded with multiple tickets list",
        extra={
            "wa_id": wa_id,
            "ticket_count": len(tickets),
            "location": "gateway_app/core/intents/ticket_status_handler.py"
        }
    )

    actions = [text_action(response)]
    return True, actions
