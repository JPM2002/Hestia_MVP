# run.py
"""
Local dev entrypoint for the WhatsApp gateway service.

In production on Render, use gunicorn with: wsgi:app
"""

from gateway_app import create_app
from gateway_app.config import cfg

app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(getattr(cfg, "PORT", 8000)),
        debug=bool(getattr(cfg, "DEBUG", False)),
    )
