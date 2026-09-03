"""M3.0 · Atomic Pre-Broadcast Revalidation & Circuit Breakers.

The final, fail-closed safety layer that runs INSIDE the single broadcast path
(:mod:`arbicore.execution.broadcast`) immediately before signing. Its job: a
transaction may be signed/broadcast ONLY when a FRESH re-check of the market
(re-quote, re-TVL, re-price, re-economics), freshness (block/reorg/deadline),
flash-loan availability, duplicate-opportunity, safety buffer, and the circuit
breaker ALL pass. Any None / stale / error / mismatch → DENIED → no broadcast.

Everything is injectable (async ``fresh_fn`` supplies genuine current values) so
it is deterministically testable offline; nothing here fabricates a value.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional


def _cfg_f(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, "") or default)
    except (TypeError, ValueError):
        return default


def _cfg_i(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, "") or default)
    except (TypeError, ValueError):
        return default


# ── fresh values fetched at broadcast time (all from genuine on-chain reads) ──
@dataclass
class RevalidationInputs:
    block_number: Optional[int]
    quoted_block: Optional[int]
    now_ts: float
    deadline_ts: Optional[float]
    net_profit_usd: Optional[float]
    min_tvl_usd: Optional[float]
    quote_ok: bool
    price_ok: bool
    mev_ok: bool
    flashloan_available: Optional[bool]
    opp_fingerprint: str


@dataclass
class PreBroadcastDecision:
    ok: bool
    gate: Dict[str, str] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)


class SeenOpportunityGuard:
    """TTL de-dupe: refuse an opportunity already claimed within the window."""

    def __init__(self, ttl_s: float = 30.0, clock: Callable[[], float] = None):
        import time as _t
        self._ttl = float(ttl_s)
        self._clock = clock or _t.monotonic
        self._seen: Dict[str, float] = {}

    def _sweep(self, now: float) -> None:
        for k in [k for k, exp in self._seen.items() if exp <= now]:
            self._seen.pop(k, None)

    def seen(self, fp: str) -> bool:
        now = self._clock()
        self._sweep(now)
        return fp in self._seen

    def claim(self, fp: str) -> None:
        self._seen[fp] = self._clock() + self._ttl


class PreBroadcastValidator:
    """Fresh final gate. ``fresh_fn(plan) -> RevalidationInputs|None`` MUST read
    genuine current chain/market state (None ⇒ fail closed)."""

    def __init__(
        self, *,
        fresh_fn: Callable[[Dict[str, Any]], Awaitable[Optional[RevalidationInputs]]],
        dedupe: Optional[SeenOpportunityGuard] = None,
        min_net_profit_usd: Optional[float] = None,
        safety_buffer_usd: Optional[float] = None,
        max_block_lag: Optional[int] = None,
    ) -> None:
        self._fresh = fresh_fn
        self._dedupe = dedupe or SeenOpportunityGuard(
            ttl_s=_cfg_f("ARBICORE_DEDUPE_TTL_S", 30.0))
        self._min_profit = (min_net_profit_usd if min_net_profit_usd is not None
                            else _cfg_f("ARBICORE_MIN_NET_PROFIT_USD", 25.0))
        self._buffer = (safety_buffer_usd if safety_buffer_usd is not None
                        else _cfg_f("ARBICORE_SAFETY_BUFFER_USD", 10.0))
        self._max_lag = (max_block_lag if max_block_lag is not None
                         else _cfg_i("ARBICORE_PRICE_MAX_BLOCK_LAG", 5))

    async def validate(self, plan: Dict[str, Any]) -> PreBroadcastDecision:
        g: Dict[str, str] = {}
        r: List[str] = []

        def deny(name: str, reason: str) -> None:
            g[name] = "DENIED"
            r.append(f"{name}: {reason}")

        try:
            inp = await self._fresh(plan)
        except Exception as exc:  # noqa: BLE001 — any error ⇒ fail closed
            return PreBroadcastDecision(
                False, {"revalidation": "DENIED"},
                [f"revalidation: fresh read raised {type(exc).__name__}"])
        if inp is None:
            return PreBroadcastDecision(
                False, {"revalidation": "DENIED"},
                ["revalidation: fresh market read unavailable"])

        # freshness + reorg
        if inp.block_number is None or inp.quoted_block is None:
            deny("block_freshness", "block number unavailable")
        elif inp.block_number < inp.quoted_block:
            deny("reorg_protection",
                 f"head {inp.block_number} < quoted {inp.quoted_block}")
        elif (inp.block_number - inp.quoted_block) > self._max_lag:
            deny("block_freshness",
                 f"lag {inp.block_number - inp.quoted_block} > {self._max_lag}")
        else:
            g["block_freshness"] = "PASS"
            g["reorg_protection"] = "PASS"

        # deadline
        if inp.deadline_ts is not None and inp.now_ts > inp.deadline_ts:
            deny("deadline", "execution deadline passed")
        else:
            g["deadline"] = "PASS"

        # fresh quote / price / mev
        g["fresh_quote"] = "PASS" if inp.quote_ok else "DENIED"
        if not inp.quote_ok:
            r.append("fresh_quote: re-quote failed/unavailable")
        g["fresh_price"] = "PASS" if inp.price_ok else "DENIED"
        if not inp.price_ok:
            r.append("fresh_price: price stale/unavailable")
        g["mev_risk"] = "PASS" if inp.mev_ok else "DENIED"
        if not inp.mev_ok:
            r.append("mev_risk: over cap")

        # flash-loan availability (real-time)
        if inp.flashloan_available is True:
            g["flashloan_availability"] = "PASS"
        else:
            deny("flashloan_availability", "provider liquidity unavailable")

        # TVL present + positive
        if inp.min_tvl_usd is not None and inp.min_tvl_usd > 0:
            g["liquidity_tvl"] = "PASS"
        else:
            deny("liquidity_tvl", "min route TVL unverifiable")

        # conservative net profit ≥ floor + safety buffer
        required = self._min_profit + self._buffer
        if inp.net_profit_usd is not None and inp.net_profit_usd >= required:
            g["profit_buffer"] = "PASS"
        else:
            deny("profit_buffer",
                 f"net {inp.net_profit_usd} < required {required:.2f} "
                 f"(min {self._min_profit} + buffer {self._buffer})")

        # duplicate-opportunity
        if inp.opp_fingerprint and self._dedupe.seen(inp.opp_fingerprint):
            deny("duplicate_opportunity", "opportunity already in-flight")
        else:
            g["duplicate_opportunity"] = "PASS"

        ok = not r
        if ok and inp.opp_fingerprint:
            self._dedupe.claim(inp.opp_fingerprint)
        return PreBroadcastDecision(ok, g, r)


class CircuitBreaker:
    """Automatic halt on realized-loss / consecutive-failure / health signals.

    Fail-closed: ``status().tripped`` True halts broadcast. ``on_trip`` (e.g.
    kill-switch engage) fires once per transition into tripped."""

    def __init__(
        self, *,
        max_daily_loss_usd: Optional[float] = None,
        max_hourly_loss_usd: Optional[float] = None,
        max_consecutive_failures: Optional[int] = None,
        on_trip: Optional[Callable[[str], Awaitable[None]]] = None,
        clock: Callable[[], float] = None,
    ) -> None:
        import time as _t
        self._clock = clock or _t.time
        self._max_daily = (max_daily_loss_usd if max_daily_loss_usd is not None
                           else _cfg_f("ARBICORE_MAX_DAILY_LOSS_USD", 100.0))
        self._max_hourly = (max_hourly_loss_usd if max_hourly_loss_usd is not None
                            else _cfg_f("ARBICORE_MAX_HOURLY_LOSS_USD", 50.0))
        self._max_consec = (max_consecutive_failures
                            if max_consecutive_failures is not None
                            else _cfg_i("ARBICORE_MAX_CONSEC_FAILURES", 3))
        self._on_trip = on_trip
        self._events: List[tuple] = []          # (ts, pnl, success)
        self._consec_fail = 0
        self._health: Dict[str, bool] = {}      # flag -> ok?
        self._tripped = False

    def record_outcome(self, *, realized_pnl_usd: float, success: bool) -> None:
        self._events.append((self._clock(), float(realized_pnl_usd), bool(success)))
        if success and realized_pnl_usd >= 0:
            self._consec_fail = 0
        else:
            self._consec_fail += 1

    def set_health(self, flag: str, ok: bool) -> None:
        self._health[flag] = bool(ok)

    def _loss_since(self, seconds: float) -> float:
        cutoff = self._clock() - seconds
        return -sum(p for ts, p, _ in self._events if ts >= cutoff and p < 0)

    def status(self) -> Dict[str, Any]:
        reasons: List[str] = []
        daily = self._loss_since(86_400.0)
        hourly = self._loss_since(3_600.0)
        if daily >= self._max_daily:
            reasons.append(f"daily_loss ${daily:.2f} ≥ ${self._max_daily:.2f}")
        if hourly >= self._max_hourly:
            reasons.append(f"hourly_loss ${hourly:.2f} ≥ ${self._max_hourly:.2f}")
        if self._consec_fail >= self._max_consec:
            reasons.append(f"consecutive_failures {self._consec_fail} ≥ {self._max_consec}")
        bad = [f for f, ok in self._health.items() if not ok]
        if bad:
            reasons.append("unhealthy: " + ",".join(sorted(bad)))
        return {"tripped": bool(reasons), "reasons": reasons,
                "daily_loss_usd": round(daily, 2),
                "hourly_loss_usd": round(hourly, 2),
                "consecutive_failures": self._consec_fail}

    async def guard(self) -> Dict[str, Any]:
        st = self.status()
        if st["tripped"] and not self._tripped:
            self._tripped = True
            if self._on_trip is not None:
                try:
                    await self._on_trip("; ".join(st["reasons"]))
                except Exception:  # noqa: BLE001
                    pass
        elif not st["tripped"]:
            self._tripped = False
        return st


__all__ = ["RevalidationInputs", "PreBroadcastDecision", "SeenOpportunityGuard",
           "PreBroadcastValidator", "CircuitBreaker"]
