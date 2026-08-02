"""Sizing targets — resolves live sizing inputs for the Approval workflow.

Pure read-only. Mirrors but never modifies the buy_price authority chain,
wallet_observer config, or HDA snapshots.

Sources for `available_balance_usd` (priority order):
  1) BSC USDT balance via BSCScan if operator_bsc_address + bscscan_api_key set
  2) Coinstore signed USDT balance (if execution_config.use_coinstore_balance_as_funding)
  3) execution_config.manual_available_balance_usd (operator-set fallback)
  4) None (proposer skips)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

from services import db
from services.execution import drift_runner as drift_runner_mod

logger = logging.getLogger("sizing")

BDAG_SWAP_MIN_USD = 50.0  # fixed
DEFAULT_RISK_LIMIT_USD = 200.0
DEFAULT_DAILY_LIMIT_USD = 500.0


async def _bsc_usdt_balance(addr: str, api_key: str) -> float | None:
    """Read USDT BEP-20 balance on BSC via BSCScan free API. Returns USD amount
    (1 USDT ≈ 1 USD). None on any error."""
    if not addr or not api_key:
        return None
    url = ("https://api.bscscan.com/api?module=account&action=tokenbalance"
           "&contractaddress=0x55d398326f99059fF775485246999027B3197955"
           f"&address={addr}&tag=latest&apikey={api_key}")
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(url)
            d = r.json()
            if d.get("status") != "1":
                return None
            return int(d["result"]) / 1e18
    except Exception as e:  # noqa: BLE001
        logger.debug("bsc_usdt_balance failed: %s", e)
        return None


async def _execution_config() -> dict:
    doc = await db.db.execution_config.find_one({}, {"_id": 0}) or {}
    return doc


async def _daily_used_usd() -> float:
    """Sum of `input_amount_usd` for cycles created today (UTC) that aren't REJECTED."""
    start_of_day = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0).isoformat()
    cur = db.db.arbitrage_cycles.find(
        {"created_at": {"$gte": start_of_day},
         "state": {"$nin": ["REJECTED", "ABORTED"]}},
        {"input_amount_usd": 1, "_id": 0})
    total = 0.0
    async for d in cur:
        try:
            total += float(d.get("input_amount_usd") or 0)
        except (TypeError, ValueError):
            pass
    return round(total, 2)


async def compute_targets() -> dict:
    """Compute the full sizing-targets payload."""
    cfg = await _execution_config()

    # 1. available balance — priority resolution chain
    avail: float | None = None
    source: str | None = None

    # BSC USDT
    obs_cfg = await db.db.observer_config.find_one({}, {"_id": 0}) or {}
    bsc_addr = obs_cfg.get("operator_bsc_address")
    bsc_key = obs_cfg.get("bscscan_api_key")
    if bsc_addr and bsc_key:
        bal = await _bsc_usdt_balance(bsc_addr, bsc_key)
        if bal is not None:
            avail, source = bal, "bsc_wallet"

    # Coinstore (if explicitly opted in)
    if avail is None and cfg.get("use_coinstore_balance_as_funding"):
        latest_bal = await db.db.balance_snapshots.find_one(
            {"exchange": "coinstore"}, {"_id": 0},
            sort=[("created_at", -1)])
        cs_usdt = ((latest_bal or {}).get("balances") or {}).get("USDT", {}).get("available")
        if cs_usdt:
            try:
                avail, source = float(cs_usdt), "coinstore_balance"
            except (TypeError, ValueError):
                pass

    # Manual fallback
    if avail is None:
        m = cfg.get("manual_available_balance_usd")
        if m is not None:
            try:
                avail, source = float(m), "manual_config"
            except (TypeError, ValueError):
                pass

    # 2. HDA sizing
    hda = await drift_runner_mod.latest(symbol="BDAGUSDT", venue="coinstore")
    cap = (hda or {}).get("opportunity_capacity") or {}
    recommended = cap.get("recommended_buy_usd")
    max_safe = cap.get("max_buy_usd")

    # 3. limits
    risk_limit = float(cfg.get("risk_limit_per_cycle_usd") or DEFAULT_RISK_LIMIT_USD)
    daily_limit = float(cfg.get("daily_limit_usd") or DEFAULT_DAILY_LIMIT_USD)
    daily_used = await _daily_used_usd()
    daily_remaining = max(0.0, daily_limit - daily_used)

    # 4. verification-sizes set
    raw = set()
    raw.add(BDAG_SWAP_MIN_USD)
    if recommended and recommended >= BDAG_SWAP_MIN_USD:
        clipped = min(float(recommended), max_safe) if max_safe else float(recommended)
        if clipped >= BDAG_SWAP_MIN_USD:
            raw.add(round(clipped, 2))
    if avail and avail >= BDAG_SWAP_MIN_USD:
        clipped = min(float(avail), max_safe) if max_safe else float(avail)
        if clipped >= BDAG_SWAP_MIN_USD:
            raw.add(round(clipped, 2))
    sizes = sorted(raw)

    feasible = bool(avail and avail >= BDAG_SWAP_MIN_USD)

    return {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "min_buy_usd": BDAG_SWAP_MIN_USD,
        "available_balance_usd": (round(avail, 2) if avail is not None else None),
        "available_source": source,
        "recommended_buy_usd": (round(recommended, 2) if recommended else None),
        "max_safe_buy_usd": (round(max_safe, 2) if max_safe else None),
        "risk_limit_usd": risk_limit,
        "daily_limit_usd": daily_limit,
        "daily_used_usd": daily_used,
        "daily_remaining_usd": daily_remaining,
        "verification_sizes_usd": sizes,
        "feasible": feasible,
        "blockers": _blockers(avail, recommended, daily_remaining),
    }


def _blockers(avail, recommended, daily_remaining) -> list[str]:
    out = []
    if avail is None:
        out.append("available_balance_unresolved — set BSC+key or manual_available_balance_usd")
    elif avail < BDAG_SWAP_MIN_USD:
        out.append(f"available_balance ${avail:.2f} below BDAG floor ${BDAG_SWAP_MIN_USD}")
    if recommended is None:
        out.append("hda_recommended_buy_unavailable — drift snapshot empty")
    if daily_remaining < BDAG_SWAP_MIN_USD:
        out.append(f"daily_remaining ${daily_remaining:.2f} below BDAG floor")
    return out
