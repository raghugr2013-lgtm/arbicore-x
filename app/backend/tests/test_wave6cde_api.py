"""Wave 6C/6D/6E API integration tests via public URL."""
import os
import json
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to reading frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"

FORBIDDEN_PATTERNS = [
    "private_key", "privateKey", "secret_plaintext",
    "signed_tx", "raw_tx",
    "eth_sendTransaction", "eth_sendRawTransaction", "personal_sign",
]


def _assert_invariants(obj, ctx=""):
    """No forbidden strings; would_broadcast, if present, must be False.
    Denylist keys legitimately contain the forbidden RPC method names -- exclude them.
    """
    # Strip out legit denylist/allowlist entries before scanning for forbidden material.
    def strip(x):
        if isinstance(x, dict):
            return {k: (None if k in ("forbidden_rpc_denylist", "read_only_rpc_allowlist") else strip(v))
                    for k, v in x.items()}
        if isinstance(x, list):
            return [strip(i) for i in x]
        return x
    blob = json.dumps(strip(obj))
    for pat in FORBIDDEN_PATTERNS:
        assert pat not in blob, f"Forbidden pattern '{pat}' found in {ctx}"

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "would_broadcast":
                    assert v is False, f"would_broadcast must be False in {ctx}, got {v}"
                walk(v)
        elif isinstance(x, list):
            for item in x:
                walk(item)
    walk(obj)


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ---------------- Wave 6C ----------------

def test_simulation_status(s):
    r = s.get(f"{API}/arbicore/execution/simulation/status", timeout=30)
    assert r.status_code == 200
    data = r.json()
    _assert_invariants(data, "simulation/status")
    assert data.get("default_simulator") == "noop"
    assert "backends" in data and isinstance(data["backends"], list)
    assert "read_only_rpc_allowlist" in data
    assert "forbidden_rpc_denylist" in data
    assert data.get("would_broadcast") is False


def test_gas_estimate(s):
    r = s.get(f"{API}/arbicore/execution/gas?chain=base", timeout=30)
    assert r.status_code == 200
    data = r.json()
    _assert_invariants(data, "gas")
    est = data.get("estimate", data)
    assert est.get("method") in ("rpc_gas_price", "static"), (
        f"Phase 10.10.8: gas oracle should return live 'rpc_gas_price' "
        f"when ARBICORE_RPC_URL is set, or 'static' as safe fallback. Got: {est.get('method')}"
    )
    assert est.get("total_gas_units")
    assert "per_step_cost_wei" in est
    assert "total_cost_usd" in est
    assert "native_price_usd" in est


def test_mev_routers(s):
    r = s.get(f"{API}/arbicore/execution/mev/routers?chain=base", timeout=30)
    assert r.status_code == 200
    data = r.json()
    _assert_invariants(data, "mev/routers")
    assert data.get("default_router") == "public_rpc"
    routers = data.get("routers", [])
    names = [x.get("router") or x.get("name") for x in routers]
    assert "public_rpc" in names
    assert "flashbots_protect" in names
    assert "current_decision" in data
    assert data["current_decision"].get("would_broadcast") is False


# ---------------- Plan build + simulate ----------------
CERT_PAYLOAD = {
    "strategy": "flash_loan_arbitrage",
    "chain": "base",
    "borrow_token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "borrow_amount_wei": 1000000000,
    "borrow_amount_usd": 100.0,
    "flash_loan_provider": "aave_v3",
    "swap_hops": [
        {"dex": "uniswap_v3", "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
         "token_out": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
         "amount_in_wei": 1000000000, "min_amount_out_wei": 999500000, "fee_tier_bps": 5},
        {"dex": "aerodrome", "token_in": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
         "token_out": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
         "amount_in_wei": 999500000, "min_amount_out_wei": 1001000000}
    ],
    "quote_effective_out_wei": 1002000000,
    "expected_net_profit_usd": 5.0
}


@pytest.fixture(scope="session")
def built_plan(s):
    # Wave-6C/D/E simulation + shadow-signer tests assert behaviours only
    # valid when the strategy is in SHADOW mode.  Since Phase 10.10.1
    # lifted the LIMITED_LIVE block on /plans/build, the operator can
    # legitimately have the strategy in LIMITED_LIVE at any time.  Force
    # SHADOW for this fixture's lifetime, then restore.
    prev_mode_resp = s.get(f"{API}/arbicore/execution/mode/flash_loan_arbitrage",
                             timeout=30).json()
    prev_mode = (prev_mode_resp.get("item") or {}).get("mode") or "SHADOW"
    s.post(f"{API}/arbicore/execution/mode/flash_loan_arbitrage",
            json={"to_mode": "SHADOW", "actor": "pytest",
                  "reason": "wave-6cde fixture"}, timeout=30)

    r = s.post(f"{API}/arbicore/execution/plans/build", json=CERT_PAYLOAD, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    _assert_invariants(data, "plans/build")
    plan_id = data.get("plan_id") or (data.get("plan") or {}).get("plan_id") or (data.get("plan") or {}).get("id")
    assert plan_id, f"plan_id missing: {data}"

    yield plan_id, data

    # Restore whatever mode the operator had before the fixture ran.
    if prev_mode and prev_mode != "SHADOW":
        s.post(f"{API}/arbicore/execution/mode/flash_loan_arbitrage",
                json={"to_mode": prev_mode, "actor": "pytest",
                      "reason": "wave-6cde fixture teardown"}, timeout=30)


def test_plan_simulate(s, built_plan):
    plan_id, _ = built_plan
    r = s.post(f"{API}/arbicore/execution/plans/{plan_id}/simulate", json={}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    _assert_invariants(data, "plans/simulate")
    assert data.get("plan_id") == plan_id or "plan_id" in data
    assert data.get("would_broadcast") is False
    sim = data.get("simulation", {})
    assert sim.get("simulator") == "noop"
    assert sim.get("would_broadcast") is False
    gas = data.get("gas_estimate", {})
    assert gas.get("method") in ("rpc_gas_price", "static"), (
        f"Phase 10.10.8: expected live or static gas method. Got: {gas.get('method')}"
    )
    mev = data.get("mev_routing", {})
    assert mev.get("would_broadcast") is False
    assert "slippage" in data


# ---------------- Wave 6D: Capital Policy ----------------

def test_capital_policy_list(s):
    r = s.get(f"{API}/arbicore/execution/capital-policy", timeout=30)
    assert r.status_code == 200
    data = r.json()
    _assert_invariants(data, "capital-policy")
    # Could be list or dict with 'policies'
    policies = data.get("items") if isinstance(data, dict) else data
    if policies is None:
        policies = data if isinstance(data, list) else data.get("policies", [])
    assert len(policies) >= 7, f"Expected >=7 policies, got {len(policies)}"


def test_capital_policy_patch(s):
    r = s.patch(f"{API}/arbicore/execution/capital-policy/flash_loan_arbitrage",
                json={"max_per_plan_usd": 1500}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    _assert_invariants(data, "capital-policy patch")
    # find seeded flag
    policy = data.get("policy", data)
    assert policy.get("max_per_plan_usd") == 1500 or data.get("max_per_plan_usd") == 1500
    seeded = policy.get("seeded", data.get("seeded"))
    assert seeded is False


def test_capital_policy_evaluate(s):
    r = s.post(f"{API}/arbicore/execution/capital-policy/flash_loan_arbitrage/evaluate",
               json={"proposed_usd": 100, "available_liquidity_usd": 10000,
                     "reference_capital_usd": 5000, "expected_net_profit_usd": 5.0},
               timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    _assert_invariants(data, "evaluate")
    assert "binding_constraint" in data or "decision" in data
    d = data.get("decision", data)
    assert "approved" in d
    assert "reasons" in d
    assert d.get("deterministic") is True


# ---------------- Wave 6D: Kill Switch ----------------

def test_kill_switch_flow(s):
    # initial
    r = s.get(f"{API}/arbicore/execution/kill-switch", timeout=30)
    assert r.status_code == 200
    data = r.json()
    _assert_invariants(data, "kill-switch get")
    state = data.get("state", data)
    initial_engaged = state.get("engaged")

    # engage
    r = s.post(f"{API}/arbicore/execution/kill-switch/engage",
               json={"reason": "TEST_engage", "actor": "test_agent"}, timeout=30)
    assert r.status_code == 200, r.text
    _assert_invariants(r.json(), "kill-switch engage")

    r = s.get(f"{API}/arbicore/execution/kill-switch", timeout=30)
    state = r.json().get("state", r.json())
    assert state.get("engaged") is True

    # disengage
    r = s.post(f"{API}/arbicore/execution/kill-switch/disengage",
               json={"reason": "TEST_disengage", "actor": "test_agent"}, timeout=30)
    assert r.status_code == 200, r.text
    _assert_invariants(r.json(), "kill-switch disengage")

    r = s.get(f"{API}/arbicore/execution/kill-switch", timeout=30)
    state = r.json().get("state", r.json())
    assert state.get("engaged") is False

    # audit
    r = s.get(f"{API}/arbicore/execution/kill-switch/audit", timeout=30)
    assert r.status_code == 200
    audit = r.json()
    _assert_invariants(audit, "kill-switch audit")
    entries = audit.get("items", audit.get("entries", audit if isinstance(audit, list) else []))
    blob = json.dumps(entries)
    assert "TEST_engage" in blob
    assert "TEST_disengage" in blob


# ---------------- Wave 6D: Live Signer ----------------

def test_sign_shadow_denied(s, built_plan):
    plan_id, _ = built_plan
    r = s.post(f"{API}/arbicore/execution/plans/{plan_id}/sign", json={}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    _assert_invariants(data, "sign")
    receipt = data.get("receipt", {})
    assert receipt.get("signed") is False
    assert receipt.get("would_broadcast") is False
    gate = receipt.get("gate_ladder", data.get("gate_ladder", {}))
    assert gate.get("mode") == "DENIED"
    reasons = receipt.get("denied_reasons", data.get("denied_reasons", []))
    assert any("mode_gate" in str(x) for x in reasons), f"mode_gate not in {reasons}"


# ---------------- Wave 6E: Certification ----------------

CANONICAL_STAGES = [
    "mode_ladder", "plan_build", "dry_run_economics", "simulation",
    "gas_estimate", "mev_routing", "slippage", "capital_policy",
    "kill_switch", "live_signer", "evidence_hooks"
]


def test_certification_stages(s):
    r = s.get(f"{API}/arbicore/execution/certification/stages", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    _assert_invariants(data, "certification/stages")
    stages = data.get("stages", data)
    names = [x.get("name") if isinstance(x, dict) else x for x in stages]
    for stage in CANONICAL_STAGES:
        assert stage in names, f"Missing stage {stage}. Got: {names}"
    assert data.get("would_broadcast") is False


def test_certification_run(s):
    # bump daily notional to avoid budget block
    s.patch(f"{API}/arbicore/execution/capital-policy/flash_loan_arbitrage",
            json={"daily_notional_usd": 1_000_000}, timeout=30)
    r = s.post(f"{API}/arbicore/execution/certification/run",
               json=CERT_PAYLOAD, timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    _assert_invariants(data, "certification/run")
    report = data.get("report", data)
    assert report.get("would_broadcast") is False
    assert report.get("plan_id")
    stages = report.get("stages", [])
    names = [x.get("stage") or x.get("name") if isinstance(x, dict) else x for x in stages]
    for stage in CANONICAL_STAGES:
        assert stage in names, f"Missing stage {stage} in run. Got: {names}"
    assert "ladder_defaults" in report or "ladder_defaults" in data
    ld = report.get("ladder_defaults") or data.get("ladder_defaults")
    assert ld and "mode" in ld
    verdict = report.get("verdict")
    assert verdict in ("PASS", "WAIT", "BLOCKED"), verdict


# ---------------- Backward compat ----------------

def test_bc_mode(s):
    r = s.get(f"{API}/arbicore/execution/mode", timeout=30)
    assert r.status_code == 200
    _assert_invariants(r.json(), "mode")


def test_bc_wallets(s):
    r = s.get(f"{API}/arbicore/execution/wallets", timeout=30)
    assert r.status_code == 200
    _assert_invariants(r.json(), "wallets")


def test_bc_secrets_status(s):
    r = s.get(f"{API}/arbicore/execution/secrets/status", timeout=30)
    assert r.status_code == 200
    _assert_invariants(r.json(), "secrets/status")


def test_bc_adapters(s):
    r = s.get(f"{API}/arbicore/execution/adapters", timeout=30)
    assert r.status_code == 200
    _assert_invariants(r.json(), "adapters")


def test_bc_plans_list(s):
    r = s.get(f"{API}/arbicore/execution/plans", timeout=30)
    assert r.status_code == 200
    _assert_invariants(r.json(), "plans")
