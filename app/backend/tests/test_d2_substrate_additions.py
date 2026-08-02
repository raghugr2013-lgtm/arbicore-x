"""ArbiCore X — Phase D D-2.0 substrate additions tests.

Covers:
  1. SOURCE_REGISTRY entries for the 7 perp/futures venues + Coinglass.
  2. VenueCapabilityRepository perp-related additions:
     - is_funding_gate_pass(venue, asset_base)
     - is_funding_pair_gate_pass(venue_a, venue_b, asset_base)
  3. Backwards compatibility — D-1 spot path (is_gate_3_pass) UNCHANGED.

No funding scanner / verifier code is touched in this test file; that
comes in the next D-2 checkpoint.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from arbicore.data import SOURCE_REGISTRY, get_classification
from arbicore.data.venue_capability_repo import VenueCapabilityRepository
from arbicore.models.enums import DataProvenance


# ============================================================================
# 1 — SOURCE_REGISTRY: D-2.0 entries present, REAL, with INV-3 documentation
# ============================================================================

D2_VENUE_FUTURES_SOURCES = [
    "bybit_futures_public",
    "okx_futures_public",
    "gate_futures_public",
    "bitget_futures_public",
    "mexc_futures_public",
    "kucoin_futures_public",
    "hyperliquid_public",
]

D2_AGGREGATOR_HINT_SOURCES = [
    "coinglass_funding_public",
]


@pytest.mark.parametrize("source_id", D2_VENUE_FUTURES_SOURCES)
def test_d2_venue_futures_source_registered_and_real(source_id):
    assert source_id in SOURCE_REGISTRY, f"missing D-2 venue source: {source_id}"
    assert get_classification(source_id) is DataProvenance.REAL


@pytest.mark.parametrize("source_id", D2_AGGREGATOR_HINT_SOURCES)
def test_d2_aggregator_hint_source_registered_and_real(source_id):
    assert source_id in SOURCE_REGISTRY
    assert get_classification(source_id) is DataProvenance.REAL
    # INV-3 documented in the reason string — guard against drift.
    reason = SOURCE_REGISTRY[source_id].reason.lower()
    assert "hint" in reason
    assert "inv-3" in reason or "telemetry" in reason


def test_d2_does_not_pollute_phase_b_native_count():
    """D-2 entries are additive — Phase B native source counts unchanged."""
    from arbicore.data import PHASE_B_NATIVE_SOURCES
    # Sanity: D-2 sources are NOT in the Phase B native list.
    for sid in D2_VENUE_FUTURES_SOURCES + D2_AGGREGATOR_HINT_SOURCES:
        assert sid not in PHASE_B_NATIVE_SOURCES


def test_hyperliquid_marked_experimental():
    """The user has asked Hyperliquid to be treated as experimental and
    operator-removable; the registry reason must document that."""
    reason = SOURCE_REGISTRY["hyperliquid_public"].reason.lower()
    assert "experimental" in reason or "optional" in reason


# ============================================================================
# 2 — VenueCapabilityRepository: funding helpers
# ============================================================================

class _StubCollection:
    """In-memory stub mimicking enough of motor's collection API for the
    repo helpers under test (find_one + update_one with upsert)."""

    def __init__(self) -> None:
        self._docs: Dict[str, Dict[str, Any]] = {}

    async def create_index(self, *a, **kw): return None
    async def find_one(self, query):
        vid = query.get("venue_id")
        return dict(self._docs[vid]) if vid in self._docs else None
    async def update_one(self, query, update, upsert=False):
        vid = query["venue_id"]
        d = dict(self._docs.get(vid, {}))
        d.update(update.get("$set", {}))
        self._docs[vid] = d
    async def insert_one(self, doc): return None
    def find(self, *a, **kw):
        class _Cur:
            def __init__(self, items): self._it = iter(items)
            def __aiter__(self): return self
            async def __anext__(self):
                try: return next(self._it)
                except StopIteration: raise StopAsyncIteration
            def sort(self, *a, **kw): return self
        return _Cur(list(self._docs.values()))


class _StubDb:
    def __init__(self) -> None:
        self._cols: Dict[str, _StubCollection] = {}
    def __getitem__(self, name): return self._cols.setdefault(name, _StubCollection())


@pytest.fixture
def repo() -> VenueCapabilityRepository:
    return VenueCapabilityRepository(_StubDb())


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) \
        if False else asyncio.run(coro)


def test_funding_gate_no_data_fails(repo):
    ok, why = _run(repo.is_funding_gate_pass("bybit", "BTC"))
    assert ok is False and why == "no_capability_data"


def test_funding_gate_venue_disabled_fails(repo):
    _run(repo.upsert("bybit", {
        "venue_status": "disabled", "has_perp_market": True,
        "perp_caps": {"BTC": {"listed": True}},
    }))
    ok, why = _run(repo.is_funding_gate_pass("bybit", "BTC"))
    assert ok is False and why.startswith("venue_status=")


def test_funding_gate_api_unhealthy_fails(repo):
    _run(repo.upsert("bybit", {
        "api_healthy": False, "has_perp_market": True,
        "perp_caps": {"BTC": {"listed": True}},
    }))
    ok, why = _run(repo.is_funding_gate_pass("bybit", "BTC"))
    assert ok is False and why == "api_unhealthy"


def test_funding_gate_requires_positive_perp_evidence(repo):
    """Absent has_perp_market → HARD fail (unlike spot caps where absent
    is permissive). Operator-mandated: we will not pretend perp exists."""
    _run(repo.upsert("bybit", {"api_healthy": True}))   # no perp data
    ok, why = _run(repo.is_funding_gate_pass("bybit", "BTC"))
    assert ok is False and why == "no_perp_market_evidence"


def test_funding_gate_requires_asset_listing(repo):
    _run(repo.upsert("bybit", {
        "api_healthy": True, "has_perp_market": True, "perp_caps": {},
    }))
    ok, why = _run(repo.is_funding_gate_pass("bybit", "BTC"))
    assert ok is False and why.startswith("perp_not_listed:")


def test_funding_gate_passes_with_full_evidence(repo):
    _run(repo.upsert("bybit", {
        "api_healthy": True, "has_perp_market": True,
        "perp_caps": {"BTC": {"listed": True, "perp_symbol": "BTCUSDT",
                              "funding_interval_h": 8}},
    }))
    ok, why = _run(repo.is_funding_gate_pass("bybit", "BTC"))
    assert ok is True and why == "ok"


def test_funding_pair_gate_rejects_same_venue(repo):
    _run(repo.upsert("bybit", {
        "api_healthy": True, "has_perp_market": True,
        "perp_caps": {"BTC": {"listed": True}},
    }))
    ok, why = _run(repo.is_funding_pair_gate_pass("bybit", "bybit", "BTC"))
    assert ok is False and why == "same_venue"


def test_funding_pair_gate_fails_when_one_venue_disqualified(repo):
    _run(repo.upsert("bybit", {
        "api_healthy": True, "has_perp_market": True,
        "perp_caps": {"BTC": {"listed": True}},
    }))
    _run(repo.upsert("okx", {"api_healthy": True}))  # no perp evidence
    ok, why = _run(repo.is_funding_pair_gate_pass("bybit", "okx", "BTC"))
    assert ok is False
    assert why.startswith("okx:")
    assert "no_perp_market_evidence" in why


def test_funding_pair_gate_passes_with_both_venues_evidenced(repo):
    for vid in ("bybit", "okx"):
        _run(repo.upsert(vid, {
            "api_healthy": True, "has_perp_market": True,
            "perp_caps": {"BTC": {"listed": True, "funding_interval_h": 8}},
        }))
    ok, why = _run(repo.is_funding_pair_gate_pass("bybit", "okx", "BTC"))
    assert ok is True and why == "ok"


# ============================================================================
# 3 — Backwards compatibility: D-1 spot gate path unaffected
# ============================================================================

def test_spot_gate_3_pass_unchanged_when_perp_fields_absent(repo):
    """Existing D-1 capability docs (no perp_caps / has_perp_market keys)
    must continue to pass the spot gate exactly as before."""
    _run(repo.upsert("bybit", {
        "api_healthy": True,
        "asset_caps": {
            "BTC": {"deposit_enabled": True},
            "USDT": {"withdraw_enabled": True},
        },
    }))
    ok, why = _run(repo.is_gate_3_pass("bybit", "BTC", "USDT"))
    assert ok is True and why == "ok"


def test_spot_gate_3_pass_still_works_alongside_perp_caps(repo):
    """A venue can be evidenced for BOTH spot AND perp without either
    path interfering with the other."""
    _run(repo.upsert("bybit", {
        "api_healthy": True,
        "asset_caps": {
            "BTC": {"deposit_enabled": True},
            "USDT": {"withdraw_enabled": True},
        },
        "has_perp_market": True,
        "perp_caps": {"BTC": {"listed": True}},
    }))
    spot_ok, _ = _run(repo.is_gate_3_pass("bybit", "BTC", "USDT"))
    funding_ok, _ = _run(repo.is_funding_gate_pass("bybit", "BTC"))
    assert spot_ok is True
    assert funding_ok is True


def test_funding_helpers_do_not_break_when_only_spot_data_present(repo):
    """A pre-existing D-1 capability doc with only spot asset_caps must
    cleanly fail the funding gate WITHOUT corrupting the spot result."""
    _run(repo.upsert("kucoin", {
        "api_healthy": True,
        "asset_caps": {"BTC": {"deposit_enabled": True},
                       "USDT": {"withdraw_enabled": True}},
    }))
    spot_ok, _ = _run(repo.is_gate_3_pass("kucoin", "BTC", "USDT"))
    funding_ok, why = _run(repo.is_funding_gate_pass("kucoin", "BTC"))
    assert spot_ok is True
    assert funding_ok is False
    assert why == "no_perp_market_evidence"
