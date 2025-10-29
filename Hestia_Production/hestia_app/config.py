# hestia_app/config.py
import os
from datetime import timedelta

class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-env")
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    # Add other common settings here (DB, mail, etc.)
    # Example:
    # DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///hestia.db")
    # SQLALCHEMY_DATABASE_URI = DATABASE_URL
    # SQLALCHEMY_TRACK_MODIFICATIONS = False

class DevelopmentConfig(BaseConfig):
    DEBUG = True
    TEMPLATES_AUTO_RELOAD = True

class ProductionConfig(BaseConfig):
    DEBUG = False

class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = True

def get_config(env: str | None = None):
    """
    Returns a config class based on env.
    Priority: explicit arg > APP_ENV > FLASK_ENV > default (production on Render, dev otherwise)
    """
    if not env:
        env = (
            os.getenv("APP_ENV")
            or os.getenv("FLASK_ENV")
            or ("production" if os.getenv("RENDER") else "development")
        )

    env = str(env).lower()
    mapping = {
        "dev": DevelopmentConfig,
        "development": DevelopmentConfig,
        "prod": ProductionConfig,
        "production": ProductionConfig,
        "test": TestingConfig,
        "testing": TestingConfig,
    }
    return mapping.get(env, ProductionConfig)
