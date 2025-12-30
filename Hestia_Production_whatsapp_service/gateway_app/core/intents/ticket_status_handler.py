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

            actions = [text_action(
                f"No encontré la solicitud #{ticket_id} asociada a tu cuenta. "
                "¿Seguro que ese es el número correcto?"
            )]
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

        actions = [text_action(
            "No encontré solicitudes anteriores asociadas a tu cuenta. "
            "Si necesitas reportar algo, solo cuéntame qué necesitas."
        )]
        return True, actions

    # 3️⃣ Si solo hay 1 ticket → responder directamente
    if len(tickets) == 1:
        ticket = tickets[0]
        estado_msg = STATUS_MESSAGES.get(ticket["estado"], "en revisión")
        detalle_corto = ticket['detalle'][:60] + "..." if len(ticket['detalle']) > 60 else ticket['detalle']

        response = f"Tu solicitud \"{detalle_corto}\" {estado_msg}."
        response += "\n\nTe notificaremos cuando haya novedades."

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
    response = f"Tienes {len(tickets)} solicitudes pendientes de aprobación:\n\n"

    for i, t in enumerate(tickets[:3], 1):  # Máximo 3
        detalle_corto = t['detalle'][:40] + "..." if len(t['detalle']) > 40 else t['detalle']
        response += f"{i}. {detalle_corto}\n"

    if len(tickets) > 3:
        response += f"\n... y {len(tickets) - 3} más.\n"

    response += "\nTodas están esperando ser aprobadas y asignadas. Te avisaremos cuando haya novedades."

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
