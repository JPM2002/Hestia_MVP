# hestia_app/wsgi.py
import os
from . import create_app

app = create_app(os.getenv("FLASK_ENV", "production"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
