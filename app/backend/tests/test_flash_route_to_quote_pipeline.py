"""End-to-end OFFLINE proof: RouteSearchDiscoverySource → chain/venue-aware
live_quote_provider → chain-specific pool resolution → real quote interface →
existing economic gate. Deterministic, no real RPC, no signing/broadcast.

Covers the confirmed acceptance list (2a + 3a):
  1  unknown decimals fail closed
  2  <=6-decimal probe is deterministic
  3  18-decimal probe is deterministic
  4  probe amount does not imply liquidity
  5  chain A never uses chain B RPC
  6  missing chain RPC returns None / fails closed
  7  Base behaviour remains unchanged (augment is a no-op for Base)
  8  non-Base route metadata reaches the live_quote_provider
  9  UniV3 resolver receives the correct chain (its registered factory)
 10  QuoterRegistry receives the correct chain
 11  hop chaining remains correct
 12  unsupported venue remains fail closed
 13  no fabricated quote/TVL can become authoritative
 14  certification distinguishes structural connectivity from runtime QUOTABLE
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from eth_abi import encode as _enc
from eth_utils import to_checksum_address

from arbicore.chains.registries import probe_amount_wei, tokens_for
from arbicore.discovery import univ3_pool_resolver as R
from arbicore.discovery.multichain_venues import build_pool_graph
from arbicore.discovery.opportunity_engine import build_opportunity_matrix
from arbicore.intelligence.roi_probability import ROIProbabilityEngine
from arbicore.scanners.flash_loan_arbitrage.economics import (
    FlashLoanEconomicsAssessor,
)
from arbicore.scanners.flash_loan_arbitrage.live_quote_provider import (
    make_live_quote_provider,
)
from arbicore.scanners.flash_loan_arbitrage.route_search import (
    PoolNode, RouteCycle, RouteSearchEngine,
)
from arbicore.scanners.flash_loan_arbitrage.sources import (
    RouteSearchDiscoverySource,
)

# The registered generic EVM chains that carry a UniV3 factory + WETH/USDC.
_QUOTE_CHAINS = ["ethereum", "arbitrum", "optimism", "polygon", "bnb"]
# The flash-loan discovery SOURCE scope is deliberately locked (see
# test_d6_0_substrate.test_chain_scope_locked) and excludes bnb.
_SOURCE_CHAINS = ["ethereum", "arbitrum", "optimism", "polygon"]

_POOL = to_checksum_address("0x" + "c3" * 20)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _addr(chain, sym):
    return tokens_for(chain)[sym]["address"]


def _healthy_eth_call(chain, *, record=None):
    """A per-chain read-only eth_call that ONLY answers for that chain's
    registered UniV3 factory + a WETH/USDC pool. Records the chain it served
    so a test can prove no cross-chain RPC bleed."""
    factory = R.univ3_factory_for(chain)
    weth, usdc = _addr(chain, "WETH"), _addr(chain, "USDC")

    async def eth_call(to, data):
        if record is not None:
            record.append(chain)
        sel = data[:10]
        if to.lower() == factory.lower():
            return "0x" + _enc(["address"], [_POOL]).hex()
        if sel == R._SEL_TOKEN0:
            return "0x" + _enc(["address"], [to_checksum_address(weth)]).hex()
        if sel == R._SEL_TOKEN1:
            return "0x" + _enc(["address"], [to_checksum_address(usdc)]).hex()
        if sel == R._SEL_FEE:
            return "0x" + _enc(["uint24"], [500]).hex()
        if sel == R._SEL_LIQUIDITY:
            return "0x" + _enc(["uint128"], [10 ** 18]).hex()
        raise AssertionError(sel)

    return eth_call


class _FakeQuoter:
    """Records the chain + hops it was asked to quote; returns a closed-cycle
    profit. NEVER contacts a network."""

    def __init__(self, *, status="ok", hop_status="ok", final=2_000_000):
        self.status, self.hop_status, self.final = status, hop_status, final
        self.last_chain = None
        self.last_hops = None

    async def quote_route(self, *, chain, hops, rpc_url=None):
        self.last_chain, self.last_hops = chain, hops
        hop_objs = [SimpleNamespace(dex=h["dex"], status=self.hop_status,
                                    block_number=100 + i)
                    for i, h in enumerate(hops)]
        return SimpleNamespace(status=self.status, hops=hop_objs,
                               final_amount_out_wei=self.final,
                               aggregate_gas_estimate_units=210_000)


def _route_meta(chain):
    """The exact hint_metric shape RouteSearchDiscoverySource now emits for a
    WETH→USDC→WETH cycle on ``chain`` (symbols + venue-id + fee ppm + probe)."""
    return {
        "chain": chain,
        "borrow_token": "WETH",
        "cycle_token_path": ["WETH", "USDC", "WETH"],
        "borrow_amount_wei": probe_amount_wei(chain, "WETH"),
        "route_hops": [
            {"dex": "uniswap_v3", "token_in": "WETH", "token_out": "USDC",
             "fee": 500, "pool": f"uniswap_v3:USDC:WETH:500"},
            {"dex": "uniswap_v3", "token_in": "USDC", "token_out": "WETH",
             "fee": 500, "pool": f"uniswap_v3:USDC:WETH:500"},
        ],
    }


# ── (1)(2)(3) deterministic probe amounts ───────────────────────────────────

def test_unknown_decimals_probe_fails_closed():
    # WBTC has 8 decimals (unsupported) → None; unknown symbol → None.
    assert probe_amount_wei("arbitrum", "WBTC") is None
    assert probe_amount_wei("arbitrum", "NOPE") is None


def test_probe_6_decimal_is_deterministic():
    a = probe_amount_wei("arbitrum", "USDC")   # 6 decimals
    b = probe_amount_wei("arbitrum", "USDC")
    assert a == b == 200 * 10 ** 6


def test_probe_18_decimal_is_deterministic():
    a = probe_amount_wei("arbitrum", "WETH")   # 18 decimals
    b = probe_amount_wei("arbitrum", "WETH")
    assert a == b == 5 * 10 ** 16


# ── (7) Base behaviour is untouched (augment is a no-op for Base) ────────────

def _base_cycle():
    pools = [
        PoolNode(pool_address="uniswap_v3:USDC:WETH:500", dex_protocol="uniswap_v3",
                 chain="base", token_a="WETH", token_b="USDC", tvl_usd=0.0, fee_bps=5),
        PoolNode(pool_address="uniswap_v3:USDC:WETH:3000", dex_protocol="uniswap_v3",
                 chain="base", token_a="USDC", token_b="WETH", tvl_usd=0.0, fee_bps=30),
    ]
    return RouteCycle(chain="base", borrow_token="WETH", pools=pools,
                      token_path=["WETH", "USDC", "WETH"], min_tvl_usd=0.0,
                      hop_count=2, estimated_total_fee_pct=0.35)


def test_base_route_metadata_is_regression_frozen():
    hm = {"chain": "base", "borrow_token": "WETH"}
    RouteSearchDiscoverySource._augment_multichain_route(_base_cycle(), hm)
    # Base must NOT gain the generic-EVM fields — it uses _plan_base.
    assert "route_hops" not in hm
    assert "borrow_amount_wei" not in hm
    assert "borrow_amount_provenance" not in hm


# ── (8) source emits non-Base route metadata that the provider consumes ──────

def _build_source(chain, *, provider="aave_v3"):
    nodes = build_pool_graph(chain)
    assert nodes, f"expected a non-empty venue graph for {chain}"
    engine = RouteSearchEngine(pool_loader=lambda c: nodes, max_hops=3,
                               min_pool_tvl_usd=0.0)
    cfg = {"chains": {chain: {"enabled": True}},
           "providers": {provider: {"enabled": True}}}
    return RouteSearchDiscoverySource(route_engine=engine,
                                      config_loader=lambda: cfg)


@pytest.mark.parametrize("chain", _SOURCE_CHAINS)
def test_source_emits_route_hops_and_probe(chain):
    src = _build_source(chain)
    cands = _run(src.discover())
    assert cands, f"no candidates discovered for {chain}"
    hm = cands[0].hint_metric
    assert hm["chain"] == chain
    hops = hm["route_hops"]
    assert len(hops) >= 2
    for h in hops:
        assert h["dex"]                       # venue preserved
        assert h["token_in"] and h["token_out"]
        assert isinstance(h["fee"], int) and h["fee"] > 0   # fee ppm carried
        assert h["pool"]                      # venue id carried, not fabricated
    # deterministic probe borrow amount for the borrow token on this chain
    assert hm["borrow_amount_wei"] == probe_amount_wei(chain, hm["borrow_token"])
    assert hm["borrow_amount_provenance"] == "deterministic_probe"


# ── (4) probe amount does not imply liquidity ───────────────────────────────

def test_probe_amount_does_not_imply_liquidity():
    src = _build_source("arbitrum")
    hm = _run(src.discover())[0].hint_metric
    assert hm["borrow_amount_wei"] > 0
    # No liquidity is asserted from a probe: the route's min TVL stays 0 and
    # nothing marks it executable / limited-live eligible.
    assert hm["min_tvl_usd"] == 0.0
    assert "limited_live_eligible" not in hm
    # And with NO TVL provider the quote's route TVL stays 0 (Gate-8 fail-closed)
    q = _FakeQuoter()
    prov = make_live_quote_provider(
        q, eth_call_for_chain=lambda c: _healthy_eth_call(c))
    facts = _run(prov(_route_meta("arbitrum"), 10_000.0))
    assert facts["min_pool_tvl_usd_in_route"] == 0.0
    assert facts["tvl_provenance"] == "unverified"


# ── (8)(9)(10)(11) full quote path per chain ────────────────────────────────

@pytest.mark.parametrize("chain", _QUOTE_CHAINS)
def test_quote_path_is_chain_correct(chain):
    q = _FakeQuoter()
    prov = make_live_quote_provider(
        q, eth_call_for_chain=lambda c: _healthy_eth_call(c))
    facts = _run(prov(_route_meta(chain), 10_000.0))
    assert facts is not None
    # (10) QuoterRegistry got the right chain
    assert q.last_chain == chain and facts["chain"] == chain
    # (9) resolver used THIS chain's tokens (chain-correct addresses on the hop)
    assert q.last_hops[0]["token_in"] == _addr(chain, "WETH")
    assert q.last_hops[0]["token_out"] == _addr(chain, "USDC")
    # fee tier propagated
    assert q.last_hops[0]["fee"] == 500
    # (11) hop chaining: only hop0 carries an explicit amount_in
    assert q.last_hops[0]["amount_in_wei"] == probe_amount_wei(chain, "WETH")
    assert "amount_in_wei" not in q.last_hops[1]


# ── (5) chain A never uses chain B RPC ──────────────────────────────────────

def test_chain_a_never_uses_chain_b_rpc():
    served: list = []

    def seam(c):
        return _healthy_eth_call(c, record=served)

    q = _FakeQuoter()
    prov = make_live_quote_provider(q, eth_call_for_chain=seam)
    _run(prov(_route_meta("arbitrum"), 10_000.0))
    # only the requested chain's RPC seam was ever invoked
    assert set(served) == {"arbitrum"}


# ── (6) missing chain RPC returns None / fails closed (per-chain) ────────────

def test_missing_chain_rpc_fails_closed_but_isolated():
    # RPC configured for arbitrum only; optimism has no seam → fails closed.
    seams = {"arbitrum": _healthy_eth_call("arbitrum")}
    q = _FakeQuoter()
    prov = make_live_quote_provider(q, eth_call_for_chain=lambda c: seams.get(c))
    assert _run(prov(_route_meta("optimism"), 10_000.0)) is None   # no RPC
    assert _run(prov(_route_meta("arbitrum"), 10_000.0)) is not None  # has RPC


# ── (12) unsupported venue family fails closed ──────────────────────────────

def test_unsupported_venue_family_fails_closed():
    q = _FakeQuoter()
    prov = make_live_quote_provider(
        q, eth_call_for_chain=lambda c: _healthy_eth_call(c))
    meta = _route_meta("arbitrum")
    meta["route_hops"] = [
        {"dex": "curve_stable", "token_in": "WETH", "token_out": "USDC", "fee": 0},
        {"dex": "curve_stable", "token_in": "USDC", "token_out": "WETH", "fee": 0},
    ]
    assert _run(prov(meta, 10_000.0)) is None


# ── (13) no fabricated quote can become authoritative ───────────────────────

def test_partial_quote_cannot_become_authoritative():
    # A hop that degraded to a fallback must never be treated as a real quote.
    q = _FakeQuoter(status="ok", hop_status="fallback:revert")
    prov = make_live_quote_provider(
        q, eth_call_for_chain=lambda c: _healthy_eth_call(c))
    assert _run(prov(_route_meta("arbitrum"), 10_000.0)) is None


# ── economic gate is CONNECTED to the live quote (discovery→quote→economics) ─

def test_live_quote_feeds_existing_economic_gate():
    q = _FakeQuoter(final=int(1.01 * 5 * 10 ** 16))   # small positive gross
    prov = make_live_quote_provider(
        q, eth_call_for_chain=lambda c: _healthy_eth_call(c))
    facts = _run(prov(_route_meta("arbitrum"), 10_000.0))
    assert facts is not None and facts["gross_profit_pct"] > 0

    econ = FlashLoanEconomicsAssessor(
        roi_engine=ROIProbabilityEngine(min_sample=8, winsorize_pct=0.05),
        default_borrow_amount_usd=10_000.0)
    result = econ.assess(
        provider="aave_v3", chain="arbitrum", borrow_token="WETH",
        borrow_amount_usd=10_000.0, hop_legs=facts["hop_legs"],
        signal_categories=["aave_v3", "arbitrum", "WETH"],
        real_outcomes=[], gross_profit_pct=facts["gross_profit_pct"],
        tx_gas_units=facts["tx_gas_units"], gross_is_quote_inclusive=True)
    # The economic engine consumed the live quote end-to-end: gross → fees →
    # flash-loan cost → gas → slippage → net were all computed.
    assert isinstance(result.atomic_profit_usd, float)
    assert isinstance(result.flash_loan_fee_usd, float)
    assert isinstance(result.economics.gross_spread_pct, float)


# ── (14) certification distinguishes structural connectivity from runtime ────

def test_certification_structural_vs_runtime():
    m = build_opportunity_matrix()
    s = m["summary"]
    assert s["quote_path_connected_count"] > 0
    connected = [r for r in m["rows"] if r["quote_path_connected"]]
    assert connected
    for r in connected:
        # structural connectivity NEVER asserts runtime capability
        assert r["quote"] == "requires_runtime"
        assert r["economic"] == "requires_runtime"
        assert r["liquidity_tvl"] == "requires_runtime"
        assert r["limited_live_eligible"] is False
    # Base uniswap_v3 is connected; a non-Base non-UniV3 venue is NOT.
    base_univ3 = [r for r in m["rows"]
                  if r["chain"] == "base" and r["venue"] == "uniswap_v3"]
    assert base_univ3 and all(r["quote_path_connected"] for r in base_univ3)
    non_univ3 = [r for r in m["rows"]
                 if r["chain"] != "base" and r["venue"] != "uniswap_v3"]
    assert non_univ3 and all(not r["quote_path_connected"] for r in non_univ3)
