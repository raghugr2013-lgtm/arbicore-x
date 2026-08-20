"""P0 — Opportunity decision path + /control/decide-opportunity endpoint.

Two layers:
  * PURE unit tests over ``decide_opportunity`` / ``run_simulation_gate``
    (EV, confidence v2, adaptive size, hard gate, rejection, evidence
    penalty, invalid input).
  * HTTP integration tests over ``POST /api/arbicore/control/decide-opportunity``
    (auth, kill-switch override, live-mode restriction, no-broadcast/no-sign
    side effects). Runs against the live preview URL (cookie auth).
"""
import os
import json
import copy

import pytest
import requests

from arbicore.economics.opportunity_decision import (
    run_simulation_gate, decide_opportunity, SimulationGateResult,
    OpportunityDecision,
)

# --------------------------------------------------------------------------- #
# Shared fixtures / constants
# --------------------------------------------------------------------------- #
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"

OP_USER = os.environ.get("ARBICORE_ADMIN_USER_TEST", "operator")
OP_PASS = os.environ.get("ARBICORE_ADMIN_PASS_TEST", "ShadowOperator!2026")

UNIV3 = "0x2626664c2603336E57B271c5C0b26F421741e481"
AERO = "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43"
WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

ROUTER_ALLOW = [UNIV3, AERO]
TOKEN_ALLOW = [WETH, USDC]

FORBIDDEN = ["private_key", "signed_tx", "raw_tx",
             "eth_sendTransaction", "eth_sendRawTransaction", "personal_sign"]


def _healthy_opp():
    return {
        "opportunity_id": "opp-healthy",
        "gross_spread_bps": 45,
        "pool_liquidity_usd": 3_000_000,
        "gas_cost_usd": 3.0,
        "flash_loan_fee_bps": 0,
        "flash_loan_provider": "balancer_v2",
        "quote_status": "REAL",
        "quote_age_sec": 2,
        "gas_certainty": 0.9,
        "mev_risk": 0.1,
        "expected_slippage_bps": 20,
        "repayment_ok": True,
        "calldata_hex": "0xabcd",
        "buy_venue_fee_bps": 5,
        "sell_venue_fee_bps": 5,
        "native_price_usd": 3000,
        "max_hops": 3,
        "hops": [
            {"router": UNIV3, "token_in": WETH, "token_out": USDC,
             "amount_out_min_wei": 123},
            {"router": AERO, "token_in": USDC, "token_out": WETH,
             "amount_out_min_wei": 456},
        ],
    }


# --------------------------------------------------------------------------- #
# PURE — simulation gate
# --------------------------------------------------------------------------- #
def test_gate_passes_on_healthy_opportunity():
    r = run_simulation_gate(_healthy_opp(), router_allowlist=ROUTER_ALLOW,
                            token_allowlist=TOKEN_ALLOW)
    assert isinstance(r, SimulationGateResult)
    assert r.passed is True
    assert r.failures == []
    assert all(r.checks.values())


def test_gate_rejects_stale_quote():
    opp = _healthy_opp()
    opp["quote_status"] = "STALE"
    r = run_simulation_gate(opp, router_allowlist=ROUTER_ALLOW,
                            token_allowlist=TOKEN_ALLOW)
    assert r.passed is False
    assert "quote_fresh" in r.failures


def test_gate_rejects_non_allowlisted_router():
    opp = _healthy_opp()
    opp["hops"][0]["router"] = "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    r = run_simulation_gate(opp, router_allowlist=ROUTER_ALLOW,
                            token_allowlist=TOKEN_ALLOW)
    assert r.passed is False
    assert "router_allowlisted" in r.failures


def test_gate_rejects_zero_min_output():
    opp = _healthy_opp()
    opp["hops"][0]["amount_out_min_wei"] = 0
    r = run_simulation_gate(opp, router_allowlist=ROUTER_ALLOW,
                            token_allowlist=TOKEN_ALLOW)
    assert r.passed is False
    assert "min_output_nonzero" in r.failures


def test_gate_rejects_missing_calldata():
    opp = _healthy_opp()
    opp.pop("calldata_hex", None)
    opp.pop("user_data_hex", None)
    r = run_simulation_gate(opp, router_allowlist=ROUTER_ALLOW,
                            token_allowlist=TOKEN_ALLOW)
    assert r.passed is False
    assert "calldata_present" in r.failures


def test_gate_rejects_bad_provider():
    opp = _healthy_opp()
    opp["flash_loan_provider"] = "shady_lender"
    r = run_simulation_gate(opp, router_allowlist=ROUTER_ALLOW,
                            token_allowlist=TOKEN_ALLOW)
    assert r.passed is False
    assert "provider_ok" in r.failures


# --------------------------------------------------------------------------- #
# PURE — full decision path (EV + confidence + size optimizer wiring)
# --------------------------------------------------------------------------- #
def test_decision_healthy_is_executable_candidate():
    d = decide_opportunity(_healthy_opp(), router_allowlist=ROUTER_ALLOW,
                           token_allowlist=TOKEN_ALLOW)
    assert isinstance(d, OpportunityDecision)
    assert d.would_execute is True
    assert d.expected_value_usd > 0
    assert d.optimal_notional_usd is not None
    assert 0 <= d.confidence <= 100
    # size optimizer must have run and chosen the max-EV feasible size
    assert d.size_optimization["chosen"] is not None
    # confidence explainability surfaces components
    assert d.confidence_components["components"]


def test_decision_ev_reflects_net_and_probability():
    d = decide_opportunity(_healthy_opp(), router_allowlist=ROUTER_ALLOW,
                           token_allowlist=TOKEN_ALLOW)
    ev = d.ev
    assert ev["success_probability"] + ev["failure_probability"] == pytest.approx(1.0, abs=1e-6)
    assert ev["net_profit_usd"] >= 0


def test_decision_simulation_failure_forces_rejection():
    opp = _healthy_opp()
    opp["quote_status"] = "STALE"          # breaks the hard gate
    d = decide_opportunity(opp, router_allowlist=ROUTER_ALLOW,
                           token_allowlist=TOKEN_ALLOW)
    assert d.would_execute is False
    assert d.simulation["passed"] is False
    assert "simulation gate failed" in d.reason


def test_decision_confidence_never_overrides_failed_gate():
    """Even with pristine confidence signals, a failed gate => not executable."""
    opp = _healthy_opp()
    opp["hops"][0]["amount_out_min_wei"] = 0   # hard gate failure
    opp["gas_certainty"] = 1.0
    opp["mev_risk"] = 0.0
    opp["historical_success_rate"] = 1.0
    d = decide_opportunity(opp, router_allowlist=ROUTER_ALLOW,
                           token_allowlist=TOKEN_ALLOW)
    assert d.would_execute is False


def test_decision_unprofitable_spread_rejected():
    opp = _healthy_opp()
    opp["gross_spread_bps"] = 1          # too small to cover fees + gas
    opp["gas_cost_usd"] = 40.0
    d = decide_opportunity(opp, router_allowlist=ROUTER_ALLOW,
                           token_allowlist=TOKEN_ALLOW)
    assert d.would_execute is False
    assert d.expected_value_usd <= 0 or d.optimal_notional_usd is None


def test_decision_missing_evidence_lowers_confidence_vs_full():
    full = decide_opportunity(_healthy_opp(), router_allowlist=ROUTER_ALLOW,
                              token_allowlist=TOKEN_ALLOW)
    sparse_opp = _healthy_opp()
    for k in ("gas_certainty", "mev_risk", "quote_age_sec"):
        sparse_opp.pop(k, None)
    sparse = decide_opportunity(sparse_opp, router_allowlist=ROUTER_ALLOW,
                                token_allowlist=TOKEN_ALLOW)
    # missing signals must show up as reported missing factors / uncertainty
    assert sparse.ev["uncertainty_penalty"] >= full.ev["uncertainty_penalty"]
    assert len(sparse.confidence_components["missing_factors"]) >= \
        len(full.confidence_components["missing_factors"])


def test_decision_empty_opportunity_is_not_executable():
    d = decide_opportunity({}, router_allowlist=ROUTER_ALLOW,
                           token_allowlist=TOKEN_ALLOW)
    assert d.would_execute is False
    assert d.simulation["passed"] is False


def test_decision_output_is_json_serializable_and_clean():
    d = decide_opportunity(_healthy_opp(), router_allowlist=ROUTER_ALLOW,
                           token_allowlist=TOKEN_ALLOW)
    blob = json.dumps(d.to_dict())
    for pat in FORBIDDEN:
        assert pat not in blob


# --------------------------------------------------------------------------- #
# HTTP — endpoint auth + safety overrides + no side effects
# --------------------------------------------------------------------------- #
def _login():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login",
               json={"username": OP_USER, "password": OP_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def session():
    return _login()


def test_endpoint_requires_auth():
    r = requests.post(f"{API}/arbicore/control/decide-opportunity",
                      json={"opportunity": _healthy_opp()}, timeout=30)
    assert r.status_code == 401


def test_endpoint_rejects_missing_opportunity(session):
    r = session.post(f"{API}/arbicore/control/decide-opportunity",
                     json={}, timeout=30)
    assert r.status_code == 422


def test_endpoint_healthy_decision(session):
    r = session.post(f"{API}/arbicore/control/decide-opportunity",
                     json={"opportunity": _healthy_opp()}, timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body["execution_performed"] is False
    assert body["shadow_safe"] is True
    assert body["data_source"] == "OPERATOR_SUPPLIED"
    assert body["mode"] in ("SHADOW", "PAPER", "PROFIT_ENGINE")
    assert body["decision"]["would_execute"] is True
    # no signing/broadcast material leaks anywhere in the payload
    blob = json.dumps(body)
    for pat in FORBIDDEN:
        assert pat not in blob


def test_endpoint_kill_switch_forces_not_executable(session):
    # engage kill switch
    er = session.post(f"{API}/arbicore/execution/kill-switch/engage",
                      json={"reason": "unit-test decide-opportunity"}, timeout=30)
    assert er.status_code == 200 and er.json().get("ok") is True
    try:
        r = session.post(f"{API}/arbicore/control/decide-opportunity",
                         json={"opportunity": _healthy_opp()}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["kill_switch_engaged"] is True
        assert body["decision"]["would_execute"] is False
        assert "kill switch" in body["decision"]["reason"].lower()
    finally:
        dr = session.post(f"{API}/arbicore/execution/kill-switch/disengage",
                          json={"reason": "unit-test cleanup"}, timeout=30)
        assert dr.status_code == 200 and dr.json().get("ok") is True


def test_endpoint_never_enables_live_mode(session):
    """The endpoint cannot flip to a broadcast mode; and if the system were
    ever in a live mode, decisions must be blocked. We assert the mode stays
    shadow-safe and execution is never performed."""
    r = session.post(f"{API}/arbicore/control/decide-opportunity",
                     json={"opportunity": _healthy_opp()}, timeout=30)
    body = r.json()
    assert body["mode"] not in ("LIMITED_LIVE", "FULL_AUTOMATION")
    assert body["execution_performed"] is False
