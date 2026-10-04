"""ArbiCore X — Phase D D-1: Discovery candidate queue (Mongo-backed).

Per PHASE_D_DISCOVERY_LAYER_SPEC.md §5.

Collection: arbicore_discovery_candidates
- Idempotency key: candidate_id (unique)
- TTL 24h on expires_at
- Cooperative claim lock via (claimed_at, claimed_by, claimed_until)

No Redis. No Kafka. Pure Mongo + atomic findOneAndUpdate.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from ..models.discovery import DiscoveryCandidate, VerifiedOutcome

COLLECTION_NAME = "arbicore_discovery_candidates"


class DiscoveryQueue:
    """Mongo-backed cooperative claim queue."""

    def __init__(self, db) -> None:
        self._db = db
        self._col = db[COLLECTION_NAME]

    async def ensure_indexes(self) -> None:
        await self._col.create_index("candidate_id", unique=True)
        await self._col.create_index(
            [("opportunity_type", 1), ("claimed_until", 1), ("expires_at", 1)]
        )
        # B2: chain-fair claim index (chain-partitioned eligibility scan).
        await self._col.create_index(
            [("chain", 1), ("verified_outcome", 1), ("claimed_until", 1),
             ("expires_at", 1)]
        )
        await self._col.create_index([("hint_source", 1), ("hint_observed_at", -1)])
        # TTL: Mongo TTL reaper deletes once expires_at is in the past.
        await self._col.create_index("expires_at", expireAfterSeconds=0)

    async def upsert_many(self, candidates: List[DiscoveryCandidate]) -> int:
        """Idempotent upsert keyed on candidate_id. Returns count of fresh
        rows (new + reset). Existing rows mid-flight are NOT overwritten."""
        if not candidates:
            return 0
        inserted = 0
        for c in candidates:
            doc = c.model_dump()
            # B2: stamp a top-level chain (fair-scheduling key) when derivable —
            # from the hint metric, else the flash-loan subject_id convention
            # (flash_loan:{provider}:{chain}:...). Never invents a chain.
            if not doc.get("chain"):
                ch = (c.hint_metric or {}).get("chain")
                if not ch:
                    parts = (c.subject_id or "").split(":")
                    if len(parts) >= 3 and parts[0] == "flash_loan":
                        ch = parts[2]
                if ch:
                    doc["chain"] = str(ch).strip().lower()
            # Only set on insert — preserves claim lock + outcome on update
            res = await self._col.update_one(
                {"candidate_id": c.candidate_id},
                {"$setOnInsert": doc},
                upsert=True,
            )
            if res.upserted_id is not None:
                inserted += 1
        return inserted

    async def claim_batch(self, worker_id: str,
                          batch_size: int = 32,
                          claim_ttl_s: float = 60.0,
                          ) -> List[DiscoveryCandidate]:
        """Atomically claim up to `batch_size` candidates with CHAIN FAIRNESS.

        Eligibility predicate (UNCHANGED — all downstream gates untouched):
          - verified_outcome is None (unprocessed)
          - claimed_until is None or < now (no live claim)
          - expires_at > now (not stale)

        B2: instead of draining whichever candidates an index happens to order
        first (which lets one chain monopolise the batch and starve others), the
        batch is filled round-robin across the chains that currently have eligible
        candidates. Each individual claim still uses the SAME atomic
        find_one_and_update with the SAME eligibility predicate, so expiry
        semantics, claim locking and verified_outcome behaviour are preserved and
        no opportunity is ever forced. Legacy rows without a ``chain`` match the
        ``None`` bucket and remain claimable.
        """
        now = time.time()
        claim_until = now + claim_ttl_s
        base_filter: Dict[str, Any] = {
            "verified_outcome": None,
            "expires_at": {"$gt": now},
            "$or": [
                {"claimed_until": None},
                {"claimed_until": {"$lt": now}},
            ],
        }
        # Chains with eligible candidates right now (None = legacy/untagged).
        chains = await self._col.distinct("chain", base_filter)
        order: List[Any] = sorted([c for c in chains if c])
        if any(c is None for c in chains):
            order.append(None)  # legacy/untagged bucket, claimed fairly too
        out: List[DiscoveryCandidate] = []
        if not order:
            return out
        exhausted: set = set()
        idx = 0
        while len(out) < batch_size and len(exhausted) < len(order):
            c = order[idx % len(order)]
            idx += 1
            if c in exhausted:
                continue
            doc = await self._col.find_one_and_update(
                {**base_filter, "chain": c},
                {"$set": {
                    "claimed_at": now,
                    "claimed_by": worker_id,
                    "claimed_until": claim_until,
                }},
                return_document=True,
            )
            if doc is None:
                exhausted.add(c)
                continue
            doc.pop("_id", None)
            try:
                out.append(DiscoveryCandidate(**doc))
            except Exception:  # noqa: BLE001
                # Malformed row — mark as expired
                await self._col.update_one(
                    {"candidate_id": doc.get("candidate_id")},
                    {"$set": {"verified_outcome": "error:malformed_candidate",
                              "verified_at": time.time()}},
                )
        return out

    async def mark_processed(self, candidate_id: str,
                             outcome_tag: str,
                             *, opportunity_id: Optional[str] = None,
                             observed_at: Optional[float] = None,
                             ) -> bool:
        now = time.time()
        latency_ms = None
        if observed_at is not None:
            latency_ms = max(0, int(round((now - observed_at) * 1000)))
        res = await self._col.update_one(
            {"candidate_id": candidate_id},
            {"$set": {
                "verified_outcome": outcome_tag,
                "verified_at": now,
                "verification_latency_ms": latency_ms,
                "emitted_opportunity_id": opportunity_id,
                # Release the claim
                "claimed_at": None, "claimed_by": None, "claimed_until": None,
            }},
        )
        return res.modified_count > 0

    async def queue_status(self) -> Dict[str, Any]:
        now = time.time()
        total = await self._col.count_documents({})
        unprocessed = await self._col.count_documents({"verified_outcome": None})
        claimed = await self._col.count_documents({
            "verified_outcome": None, "claimed_until": {"$gt": now}
        })
        unclaimed = await self._col.count_documents({
            "verified_outcome": None,
            "expires_at": {"$gt": now},
            "$or": [{"claimed_until": None}, {"claimed_until": {"$lt": now}}],
        })
        oldest = await self._col.find(
            {"verified_outcome": None, "expires_at": {"$gt": now}},
        ).sort("hint_observed_at", 1).limit(1).to_list(1)
        oldest_age_s = None
        if oldest:
            oldest_age_s = now - float(oldest[0].get("hint_observed_at", now))
        return {
            "total": total,
            "unprocessed": unprocessed,
            "claimed_in_flight": claimed,
            "unclaimed_eligible": unclaimed,
            "oldest_unclaimed_age_s": oldest_age_s,
        }

    async def list_candidates(self, limit: int = 50,
                              source_id: Optional[str] = None,
                              ) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {}
        if source_id:
            q["hint_source"] = source_id
        cur = self._col.find(q).sort("hint_observed_at", -1).limit(limit)
        out = []
        async for doc in cur:
            doc.pop("_id", None)
            out.append(doc)
        return out

    async def get_candidate(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        doc = await self._col.find_one({"candidate_id": candidate_id})
        if doc is None:
            return None
        doc.pop("_id", None)
        return doc

    async def reap_expired_unclaimed(self) -> int:
        """Synthetic 'expired_unclaimed' tagger for telemetry. The TTL index
        will delete these eventually; this just stamps the outcome first."""
        now = time.time()
        res = await self._col.update_many(
            {"verified_outcome": None, "expires_at": {"$lt": now}},
            {"$set": {
                "verified_outcome": VerifiedOutcome.EXPIRED_UNCLAIMED,
                "verified_at": now,
            }},
        )
        return res.modified_count

    async def count(self) -> int:
        return await self._col.count_documents({})
