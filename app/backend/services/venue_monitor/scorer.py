"""Venue scorer + Full Cycle Readiness evaluator.

Scoring inputs (per venue, latest snapshot + recent history):
  - api_health_score        : derived from last N poll outcomes
  - depth_quality           : profitable-buyer-depth at target buy_price
  - liquidity_volume        : 24h quote volume in USD
  - status flags            : deposit_enabled, withdraw_enabled_usdt, trading_active
  - operator_verified flags : deposit_credit_verified (manual), withdraw_credit_verified (manual)

Outputs:
  - venue_health_score      : 0–100
  - full_cycle_readiness    : 6-check object with pass/fail + score (0–6)
  - full_cycle_ready        : bool (all 6 pass)
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

# Tunables (small surface; kept here so they're easy to find)
TARGET_BUY_USD = 50.0                  # min buy size — used for "sufficient depth" check
SUFFICIENT_DEPTH_USD = 200.0           # >= $200 of profitable-buyer-depth
RECENT_HEALTH_WINDOW = 10              # last N poll outcomes for api_health_score


def api_health_from_history(history: list[dict]) -> float:
    """0..1 health score from recent poll outcomes."""
    recent = (history or [])[-RECENT_HEALTH_WINDOW:]
    if not recent:
        return 0.0
    ok_count = sum(1 for r in recent if r.get("ok"))
    return round(ok_count / max(1, len(recent)), 3)


def profitable_buyer_depth_usd(depth: dict | None, target_price: float | None = None) -> float:
    """USD value of bids at or above `target_price`. If target_price is None,
    returns USD value of top-10 bid levels."""
    if not depth or not depth.get("bids"):
        return 0.0
    bids = depth["bids"]
    if target_price is None:
        bids = bids[:10]
        return round(sum(p * q for p, q in bids), 2)
    total = 0.0
    for p, q in bids:
        if p < target_price:
            break  # bids sorted desc
        total += p * q
    return round(total, 2)


def compute_health_score(snapshot: dict, history: list[dict]) -> float:
    """0–100 venue health score blending API health, depth, status."""
    api_h = api_health_from_history(history) * 100  # 0..100
    depth_usd = profitable_buyer_depth_usd(snapshot.get("depth"))
    depth_score = min(100, (depth_usd / 5000.0) * 100)  # $5k → 100
    status = snapshot.get("status") or {}
    flags_passed = sum(1 for v in (status.get("trading_active"),
                                   status.get("deposit_enabled"),
                                   status.get("withdraw_enabled_usdt")) if v is True)
    flags_score = (flags_passed / 3.0) * 100
    # Weighted blend
    return round(api_h * 0.40 + depth_score * 0.30 + flags_score * 0.30, 1)


def evaluate_readiness(snapshot: dict, history: list[dict], intelligence: dict | None) -> dict:
    """Six readiness checks. `intelligence` carries operator-verified flags
    (manual confirmations from prior deposit/withdraw tests)."""
    intel = intelligence or {}
    status = snapshot.get("status") or {}
    depth_usd = profitable_buyer_depth_usd(snapshot.get("depth"))
    api_h = api_health_from_history(history)

    checks = {
        "deposit_open": bool(status.get("deposit_enabled")) if status.get("deposit_enabled") is not None else None,
        "deposit_crediting_verified": bool(intel.get("deposit_credit_verified")),
        "trading_active": bool(status.get("trading_active")) if status.get("trading_active") is not None else None,
        "usdt_withdrawal_available": bool(status.get("withdraw_enabled_usdt")) if status.get("withdraw_enabled_usdt") is not None else None,
        "api_healthy": api_h >= 0.6,
        "sufficient_depth": depth_usd >= SUFFICIENT_DEPTH_USD,
    }
    passed = sum(1 for v in checks.values() if v is True)
    unknown = sum(1 for v in checks.values() if v is None)
    full_cycle_ready = (passed == 6)
    return {
        "checks": checks,
        "passed": passed,
        "unknown": unknown,
        "failed": 6 - passed - unknown,
        "full_cycle_ready": full_cycle_ready,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "evaluated_at_ts": int(time.time()),
        "profitable_buyer_depth_usd": depth_usd,
        "api_health_fraction": api_h,
    }
