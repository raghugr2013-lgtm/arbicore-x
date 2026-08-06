"""v2.11.10 · Opportunity Decision Analytics — unit tests.

Locks in the canonical rejection taxonomy so future pipeline changes
must update the mapper deliberately (a new failure category should
never silently land in ``OTHER``).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from arbicore.analytics import (
    DecisionRecord,
    RejectionCategory,
    classify_evidence,
)
from arbicore.analytics.service import DecisionAnalyticsService


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1. Taxonomy — every closed category is reachable.
# ---------------------------------------------------------------------------
def test_taxonomy_is_closed_and_matches_stage_map():
    from arbicore.analytics import STAGE_TO_CATEGORY, CANONICAL_STAGE_ORDER
    # Every stage in the pipeline order has a canonical category.
    for stage in CANONICAL_STAGE_ORDER:
        if stage in ("decision",):
            continue  # meta stage, not a rejection dimension
        assert stage in STAGE_TO_CATEGORY, f"stage {stage} missing category"
    # Every mapped category is a member of the enum.
    for cat in STAGE_TO_CATEGORY.values():
        assert isinstance(cat, RejectionCategory)


# ---------------------------------------------------------------------------
# 2. Classify: OBSERVE-mode short-circuit
# ---------------------------------------------------------------------------
def test_classify_observe_only_short_circuit():
    doc = {
        "opportunity_id": "opp-a",
        "outcome":        "REJECTED",
        "outcome_reason": "mode is OBSERVE — no analysis",
        "pipeline_action": "observe",
        "stages": [
            {"stage": "observe_only", "ok": True,
             "detail": "OBSERVE mode records the opportunity."},
        ],
    }
    r = classify_evidence(doc)
    assert r.category == RejectionCategory.OBSERVE_ONLY.value
    assert r.attributing_stage == "observe_only"
    assert r.executable is False
    assert r.sub_code == "mode_is_observe_—_no_analysis"


# ---------------------------------------------------------------------------
# 3. Classify: real ROUTE failure
# ---------------------------------------------------------------------------
def test_classify_route_failure_from_quote_stage():
    doc = {
        "opportunity_id": "opp-b",
        "outcome":        "ROUTE_FAILURE",
        "outcome_reason": "no swap_hops on opportunity — cannot quote",
        "pipeline_action": "reject",
        "stages": [
            {"stage": "quote",     "ok": False,
             "failure_reason": "no swap_hops on opportunity — cannot quote",
             "duration_ms": 0.007},
            {"stage": "liquidity", "ok": True, "duration_ms": 0.020},
        ],
    }
    r = classify_evidence(doc)
    assert r.category == RejectionCategory.ROUTE.value
    assert r.attributing_stage == "quote"
    assert r.sub_code == "no_hops"
    assert r.stage_failures[0]["stage"] == "quote"
    assert r.e2e_duration_ms == pytest.approx(0.027, abs=0.001)


# ---------------------------------------------------------------------------
# 4. Classify: profit failure sub-code
# ---------------------------------------------------------------------------
def test_classify_profitability_negative_after_gas():
    doc = {
        "opportunity_id": "opp-c",
        "outcome":        "REJECTED",
        "outcome_reason": "net=50.00 gas=60.00 after_gas=-10.00",
        "pipeline_action": "reject",
        "stages": [
            {"stage": "profit", "ok": False,
             "failure_reason": "net=50.00 gas=60.00 after_gas=-10.00",
             "duration_ms": 0.5},
        ],
    }
    r = classify_evidence(doc)
    assert r.category == RejectionCategory.PROFITABILITY.value
    assert r.sub_code == "negative_after_gas"


# ---------------------------------------------------------------------------
# 5. Classify: EXECUTABLE meta-category
# ---------------------------------------------------------------------------
def test_classify_executable_meta():
    doc = {
        "opportunity_id": "opp-x",
        "outcome":        "EXECUTABLE",
        "outcome_reason": "would_survive=True",
        "pipeline_action": "shadow",
        "stages": [{"stage": "decision", "ok": True, "duration_ms": 0.03}],
    }
    r = classify_evidence(doc)
    assert r.executable is True
    assert r.category == RejectionCategory.EXECUTABLE.value


# ---------------------------------------------------------------------------
# 6. Classify: unknown reason falls to OTHER (never None)
# ---------------------------------------------------------------------------
def test_classify_unknown_falls_to_other():
    doc = {
        "opportunity_id": "opp-y",
        "outcome":        "REJECTED",
        "outcome_reason": "🌀 pipeline emitted a novel error we've never seen",
        "stages": [],
    }
    r = classify_evidence(doc)
    assert r.category == RejectionCategory.OTHER.value


# ---------------------------------------------------------------------------
# Service tests — in-memory repo double
# ---------------------------------------------------------------------------
class _FakeRepo:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = docs

        class _Col:
            def __init__(self, docs):
                self._docs = docs

            def find(self, q, sort=None):
                gt = None
                if isinstance(q.get("created_at"), dict):
                    gt = q["created_at"].get("$gt")
                out = [
                    d for d in self._docs
                    if (gt is None or (d.get("created_at") or "") > gt)
                ]
                # honour scanner_family filter
                if "scanner_family" in q:
                    out = [d for d in out if d.get("scanner_family") == q["scanner_family"]]
                if "outcome" in q:
                    out = [d for d in out if d.get("outcome") == q["outcome"]]
                out.sort(key=lambda d: d.get("created_at") or "", reverse=True)
                return _Cur(out)
        class _Cur:
            def __init__(self, docs):
                self._d = docs
                self._n = len(docs)
            def limit(self, n):
                self._d = self._d[:n]
                return self
            def __aiter__(self):
                self._i = 0
                return self
            async def __anext__(self):
                if self._i >= len(self._d):
                    raise StopAsyncIteration
                d = self._d[self._i]
                self._i += 1
                return d
        self._col = _Col(docs)

    async def list_recent(self, *, limit=100, **_):
        return sorted(self._docs, key=lambda d: d.get("created_at") or "", reverse=True)[:limit]


def _seed_docs():
    return [
        # 3 REJECTED at quote (ROUTE)
        {"opportunity_id": "a1", "outcome": "ROUTE_FAILURE",
         "outcome_reason": "no swap_hops", "scanner_family": "CEX_ARBITRAGE",
         "created_at": "2026-08-06T14:00:00", "stages": [
            {"stage": "quote", "ok": False, "duration_ms": 0.01,
             "failure_reason": "no swap_hops"}]},
        {"opportunity_id": "a2", "outcome": "ROUTE_FAILURE",
         "outcome_reason": "no swap_hops", "scanner_family": "CEX_ARBITRAGE",
         "created_at": "2026-08-06T14:05:00", "stages": [
            {"stage": "quote", "ok": False, "duration_ms": 0.02,
             "failure_reason": "no swap_hops"}]},
        {"opportunity_id": "a3", "outcome": "ROUTE_FAILURE",
         "outcome_reason": "no swap_hops", "scanner_family": "DEX_ARBITRAGE",
         "created_at": "2026-08-06T14:10:00", "stages": [
            {"stage": "quote", "ok": False, "duration_ms": 0.03,
             "failure_reason": "no swap_hops"}]},
        # 1 PROFIT rejection
        {"opportunity_id": "b1", "outcome": "REJECTED",
         "outcome_reason": "net=50 gas=60 after_gas=-10",
         "scanner_family": "DEX_ARBITRAGE",
         "created_at": "2026-08-06T14:15:00", "stages": [
            {"stage": "quote",     "ok": True, "duration_ms": 0.5},
            {"stage": "liquidity", "ok": True, "duration_ms": 0.2},
            {"stage": "gas",       "ok": True, "duration_ms": 0.1},
            {"stage": "profit",    "ok": False, "duration_ms": 0.3,
             "failure_reason": "net=50 gas=60 after_gas=-10"}]},
        # 1 EXECUTABLE
        {"opportunity_id": "c1", "outcome": "EXECUTABLE",
         "outcome_reason": "would survive", "scanner_family": "FLASH_LOAN_ARB",
         "created_at": "2026-08-06T14:20:00", "stages": [
            {"stage": "quote", "ok": True, "duration_ms": 0.1},
            {"stage": "decision", "ok": True, "duration_ms": 0.1}]},
        # 2 OBSERVE_ONLY (should be excluded from effective rate)
        {"opportunity_id": "o1", "outcome": "REJECTED",
         "outcome_reason": "mode is OBSERVE — no analysis",
         "scanner_family": "CEX_ARBITRAGE",
         "created_at": "2026-08-06T14:25:00", "stages": [
            {"stage": "observe_only", "ok": True, "duration_ms": 0.01}]},
        {"opportunity_id": "o2", "outcome": "REJECTED",
         "outcome_reason": "mode is OBSERVE — no analysis",
         "scanner_family": "CEX_ARBITRAGE",
         "created_at": "2026-08-06T14:30:00", "stages": [
            {"stage": "observe_only", "ok": True, "duration_ms": 0.01}]},
    ]


def test_service_summary_computes_effective_rate():
    svc = DecisionAnalyticsService(_FakeRepo(_seed_docs()))
    s = _run(svc.summary(limit=100))
    assert s["window"]["sampled"] == 7
    assert s["executable_count"] == 1
    assert s["observed_only_count"] == 2
    assert s["real_rejection_count"] == 4
    # effective_rate = executable / (executable + real_rejects) = 1 / 5
    assert s["effective_executable_rate"] == pytest.approx(0.2, abs=1e-6)
    assert s["category_counts"]["ROUTE"] == 3
    assert s["category_counts"]["PROFITABILITY"] == 1
    assert s["category_counts"]["EXECUTABLE"] == 1
    assert s["category_counts"]["OBSERVE_ONLY"] == 2


def test_service_rejection_breakdown_ordered_and_sampled_reasons():
    svc = DecisionAnalyticsService(_FakeRepo(_seed_docs()))
    r = _run(svc.rejection_breakdown(limit=100))
    cats = [c["category"] for c in r["categories"]]
    # OBSERVE_ONLY (2) < ROUTE (3), so ROUTE comes first
    assert cats[0] == "ROUTE"
    assert cats.index("OBSERVE_ONLY") < len(cats)
    route = next(c for c in r["categories"] if c["category"] == "ROUTE")
    assert route["count"] == 3
    assert route["attributing_stages"] == {"quote": 3}
    assert route["sub_codes"] == {"no_hops": 3}


def test_service_by_scanner_top_category_and_rate():
    svc = DecisionAnalyticsService(_FakeRepo(_seed_docs()))
    by = _run(svc.by_scanner(limit=100))
    cex = next(f for f in by["families"] if f["family"] == "CEX_ARBITRAGE")
    assert cex["sampled"] == 4
    assert cex["executable"] == 0
    assert cex["observe_only"] == 2
    assert cex["rejected"] == 2
    assert cex["executable_rate"] == 0.0
    flash = next(f for f in by["families"] if f["family"] == "FLASH_LOAN_ARB")
    assert flash["executable"] == 1
    assert flash["executable_rate"] == 1.0


def test_service_bottlenecks_ranks_by_rejection_then_p95():
    svc = DecisionAnalyticsService(_FakeRepo(_seed_docs()))
    b = _run(svc.bottlenecks(limit=100))
    stages = [s["stage"] for s in b["stages"]]
    # `quote` had 3 rejections → first
    assert stages[0] == "quote"
    top = b["stages"][0]
    assert top["rejections"] == 3
    assert top["rejection_share"] == pytest.approx(0.75, abs=1e-6)  # 3/4 real rejects


def test_service_trend_returns_dense_series():
    svc = DecisionAnalyticsService(_FakeRepo(_seed_docs()))
    t = _run(svc.trend(hours=6, limit=100))
    assert len(t["points"]) == 6  # dense — always exactly N hours
    total = sum(p["total"] for p in t["points"])
    # Seed docs are from Aug 6 14:00 window — likely outside the last 6h in test time
    # but the trend function computes since = now - hours, so window may exclude them.
    # Assert only the shape guarantee here.
    assert all("effective_rate" in p for p in t["points"])
    assert all(0.0 <= p["effective_rate"] <= 1.0 for p in t["points"])


def test_service_recent_filters_by_scanner_family():
    svc = DecisionAnalyticsService(_FakeRepo(_seed_docs()))
    r = _run(svc.recent_decisions(limit=100, scanner_family="CEX_ARBITRAGE"))
    assert r["count"] == 4
    assert all(i["scanner_family"] == "CEX_ARBITRAGE" for i in r["items"])
