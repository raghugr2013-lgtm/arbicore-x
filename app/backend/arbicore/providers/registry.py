"""ProviderRegistry — health-aware provider selection with automatic
failover, per-provider circuit breaker, and EWMA latency tracking.

Every business-logic module goes through this registry. The registry
is the *only* place that knows about concrete provider instances.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import (
    Any, Awaitable, Callable, Dict, List, Optional,
)

from .base import (
    BaseProvider, HealthEvent, ProviderError, ProviderHealth,
    ProviderKind, ProviderStatus,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat().replace("+00:00", "Z")


@dataclass
class CircuitBreaker:
    """Per-provider circuit breaker.

    Trip conditions (any of):
      * consecutive failures >= consecutive_failure_threshold
      * failure rate over the last N events >= failure_rate_threshold
    """
    consecutive_failure_threshold: int = 5
    failure_rate_threshold: float = 0.5
    failure_rate_window: int = 20
    open_duration_seconds: float = 60.0

    def should_trip(self, health: ProviderHealth) -> bool:
        if health.consecutive_failures >= self.consecutive_failure_threshold:
            return True
        window = health.last_events[-self.failure_rate_window:]
        if len(window) >= self.failure_rate_window:
            fails = sum(1 for e in window if not e.ok)
            if fails / len(window) >= self.failure_rate_threshold:
                return True
        return False

    def can_close(self, health: ProviderHealth, now: datetime) -> bool:
        if health.circuit_open_until is None:
            return True
        try:
            deadline = datetime.fromisoformat(
                health.circuit_open_until.replace("Z", "+00:00"))
        except Exception:
            return True
        return now >= deadline


class ProviderRegistry:
    """Holds every registered provider + its live health."""

    def __init__(
        self,
        *,
        ewma_alpha: float = 0.2,
        breaker: Optional[CircuitBreaker] = None,
        event_ring: int = 20,
    ) -> None:
        self._providers: Dict[str, BaseProvider] = {}
        self._health: Dict[str, ProviderHealth] = {}
        self._alpha = ewma_alpha
        self._breaker = breaker or CircuitBreaker()
        self._event_ring = event_ring
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # registration
    # ------------------------------------------------------------------

    def register(self, provider: BaseProvider, *,
                 chain: Optional[str] = None,
                 priority: int = 100) -> ProviderHealth:
        h = ProviderHealth(
            provider_id=provider.provider_id,
            kind=provider.kind,
            chain=chain or getattr(provider, "chain", None),
            priority=priority,
        )
        self._providers[provider.provider_id] = provider
        self._health[provider.provider_id] = h
        logger.info(
            "providers: registered id=%s kind=%s chain=%s priority=%d",
            provider.provider_id, provider.kind.value, h.chain, priority)
        return h

    def deregister(self, provider_id: str) -> bool:
        self._providers.pop(provider_id, None)
        return self._health.pop(provider_id, None) is not None

    def get(self, provider_id: str) -> Optional[BaseProvider]:
        return self._providers.get(provider_id)

    def list(self, *, kind: Optional[ProviderKind] = None,
             chain: Optional[str] = None,
             include_tripped: bool = False) -> List[ProviderHealth]:
        rows: List[ProviderHealth] = []
        for h in self._health.values():
            if kind and h.kind != kind:
                continue
            if chain and h.chain and h.chain != chain:
                continue
            if not include_tripped and h.status == ProviderStatus.TRIPPED:
                # reopen if breaker deadline passed
                if self._breaker.can_close(h, _now()):
                    self._transition(h, ProviderStatus.DEGRADED,
                                      reason="breaker_reset")
                else:
                    continue
            rows.append(h)
        # sort by score DESC
        rows.sort(key=lambda h: h.score(), reverse=True)
        return rows

    # ------------------------------------------------------------------
    # health event tracking
    # ------------------------------------------------------------------

    def _transition(self, h: ProviderHealth,
                     new_status: ProviderStatus, *,
                     reason: Optional[str] = None) -> None:
        if h.status == new_status:
            return
        logger.info(
            "providers: %s %s → %s (%s)",
            h.provider_id, h.status.value, new_status.value, reason)
        h.status = new_status
        if new_status == ProviderStatus.TRIPPED:
            h.circuit_open_until = _iso(
                _now() + timedelta(
                    seconds=self._breaker.open_duration_seconds))
        elif new_status != ProviderStatus.TRIPPED:
            h.circuit_open_until = None

    def _record_event(self, h: ProviderHealth, *, ok: bool,
                       latency_ms: float,
                       error: Optional[str] = None) -> None:
        ev = HealthEvent(ts=_iso(), ok=ok, latency_ms=latency_ms,
                          error=error)
        h.last_events.append(ev)
        if len(h.last_events) > self._event_ring:
            h.last_events = h.last_events[-self._event_ring:]

        h.last_latency_ms = latency_ms
        h.ewma_latency_ms = (
            self._alpha * latency_ms +
            (1 - self._alpha) * (h.ewma_latency_ms or latency_ms))

        if ok:
            h.successes += 1
            h.consecutive_failures = 0
            h.last_ok_at = ev.ts
            if h.status == ProviderStatus.DEGRADED:
                self._transition(h, ProviderStatus.HEALTHY,
                                  reason="ok_after_degraded")
        else:
            h.failures += 1
            h.consecutive_failures += 1
            h.last_error_at = ev.ts
            h.last_error = error
            if self._breaker.should_trip(h):
                self._transition(h, ProviderStatus.TRIPPED,
                                  reason="breaker_tripped")
            else:
                self._transition(h, ProviderStatus.DEGRADED,
                                  reason="failure")

    # ------------------------------------------------------------------
    # invocation with automatic failover
    # ------------------------------------------------------------------

    async def call(
        self,
        kind: ProviderKind,
        method: Callable[[BaseProvider], Awaitable[Any]],
        *,
        chain: Optional[str] = None,
        max_attempts: int = 3,
    ) -> Any:
        """Call ``method`` on the healthiest provider of ``kind``.

        On failure, records a health event and fails over to the next
        provider. Raises :class:`ProviderError` only if every candidate
        fails within ``max_attempts``.
        """
        async with self._lock:
            candidates = self.list(kind=kind, chain=chain)
        if not candidates:
            raise ProviderError(
                f"no providers registered for kind={kind.value}"
                + (f" chain={chain}" if chain else ""),
                retryable=False)

        attempts = 0
        last_error: Optional[Exception] = None
        for health in candidates:
            if attempts >= max_attempts:
                break
            provider = self._providers.get(health.provider_id)
            if provider is None:
                continue
            attempts += 1
            t0 = time.time()
            try:
                result = await method(provider)
                self._record_event(
                    health, ok=True, latency_ms=(time.time() - t0) * 1000)
                return result
            except Exception as exc:  # noqa: BLE001
                self._record_event(
                    health, ok=False,
                    latency_ms=(time.time() - t0) * 1000,
                    error=f"{type(exc).__name__}: {exc}")
                last_error = exc
                logger.warning(
                    "providers: %s failed (%s), failing over",
                    health.provider_id, exc)
                continue
        raise ProviderError(
            f"all providers exhausted for kind={kind.value}"
            f" chain={chain}: last_error={last_error!r}",
            retryable=True)

    # ------------------------------------------------------------------
    # observability
    # ------------------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        by_kind: Dict[str, List[Dict[str, Any]]] = {}
        for h in self._health.values():
            by_kind.setdefault(h.kind.value, []).append(h.to_dict())
        for kind, rows in by_kind.items():
            rows.sort(key=lambda r: r["score"], reverse=True)
        return {
            "provider_count": len(self._health),
            "by_kind": by_kind,
            "breaker": {
                "consecutive_failure_threshold":
                    self._breaker.consecutive_failure_threshold,
                "failure_rate_threshold":
                    self._breaker.failure_rate_threshold,
                "open_duration_seconds":
                    self._breaker.open_duration_seconds,
            },
        }
