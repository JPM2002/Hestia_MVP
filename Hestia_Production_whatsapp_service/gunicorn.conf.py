# gunicorn.conf.py
import multiprocessing
import os

# Render establece $PORT automáticamente
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# Workers: 2 * CPU + 1 por defecto, pero configurable
workers = int(os.getenv("WEB_CONCURRENCY", str(multiprocessing.cpu_count() * 2 + 1)))

timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOGLEVEL", "info")
