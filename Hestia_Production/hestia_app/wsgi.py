import os
from hestia_app import create_app

# Do NOT pass any positional arg if your factory takes none
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
