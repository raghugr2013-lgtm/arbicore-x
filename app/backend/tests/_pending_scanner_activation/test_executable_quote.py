"""Tests for GET /api/execution/executable-quote (Executable Quote Resolver)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
CREDS = {"username": "admin", "password": "ArbiCore2026!"}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=CREDS, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def quote(client):
    t0 = time.time()
    r = client.get(f"{BASE_URL}/api/execution/executable-quote", timeout=20)
    elapsed = time.time() - t0
    assert r.status_code == 200, f"executable-quote failed: {r.text[:200]}"
    assert elapsed < 12, f"endpoint too slow: {elapsed:.2f}s"
    return r.json()


# ---------------- Top-level shape ----------------

class TestExecutableQuoteShape:
    def test_top_level_keys(self, quote):
        for k in ["phase", "generated_at", "authoritative", "authoritative_explanation",
                  "precedence", "chain", "sources", "side_by_side", "secondary_observation",
                  "effective_price_from_completed_swaps", "consumed_by_arbicore_for_roi",
                  "thresholds", "note"]:
            assert k in quote, f"missing top-level key: {k}"

    def test_precedence_order(self, quote):
        assert quote["precedence"] == ["executed_history", "live_swap_ui", "sw_api_fallback"]

    def test_thresholds(self, quote):
        th = quote["thresholds"]
        assert th["min_executed_samples_for_authoritative"] == 3
        assert th["executed_rolling_window"] == 20

    def test_consumed_flag_false(self, quote):
        assert quote["consumed_by_arbicore_for_roi"] is False

    def test_sources_dict(self, quote):
        for k in ["executed_history", "live_swap_ui", "sw_api_fallback"]:
            assert k in quote["sources"]

    def test_side_by_side_three_rows(self, quote):
        sbs = quote["side_by_side"]
        assert len(sbs) == 3
        sources = {row["source"] for row in sbs}
        assert sources == {"executed_history", "live_swap_ui", "sw_api_fallback"}
        for row in sbs:
            for k in ["source", "label", "value", "delta_pct_vs_authoritative",
                      "available", "is_authoritative", "fetched_at"]:
                assert k in row, f"row {row['source']} missing {k}"


# ---------------- Authoritative = executed_history (≥3 samples) ----------------

class TestAuthoritativeExecutedHistory:
    def test_authoritative_is_executed_history(self, quote):
        # Pre-condition: iter3 left ≥3 empirical quotes
        assert quote["sources"]["executed_history"]["count"] >= 3, \
            "Need ≥3 empirical quotes seeded for this test"
        assert quote["authoritative"]["source"] == "executed_history"

    def test_authoritative_value_near_3_6e_5(self, quote):
        v = quote["authoritative"]["value"]
        assert v is not None
        # Should be in the 10^-5 magnitude range (~3.6e-5)
        assert 1e-5 <= v <= 1e-4, f"unexpected magnitude: {v}"

    def test_effective_price_matches_executed(self, quote):
        eff = quote["effective_price_from_completed_swaps"]
        assert eff is not None
        assert abs(eff - quote["sources"]["executed_history"]["value"]) < 1e-15

    def test_executed_history_row_zero_delta(self, quote):
        row = next(r for r in quote["side_by_side"] if r["source"] == "executed_history")
        assert row["is_authoritative"] is True
        assert row["delta_pct_vs_authoritative"] == 0.0

    def test_live_swap_ui_delta_positive(self, quote):
        # live > executed → positive delta around +12
        live_row = next(r for r in quote["side_by_side"] if r["source"] == "live_swap_ui")
        if live_row["available"]:
            d = live_row["delta_pct_vs_authoritative"]
            assert d is not None and d > 0, f"expected positive delta, got {d}"

    def test_chain_step_zero_won(self, quote):
        chain = quote["chain"]
        assert chain[0]["source"] == "executed_history"
        assert chain[0]["won"] is True
        assert "≥3 executed-swap samples" in chain[0]["reason"]


# ---------------- Sources detail ----------------

class TestLiveSwapUiSource:
    def test_url_and_discovery(self, quote):
        live = quote["sources"]["live_swap_ui"]
        assert live["url"] == "https://live-price.blockdag.network/bdag-price"
        assert "endpoint_label" in live
        assert "purchase3.blockdag.network" in (live.get("discovery") or "")

    def test_live_value_positive_when_available(self, quote):
        live = quote["sources"]["live_swap_ui"]
        if live.get("ok"):
            assert live["value"] > 0


class TestSwApiFallback:
    def test_has_stale_and_url(self, quote):
        sw = quote["sources"]["sw_api_fallback"]
        assert "stale" in sw
        # source_url (or url) field
        assert sw.get("source_url") is not None or "url" in sw


class TestSecondaryObservation:
    def test_secondary_present_and_not_in_sbs(self, quote):
        sec = quote["secondary_observation"]
        # implied_price_from_latest_orders may be present (may be None on upstream fail)
        assert "implied_price_from_latest_orders" in sec
        if sec.get("ok"):
            assert isinstance(sec["implied_price_from_latest_orders"], (int, float))
            assert sec["sample_count"] > 0
            assert "denomination" in (sec.get("note") or "").lower() or "denominated" in (sec.get("note") or "").lower()
        # Verify side_by_side has exactly 3 rows (no secondary leak)
        assert len(quote["side_by_side"]) == 3


# ---------------- Hard guardrails (no behavior change to ArbiCore) ----------------

class TestHardGuardrails:
    def test_execution_disabled(self, client):
        r = client.get(f"{BASE_URL}/api/execution/status", timeout=10)
        assert r.status_code == 200
        assert r.json()["execution_enabled"] is False

    def test_intel_unchanged(self, client):
        # find a bdag route id
        r = client.get(f"{BASE_URL}/api/routes", timeout=10)
        if r.status_code != 200:
            pytest.skip("routes endpoint unavailable")
        routes = r.json()
        if isinstance(routes, dict):
            routes = routes.get("routes", [])
        bdag = next((rt for rt in routes if (rt.get("purchase") or {}).get("asset") == "BDAG"), None)
        if not bdag:
            pytest.skip("no bdag route")
        r2 = client.get(f"{BASE_URL}/api/execution/intel/{bdag['id']}", timeout=15)
        assert r2.status_code == 200
        # Just ensure the response exists; the consumed_by_arbicore_for_roi flag is on /executable-quote
        # The key point: this endpoint still works (uses Portal Feed, not the new resolver)


# ---------------- Negative path: empty empirical collection ----------------

def test_negative_path_no_executed_samples(client):
    """Drop all rows, verify resolver falls through to live_swap_ui, then restore."""
    import asyncio
    import sys
    sys.path.insert(0, "/app/backend")

    async def _run():
        from services import db as _db
        col = _db.db["buy_price_empirical_quotes"]
        captured = await col.find({}).to_list(length=10000)
        if not captured:
            return "skip"
        try:
            await col.delete_many({})
            r = client.get(f"{BASE_URL}/api/execution/executable-quote", timeout=20)
            assert r.status_code == 200
            q = r.json()
            chain = q["chain"]
            assert chain[0]["source"] == "executed_history"
            assert chain[0]["won"] is False
            reason_l = chain[0]["reason"].lower()
            assert "insufficient" in reason_l or "need" in reason_l
            live_ok = q["sources"]["live_swap_ui"].get("ok")
            if live_ok:
                assert q["authoritative"]["source"] == "live_swap_ui"
                assert len(chain) >= 2 and chain[1]["source"] == "live_swap_ui"
                assert chain[1]["won"] is True
            return "ok"
        finally:
            for doc in captured:
                doc.pop("_id", None)
            if captured:
                await col.insert_many(captured)

    result = asyncio.run(_run())
    if result == "skip":
        pytest.skip("no empirical rows to drop")
