"""Emergent B2 — discovery queue chain-fair claim_batch (offline).

In-memory Mongo stand-in. No deploy, no filter bypass, no unsupported chains.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import pytest

from arbicore.data.discovery_queue import (
    DiscoveryQueue,
    resolve_candidate_chain,
)
from arbicore.models.discovery import (
    DISCOVERY_SUPPORTED_CHAINS,
    DiscoveryCandidate,
)
from arbicore.models.enums import OpportunityType


# ---------------------------------------------------------------------------
# Minimal Mongo stand-in (supports claim_batch filters)
# ---------------------------------------------------------------------------

def _match(doc: Dict[str, Any], filt: Any) -> bool:
    if not isinstance(filt, dict):
        return False
    if len(filt) == 1 and "$and" in filt:
        return all(_match(doc, c) for c in filt["$and"])
    if len(filt) == 1 and "$or" in filt:
        return any(_match(doc, c) for c in filt["$or"])
    for k, v in filt.items():
        if k == "$and":
            if not all(_match(doc, c) for c in v):
                return False
            continue
        if k == "$or":
            if not any(_match(doc, c) for c in v):
                return False
            continue
        if "." in k:
            cur: Any = doc
            for part in k.split("."):
                if not isinstance(cur, dict) or part not in cur:
                    cur = None
                    break
                cur = cur[part]
            actual = cur
        else:
            actual = doc.get(k) if k in doc else _MISSING
        if isinstance(v, dict) and any(str(op).startswith("$") for op in v):
            for op, ov in v.items():
                if op == "$gt":
                    if actual is _MISSING or actual is None or not (actual > ov):
                        return False
                elif op == "$lt":
                    if actual is _MISSING or actual is None or not (actual < ov):
                        return False
                elif op == "$exists":
                    exists = k in doc if "." not in k else actual is not _MISSING and _path_exists(doc, k)
                    if bool(ov) != exists:
                        # For dotted paths, treat missing nested as not exists
                        if "." in k:
                            exists = _path_exists(doc, k)
                        else:
                            exists = k in doc
                        if bool(ov) != exists:
                            return False
                elif op == "$in":
                    if actual not in ov:
                        return False
                elif op == "$nin":
                    if actual in ov:
                        return False
                else:
                    return False
        else:
            if actual != v:
                return False
    return True


_MISSING = object()


def _path_exists(doc: Dict[str, Any], dotted: str) -> bool:
    cur: Any = doc
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True


class _UpdateResult:
    def __init__(self, upserted_id=None, modified_count=0):
        self.upserted_id = upserted_id
        self.modified_count = modified_count


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, n):
        return list(self._docs)[:n]

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _FakeCollection:
    def __init__(self):
        self.docs: Dict[str, Dict[str, Any]] = {}
        self.indexes: List[Any] = []

    async def create_index(self, spec, **kwargs):
        self.indexes.append((spec, kwargs))
        return "ok"

    async def update_one(self, filt, update, upsert=False):
        cid = filt.get("candidate_id")
        if cid in self.docs:
            doc = self.docs[cid]
            if "$set" in update:
                doc.update(update["$set"])
            return _UpdateResult(modified_count=1)
        if upsert and "$setOnInsert" in update:
            doc = dict(update["$setOnInsert"])
            self.docs[cid] = doc
            return _UpdateResult(upserted_id=cid)
        return _UpdateResult()

    async def find_one_and_update(self, filt, update, return_document=True):
        for cid, doc in list(self.docs.items()):
            if _match(doc, filt):
                if "$set" in update:
                    doc.update(update["$set"])
                out = dict(doc)
                out["_id"] = cid
                return out
        return None

    async def find_one(self, filt):
        for doc in self.docs.values():
            if _match(doc, filt):
                return dict(doc)
        return None

    def find(self, filt=None):
        docs = [dict(d) for d in self.docs.values() if _match(d, filt or {})]
        return _FakeCursor(docs)

    async def count_documents(self, filt):
        return sum(1 for d in self.docs.values() if _match(d, filt))

    async def update_many(self, filt, update):
        n = 0
        for doc in self.docs.values():
            if _match(doc, filt):
                doc.update(update.get("$set", {}))
                n += 1
        return _UpdateResult(modified_count=n)


class _FakeDB:
    def __init__(self):
        self._cols: Dict[str, _FakeCollection] = {}

    def __getitem__(self, name):
        return self._cols.setdefault(name, _FakeCollection())


def _cand(cid: str, *, chain: Optional[str] = None,
          hint_chain: Optional[str] = None,
          expires_in: float = 600.0,
          verified_outcome=None,
          claimed_until=None,
          claimed_by=None) -> DiscoveryCandidate:
    now = time.time()
    hm: Dict[str, Any] = {}
    if hint_chain is not None:
        hm["chain"] = hint_chain
    kwargs: Dict[str, Any] = dict(
        candidate_id=cid,
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        hint_source="test_source",
        hint_observed_at=now,
        subject_id=f"subj:{cid}",
        asset="WETH",
        candidate_venues=["0xpool"],
        hint_metric=hm,
        reason="test",
        expires_at=now + expires_in,
        verified_outcome=verified_outcome,
        claimed_until=claimed_until,
        claimed_by=claimed_by,
    )
    if chain is not None:
        kwargs["chain"] = chain
    return DiscoveryCandidate(**kwargs)


@pytest.fixture
def queue():
    return DiscoveryQueue(_FakeDB())


# 1. Six-chain fairness
@pytest.mark.asyncio
async def test_six_chain_fairness(queue):
    for ch in DISCOVERY_SUPPORTED_CHAINS:
        await queue.upsert_many([_cand(f"c-{ch}", chain=ch)])
    claimed = await queue.claim_batch("w1", batch_size=6)
    chains = {c.chain for c in claimed}
    assert chains == set(DISCOVERY_SUPPORTED_CHAINS)
    assert len(claimed) == 6


# 2. Skewed candidate-count — minority chains still get access
@pytest.mark.asyncio
async def test_skewed_candidate_counts(queue):
    # 20 base + 1 ethereum + 1 arbitrum
    batch = [_cand(f"base-{i}", chain="base") for i in range(20)]
    batch.append(_cand("eth-1", chain="ethereum"))
    batch.append(_cand("arb-1", chain="arbitrum"))
    await queue.upsert_many(batch)
    claimed = await queue.claim_batch("w1", batch_size=6)
    by_chain: Dict[str, int] = {}
    for c in claimed:
        by_chain[c.chain or ""] = by_chain.get(c.chain or "", 0) + 1
    assert by_chain.get("ethereum") == 1
    assert by_chain.get("arbitrum") == 1
    # Base may take remaining slots but cannot be the sole chain in the batch
    assert len(by_chain) >= 3


# 3. No single chain permanently monopolizes a batch
@pytest.mark.asyncio
async def test_no_monopoly_across_batches(queue):
    for ch in ("base", "ethereum", "optimism"):
        for i in range(10):
            await queue.upsert_many([_cand(f"{ch}-{i}", chain=ch)])
    seen_sets = []
    for n in range(3):
        claimed = await queue.claim_batch(f"w{n}", batch_size=3)
        chains = {c.chain for c in claimed}
        seen_sets.append(chains)
        assert len(chains) == 3  # one from each of the three populated chains
    # Across batches, ethereum/optimism remain represented (not starved by base)
    union = set().union(*seen_sets)
    assert {"base", "ethereum", "optimism"} <= union


# 4. Expired never claimed
@pytest.mark.asyncio
async def test_expired_never_claimed(queue):
    await queue.upsert_many([
        _cand("live", chain="base", expires_in=600),
        _cand("dead", chain="ethereum", expires_in=-10),
    ])
    claimed = await queue.claim_batch("w1", batch_size=10)
    ids = {c.candidate_id for c in claimed}
    assert "live" in ids
    assert "dead" not in ids


# 5. Already claimed / processed never incorrectly claimed
@pytest.mark.asyncio
async def test_claimed_and_processed_not_reclaimed(queue):
    now = time.time()
    await queue.upsert_many([
        _cand("free", chain="base"),
        _cand("locked", chain="ethereum", claimed_until=now + 120, claimed_by="other"),
        _cand("done", chain="optimism", verified_outcome="denied:venue_unreadable"),
    ])
    claimed = await queue.claim_batch("w1", batch_size=10)
    ids = {c.candidate_id for c in claimed}
    assert ids == {"free"}


# 6. Legacy without chain safely claimable
@pytest.mark.asyncio
async def test_legacy_without_chain_claimable(queue):
    # Insert a raw legacy doc (no top-level chain) via collection
    now = time.time()
    legacy = {
        "candidate_id": "legacy-1",
        "opportunity_type": OpportunityType.FLASH_LOAN_ARBITRAGE.value,
        "hint_source": "old",
        "hint_observed_at": now,
        "subject_id": "s",
        "asset": "WETH",
        "candidate_venues": [],
        "hint_metric": {},  # no chain
        "reason": "legacy",
        "expires_at": now + 600,
        "verified_outcome": None,
        "claimed_until": None,
    }
    queue._col.docs["legacy-1"] = legacy
    # Also a hint_metric-only ethereum legacy row
    hint_only = dict(legacy)
    hint_only["candidate_id"] = "hint-eth"
    hint_only["hint_metric"] = {"chain": "ethereum"}
    queue._col.docs["hint-eth"] = hint_only

    claimed = await queue.claim_batch("w1", batch_size=10)
    ids = {c.candidate_id for c in claimed}
    assert "legacy-1" in ids
    assert "hint-eth" in ids


# 7. Expiry semantics unchanged
@pytest.mark.asyncio
async def test_expiry_semantics_unchanged(queue):
    now = time.time()
    c = _cand("exp", chain="base", expires_in=0.01)
    await queue.upsert_many([c])
    # Force expires_at into the past
    queue._col.docs["exp"]["expires_at"] = now - 1
    claimed = await queue.claim_batch("w1", batch_size=5)
    assert claimed == []
    # reap stamps expired_unclaimed
    n = await queue.reap_expired_unclaimed()
    assert n == 1
    assert queue._col.docs["exp"]["verified_outcome"] == "expired_unclaimed"


# 8. Unsupported chains not introduced into fairness buckets
@pytest.mark.asyncio
async def test_unsupported_chains_not_introduced(queue):
    assert "solana" not in DISCOVERY_SUPPORTED_CHAINS
    c = _cand("sol", chain="solana")
    # Constructor lowercases; resolve maps unsupported → legacy
    assert resolve_candidate_chain(c) is None
    await queue.upsert_many([c, _cand("base-1", chain="base")])
    # upsert should not persist unsupported as a first-class supported chain
    # when resolve strips it — model may still carry the string, but fair
    # scheduling treats it as legacy.
    claimed = await queue.claim_batch("w1", batch_size=2)
    assert {x.candidate_id for x in claimed} == {"sol", "base-1"}
    # Index creation includes chain (additive)
    await queue.ensure_indexes()
    chain_indexes = [ix for ix in queue._col.indexes
                     if isinstance(ix[0], list) and any(
                         isinstance(p, tuple) and p[0] == "chain" for p in ix[0])]
    assert chain_indexes, "chain index must be registered"


# Upsert path populates chain from hint_metric
@pytest.mark.asyncio
async def test_upsert_derives_chain_from_hint_metric(queue):
    c = _cand("hm", hint_chain="polygon")  # no top-level chain arg
    assert c.chain == "polygon"  # model __init__ derives it
    await queue.upsert_many([c])
    assert queue._col.docs["hm"]["chain"] == "polygon"
