"""Wave 6C · Unit tests — Gas Oracle, Slippage Estimator, MEV Registry,
SimulationRegistry (Noop path).  Fully offline / deterministic — no
Mongo or HTTP contact required."""
from __future__ import annotations

import asyncio

import pytest

from arbicore.execution.gas import (
    DEFAULT_GAS_UNITS, GasEstimate, RpcGasOracle, StaticGasOracle,
)
from arbicore.execution.slippage import SlippageEstimator
from arbicore.execution.mev import (
    FlashbotsRouter, MevRouterRegistry, PublicRpcRouter, RoutingDecision,
)
from arbicore.execution.simulation import (
    EthCallSimulator, FORBIDDEN_RPC_METHODS, NoopSimulator, READ_ONLY_RPC_METHODS,
    SimulationRegistry, SimulationResult,
)


# ---------------------------------------------------------------------------
# Gas Oracle
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


class TestStaticGasOracle:
    def test_estimate_shape(self):
        oracle = StaticGasOracle(default_gwei=0.1, priority_gwei=0.01,
                                  native_price_usd=2000.0)
        est = _run(oracle.estimate(chain="base",
                                     step_kinds=["borrow", "swap", "repay", "profit"]))
        assert isinstance(est, GasEstimate)
        assert est.provider == "static_gas_oracle"
        assert est.total_gas_units == sum(DEFAULT_GAS_UNITS[k] for k in
                                            ("borrow", "swap", "repay", "profit"))
        assert est.total_cost_wei == est.total_gas_units * est.gas_price_wei
        assert est.total_cost_usd is not None
        assert est.method == "static"

    def test_estimate_deterministic(self):
        oracle = StaticGasOracle()
        a = _run(oracle.estimate(chain="base", step_kinds=["borrow", "swap", "repay"]))
        b = _run(oracle.estimate(chain="base", step_kinds=["borrow", "swap", "repay"]))
        assert a.total_cost_wei == b.total_cost_wei
        assert a.total_gas_units == b.total_gas_units

    def test_unknown_kind_falls_back(self):
        oracle = StaticGasOracle()
        est = _run(oracle.estimate(chain="base", step_kinds=["unknown_kind"]))
        # Falls back to 100_000 units.
        assert est.total_gas_units == 100_000


class TestRpcGasOracleFallback:
    def test_disabled_when_no_url(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
        oracle = RpcGasOracle(rpc_url=None)
        assert oracle.is_available() is False

    def test_estimate_falls_back_to_static_when_disabled(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
        oracle = RpcGasOracle(rpc_url=None)
        est = _run(oracle.estimate(chain="base",
                                     step_kinds=["borrow", "swap", "repay", "profit"]))
        # Fallback returns a StaticGasOracle estimate.
        assert est.method == "static"
        assert est.provider == "static_gas_oracle"


# ---------------------------------------------------------------------------
# Slippage
# ---------------------------------------------------------------------------

class TestSlippageEstimator:
    def test_deterministic_default_midpoint(self):
        s = SlippageEstimator()
        r = s.estimate(quoted_output_wei=1_000_000_000, hops=1)
        assert r.deterministic is True
        assert r.method == "band_midpoint"
        # Midpoint of default band is (0.003+0.006)/2 = 0.0045.
        assert r.aggregate_slippage_bps == 45

    def test_multiplicative_aggregation(self):
        s = SlippageEstimator()
        one = s.estimate(quoted_output_wei=1_000_000_000, hops=1)
        two = s.estimate(quoted_output_wei=1_000_000_000, hops=2)
        # 2-hop slippage must be strictly greater than 1-hop.
        assert two.aggregate_slippage > one.aggregate_slippage
        # Never exceeds 1.0
        assert two.aggregate_slippage <= 1.0

    def test_explicit_per_hop(self):
        s = SlippageEstimator()
        r = s.estimate(quoted_output_wei=1_000_000, hops=2,
                       per_hop_slippage=[0.01, 0.02])
        assert r.method == "explicit_per_hop"
        expected = 1.0 - (1 - 0.01) * (1 - 0.02)
        assert abs(r.aggregate_slippage - expected) < 1e-6

    def test_padding_and_trimming(self):
        s = SlippageEstimator()
        r_pad = s.estimate(quoted_output_wei=1_000_000, hops=3,
                            per_hop_slippage=[0.01])
        assert len(r_pad.per_hop_slippage) == 3
        r_trim = s.estimate(quoted_output_wei=1_000_000, hops=1,
                             per_hop_slippage=[0.01, 0.02, 0.03])
        assert len(r_trim.per_hop_slippage) == 1

    def test_invalid_band(self):
        with pytest.raises(ValueError):
            SlippageEstimator(min_slippage=0.5, max_slippage=0.1)


# ---------------------------------------------------------------------------
# MEV Router Registry
# ---------------------------------------------------------------------------

class TestMevRegistry:
    def test_default_router_public(self):
        reg = MevRouterRegistry()
        assert reg.default == "public_rpc"
        cat = reg.catalog()
        assert cat["would_broadcast"] is False
        assert any(r["router"] == "flashbots_protect" for r in cat["routers"])

    def test_route_default(self):
        reg = MevRouterRegistry()
        dec = _run(reg.route(chain="base"))
        assert isinstance(dec, RoutingDecision)
        assert dec.would_broadcast is False
        assert dec.router == "public_rpc"

    def test_flashbots_supports_only_ethereum(self):
        reg = MevRouterRegistry()
        # Chain=base but router=flashbots → registry falls back to default.
        dec = _run(reg.route(router="flashbots_protect", chain="base"))
        # Falls back to public_rpc because flashbots is ethereum-only.
        assert dec.router == "public_rpc"

    def test_flashbots_on_ethereum_returns_private(self):
        reg = MevRouterRegistry()
        dec = _run(reg.route(router="flashbots_protect", chain="ethereum"))
        assert dec.router == "flashbots_protect"
        assert dec.private is True
        assert "sandwich" in dec.protects_against

    def test_serialisation_invariant(self):
        reg = MevRouterRegistry()
        dec = _run(reg.route(chain="base"))
        d = dec.to_dict()
        assert d["would_broadcast"] is False


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def _sample_plan():
    return {
        "plan_id": "plan-test",
        "strategy": "flash_loan_arbitrage",
        "chain": "base",
        "steps": [
            {"step_index": 0, "kind": "borrow", "provider": "aave_v3"},
            {"step_index": 1, "kind": "swap",   "provider": "uniswap_v3"},
            {"step_index": 2, "kind": "swap",   "provider": "aerodrome"},
            {"step_index": 3, "kind": "repay",  "provider": "aave_v3"},
            {"step_index": 4, "kind": "profit", "provider": "reconciler"},
        ],
    }


class TestNoopSimulator:
    def test_simulate_shape(self):
        sim = NoopSimulator()
        r = _run(sim.simulate(_sample_plan()))
        assert isinstance(r, SimulationResult)
        assert r.simulator == "noop"
        assert r.ok is True
        assert r.would_broadcast is False
        assert len(r.steps) == 5
        for s in r.steps:
            assert s.ok is True
            assert s.method == "noop"

    def test_no_rpc_methods(self):
        sim = NoopSimulator()
        r = _run(sim.simulate(_sample_plan()))
        assert r.rpc_methods_called == []


class TestEthCallSimulatorFallback:
    def test_falls_back_to_noop_when_disabled(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
        sim = EthCallSimulator(rpc_url=None)
        assert sim.is_available() is False
        r = _run(sim.simulate(_sample_plan()))
        assert r.would_broadcast is False
        assert r.fallback_reason == "rpc_url not configured"
        assert r.method == "fallback_noop"

    def test_refuses_forbidden_rpc_method(self):
        sim = EthCallSimulator(rpc_url="http://127.0.0.1:1")
        for method in ("eth_sendTransaction", "eth_sendRawTransaction",
                       "eth_sign", "personal_sign"):
            with pytest.raises(PermissionError):
                _run(sim._rpc(method))


class TestSimulationRegistry:
    def test_default_noop(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_SIMULATOR", raising=False)
        reg = SimulationRegistry()
        assert reg.default == "noop"

    def test_simulate_dispatches_and_asserts_invariant(self):
        reg = SimulationRegistry()
        r = _run(reg.simulate(_sample_plan()))
        assert r.would_broadcast is False
        d = r.to_dict()
        assert d["would_broadcast"] is False
        for m in d["rpc_methods_called"]:
            assert m in READ_ONLY_RPC_METHODS

    def test_status_exposes_allowlists(self):
        reg = SimulationRegistry()
        st = reg.status()
        assert "eth_call" in st["read_only_rpc_allowlist"]
        assert "eth_sendTransaction" in st["forbidden_rpc_denylist"]
        assert st["would_broadcast"] is False
