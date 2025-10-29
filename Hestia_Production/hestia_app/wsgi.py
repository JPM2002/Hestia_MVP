# hestia_app/wsgi.py
# Gunicorn entrypoint: hestia_app.wsgi:app
from . import app  # app is created in __init__.py
