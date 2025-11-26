# wsgi.py
from gateway_app import create_app

# Objeto WSGI que usará gunicorn / Render
app = create_app()
