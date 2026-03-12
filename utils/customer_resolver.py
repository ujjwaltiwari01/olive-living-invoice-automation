"""
GSTIN-based Customer Resolver (Layer 5)

Maintains a local JSON mapping: GSTIN → {customer_id, name}
This allows automatic resolution of Zoho customer_id without calling the Zoho API,
using GSTIN as the unique identifier (more reliable than customer name matching).

Usage:
    from utils.customer_resolver import resolve_by_gstin, register_customer

    result = resolve_by_gstin("08BJYPR4499A1ZF")
    if result["resolved"]:
        customer_id = result["customer_id"]
    else:
        # Needs manual entry in customer_mapping.json
        pass
"""

import json
import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Mapping file — sits in the project root
MAPPING_PATH = Path(__file__).parent.parent / "customer_mapping.json"

# Indian GSTIN format: ##AAAAA####A#Z#
GSTIN_RE = re.compile(r'^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]$')


def _load_mapping() -> dict:
    """Load the customer mapping file, creating it if it doesn't exist."""
    if MAPPING_PATH.exists():
        try:
            return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"CUSTOMER_RESOLVER: Failed to load mapping: {e}")
            return {}
    # Create empty mapping with example entry
    empty = {
        "_example": {
            "customer_id": "REPLACE_WITH_ZOHO_CUSTOMER_ID",
            "name": "Example Company Pvt Ltd",
            "added_on": "2026-03-01"
        }
    }
    _save_mapping(empty)
    logger.info(f"CUSTOMER_RESOLVER: Created new mapping file at {MAPPING_PATH}")
    return {}


def _save_mapping(mapping: dict) -> None:
    """Persist the mapping file."""
    try:
        MAPPING_PATH.write_text(
            json.dumps(mapping, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except OSError as e:
        logger.error(f"CUSTOMER_RESOLVER: Failed to save mapping: {e}")


def validate_gstin(gstin: str) -> bool:
    """Returns True if GSTIN matches the valid 15-char Indian format."""
    if not gstin or not isinstance(gstin, str):
        return False
    clean = gstin.strip().upper().replace(" ", "")
    return bool(GSTIN_RE.match(clean))


def resolve_by_gstin(gstin: Optional[str], customer_name: Optional[str] = None) -> dict:
    """
    Attempts to resolve a Zoho customer_id using the GSTIN.

    Returns a dict with:
        resolved     (bool)   — True if customer_id was found
        customer_id  (str)    — Zoho internal ID (only if resolved=True)
        customer_name(str)    — Confirmed name from mapping (or fallback)
        reason       (str)    — Why resolution failed (only if resolved=False)
    """
    if not gstin:
        return {
            "resolved": False,
            "reason": "no_gstin_provided",
            "customer_name": customer_name or "Unknown Customer",
        }

    clean_gstin = gstin.strip().upper().replace(" ", "")

    if not validate_gstin(clean_gstin):
        logger.warning(f"CUSTOMER_RESOLVER: Invalid GSTIN format '{clean_gstin}' — skipping lookup")
        return {
            "resolved": False,
            "reason": "invalid_gstin_format",
            "customer_name": customer_name or "Unknown Customer",
            "raw_gstin": clean_gstin,
        }

    mapping = _load_mapping()
    entry = mapping.get(clean_gstin)

    if entry and entry.get("customer_id") and not entry["customer_id"].startswith("REPLACE"):
        logger.info(
            f"CUSTOMER_RESOLVER: Resolved GSTIN {clean_gstin} → "
            f"customer_id={entry['customer_id']} ({entry.get('name', '')})"
        )
        return {
            "resolved": True,
            "customer_id": entry["customer_id"],
            "customer_name": entry.get("name", customer_name or ""),
        }

    logger.warning(
        f"CUSTOMER_RESOLVER: GSTIN {clean_gstin} not in mapping. "
        f"Add it to {MAPPING_PATH.name} with the Zoho customer_id."
    )
    return {
        "resolved": False,
        "reason": "gstin_not_in_mapping",
        "customer_name": customer_name or "Unknown Customer",
        "gstin": clean_gstin,
    }


def register_customer(gstin: str, customer_id: str, name: str) -> bool:
    """
    Adds or updates a customer in the mapping file.

    Args:
        gstin:       e.g. "08BJYPR4499A1ZF"
        customer_id: Zoho Books internal ID e.g. "982000000567001"
        name:        Customer display name

    Returns True on success, False on failure.
    """
    clean_gstin = gstin.strip().upper().replace(" ", "")
    if not validate_gstin(clean_gstin):
        logger.error(f"CUSTOMER_RESOLVER: Cannot register invalid GSTIN '{clean_gstin}'")
        return False

    from datetime import date
    mapping = _load_mapping()
    mapping[clean_gstin] = {
        "customer_id": customer_id,
        "name": name,
        "added_on": str(date.today()),
    }
    _save_mapping(mapping)
    logger.info(f"CUSTOMER_RESOLVER: Registered {clean_gstin} → {customer_id} ({name})")
    return True


def get_all_customers() -> dict:
    """Returns the full mapping (minus example entries) for display in the UI."""
    return {
        k: v for k, v in _load_mapping().items()
        if not k.startswith("_")
    }
