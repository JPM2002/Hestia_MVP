# gateway_app/wsgi.py
"""
WSGI entrypoint for the WhatsApp gateway app package.

This is what gunicorn will import as `gateway_app.wsgi:app`.
"""

from __future__ import annotations

from gateway_app import create_app

# WSGI application object
app = create_app()
