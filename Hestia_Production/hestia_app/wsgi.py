# hestia_app/wsgi.py
import os
from . import create_app

app = create_app(os.getenv("FLASK_ENV", "production"))

# Optional: list routes once at boot
if os.getenv("PRINT_ROUTES") == "1":
    for rule in app.url_map.iter_rules():
        print("ROUTE:", rule, "→ endpoint:", rule.endpoint)
