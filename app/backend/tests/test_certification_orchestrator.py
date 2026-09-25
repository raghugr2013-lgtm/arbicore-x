"""Deterministic tests for the Certification / Gate Orchestrator.

Offline, no RPC/no server. Proves: gate order + AND-semantics, fail-closed on
absent evidence, circuit-breaker → PAUSED, live transitions never auto-authorised,
minimum-evidence prevents single-green qualification, remediation deny-list,
evidence-ledger records are hashed + machine-readable, and the test-classifier
distinguishes genuine vs stale/env-gated failures using the manifest."""
from arbicore.certification_orchestrator import (
    evaluate_certification, compute_dashboard_state, RemediationPolicy,
    ObservationWindow, ECONOMIC_POLICY,
)
from arbicore.certification_orchestrator.test_classifier import summarize, classify_failures


def _green_g0_g1_evidence():
    return {
        "toolchain": {"forge_available": True},
        "git": {"branch": "cert/vps-current-20260925"},
        "economic_policy": dict(ECONOMIC_POLICY),
        "integrity": {"v1_source_unchanged": True},
        "security": {"violations": 0},
        "tests": {"passed": 128, "genuine_failures": 0},
    }


# ---- gate semantics ----

def test_empty_evidence_is_failclosed_not_eligible():
    r = evaluate_certification({})
    assert r["current_gate"] is None          # not even G0 passes without toolchain
    assert r["live_state"] == "NOT_ELIGIBLE"
    assert r["gates"][0]["verdict"] in ("RED", "UNKNOWN")


def test_g1_green_but_downstream_blocked():
    r = evaluate_certification(_green_g0_g1_evidence())
    gv = {g["gate_id"]: g["verdict"] for g in r["gates"]}
    assert gv["G0_PREFLIGHT"] == "GREEN"
    assert gv["G1_CONFIG_INTEGRITY"] == "GREEN"
    # G2 runtime probe unavailable -> fail-closed, not green.
    assert gv["G2_RUNTIME_LIQUIDITY"] != "GREEN"
    assert r["current_gate"] == "G1_CONFIG_INTEGRITY"
    assert r["live_state"] == "NOT_ELIGIBLE"


def test_economic_drift_trips_circuit_breaker():
    ev = _green_g0_g1_evidence()
    ev["economic_policy"]["min_atomic_profit_usd"] = 5   # someone lowered the floor
    r = evaluate_certification(ev)
    assert r["circuit_breaker"]["tripped"] is True
    assert any(t["kind"] == "economic_policy_violation" for t in r["circuit_breaker"]["trips"])
    assert r["live_state"] == "PAUSED"
    # G1 must be BLOCKED (critical requirement).
    gv = {g["gate_id"]: g["verdict"] for g in r["gates"]}
    assert gv["G1_CONFIG_INTEGRITY"] == "BLOCKED"


def test_security_violation_pauses():
    ev = _green_g0_g1_evidence()
    ev["security"]["violations"] = 1
    r = evaluate_certification(ev)
    assert r["live_state"] == "PAUSED"
    assert any(t["kind"] == "security_invariant_violation" for t in r["circuit_breaker"]["trips"])


def _all_gates_green_evidence():
    ev = _green_g0_g1_evidence()
    ev.update({
        "runtime": {"probe_available": True, "healthy": True},
        "execution_capability": {
            "receiver_deployed": True, "bytecode_verified": True,
            "receiver_version": "v2", "route_executable": True,
        },
        "simulation": {
            "eth_call_available": True, "eth_call_ok": True,
            "fork_available": True, "fork_ok": True, "failure_isolation_proven": True,
        },
        "paper": {"qualifying_observations": 30, "successful_simulations": 30,
                  "economic_violations": 0, "security_violations": 0},
        "evidence_ledger": {"complete": True, "corrupted": False},
    })
    return ev


def test_all_gates_green_reaches_live_eligibility_only():
    r = evaluate_certification(_all_gates_green_evidence())
    assert r["all_technical_gates_green"] is True
    # Without observation windows meeting minimums -> LIVE_ELIGIBILITY, NOT limited-live.
    assert r["live_state"] == "LIVE_ELIGIBILITY"


def test_single_green_cannot_qualify_limited_live():
    # All gates green + a window that has only 1 observation -> still not eligible.
    w = ObservationWindow(label="24h", recommended_hours=24,
                          qualifying_observations=1, successful_simulations=1,
                          evidence_complete=True)
    r = evaluate_certification(_all_gates_green_evidence(), windows={"24h": w})
    assert r["live_state"] == "LIVE_ELIGIBILITY"   # not LIMITED_LIVE_ELIGIBLE


def test_sufficient_evidence_reaches_eligible_but_never_auto_authorized():
    w = ObservationWindow(label="24h", recommended_hours=24,
                          qualifying_observations=25, successful_simulations=25,
                          evidence_complete=True)
    r = evaluate_certification(_all_gates_green_evidence(), windows={"24h": w})
    assert r["live_state"] == "LIMITED_LIVE_ELIGIBLE"
    assert "operator must authorise" in r["authorization_required"]


def test_operator_authorization_advances_but_full_live_needs_more():
    w24 = ObservationWindow(label="24h", recommended_hours=24,
                            qualifying_observations=25, successful_simulations=25,
                            evidence_complete=True)
    r = evaluate_certification(_all_gates_green_evidence(),
                               windows={"24h": w24},
                               authorizations={"limited_live": True})
    assert r["live_state"] == "LIMITED_LIVE_AUTHORIZED"


def test_full_live_requires_72h_evidence_and_authorization():
    w24 = ObservationWindow(label="24h", recommended_hours=24,
                            qualifying_observations=25, successful_simulations=25,
                            evidence_complete=True)
    w72 = ObservationWindow(label="72h", recommended_hours=72,
                            qualifying_observations=120, successful_simulations=120,
                            evidence_complete=True)
    ev = _all_gates_green_evidence()
    ev["limited_live"] = {"executions": 15}
    r = evaluate_certification(ev, windows={"24h": w24, "72h": w72},
                               authorizations={"limited_live": True})
    assert r["live_state"] == "FULL_LIVE_ELIGIBLE"
    r2 = evaluate_certification(ev, windows={"24h": w24, "72h": w72},
                                authorizations={"limited_live": True, "full_live": True})
    assert r2["live_state"] == "FULL_LIVE_AUTHORIZED"


def test_evidence_ledger_records_are_hashed_and_complete():
    r = evaluate_certification(_green_g0_g1_evidence())
    led = r["evidence_ledger"]
    assert len(led) == 6   # one per gate G0..G5
    for rec in led:
        assert rec["record_hash"].startswith("sha256:")
        for key in ("gate_id", "evaluated_at", "result", "requirements",
                    "evidence_snapshot_hash", "previous_gate", "next_eligible_gate",
                    "reason", "orchestrator_version"):
            assert key in rec


def test_evidence_corruption_blocks():
    ev = _all_gates_green_evidence()
    ev["evidence_ledger"] = {"complete": False, "corrupted": True}
    r = evaluate_certification(ev)
    assert r["live_state"] == "PAUSED"
    assert any(t["kind"] == "evidence_corruption" for t in r["circuit_breaker"]["trips"])


# ---- remediation policy ----

def test_remediation_allow_and_deny():
    assert RemediationPolicy.is_allowed("clear_stale_generated_artifacts")
    for forbidden in ("lower_economic_threshold", "enable_live_execution",
                      "allow_unapproved_router", "bypass_simulation",
                      "broadcast_transaction", "deploy_contract"):
        assert not RemediationPolicy.is_allowed(forbidden)


# ---- dashboard state model ----

def test_dashboard_state_exposes_required_fields():
    s = compute_dashboard_state(_green_g0_g1_evidence())
    for key in ("gates", "current_gate", "next_gate", "current_blocker",
                "live_eligibility", "limited_live_eligible", "limited_live_authorized",
                "full_live_eligible", "full_live_authorized", "circuit_breaker_state",
                "evidence_24h", "evidence_72h", "last_certification_run"):
        assert key in s
    assert set(s["gates"].keys()) == {
        "G0_PREFLIGHT", "G1_CONFIG_INTEGRITY", "G2_RUNTIME_LIQUIDITY",
        "G3_EXECUTION_CAPABILITY", "G4_SIMULATION", "G5_PAPER_SHADOW"}


# ---- deterministic test classifier (the 5-way distinction) ----

def test_classifier_distinguishes_stale_and_env_gated_from_genuine():
    failed = [
        "tests/test_executor_registry.py::test_mainnet_not_deployed_fails_closed",  # STALE
        "tests/test_p0d_auto_executor.py::test_something",                          # ENV_GATED (file-level)
        "tests/test_iter17_executor_fork_validation.py::TestForkValidation::test_fork_status",  # UNAVAILABLE
        "tests/test_p0_executor_entrypoint.py::test_build_entrypoint_calldata",     # DEPRECATED
        "tests/test_brand_new_regression.py::test_real_bug",                        # GENUINE (unlisted)
    ]
    out = classify_failures(failed)
    cats = {c["test"].split("::")[0].split("/")[-1]: c["category"] for c in out["classified"]}
    assert cats["test_executor_registry.py"] == "STALE_EXPECTATION"
    assert cats["test_p0d_auto_executor.py"] == "ENV_GATED"
    assert cats["test_iter17_executor_fork_validation.py"] == "UNAVAILABLE_DEPENDENCY"
    assert cats["test_p0_executor_entrypoint.py"] == "DEPRECATED_PATH"
    assert cats["test_brand_new_regression.py"] == "GENUINE_FAILURE"
    # Only the unlisted one counts as a genuine failure.
    assert out["genuine_failures"] == 1


def test_summarize_feeds_engine_green_when_only_nongenuine_failures():
    failed = [
        "tests/test_executor_registry.py::test_mainnet_not_deployed_fails_closed",
        "tests/test_p0d_auto_executor.py::test_x",
    ]
    tests_ev = summarize(passed=128, failed_node_ids=failed)
    assert tests_ev["genuine_failures"] == 0
    ev = _green_g0_g1_evidence()
    ev["tests"] = tests_ev
    r = evaluate_certification(ev)
    gv = {g["gate_id"]: g["verdict"] for g in r["gates"]}
    assert gv["G1_CONFIG_INTEGRITY"] == "GREEN"   # stale/env-gated don't block G1
