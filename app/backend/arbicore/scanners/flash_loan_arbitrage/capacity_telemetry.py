"""Capacity-manager-ready telemetry for the flash-loan scanner.

Observability only. Does NOT scale workers, claim, or alter B2 / Gate-7 / H05.
A future Capacity Manager can read ``snapshot()`` to map:
  workload → required concurrency → safe active worker count
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional


def _rate_per_min(events: Deque[float], *, now: float, window_s: float) -> float:
    cutoff = now - window_s
    while events and events[0] < cutoff:
        events.popleft()
    if window_s <= 0:
        return 0.0
    return (len(events) / window_s) * 60.0


def _percentile(xs: List[float], p: float) -> Optional[float]:
    if not xs:
        return None
    ordered = sorted(xs)
    if len(ordered) == 1:
        return float(ordered[0])
    idx = int(round((len(ordered) - 1) * (p / 100.0)))
    idx = max(0, min(len(ordered) - 1, idx))
    return float(ordered[idx])


class CapacityTelemetry:
    """Rolling-window counters for Capacity Manager inputs."""

    def __init__(self, *, rate_window_s: float = 60.0) -> None:
        self.rate_window_s = float(rate_window_s)
        self.started_at = time.time()
        self._claim_events: Deque[float] = deque()
        self._verify_events: Deque[float] = deque()
        self._arrival_events: Deque[float] = deque()
        self.per_chain_claims: Dict[str, int] = {}
        self.candidate_ages_s: Deque[float] = deque(maxlen=512)
        self.mongo_latencies_ms: Deque[float] = deque(maxlen=256)
        self.mongo_errors: int = 0
        self.rpc_proxy: Dict[str, Any] = {
            "source": "verifier_outcomes_proxy",
            "note": (
                "No dedicated RPC latency registry on the scanner path; "
                "proxy uses verifier_errors / denied_venue_unreadable."
            ),
            "verifier_errors": 0,
            "denied_venue_unreadable": 0,
        }
        # Last tick / drain fields
        self.queue_depth: Optional[int] = None
        self.fresh_eligible_depth: Optional[int] = None
        self.per_chain_backlog: Dict[str, int] = {}
        self.per_strategy_backlog: Dict[str, int] = {}
        self.discover_skipped: bool = False
        self.drain_batches: int = 0
        self.drain_candidates: int = 0
        self.drain_duration_s: Optional[float] = None
        self.worker_active_time_s: float = 0.0
        self.worker_configured: int = 0
        self.last_drain_wall_s: Optional[float] = None

    def record_claims(self, n: int, *, chains: Optional[List[Optional[str]]] = None) -> None:
        now = time.time()
        for _ in range(max(0, int(n))):
            self._claim_events.append(now)
        if chains:
            for ch in chains:
                key = (ch or "legacy").lower()
                self.per_chain_claims[key] = self.per_chain_claims.get(key, 0) + 1

    def record_verifies(self, n: int = 1) -> None:
        now = time.time()
        for _ in range(max(0, int(n))):
            self._verify_events.append(now)

    def record_arrivals(self, n: int) -> None:
        now = time.time()
        for _ in range(max(0, int(n))):
            self._arrival_events.append(now)

    def record_candidate_age(self, age_s: float) -> None:
        if age_s >= 0:
            self.candidate_ages_s.append(float(age_s))

    def record_mongo(self, latency_ms: float, *, error: bool = False) -> None:
        self.mongo_latencies_ms.append(float(latency_ms))
        if error:
            self.mongo_errors += 1

    def update_queue_snapshot(self, status: Dict[str, Any]) -> None:
        self.queue_depth = status.get("unclaimed_eligible")
        self.fresh_eligible_depth = status.get("fresh_eligible")
        pc = status.get("per_chain_backlog")
        if isinstance(pc, dict):
            self.per_chain_backlog = {str(k): int(v) for k, v in pc.items()}
        ps = status.get("per_strategy_backlog")
        if isinstance(ps, dict):
            self.per_strategy_backlog = {str(k): int(v) for k, v in ps.items()}

    def set_rpc_proxy(self, *, verifier_errors: int,
                      denied_venue_unreadable: int) -> None:
        self.rpc_proxy["verifier_errors"] = int(verifier_errors)
        self.rpc_proxy["denied_venue_unreadable"] = int(denied_venue_unreadable)

    def note_worker_active(self, active_time_s: float, *,
                           workers: int, drain_wall_s: Optional[float]) -> None:
        self.worker_active_time_s = float(active_time_s)
        self.worker_configured = int(workers)
        self.last_drain_wall_s = (
            float(drain_wall_s) if drain_wall_s is not None else None)

    def _rpc_snapshot(self) -> Dict[str, Any]:
        out = dict(self.rpc_proxy)
        try:
            from arbicore.execution.quoter import rpc_429_telemetry_snapshot
            out["quoter_429"] = rpc_429_telemetry_snapshot()
        except Exception:  # noqa: BLE001 — telemetry must never break status
            out["quoter_429"] = {"error": "unavailable"}
        return out

    def snapshot(self) -> Dict[str, Any]:
        now = time.time()
        window = self.rate_window_s
        ages = list(self.candidate_ages_s)
        mongo = list(self.mongo_latencies_ms)
        util = None
        if (self.worker_configured > 0
                and self.last_drain_wall_s
                and self.last_drain_wall_s > 0):
            capacity = self.worker_configured * self.last_drain_wall_s
            if capacity > 0:
                util = min(1.0, self.worker_active_time_s / capacity)
        return {
            "queue_depth": self.queue_depth,
            "fresh_eligible_depth": self.fresh_eligible_depth,
            "candidate_arrival_rate": _rate_per_min(
                self._arrival_events, now=now, window_s=window),
            "claims_per_min": _rate_per_min(
                self._claim_events, now=now, window_s=window),
            "verifies_per_min": _rate_per_min(
                self._verify_events, now=now, window_s=window),
            "worker_active_time": self.worker_active_time_s,
            "worker_utilization": util,
            "worker_configured": self.worker_configured,
            "per_chain_backlog": dict(self.per_chain_backlog),
            "per_chain_claims": dict(self.per_chain_claims),
            "per_strategy_backlog": dict(self.per_strategy_backlog),
            "candidate_age_at_verify": {
                "n": len(ages),
                "min_s": min(ages) if ages else None,
                "max_s": max(ages) if ages else None,
                "mean_s": (sum(ages) / len(ages)) if ages else None,
                "p50_s": _percentile(ages, 50),
                "p95_s": _percentile(ages, 95),
            },
            "rpc": self._rpc_snapshot(),
            "mongo": {
                "error_count": self.mongo_errors,
                "latency_n": len(mongo),
                "latency_ms_min": min(mongo) if mongo else None,
                "latency_ms_max": max(mongo) if mongo else None,
                "latency_ms_mean": (sum(mongo) / len(mongo)) if mongo else None,
                "latency_ms_p50": _percentile(mongo, 50),
                "latency_ms_p95": _percentile(mongo, 95),
                "source": "scanner_local_op_timing",
            },
            "scheduler": {
                "discover_skipped": self.discover_skipped,
                "drain_batches": self.drain_batches,
                "drain_candidates": self.drain_candidates,
                "drain_duration_s": self.drain_duration_s,
                "rate_window_s": window,
                "uptime_s": now - self.started_at,
            },
        }
