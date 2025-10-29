# hestia_app/wsgi.py
# Gunicorn entrypoint: hestia_app.wsgi:app
from . import create_app

app = create_app()
