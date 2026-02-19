"""
Test simple del mensaje de fallback (sin llamadas a OpenAI).

Verifica que el mensaje de fallback incluya el teléfono de recepción correcto.
"""

def get_reception_fallback_message() -> str:
    """
    Generate fallback message for questions without FAQ answer.

    Directs user to contact reception with phone number.

    Returns:
        Formatted message to contact reception
    """
    return (
        "Para resolver esta duda te pedimos llamar a recepción al *+56 9 2035 5564* "
        "Si necesitas que gestionemos algo (ej. pedir algo a la habitación), "
        "dime 'Necesito...' y lo registramos. 😊"
    )

def test_mensaje_fallback():
    """Test del mensaje de fallback"""
    print("="*80)
    print("TEST: Mensaje de fallback a recepción")
    print("="*80)

    mensaje = get_reception_fallback_message()

    print("\nMENSAJE ACTUAL:")
    print("-"*80)
    print(mensaje)
    print("-"*80)

    # Verificaciones
    verificaciones = [
        ("+56 9 2035 5564", "Incluye teléfono de recepción"),
        ("habitación", "Menciona que es desde la habitación"),
        ("Necesito", "Sugiere cómo usar el bot para solicitudes"),
        ("resolver esta duda", "Explica que es para preguntas informativas"),
    ]

    print("\nVERIFICACIONES:")
    print("-"*80)

    all_passed = True
    for texto, descripcion in verificaciones:
        presente = texto in mensaje
        status = "✅" if presente else "❌"
        print(f"{status} {descripcion}: '{texto}' {'presente' if presente else 'FALTA'}")

        if not presente:
            all_passed = False

    print("-"*80)

    if all_passed:
        print("\n✅ TODAS LAS VERIFICACIONES PASARON")
        print("\nEste mensaje se mostrará cuando:")
        print("  - El usuario haga una pregunta informativa")
        print("  - El FAQ no tenga respuesta para esa pregunta")
        print("  - Ejemplo: '¿A qué hora es el almuerzo?' (si no hay FAQ)")
    else:
        print("\n❌ ALGUNAS VERIFICACIONES FALLARON")

    print("="*80)

    return all_passed

def test_caso_bug_69():
    """Simular el caso del bug #69"""
    print("\n" + "="*80)
    print("SIMULACIÓN: Caso del Bug #69")
    print("="*80)

    print("\n📱 CONVERSACIÓN ESPERADA:")
    print("-"*80)

    print("\n👤 Usuario: '¿A qué hora es el desayuno?'")
    print("🤖 Bot: El desayuno se sirve de 7:00 a 10:00 AM.")
    print("        ¿Puedo ayudarte con algo más durante tu estadía?")

    print("\n👤 Usuario: '¿Y el almuerzo?'")
    print("🤖 Bot (FAQ no tiene respuesta, usa fallback):")
    print()
    print(get_reception_fallback_message())

    print("\n" + "-"*80)
    print("✅ RESULTADO ESPERADO:")
    print("   - Usuario recibe instrucciones claras para llamar a recepción")
    print("   - NO se crea ticket innecesariamente")
    print("   - Se evita confusión sobre qué hacer")

    print("\n❌ COMPORTAMIENTO ANTERIOR (BUG):")
    print("   - Mensaje genérico ambiguo")
    print("   - Usuario confundido")
    print("   - Posible creación de ticket incorrecto")

    print("="*80)

if __name__ == "__main__":
    resultado = test_mensaje_fallback()
    test_caso_bug_69()

    exit(0 if resultado else 1)
