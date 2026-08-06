"""v2.11.8 · Paper Validation Framework — Slice B unit tests.

Covers:
  * Liquidity check stage: threshold + hop-index reporting.
  * Simulation providers: HeuristicSimulator + EthCallSimulator +
    SimulationRouter env-based selection.
  * Pipeline integration: liquidity + simulate stages appear, fail
    paths route to LIQUIDITY_FAILURE / SIMULATION_FAILURE, and
    ``simulation_backend`` is persisted on the EvidenceBundle.
"""
from __future__ import annotations

import asyncio
import os

import pytest

from arbicore.paper import (
    EthCallSimulator,
    HeuristicSimulator,
    InMemoryPaperEvidenceRepository,
    LiquidityCheckResult,
    PaperOutcome,
    SimulationBackend,
    SimulationResult,
    SimulationRouter,
    check_liquidity,
)
from arbicore.execution.pipeline import OpportunityPipeline


class _NoopJournal:
    async def record_discovery(self, *a, **k): pass
    async def record_event(self, *a, **k): pass


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Liquidity check
# ---------------------------------------------------------------------------
class TestLiquidityCheck:
    def test_no_hops_permissive(self):
        r = check_liquidity({"swap_hops": [], "borrow_amount_usd": 1000})
        assert r.ok

    def test_no_borrow_amount_skipped(self):
        r = check_liquidity({"swap_hops": [{"pool_liquidity_usd": 1}]})
        assert r.ok
        assert "borrow amount not specified" in r.detail

    def test_no_liquidity_annotation_skipped(self):
        r = check_liquidity({"swap_hops": [{"dex": "uni-v3"}],
                              "borrow_amount_usd": 1000})
        assert r.ok
        assert "no hops carried pool_liquidity_usd" in r.detail
        assert r.skipped_hops == 1
        assert r.checked_hops == 0

    def test_all_hops_pass(self):
        r = check_liquidity({
            "swap_hops": [
                {"pool_liquidity_usd": 100_000},
                {"pool_liquidity_usd": 200_000},
            ],
            "borrow_amount_usd": 1000,
        })
        assert r.ok
        assert r.checked_hops == 2
        assert r.min_ratio_seen == 100.0  # 100_000 / 1000

    def test_under_liquid_hop_fails(self):
        r = check_liquidity({
            "swap_hops": [
                {"pool_liquidity_usd": 10_000},  # 10x ok
                {"pool_liquidity_usd": 500},     # under 5x
            ],
            "borrow_amount_usd": 1000,
        })
        assert not r.ok
        assert r.failing_hop_index == 1
        assert "hop #1" in r.detail

    def test_custom_safety_ratio(self):
        # 2x ratio — 500 USD is >= 2*100 = 200, ok.
        r = check_liquidity({
            "swap_hops": [{"pool_liquidity_usd": 500}],
            "borrow_amount_usd": 100,
        }, safety_ratio=2.0)
        assert r.ok
        # 6x ratio — 500 USD < 6*100 = 600 → fail.
        r = check_liquidity({
            "swap_hops": [{"pool_liquidity_usd": 500}],
            "borrow_amount_usd": 100,
        }, safety_ratio=6.0)
        assert not r.ok


# ---------------------------------------------------------------------------
# HeuristicSimulator
# ---------------------------------------------------------------------------
class TestHeuristicSimulator:
    def test_backend_name(self):
        assert HeuristicSimulator.name == "heuristic"

    def test_conforms_to_protocol(self):
        # Runtime check — HeuristicSimulator must satisfy the Protocol.
        assert isinstance(HeuristicSimulator(), SimulationBackend)

    def test_rejects_short_calldata(self):
        h = HeuristicSimulator()
        r = _run(h.simulate(chain="base", to="0x" + "01" * 20,
                             data="0x", from_="0x" + "02" * 20))
        assert not r.ok
        assert "selector" in r.detail

    def test_rejects_zero_to(self):
        h = HeuristicSimulator()
        r = _run(h.simulate(chain="base", to="0x" + "00" * 20,
                             data="0xdeadbeef", from_="0x" + "02" * 20))
        assert not r.ok
        assert "address" in r.detail

    def test_rejects_error_selector(self):
        h = HeuristicSimulator()
        r = _run(h.simulate(chain="base", to="0x" + "01" * 20,
                             data="0x08c379a0" + "00" * 32,
                             from_="0x" + "02" * 20))
        assert not r.ok
        assert r.revert_selector == "0x08c379a0"

    def test_passes_valid_calldata(self):
        h = HeuristicSimulator()
        r = _run(h.simulate(chain="base", to="0x" + "01" * 20,
                             data="0x64ba4bc1" + "00" * 32,
                             from_="0x" + "02" * 20))
        assert r.ok
        assert r.backend == "heuristic"


# ---------------------------------------------------------------------------
# EthCallSimulator
# ---------------------------------------------------------------------------
class TestEthCallSimulator:
    def test_supports_only_configured_chains(self):
        e = EthCallSimulator({"base": "https://example.invalid"})
        assert e.supports("base")
        assert not e.supports("arbitrum")

    def test_no_rpc_returns_fail(self):
        e = EthCallSimulator({})  # nothing configured
        r = _run(e.simulate(chain="base", to="0x" + "01" * 20,
                             data="0xdeadbeef", from_="0x" + "02" * 20))
        assert not r.ok
        assert "no RPC configured" in r.detail


# ---------------------------------------------------------------------------
# SimulationRouter env-based selection
# ---------------------------------------------------------------------------
class TestSimulationRouter:
    def test_from_env_without_rpc_uses_heuristic(self, monkeypatch):
        monkeypatch.delenv("BASE_RPC_URL", raising=False)
        monkeypatch.delenv("BASE_SEPOLIA_RPC_URL", raising=False)
        r = SimulationRouter.from_env()
        # Force route via public interface — call `simulate` on any chain,
        # expect heuristic (no eth_call configured).
        res = _run(r.simulate(chain="base", to="0x" + "01" * 20,
                               data="0x64ba4bc1" + "00" * 32,
                               from_="0x" + "02" * 20))
        assert res.backend == "heuristic"

    def test_from_env_with_rpc_prefers_eth_call(self, monkeypatch):
        # Point at an unreachable RPC to force an eth_call *failure*,
        # but critically the router should still SELECT the eth_call
        # backend. Backend name is recorded on the (failed) result.
        monkeypatch.setenv("BASE_RPC_URL",
                            "http://localhost:1/definitely-not-a-node")
        r = SimulationRouter.from_env()
        res = _run(r.simulate(chain="base", to="0x" + "01" * 20,
                               data="0x64ba4bc1" + "00" * 32,
                               from_="0x" + "02" * 20))
        assert res.backend == "eth_call"


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------
class TestPipelineSliceB:
    def _pipeline(self, repo=None, sim=None):
        return OpportunityPipeline(journal=_NoopJournal(),
                                   evidence_repo=repo,
                                   simulator=sim)

    def test_liquidity_failure_short_circuits(self):
        async def _r():
            repo = InMemoryPaperEvidenceRepository()
            p = self._pipeline(repo)
            r = await p.evaluate({
                "opportunity_id": "opp-lf",
                "swap_hops": [{"dex": "uni-v3", "pool_liquidity_usd": 100}],
                "borrow_amount_usd": 1000,
                "expected_profit_usd": 50.0,
            })
            assert r.outcome == "LIQUIDITY_FAILURE"
            # Downstream stages (gas/profit/policy/…) should NOT run.
            stage_names = [s["stage"] for s in r.stages]
            assert "liquidity" in stage_names
            assert "simulate" not in stage_names
            assert "gas" not in stage_names
        _run(_r())

    def test_simulate_stage_records_backend_on_evidence(self):
        """Executable path: sim stage runs, sim_backend persisted on the bundle."""
        async def _r():
            repo = InMemoryPaperEvidenceRepository()
            p = self._pipeline(repo)
            r = await p.evaluate({
                "opportunity_id": "opp-sim-ok",
                "swap_hops": [{"dex": "uni-v3", "pool_liquidity_usd": 100_000}],
                "borrow_amount_usd": 1000,
                "expected_profit_usd": 50.0,
                "strategy": "flash_loan_arbitrage",
            })
            assert r.outcome == "EXECUTABLE"
            b = await repo.get_by_validation_id(r.validation_id)
            assert b.simulation_backend in ("heuristic", "eth_call")
        _run(_r())

    def test_simulate_failure_classified(self):
        """Force a SIMULATION_FAILURE by injecting a fake simulator."""
        class _AlwaysFailSim:
            async def simulate(self, **k):
                return SimulationResult(ok=False, backend="test_fail",
                                         detail="forced fail")
        async def _r():
            repo = InMemoryPaperEvidenceRepository()
            p = self._pipeline(repo, sim=_AlwaysFailSim())
            r = await p.evaluate({
                "opportunity_id": "opp-sim-fail",
                "swap_hops": [{"dex": "uni-v3", "pool_liquidity_usd": 100_000}],
                "borrow_amount_usd": 1000,
                "expected_profit_usd": 50.0,
            })
            assert r.outcome == "SIMULATION_FAILURE"
            b = await repo.get_by_validation_id(r.validation_id)
            assert b.simulation_backend == "test_fail"
        _run(_r())

    def test_liquidity_stage_appears_in_stages_list(self):
        async def _r():
            p = self._pipeline()
            r = await p.evaluate({
                "opportunity_id": "opp-liq-stage",
                "swap_hops": [{"dex": "uni-v3"}],   # no liquidity annotation
                "expected_profit_usd": 50.0,
            })
            names = [s["stage"] for s in r.stages]
            assert "liquidity" in names
            # Stage timing captured for the liquidity stage.
            liq_stage = next(s for s in r.stages if s["stage"] == "liquidity")
            assert "started_at" in liq_stage
            assert "duration_ms" in liq_stage
        _run(_r())

    def test_backward_compat_no_simulator_kwarg(self):
        """Constructing OpportunityPipeline WITHOUT `simulator` still works."""
        async def _r():
            p = OpportunityPipeline(journal=_NoopJournal())
            r = await p.evaluate({
                "opportunity_id": "opp-bc",
                "swap_hops": [{"dex": "uni-v3"}],
                "expected_profit_usd": 50.0,
            })
            assert r.outcome == "EXECUTABLE"
        _run(_r())
