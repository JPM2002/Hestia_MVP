
# Configuración de textos por área
TEXTOS_POR_AREA = {
    "HOUSEKEEPING": {
        "ubicacion_label": "🏠 Habitación",
        "ubicacion_pregunta": "🏠 ¿Qué habitación?\n\nEj: 305, 1503",
        "ubicacion_ejemplo": "305",
    },
    "AREAS_COMUNES": {
        "ubicacion_label": "📍 Área",
        "ubicacion_pregunta": (
            "📍 ¿Qué área?\n\n"
            "Ejemplos:\n"
            "• ascensor piso 3\n"
            "• cafetería\n"
            "• lobby\n"
            "• pasillo piso 2"
        ),
        "ubicacion_ejemplo": "Cafetería",
    },
    "MANTENIMIENTO": {
        "ubicacion_label": "📍 Ubicación",
        "ubicacion_pregunta": "📍 ¿Dónde está el problema?\n\nEj: calderas, roof, sistema eléctrico",
        "ubicacion_ejemplo": "Calderas",
    }
}

def get_texto_por_area(area_worker: str, clave: str) -> str:
    """
    Obtiene texto adaptado según el área del worker.
    
    Args:
        area_worker: Área del worker
        clave: Clave del texto a obtener
    
    Returns:
        Texto adaptado
    """
    textos = TEXTOS_POR_AREA.get(area_worker, TEXTOS_POR_AREA["HOUSEKEEPING"])
    return textos.get(clave, "")

def formatear_ubicacion_para_mensaje(ubicacion: str, area_worker: str) -> str:
    """
    Formatea la ubicación para mostrar en mensajes.
    
    Args:
        ubicacion: Ubicación extraída
        area_worker: Área del worker
    
    Returns:
        Ubicación formateada con emoji
    
    Ejemplos:
        ("305", "HOUSEKEEPING") → "🏠 Habitación: 305"
        ("Ascensor Piso 3", "AREAS_COMUNES") → "📍 Área: Ascensor Piso 3"
    """
    label = get_texto_por_area(area_worker, "ubicacion_label")
    return f"{label}: {ubicacion}"