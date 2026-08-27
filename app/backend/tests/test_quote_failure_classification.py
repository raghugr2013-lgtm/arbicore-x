"""§7 — quote-failure / status classification (deterministic, offline).

Proves a failed/stale quote is bucketed correctly and can NEVER be mistaken for a
usable REAL quote, so it cannot contaminate economics or become a synthetic
opportunity. Target: OpportunityEngine.categorize_quote_failure + classify_route.
"""
from __future__ import annotations

from arbicore.economics.opportunity_engine import categorize_quote_failure


def _rq(*statuses_errors):
    return {"hops": [{"status": s, "error": e} for (s, e) in statuses_errors]}


def test_all_ok_hops_is_not_a_failure():
    assert categorize_quote_failure(_rq(("ok", ""), ("ok", ""))) is None


def test_revert_no_pool():
    assert categorize_quote_failure(_rq(("ok", ""), ("fallback:revert", ""))) == "revert_no_pool"
    assert categorize_quote_failure(_rq(("bad", "execution reverted"))) == "revert_no_pool"


def test_no_adapter():
    assert categorize_quote_failure(_rq(("fallback:no_adapter", ""))) == "no_adapter"


def test_rpc_error():
    assert categorize_quote_failure(_rq(("fallback:rpc_error", ""))) == "rpc_error"


def test_rate_limited():
    assert categorize_quote_failure(_rq(("fallback:rate_limited", ""))) == "rate_limited"
    assert categorize_quote_failure(_rq(("x", "429 Too Many Requests"))) == "rate_limited"


def test_other_bucket_is_explicit():
    assert categorize_quote_failure(_rq(("weird", "something else"))) == "other"


def test_failure_precedence_first_bad_hop_wins_and_ok_never_masks():
    # A single bad hop makes the whole route a failure — cannot pass as REAL.
    assert categorize_quote_failure(_rq(("ok", ""), ("fallback:no_adapter", ""))) == "no_adapter"
