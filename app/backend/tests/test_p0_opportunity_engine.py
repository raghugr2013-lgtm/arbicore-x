"""P0 — Autonomous Opportunity Engine: discovery, classification, scan, matrix.

PURE tests exercise route enumeration + classification (no RPC). HTTP tests
drive the live read-only Base scan, evidence history and readiness matrix.
"""
import os
import json

import pytest
import requests

from arbicore.economics.opportunity_engine import OpportunityEngine, classify_route
from arbicore.discovery.base_venues import build_pool_graph, TOKENS, BORROW_TOKENS

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"
OP_USER, OP_PASS = "operator", "ShadowOperator!2026"

FORBIDDEN = ["private_key", "signed_tx", "raw_tx",
             "eth_sendTransaction", "eth_sendRawTransaction", "personal_sign"]


class _FakeQuoter:
    def _rpc_url(self):
        return None


# ------------------------------------------------------------- discovery
def test_pool_graph_builds_from_verified_tokens():
    pools, specs = build_pool_graph()
    assert pools and specs
    # every pool node maps to a venue spec with a dex
    for p in pools:
        assert p.pool_address in specs
        assert "dex" in specs[p.pool_address]


def test_enumerate_routes_covers_multiple_opportunity_types():
    eng = OpportunityEngine(quoter_registry=_FakeQuoter())
    routes = eng.enumerate_routes()
    assert routes, "expected non-empty route enumeration"
    types = {classify_route(r) for r in routes}
    # discovery must surface cross-DEX and multi-token cycles
    assert "cross_dex" in types or "same_dex_fee_tier" in types
    assert any(t in types for t in ("triangular", "stablecoin_triangular", "multi_hop"))
    # every cycle closes on its borrow token
    for r in routes:
        assert r.token_path[0] == r.borrow_token
        assert r.token_path[-1] == r.borrow_token
        assert r.borrow_token in BORROW_TOKENS


def test_classify_route_labels():
    eng = OpportunityEngine(quoter_registry=_FakeQuoter())
    routes = eng.enumerate_routes()
    two_hop = [r for r in routes if r.hop_count == 2]
    three_hop = [r for r in routes if r.hop_count == 3]
    assert two_hop and all(
        classify_route(r) in ("same_dex_fee_tier", "cross_dex") for r in two_hop)
    if three_hop:
        assert all(classify_route(r) in
                   ("triangular", "stablecoin_triangular", "multi_hop")
                   for r in three_hop)


# ------------------------------------------------------------------ HTTP
def _login():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"username": OP_USER, "password": OP_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def session():
    return _login()


def test_scan_once_requires_auth():
    r = requests.post(f"{API}/arbicore/engine/scan-once", json={"limit": 2}, timeout=30)
    assert r.status_code == 401


def test_scan_once_runs_full_chain_and_persists(session):
    r = session.post(f"{API}/arbicore/engine/scan-once", json={"limit": 5}, timeout=90)
    assert r.status_code == 200
    body = r.json()
    assert body["execution_performed"] is False
    assert body["shadow_safe"] is True
    assert body["routes_enumerated"] > 0
    assert body["routes_evaluated"] >= 1
    # each opportunity carries the full decision + provenance
    for o in body["opportunities"]:
        assert o["opportunity_type"] in (
            "same_dex_fee_tier", "cross_dex", "triangular",
            "stablecoin_triangular", "multi_hop")
        assert o["quote_provenance"]["quote_status"] in ("REAL", "STALE", "UNAVAILABLE")
        assert "would_execute" in o and "expected_value_usd" in o
        assert "simulation" in o["decision"] and "ev" in o["decision"]
    blob = json.dumps(body)
    for pat in FORBIDDEN:
        assert pat not in blob


def test_history_and_opportunities_populated(session):
    session.post(f"{API}/arbicore/engine/scan-once", json={"limit": 4}, timeout=90)
    h = session.get(f"{API}/arbicore/engine/history?limit=20", timeout=30)
    assert h.status_code == 200
    hb = h.json()
    assert hb["count"] >= 1
    assert hb["stats"]["total"] >= 1
    rec = hb["history"][0]
    for k in ("route_id", "opportunity_type", "quote_status", "gross_spread_bps",
              "net_profit_usd", "confidence", "expected_value_usd",
              "simulation_passed", "would_execute", "reason"):
        assert k in rec
    o = session.get(f"{API}/arbicore/engine/opportunities?limit=10", timeout=30)
    assert o.status_code == 200 and o.json()["count"] >= 1


def test_readiness_matrix_authoritative(session):
    r = session.get(f"{API}/arbicore/engine/readiness-matrix", timeout=30)
    assert r.status_code == 200
    m = r.json()
    assert m["overall_status"] in ("RED", "YELLOW", "GREEN")
    caps = {c["capability"]: c for c in m["capabilities"]}
    for req in ("CONFIGURATION_RPC", "DISCOVERY_ENGINE", "ROUTE_ENGINE",
                "OPP_TYPES", "QUOTES_LIVE", "PROFITABILITY", "CONFIDENCE_V2",
                "EXPECTED_VALUE", "SIZE_OPTIMIZER", "SIMULATION_GATE",
                "DECISION_HISTORY", "FORK_VALIDATION"):
        assert req in caps, f"missing capability {req}"
        assert caps[req]["status"] in ("RED", "YELLOW", "GREEN")
    # every RED/YELLOW row states a blocker + action + owner
    for c in m["capabilities"]:
        if c["status"] in ("RED", "YELLOW"):
            assert c["blocker"] and c["action"] and c["owner"] in ("USER", "ENGINEERING")
    # all five modes present; live modes hard-blocked
    modes = m["modes"]
    assert set(modes) == {"SHADOW", "PAPER", "PROFIT_ENGINE",
                          "LIMITED_LIVE", "FULL_AUTOMATION"}
    assert modes["LIMITED_LIVE"]["can_activate"] is False
    assert modes["FULL_AUTOMATION"]["can_activate"] is False
    # RPC is configured so live quote/analysis modes are activatable
    assert modes["SHADOW"]["can_activate"] is True


# ------------------------------------------------- dynamic liquidity probe
class _DegradingQuoter:
    """Fake quoter: realized ratio worsens as notional grows (depth model)."""
    def _rpc_url(self):
        return "x"

    async def quote_route(self, *, chain, hops, rpc_url=None):
        from datetime import datetime, timezone
        ain = int(hops[0]["amount_in_wei"])
        base = 5 * 10**16
        slip = 0.0008 * (ain / base)          # 8 bps per probe-unit
        out = int(ain * (1.001 - slip))

        class RQ:
            status = "ok"
            final_amount_out_wei = out

            def to_dict(self):
                return {"status": "ok", "final_amount_out_wei": out,
                        "aggregate_price_impact_bps": None,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "hops": [{"amount_in_wei": ain, "amount_out_wei": out,
                                  "block_number": 1, "rpc_host": "h", "status": "ok"}]}
        return RQ()


def test_measure_liquidity_uses_live_quote_curve():
    import asyncio
    eng = OpportunityEngine(quoter_registry=_DegradingQuoter(),
                            config={"depth_probe_threshold_bps": -1000.0})
    hops = [{"dex": "uniswap_v3", "token_in": TOKENS["WETH"]["address"],
             "token_out": TOKENS["WETH"]["address"],
             "amount_in_wei": 5 * 10**16, "fee": 500}]
    liq, src = asyncio.get_event_loop().run_until_complete(
        eng._measure_liquidity(hops, borrow_token="WETH", eth_usd=2300.0,
                               marginal_spread_bps=10.0))
    assert src == "live_probe"
    assert liq > 0


def test_measure_liquidity_skips_deeply_unprofitable():
    import asyncio
    eng = OpportunityEngine(quoter_registry=_DegradingQuoter(),
                            config={"depth_probe_threshold_bps": -25.0})
    hops = [{"dex": "uniswap_v3", "token_in": TOKENS["WETH"]["address"],
             "token_out": TOKENS["WETH"]["address"],
             "amount_in_wei": 5 * 10**16, "fee": 500}]
    liq, src = asyncio.get_event_loop().run_until_complete(
        eng._measure_liquidity(hops, borrow_token="WETH", eth_usd=2300.0,
                               marginal_spread_bps=-500.0))
    assert src == "default:below_threshold"


# ------------------------------------------------------- scanner + checkpoint HTTP
def test_scanner_status_and_toggle(session):
    st = session.get(f"{API}/arbicore/engine/scanner/status", timeout=30).json()
    assert "running" in st and "cumulative" in st
    # stop then start (idempotent-safe); leave it running for autonomous mode
    stopped = session.post(f"{API}/arbicore/engine/scanner/stop", timeout=30).json()
    assert stopped["running"] is False
    started = session.post(f"{API}/arbicore/engine/scanner/start", timeout=30).json()
    assert started["running"] is True


def test_checkpoint_report_complete(session):
    session.post(f"{API}/arbicore/engine/scan-once", json={"limit": 4}, timeout=90)
    r = session.get(f"{API}/arbicore/engine/checkpoint", timeout=60)
    assert r.status_code == 200
    c = r.json()
    for k in ("routes_scanned_records", "positive_after_costs", "executable",
              "opportunity_type_coverage", "top_opportunities", "rejection_reasons",
              "dynamic_sizing_results", "simulation_results", "recurring_routes",
              "decision_history", "scanner", "readiness_matrix", "limited_live_blockers"):
        assert k in c, f"checkpoint missing {k}"
    assert c["readiness_matrix"]["overall_status"] in ("RED", "YELLOW", "GREEN")
    # LIMITED_LIVE blockers must be actionable
    for b in c["limited_live_blockers"]:
        assert b["blocker"] and b["action"] and b["owner"] in ("USER", "ENGINEERING")


def test_recurring_endpoint(session):
    # two scans so some routes recur
    session.post(f"{API}/arbicore/engine/scan-once", json={"limit": 4}, timeout=90)
    session.post(f"{API}/arbicore/engine/scan-once", json={"limit": 4}, timeout=90)
    r = session.get(f"{API}/arbicore/engine/recurring?min_seen=2&limit=10", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert "recurring_routes" in body
    for row in body["recurring_routes"]:
        assert row["times_seen"] >= 2
