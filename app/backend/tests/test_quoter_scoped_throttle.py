"""Regression: quoter RPC throttle must be scoped PER HOST (chain/provider),
not process-wide, so unrelated chains run concurrently while same-host calls
stay paced. Also verifies rate-limit detection/retry, fail-closed behaviour,
and that the Opportunity Race stays uncapped with all safety gates off.
"""
from __future__ import annotations

import asyncio
import time

import pytest

import arbicore.execution.quoter as q


@pytest.fixture(autouse=True)
def _reset_throttle_state(monkeypatch):
    monkeypatch.setattr(q, "_RPC_LOCKS", {}, raising=True)
    monkeypatch.setattr(q, "_RPC_LAST_TS", {}, raising=True)
    yield


# ── A. Independent host scopes run CONCURRENTLY ──────────────────────────────
def test_independent_scopes_are_concurrent(monkeypatch):
    monkeypatch.setattr(q, "_RPC_MIN_INTERVAL_S", 0.20, raising=True)

    async def _run():
        # Prime each host so a subsequent call must wait a full interval.
        await q._throttle("chainA")
        await q._throttle("chainB")
        t0 = time.perf_counter()
        # Two DIFFERENT hosts throttled concurrently → ~one interval, not two.
        await asyncio.gather(q._throttle("chainA"), q._throttle("chainB"))
        return time.perf_counter() - t0

    elapsed = asyncio.run(_run())
    assert elapsed < 0.35, f"independent scopes serialized: {elapsed:.3f}s"


def test_scopes_use_distinct_locks():
    a = q._throttle_lock_for("polygon-host")
    b = q._throttle_lock_for("ethereum-host")
    assert a is not b
    assert q._throttle_lock_for("polygon-host") is a  # stable per scope


def test_throttle_scope_is_host():
    s1 = q._throttle_scope("https://polygon-bor-rpc.publicnode.com")
    s2 = q._throttle_scope("https://polygon-bor-rpc.publicnode.com/v2/x")
    s3 = q._throttle_scope("https://eth.example.com")
    assert s1 == s2 and s1 != s3


# ── B. Same scope remains PACED (flood-safe) ─────────────────────────────────
def test_same_scope_is_paced(monkeypatch):
    monkeypatch.setattr(q, "_RPC_MIN_INTERVAL_S", 0.20, raising=True)

    async def _run():
        t0 = time.perf_counter()
        for _ in range(3):                       # 3 sequential same-host calls
            await q._throttle("samehost")
        return time.perf_counter() - t0

    elapsed = asyncio.run(_run())
    # first call immediate, then 2 waits of ~0.20s each.
    assert elapsed >= 0.35, f"same scope not paced: {elapsed:.3f}s"


def test_concurrent_same_scope_serialized(monkeypatch):
    monkeypatch.setattr(q, "_RPC_MIN_INTERVAL_S", 0.15, raising=True)

    async def _run():
        await q._throttle("h")                    # prime
        t0 = time.perf_counter()
        await asyncio.gather(*(q._throttle("h") for _ in range(3)))
        return time.perf_counter() - t0

    elapsed = asyncio.run(_run())
    assert elapsed >= 0.30, f"same-scope concurrency not paced: {elapsed:.3f}s"


# ── C. Rate-limit detection + retry preserved ────────────────────────────────
def test_rate_limit_detection():
    assert q._is_rate_limited({"code": -32016, "message": "over rate limit"}) is True
    assert q._is_rate_limited({"code": -32000, "message": "too many requests"}) is True
    assert q._is_rate_limited({"message": "RATE LIMIT exceeded"}) is True
    assert q._is_rate_limited({"code": -32000, "message": "revert"}) is False
    assert q._is_rate_limited(None) is False


def test_eth_call_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(q, "_RPC_MIN_INTERVAL_S", 0.0, raising=True)
    calls = {"n": 0}

    class _Resp:
        def __init__(self, status, body):
            self.status_code = status
            self._body = body

        def raise_for_status(self):
            if self.status_code >= 400:
                raise q.httpx.HTTPStatusError("err", request=None, response=self)

        def json(self):
            return self._body

    async def _fake_post(url, payload, timeout):
        calls["n"] += 1
        if calls["n"] == 1:                       # first attempt → 429
            return _Resp(429, {})
        return _Resp(200, [{"id": 1, "result": "0x2a"},
                           {"id": 2, "result": "0x10"}])

    monkeypatch.setattr(q, "_post_json", _fake_post)
    res, bn, err = asyncio.run(q._eth_call(
        "https://h.example/rpc", to="0x1", data="0x", max_retries=3))
    assert err is None and res == "0x2a" and bn == 16
    assert calls["n"] == 2                         # retried once


# ── E. Fail-closed: persistent rate limit → error_dict, never raises ─────────
def test_eth_call_fail_closed_on_persistent_429(monkeypatch):
    monkeypatch.setattr(q, "_RPC_MIN_INTERVAL_S", 0.0, raising=True)

    class _Resp:
        status_code = 429

        def raise_for_status(self):
            raise q.httpx.HTTPStatusError("429", request=None, response=self)

        def json(self):
            return {}

    async def _always_429(url, payload, timeout):
        return _Resp()

    monkeypatch.setattr(q, "_post_json", _always_429)
    res, bn, err = asyncio.run(q._eth_call(
        "https://h.example/rpc", to="0x1", data="0x", max_retries=2))
    assert res is None and bn is None
    assert err is not None and q._is_rate_limited(err)   # fail-closed, no raise


# ── D. Failover mechanism preserved: _eth_call returns error (never raises) so
#      the caller's provider-failover loop can advance to the next provider ───
def test_eth_call_surfaces_error_for_failover(monkeypatch):
    monkeypatch.setattr(q, "_RPC_MIN_INTERVAL_S", 0.0, raising=True)

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return [{"id": 1, "error": {"code": -32000, "message": "boom"}}]

    async def _err(url, payload, timeout):
        return _Resp()

    monkeypatch.setattr(q, "_post_json", _err)
    res, bn, err = asyncio.run(q._eth_call(
        "https://h.example/rpc", to="0x1", data="0x", max_retries=1))
    assert res is None and err and err.get("message") == "boom"


# ── F+G. Opportunity Race stays uncapped; safety gates off ───────────────────
def test_opportunity_race_uncapped_and_safe():
    from arbicore.runtime.opportunity_race import SixChainOpportunityRace, SAFETY_POSTURE
    assert SixChainOpportunityRace()._pairs_cap is None
    for k in ("signing", "broadcast", "auto_execution", "full_live", "withdrawals"):
        assert SAFETY_POSTURE[k] is False


def test_no_global_rpc_lock_symbol():
    # The old process-wide lock must be gone (replaced by per-host locks).
    assert not hasattr(q, "_RPC_LOCK")
    assert isinstance(q._RPC_LOCKS, dict) and isinstance(q._RPC_LAST_TS, dict)
