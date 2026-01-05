"""
Servicio de notificaciones a huéspedes por WhatsApp.
Maneja notificaciones de cambio de estado y encuestas CSAT.
"""

from datetime import datetime
from .whatsapp import send_whatsapp
from .db import execute, fetchone


# Mensajes de notificación por estado
STATE_MESSAGES = {
    "ASIGNADO": "¡Hola! Ya asignamos un técnico para tu solicitud. Pronto se pondrá en contacto contigo.",
    "ACEPTADO": "¡Buenas noticias! El técnico aceptó tu solicitud y está en camino.",
    "EN_CURSO": "Tu solicitud está siendo atendida en este momento.",
    "PAUSADO": "Tu solicitud fue pausada temporalmente. Te avisaremos cuando continuemos.",
    "DERIVADO": "Derivamos tu solicitud a otra área para darte mejor atención.",
}

# Mensajes de encuesta CSAT
SURVEY_Q1_MESSAGE = """¡Listo! Tu solicitud ha sido resuelta.

¿Qué tan satisfecho quedaste con el servicio?

Responde del 1 al 5:
1 - Muy insatisfecho
5 - Muy satisfecho"""

SURVEY_Q2_LOW_MESSAGE = "¿Qué podríamos haber hecho mejor?"
SURVEY_Q2_HIGH_MESSAGE = "¡Qué bueno! ¿Qué fue lo que más te gustó?"

SURVEY_Q3_MESSAGE = """Una última pregunta: ¿qué tan útil te pareció usar WhatsApp para esto?

Del 1 al 5:
1 - Nada útil
5 - Muy útil"""

SURVEY_THANK_YOU_MESSAGE = """¡Gracias por tu tiempo! Nos ayuda mucho a mejorar. 🙏

Si necesitas algo más, escríbenos cuando quieras."""


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


def send_csat_survey(ticket_id: int, guest_phone: str, org_id: int, hotel_id: int):
    """
    Crea registro de encuesta CSAT y envía primera pregunta.
    Se ejecuta inmediatamente después de marcar ticket como RESUELTO.

    Args:
        ticket_id: ID del ticket resuelto
        guest_phone: Número WhatsApp del huésped
        org_id: ID de la organización
        hotel_id: ID del hotel
    """
    try:
        # 1. Verificar que no exista encuesta previa (idempotencia)
        existing = fetchone(
            "SELECT id FROM csat_surveys WHERE ticket_id = ?",
            (ticket_id,)
        )

        if existing:
            print(f"[CSAT] Ticket {ticket_id}: Ya existe encuesta, skip", flush=True)
            return

        # 2. Crear registro de encuesta
        now = datetime.utcnow().isoformat()

        execute("""
            INSERT INTO csat_surveys (
                ticket_id,
                guest_phone,
                org_id,
                hotel_id,
                survey_state,
                created_at,
                scheduled_at,
                survey_started_at,
                guest_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticket_id,
            guest_phone,
            org_id,
            hotel_id,
            'q1_sent',
            now,
            now,  # Sin delay, scheduled_at = created_at
            now,  # survey_started_at = now (envío inmediato)
            'active'
        ))

        print(f"[CSAT] Ticket {ticket_id}: Registro creado con estado q1_sent", flush=True)

        # 3. Enviar Q1 (CSAT) inmediatamente
        send_whatsapp(
            to=guest_phone,
            body=SURVEY_Q1_MESSAGE,
            tag="SURVEY_Q1"
        )

        print(f"[CSAT] Ticket {ticket_id}: Q1 enviada a {guest_phone}", flush=True)

    except Exception as e:
        # No fallar el flujo principal
        print(f"[CSAT] Error al enviar encuesta para ticket {ticket_id}: {e}", flush=True)
