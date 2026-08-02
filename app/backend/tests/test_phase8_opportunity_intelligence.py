"""Phase 8 Canonical Opportunity Intelligence Activation — API tests.

Covers:
  * canonical + preview merge (list endpoint w/ source field)
  * sort_by options (confidence, spread, depth, freshness)
  * filters (family, verdict) backward compat with slice-1
  * canonical detail (base-weth-usdc-univ3-aero) w/ verification.quote_source
  * preview detail (opp-001)
  * new timeline endpoint (multi-kind institutional trail, desc order)
  * FSM approve (canonical=true, idempotent-ish)
  * FSM reject on canonical + preview-fallback
"""
from __future__ import annotations

import os
import time

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
CANONICAL_ID = "base-weth-usdc-univ3-aero"


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------------------------------------------------------------------
# LIST — merge + source
# ---------------------------------------------------------------------------

def _wait_for_canonical(sess, tries: int = 6):
    """Discovery worker writes canonical rows every ~60s. Poll briefly."""
    for _ in range(tries):
        r = sess.get(f"{BASE_URL}/api/arbicore/opportunities?limit=50", timeout=15)
        assert r.status_code == 200
        data = r.json()
        if any(i.get("canonical") for i in data.get("items", [])):
            return data
        time.sleep(10)
    return data  # last snapshot even if no canonical yet


def test_list_returns_merged_universe(sess):
    data = _wait_for_canonical(sess)
    assert isinstance(data.get("items"), list) and data["items"]
    assert data["source"] in ("canonical", "preview", "canonical+preview")
    ids = {i["id"] for i in data["items"]}
    # All 8 preview rows must remain (BC)
    for pid in ("opp-001", "opp-002", "opp-003", "opp-004",
                "opp-005", "opp-006", "opp-007", "opp-008"):
        assert pid in ids, f"missing preview id {pid}"


def test_list_sort_by_confidence(sess):
    r = sess.get(f"{BASE_URL}/api/arbicore/opportunities?sort_by=confidence&limit=50")
    assert r.status_code == 200
    conf = [i["confidence"] for i in r.json()["items"]]
    assert conf == sorted(conf, reverse=True)


def test_list_sort_by_spread(sess):
    r = sess.get(f"{BASE_URL}/api/arbicore/opportunities?sort_by=spread&limit=50")
    assert r.status_code == 200
    vals = [i["spread_bps"] for i in r.json()["items"]]
    assert vals == sorted(vals, reverse=True)


def test_list_sort_by_depth(sess):
    r = sess.get(f"{BASE_URL}/api/arbicore/opportunities?sort_by=depth&limit=50")
    assert r.status_code == 200
    vals = [i["depth_usd"] for i in r.json()["items"]]
    assert vals == sorted(vals, reverse=True)


def test_list_sort_default_freshness(sess):
    r = sess.get(f"{BASE_URL}/api/arbicore/opportunities?limit=50")
    assert r.status_code == 200
    ages = [i["age_s"] for i in r.json()["items"]]
    assert ages == sorted(ages)


def test_list_filter_family_cex(sess):
    r = sess.get(f"{BASE_URL}/api/arbicore/opportunities?family=CEX_ARBITRAGE&limit=50")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items
    for it in items:
        assert it["opportunity_type"] == "CEX_ARBITRAGE"
    ids = {i["id"] for i in items}
    assert {"opp-001", "opp-004"}.issubset(ids)


def test_list_filter_verdict_go(sess):
    r = sess.get(f"{BASE_URL}/api/arbicore/opportunities?verdict=GO&limit=50")
    assert r.status_code == 200
    for it in r.json()["items"]:
        assert it["verdict"] == "GO"


# ---------------------------------------------------------------------------
# DETAIL
# ---------------------------------------------------------------------------

def test_detail_canonical(sess):
    _wait_for_canonical(sess)
    r = sess.get(f"{BASE_URL}/api/arbicore/opportunities/{CANONICAL_ID}")
    if r.status_code == 404:
        pytest.skip("canonical row not yet written by discovery worker")
    assert r.status_code == 200
    data = r.json()
    assert data.get("canonical") is True
    assert data.get("verification", {}).get("quote_source") == "canonical_opp_repo"


def test_detail_preview(sess):
    r = sess.get(f"{BASE_URL}/api/arbicore/opportunities/opp-001")
    assert r.status_code == 200
    data = r.json()
    for k in ("reasoning", "verification", "quote", "sizing", "evidence"):
        assert k in data, f"missing key {k}"
    assert "confidence_breakdown" in data["reasoning"]


# ---------------------------------------------------------------------------
# TIMELINE
# ---------------------------------------------------------------------------

def test_timeline_canonical_multi_kind(sess):
    _wait_for_canonical(sess)
    r = sess.get(f"{BASE_URL}/api/arbicore/opportunities/{CANONICAL_ID}/timeline")
    assert r.status_code == 200
    data = r.json()
    for k in ("opportunity_id", "count", "events", "generated_at"):
        assert k in data
    events = data["events"]
    assert isinstance(events, list)
    kinds = {e.get("kind") for e in events}
    # We should see at least a handful of institutional-trail kinds present.
    # At minimum: opportunity_state + several ambient global kinds.
    ambient = {"mode_transition", "capital_policy", "kill_switch",
               "calibration", "adaptive_weights", "wallet_registry"}
    assert kinds & ambient, f"no ambient audit events found: kinds={kinds}"
    # opportunity_state must be present for canonical row
    assert "opportunity_state" in kinds
    # Descending by `at` (string ISO compares chronologically)
    ats = [str(e.get("at") or "") for e in events]
    assert ats == sorted(ats, reverse=True)


def test_timeline_preview_only_empty_or_ambient(sess):
    r = sess.get(f"{BASE_URL}/api/arbicore/opportunities/opp-001/timeline")
    assert r.status_code == 200
    data = r.json()
    assert data["opportunity_id"] == "opp-001"
    assert isinstance(data["events"], list)


# ---------------------------------------------------------------------------
# FSM approve / reject
# ---------------------------------------------------------------------------

def test_reject_canonical_then_approve_semantics(sess):
    """FSM: reject may only succeed from valid states; approve must be canonical
    when the row exists."""
    _wait_for_canonical(sess)
    # First — approve. Should chain CANDIDATE->VALIDATED->APPROVED (or be no-op
    # if already there). canonical=true expected.
    r = sess.post(f"{BASE_URL}/api/arbicore/opportunities/{CANONICAL_ID}/approve")
    assert r.status_code == 200
    approve_data = r.json()
    if approve_data.get("canonical") is False:
        pytest.skip("canonical row not yet in repo; approve fell back to preview")
    assert approve_data["canonical"] is True
    assert approve_data.get("ok") is True

    # Second approve — idempotent-ish: either ok:true with same status, or
    # ok:false with InvalidTransition (both acceptable per problem statement).
    r2 = sess.post(f"{BASE_URL}/api/arbicore/opportunities/{CANONICAL_ID}/approve")
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["id"] == CANONICAL_ID
    assert "generated_at" in d2

    # Reject from APPROVED — depending on FSM either OK or InvalidTransition;
    # response must be well-formed either way.
    r3 = sess.post(f"{BASE_URL}/api/arbicore/opportunities/{CANONICAL_ID}/reject",
                    json={"reason": "test"})
    assert r3.status_code == 200
    d3 = r3.json()
    assert "ok" in d3
    if d3["ok"] is False:
        assert "error" in d3
    else:
        assert d3.get("canonical") is True


def test_reject_preview_fallback(sess):
    r = sess.post(f"{BASE_URL}/api/arbicore/opportunities/opp-002/reject",
                   json={"reason": "test"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data.get("canonical") is False
    assert data["status"] == "REJECTED"
