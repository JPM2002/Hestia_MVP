# hestia_app/core/status.py

ESTADO_NICE = {
    "PENDIENTE": "Pendiente",
    "ASIGNADO": "Asignado",
    "ACEPTADO": "Aceptado",
    "EN_CURSO": "En curso",
    "PAUSADO": "Pausado",
    "DERIVADO": "Derivado",
    "RESUELTO": "Resuelto",
    "PENDIENTE_APROBACION": "Pendiente de aprobación",
}

def nice_state(code: str) -> str:
    if not code:
        return ""
    return ESTADO_NICE.get(str(code).upper(), str(code).title())

OPEN_STATES = ("PENDIENTE_APROBACION","PENDIENTE","ASIGNADO","ACEPTADO","EN_CURSO","PAUSADO","DERIVADO")
