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


def _validate_item(item: object, idx: int) -> Dict[str, str]:
    if not isinstance(item, dict):
        raise ValueError(f"FAQ item #{idx} must be an object/dict, got {type(item).__name__}")

    missing = [k for k in ("key", "q", "a") if k not in item]
    if missing:
        raise ValueError(f"FAQ item #{idx} missing required fields: {missing}")

    out: Dict[str, str] = {}
    for k in ("key", "q", "a"):
        v = item.get(k)
        if v is None:
            raise ValueError(f"FAQ item #{idx} field '{k}' is null")
        s = str(v).strip()
        if not s:
            raise ValueError(f"FAQ item #{idx} field '{k}' is empty")
        out[k] = s

    return out


def load_faq_items() -> List[Dict[str, str]]:
    """
    Load FAQ items from JSON file.

    Returns:
        List of FAQ dictionaries with keys: key, q, a

    Raises:
        FileNotFoundError: If FAQ data file doesn't exist.
        ValueError: If JSON is invalid or schema is wrong.
    """
    faq_path = DATA_DIR / "faq_items.json"

    if not faq_path.exists():
        logger.error(
            "[FAQ LOADER] FAQ data file not found",
            extra={"path": str(faq_path)},
        )
        raise FileNotFoundError(f"FAQ data file not found: {faq_path}")

    # Read bytes first (useful for BOM / debugging)
    try:
        raw = faq_path.read_bytes()
    except Exception as e:
        logger.exception(
            "[FAQ LOADER] Failed to read FAQ file bytes",
            extra={"path": str(faq_path), "error": str(e)},
        )
        raise

    # Decode with utf-8-sig (handles UTF-8 BOM automatically)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        logger.exception(
            "[FAQ LOADER] FAQ file is not valid UTF-8",
            extra={"path": str(faq_path), "error": str(e)},
        )
        raise ValueError(f"FAQ file encoding error (expected UTF-8): {e}")

    # Parse JSON
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        preview = text[:200].replace("\n", "\\n")
        logger.exception(
            "[FAQ LOADER] Invalid JSON in FAQ file",
            extra={"path": str(faq_path), "error": str(e), "preview": preview},
        )
        raise ValueError(f"Invalid JSON in FAQ file: {e}")

    if not isinstance(data, list):
        logger.error(
            "[FAQ LOADER] FAQ data must be a JSON array (list)",
            extra={"path": str(faq_path), "type": type(data).__name__},
        )
        raise ValueError("FAQ data must be a list of items (JSON array).")

    # Validate each item
    items: List[Dict[str, str]] = []
    seen_keys: set[str] = set()
    for idx, item in enumerate(data):
        validated = _validate_item(item, idx)

        # Optional: prevent duplicate keys (helps avoid “random” behavior)
        k = validated["key"]
        if k in seen_keys:
            logger.warning(
                "[FAQ LOADER] Duplicate FAQ key detected",
                extra={"path": str(faq_path), "key": k, "index": idx},
            )
        else:
            seen_keys.add(k)

        items.append(validated)

    logger.info(
        "[FAQ LOADER] Loaded FAQ items from JSON",
        extra={"count": len(items), "path": str(faq_path)},
    )
    return items
