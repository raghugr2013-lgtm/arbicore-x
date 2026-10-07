"""ArbiCore X — Phase D D-1: Discovery candidate queue (Mongo-backed).

Per PHASE_D_DISCOVERY_LAYER_SPEC.md §5.

Collection: arbicore_discovery_candidates
- Idempotency key: candidate_id (unique)
- TTL 24h on expires_at
- Cooperative claim lock via (claimed_at, claimed_by, claimed_until)
- B2: additive top-level ``chain`` + chain-fair claim_batch scheduling

No Redis. No Kafka. Pure Mongo + atomic findOneAndUpdate.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from ..models.discovery import (
    DISCOVERY_SUPPORTED_CHAINS,
    DiscoveryCandidate,
    VerifiedOutcome,
)

COLLECTION_NAME = "arbicore_discovery_candidates"

# Fair-scheduling buckets: the six supported chains + a legacy bucket for rows
# without a resolvable supported chain. Legacy remains claimable; unsupported
# chain labels are NOT promoted into the supported set.
_FAIR_CHAIN_BUCKETS: Tuple[Optional[str], ...] = (
    tuple(DISCOVERY_SUPPORTED_CHAINS) + (None,)  # type: ignore[operator]
)
_LEGACY_BUCKET: Optional[str] = None


def _normalize_chain(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    c = value.strip().lower()
    return c or None


def resolve_candidate_chain(candidate: DiscoveryCandidate) -> Optional[str]:
    """Return a supported-chain id for fair scheduling, or None (legacy).

    Prefers top-level ``chain``, then ``hint_metric.chain``. Unsupported /
    missing values map to the legacy bucket (still claimable).
    """
    ch = _normalize_chain(getattr(candidate, "chain", None))
    if ch is None:
        hm = getattr(candidate, "hint_metric", None) or {}
        if isinstance(hm, dict):
            ch = _normalize_chain(hm.get("chain"))
    if ch in DISCOVERY_SUPPORTED_CHAINS:
        return ch
    return None


class DiscoveryQueue:
    """Mongo-backed cooperative claim queue."""

    def __init__(self, db) -> None:
        self._db = db
        self._col = db[COLLECTION_NAME]
        # Round-robin cursor across fair buckets (process-local; best-effort).
        self._fair_rr_idx = 0

    async def ensure_indexes(self) -> None:
        await self._col.create_index("candidate_id", unique=True)
        await self._col.create_index(
            [("opportunity_type", 1), ("claimed_until", 1), ("expires_at", 1)]
        )
        await self._col.create_index([("hint_source", 1), ("hint_observed_at", -1)])
        # TTL: Mongo TTL reaper deletes once expires_at is in the past.
        await self._col.create_index("expires_at", expireAfterSeconds=0)
        # B2: additive chain index for fair claim scheduling (does not alter
        # eligibility semantics — only speeds per-chain claim filters).
        await self._col.create_index(
            [("chain", 1), ("verified_outcome", 1),
             ("claimed_until", 1), ("expires_at", 1)]
        )

    async def upsert_many(self, candidates: List[DiscoveryCandidate]) -> int:
        """Idempotent upsert keyed on candidate_id. Returns count of fresh
        rows (new + reset). Existing rows mid-flight are NOT overwritten."""
        if not candidates:
            return 0
        inserted = 0
        for c in candidates:
            doc = c.model_dump()
            # Ensure additive chain is persisted for new rows (from top-level
            # or hint_metric). Legacy-compatible: omit when unresolved.
            resolved = resolve_candidate_chain(c)
            if resolved is not None:
                doc["chain"] = resolved
            else:
                # Missing OR unsupported label → legacy bucket. Do not persist
                # unsupported chain strings (they match no fair bucket and would
                # become permanently unclaimable).
                doc.pop("chain", None)
            # Only set on insert — preserves claim lock + outcome on update
            res = await self._col.update_one(
                {"candidate_id": c.candidate_id},
                {"$setOnInsert": doc},
                upsert=True,
            )
            if res.upserted_id is not None:
                inserted += 1
        return inserted

    def _eligible_base(self, now: float) -> Dict[str, Any]:
        """Unchanged eligibility: unprocessed, unexpired, claim lock free."""
        return {
            "verified_outcome": None,
            "expires_at": {"$gt": now},
            "$or": [
                {"claimed_until": None},
                {"claimed_until": {"$lt": now}},
            ],
        }

    def _chain_bucket_clause(self, bucket: Optional[str]) -> Dict[str, Any]:
        """Match docs belonging to a fair-scheduling bucket.

        Supported chain: top-level ``chain`` OR legacy rows whose
        ``hint_metric.chain`` equals that chain.
        Legacy bucket: no supported chain on top-level or hint_metric.
        """
        missing_top = {
            "$or": [
                {"chain": {"$exists": False}},
                {"chain": None},
                {"chain": ""},
            ]
        }
        if bucket is not None:
            return {
                "$or": [
                    {"chain": bucket},
                    {"$and": [
                        missing_top,
                        {"hint_metric.chain": bucket},
                    ]},
                ]
            }
        # Legacy: missing/empty top-level chain AND hint_metric.chain is not a
        # supported chain (missing / empty / unsupported label).
        return {
            "$and": [
                missing_top,
                {"$or": [
                    {"hint_metric.chain": {"$exists": False}},
                    {"hint_metric.chain": None},
                    {"hint_metric.chain": ""},
                    {"hint_metric.chain": {"$nin": list(DISCOVERY_SUPPORTED_CHAINS)}},
                ]},
            ]
        }

    def _claim_filter(self, now: float, bucket: Optional[str]) -> Dict[str, Any]:
        base = self._eligible_base(now)
        clause = self._chain_bucket_clause(bucket)
        # Merge carefully: base already has a top-level $or for claim lock.
        return {"$and": [base, clause]}

    async def _claim_one(self, worker_id: str, now: float, claim_until: float,
                         bucket: Optional[str]) -> Optional[Dict[str, Any]]:
        return await self._col.find_one_and_update(
            self._claim_filter(now, bucket),
            {"$set": {
                "claimed_at": now,
                "claimed_by": worker_id,
                "claimed_until": claim_until,
            }},
            return_document=True,
        )

    async def claim_batch(self, worker_id: str,
                          batch_size: int = 32,
                          claim_ttl_s: float = 60.0,
                          ) -> List[DiscoveryCandidate]:
        """Atomically claim up to `batch_size` candidates with chain fairness.

        A candidate is eligible if (UNCHANGED):
          - verified_outcome is None (unprocessed)
          - claimed_until is None or < now (no live claim)
          - expires_at > now (not stale)

        B2: among eligible candidates, claim round-robin across the six
        supported chains plus a legacy bucket so no single chain permanently
        monopolizes a batch. Fairness never bypasses eligibility filters and
        never forces opportunities through TVL/quote/safety gates.
        """
        if batch_size <= 0:
            return []
        now = time.time()
        claim_until = now + claim_ttl_s
        out: List[DiscoveryCandidate] = []
        n_buckets = len(_FAIR_CHAIN_BUCKETS)
        # Start from rotating index so consecutive batches don't always prefer
        # ethereum; wrap with empty-streak termination.
        start = self._fair_rr_idx % n_buckets
        empty_streak = 0
        i = 0
        while len(out) < batch_size and empty_streak < n_buckets:
            bucket = _FAIR_CHAIN_BUCKETS[(start + i) % n_buckets]
            i += 1
            doc = await self._claim_one(worker_id, now, claim_until, bucket)
            if doc is None:
                empty_streak += 1
                continue
            empty_streak = 0
            doc.pop("_id", None)
            try:
                out.append(DiscoveryCandidate(**doc))
            except Exception:  # noqa: BLE001
                # Malformed row — mark as expired / error (same as prior path)
                await self._col.update_one(
                    {"candidate_id": doc.get("candidate_id")},
                    {"$set": {"verified_outcome": "error:malformed_candidate",
                              "verified_at": time.time()}},
                )
        # Advance RR cursor past the last attempted bucket for the next batch.
        self._fair_rr_idx = (start + i) % n_buckets
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
