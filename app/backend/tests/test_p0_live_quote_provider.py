"""P0-4 — Live-quote seam (quote_provider) + /control/live-quote endpoint.

PURE tests build synthetic RouteQuote dicts (no RPC) to verify freshness
classification and route→opportunity transform. HTTP tests hit the live
read-only Base quoter through the running preview server.
"""
import os
import json
from datetime import datetime, timezone, timedelta

import pytest
import requests

from arbicore.economics.quote_provider import (
    classify_quote_status, build_opportunity_from_route, quote_age_seconds,
)

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"

OP_USER = "operator"
OP_PASS = "ShadowOperator!2026"

WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


def _now_iso(offset_sec=0.0):
    return (datetime.now(timezone.utc) - timedelta(seconds=offset_sec)).isoformat()


def _route_quote(*, status="ok", generated_offset=0.0, initial_in=10**16,
                 final_out=None, hops=None):
    final_out = final_out if final_out is not None else int(initial_in * 1.002)
    hops = hops or [
        {"amount_in_wei": initial_in, "amount_out_wei": 22_900_000,
         "block_number": 50_000_000, "rpc_host": "mainnet.base.org", "status": "ok"},
        {"amount_in_wei": 22_900_000, "amount_out_wei": final_out,
         "block_number": 50_000_000, "rpc_host": "mainnet.base.org", "status": "ok"},
    ]
    return {
        "chain": "base", "hops": hops, "final_amount_out_wei": final_out,
        "aggregate_price_impact_bps": 8, "aggregate_gas_estimate_units": 210000,
        "status": status, "generated_at": _now_iso(generated_offset),
        "ttl_seconds": 5,
    }


# ------------------------------------------------------------- freshness
def test_fresh_ok_quote_is_real():
    r = classify_quote_status(_route_quote(status="ok", generated_offset=1.0))
    assert r["quote_status"] == "REAL"
    assert r["quote_age_sec"] >= 0


def test_old_ok_quote_is_stale():
    r = classify_quote_status(_route_quote(status="ok", generated_offset=60.0),
                              max_age_sec=12.0)
    assert r["quote_status"] == "STALE"


def test_fallback_quote_is_unavailable():
    r = classify_quote_status(_route_quote(status="fallback:break_even"))
    assert r["quote_status"] == "UNAVAILABLE"


def test_quote_age_handles_missing_timestamp():
    assert quote_age_seconds(None) is None


# ------------------------------------------------- route → opportunity
def _cyclic_hops():
    return [
        {"dex": "uniswap_v3", "token_in": WETH, "token_out": USDC,
         "amount_in_wei": 10**16, "fee": 500},
        {"dex": "aerodrome_slipstream", "token_in": USDC, "token_out": WETH,
         "tick_spacing": 100},
    ]


def test_profitable_cyclic_route_builds_executable_shaped_opp():
    rq = _route_quote(status="ok", initial_in=10**16, final_out=int(10**16 * 1.01))
    built = build_opportunity_from_route(
        rq, input_hops=_cyclic_hops(),
        economics={"pool_liquidity_usd": 3_000_000, "gas_cost_usd": 3.0,
                   "native_price_usd": 3000, "gas_certainty": 0.9, "mev_risk": 0.1,
                   "buy_venue_fee_bps": 5, "sell_venue_fee_bps": 5})
    opp = built["opportunity"]
    assert opp["quote_status"] == "REAL"
    assert opp["gross_spread_bps"] > 0            # realized on-chain spread
    assert opp["repayment_ok"] is True
    assert opp["user_data_hex"] and opp["user_data_hex"].startswith("0x")
    # routers mapped from dex names; tokens preserved
    assert opp["hops"][0]["router"].lower() == "0x2626664c2603336E57B271c5C0b26F421741e481".lower()
    assert opp["hops"][1]["router"].lower() == "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43".lower()
    assert all(h["amount_out_min_wei"] > 0 for h in opp["hops"])
    assert built["quote_provenance"]["cyclic_route"] is True


def test_unprofitable_cyclic_route_reports_zero_or_negative_spread():
    rq = _route_quote(status="ok", initial_in=10**16, final_out=int(10**16 * 0.999))
    built = build_opportunity_from_route(rq, input_hops=_cyclic_hops(),
                                         economics={"pool_liquidity_usd": 1})
    opp = built["opportunity"]
    assert opp["gross_spread_bps"] < 0
    assert opp["repayment_ok"] is False


def test_stale_quote_never_marked_real_and_spread_zeroed():
    rq = _route_quote(status="ok", generated_offset=120.0,
                      initial_in=10**16, final_out=int(10**16 * 1.05))
    built = build_opportunity_from_route(rq, input_hops=_cyclic_hops(),
                                         max_age_sec=12.0,
                                         economics={"pool_liquidity_usd": 3_000_000})
    opp = built["opportunity"]
    assert opp["quote_status"] == "STALE"
    # realized spread is only computed for a REAL quote → 0 here (no fabrication)
    assert opp["gross_spread_bps"] == 0.0
    assert opp["repayment_ok"] is False


def test_non_cyclic_route_has_zero_spread():
    hops = [{"dex": "uniswap_v3", "token_in": WETH, "token_out": USDC,
             "amount_in_wei": 10**16, "fee": 500}]
    rq = _route_quote(status="ok", hops=[
        {"amount_in_wei": 10**16, "amount_out_wei": 22_900_000,
         "block_number": 1, "rpc_host": "h", "status": "ok"}],
        final_out=22_900_000)
    built = build_opportunity_from_route(rq, input_hops=hops,
                                         economics={"pool_liquidity_usd": 1})
    assert built["opportunity"]["gross_spread_bps"] == 0.0
    assert built["quote_provenance"]["cyclic_route"] is False


# --------------------------------------------------------------- HTTP
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


def test_live_quote_requires_auth():
    r = requests.post(f"{API}/arbicore/control/live-quote",
                      json={"chain": "base", "hops": [{"dex": "uniswap_v3",
                            "token_in": WETH, "token_out": USDC,
                            "amount_in_wei": 10**16, "fee": 500}]}, timeout=30)
    assert r.status_code == 401


def test_live_quote_requires_hops(session):
    r = session.post(f"{API}/arbicore/control/live-quote",
                     json={"chain": "base"}, timeout=30)
    assert r.status_code == 422


def test_live_quote_returns_real_base_price(session):
    r = session.post(f"{API}/arbicore/control/live-quote", json={
        "chain": "base",
        "hops": [{"dex": "uniswap_v3", "token_in": WETH, "token_out": USDC,
                  "amount_in_wei": 10**16, "fee": 500}]}, timeout=45)
    assert r.status_code == 200
    body = r.json()
    assert body["rpc_configured"] is True
    assert body["quote_status"] in ("REAL", "STALE", "UNAVAILABLE")
    hop = body["route_quote"]["hops"][0]
    # a live Base RPC should quote a real, non-zero WETH->USDC output
    if hop["status"] == "ok":
        assert body["quote_status"] == "REAL"
        assert int(hop["amount_out_wei"]) > 0
        assert hop["block_number"] is not None


def test_decide_via_live_route_runs_full_chain(session):
    r = session.post(f"{API}/arbicore/control/decide-opportunity", json={
        "route": {"chain": "base", "hops": [
            {"dex": "uniswap_v3", "token_in": WETH, "token_out": USDC,
             "amount_in_wei": 10**16, "fee": 500},
            {"dex": "aerodrome_slipstream", "token_in": USDC, "token_out": WETH,
             "tick_spacing": 100}]},
        "economics": {"pool_liquidity_usd": 3_000_000, "gas_cost_usd": 3.0,
                      "native_price_usd": 3000, "gas_certainty": 0.9,
                      "mev_risk": 0.1, "buy_venue_fee_bps": 5,
                      "sell_venue_fee_bps": 5}}, timeout=45)
    assert r.status_code == 200
    body = r.json()
    assert body["data_source"] == "LIVE_QUOTE"
    assert body["execution_performed"] is False
    prov = body["quote_provenance"]
    assert prov["quote_status"] in ("REAL", "STALE", "UNAVAILABLE")
    assert prov["cyclic_route"] is True
    # decision object is fully populated regardless of profitability
    dec = body["decision"]
    assert "would_execute" in dec and "simulation" in dec and "ev" in dec
