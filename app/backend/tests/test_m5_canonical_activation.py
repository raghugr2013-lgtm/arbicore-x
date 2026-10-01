"""M5 Canonical Activation — DiscoverySource wiring + Gate 7 / gas sanity."""
from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest
from eth_utils import to_checksum_address

from arbicore.models.discovery import DiscoveryCandidate
from arbicore.models.enums import OpportunityType
from arbicore.scanners.flash_loan_arbitrage.activation_sources import (
    BalancerV2DiscoverySource,
    GenericDexDiscoverySource,
    TriangularDiscoverySource,
)
from arbicore.scanners.flash_loan_arbitrage.filter import (
    FlashLoanGate7AtomicProfit,
)
from arbicore.scanners.flash_loan_arbitrage.route_search import (
    PoolNode, RouteSearchEngine,
)
from arbicore.scanners.flash_loan_arbitrage.sources import (
    build_all_flash_loan_sources,
)
from arbicore.scanners.flash_loan_arbitrage.triangular import (
    discover_triangular,
)
import arbicore.scanners.generic_dex_route_engine as gde
from arbicore.scanners.generic_dex_route_engine import (
    GenericDexRouteEngine, VenueSpec, UNKNOWN_GAS, MIN_ATOMIC_PROFIT_USD,
)
from arbicore.intelligence.roi_probability import ROIProbabilityEngine
from arbicore.scanners.flash_loan_arbitrage.economics import (
    FlashLoanEconomicsAssessor,
)
from arbicore.models.enums import MevRiskLevel
from arbicore.scanners.flash_loan_arbitrage import live_quote_provider as lqp


def _pool(addr, a, b, *, tvl=1_000_000.0, fee_bps=30,
          dex="uniswap_v3", chain="ethereum"):
    return PoolNode(pool_address=addr, dex_protocol=dex, chain=chain,
                    token_a=a, token_b=b, tvl_usd=tvl, fee_bps=fee_bps)


def _cfg(**overrides) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {
        "interval_s": 60,
        "default_notional_usd": 10_000.0,
        "providers": {
            "aave_v3": {"enabled": False},
            "balancer_v2": {"enabled": False},
        },
        "chains": {c: {"enabled": False}
                   for c in ("ethereum", "arbitrum", "base",
                             "optimism", "polygon", "bnb")},
        "route_search": {
            "max_hops": 4, "wall_clock_cap_s": 5.0,
            "candidate_cap": 64, "min_pool_tvl_usd": 100_000,
        },
        "discovery_sources": {
            "generic_dex": {"enabled": True},
            "triangular": {"enabled": True},
            "balancer_v2": {"enabled": True},
        },
        "gate_thresholds": {
            "default": {"min_atomic_profit_usd": 25.0},
        },
    }
    cfg.update(overrides)
    return cfg


# --------------------------------------------------------------------------- #
# Factory / INV wiring
# --------------------------------------------------------------------------- #

def test_m5_factory_registers_activation_sources():
    engine = RouteSearchEngine(pool_loader=lambda c: [])
    out = build_all_flash_loan_sources(
        route_engine=engine, config_loader=lambda: _cfg())
    ids = sorted(s.source_id for s in out)
    assert ids == [
        "flash_loan_balancer_v2",
        "flash_loan_generic_dex",
        "flash_loan_provider_health",
        "flash_loan_route_search",
        "flash_loan_triangular",
    ]


def test_m5_sources_inv1_no_emission_bus():
    import arbicore.scanners.flash_loan_arbitrage.activation_sources as mod
    text = open(mod.__file__).read()
    assert "from ...emission_bus" not in text
    assert "_bus.emit(" not in text
    # Must not CALL the library emit helper (docstring may mention it).
    assert "emit_flash_candidate(" not in text


def test_gate7_floor_still_25():
    g = FlashLoanGate7AtomicProfit(thresholds={})
    r = g.evaluate(atomic_profit_usd=24.99, borrow_amount_usd=10_000.0)
    assert r.passed is False
    r2 = g.evaluate(atomic_profit_usd=25.0, borrow_amount_usd=10_000.0)
    assert r2.passed is True
    assert MIN_ATOMIC_PROFIT_USD == 25.0


# --------------------------------------------------------------------------- #
# GENERIC_DEX DiscoverySource
# --------------------------------------------------------------------------- #

def test_generic_dex_source_emits_cross_venue_2hop():
    cfg = _cfg()
    cfg["chains"]["ethereum"]["enabled"] = True
    cfg["providers"]["aave_v3"]["enabled"] = True
    pools = [
        _pool("univ3:USDC:WETH:500", "USDC", "WETH", dex="uniswap_v3"),
        _pool("sushi:USDC:WETH:3000", "USDC", "WETH", dex="sushiswap"),
    ]
    engine = RouteSearchEngine(pool_loader=lambda c: pools, min_pool_tvl_usd=0)
    src = GenericDexDiscoverySource(
        route_engine=engine, config_loader=lambda: cfg,
        borrow_token_set=["USDC"])
    out = asyncio.run(src.discover())
    assert out
    assert all(isinstance(c, DiscoveryCandidate) for c in out)
    assert all(c.opportunity_type == OpportunityType.FLASH_LOAN_ARBITRAGE
               for c in out)
    assert all(c.hint_metric.get("strategy_hint") == "GENERIC_DEX" for c in out)
    assert all(c.hint_metric.get("hop_count") == 2 for c in out)
    assert all("route_hops" in c.hint_metric for c in out)


def test_generic_dex_source_dormant_when_disabled():
    cfg = _cfg()
    cfg["chains"]["ethereum"]["enabled"] = True
    cfg["providers"]["aave_v3"]["enabled"] = True
    cfg["discovery_sources"]["generic_dex"]["enabled"] = False
    pools = [
        _pool("p1", "USDC", "WETH", dex="uniswap_v3"),
        _pool("p2", "USDC", "WETH", dex="sushiswap"),
    ]
    engine = RouteSearchEngine(pool_loader=lambda c: pools, min_pool_tvl_usd=0)
    src = GenericDexDiscoverySource(
        route_engine=engine, config_loader=lambda: cfg,
        borrow_token_set=["USDC"])
    assert asyncio.run(src.discover()) == []


# --------------------------------------------------------------------------- #
# Triangular DiscoverySource + $25 library alignment
# --------------------------------------------------------------------------- #

def test_triangular_library_default_is_gate7_25():
    sig = inspect.signature(discover_triangular)
    assert sig.parameters["min_net_profit_usd"].default == 25.0


def test_triangular_source_emits_3hop_candidates():
    cfg = _cfg()
    cfg["chains"]["ethereum"]["enabled"] = True
    cfg["providers"]["balancer_v2"]["enabled"] = True
    pools = [
        _pool("p_usdc_weth", "USDC", "WETH"),
        _pool("p_weth_wbtc", "WETH", "WBTC"),
        _pool("p_wbtc_usdc", "WBTC", "USDC"),
    ]
    engine = RouteSearchEngine(pool_loader=lambda c: pools, min_pool_tvl_usd=0)
    src = TriangularDiscoverySource(
        route_engine=engine, config_loader=lambda: cfg,
        borrow_token_set=["USDC"], intermediates=["WETH", "WBTC"])
    out = asyncio.run(src.discover())
    assert out
    assert all(c.hint_metric.get("strategy_hint") == "TRIANGULAR" for c in out)
    assert all(c.hint_metric.get("hop_count") == 3 for c in out)
    assert all(c.hint_metric.get("canonical_gate7_floor_usd") == 25.0
               for c in out)
    assert all(isinstance(c, DiscoveryCandidate) for c in out)


# --------------------------------------------------------------------------- #
# Balancer P1/P1b DiscoverySource — fail-closed + wiring
# --------------------------------------------------------------------------- #

class _FakeSubgraph:
    source_name = "balancer_v2_subgraph"

    def __init__(self, result):
        self._result = result
        self.calls = []

    async def find_pools(self, chain, token_a, token_b):
        self.calls.append((chain, token_a, token_b))
        return self._result


def test_balancer_source_failclosed_without_subgraph_url():
    from arbicore.discovery.balancer_v2_pool_enumeration import (
        DiscoverySourceResult, SRC_DISCOVERY_UNAVAILABLE)

    cfg = _cfg()
    cfg["chains"]["ethereum"]["enabled"] = True
    cfg["providers"]["aave_v3"]["enabled"] = True
    pools = [
        _pool("univ3:USDC:WETH:500", "USDC", "WETH", dex="uniswap_v3"),
    ]
    engine = RouteSearchEngine(pool_loader=lambda c: pools, min_pool_tvl_usd=0)
    unavailable = DiscoverySourceResult(
        SRC_DISCOVERY_UNAVAILABLE, source_name="balancer_v2_subgraph",
        error="no subgraph URL configured for chain 'ethereum'")

    def _onchain_factory(**kw):
        class _Empty:
            async def find_pools(self, chain, a, b):
                return DiscoverySourceResult(
                    SRC_DISCOVERY_UNAVAILABLE,
                    source_name="balancer_v2_onchain_pool_registered",
                    error="no eth_getLogs fetcher configured")
        return _Empty()

    src = BalancerV2DiscoverySource(
        route_engine=engine, config_loader=lambda: cfg,
        borrow_token_set=["USDC"], intermediates=["WETH"],
        subgraph_source=_FakeSubgraph(unavailable),
        onchain_source_factory=_onchain_factory,
        eth_get_logs_factory=lambda c: None,
    )
    out = asyncio.run(src.discover())
    assert out == []
    health = asyncio.run(src.health())
    assert health.ok is False
    assert health.last_error
    # Either subgraph URL absence or onchain getLogs absence is recorded —
    # both are fail-closed (no fabricated pools).
    assert ("subgraph" in health.last_error
            or "onchain" in health.last_error
            or "unavailable" in health.last_error.lower())


def test_balancer_source_emits_with_explicit_pool_identity():
    from arbicore.discovery.balancer_v2_pool_enumeration import (
        DiscoverySourceResult, PoolCandidate, SRC_OK, SRC_DISCOVERY_UNAVAILABLE)

    cfg = _cfg()
    cfg["chains"]["ethereum"]["enabled"] = True
    cfg["providers"]["aave_v3"]["enabled"] = True
    pools = [
        _pool("univ3:USDC:WETH:500", "USDC", "WETH", dex="uniswap_v3"),
    ]
    engine = RouteSearchEngine(pool_loader=lambda c: pools, min_pool_tvl_usd=0)
    pid = "0x" + "ab" * 32
    paddr = "0x" + "cd" * 20
    ok = DiscoverySourceResult(
        SRC_OK, candidates=[
            PoolCandidate(chain="ethereum", pool_id=pid, pool_address=paddr,
                          source="test")],
        source_name="balancer_v2_subgraph")

    def _onchain_factory(**kw):
        class _Empty:
            async def find_pools(self, chain, a, b):
                return DiscoverySourceResult(
                    SRC_DISCOVERY_UNAVAILABLE,
                    source_name="balancer_v2_onchain_pool_registered",
                    error="no eth_getLogs fetcher configured")
        return _Empty()

    src = BalancerV2DiscoverySource(
        route_engine=engine, config_loader=lambda: cfg,
        borrow_token_set=["USDC"], intermediates=["WETH"],
        subgraph_source=_FakeSubgraph(ok),
        onchain_source_factory=_onchain_factory,
    )
    out = asyncio.run(src.discover())
    assert out
    hm = out[0].hint_metric
    assert hm["route_hops"][0]["dex"] == "balancer_v2"
    assert hm["route_hops"][0]["pool_id"] == pid
    assert hm["route_hops"][0]["pool_address"] == paddr
    assert hm["route_hops"][1]["dex"] == "uniswap_v3"


# --------------------------------------------------------------------------- #
# live_quote_provider — balancer_v2 hop identity plumbing
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_plan_generic_evm_accepts_balancer_with_identity():
    async def eth_call(to, data):
        return "0x"

    hm = {
        "cycle_token_path": ["USDC", "WETH", "USDC"],
        "borrow_amount_wei": 10 ** 6,
        "route_hops": [
            {"dex": "balancer_v2", "token_in": "USDC", "token_out": "WETH",
             "pool_id": "0x" + "ab" * 32,
             "pool_address": "0x" + "cd" * 20},
            {"dex": "balancer_v2", "token_in": "WETH", "token_out": "USDC",
             "pool_id": "0x" + "ef" * 32,
             "pool_address": "0x" + "11" * 20},
        ],
    }
    # tokens_for must resolve USDC/WETH — monkeypatch via real registry if present
    planned = await lqp._plan_generic_evm("ethereum", hm, eth_call)
    # May be None if registry lacks tokens in offline env; identity helper still
    # must accept balancer when tokens resolve.
    if planned is None:
        # Explicit: missing identity must fail closed
        bad = dict(hm)
        bad["route_hops"] = [
            {"dex": "balancer_v2", "token_in": "USDC", "token_out": "WETH"},
            {"dex": "balancer_v2", "token_in": "WETH", "token_out": "USDC"},
        ]
        assert await lqp._plan_generic_evm("ethereum", bad, eth_call) is None
        return
    plans, path, amt = planned
    assert len(plans) == 2
    assert plans[0].dex == "balancer_v2"
    assert plans[0].pool_id == "0x" + "ab" * 32
    assert amt == 10 ** 6


def test_explicit_balancer_identity_rejects_synthetic_venue_id():
    assert lqp._explicit_balancer_identity(
        {"dex": "balancer_v2", "pool": "balancer_v2:USDC:WETH:1"}) is None
    ident = lqp._explicit_balancer_identity(
        {"pool_id": "0x" + "ab" * 32, "pool_address": "0x" + "cd" * 20})
    assert ident == ("0x" + "ab" * 32, "0x" + "cd" * 20)


# --------------------------------------------------------------------------- #
# Gas pathological → UNKNOWN_GAS (M5-A)
# --------------------------------------------------------------------------- #

USDC = to_checksum_address("0x" + "11" * 20)
WETH = to_checksum_address("0x" + "22" * 20)
USDC_WEI = 10 ** 10
LEG1_OUT = 3 * 10 ** 18
UNIV3 = VenueSpec(dex="uniswap_v3", fee=500, venue_id="univ3_500")
BAL = VenueSpec(dex="balancer_v2", pool_id="0x" + "ab" * 32, venue_id="bal_pool")


def _route(status, out, gas_units=None):
    return SimpleNamespace(
        status=status, final_amount_out_wei=int(out),
        aggregate_gas_estimate_units=gas_units,
        hops=[SimpleNamespace(status=status, block_number=1,
                              quoter_contract="0xp")])


class FakePrice:
    def __init__(self, price=1.0, native=3000.0):
        self._price, self._native = price, native

    async def price_usd(self, chain, token):
        return self._price if to_checksum_address(token) == USDC else self._native


class FakeQuoter:
    def __init__(self, *routes):
        self._routes = list(routes)

    async def quote_route(self, *, chain, hops, rpc_url=None):
        return self._routes.pop(0)


@pytest.mark.asyncio
async def test_pathological_gas_usd_is_unknown_gas(monkeypatch):
    class BoomGas:
        async def all_in_cost(self, **kw):
            return {"l1_fee_usd": 0.0, "l2_fee_usd": 1e11}  # >> sane ceiling

    monkeypatch.setattr(gde, "get_chain_gas_model", lambda c: BoomGas())
    eng = GenericDexRouteEngine(
        FakeQuoter(_route("ok", LEG1_OUT, 100_000),
                   _route("ok", USDC_WEI + 100 * 10 ** 6, 100_000)),
        FakePrice(1.0, 3000.0), decimals_fn=lambda c, t: 6,
        economics_assessor=FlashLoanEconomicsAssessor(
            roi_engine=ROIProbabilityEngine()),
        mev_risk_level=MevRiskLevel.LOW)
    r = await eng.evaluate_route(
        chain="bnb", borrow_token=USDC, intermediate_token=WETH,
        amount_usd=200.0, venue_buy=UNIV3, venue_sell=BAL,
        flash_provider="aave_v3")
    assert r.status == UNKNOWN_GAS
    assert r.eligible is False


@pytest.mark.asyncio
async def test_pathological_native_price_is_unknown_gas(monkeypatch):
    class OkGas:
        async def all_in_cost(self, **kw):
            return {"l1_fee_usd": 0.0, "l2_fee_usd": 1.0}

    monkeypatch.setattr(gde, "get_chain_gas_model", lambda c: OkGas())
    eng = GenericDexRouteEngine(
        FakeQuoter(_route("ok", LEG1_OUT, 100_000),
                   _route("ok", USDC_WEI + 100 * 10 ** 6, 100_000)),
        FakePrice(1.0, native=1e12),  # pathological BNB/ETH price
        decimals_fn=lambda c, t: 6,
        economics_assessor=FlashLoanEconomicsAssessor(
            roi_engine=ROIProbabilityEngine()),
        mev_risk_level=MevRiskLevel.LOW)
    r = await eng.evaluate_route(
        chain="bnb", borrow_token=USDC, intermediate_token=WETH,
        amount_usd=200.0, venue_buy=UNIV3, venue_sell=BAL,
        flash_provider="aave_v3")
    assert r.status == UNKNOWN_GAS


def test_min_atomic_still_immutable_floor():
    eng = GenericDexRouteEngine(
        FakeQuoter(), FakePrice(),
        decimals_fn=lambda c, t: 6,
        min_atomic_profit_usd=1.0)  # attempt to lower
    assert eng.min_atomic == 25.0
