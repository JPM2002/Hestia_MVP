#!/usr/bin/env python3
"""
Script de ejecución para Notification Worker

Este script inicializa y ejecuta el worker de notificaciones que monitorea
la base de datos y envía notificaciones automáticas de WhatsApp.

Uso:
    python run_notification_worker.py

    # O con variables de entorno específicas:
    POLLING_INTERVAL_SECONDS=5 python run_notification_worker.py
"""

import sys
import os
from pathlib import Path

# Agregar el directorio raíz al Python path
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

# Cargar variables de entorno
from dotenv import load_dotenv
load_dotenv()

# Importar y ejecutar el worker
from gateway_app.workers.notification_worker import main

if __name__ == "__main__":
    print("=" * 80)
    print("🔔 Hestia Notification Worker")
    print("=" * 80)
    print(f"Working directory: {os.getcwd()}")
    print(f"Python path: {sys.path[0]}")
    print("=" * 80)
    print()

    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Worker detenido por el usuario")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Error fatal: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
