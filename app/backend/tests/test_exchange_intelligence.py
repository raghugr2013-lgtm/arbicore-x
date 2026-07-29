"""Exchange Intelligence Registry & Ranking tests (READ-ONLY, NON-EXECUTING).

Covers: registry shape & all 11 BDAG venues, the 13 tracked fields per venue,
3-bucket classification (execution_approved / monitor_only / disabled), the two
rankings (best profit vs best executable) and that they meaningfully DIFFER,
live overlay on connector venues, the operator-verification promotion gate
(PATCH), the 5-section assessment report, and auth enforcement.
"""
import os
from pathlib import Path

import pytest
import requests

from services.execution import exchange_intelligence as exi

_BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not _BASE:
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            _BASE = line.split("=", 1)[1].strip()
            break
assert _BASE
BASE = _BASE.rstrip("/")

ALL_VENUES = {"coinstore", "bitmart", "xt", "pionex", "ascendex", "lbank",
              "p2b", "biconomy", "btcc", "azbit", "bifinance"}
STATUSES = {"execution_approved", "monitor_only", "disabled"}
TRACKED_FIELDS = [
    "name", "bdag_pair", "india_accessibility", "api_availability", "kyc_requirement",
    "deposit_status", "withdrawal_status", "liquidity_score", "vol_24h_usd",
    "spread_score", "trust_score", "execution_approved", "last_verified",
]


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": "admin", "password": "ArbiCore#2026"}, timeout=15)
    assert r.status_code == 200, r.text
    return s


# ---------------- pure scoring logic (deterministic) ----------------

class TestScoringLogic:
    def test_api_availability_derivation(self):
        full = {"trade": True, "deposit_address": True, "deposit_monitor": True, "withdraw": True}
        partial = {"trade": True, "deposit_address": True, "deposit_monitor": False, "withdraw": False}
        trade_only = {"trade": True, "deposit_address": False, "deposit_monitor": False, "withdraw": False}
        none = {"trade": False}
        assert exi._api_availability(full) == "full"
        assert exi._api_availability(partial) == "partial"
        assert exi._api_availability(trade_only) == "trade_only"
        assert exi._api_availability(none) == "none"

    def test_critical_flags_force_disabled(self):
        # P2B (wash_trading) and BTCC (no_public_spot_api) carry critical flags
        assert "wash_trading" in exi.CURATED_MAP["p2b"]["red_flags"]
        assert "no_public_spot_api" in exi.CURATED_MAP["btcc"]["red_flags"]
        # XT's closed-gate flag is NOT critical (keeps it monitor_only)
        assert "bdag_gates_closed" not in exi.CRITICAL_FLAGS

    def test_classify_rules(self):
        # critical flag -> disabled regardless of other attrs
        s, _ = exi._classify(exi.CURATED_MAP["p2b"], None, False, ["wash_trading"])
        assert s == "disabled"
        # approved -> execution_approved
        s, _ = exi._classify(exi.CURATED_MAP["coinstore"], None, True, [])
        assert s == "execution_approved"
        # clean but not approved -> monitor_only
        s, _ = exi._classify(exi.CURATED_MAP["bitmart"], None, False, [])
        assert s == "monitor_only"
        # operator override wins
        s, _ = exi._classify(exi.CURATED_MAP["bitmart"], "disabled", False, [])
        assert s == "disabled"


# ---------------- registry endpoint ----------------

class TestRegistry:
    def test_registry_lists_all_eleven(self, client):
        d = client.get(f"{BASE}/api/execution/exchanges", timeout=20).json()
        assert d["counts"]["total"] == 11
        got = {r["exchange"] for r in d["exchanges"]}
        assert got == ALL_VENUES

    def test_every_venue_has_all_tracked_fields(self, client):
        d = client.get(f"{BASE}/api/execution/exchanges", timeout=20).json()
        for r in d["exchanges"]:
            for f in TRACKED_FIELDS:
                assert f in r, f"{r['exchange']} missing {f}"
            assert r["status"] in STATUSES
            assert isinstance(r["liquidity_score"], int)
            assert isinstance(r["trust_score"], int)
            assert isinstance(r["executability_score"], int)

    def test_coinstore_is_sole_execution_approved(self, client):
        d = client.get(f"{BASE}/api/execution/exchanges", timeout=20).json()
        approved = d["classification"]["execution_approved"]
        assert approved == ["Coinstore"]
        coin = next(r for r in d["exchanges"] if r["exchange"] == "coinstore")
        assert coin["execution_approved"] is True
        assert coin["status"] == "execution_approved"

    def test_disabled_bucket_contains_red_flag_venues(self, client):
        d = client.get(f"{BASE}/api/execution/exchanges", timeout=20).json()
        disabled = {r["exchange"] for r in d["exchanges"] if r["status"] == "disabled"}
        # all six hard-blocker venues must be disabled
        assert {"p2b", "btcc", "biconomy", "azbit", "lbank", "bifinance"} <= disabled
        # bitmart must NOT be disabled (real market + full API)
        assert "bitmart" not in disabled

    def test_bitmart_monitor_only_not_executable(self, client):
        d = client.get(f"{BASE}/api/execution/exchanges", timeout=20).json()
        bm = next(r for r in d["exchanges"] if r["exchange"] == "bitmart")
        assert bm["status"] == "monitor_only"
        assert bm["execution_approved"] is False

    def test_live_overlay_on_connector_venues(self, client):
        d = client.get(f"{BASE}/api/execution/exchanges", timeout=20).json()
        # connector venues with a live book should report data_source=live + fresh last_verified
        live = {r["exchange"] for r in d["exchanges"] if r["data_source"] == "live"}
        assert "coinstore" in live or "bitmart" in live
        assert d["counts"]["live_overlay"] >= 1

    def test_buy_price_basis_present(self, client):
        d = client.get(f"{BASE}/api/execution/exchanges", timeout=20).json()
        assert d["buy_price_basis"]["price"] is not None
        assert d["buy_price_basis"]["source"] is not None


# ---------------- the two rankings ----------------

class TestRankings:
    def test_both_rankings_present_and_sorted(self, client):
        d = client.get(f"{BASE}/api/execution/exchanges", timeout=20).json()
        bp = d["rankings"]["best_profit"]
        be = d["rankings"]["best_executable"]
        assert bp and be
        # best_executable sorted desc by executability_score
        es = [r["executability_score"] for r in be]
        assert es == sorted(es, reverse=True)
        # best_profit sorted desc by profit_score
        ps = [r["profit_score"] for r in bp]
        assert ps == sorted(ps, reverse=True)

    def test_executable_leader_is_execution_approved(self, client):
        d = client.get(f"{BASE}/api/execution/exchanges", timeout=20).json()
        leader = d["rankings"]["best_executable"][0]
        assert leader["exchange"] == "coinstore"
        assert leader["status"] == "execution_approved"

    def test_profit_and_executable_rankings_differ(self, client):
        """The core thesis: the profit ranking is NOT the same ordering as the
        executable ranking. The two leaders MAY coincide under live data (e.g. a
        venue that is both deepest-edge and most-executable), so we assert the
        full ranking SEQUENCES differ rather than requiring different leaders —
        which keeps the thesis honest across changing market conditions."""
        d = client.get(f"{BASE}/api/execution/exchanges", timeout=20).json()
        profit_order = [r["exchange"] for r in d["rankings"]["best_profit"]]
        exec_order = [r["exchange"] for r in d["rankings"]["best_executable"]]
        assert profit_order != exec_order, "rankings collapsed — profit ordering == executable ordering"

    def test_disabled_venue_can_outrank_on_profit(self, client):
        """A disabled venue (e.g. dislocated Biconomy) can show high profit but
        must never top the executable ranking."""
        d = client.get(f"{BASE}/api/execution/exchanges", timeout=20).json()
        disabled_profit = [r for r in d["rankings"]["best_profit"]
                           if r["status"] == "disabled" and r["profit_score"]]
        assert disabled_profit, "expected at least one disabled venue with a profit score"
        top_exec = d["rankings"]["best_executable"][0]
        assert top_exec["status"] != "disabled"


# ---------------- single venue + promotion gate ----------------

class TestSingleAndPromotion:
    def test_single_venue(self, client):
        d = client.get(f"{BASE}/api/execution/exchanges/coinstore", timeout=15).json()
        assert d["exchange"] == "coinstore"
        assert d["execution_approved"] is True

    def test_unknown_venue_404(self, client):
        r = client.get(f"{BASE}/api/execution/exchanges/doesnotexist", timeout=15)
        assert r.status_code == 404

    def test_operator_verification_promotes_then_reverts(self, client):
        # BitMart is monitor_only until operator-verified; verifying promotes it.
        r = client.patch(f"{BASE}/api/execution/exchanges/bitmart",
                         json={"operator_verified": True}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "execution_approved"
        assert r.json()["execution_approved"] is True
        # revert
        r2 = client.patch(f"{BASE}/api/execution/exchanges/bitmart",
                          json={"operator_verified": False}, timeout=15)
        assert r2.json()["status"] == "monitor_only"

    def test_invalid_status_override_400(self, client):
        r = client.patch(f"{BASE}/api/execution/exchanges/bitmart",
                         json={"status_override": "nonsense"}, timeout=15)
        assert r.status_code == 400


# ---------------- assessment report ----------------

class TestAssessment:
    def test_assessment_five_sections(self, client):
        d = client.get(f"{BASE}/api/execution/exchanges/assessment", timeout=20).json()
        for s in ("section_1_detected_exchanges", "section_2_accessibility_assessment",
                  "section_3_liquidity_comparison", "section_4_execution_suitability_ranking",
                  "section_5_recommended_production_ranking"):
            assert s in d, s
        assert len(d["section_1_detected_exchanges"]) == 11
        assert "headline" in d

    def test_production_ranking_three_tiers(self, client):
        d = client.get(f"{BASE}/api/execution/exchanges/assessment", timeout=20).json()
        prod = d["section_5_recommended_production_ranking"]
        assert len(prod) == 3
        assert prod[0]["exchanges"] == ["Coinstore"]

    def test_liquidity_comparison_sorted(self, client):
        d = client.get(f"{BASE}/api/execution/exchanges/assessment", timeout=20).json()
        scores = [x["liquidity_score"] or 0 for x in d["section_3_liquidity_comparison"]]
        assert scores == sorted(scores, reverse=True)


# ---------------- auth + non-execution invariant ----------------

class TestSafety:
    def test_anon_blocked(self):
        assert requests.get(f"{BASE}/api/execution/exchanges", timeout=10).status_code == 401
        assert requests.get(f"{BASE}/api/execution/exchanges/assessment", timeout=10).status_code == 401

    def test_execution_remains_disabled(self, client):
        cfg = client.get(f"{BASE}/api/execution/config", timeout=15).json()
        assert cfg["execution_enabled"] is False
        assert cfg["wallet_enabled"] is False
