# gateway_app/services/audio.py
"""
Audio download + transcription helpers for WhatsApp voice notes.

Responsibilities:
- Fetch media from WhatsApp Cloud API using a media_id.
- Store audio in a temporary file.
- Transcribe using the provider indicated by TRANSCRIBE_PROVIDER.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Optional, Tuple

import requests
from openai import OpenAI

from gateway_app.config import cfg

logger = logging.getLogger(__name__)

WHATSAPP_API_BASE = "https://graph.facebook.com/v21.0"


@dataclass
class AudioDownloadResult:
    path: str
    mime_type: Optional[str]


class AudioError(RuntimeError):
    """Raised for audio download or transcription issues."""


def _whatsapp_headers() -> dict:
    if not cfg.WHATSAPP_CLOUD_TOKEN:
        logger.error("WHATSAPP_CLOUD_TOKEN is not configured for audio download.")
    return {
        "Authorization": f"Bearer {cfg.WHATSAPP_CLOUD_TOKEN}",
    }


def fetch_whatsapp_media_url(media_id: str) -> Tuple[str, Optional[str]]:
    """
    Step 1: Get the direct media URL from a WhatsApp media_id.

    This calls:
      GET /{media_id}
    which returns JSON with a "url" field and "mime_type".
    """
    url = f"{WHATSAPP_API_BASE}/{media_id}"
    logger.info("Fetching WhatsApp media URL", extra={"media_id": media_id})

    resp = requests.get(url, headers=_whatsapp_headers(), timeout=15)
    try:
        data = resp.json()
    except Exception as exc:
        logger.exception("Failed to decode WhatsApp media metadata JSON")
        raise AudioError(f"Invalid JSON from WhatsApp media metadata: {exc}") from exc

    if not resp.ok:
        logger.error("WhatsApp media metadata error %s: %s", resp.status_code, data)
        raise AudioError(f"WhatsApp media metadata error {resp.status_code}: {data}")

    media_url = data.get("url")
    mime_type = data.get("mime_type")
    if not media_url:
        logger.error("WhatsApp media metadata missing 'url' field: %s", data)
        raise AudioError("WhatsApp media metadata missing 'url' field")

    return media_url, mime_type


def download_whatsapp_media_to_temp(media_id: str) -> AudioDownloadResult:
    """
    Download WhatsApp media identified by media_id into a temp file.

    Returns:
        AudioDownloadResult(path=temp_file_path, mime_type=original_mime_type)
    """
    media_url, mime_type = fetch_whatsapp_media_url(media_id)

    logger.info(
        "Downloading WhatsApp media",
        extra={"media_id": media_id, "mime_type": mime_type},
    )

    resp = requests.get(media_url, headers=_whatsapp_headers(), timeout=30, stream=True)
    if not resp.ok:
        logger.error("WhatsApp media download error %s", resp.status_code)
        raise AudioError(f"WhatsApp media download error {resp.status_code}")

    suffix = _guess_extension_from_mime(mime_type)
    fd, path = tempfile.mkstemp(suffix=suffix or ".bin", prefix="wa_audio_")
    os.close(fd)

    try:
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    except Exception as exc:
        logger.exception("Failed to write WhatsApp media to temp file")
        # Best-effort cleanup
        try:
            os.remove(path)
        except OSError:
            pass
        raise AudioError(f"Failed to write media to temp file: {exc}") from exc

    logger.info("WhatsApp media stored to temp file", extra={"path": path})
    return AudioDownloadResult(path=path, mime_type=mime_type)


def _guess_extension_from_mime(mime_type: Optional[str]) -> Optional[str]:
    if not mime_type:
        return None
    # Very small mapping; expand as needed
    if "ogg" in mime_type:
        return ".ogg"
    if "mpeg" in mime_type or "mp3" in mime_type:
        return ".mp3"
    if "wav" in mime_type:
        return ".wav"
    if "m4a" in mime_type or "mp4" in mime_type:
        return ".m4a"
    return None


# ---------- Transcription ----------


def _openai_client() -> OpenAI:
    if not cfg.OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY is not configured for transcription.")
        raise AudioError("OPENAI_API_KEY is missing; cannot transcribe audio.")
    return OpenAI(api_key=cfg.OPENAI_API_KEY)


def transcribe_file(
    file_path: str,
    language: Optional[str] = None,
) -> str:
    """
    Transcribe a local audio file using the provider set in TRANSCRIBE_PROVIDER.

    Currently supports:
    - 'openai' or 'whisper': OpenAI Whisper API.
    """
    provider = (cfg.TRANSCRIBE_PROVIDER or "openai").lower()
    logger.info(
        "Transcribing audio file",
        extra={"path": file_path, "provider": provider, "language": language},
    )

    if provider in {"openai", "whisper"}:
        return _transcribe_with_openai(file_path, language=language)

    # If at some point you add Deepgram, AssemblyAI, etc., branch here.
    logger.error("Unsupported TRANSCRIBE_PROVIDER=%s", provider)
    raise AudioError(f"Unsupported TRANSCRIBE_PROVIDER={provider!r}")


def _transcribe_with_openai(file_path: str, language: Optional[str] = None) -> str:
    """
    Transcribe using OpenAI Whisper.

    Model name can be swapped later (e.g., 'whisper-1' or future audio models).
    """
    client = _openai_client()

    try:
        with open(file_path, "rb") as f:
            # Whisper-1 is stable and widely available
            kwargs = {"model": "whisper-1"}
            if language:
                kwargs["language"] = language

            result = client.audio.transcriptions.create(file=f, **kwargs)
    except Exception as exc:
        logger.exception("OpenAI transcription failed")
        raise AudioError(f"OpenAI transcription failed: {exc}") from exc

    # `result.text` is the standard field returned by Whisper API
    text = getattr(result, "text", None)
    if not text:
        logger.error("OpenAI transcription result missing 'text' field: %s", result)
        raise AudioError("OpenAI transcription result missing 'text' field")

    return text.strip()


def transcribe_whatsapp_audio(
    media_id: str,
    language: Optional[str] = None,
    cleanup: bool = True,
) -> str:
    """
    Convenience function:

    - Download WhatsApp media into a temp file.
    - Transcribe using configured provider.
    - Optionally delete temp file after transcription.

    Returns:
        Transcribed text.
    """
    dl = download_whatsapp_media_to_temp(media_id)
    try:
        text = transcribe_file(dl.path, language=language)
    finally:
        if cleanup:
            try:
                os.remove(dl.path)
            except OSError:
                logger.warning("Failed to remove temp audio file", exc_info=True)

    return text
