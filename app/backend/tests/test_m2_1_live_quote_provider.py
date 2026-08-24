"""M2.1 — real live quote provider is wired and FAILS CLOSED (offline).

Exercises arbicore/scanners/flash_loan_arbitrage/live_quote_provider.py
::make_live_quote_provider against a fake QuoterRegistry (registry is a test
double ONLY to drive the provider plumbing offline — the REAL QuoterRegistry
is validated on the VPS with live RPC). Proves:
  * real quote facts carry on-chain provenance source_ids (no fabricated profit)
  * fail-closed (None) on: malformed route, registry exception, un-priceable
    route (rq None / status 'fallback:break_even')
  * gross_profit_pct is computed from the real quoted wei ratio, not assumed.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from arbicore.scanners.flash_loan_arbitrage.live_quote_provider import (
    make_live_quote_provider,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _meta():
    return {
        "borrow_token": "WETH",
        "route_pools": ["p1", "p2"],
        "cycle_token_path": ["WETH", "USDC", "WETH"],
    }


class _FakeRegistry:
    def __init__(self, rq):
        self._rq = rq
        self.calls = []

    async def quote_route(self, *, chain, hops):
        self.calls.append((chain, hops))
        if isinstance(self._rq, Exception):
            raise self._rq
        return self._rq


def _rq(final_out_wei, status="ok"):
    hop = SimpleNamespace(dex="uniswap_v3", status="ok")
    return SimpleNamespace(
        status=status, final_amount_out_wei=final_out_wei,
        aggregate_gas_estimate_units=300_000, hops=[hop, hop])


def test_live_provider_returns_real_facts_with_provenance():
    prov = make_live_quote_provider(_FakeRegistry(_rq(int(1.05e16))))
    facts = _run(prov(_meta(), 10_000.0))
    assert facts is not None
    assert facts["hop_legs"], "must carry per-hop legs"
    # provenance: each hop carries a REGISTERED, REAL-classified quoter source
    # id (never a DEAD/unregistered tag that would fail-close downstream).
    from arbicore.data.provenance import get_classification
    from arbicore.models.enums import DataProvenance
    assert all(get_classification(l["source_id"]) == DataProvenance.REAL
               for l in facts["hop_legs"])
    assert "gross_profit_pct" in facts and facts["tx_gas_units"] == 300_000
    assert facts["route_quote_status"] == "ok"


def test_live_provider_gross_profit_from_real_ratio():
    # final_out >> amount_in → positive; final_out ~0 → negative. Robust to the
    # configured probe amount; proves profit is the real quoted ratio, not assumed.
    pos = _run(make_live_quote_provider(_FakeRegistry(_rq(10 ** 30)))(_meta(), 1e4))
    neg = _run(make_live_quote_provider(_FakeRegistry(_rq(1)))(_meta(), 1e4))
    assert pos["gross_profit_pct"] > 0
    assert neg["gross_profit_pct"] < 0     # losing route surfaces honestly → Gate 7


def test_fail_closed_on_malformed_route():
    prov = make_live_quote_provider(_FakeRegistry(_rq(int(1.05e16))))
    bad = {"borrow_token": "WETH", "route_pools": ["p1"],
           "cycle_token_path": ["WETH", "USDC", "WETH"]}   # len mismatch
    assert _run(prov(bad, 1e4)) is None


def test_fail_closed_on_registry_exception():
    prov = make_live_quote_provider(_FakeRegistry(RuntimeError("rpc down")))
    assert _run(prov(_meta(), 1e4)) is None


def test_fail_closed_on_unpriceable_route():
    assert _run(make_live_quote_provider(_FakeRegistry(None))(_meta(), 1e4)) is None
    fb = make_live_quote_provider(_FakeRegistry(_rq(int(1.05e16), status="fallback:break_even")))
    assert _run(fb(_meta(), 1e4)) is None
