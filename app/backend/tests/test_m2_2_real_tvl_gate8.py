"""M2.2 — REAL measured on-chain TVL feeds Gate 8; fail-closed (offline).

Proves the live quote provider (make_live_quote_provider) now derives
``min_pool_tvl_usd_in_route`` from a REAL injected tvl_provider keyed by the
canonical registry's REAL pool addresses — and FAILS CLOSED (0.0) whenever
depth is unverifiable, so Gate 8 can never pass on fabricated liquidity.

All fixtures are deterministic doubles (no RPC): the REAL OnChainReserveTVL
path is validated live on the VPS.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from arbicore.discovery import base_pool_registry as reg
from arbicore.discovery.base_venues import build_pool_graph
from arbicore.scanners.flash_loan_arbitrage.live_quote_provider import (
    make_live_quote_provider, _resolve_pool_tvls, _route_min_tvl,
)
from arbicore.scanners.flash_loan_arbitrage.filter import (
    FlashLoanGate8LiquidityDepth,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _two_univ3_pool_ids():
    """Two REAL deterministic-verified UniV3 canonical ids sharing a token so a
    2-hop cycle is well-formed (WETH/USDC 0.05% and 0.30%)."""
    ids = [p.canonical_id for p in reg.get_canonical_pools()
           if p.address_resolution == reg.DETERMINISTIC_VERIFIED
           and p.dex == "uniswap_v3"
           and {"WETH", "USDC"} == {p.token0_symbol, p.token1_symbol}]
    return ids[:2]


def _meta_real():
    ids = _two_univ3_pool_ids()
    assert len(ids) == 2, "need two real WETH/USDC UniV3 pools in registry"
    return {"borrow_token": "WETH", "route_pools": ids,
            "cycle_token_path": ["WETH", "USDC", "WETH"]}


class _FakeRegistry:
    async def quote_route(self, *, chain, hops):
        hop = SimpleNamespace(dex="uniswap_v3", status="ok")
        return SimpleNamespace(status="ok", final_amount_out_wei=int(1.05e16),
                               aggregate_gas_estimate_units=300_000,
                               hops=[hop, hop])


class _StaticAddrTVL:
    """tvl_provider double keyed by REAL pool ADDRESS (chain, address)."""

    def __init__(self, by_addr):
        self._by_addr = {a.lower(): v for a, v in by_addr.items()}

    async def get_pool_tvl_usd(self, chain, pool_address):
        return self._by_addr.get((pool_address or "").lower())


class _RaisingTVL:
    async def get_pool_tvl_usd(self, chain, pool_address):
        raise RuntimeError("rpc down")


# ── unit: TVL resolution + min helper ───────────────────────────────────────

def test_resolve_and_min_all_pools_positive():
    ids = _two_univ3_pool_ids()
    addr = {reg.canonical_pool_by_id(i).address: v
            for i, v in zip(ids, [500_000.0, 250_000.0])}
    tvls = _run(_resolve_pool_tvls(ids, _StaticAddrTVL(addr)))
    assert set(tvls) == set(ids)
    assert _route_min_tvl(tvls, ids) == 250_000.0


def test_min_fail_closed_when_one_pool_unresolved():
    ids = _two_univ3_pool_ids()
    # Only price the first pool → second is missing → fail closed (0.0).
    addr = {reg.canonical_pool_by_id(ids[0]).address: 500_000.0}
    tvls = _run(_resolve_pool_tvls(ids, _StaticAddrTVL(addr)))
    assert _route_min_tvl(tvls, ids) == 0.0


def test_resolve_fail_closed_on_provider_exception():
    ids = _two_univ3_pool_ids()
    tvls = _run(_resolve_pool_tvls(ids, _RaisingTVL()))
    assert tvls == {}
    assert _route_min_tvl(tvls, ids) == 0.0


def test_resolve_none_provider_is_empty():
    ids = _two_univ3_pool_ids()
    assert _run(_resolve_pool_tvls(ids, None)) == {}


# ── integration: provider → facts → Gate 8 ─────────────────────────────────

def test_provider_reports_real_min_tvl_and_gate8_passes():
    ids = _two_univ3_pool_ids()
    addr = {reg.canonical_pool_by_id(i).address: v
            for i, v in zip(ids, [500_000.0, 300_000.0])}
    prov = make_live_quote_provider(_FakeRegistry(),
                                    tvl_provider=_StaticAddrTVL(addr))
    facts = _run(prov(_meta_real(), 10_000.0))
    assert facts is not None
    assert facts["min_pool_tvl_usd_in_route"] == 300_000.0
    assert facts["tvl_provenance"] == "onchain_reserves"
    g8 = FlashLoanGate8LiquidityDepth(thresholds={}).evaluate(
        min_pool_tvl_usd_in_route=facts["min_pool_tvl_usd_in_route"])
    assert g8.passed is True


def test_provider_fail_closed_no_tvl_provider_denies_gate8():
    prov = make_live_quote_provider(_FakeRegistry())  # no tvl_provider
    facts = _run(prov(_meta_real(), 10_000.0))
    assert facts["min_pool_tvl_usd_in_route"] == 0.0
    assert facts["tvl_provenance"] == "unverified"
    g8 = FlashLoanGate8LiquidityDepth(thresholds={}).evaluate(
        min_pool_tvl_usd_in_route=facts["min_pool_tvl_usd_in_route"])
    assert g8.passed is False
    assert "unverifiable" in g8.reason


def test_provider_fail_closed_thin_pool_denies_gate8():
    ids = _two_univ3_pool_ids()
    addr = {reg.canonical_pool_by_id(i).address: v
            for i, v in zip(ids, [500_000.0, 10_000.0])}  # 2nd below 100k floor
    prov = make_live_quote_provider(_FakeRegistry(),
                                    tvl_provider=_StaticAddrTVL(addr))
    facts = _run(prov(_meta_real(), 10_000.0))
    assert facts["min_pool_tvl_usd_in_route"] == 10_000.0
    g8 = FlashLoanGate8LiquidityDepth(thresholds={}).evaluate(
        min_pool_tvl_usd_in_route=facts["min_pool_tvl_usd_in_route"])
    assert g8.passed is False
