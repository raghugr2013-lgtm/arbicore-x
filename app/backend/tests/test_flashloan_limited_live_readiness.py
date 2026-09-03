"""Limited-Live readiness controls — executor capability, borrow sizing, and
the single fail-closed Limited-Live eligibility decision (+ bundle mapping).

Covers mission test matrix sections B, C, D, F and the CONFIRMED != EXECUTABLE
invariant. Offline/deterministic; no RPC, no signing, no broadcast.
"""
from __future__ import annotations

from arbicore.execution.limited_live_eligibility import (
    MANDATORY_CONTROLS, evaluate_limited_live_eligibility,
)
from arbicore.scanners.flash_loan_arbitrage.borrow_sizing import (
    BorrowSizeEval, select_borrow_size,
)
from arbicore.scanners.flash_loan_arbitrage.executor_capability import (
    ExecutorCapabilityStatus, evaluate_executor_capability,
)
from arbicore.scanners.flash_loan_arbitrage.executor_capability import (
    ExecutorCapability,
)
from arbicore.scanners.flash_loan_arbitrage.provider_liquidity import (
    ProviderLiquidity, ProviderStatus,
)
from arbicore.scanners.flash_loan_arbitrage.readiness_assessment import (
    ReadinessControls, assess_candidate_readiness,
)


# ---------------------------------------------------------------------------
# D. Executor capability
# ---------------------------------------------------------------------------

_UNIV3 = {"p1": {"dex": "uniswap_v3"}, "p2": {"dex": "uniswap_v3"}}


def test_executor_capability_supported():
    cap = evaluate_executor_capability(route_pools=["p1", "p2"], pool_specs=_UNIV3)
    assert cap.status == ExecutorCapabilityStatus.SUPPORTED and cap.is_supported


def test_executor_capability_unsupported_aerodrome():
    specs = {"p1": {"dex": "uniswap_v3"}, "p2": {"dex": "aerodrome"}}
    cap = evaluate_executor_capability(route_pools=["p1", "p2"], pool_specs=specs)
    assert cap.status == ExecutorCapabilityStatus.UNSUPPORTED
    assert cap.unsupported_pools == ["p2"] and not cap.is_supported


def test_executor_capability_unverifiable_missing_metadata():
    specs = {"p1": {"dex": "uniswap_v3"}}          # p2 absent
    cap = evaluate_executor_capability(route_pools=["p1", "p2"], pool_specs=specs)
    assert cap.status == ExecutorCapabilityStatus.UNVERIFIABLE
    assert cap.unverifiable_pools == ["p2"]


def test_executor_capability_unverifiable_empty_route():
    cap = evaluate_executor_capability(route_pools=[], pool_specs={})
    assert cap.status == ExecutorCapabilityStatus.UNVERIFIABLE


# ---------------------------------------------------------------------------
# B. Borrow sizing
# ---------------------------------------------------------------------------

def _feasible(size, net):
    return BorrowSizeEval(size_usd=size, net_profit_usd=net, quote_complete=True,
                          economics_ok=True, liquidity_sufficient=True,
                          executor_supported=True, atomic_sim_passed=True)


def test_borrow_sizing_selects_most_profitable_feasible():
    d = select_borrow_size([_feasible(10_000, 40.0), _feasible(50_000, 120.0),
                            _feasible(100_000, 90.0)])
    assert d.ok and d.selected.size_usd == 50_000


def test_borrow_sizing_rejects_unprofitable():
    e = _feasible(10_000, -5.0)          # negative net -> not feasible
    d = select_borrow_size([e])
    assert not d.ok and d.status == "INFEASIBLE"


def test_borrow_sizing_rejects_liquidity_limited():
    e = _feasible(10_000, 40.0)
    e.liquidity_sufficient = False
    assert not select_borrow_size([e]).ok


def test_borrow_sizing_rejects_executor_limited():
    e = _feasible(10_000, 40.0)
    e.executor_supported = False
    assert not select_borrow_size([e]).ok


def test_borrow_sizing_rejects_sim_failed():
    e = _feasible(10_000, 40.0)
    e.atomic_sim_passed = False
    assert not select_borrow_size([e]).ok


def test_borrow_sizing_rejects_missing_sizes():
    assert not select_borrow_size([]).ok


def test_borrow_sizing_rejects_none_net_profit():
    e = _feasible(10_000, None)          # missing net -> fail closed
    assert not select_borrow_size([e]).ok


# ---------------------------------------------------------------------------
# F. Limited-Live eligibility (single fail-closed decision)
# ---------------------------------------------------------------------------

def _all_pass():
    return {
        "quote_complete": True, "economics_ok": True, "gate_7": "PASS",
        "liquidity_verified": "PASS", "gate_8": "PASS",
        "executor_capability": "SUPPORTED", "gate_9": "PASS",
        "borrow_size_feasible": True, "balancer_liquidity": "ON_CHAIN_CONFIRMED",
        "atomic_simulation": True, "freshness_ok": True,
        "provenance_complete": True, "verification_confirmed": True,
        "mode_allows": True, "kill_switch_ok": True,
    }


def test_eligibility_all_controls_pass():
    d = evaluate_limited_live_eligibility(_all_pass())
    assert d.eligible and d.decision == "ELIGIBLE" and d.deny_reasons == []
    assert d.signed is False and d.broadcast is False
    assert d.limited_live_enabled is False


def test_eligibility_denies_when_any_single_control_fails():
    for name in MANDATORY_CONTROLS:
        c = _all_pass()
        c[name] = "FAIL" if isinstance(c[name], str) else False
        d = evaluate_limited_live_eligibility(c)
        assert not d.eligible, f"{name} failing must DENY"
        assert any(name in r for r in d.deny_reasons)


def test_eligibility_denies_when_any_control_missing():
    for name in MANDATORY_CONTROLS:
        c = _all_pass()
        c.pop(name)
        d = evaluate_limited_live_eligibility(c)
        assert not d.eligible
        assert any(name in r and "missing" in r for r in d.deny_reasons)


def test_eligibility_denies_on_unknown_values():
    for name, bad in (("executor_capability", "UNVERIFIABLE"),
                      ("balancer_liquidity", "UNKNOWN"),
                      ("gate_8", "NOT_EVALUATED"),
                      ("atomic_simulation", None)):
        c = _all_pass()
        c[name] = bad
        assert not evaluate_limited_live_eligibility(c).eligible


def test_confirmed_alone_is_not_executable():
    # Only verification_confirmed passes; every execution proof is missing.
    c = {k: (False if k != "verification_confirmed" else True)
         for k in MANDATORY_CONTROLS}
    d = evaluate_limited_live_eligibility(c)
    assert not d.eligible
    # The execution-proof controls must all be denied.
    denied = {r.split(":")[0] for r in d.deny_reasons}
    for proof in ("atomic_simulation", "balancer_liquidity", "executor_capability",
                  "borrow_size_feasible"):
        assert proof in denied


# ---------------------------------------------------------------------------
# Bundle mapping (readiness_assessment) — CONFIRMED bundle -> eligibility
# ---------------------------------------------------------------------------

def _confirmed_bundle():
    return {
        "bundle_id": "b1", "source_component": "flash_loan_arb_verifier",
        "verification_status": "CONFIRMED", "input_amount_usd": 10_000.0,
        "route": {"route_pools": ["p1", "p2"]},
        "quotes": {"route_quote_status": "ok", "gross_profit_pct": 2.0},
        "economics": {"atomic_profit_usd": 42.0},
        "gates": {"gate_7": {"status": "PASS"}, "gate_8": {"status": "PASS"},
                  "gate_9": {"status": "PASS"}},
        "diagnostics": {"audit_run_id": "RUN-A", "scanner_tick_id": 3,
                        "worker_id": "w1", "candidate_id": "cand-1"},
    }


def _cap_supported():
    return ExecutorCapability(status=ExecutorCapabilityStatus.SUPPORTED,
                              supported_pools=["p1", "p2"], unsupported_pools=[],
                              unverifiable_pools=[], reason="ok")


def _bal_confirmed():
    return ProviderLiquidity(provider="balancer_v2", chain="base",
                             status=ProviderStatus.ON_CHAIN_CONFIRMED,
                             fee_bps=0, liquidity_usd=5_000_000.0,
                             reason="confirmed")


def test_readiness_bundle_all_controls_present_is_eligible():
    controls = ReadinessControls(
        executor_capability=_cap_supported(), balancer_liquidity=_bal_confirmed(),
        borrow_size=select_borrow_size([_feasible(10_000, 42.0)]),
        atomic_sim={"available": True, "passed": True, "block_tag": "latest"},
        freshness_ok=True, mode_allows=True, kill_switch_ok=True)
    r = assess_candidate_readiness(_confirmed_bundle(), controls)
    assert r["limited_live"]["eligible"] is True
    assert r["provenance"]["audit_run_id"] == "RUN-A"
    assert r["signed"] is False and r["broadcast"] is False


def test_readiness_bundle_denies_without_atomic_sim():
    controls = ReadinessControls(
        executor_capability=_cap_supported(), balancer_liquidity=_bal_confirmed(),
        borrow_size=select_borrow_size([_feasible(10_000, 42.0)]),
        atomic_sim={"available": False, "passed": False, "reason": "no executor"},
        freshness_ok=True, mode_allows=True, kill_switch_ok=True)
    r = assess_candidate_readiness(_confirmed_bundle(), controls)
    assert r["limited_live"]["eligible"] is False
    assert any("atomic_simulation" in x for x in r["limited_live"]["deny_reasons"])


def test_readiness_bundle_denies_unverified_liquidity_and_unfetched_controls():
    # Default ReadinessControls = all fail-closed (unfetched) -> DENY.
    r = assess_candidate_readiness(_confirmed_bundle(), ReadinessControls())
    assert r["limited_live"]["eligible"] is False
    denied = {x.split(":")[0] for x in r["limited_live"]["deny_reasons"]}
    assert {"balancer_liquidity", "atomic_simulation", "executor_capability",
            "borrow_size_feasible", "freshness_ok", "mode_allows",
            "kill_switch_ok"} <= denied


def test_readiness_bundle_aerodrome_route_denied():
    b = _confirmed_bundle()
    cap = ExecutorCapability(status=ExecutorCapabilityStatus.UNSUPPORTED,
                             supported_pools=["p1"], unsupported_pools=["p2"],
                             unverifiable_pools=[], reason="aerodrome")
    controls = ReadinessControls(
        executor_capability=cap, balancer_liquidity=_bal_confirmed(),
        borrow_size=select_borrow_size([_feasible(10_000, 42.0)]),
        atomic_sim={"available": True, "passed": True}, freshness_ok=True,
        mode_allows=True, kill_switch_ok=True)
    r = assess_candidate_readiness(b, controls)
    assert r["limited_live"]["eligible"] is False
    assert any("executor_capability" in x for x in r["limited_live"]["deny_reasons"])
