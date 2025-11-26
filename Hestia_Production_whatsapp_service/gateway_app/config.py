# gateway_app/config.py
import os
from dataclasses import dataclass


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Config:
    # Core envs from Render
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    INTERNAL_NOTIFY_TOKEN: str = os.getenv("INTERNAL_NOTIFY_TOKEN", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    TRANSCRIBE_PROVIDER: str = os.getenv("TRANSCRIBE_PROVIDER", "openai")

    WHATSAPP_CLOUD_PHONE_ID: str = os.getenv("WHATSAPP_CLOUD_PHONE_ID", "")
    WHATSAPP_CLOUD_TOKEN: str = os.getenv("WHATSAPP_CLOUD_TOKEN", "")
    WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")

    # Runtime / logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    ENV: str = os.getenv("ENV", "production")

    # Flags used by create_app()
    TESTING: bool = _get_bool("TESTING", False)
    DEBUG: bool = _get_bool("DEBUG", False)


cfg = Config()
