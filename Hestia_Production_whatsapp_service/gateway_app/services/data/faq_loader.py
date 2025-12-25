# gateway_app/services/data/faq_loader.py
"""
FAQ data loader - Loads FAQ items from JSON file.

This allows easy maintenance of FAQ data without modifying code.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)

# Base directory for data files
DATA_DIR = Path(__file__).parent


def load_faq_items() -> List[Dict[str, str]]:
    """
    Load FAQ items from JSON file.

    Returns:
        List of FAQ dictionaries with keys: key, q, a

    Raises:
        FileNotFoundError: If FAQ data file doesn't exist.
        ValueError: If JSON is invalid.
    """
    faq_path = DATA_DIR / "faq_items.json"

    if not faq_path.exists():
        logger.error(
            f"[FAQ LOADER] FAQ data file not found: {faq_path}",
            extra={"path": str(faq_path)}
        )
        raise FileNotFoundError(f"FAQ data file not found: {faq_path}")

    try:
        with open(faq_path, "r", encoding="utf-8") as f:
            faq_items = json.load(f)

        if not isinstance(faq_items, list):
            raise ValueError("FAQ data must be a list of items")

        logger.info(
            f"[FAQ LOADER] Loaded {len(faq_items)} FAQ items from JSON",
            extra={"count": len(faq_items), "path": str(faq_path)}
        )

        return faq_items

    except json.JSONDecodeError as e:
        logger.exception(
            f"[FAQ LOADER] Invalid JSON in FAQ file",
            extra={"path": str(faq_path), "error": str(e)}
        )
        raise ValueError(f"Invalid JSON in FAQ file: {e}")

    except Exception as e:
        logger.exception(
            f"[FAQ LOADER] Failed to load FAQ items",
            extra={"path": str(faq_path), "error": str(e)}
        )
        raise
