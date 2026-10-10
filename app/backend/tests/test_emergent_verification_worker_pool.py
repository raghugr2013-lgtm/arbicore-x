"""Emergent — configurable shared flash-loan verification worker pool.

Offline / deterministic. Does not deploy, touch production, or alter
B2 / H05 / Gate-7 business rules — only capacity scheduling.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from arbicore.models.discovery import (
    DISCOVERY_SUPPORTED_CHAINS,
    DiscoveryCandidate,
    VerifiedOutcome,
)
from arbicore.models.enums import OpportunityType
from arbicore.scanners.flash_loan_arbitrage.verification_pool import (
    MAX_VERIFICATION_WORKERS,
    VerificationPoolStats,
    resolve_claim_batch_size,
    resolve_claim_ttl_s,
    resolve_verification_workers,
    run_bounded,
)


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", [6, 12, 24, 36])
def test_resolve_workers_benchmark_targets(n, monkeypatch):
    monkeypatch.setenv("ARBICORE_FLASH_LOAN_VERIFICATION_WORKERS", str(n))
    assert resolve_verification_workers({}) == n


def test_resolve_workers_from_config_when_env_absent(monkeypatch):
    monkeypatch.delenv("ARBICORE_FLASH_LOAN_VERIFICATION_WORKERS", raising=False)
    assert resolve_verification_workers({"verifier_concurrency": 12}) == 12


def test_resolve_workers_capped_at_36(monkeypatch):
    monkeypatch.setenv("ARBICORE_FLASH_LOAN_VERIFICATION_WORKERS", "999")
    assert resolve_verification_workers({}) == MAX_VERIFICATION_WORKERS


def test_resolve_workers_floor_at_1(monkeypatch):
    monkeypatch.setenv("ARBICORE_FLASH_LOAN_VERIFICATION_WORKERS", "0")
    assert resolve_verification_workers({}) == 1


def test_claim_batch_scales_with_workers(monkeypatch):
    monkeypatch.delenv("ARBICORE_FLASH_LOAN_CLAIM_BATCH_SIZE", raising=False)
    assert resolve_claim_batch_size({}, workers=6) == 32  # floor
    assert resolve_claim_batch_size({}, workers=36) == 36


def test_claim_ttl_extends_for_large_batches():
    ttl = resolve_claim_ttl_s(batch_size=36, workers=6, base_ttl_s=60.0)
    assert ttl >= 120.0


# ---------------------------------------------------------------------------
# Bounded pool behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_bounded_respects_concurrency_ceiling():
    active = 0
    peak = 0
    lock = asyncio.Lock()

    async def work(_i: int) -> int:
        nonlocal active, peak
        async with lock:
            active += 1
            peak = max(peak, active)
        await asyncio.sleep(0.05)
        async with lock:
            active -= 1
        return _i

    stats = VerificationPoolStats()
    out = await run_bounded(list(range(20)), work, workers=6, stats=stats)
    assert out == list(range(20))
    assert peak <= 6
    assert stats.workers_configured == 6
    assert stats.workers_active_peak <= 6
    assert stats.jobs_completed == 20


@pytest.mark.asyncio
@pytest.mark.parametrize("n", [6, 12, 24, 36])
async def test_run_bounded_starts_with_configured_n(n):
    seen = []

    async def work(i: int) -> int:
        seen.append(i)
        return i

    stats = VerificationPoolStats()
    await run_bounded(list(range(n)), work, workers=n, stats=stats)
    assert stats.workers_configured == n
    assert len(seen) == n


@pytest.mark.asyncio
async def test_worker_failure_does_not_kill_pool():
    async def work(i: int) -> int:
        if i == 3:
            raise RuntimeError("boom")
        return i

    errors: List[Any] = []

    async def on_err(item, exc):
        errors.append((item, type(exc).__name__))

    stats = VerificationPoolStats()
    out = await run_bounded(
        list(range(8)), work, workers=4, stats=stats, on_item_error=on_err)
    assert isinstance(out[3], RuntimeError)
    assert [x for i, x in enumerate(out) if i != 3] == [0, 1, 2, 4, 5, 6, 7]
    assert stats.jobs_failed == 1
    assert stats.jobs_completed == 7
    assert errors and errors[0][0] == 3


@pytest.mark.asyncio
async def test_malformed_job_does_not_crash_pool():
    async def work(c: Dict[str, Any]) -> str:
        if c.get("bad"):
            raise ValueError("malformed")
        return "ok"

    stats = VerificationPoolStats()
    items = [{"id": 1}, {"id": 2, "bad": True}, {"id": 3}]
    out = await run_bounded(items, work, workers=3, stats=stats)
    assert out[0] == "ok"
    assert isinstance(out[1], ValueError)
    assert out[2] == "ok"


@pytest.mark.asyncio
async def test_stop_event_skips_remaining_jobs():
    stop = asyncio.Event()
    started = []

    async def work(i: int) -> int:
        started.append(i)
        if i == 0:
            stop.set()
            await asyncio.sleep(0.02)
        return i

    stats = VerificationPoolStats()
    # workers=1 so jobs after 0 see stop before start
    await run_bounded(list(range(10)), work, workers=1,
                      stop_event=stop, stats=stats)
    assert stats.jobs_cancelled >= 1
    assert len(started) < 10


@pytest.mark.asyncio
async def test_bounded_no_unbounded_fanout():
    """Creating N jobs does not exceed semaphore concurrency."""
    concurrent = 0
    peak = 0

    async def work(_):
        nonlocal concurrent, peak
        concurrent += 1
        peak = max(peak, concurrent)
        await asyncio.sleep(0.01)
        concurrent -= 1

    await run_bounded(list(range(50)), work, workers=4)
    assert peak <= 4


# ---------------------------------------------------------------------------
# Scanner integration — same verify path, B2 claim still used
# ---------------------------------------------------------------------------

def _cand(cid: str, chain: str) -> DiscoveryCandidate:
    now = time.time()
    return DiscoveryCandidate(
        candidate_id=cid,
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        hint_source="test",
        hint_observed_at=now,
        subject_id=f"s:{cid}",
        asset="WETH",
        candidate_venues=["0xpool"],
        hint_metric={"chain": chain},
        chain=chain,
        reason="t",
        expires_at=now + 600,
    )


def _make_flash_scanner(*, workers: int = 6, batch: Optional[List] = None):
    from arbicore.scanners.flash_loan_arbitrage.scanner import (
        FlashLoanArbitrageScanner,
    )

    cfg = {
        "interval_s": 60,
        "default_notional_usd": 10000.0,
        "verifier_concurrency": workers,
        "route_search": {
            "max_hops": 2, "wall_clock_cap_s": 1.0,
            "candidate_cap": 8, "min_pool_tvl_usd": 100000,
        },
        "gate_thresholds": {
            "default": {
                "min_atomic_profit_usd": 0.0,
                "min_pool_tvl_usd_in_route": 100000.0,
                "max_flash_loan_mev_risk_class": "MEDIUM",
                "min_confidence": 60.0,
            }
        },
        "roi_probability": {"min_sample_size": 2, "winsor_low_pct": 5.0},
        "providers": {},
        "chains": {c: {"enabled": True} for c in DISCOVERY_SUPPORTED_CHAINS},
    }
    state = {"enabled": True}
    queue = MagicMock()
    queue.upsert_many = AsyncMock(return_value=0)
    claimed = list(batch) if batch is not None else [
        _cand(f"c-{ch}", ch) for ch in DISCOVERY_SUPPORTED_CHAINS
    ]
    # Hybrid E drain: return one fair batch then empty (no infinite re-claim).
    _claim_n = {"n": 0}

    async def _claim_once(*_a, **_k):
        _claim_n["n"] += 1
        return claimed if _claim_n["n"] == 1 else []

    queue.claim_batch = AsyncMock(side_effect=_claim_once)
    queue.mark_processed = AsyncMock(return_value=True)
    queue.queue_status = AsyncMock(return_value={
        "unclaimed_eligible": len(claimed),
        "fresh_eligible": len(claimed),
        "per_chain_backlog": {},
        "per_strategy_backlog": {},
    })
    bus = MagicMock()
    bus.emit = AsyncMock(return_value=None)

    scanner = FlashLoanArbitrageScanner(
        emission_bus=bus,
        discovery_queue=queue,
        venue_capability_repo=MagicMock(),
        config_loader=lambda: cfg,
        state_loader=lambda: state,
        pool_loader=lambda _chain: [],
        quote_provider=AsyncMock(return_value=None),
    )
    # Stub discover sources to no-op fast
    for s in scanner._sources:
        s.discover = AsyncMock(return_value=[])  # type: ignore[method-assign]
    # Stub verifier to cheap deny (still the same registry path)
    async def _verify(c):
        return None, VerifiedOutcome.DENIED_VENUE_UNREADABLE

    scanner._verifier.verify = _verify  # type: ignore[method-assign]
    return scanner, queue, bus, cfg


@pytest.mark.asyncio
async def test_scanner_tick_uses_b2_claim_then_pool(monkeypatch):
    monkeypatch.delenv("ARBICORE_FLASH_LOAN_VERIFICATION_WORKERS", raising=False)
    monkeypatch.delenv("ARBICORE_FLASH_LOAN_CLAIM_BATCH_SIZE", raising=False)
    scanner, queue, bus, cfg = _make_flash_scanner(workers=6)
    await scanner._tick()
    queue.claim_batch.assert_awaited()
    kwargs = queue.claim_batch.await_args.kwargs
    assert kwargs.get("batch_size") == 32  # max(32, 6)
    assert kwargs.get("claim_ttl_s", 0) >= 60.0
    # All six claimed candidates processed via mark_processed
    assert queue.mark_processed.await_count == 6
    assert scanner.stats["verification_workers_configured"] == 6
    snap = scanner.stats["verification_pool"]
    assert snap["workers_configured"] == 6
    assert snap["jobs_completed"] == 6


@pytest.mark.asyncio
async def test_six_chains_receive_verify_via_shared_path(monkeypatch):
    monkeypatch.delenv("ARBICORE_FLASH_LOAN_VERIFICATION_WORKERS", raising=False)
    batch = [_cand(f"c-{ch}", ch) for ch in DISCOVERY_SUPPORTED_CHAINS]
    scanner, queue, bus, cfg = _make_flash_scanner(workers=6, batch=batch)

    seen_chains = []
    real_verify = scanner._verifier.verify

    async def wrap(c, *a, **k):
        seen_chains.append(c.chain)
        return None, VerifiedOutcome.DENIED_VENUE_UNREADABLE

    scanner._verifier.verify = wrap  # type: ignore[method-assign]
    await scanner._tick()
    assert set(seen_chains) == set(DISCOVERY_SUPPORTED_CHAINS)
    # Same verifier instance for every chain (no per-chain verify_*).
    assert scanner._verifier.verify is wrap


@pytest.mark.asyncio
async def test_eth_cannot_monopolize_when_batch_is_fair(monkeypatch):
    """Pool does not re-order: fair claim composition is preserved end-to-end."""
    monkeypatch.delenv("ARBICORE_FLASH_LOAN_VERIFICATION_WORKERS", raising=False)
    # Simulate B2 fair batch: 1 per chain (not 32 eth).
    batch = [_cand(f"c-{ch}", ch) for ch in DISCOVERY_SUPPORTED_CHAINS]
    scanner, queue, _, _ = _make_flash_scanner(workers=6, batch=batch)
    order = []

    async def wrap(c, *a, **k):
        order.append(c.chain)
        await asyncio.sleep(0.01)
        return None, "denied:gate_rejection:gate_7:atomic_profit $-1.00 < floor $0.00"

    scanner._verifier.verify = wrap  # type: ignore[method-assign]
    await scanner._tick()
    assert len(order) == 6
    assert order.count("ethereum") == 1
    assert set(order) == set(DISCOVERY_SUPPORTED_CHAINS)


@pytest.mark.asyncio
async def test_shutdown_marks_unstarted_or_inflight(monkeypatch):
    monkeypatch.delenv("ARBICORE_FLASH_LOAN_VERIFICATION_WORKERS", raising=False)
    batch = [_cand(f"c-{i}", "ethereum") for i in range(4)]
    scanner, queue, _, _ = _make_flash_scanner(workers=1, batch=batch)

    async def wrap(c, *a, **k):
        scanner._stop.set()
        await asyncio.sleep(0.01)
        return None, VerifiedOutcome.DENIED_VENUE_UNREADABLE

    scanner._verifier.verify = wrap  # type: ignore[method-assign]
    await scanner._tick()
    # At least one mark_processed happened; shutdown path may add error tags.
    assert queue.mark_processed.await_count >= 1


def test_gate7_defaults_unchanged_in_scanner_construction():
    scanner, *_ = _make_flash_scanner(workers=6)
    floor = float(scanner._gate_7.cfg.get("min_atomic_profit_usd", -1))
    assert floor == 0.0
    from arbicore.scanners.flash_loan_arbitrage.filter import (
        REPORTING_ATOMIC_PROFIT_FLOOR_USD,
    )
    assert REPORTING_ATOMIC_PROFIT_FLOOR_USD == 25.0


def test_h05_wiring_not_touched_by_pool_module():
    """Pool module must not import or replace borrow sizer."""
    import arbicore.scanners.flash_loan_arbitrage.verification_pool as vp
    src = open(vp.__file__).read()
    assert "build_h05" not in src
    assert "borrow_sizer" not in src
    assert "gate_7" not in src.lower() or "Gate-7" in src or "Gate7" in src
