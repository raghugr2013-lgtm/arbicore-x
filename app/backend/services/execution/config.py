"""Execution config — certification limits + kill-switch flags (E2 scaffold).

DISABLED BY DEFAULT. No flag here ever moves funds on its own; the flags gate a
FUTURE execution layer (E3+). Everything in E2 runs in SIMULATED / DRY-RUN mode
regardless of these flags.
"""
from core.models import now_iso
from services import db

CONFIG_KEY = "execution"

DEFAULTS = {
    "key": CONFIG_KEY,
    "execution_enabled": False,   # global kill switch — OFF (no real side effects ever in E2/E3)
    "wallet_enabled": False,      # automation-wallet signing — OFF
    "hard_freeze": False,         # pauses even in-flight cycles → MANUAL_REVIEW
    "shadow_enabled": False,      # E3 — shadow runner: drives SHADOW cycles off LIVE data, records "would-do", NO execution
    "limits": {
        "max_cycle_usd": 25.0,
        "max_purchase_usd": 25.0,
        "max_daily_volume_usd": 100.0,
        "max_daily_loss_usd": 20.0,
        "max_concurrent_cycles": 1,
        "min_net_spread_pct": 2.0,
        "min_cooldown_s": 60,
        "min_executable_purchase_usd": 50.0,   # BlockDAG Live Swap minimum purchase — a live cycle cannot be placed below this
        "shadow_cycle_size_usd": 25.0,         # size used by the shadow runner / certification campaign (non-executing)
        "shadow_max_cycle_usd": 100.0,         # upper bound for SHADOW-only cycle size (real execution stays capped at max_cycle_usd)
    },
    "funding_assets": ["USDT", "BNB", "ETH"],
    "default_funding_asset": "USDT",
    "withdrawal_whitelist": [],   # operator destination wallet(s); empty = settlement leg is MANUAL
}

LIMIT_KEYS = set(DEFAULTS["limits"].keys())


async def get_config() -> dict:
    doc = await db.execution_config.find_one({"key": CONFIG_KEY}, {"_id": 0})
    if not doc:
        return {**DEFAULTS, "limits": dict(DEFAULTS["limits"])}
    merged = {**DEFAULTS, **doc}
    merged["limits"] = {**DEFAULTS["limits"], **(doc.get("limits") or {})}
    return merged


async def ensure_seeded():
    existing = await db.execution_config.find_one({"key": CONFIG_KEY})
    if not existing:
        await db.execution_config.insert_one({**DEFAULTS, "limits": dict(DEFAULTS["limits"]),
                                              "updated_at": now_iso()})


async def update_config(patch: dict) -> dict:
    cfg = await get_config()
    updates = {}
    for k in ("execution_enabled", "wallet_enabled", "hard_freeze", "shadow_enabled", "default_funding_asset"):
        if k in patch:
            updates[k] = patch[k]
    if "withdrawal_whitelist" in patch and isinstance(patch["withdrawal_whitelist"], list):
        updates["withdrawal_whitelist"] = [str(x).strip() for x in patch["withdrawal_whitelist"] if str(x).strip()]
    if "limits" in patch and isinstance(patch["limits"], dict):
        new_limits = dict(cfg["limits"])
        for lk, lv in patch["limits"].items():
            if lk in LIMIT_KEYS and isinstance(lv, (int, float)):
                new_limits[lk] = lv
        updates["limits"] = new_limits
    if not updates:
        return cfg
    updates["updated_at"] = now_iso()
    await db.execution_config.update_one({"key": CONFIG_KEY}, {"$set": updates}, upsert=True)
    return await get_config()
