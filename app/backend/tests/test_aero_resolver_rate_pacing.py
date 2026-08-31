"""Regression for the P0 RPC 429 failure mode: resolve_all must PACE its
underlying eth_calls (configurable min-interval) so the ~4-calls-per-pool burst
across 11 pools doesn't exceed RPC rate limits. Pacing must be disableable
(interval=0) and must restore the original _call afterwards. Fail-closed and
resolution correctness are covered elsewhere (test_m2_6)."""
import asyncio

import pytest

import arbicore.searcher.aero_resolver as A
from arbicore.discovery import base_pool_registry as R


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Rec:
    def __init__(self): self.calls = 0
    async def __call__(self, *a, **k):
        self.calls += 1
        return "0x" + "00" * 32          # zero addr => fail-closed (fine for pacing test)


def _resolver(rec, monkeypatch, ms):
    monkeypatch.setenv("ARBICORE_AERO_POOL_FACTORY_BASE", "0x" + "11" * 20)
    monkeypatch.setenv("ARBICORE_AERO_CL_FACTORY_BASE", "0x" + "22" * 20)
    monkeypatch.setenv("ARBICORE_AERO_RESOLVE_MIN_INTERVAL_MS", ms)
    r = A.build_base_aero_resolver_from_env(rec)
    assert r is not None
    return r


def _aero_pools():
    return [p for p in R.get_canonical_pools()
            if p.dex in ("aerodrome", "aerodrome_slipstream")]


def test_pacing_throttles_calls_and_restores(monkeypatch):
    rec = _Rec()
    r = _resolver(rec, monkeypatch, "20")
    sleeps = []
    async def fake_sleep(s): sleeps.append(s)
    monkeypatch.setattr(A.asyncio, "sleep", fake_sleep)

    _run(r.resolve_all(_aero_pools()))

    assert rec.calls > 0                       # calls were issued
    assert len(sleeps) >= 1                     # pacing engaged between calls
    assert all(s <= 0.020 + 1e-6 for s in sleeps)
    assert "_call" not in r.__dict__            # class method restored cleanly


def test_zero_interval_disables_pacing(monkeypatch):
    rec = _Rec()
    r = _resolver(rec, monkeypatch, "0")
    sleeps = []
    async def fake_sleep(s): sleeps.append(s)
    monkeypatch.setattr(A.asyncio, "sleep", fake_sleep)

    _run(r.resolve_all(_aero_pools()))

    assert rec.calls > 0
    assert sleeps == []                         # no throttle when disabled
    assert "_call" not in r.__dict__


def test_pacing_default_is_applied_when_env_absent(monkeypatch):
    monkeypatch.delenv("ARBICORE_AERO_RESOLVE_MIN_INTERVAL_MS", raising=False)
    rec = _Rec()
    monkeypatch.setenv("ARBICORE_AERO_POOL_FACTORY_BASE", "0x" + "11" * 20)
    monkeypatch.setenv("ARBICORE_AERO_CL_FACTORY_BASE", "0x" + "22" * 20)
    r = A.build_base_aero_resolver_from_env(rec)
    sleeps = []
    async def fake_sleep(s): sleeps.append(s)
    monkeypatch.setattr(A.asyncio, "sleep", fake_sleep)
    _run(r.resolve_all(_aero_pools()))
    assert len(sleeps) >= 1                      # default 150ms pacing active
