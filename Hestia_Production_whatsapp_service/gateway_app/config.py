# gateway_app/config.py
"""
Central configuration for the WhatsApp gateway service.

All configuration is read from environment variables so it works
both locally and on Render.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    # Flask / runtime
    ENV: str = os.getenv("FLASK_ENV", "production")
    DEBUG: bool = _as_bool(os.getenv("DEBUG"), False)
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-change-me")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # OpenAI + LLM models
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    TRANSCRIBE_PROVIDER: str = os.getenv("TRANSCRIBE_PROVIDER", "openai")
    GUEST_LLM_MODEL: str = os.getenv("GUEST_LLM_MODEL", "gpt-4.1-mini")
    FAQ_LLM_MODEL: str = os.getenv("FAQ_LLM_MODEL", "gpt-4.1-mini")

    # WhatsApp Cloud API
    WHATSAPP_CLOUD_TOKEN: str = os.getenv("WHATSAPP_CLOUD_TOKEN", "")
    WHATSAPP_CLOUD_PHONE_ID: str = os.getenv("WHATSAPP_CLOUD_PHONE_ID", "")
    WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")

    # Internal notifications (to main Hestia app or other backend)
    INTERNAL_NOTIFY_TOKEN: str = os.getenv("INTERNAL_NOTIFY_TOKEN", "")

    # Optional: base URL of the main Hestia backend if we need to call it
    HESTIA_BACKEND_BASE_URL: str = os.getenv("HESTIA_BACKEND_BASE_URL", "")


cfg = Config()
