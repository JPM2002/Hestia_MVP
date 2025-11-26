# gateway_app/blueprints/webhook/__init__.py
"""
Webhook blueprint package.

Exposes:
    bp  -> the Flask Blueprint for WhatsApp webhooks.
"""

from .routes import bp

__all__ = ["bp"]
