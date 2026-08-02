"""Curated wallet labels for Launch Intelligence.

REUSE WITH REFINEMENT of `archive/backend/intel/labels.py` per
LEGACY_ARCHIVE_IMPORT_ASSESSMENT §2.2.2. Refinements:
  - Curated JSON relocated to `arbicore/intel/launch/labels.json` (was
    `data/curated_wallets.json`) — under the launch package so other
    opportunity families don't accidentally couple
  - `rug_wallet` entries are advisory only per Operator Decision 4 — the
    runtime survival analytics owns the actual rug detection. Documented
    in the LABEL_NOTES dict below.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("arbicore.intel.launch.labels")

# Canonical label vocabulary. Anything outside this set is rejected at load.
LABEL_VOCABULARY = frozenset({
    "smart_money",
    "influencer",
    "sniper",
    "whale",
    "retail_fomo",
    "rug_wallet",
})

# Per Operator Decision 4 — rug_wallet entries are advisory only.
LABEL_NOTES: Dict[str, str] = {
    "rug_wallet": (
        "advisory_only: rug wallets cycle addresses frequently; runtime "
        "survival analytics owns actual rug detection at verifier time"
    ),
}

CURATED_LABELS_PATH = Path(__file__).resolve().parent / "labels.json"


def load_curated(path: Optional[Path] = None) -> List[Dict]:
    """Load curated wallet labels from JSON. Returns [] on missing/malformed.

    Each returned record is normalized to:
        {address, chain, label, label_source, notes}
    Invalid records are dropped (logged at WARNING).
    """
    p = path or CURATED_LABELS_PATH
    try:
        if not p.exists():
            return []
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load curated wallets: %s", exc)
        return []
    wallets = data.get("wallets") if isinstance(data, dict) else data
    if not isinstance(wallets, list):
        return []
    valid: List[Dict] = []
    for w in wallets:
        if not isinstance(w, dict):
            continue
        addr = w.get("address")
        label = w.get("label")
        if not addr or label not in LABEL_VOCABULARY:
            continue
        valid.append({
            "address": addr,
            "chain": w.get("chain", "solana"),
            "label": label,
            "label_source": "curated",
            "notes": w.get("notes", ""),
        })
    return valid


def curated_index(path: Optional[Path] = None) -> Dict[str, Dict]:
    """O(1) address-keyed lookup table for ingestion-time enrichment."""
    return {w["address"]: w for w in load_curated(path)}


def is_valid_label(label: Optional[str]) -> bool:
    return label in LABEL_VOCABULARY
