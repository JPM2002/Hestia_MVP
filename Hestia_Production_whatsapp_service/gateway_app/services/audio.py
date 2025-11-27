# gateway_app/services/audio.py
"""
Audio helpers for the WhatsApp gateway.

Responsibilities:
- Download voice notes from WhatsApp Cloud API given a media_id.
- Transcribe them using OpenAI (Whisper / gpt-4o-mini-transcribe).
- Expose `transcribe_whatsapp_audio(media_id, language="es")` for routes.py.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional

import requests
from openai import OpenAI

from gateway_app.config import cfg

logger = logging.getLogger(__name__)

# OpenAI client (uses OPENAI_API_KEY from env)
_client = OpenAI()

# WhatsApp Cloud API base (same version as whatsapp_api.py)
WHATSAPP_API_BASE = "https://graph.facebook.com/v21.0"

# Transcription provider (currently we only implement OpenAI)
_TRANSCRIBE_PROVIDER = (cfg.TRANSCRIBE_PROVIDER or "openai").lower()


# ---------------------------------------------------------------------------
# WhatsApp media download helpers
# ---------------------------------------------------------------------------


def _get_media_url(media_id: str) -> str:
    """
    Given a WhatsApp media_id, ask the Graph API for the actual download URL.

    GET /{media-id}
    Docs:
      https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media
    """
    token = (cfg.WHATSAPP_CLOUD_TOKEN or "").strip()
    if not token:
        raise RuntimeError("WHATSAPP_CLOUD_TOKEN is not configured; cannot download audio.")

    url = f"{WHATSAPP_API_BASE}/{media_id}"
    logger.debug("Fetching WhatsApp media metadata from %s", url)

    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    media_url = data.get("url")
    if not media_url:
        raise RuntimeError(f"No 'url' field in WhatsApp media metadata for id={media_id!r}")
    return media_url


def _download_media_to_temp(media_url: str) -> str:
    """
    Download the media file to a temporary file and return its path.
    """
    token = (cfg.WHATSAPP_CLOUD_TOKEN or "").strip()
    if not token:
        raise RuntimeError("WHATSAPP_CLOUD_TOKEN is not configured; cannot download audio.")

    logger.debug("Downloading WhatsApp media from %s", media_url)

    resp = requests.get(
        media_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
        stream=True,
    )
    resp.raise_for_status()

    # We don't know the exact extension; ogg/opus is typical for voice notes.
    fd, path = tempfile.mkstemp(suffix=".ogg")
    try:
        with os.fdopen(fd, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                f.write(chunk)
    except Exception:
        # If writing fails, make sure we don't leave an empty file lying around.
        try:
            os.remove(path)
        except Exception:
            pass
        raise

    logger.debug("WhatsApp media downloaded to %s", path)
    return path


# ---------------------------------------------------------------------------
# OpenAI transcription helper
# ---------------------------------------------------------------------------


def _transcribe_with_openai(file_path: str, language: Optional[str] = None) -> str:
    """
    Transcribe an audio file using OpenAI.

    Uses the newer audio transcription models. Adjust model name if needed.
    """
    # Choose a default model suitable for speech recognition.
    # If you prefer classic Whisper, you can use "whisper-1".
    model_name = os.getenv("TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")

    logger.info(
        "Transcribing audio with OpenAI",
        extra={"model": model_name, "language": language},
    )

    with open(file_path, "rb") as f:
        resp = _client.audio.transcriptions.create(
            model=model_name,
            file=f,
            language=language or None,  # let model auto-detect if not provided
        )

    # For the 1.x OpenAI client, `resp.text` holds the transcript.
    text = getattr(resp, "text", "") or ""
    return text.strip()


# ---------------------------------------------------------------------------
# Public API used by routes.py
# ---------------------------------------------------------------------------


def transcribe_whatsapp_audio(media_id: str, language: str = "es") -> str:
    """
    Main entrypoint used by the webhook:

        text = audio_svc.transcribe_whatsapp_audio(media_id=audio_media_id, language="es")

    Steps:
    - Ask WhatsApp API for the media URL.
    - Download the file to a temp path.
    - Transcribe with the configured provider (OpenAI).
    - Return the transcript text (may be empty string if something fails).
    """
    if not media_id:
        logger.warning("transcribe_whatsapp_audio called with empty media_id")
        return ""

    logger.info("Starting transcription for media_id=%s", media_id)

    tmp_path: Optional[str] = None
    try:
        media_url = _get_media_url(media_id)
        tmp_path = _download_media_to_temp(media_url)

        if _TRANSCRIBE_PROVIDER in {"openai", "whisper", "whisper_openai", "gpt4o"}:
            return _transcribe_with_openai(tmp_path, language=language)

        # Unknown provider: log and return empty text, rather than crashing webhook.
        logger.error(
            "Unknown TRANSCRIBE_PROVIDER=%r; supported: 'openai'",
            _TRANSCRIBE_PROVIDER,
        )
        return ""
    except Exception:
        logger.exception("Error while transcribing WhatsApp audio (media_id=%s)", media_id)
        return ""
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                logger.warning("Could not remove temp audio file %s", tmp_path)
