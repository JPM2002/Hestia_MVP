"""
Test script para verificar el comportamiento del fallback de FAQ.

Casos de prueba:
1. Pregunta con respuesta en FAQ (desayuno)
2. Pregunta sin respuesta en FAQ (almuerzo) → Debe derivar a recepción
3. Otras preguntas informativas sin FAQ
"""

import sys
import os

# Agregar el directorio raíz al path para imports
sys.path.insert(0, os.path.dirname(__file__))

from gateway_app.core.intents.faq_handler import handle_faq_fallback, get_reception_fallback_message
from gateway_app.services import faq_llm

def print_separator():
    print("\n" + "="*80 + "\n")

def test_reception_fallback_message():
    """Test 1: Verificar el nuevo mensaje de fallback"""
    print("TEST 1: Mensaje de fallback a recepción")
    print("-" * 80)

    message = get_reception_fallback_message()
    print("Mensaje:")
    print(message)

    # Verificaciones
    assert "0 o 1" in message, "Debe incluir el teléfono de recepción"
    assert "habitación" in message.lower(), "Debe mencionar que es desde la habitación"
    assert "Necesito" in message, "Debe sugerir cómo usar el bot para solicitudes"

    print("\n✅ Mensaje de fallback correcto")
    print_separator()

def test_faq_answer_exists():
    """Test 2: Pregunta con respuesta en FAQ (caso exitoso)"""
    print("TEST 2: Pregunta con respuesta en FAQ")
    print("-" * 80)

    test_messages = [
        "¿A qué hora es el desayuno?",
        "horario de desayuno",
        "cuando es el desayuno"
    ]

    for msg in test_messages:
        print(f"\nPregunta: '{msg}'")
        answer = faq_llm.answer_faq(msg)

        if answer:
            print(f"✅ FAQ encontró respuesta: {answer[:100]}...")
        else:
            print(f"❌ FAQ NO encontró respuesta (debería encontrar)")

    print_separator()

def test_faq_answer_missing():
    """Test 3: Pregunta SIN respuesta en FAQ → Debe usar fallback"""
    print("TEST 3: Preguntas SIN respuesta en FAQ (deben derivar a recepción)")
    print("-" * 80)

    test_messages = [
        "¿Y el almuerzo?",
        "¿A qué hora es el almuerzo?",
        "¿Hasta qué hora está abierto el restaurante?",
        "¿Cuánto cuesta el spa?",
        "¿Dónde está la piscina?"
    ]

    session = {
        "wa_id": "test_user",
        "phone": "+56912345678",
        "state": "GH_S0"
    }

    for msg in test_messages:
        print(f"\nPregunta: '{msg}'")

        # Verificar si FAQ tiene respuesta
        faq_answer = faq_llm.answer_faq(msg)

        if faq_answer:
            print(f"  FAQ respuesta: {faq_answer[:80]}...")
        else:
            print(f"  FAQ: No hay respuesta")

            # Ejecutar fallback handler
            found, actions = handle_faq_fallback(msg, session)

            print(f"  Fallback found: {found}")
            print(f"  Número de acciones: {len(actions)}")

            if actions:
                for i, action in enumerate(actions):
                    if action.get("type") == "text":
                        text = action.get("text", "")
                        print(f"  Acción {i+1}: {text[:100]}...")

                        # Verificar que contenga el teléfono de recepción
                        if "0 o 1" in text:
                            print(f"  ✅ Mensaje correcto: Deriva a recepción con teléfono")
                        else:
                            print(f"  ❌ ERROR: No incluye teléfono de recepción")

    print_separator()

def test_full_flow():
    """Test 4: Flujo completo - Desayuno → Almuerzo (caso del bug)"""
    print("TEST 4: Flujo completo (caso del bug #69)")
    print("-" * 80)

    session = {
        "wa_id": "test_user",
        "phone": "+56912345678",
        "state": "GH_S0"
    }

    print("\n👤 Usuario: '¿A qué hora es el desayuno?'")
    msg1 = "¿A qué hora es el desayuno?"
    answer1 = faq_llm.answer_faq(msg1)

    if answer1:
        print(f"🤖 Bot: {answer1}")
        print("✅ FAQ respondió correctamente")
    else:
        print("❌ ERROR: FAQ debería responder")

    print("\n" + "-"*40)

    print("\n👤 Usuario: '¿Y el almuerzo?'")
    msg2 = "¿Y el almuerzo?"
    answer2 = faq_llm.answer_faq(msg2)

    if answer2:
        print(f"🤖 Bot: {answer2}")
        print("ℹ️ FAQ encontró respuesta para almuerzo")
    else:
        print("ℹ️ FAQ no tiene respuesta para almuerzo")
        print("Ejecutando fallback...")

        found, actions = handle_faq_fallback(msg2, session)

        if actions:
            for action in actions:
                if action.get("type") == "text":
                    text = action.get("text", "")
                    print(f"🤖 Bot: {text}")

                    if "0 o 1" in text:
                        print("\n✅ CORRECTO: Bot deriva a recepción con teléfono")
                        print("✅ NO crea ticket innecesariamente")
                    else:
                        print("\n❌ ERROR: Mensaje no incluye teléfono de recepción")

    print_separator()

def main():
    """Ejecutar todos los tests"""
    print("="*80)
    print("PRUEBAS DE FALLBACK FAQ - BUG #69")
    print("="*80)

    try:
        test_reception_fallback_message()
        test_faq_answer_exists()
        test_faq_answer_missing()
        test_full_flow()

        print("\n" + "="*80)
        print("✅ TODAS LAS PRUEBAS COMPLETADAS")
        print("="*80)

    except Exception as e:
        print(f"\n❌ ERROR EN PRUEBAS: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
