# gateway_app/services/ai/prompt_loader.py
"""
Prompt loader utility for externalizing LLM prompts.

Allows loading prompts from .txt files for easier maintenance and versioning.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Base directory for prompts
PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(filename: str) -> str:
    """
    Load a prompt from the prompts/ directory.

    Args:
        filename: Name of the prompt file (e.g., "nlu_system_v1.txt")

    Returns:
        The prompt text as a string.

    Raises:
        FileNotFoundError: If the prompt file doesn't exist.
    """
    prompt_path = PROMPTS_DIR / filename

    if not prompt_path.exists():
        logger.error(
            f"[PROMPT LOADER] Prompt file not found: {prompt_path}",
            extra={"filename": filename, "path": str(prompt_path)}
        )
        raise FileNotFoundError(f"Prompt file not found: {filename}")

    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read()

        logger.debug(
            f"[PROMPT LOADER] Loaded prompt from {filename}",
            extra={"filename": filename, "length": len(content)}
        )

        return content

    except Exception as e:
        logger.exception(
            f"[PROMPT LOADER] Failed to load prompt: {filename}",
            extra={"filename": filename, "error": str(e)}
        )
        raise


def get_nlu_system_prompt(version: str = "v1") -> str:
    """Get the NLU system prompt."""
    return load_prompt(f"nlu_system_{version}.txt")


def get_faq_system_prompt(version: str = "v1") -> str:
    """Get the FAQ system prompt."""
    return load_prompt(f"faq_system_{version}.txt")


def get_confirm_draft_prompt(version: str = "v1") -> str:
    """Get the confirm draft system prompt."""
    return load_prompt(f"confirm_draft_{version}.txt")
