# config.py
import os

class Base:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    ENABLE_TECH_DEMO = os.getenv("ENABLE_TECH_DEMO", "0") == "1"
    DATABASE_URL = os.getenv("DATABASE_URL")  # Postgres on Render
    SLA_TARGET = float(os.getenv("SLA_TARGET", "0.90"))  # default 90%

class Production(Base):
    DEBUG = False

class Development(Base):
    DEBUG = True

def load_config(app):
    env = os.getenv("APP_ENV", "production").lower()
    app.config.from_object(Development if env.startswith("dev") else Production)
