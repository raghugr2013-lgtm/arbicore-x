"""UI v2 · Wave 2 — Expose file-verified canonical engines (contract tests).

Shapes below mirror `services/execution/certification_review.latest_review()`
and the composed `/entities` + `/entities/scores/top` canonical endpoints.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://exec-readiness-x.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


class TestCertification:
    """RouteCertifier / Shadow Certification Review — expose existing engine."""

    def test_get(self, client):
        r = client.get(f"{API}/arbicore/intelligence/certification")
        assert r.status_code == 200
        d = r.json()
        # Canonical top-level shape (verified against certification_review.py)
        for k in ["phase", "available", "generated_at", "recommendation",
                  "campaign", "summary", "readiness_criteria", "sections", "note"]:
            assert k in d, f"missing {k}"
        # Recommendation vocabulary is frozen
        assert d["recommendation"] in {
            "READY_FOR_MICROCAPITAL_REVIEW", "NEEDS_MORE_DATA", "NOT_READY", None
        }
        # Campaign block
        for k in ["id", "status", "target_completed", "start_at", "ended_at",
                  "breach_reason", "breach_thresholds"]:
            assert k in d["campaign"]
        # Summary block — every field mirrors the canonical shape
        for k in ["total_cycles", "completed", "aborted", "completion_rate_pct",
                  "ever_stuck", "stuck_rate_pct", "recovery_success_rate_pct",
                  "recovery_failures", "expected_total_quote", "realized_total_quote",
                  "variance_pct", "profitable_rate_pct", "avg_realized_per_cycle",
                  "recommended_safe_cycle_usd", "criteria_passed", "criteria_failed",
                  "criteria_na"]:
            assert k in d["summary"]
        # Readiness criteria mirror the READINESS_CRITERIA dict in canonical source
        for k in ["min_completed_cycles", "min_completion_rate_pct",
                  "min_recovery_success_rate_pct", "max_stuck_rate_pct",
                  "max_variance_pct", "min_profitable_rate_pct"]:
            assert k in d["readiness_criteria"]
        # Sections carry the (title, verdict, evidence) shape used in canonical
        assert len(d["sections"]) >= 3
        s0 = d["sections"][0]
        for k in ["title", "verdict", "evidence"]:
            assert k in s0
        # Each evidence row carries the {metric, value, threshold, status} shape
        e0 = s0["evidence"][0]
        for k in ["metric", "value", "threshold", "status"]:
            assert k in e0

    def test_safety_note_present(self, client):
        # Canonical certification_review contains a mandatory read-only safety note.
        # Preserve it verbatim so operators + auditors trust the surface.
        d = client.get(f"{API}/arbicore/intelligence/certification").json()
        assert "Read-only" in d["note"] or "read-only" in d["note"]
        assert "wallet" in d["note"].lower()


class TestEntities:
    """Entity Graph — expose existing canonical `/entities` composed view."""

    def test_get(self, client):
        r = client.get(f"{API}/arbicore/intelligence/entities")
        assert r.status_code == 200
        d = r.json()
        for k in ["count", "total_entities", "counts_by_type", "items",
                  "vocabulary", "generated_at"]:
            assert k in d
        # Canonical EntityType vocabulary (frozen) — verified against entity_types.py
        assert set(d["vocabulary"]) == {
            "WALLET", "SMART_MONEY", "EXCHANGE_WALLET", "MARKET_MAKER",
            "LIQUIDITY_PROVIDER", "LAUNCH_PARTICIPANT", "CEX_ACCOUNT",
            "DEX_POOL", "UNKNOWN"
        }
        assert d["total_entities"] >= 5
        e = d["items"][0]
        for k in ["entity_id", "entity_type", "label", "score", "samples", "last_seen"]:
            assert k in e
        # Score is a bounded float
        assert 0.0 <= e["score"] <= 1.0

    def test_filter_by_type(self, client):
        r = client.get(f"{API}/arbicore/intelligence/entities",
                       params={"entity_type": "SMART_MONEY"})
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        assert all(e["entity_type"] == "SMART_MONEY" for e in items)

    def test_counts_by_type(self, client):
        d = client.get(f"{API}/arbicore/intelligence/entities").json()
        c = d["counts_by_type"]
        # counts_by_type keys must be a subset of the vocabulary
        assert set(c.keys()).issubset(set(d["vocabulary"]))
        # Sum of counts equals total_entities
        assert sum(c.values()) == d["total_entities"]


class TestBackwardsCompat:
    """Wave-2 additions must not break Wave-1 or Slice-0..5 endpoints."""

    def test_wave1_still_works(self, client):
        for path in ["/arbicore/intelligence/calibration",
                     "/arbicore/intelligence/models",
                     "/arbicore/intelligence/decisions"]:
            r = client.get(f"{API}{path}")
            assert r.status_code == 200, f"{path} broken"

    def test_slice0_pulse_still_works(self, client):
        r = client.get(f"{API}/arbicore/dashboard/pulse")
        assert r.status_code == 200
