# run.py
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

from gateway_app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
