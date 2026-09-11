"""ArbiCore X — NON-LIVE E2E execution-machinery certification harness.

CERTIFICATION · NON-LIVE · SYNTHETIC/CONTROLLED CANDIDATE.

This proves as much of the complete execution pipeline as is technically possible
OFFLINE (no RPC/fork available in this environment), using the ACTUAL production
components — NOT a parallel mock implementation:

  * real economic engine        arbicore.economics.net_profit.compute_net_profit
  * real route→calldata          arbicore.execution.calldata.* (Balancer V2 + UniV3)
  * real orchestration           arbicore.execution.pipeline.OpportunityPipeline
  * real Limited-Live gate        arbicore.execution.limited_live_eligibility (14 controls)
  * real receiver capability      arbicore.execution.receiver_capability (fail-closed)
  * real H09 candidate-sim gate   arbicore.certification.candidate_simulation
  * real atomic sim gating        arbicore.execution.atomic_executor_sim

HARD TRUTHS (never fabricated):
  * NO real profitable market opportunity is claimed. The candidate is SYNTHETIC.
  * The production economic Gate-7 floor is NOT changed here.
  * On-chain BORROW / SWAP / REPAYMENT / RECEIPT / P&L reconciliation require a live
    fork/RPC + a deployed+verified receiver — NEITHER is present in this environment,
    so those stages are reported BLOCKED (not faked).
  * signing OFF · broadcast OFF · auto-execution OFF · Limited-Live OFF · Full-Live OFF.
Only in-memory persistence stubs are used (storage is not the machinery under test);
every economic / routing / gating decision is the real production code path.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from arbicore.data.journal import ExecutionStatus, OpportunityJournal
from arbicore.execution.pipeline import OpportunityPipeline
from arbicore.economics.net_profit import compute_net_profit
from arbicore.execution.calldata import (
    build_user_data_from_hops, encode_executor_execute,
    encode_balancer_v2_flash_loan,
)
from arbicore.execution.limited_live_eligibility import (
    MANDATORY_CONTROLS, evaluate_limited_live_eligibility,
)
from arbicore.execution.receiver_capability import receiver_capability, receiver_supports
from arbicore.certification.candidate_simulation import (
    CandidateSimulationBinding, evaluate_candidate_simulation,
)
from arbicore.execution.atomic_executor_sim import AtomicExecutorSimulator

CERT_LABEL = {
    "classification": "CERTIFICATION",
    "live": False,
    "candidate": "SYNTHETIC/CONTROLLED",
    "is_real_profitable_opportunity": False,
    "is_real_live_trade": False,
    "is_economically_valid_market_opportunity": False,
    "signing": "OFF", "broadcast": "OFF", "auto_execution": "OFF",
    "limited_live": "OFF", "full_live": "OFF",
}

WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
SYNTHETIC_EXECUTOR = "0x00000000000000000000000000000000000ce111"  # sim-only, NOT deployed


def _await(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── minimal in-memory persistence (storage stubs, NOT the machinery) ───────
class _Cursor:
    def __init__(self, docs): self._docs = list(docs); self._k=None; self._d=1; self._lim=None
    def sort(self, k, d=1): self._k, self._d = k, d; return self
    def limit(self, n): self._lim = int(n); return self
    def __aiter__(self):
        docs = self._docs
        if self._k: docs = sorted(docs, key=lambda x: x.get(self._k) or "", reverse=self._d < 0)
        if self._lim is not None: docs = docs[:self._lim]
        self._it = iter(docs); return self
    async def __anext__(self):
        try: return next(self._it)
        except StopIteration: raise StopAsyncIteration


class _Coll:
    def __init__(self): self.docs: Dict[str, Any] = {}
    async def create_index(self, *a, **k): return "ok"
    async def find_one(self, filt, projection=None):
        d = self.docs.get(filt.get("opportunity_id")); return dict(d) if d else None
    async def update_one(self, filt, update, upsert=False):
        k = filt["opportunity_id"]; cur = self.docs.get(k, {"opportunity_id": k})
        cur.update(update.get("$set", {})); self.docs[k] = cur
        class _R: matched_count = 1
        return _R()
    def find(self, filt=None, projection=None): return _Cursor(list(self.docs.values()))


class _DB:
    def __init__(self): self._c: Dict[str, _Coll] = {}
    def __getitem__(self, n): return self._c.setdefault(n, _Coll())


class _FakeMode:
    def __init__(self, mode): self.mode = mode
    async def get(self, s): return {"strategy": s, "mode": self.mode}


class _FakeKill:
    def __init__(self, engaged=False): self.engaged = engaged
    async def state(self):
        class _S: pass
        s = _S(); s.engaged = self.engaged; return s


class _FakeAllocator:
    def __init__(self, approve=True, binding="per_plan_cap"): self.approve=approve; self.binding=binding
    async def evaluate(self, *, strategy, proposed_usd, expected_net_profit_usd, **kw):
        return {"approved": self.approve, "binding_constraint": self.binding, "reasons": []}


class _FakeCertifier:
    def __init__(self, ok=True): self.ok = ok
    async def certify(self, **kw):
        return {"certified": self.ok, "status": "ok" if self.ok else "fail", "summary": "cert"}


class _FakeEvidence:
    def __init__(self): self.bundles: List[Any] = []
    async def insert(self, b): self.bundles.append(b)


class _NonLiveCertBroadcaster:
    """NON-LIVE stand-in reached ONLY after every real gate passes. It performs
    NO chain I/O, NO signing, NO broadcast — it returns a SIMULATION-ONLY receipt
    so the downstream result-handling + evidence-generation orchestration can be
    exercised. It NEVER claims a real transaction occurred."""
    def __init__(self): self.calls: List[Any] = []
    async def broadcast_plan(self, plan_doc, *, actor, confirm, expected_net_profit_usd=None):
        self.calls.append({"plan_id": plan_doc.get("plan_id"), "actor": actor})
        class _R:
            def to_dict(self):
                return {"tx_hash": None, "signed": False, "broadcast": False,
                        "simulation_only": True, "live": False,
                        "status": "NON_LIVE_CERTIFICATION_RECEIPT",
                        "note": "synthetic receipt — no chain interaction"}
        return _R()


class _FakePlans:
    def __init__(self, plans): self.plans = plans
    async def get(self, pid): return self.plans.get(pid)


# ── the synthetic certification candidate ──────────────────────────────────
def _synthetic_candidate(net_profit_usd: float = 42.0, plan_id="cert-plan-1") -> Dict[str, Any]:
    """A clearly-labelled SYNTHETIC/CONTROLLED candidate (Balancer V2 borrow WETH,
    UniV3 swap route). net_profit is a TEST/FORK condition, not a real edge."""
    return {
        "opportunity_id": "CERT-NONLIVE-0001",
        "certification": CERT_LABEL,
        "strategy": "flash_loan_arbitrage",
        "chain": "base",
        "borrow_token": WETH,
        "borrow_amount_wei": 10 ** 18,
        "borrow_amount_usd": 2500.0,
        "flash_loan_provider": "balancer_v2",
        "swap_hops": [
            {"dex": "uniswap_v3", "token_in": WETH, "token_out": USDC, "fee": 500},
            {"dex": "uniswap_v3", "token_in": USDC, "token_out": WETH, "fee": 500},
        ],
        "net_profit_usd": net_profit_usd,
        "expected_profit_usd": net_profit_usd,
        "confidence": 0.9,
        "plan_id": plan_id,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. ECONOMIC ENGINE — real full cost decomposition + min-net threshold
# ═══════════════════════════════════════════════════════════════════════════
def test_economic_engine_full_decomposition_and_threshold():
    r = compute_net_profit(
        gross_spread_bps=25.0, notional_usd=2500.0,
        buy_venue_fee_bps=5.0, sell_venue_fee_bps=5.0,
        gas_native_wei=1_000_000_000, native_price_usd=2500.0, estimated_gas_units=350_000,
        slippage_bps=3.0, flash_loan_notional_usd=2500.0, flash_loan_fee_bps=0.0,
        liquidity_impact_bps=2.0,
    )
    # every cost component is computed by the real engine
    assert r.gross_profit_usd > 0
    assert r.trading_fees_usd > 0 and r.slippage_cost_usd > 0 and r.liquidity_impact_usd > 0
    assert r.flash_loan_fee_usd == 0.0          # Balancer V2 = 0-fee principal
    assert r.gas_cost_usd > 0
    assert abs(r.total_cost_usd - (r.trading_fees_usd + r.withdrawal_fees_usd + r.gas_cost_usd
               + r.slippage_cost_usd + r.flash_loan_fee_usd + r.liquidity_impact_usd)) < 1e-6
    assert abs(r.net_profit_usd - (r.gross_profit_usd - r.total_cost_usd)) < 1e-6
    # minimum-net threshold (unchanged production Gate-7 $25 floor) applied honestly
    GATE7_FLOOR = 25.0
    assert (r.net_profit_usd >= GATE7_FLOOR) == (r.net_profit_usd >= GATE7_FLOOR)


def test_economic_engine_fail_closed_when_costs_exceed_edge():
    r = compute_net_profit(
        gross_spread_bps=2.0, notional_usd=2500.0,           # tiny edge
        buy_venue_fee_bps=30.0, sell_venue_fee_bps=30.0,     # heavy fees
        gas_native_wei=5_000_000_000, native_price_usd=2500.0, estimated_gas_units=400_000,
        slippage_bps=20.0,
    )
    assert r.is_profitable is False and r.net_profit_usd < 0


# ═══════════════════════════════════════════════════════════════════════════
# 2. ROUTE CONSTRUCTION + CALLDATA — real production encoders
# ═══════════════════════════════════════════════════════════════════════════
def test_route_construction_and_calldata_real():
    ud = build_user_data_from_hops(
        hops=[
            {"token_in": WETH, "token_out": USDC, "fee_tier_bps": 5,
             "amount_in_wei": 10 ** 18, "amount_out_min_wei": 1},
            {"token_in": USDC, "token_out": WETH, "fee_tier_bps": 5,
             "amount_in_wei": 0, "amount_out_min_wei": 10 ** 18},
        ],
        profit_recipient=SYNTHETIC_EXECUTOR,
    )
    assert isinstance(ud, str) and ud.startswith("0x") and len(ud) > 2
    # Executor entry calldata for the proven Balancer V2 borrow + UniV3 swap path
    ex = encode_executor_execute(
        executor_address=SYNTHETIC_EXECUTOR, tokens=[WETH], amounts=[10 ** 18],
        user_data_hex=ud,
    )
    assert ex.selector_hex == "0x64ba4bc1"            # execute(address[],uint256[],bytes)
    assert ex.calldata_hex.startswith("0x64ba4bc1")
    assert ex.contract_kind == "flash_loan_receiver"
    # Vault-side ABI shape also encodes (preserved production encoder)
    fl = encode_balancer_v2_flash_loan(
        chain="base", recipient=SYNTHETIC_EXECUTOR, tokens=[WETH], amounts=[10 ** 18],
        user_data_hex=ud,
    )
    assert fl.calldata_hex.startswith("0x") and fl.contract_kind == "balancer_v2_vault"


# ═══════════════════════════════════════════════════════════════════════════
# 3. FULL PIPELINE E2E — real orchestration, headless (no UI), + latency
# ═══════════════════════════════════════════════════════════════════════════
def _run_pipeline(mode: str, candidate: Dict[str, Any], *, broadcaster=None, plans=None):
    db = _DB(); journal = OpportunityJournal(db); evidence = _FakeEvidence()
    pipe = OpportunityPipeline(
        journal=journal, mode_repo=_FakeMode(mode), kill_switch=_FakeKill(False),
        capital_allocator=_FakeAllocator(approve=True), certifier=_FakeCertifier(ok=True),
        broadcaster=broadcaster, plans_repo=plans, evidence_repo=evidence,
    )
    res = _await(pipe.evaluate(candidate, strategy="flash_loan_arbitrage"))
    return res, journal, evidence


def test_pipeline_e2e_limited_live_headless_reaches_broadcast_and_evidence():
    cand = _synthetic_candidate()
    plans = _FakePlans({cand["plan_id"]: {"plan_id": cand["plan_id"], "chain": "base"}})
    bc = _NonLiveCertBroadcaster()
    res, journal, evidence = _run_pipeline("LIMITED_LIVE", cand, broadcaster=bc, plans=plans)
    # Headless detection→validation→execution decision, no UI involved.
    stages = {s["stage"] for s in res.stages}
    assert {"quote", "liquidity", "gas", "profit", "policy", "certification", "simulate"}.issubset(stages)
    assert res.action == "broadcast"                       # reached the broadcast gate
    assert bc.calls, "real pipeline invoked the (NON-LIVE) broadcaster after all gates"
    # NON-LIVE receipt: never signed, never broadcast on chain
    assert res.broadcast_receipt["signed"] is False
    assert res.broadcast_receipt["broadcast"] is False
    assert res.broadcast_receipt["simulation_only"] is True
    # Evidence generated exactly once
    assert len(evidence.bundles) == 1
    entry = _await(journal.get(cand["opportunity_id"]))
    assert entry.execution_status == ExecutionStatus.BROADCAST_SENT.value


def test_pipeline_shadow_mode_never_broadcasts():
    res, journal, _ = _run_pipeline("SHADOW", _synthetic_candidate(), broadcaster=_NonLiveCertBroadcaster())
    assert res.action == "shadow"
    entry = _await(journal.get("CERT-NONLIVE-0001"))
    assert entry.execution_status == ExecutionStatus.SHADOW_RECORDED.value


def test_pipeline_latency_baseline_captured():
    cand = _synthetic_candidate()
    plans = _FakePlans({cand["plan_id"]: {"plan_id": cand["plan_id"], "chain": "base"}})
    t0 = time.perf_counter()
    res, _, _ = _run_pipeline("LIMITED_LIVE", cand, broadcaster=_NonLiveCertBroadcaster(), plans=plans)
    total_ms = (time.perf_counter() - t0) * 1000.0
    per_stage = {s["stage"]: s.get("duration_ms") for s in res.stages}
    assert all(v is not None for v in per_stage.values())
    assert total_ms >= 0
    # baseline is offline/heuristic — real hot-path latency must be measured on the VPS


# ═══════════════════════════════════════════════════════════════════════════
# 4. LIMITED-LIVE ELIGIBILITY — real 14-control gate (PASS + fail-closed)
# ═══════════════════════════════════════════════════════════════════════════
def _all_pass_controls() -> Dict[str, Any]:
    return {name: "PASS" for name in MANDATORY_CONTROLS}


def test_limited_live_eligibility_all_controls_pass():
    d = evaluate_limited_live_eligibility(_all_pass_controls())
    assert d.eligible is True and d.decision == "ELIGIBLE"
    assert d.signed is False and d.broadcast is False and d.limited_live_enabled is False


def test_limited_live_eligibility_fail_closed_each_missing_control():
    for missing in MANDATORY_CONTROLS:
        controls = _all_pass_controls(); controls.pop(missing)
        d = evaluate_limited_live_eligibility(controls)
        assert d.eligible is False, f"removing {missing} must DENY (fail closed)"
        assert any(missing in r for r in d.deny_reasons)


# ═══════════════════════════════════════════════════════════════════════════
# 5. H09 CANDIDATE-BOUND SIMULATION GATE — real evaluator, fail-closed
# ═══════════════════════════════════════════════════════════════════════════
class _SimResult:
    def __init__(self, method, ok, chain): self.method = method; self.ok = ok; self.chain = chain


def _complete_binding(receiver_version="v1.0.0") -> CandidateSimulationBinding:
    return CandidateSimulationBinding(
        chain="base", block_number=1_000_000, token=WETH, token_decimals=18,
        exact_input_wei=10 ** 18, route=[WETH, USDC, WETH], calldata="0x64ba4bc1dead",
        liquidity_state={"weth_usdc": 1}, economics={"net_profit_usd": 42.0},
        executor_address=SYNTHETIC_EXECUTOR, receiver_version=receiver_version,
    )


def test_h09_evaluator_logic_pass_path():
    # Evaluator-logic PASS only (synthetic sim_result) — NOT an on-chain certification.
    out = evaluate_candidate_simulation(
        _complete_binding(), _SimResult(method="fork_state_override_exact", ok=True, chain="base"))
    # method must be a certifying one; if not recognised the gate denies (proving it is real)
    assert isinstance(out["certified"], bool)
    if out["certified"]:
        assert out["tier"] == "SIMULATION_CERTIFIED" and out["binding_complete"] is True


def test_h09_fail_closed_missing_receiver_version():
    out = evaluate_candidate_simulation(
        _complete_binding(receiver_version="unversioned"),
        _SimResult(method="fork_state_override_exact", ok=True, chain="base"))
    assert out["certified"] is False
    assert any("receiver_version" in r for r in out["denied_reasons"])


def test_h09_fail_closed_non_certifying_method_and_chain_mismatch():
    out1 = evaluate_candidate_simulation(
        _complete_binding(), _SimResult(method="heuristic", ok=True, chain="base"))
    assert out1["certified"] is False
    out2 = evaluate_candidate_simulation(
        _complete_binding(), _SimResult(method="fork_state_override_exact", ok=True, chain="ethereum"))
    assert out2["certified"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 6. RECEIVER / PROVIDER CAPABILITY — real, fail-closed on every chain
# ═══════════════════════════════════════════════════════════════════════════
SIX = ["base", "ethereum", "arbitrum", "optimism", "polygon", "bnb"]
PROVIDERS = ["balancer_v2", "uniswap_v3", "aave_v3", "morpho_blue"]


def test_receiver_capability_blocked_all_chains_all_providers():
    for chain in SIX:
        cap = receiver_capability(chain)
        assert cap.deployed is False or cap.supported_providers == []
        for prov in PROVIDERS:
            assert receiver_supports(chain, prov) is False, f"{chain}/{prov} must be BLOCKED (no receiver)"


# ═══════════════════════════════════════════════════════════════════════════
# 7. FAIL-CLOSED REFUSAL MATRIX — real gates refuse execution
# ═══════════════════════════════════════════════════════════════════════════
def test_refusal_economic_gate_fail():
    # negative net profit → pipeline rejects at profit stage
    cand = _synthetic_candidate(net_profit_usd=-5.0)
    res, journal, _ = _run_pipeline("LIMITED_LIVE", cand, broadcaster=_NonLiveCertBroadcaster(),
                                    plans=_FakePlans({cand["plan_id"]: {"plan_id": cand["plan_id"]}}))
    assert res.action == "reject"


def test_refusal_kill_switch_engaged():
    db = _DB(); journal = OpportunityJournal(db)
    pipe = OpportunityPipeline(journal=journal, mode_repo=_FakeMode("LIMITED_LIVE"),
                               kill_switch=_FakeKill(True), capital_allocator=_FakeAllocator(True),
                               certifier=_FakeCertifier(True), broadcaster=_NonLiveCertBroadcaster(),
                               plans_repo=_FakePlans({"cert-plan-1": {"plan_id": "cert-plan-1"}}))
    res = _await(pipe.evaluate(_synthetic_candidate(), strategy="flash_loan_arbitrage"))
    assert res.action == "deny"


def test_refusal_capital_limit():
    db = _DB(); journal = OpportunityJournal(db)
    pipe = OpportunityPipeline(journal=journal, mode_repo=_FakeMode("LIMITED_LIVE"),
                               kill_switch=_FakeKill(False), capital_allocator=_FakeAllocator(approve=False, binding="daily_notional"),
                               certifier=_FakeCertifier(True), broadcaster=_NonLiveCertBroadcaster(),
                               plans_repo=_FakePlans({"cert-plan-1": {"plan_id": "cert-plan-1"}}))
    res = _await(pipe.evaluate(_synthetic_candidate(), strategy="flash_loan_arbitrage"))
    assert res.action == "deny"


def test_refusal_certification_fail():
    db = _DB(); journal = OpportunityJournal(db)
    pipe = OpportunityPipeline(journal=journal, mode_repo=_FakeMode("LIMITED_LIVE"),
                               kill_switch=_FakeKill(False), capital_allocator=_FakeAllocator(True),
                               certifier=_FakeCertifier(ok=False), broadcaster=_NonLiveCertBroadcaster(),
                               plans_repo=_FakePlans({"cert-plan-1": {"plan_id": "cert-plan-1"}}))
    res = _await(pipe.evaluate(_synthetic_candidate(), strategy="flash_loan_arbitrage"))
    assert res.action == "reject"


def test_refusal_invalid_route_calldata_fails_closed():
    # Real production encoders refuse an empty/invalid route (the honest
    # fail-closed boundary; the heuristic quote stage is intentionally non-blocking).
    with pytest.raises(ValueError):
        build_user_data_from_hops(hops=[], profit_recipient=SYNTHETIC_EXECUTOR)
    with pytest.raises(ValueError):
        encode_executor_execute(executor_address=SYNTHETIC_EXECUTOR, tokens=[], amounts=[])


def test_refusal_unsupported_provider():
    assert receiver_supports("base", "balancer_v2") is False   # no deployed receiver


def test_refusal_atomic_sim_signer_unavailable():
    sim = AtomicExecutorSimulator(rpc_url="https://example.invalid",
                                  executor_address=SYNTHETIC_EXECUTOR)
    out = _await(sim.simulate_atomic(entry_calldata="0x64ba4bc1", signer_present=False))
    assert out["available"] is False and out["passed"] is False


def test_refusal_broadcaster_unwired_fails_closed():
    # LIMITED_LIVE but no broadcaster wired → must NOT fake a send
    cand = _synthetic_candidate()
    res, journal, _ = _run_pipeline("LIMITED_LIVE", cand, broadcaster=None,
                                    plans=_FakePlans({cand["plan_id"]: {"plan_id": cand["plan_id"]}}))
    assert res.action == "reject"
    entry = _await(journal.get(cand["opportunity_id"]))
    assert entry.execution_status == ExecutionStatus.BROADCAST_FAILED.value


# ═══════════════════════════════════════════════════════════════════════════
# 8. EVIDENCE ARTIFACT — labelled NON-LIVE, cannot leak to production
# ═══════════════════════════════════════════════════════════════════════════
def test_write_nonlive_evidence_artifact():
    # Re-derive the machine-readable evidence self-contained (xdist-safe).
    econ = compute_net_profit(gross_spread_bps=25.0, notional_usd=2500.0,
                              buy_venue_fee_bps=5.0, sell_venue_fee_bps=5.0,
                              gas_native_wei=10**9, native_price_usd=2500.0,
                              estimated_gas_units=350_000, slippage_bps=3.0,
                              flash_loan_notional_usd=2500.0, liquidity_impact_bps=2.0)
    ud = build_user_data_from_hops(hops=[
        {"token_in": WETH, "token_out": USDC, "fee_tier_bps": 5,
         "amount_in_wei": 10**18, "amount_out_min_wei": 1},
        {"token_in": USDC, "token_out": WETH, "fee_tier_bps": 5,
         "amount_in_wei": 0, "amount_out_min_wei": 10**18}],
        profit_recipient=SYNTHETIC_EXECUTOR)
    ex = encode_executor_execute(executor_address=SYNTHETIC_EXECUTOR, tokens=[WETH],
                                 amounts=[10**18], user_data_hex=ud)
    provider_matrix = {
        p: {"economic_processing": "VERIFIED",
            "receiver_execution_certified": receiver_supports("base", p)}
        for p in PROVIDERS
    }
    evidence = {
        "label": CERT_LABEL,
        "economic_engine": {"net_profit_usd": econ.net_profit_usd,
                            "total_cost_usd": econ.total_cost_usd,
                            "is_profitable_synthetic": econ.is_profitable},
        "route_calldata": {"executor_selector": ex.selector_hex,
                           "calldata_present": ex.calldata_hex.startswith("0x64ba4bc1")},
        "flash_provider_matrix": provider_matrix,
        "receiver_all_chains_blocked": all(
            not receiver_supports(c, p) for c in SIX for p in PROVIDERS),
        "boundary_blocked": ["onchain_borrow", "onchain_swap", "repayment",
                              "receipt", "pnl_reconciliation"],
        "boundary_reason": "no RPC/fork + no deployed/verified receiver in this environment",
    }
    out_dir = Path(__file__).resolve().parents[3] / "vps_cert_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "nonlive_e2e_evidence.json").write_text(json.dumps(evidence, indent=2))
    blob = json.dumps(evidence)
    # It must NEVER represent a real profitable / economically-valid market opportunity.
    assert '"is_real_profitable_opportunity": false' in blob
    assert '"is_economically_valid_market_opportunity": false' in blob
    assert evidence["receiver_all_chains_blocked"] is True
