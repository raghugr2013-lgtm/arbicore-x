"""WalletProfile — canonical Solana wallet identity carrying scores, stats,
cluster, entity. Pydantic v2.

REUSE WITH REFINEMENT of `archive/backend/intel/wallets.py` per
LEGACY_ARCHIVE_IMPORT_ASSESSMENT §2.2.2. Refinements:
  - Pydantic v2 model (was dataclass)
  - Default `chain="solana"` preserved
  - `cluster_id` / `entity_id` map to Phase C Wave 4 `EntityResolver` output
    when the orchestrator wires it (D-4.5).
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class WalletProfile(BaseModel):
    """Canonical view of a wallet — single source of truth.

    `scores` carries 4-factor sub-scores produced by `WalletScorer`.
    `stats` is an idempotent merge target for ingestion-time counters.
    """

    address: str
    chain: str = "solana"
    label: Optional[str] = None
    label_source: Optional[str] = None  # "curated" | "algorithmic" | None
    first_seen: int = 0
    last_seen: int = 0
    scores: Dict[str, float] = Field(default_factory=dict)
    stats: Dict[str, float] = Field(default_factory=dict)
    cluster_id: Optional[str] = None
    entity_id: Optional[str] = None     # Phase C Wave 4 EntityResolver ref
    funding_source: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    def to_storage(self) -> Dict:
        """Storage projection — uses ``id`` as the unique key (mirrors legacy)."""
        d = self.model_dump()
        d["id"] = self.address
        return d


def is_smart_money(profile: Optional[Dict]) -> bool:
    """Curated-label OR algorithmic-quality gate. Mirrors legacy contract."""
    if not profile:
        return False
    if profile.get("label") in ("smart_money", "whale"):
        return True
    score = (profile.get("scores") or {}).get("wallet_quality") or 0
    return score >= 75


def merge_stats(existing: Dict, delta: Dict) -> Dict:
    """Idempotent stats merge. ``total_*`` keys accumulate; others replace."""
    out = dict(existing)
    for k, v in delta.items():
        if isinstance(v, (int, float)) and k.startswith("total_"):
            out[k] = (existing.get(k) or 0) + v
        else:
            out[k] = v
    out["updated_at"] = int(time.time())
    return out
