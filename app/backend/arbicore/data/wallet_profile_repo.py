"""WalletProfileRepository — D-4 Subset B.

Persists ``WalletProfile`` dicts produced by the D-4.2
``WalletEnrichmentOrchestrator`` so the verifier's
``SmartMoneyDetector`` can read non-empty wallet intelligence at
verification time. Replaces the empty stub in
``composition.py:_wallet_profile_loader``.

Storage:
  - Mongo: ``arbicore_wallet_metrics`` (collection already exists with a
    unique index on ``wallet_id``; see ``arbicore_collections.py``).
  - Document shape: a thin wrapper around ``WalletProfile.to_storage()``
    plus ``wallet_id`` (= address) for the unique index, plus
    ``updated_at`` for monotonic write ordering.

Invariants:
  - INV-1: returns plain dicts; never DiscoveryCandidate / CanonicalOpportunity.
  - INV-2: never references EmissionBus.
  - INV-3: WalletProfile is intelligence; carries no leg-level provenance.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List, Optional

from ..intel.launch.wallet_profile import WalletProfile, merge_stats


class WalletProfileRepository(ABC):
    """Abstract repository for WalletProfile persistence + lookup."""

    @abstractmethod
    async def get_many(self, addresses: List[str]) -> Dict[str, Dict[str, Any]]:
        """Bulk lookup. Returns ``{address: profile_dict}`` for addresses
        that exist; missing addresses are simply absent from the result.

        ``profile_dict`` matches ``WalletProfile.model_dump()`` so the
        SmartMoneyDetector's ``profile.get("scores", {}).get("wallet_quality")``
        and ``profile.get("label")`` lookups work unchanged.
        """

    @abstractmethod
    async def get(self, address: str) -> Optional[Dict[str, Any]]:
        """Single-address lookup convenience."""

    @abstractmethod
    async def upsert(self, profile: WalletProfile) -> None:
        """Insert-or-update one profile. Stats are idempotently merged."""

    @abstractmethod
    async def bulk_upsert(self, profiles: Iterable[WalletProfile]) -> int:
        """Persist many profiles. Returns the number of documents written."""

    @abstractmethod
    async def count(self) -> int:
        """Total profile count (operational health metric)."""


# ============================================================================
# In-memory implementation — used in tests, optional fallback
# ============================================================================

class InMemoryWalletProfileRepository(WalletProfileRepository):
    """Dict-backed implementation. Test-only; production uses Mongo."""

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}

    async def get_many(self, addresses: List[str]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for a in addresses or []:
            doc = self._store.get(a)
            if doc is not None:
                out[a] = doc
        return out

    async def get(self, address: str) -> Optional[Dict[str, Any]]:
        return self._store.get(address)

    async def upsert(self, profile: WalletProfile) -> None:
        existing = self._store.get(profile.address) or {}
        merged_stats = merge_stats(existing.get("stats", {}) or {},
                                    profile.stats or {})
        doc = profile.model_dump()
        doc["stats"] = merged_stats
        doc["updated_at"] = time.time()
        self._store[profile.address] = doc

    async def bulk_upsert(self, profiles: Iterable[WalletProfile]) -> int:
        n = 0
        for p in profiles:
            await self.upsert(p)
            n += 1
        return n

    async def count(self) -> int:
        return len(self._store)


def seed_curated_into(repo: WalletProfileRepository,
                      curated_records: List[Dict[str, Any]],
                      ) -> List[WalletProfile]:
    """Project curated label rows (`labels.load_curated()` output) into
    ``WalletProfile`` instances. Returns the list of synthesised profiles;
    caller decides when to await ``bulk_upsert``.

    Each record has shape ``{address, chain, label, label_source, notes}``.
    The resulting profile carries the curated label so the
    ``SmartMoneyDetector`` quality-via-label fallback (curated_label in
    {smart_money, whale, influencer}) fires at verification time.
    """
    out: List[WalletProfile] = []
    for r in curated_records or []:
        addr = r.get("address")
        if not addr:
            continue
        label = r.get("label")
        out.append(WalletProfile(
            address=addr,
            chain=r.get("chain", "solana"),
            label=label,
            label_source=r.get("label_source", "curated"),
            first_seen=0,
            last_seen=0,
            scores={},
            stats={},
            tags=[r.get("notes")] if r.get("notes") else [],
        ))
    return out
