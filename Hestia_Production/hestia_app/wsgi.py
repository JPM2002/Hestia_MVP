# hestia_app/wsgi.py
import os
from . import create_app

app = create_app(os.getenv("APP_ENV"))
