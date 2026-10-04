"""B2 — DiscoveryQueue chain-fair claim scheduling.

Confirms claim_batch distributes verifier access fairly across the six supported
chains (no monopoly / no starvation) while preserving the EXACT eligibility
predicate, expiry semantics, claim locking and verified_outcome behaviour.
Uses an in-memory async Mongo fake — no real database required.
"""
import time

import pytest

from arbicore.data.discovery_queue import DiscoveryQueue
from arbicore.models.enums import OpportunityType

SIX = ("ethereum", "arbitrum", "base", "optimism", "polygon", "bnb")


def _match(doc, flt):
    for k, cond in flt.items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in cond):
                return False
            continue
        val = doc.get(k)
        if isinstance(cond, dict):
            if "$gt" in cond and not (val is not None and val > cond["$gt"]):
                return False
            if "$lt" in cond and not (val is not None and val < cond["$lt"]):
                return False
        else:
            # equality; None matches missing-or-None (Mongo semantics)
            if cond is None:
                if val is not None:
                    return False
            elif val != cond:
                return False
    return True


class _FakeCol:
    def __init__(self):
        self._docs = []  # insertion-ordered

    async def create_index(self, *a, **k):
        return None

    async def distinct(self, field, flt):
        seen, out = set(), []
        for d in self._docs:
            if _match(d, flt):
                v = d.get(field)
                if v not in seen:
                    seen.add(v); out.append(v)
        return out

    async def find_one_and_update(self, flt, update, return_document=True):
        for d in self._docs:
            if _match(d, flt):
                d.update(update.get("$set", {}))
                return dict(d)
        return None

    async def update_one(self, flt, update, upsert=False):
        for d in self._docs:
            if _match(d, flt):
                d.update(update.get("$set", {}))
                return type("R", (), {"upserted_id": None, "modified_count": 1})()
        if upsert:
            doc = dict(update.get("$setOnInsert", {}))
            doc.update(flt)
            self._docs.append(doc)
            return type("R", (), {"upserted_id": "x", "modified_count": 0})()
        return type("R", (), {"upserted_id": None, "modified_count": 0})()


def _seed(col, chain, n, *, expired=False, claimed=False, processed=False):
    now = time.time()
    for i in range(n):
        col._docs.append({
            "candidate_id": f"{chain}-{i}-{len(col._docs)}",
            "opportunity_type": OpportunityType.FLASH_LOAN_ARBITRAGE.value,
            "hint_source": "flash_loan_route_search",
            "subject_id": f"flash_loan:aave_v3:{chain}:USDC:r{i}",
            "chain": chain,
            "hint_observed_at": now,
            "expires_at": now - 10 if expired else now + 600,
            "verified_outcome": "CONFIRMED:x" if processed else None,
            "claimed_at": None, "claimed_by": None,
            "claimed_until": (now + 300) if claimed else None,
        })


def _q():
    q = DiscoveryQueue.__new__(DiscoveryQueue)
    q._col = _FakeCol()
    return q


def _chains(batch):
    return [c.chain for c in batch]


# 1 + 2 + 3: fairness across six chains, incl. skew and no monopoly
async def test_six_chain_fairness_balanced():
    q = _q()
    for c in SIX:
        _seed(q._col, c, 10)
    batch = await q.claim_batch("w1", batch_size=12)
    counts = {c: _chains(batch).count(c) for c in SIX}
    assert len(batch) == 12
    assert all(counts[c] >= 1 for c in SIX)          # every chain served
    assert max(counts.values()) <= 3                 # no monopoly


async def test_skewed_counts_do_not_starve_minority_chains():
    q = _q()
    _seed(q._col, "ethereum", 100)                   # heavy chain
    for c in ("arbitrum", "optimism", "bnb"):
        _seed(q._col, c, 1)                          # minority chains
    batch = await q.claim_batch("w1", batch_size=8)
    served = set(_chains(batch))
    assert {"arbitrum", "optimism", "bnb"}.issubset(served)
    assert _chains(batch).count("ethereum") < 8      # cannot take whole batch


async def test_no_permanent_monopoly_over_repeated_claims():
    q = _q()
    _seed(q._col, "ethereum", 50)
    _seed(q._col, "arbitrum", 3)
    seen = set()
    for _ in range(3):
        seen.update(_chains(await q.claim_batch("w", batch_size=4)))
    assert "arbitrum" in seen                         # minority eventually served


# 4 + 7: expired candidates never claimed; expiry semantics unchanged
async def test_expired_never_claimed():
    q = _q()
    _seed(q._col, "base", 5, expired=True)
    _seed(q._col, "ethereum", 2)
    batch = await q.claim_batch("w1", batch_size=10)
    assert _chains(batch) == ["ethereum", "ethereum"]  # expired base excluded
    assert len(batch) == 2


# 5: already-claimed / processed never incorrectly claimed
async def test_claimed_and_processed_excluded():
    q = _q()
    _seed(q._col, "ethereum", 3, claimed=True)
    _seed(q._col, "arbitrum", 3, processed=True)
    _seed(q._col, "optimism", 2)
    batch = await q.claim_batch("w1", batch_size=10)
    assert set(_chains(batch)) == {"optimism"}
    assert len(batch) == 2


# 6: legacy candidates without a chain field remain claimable
async def test_legacy_without_chain_still_claimable():
    q = _q()
    now = time.time()
    q._col._docs.append({
        "candidate_id": "legacy-1",
        "opportunity_type": OpportunityType.FLASH_LOAN_ARBITRAGE.value,
        "hint_source": "legacy", "subject_id": "legacy:subject",
        "hint_observed_at": now, "expires_at": now + 600,
        "verified_outcome": None, "claimed_at": None,
        "claimed_by": None, "claimed_until": None,
        # NOTE: no 'chain' key at all
    })
    _seed(q._col, "base", 1)
    batch = await q.claim_batch("w1", batch_size=10)
    ids = {c.candidate_id for c in batch}
    assert "legacy-1" in ids                          # legacy served via None bucket
    assert len(batch) == 2


# 8: no unsupported/synthetic chains are ever introduced
async def test_no_unsupported_chains_introduced():
    q = _q()
    _seed(q._col, "ethereum", 2)
    _seed(q._col, "base", 2)
    batch = await q.claim_batch("w1", batch_size=10)
    assert set(_chains(batch)).issubset({"ethereum", "base"})


# upsert_many stamps a top-level chain from the flash-loan subject_id
async def test_upsert_stamps_chain_from_subject_id():
    from arbicore.models.discovery import DiscoveryCandidate
    q = _q()
    cand = DiscoveryCandidate(
        candidate_id="c1", opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        hint_source="flash_loan_route_search",
        subject_id="flash_loan:aave_v3:arbitrum:USDC:r0")
    await q.upsert_many([cand])
    assert q._col._docs[0].get("chain") == "arbitrum"
