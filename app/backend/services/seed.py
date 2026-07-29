from core.models import DEFAULT_RISK_PROFILE, DEFAULT_SIM_CONFIG, new_id, now_iso
from services.db import networks_col, routes_col

NETWORKS = [
    {"key": "BSC", "name": "BNB Smart Chain", "chain_id": 56,
     "rpc_urls": ["https://bsc-dataseed.binance.org", "https://bsc-dataseed1.defibit.io"],
     "explorer_url": "https://bscscan.com", "native_symbol": "BNB", "decimals": 18, "kind": "evm"},
    {"key": "BLOCKDAG", "name": "BlockDAG Mainnet", "chain_id": 1404,
     "rpc_urls": ["https://rpc.bdagscan.com"],
     "explorer_url": "https://bdagscan.com", "native_symbol": "BDAG", "decimals": 18, "kind": "evm"},
]

DEFAULT_ROUTE = {
    "name": "BDAG via XT v1",
    "active": True,
    "mode": "live",
    "funding": {"coin": "BNB", "network": "BSC"},
    "purchase": {"asset": "BDAG", "network": "BLOCKDAG", "venue": "manual"},
    "wallet": {"connector": "evm_watch", "address": "", "label": "MetaMask main"},
    "exit": {"exchange": "xt", "base": "BDAG", "quote": "USDT"},
    "comparison_exchanges": ["xt", "mexc", "gate", "bitmart", "coinstore"],
    "settlement": {"coin": "BNB", "network": "BSC", "conversion_path": ["USDT/BNB"]},
    "manual_buy": {"price": 0.000035, "qty": 10000000, "override": False},
    "risk_profile": DEFAULT_RISK_PROFILE,
    "sim_config": DEFAULT_SIM_CONFIG,
}


async def seed():
    for n in NETWORKS:
        await networks_col.update_one({"key": n["key"]}, {"$setOnInsert": {**n, "id": new_id()}}, upsert=True)
    existing = await routes_col.find_one({"name": DEFAULT_ROUTE["name"]})
    if not existing:
        await routes_col.insert_one({**DEFAULT_ROUTE, "id": new_id(),
                                     "created_at": now_iso(), "updated_at": now_iso()})
    # Sprint 2 migration: ensure coinstore is in every route's comparison set
    await routes_col.update_many({}, {"$addToSet": {"comparison_exchanges": "coinstore"}})
    # Phase E1 migration: default BDAG routes to live portal price (manual override off)
    await routes_col.update_many(
        {"manual_buy.override": {"$exists": False}},
        {"$set": {"manual_buy.override": False}})
