# wsgi.py
"""
WSGI entrypoint for the WhatsApp gateway service.

Gunicorn on Render should point to: wsgi:app
"""

from gateway_app import create_app

# WSGI application object used by gunicorn
app = create_app()
