"""Hybrid E — bounded backlog drain + deferred discovery (offline).

No deploy. No VPS. No worker auto-scaling. B2 / Gate-7 / H05 unchanged.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from arbicore.data.discovery_queue import DiscoveryQueue
from arbicore.models.discovery import (
    DISCOVERY_SUPPORTED_CHAINS,
    DiscoveryCandidate,
    VerifiedOutcome,
)
from arbicore.models.enums import OpportunityType
from arbicore.scanners.flash_loan_arbitrage.scanner import (
    DEFAULT_DISCOVER_REFRESH_S,
    DEFAULT_MAX_BACKLOG_DRAIN_S,
    DEFAULT_MAX_CLAIM_BATCHES_PER_TICK,
    FlashLoanArbitrageScanner,
)
from test_emergent_b2_discovery_queue_fairness import _FakeDB, _cand


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_GATES = {
    "min_atomic_profit_usd": 0.0,
    "min_pool_tvl_usd_in_route": 100_000.0,
    "max_flash_loan_mev_risk_class": "MEDIUM",
    "reporting_atomic_profit_floor_usd": 25.0,
}


def _cfg(**overrides) -> Dict[str, Any]:
    base = {
        "interval_s": 60,
        "default_notional_usd": 10_000.0,
        "verifier_concurrency": 6,
        "max_claim_batches_per_tick": DEFAULT_MAX_CLAIM_BATCHES_PER_TICK,
        "max_backlog_drain_s": DEFAULT_MAX_BACKLOG_DRAIN_S,
        "backlog_skip_discover_min_eligible": 64,
        "discover_refresh_s": DEFAULT_DISCOVER_REFRESH_S,
        "fresh_eligible_window_s": 120.0,
        "providers": {
            "aave_v3": {"enabled": False, "fee_bps": 5},
            "balancer_v2": {"enabled": False, "fee_bps": 0},
            "uniswap_v3": {"enabled": False, "fee_bps_default": 30},
        },
        "chains": {
            c: {"enabled": False, "gas_token": "ETH", "tx_gas_units": 800_000}
            for c in DISCOVERY_SUPPORTED_CHAINS
        },
        "route_search": {
            "max_hops": 4, "wall_clock_cap_s": 0.01,
            "candidate_cap": 4, "min_pool_tvl_usd": 100_000,
        },
        "gate_thresholds": {"default": dict(_GATES)},
        "roi_probability": {"min_sample_size": 2},
        "discovery_sources": {
            "generic_dex": {"enabled": False},
            "triangular": {"enabled": False},
            "balancer_v2": {"enabled": False},
        },
    }
    base.update(overrides)
    return base


class _SpyBus:
    def __init__(self):
        self.emits: List[Any] = []

    async def emit(self, opp, *, venue_ids=None, actor=None):
        self.emits.append(opp)


async def _deny_quote(hm, amt):
    return None  # venue_unreadable path


def _make_scanner(
    *,
    queue: DiscoveryQueue,
    cfg: Optional[Dict[str, Any]] = None,
    enabled: bool = True,
    quote_provider=None,
) -> FlashLoanArbitrageScanner:
    state = {"enabled": enabled}
    return FlashLoanArbitrageScanner(
        emission_bus=_SpyBus(),
        discovery_queue=queue,
        venue_capability_repo=MagicMock(),
        config_loader=lambda: dict(cfg or _cfg()),
        state_loader=lambda: state,
        pool_loader=lambda chain: [],
        quote_provider=quote_provider or _deny_quote,
    )


@pytest.fixture
async def queue():
    q = DiscoveryQueue(_FakeDB())
    await q.ensure_indexes()
    return q


async def _seed_eligible(queue: DiscoveryQueue, n: int, *,
                         chains: Optional[List[str]] = None) -> None:
    chains = list(chains or DISCOVERY_SUPPORTED_CHAINS)
    batch = []
    for i in range(n):
        ch = chains[i % len(chains)]
        batch.append(_cand(f"hyb-{uuid.uuid4().hex[:10]}-{i}", chain=ch))
    await queue.upsert_many(batch)


# ---------------------------------------------------------------------------
# Drain bounds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_max_batches_caps_drain(queue):
    await _seed_eligible(queue, 200)
    scanner = _make_scanner(
        queue=queue,
        cfg=_cfg(max_claim_batches_per_tick=3,
                 max_backlog_drain_s=60.0,
                 backlog_skip_discover_min_eligible=0))
    # skip_min=0 + last_discover set → skip rediscover; drain only.
    scanner._last_discover_at = time.time()
    await scanner._tick()
    assert scanner.stats["drain_batches"] == 3
    assert scanner.stats["candidates_claimed"] == 3 * 32  # floor batch 32


@pytest.mark.asyncio
async def test_max_drain_time_caps_drain(queue, monkeypatch):
    await _seed_eligible(queue, 200)
    scanner = _make_scanner(
        queue=queue,
        cfg=_cfg(max_claim_batches_per_tick=50, max_backlog_drain_s=0.0,
                 backlog_skip_discover_min_eligible=0))
    scanner._last_discover_at = time.time()
    await scanner._tick()
    # drain_s=0 → loop breaks before any claim (elapsed >= 0 immediately
    # after first check... actually first check is at loop entry with
    # elapsed ~0, so >= 0 breaks immediately with 0 batches)
    assert scanner.stats["drain_batches"] == 0


@pytest.mark.asyncio
async def test_empty_backlog_exits_without_verify(queue):
    scanner = _make_scanner(
        queue=queue,
        cfg=_cfg(max_claim_batches_per_tick=6,
                 backlog_skip_discover_min_eligible=999999))
    # Force discover skip? skip_min huge → won't skip; discover runs but
    # sources disabled → no upsert; claim returns [].
    await scanner._tick()
    assert scanner.stats["drain_batches"] == 0
    assert scanner.stats["candidates_claimed"] == 0


@pytest.mark.asyncio
async def test_one_batch_when_backlog_small(queue):
    await _seed_eligible(queue, 10)
    scanner = _make_scanner(
        queue=queue,
        cfg=_cfg(max_claim_batches_per_tick=6,
                 backlog_skip_discover_min_eligible=0))
    scanner._last_discover_at = time.time()
    await scanner._tick()
    assert scanner.stats["drain_batches"] == 1
    assert scanner.stats["candidates_claimed"] == 10


# ---------------------------------------------------------------------------
# Discovery skip / refresh
# ---------------------------------------------------------------------------

def _freeze_route_cfg(scanner: FlashLoanArbitrageScanner) -> None:
    """Prevent C-1 route rebuild from replacing discovery sources mid-test."""
    scanner._route_cfg_sig = scanner._route_sig(scanner._cfg() or {})


def _spy_all_discovers(scanner: FlashLoanArbitrageScanner, counter: Dict[str, int]):
    async def _spy_discover():
        counter["n"] += 1
        return []

    for s in scanner._sources:
        s.discover = _spy_discover  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_discovery_skipped_when_backlog_large_and_fresh(queue):
    await _seed_eligible(queue, 80)
    discover_calls = {"n": 0}

    scanner = _make_scanner(
        queue=queue,
        cfg=_cfg(backlog_skip_discover_min_eligible=64,
                 discover_refresh_s=120.0,
                 max_claim_batches_per_tick=1))
    scanner._last_discover_at = time.time()
    _freeze_route_cfg(scanner)
    _spy_all_discovers(scanner, discover_calls)

    await scanner._tick()
    assert scanner.stats["discover_skipped"] is True
    assert discover_calls["n"] == 0
    assert scanner.stats["drain_batches"] == 1


@pytest.mark.asyncio
async def test_discovery_refresh_forces_rediscover(queue):
    await _seed_eligible(queue, 80)
    discover_calls = {"n": 0}
    scanner = _make_scanner(
        queue=queue,
        cfg=_cfg(backlog_skip_discover_min_eligible=64,
                 discover_refresh_s=120.0,
                 max_claim_batches_per_tick=1))
    # Stale last discover → must refresh
    scanner._last_discover_at = time.time() - 999.0
    _freeze_route_cfg(scanner)
    _spy_all_discovers(scanner, discover_calls)

    await scanner._tick()
    assert scanner.stats["discover_skipped"] is False
    assert discover_calls["n"] == len(scanner._sources)


# ---------------------------------------------------------------------------
# B2 fairness across repeated drain claims
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_b2_fairness_across_repeated_drain_batches(queue):
    # Dense 6-chain backlog
    for ch in DISCOVERY_SUPPORTED_CHAINS:
        await queue.upsert_many(
            [_cand(f"fair-{ch}-{i}", chain=ch) for i in range(20)])
    scanner = _make_scanner(
        queue=queue,
        cfg=_cfg(max_claim_batches_per_tick=3,
                 backlog_skip_discover_min_eligible=0,
                 verifier_concurrency=6))
    scanner._last_discover_at = time.time()
    await scanner._tick()
    assert scanner.stats["drain_batches"] == 3
    # RR cursor advanced; per_chain_claims should cover all six
    caps = scanner.stats["capacity"]
    claimed_chains = set(caps["per_chain_claims"].keys())
    assert set(DISCOVERY_SUPPORTED_CHAINS) <= claimed_chains
    # No ethereum monopoly: each chain roughly equal for 96 claims
    counts = [caps["per_chain_claims"].get(ch, 0)
              for ch in DISCOVERY_SUPPORTED_CHAINS]
    assert max(counts) - min(counts) <= 2


@pytest.mark.asyncio
async def test_expired_never_claimed_during_drain(queue):
    await queue.upsert_many([
        _cand("exp-1", chain="base", expires_in=-10.0),
        _cand("ok-1", chain="base", expires_in=600.0),
    ])
    scanner = _make_scanner(
        queue=queue,
        cfg=_cfg(max_claim_batches_per_tick=2,
                 backlog_skip_discover_min_eligible=0))
    scanner._last_discover_at = time.time()
    await scanner._tick()
    assert scanner.stats["candidates_claimed"] == 1
    doc = await queue.get_candidate("exp-1")
    assert doc is not None
    assert doc.get("verified_outcome") is None
    assert doc.get("claimed_until") is None or doc.get("claimed_until") < time.time()


@pytest.mark.asyncio
async def test_claim_ttl_applied_per_batch(queue):
    await _seed_eligible(queue, 5, chains=["base"])
    scanner = _make_scanner(
        queue=queue,
        cfg=_cfg(max_claim_batches_per_tick=1,
                 backlog_skip_discover_min_eligible=0))
    scanner._last_discover_at = time.time()
    # Intercept claim to capture ttl
    seen = {}
    orig = queue.claim_batch

    async def _wrap(worker_id, batch_size=32, claim_ttl_s=60.0):
        seen["ttl"] = claim_ttl_s
        return await orig(worker_id, batch_size=batch_size,
                          claim_ttl_s=claim_ttl_s)

    queue.claim_batch = _wrap  # type: ignore[method-assign]
    await scanner._tick()
    assert seen["ttl"] >= 120.0


@pytest.mark.asyncio
async def test_no_duplicate_claim_across_batches(queue):
    await _seed_eligible(queue, 40)
    scanner = _make_scanner(
        queue=queue,
        cfg=_cfg(max_claim_batches_per_tick=2,
                 backlog_skip_discover_min_eligible=0))
    scanner._last_discover_at = time.time()
    claimed_ids: List[str] = []
    orig_proc = scanner._process_claimed_candidate

    async def _wrap(c):
        claimed_ids.append(c.candidate_id)
        return await orig_proc(c)

    scanner._process_claimed_candidate = _wrap  # type: ignore[method-assign]
    await scanner._tick()
    assert len(claimed_ids) == len(set(claimed_ids))
    assert len(claimed_ids) == 40


# ---------------------------------------------------------------------------
# Shutdown / cancellation / worker failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shutdown_stops_further_claims(queue):
    await _seed_eligible(queue, 200)
    scanner = _make_scanner(
        queue=queue,
        cfg=_cfg(max_claim_batches_per_tick=10,
                 max_backlog_drain_s=60.0,
                 backlog_skip_discover_min_eligible=0))
    scanner._last_discover_at = time.time()
    claim_n = {"n": 0}
    orig = queue.claim_batch

    async def _wrap(worker_id, batch_size=32, claim_ttl_s=60.0):
        claim_n["n"] += 1
        if claim_n["n"] >= 2:
            scanner._stop.set()
        return await orig(worker_id, batch_size=batch_size,
                          claim_ttl_s=claim_ttl_s)

    queue.claim_batch = _wrap  # type: ignore[method-assign]
    await scanner._tick()
    # After stop set mid-drain, next loop iteration must not claim again
    assert claim_n["n"] <= 2
    assert scanner.stats["drain_batches"] <= 2


@pytest.mark.asyncio
async def test_worker_failure_isolated(queue):
    await _seed_eligible(queue, 6, chains=["base"])
    boom = {"n": 0}
    scanner = _make_scanner(
        queue=queue,
        cfg=_cfg(max_claim_batches_per_tick=1,
                 backlog_skip_discover_min_eligible=0,
                 verifier_concurrency=2),
    )
    scanner._last_discover_at = time.time()
    _freeze_route_cfg(scanner)
    orig_verify = scanner._verifier.verify

    async def _flaky_verify(candidate):
        boom["n"] += 1
        if boom["n"] <= 2:
            raise RuntimeError("boom")
        return await orig_verify(candidate)

    scanner._verifier.verify = _flaky_verify  # type: ignore[method-assign]
    await scanner._tick()
    assert scanner.stats["candidates_claimed"] == 6
    assert scanner.stats["verifier_errors"] >= 2
    status = await queue.queue_status(include_breakdowns=False)
    assert status["claimed_in_flight"] == 0


# ---------------------------------------------------------------------------
# Capacity telemetry surface
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_capacity_telemetry_keys_present(queue):
    await _seed_eligible(queue, 32)
    scanner = _make_scanner(
        queue=queue,
        cfg=_cfg(max_claim_batches_per_tick=1,
                 backlog_skip_discover_min_eligible=0))
    scanner._last_discover_at = time.time()
    await scanner._tick()
    cap = scanner.stats["capacity"]
    for key in (
        "queue_depth", "fresh_eligible_depth", "candidate_arrival_rate",
        "claims_per_min", "verifies_per_min", "worker_active_time",
        "worker_utilization", "per_chain_backlog", "per_chain_claims",
        "per_strategy_backlog", "candidate_age_at_verify", "rpc", "mongo",
    ):
        assert key in cap
    assert cap["claims_per_min"] > 0
    assert cap["verifies_per_min"] > 0
    assert cap["scheduler"]["drain_batches"] == 1


@pytest.mark.asyncio
async def test_disabled_scanner_is_noop(queue):
    await _seed_eligible(queue, 10)
    scanner = _make_scanner(queue=queue, enabled=False)
    await scanner._tick()
    assert scanner.stats["iterations"] == 0
    assert scanner.stats["drain_batches"] == 0
