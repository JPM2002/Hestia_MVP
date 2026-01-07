"""
Servicio de notificaciones a huéspedes por WhatsApp.
Maneja notificaciones de cambio de estado de tickets.
"""

from .whatsapp import send_whatsapp
from .db import fetchone


# Mensajes de notificación por estado
STATE_MESSAGES = {
    "ASIGNADO": "¡Hola! Ya asignamos un técnico para tu solicitud. Pronto se pondrá en contacto contigo.",
    "ACEPTADO": "¡Buenas noticias! El técnico aceptó tu solicitud y está en camino.",
    "EN_CURSO": "Tu solicitud está siendo atendida en este momento.",
    "PAUSADO": "Tu solicitud fue pausada temporalmente. Te avisaremos cuando continuemos.",
    "DERIVADO": "Derivamos tu solicitud a otra área para darte mejor atención.",
}


def notify_state_change(ticket_id: int, new_state: str):
    """
    Envía notificación al huésped cuando cambia el estado del ticket.

    Args:
        ticket_id: ID del ticket
        new_state: Nuevo estado (ASIGNADO, ACEPTADO, EN_CURSO, etc.)
    """
    # Solo notificar para estados específicos
    if new_state not in STATE_MESSAGES:
        return

    try:
        # Obtener huesped_whatsapp del ticket
        ticket = fetchone(
            "SELECT huesped_whatsapp FROM Tickets WHERE id = ?",
            (ticket_id,)
        )

        if not ticket or not ticket.get("huesped_whatsapp"):
            # No hay WhatsApp, skip notificación
            print(f"[NOTIFY] Ticket {ticket_id}: No huesped_whatsapp, skip", flush=True)
            return

        guest_phone = ticket["huesped_whatsapp"].strip()
        if not guest_phone:
            return

        # Obtener mensaje para el estado
        message = STATE_MESSAGES[new_state]

        # Enviar por WhatsApp
        send_whatsapp(
            to=guest_phone,
            body=message,
            tag=f"STATE_{new_state}"
        )

        print(f"[NOTIFY] Ticket {ticket_id}: Notificación '{new_state}' enviada a {guest_phone}", flush=True)

    except Exception as e:
        # No fallar el flujo principal si falla WhatsApp
        print(f"[NOTIFY] Error al notificar ticket {ticket_id}: {e}", flush=True)


