# gunicorn.conf.py
import os

# Render establece $PORT automáticamente
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# IMPORTANTE:
# Mientras las sesiones estén en memoria (_SESSIONS en state.py),
# debemos usar UN SOLO worker para que todas las requests del mismo huésped
# lleguen al mismo proceso.
#
# Puedes sobreescribir WEB_CONCURRENCY en Render, pero el default será 1.
workers = int(os.getenv("WEB_CONCURRENCY", "1"))

# Opcional: también fijar threads a 1 para simplificar el modelo de concurrencia.
threads = int(os.getenv("GUNICORN_THREADS", "1"))

timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOGLEVEL", "info")
