"""
Script de diagnóstico para el Notification Worker
Verifica por qué no se están enviando las encuestas FAQ
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Agregar el path del proyecto
sys.path.insert(0, os.path.dirname(__file__))

from gateway_app.services.notifications import notification_db as db
from gateway_app.services.notifications.notification_config import notification_cfg

print("=" * 80)
print("DIAGNÓSTICO DEL NOTIFICATION WORKER")
print("=" * 80)
print()

# 1. Verificar configuración
print("1. CONFIGURACIÓN:")
print("-" * 80)
notification_cfg.log_config()
print()

# 2. Verificar conexión a BD
print("2. CONEXIÓN A BASE DE DATOS:")
print("-" * 80)
try:
    test_query = "SELECT 1 as test"
    result = db.fetchone(test_query)
    print(f"[OK] Conexion exitosa: {result}")
    print(f"[OK] Usando PostgreSQL: {db.using_pg()}")
except Exception as e:
    print(f"[ERROR] Error de conexion: {e}")
    sys.exit(1)
print()

# 3. Verificar conversaciones pendientes de encuesta FAQ
print("3. CONVERSACIONES FAQ PENDIENTES:")
print("-" * 80)

delay_seconds = notification_cfg.FAQ_SURVEY_DELAY_SECONDS
cutoff_time = (datetime.utcnow() - timedelta(seconds=delay_seconds)).isoformat()

print(f"Delay configurado: {delay_seconds} segundos ({delay_seconds/60:.0f} minutos)")
print(f"Cutoff time: {cutoff_time}")
print(f"Hora actual UTC: {datetime.utcnow().isoformat()}")
print()

sql = """
    SELECT
        id,
        wa_id,
        faq_count,
        survey_sent,
        created_at,
        updated_at,
        EXTRACT(EPOCH FROM (NOW() - updated_at)) as seconds_inactive
    FROM conversation_logs
    WHERE faq_count > 0
      AND (survey_sent IS NULL OR survey_sent = FALSE)
      AND wa_id IS NOT NULL
    ORDER BY updated_at DESC
    LIMIT 10
"""

try:
    conversations = db.fetchall(sql)
    print(f"Total conversaciones con FAQs sin encuesta: {len(conversations)}")
    print()

    if conversations:
        for conv in conversations:
            inactive_mins = conv['seconds_inactive'] / 60
            meets_delay = conv['seconds_inactive'] >= delay_seconds

            print(f"Conversación ID {conv['id']}:")
            print(f"  wa_id: {conv['wa_id']}")
            print(f"  faq_count: {conv['faq_count']}")
            print(f"  survey_sent: {conv['survey_sent']}")
            print(f"  updated_at: {conv['updated_at']}")
            print(f"  Inactivo: {inactive_mins:.1f} minutos")
            print(f"  Cumple delay? {'[OK] SÍ' if meets_delay else '[X] NO (falta ' + str(int((delay_seconds - conv['seconds_inactive'])/60)) + ' min)'}")
            print()
    else:
        print("No hay conversaciones con FAQs sin encuesta")

except Exception as e:
    print(f"[X] Error al consultar conversaciones: {e}")
    import traceback
    traceback.print_exc()
print()

# 4. Verificar qué detectaría el worker AHORA
print("4. CONVERSACIONES QUE EL WORKER DETECTARÍA AHORA:")
print("-" * 80)

ph = "%s" if db.using_pg() else "?"
sql_worker = f"""
    SELECT id, wa_id, faq_count, updated_at
    FROM conversation_logs
    WHERE faq_count > 0
      AND (survey_sent IS NULL OR survey_sent = FALSE)
      AND updated_at < {ph}
      AND wa_id IS NOT NULL
    LIMIT 50
"""

try:
    detected = db.fetchall(sql_worker, [cutoff_time])
    print(f"Total que detectaría el worker: {len(detected)}")
    print()

    if detected:
        for conv in detected:
            print(f"  ID {conv['id']}: wa_id={conv['wa_id']}, faq_count={conv['faq_count']}, updated_at={conv['updated_at']}")
    else:
        print("  El worker NO detectaría ninguna conversación ahora")

except Exception as e:
    print(f"[X] Error: {e}")
    import traceback
    traceback.print_exc()
print()

# 5. Verificar módulo de WhatsApp
print("5. MÓDULO DE WHATSAPP:")
print("-" * 80)
try:
    from gateway_app.services.notifications import notification_whatsapp as wa
    print("[OK] Módulo notification_whatsapp importado correctamente")

    # Verificar configuración de WhatsApp
    phone_id = os.getenv("WHATSAPP_CLOUD_PHONE_ID")
    token = os.getenv("WHATSAPP_CLOUD_TOKEN")

    if phone_id:
        print(f"[OK] WHATSAPP_CLOUD_PHONE_ID: {phone_id[:10]}...")
    else:
        print("[X] WHATSAPP_CLOUD_PHONE_ID no configurado")

    if token:
        print(f"[OK] WHATSAPP_CLOUD_TOKEN: {token[:20]}...")
    else:
        print("[X] WHATSAPP_CLOUD_TOKEN no configurado")

except Exception as e:
    print(f"[X] Error al importar módulo WhatsApp: {e}")
    import traceback
    traceback.print_exc()
print()

# 6. Test del handler
print("6. TEST DEL HANDLER:")
print("-" * 80)
try:
    from gateway_app.services.notifications.handlers import handle_faq_surveys

    print("Ejecutando handle_faq_surveys()...")
    count = handle_faq_surveys()
    print(f"Resultado: {count} encuestas enviadas")

except Exception as e:
    print(f"[X] Error al ejecutar handler: {e}")
    import traceback
    traceback.print_exc()
print()

print("=" * 80)
print("DIAGNÓSTICO COMPLETADO")
print("=" * 80)
