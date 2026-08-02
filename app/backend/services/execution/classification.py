"""Route Classification + Automation Coverage (E2) — read-only.

Classifies each route x venue path as:
  A — Fully Automated    (every leg automatable, coverage 100%)
  B — Semi-Automated     (exactly one manual leg, coverage 80%)
  C — Manual Opportunity  (two or more manual legs / a critical leg missing)

Coverage = % of automatable legs across 5 equally-weighted legs (each 20%):
  1. Buy BDAG on BlockDAG portal
  2. Receive BDAG + transfer to exchange
  3. Detect exchange deposit credit
  4. Sell BDAG on exchange
  5. Withdraw / settle USDT to wallet

Leg automatability is derived from: the dedicated-wallet readiness flag
(wallet_enabled), the venue's exchange-side API surface (venue registry), the
LIVE BDAG deposit-gate status (capability registry), and whether a withdrawal
whitelist is configured. Nothing here executes anything.
"""
from services import db
from services.execution import config, venue_registry

LEGS = [
    {"key": "portal_purchase", "label": "Buy BDAG on BlockDAG portal", "weight": 20},
    {"key": "bdag_transfer", "label": "Receive BDAG + transfer to exchange", "weight": 20},
    {"key": "deposit_detection", "label": "Detect exchange deposit credit", "weight": 20},
    {"key": "exchange_sell", "label": "Sell BDAG on exchange", "weight": 20},
    {"key": "usdt_settlement", "label": "Withdraw / settle USDT to wallet", "weight": 20},
]

CLASS = {0: ("A", "Fully Automated"), 1: ("B", "Semi-Automated")}


async def classify(route: dict, exchange: str) -> dict:
    cfg = await config.get_config()
    wallet_ready = bool(cfg.get("wallet_enabled"))
    whitelist_ready = bool(cfg.get("withdrawal_whitelist"))
    venue = await db.venue_registry.find_one({"exchange": exchange}, {"_id": 0})
    auto = (venue or {}).get("automation") or venue_registry.VENUE_AUTOMATION.get(exchange, {})
    asset = (route.get("purchase") or {}).get("asset", "BDAG")
    cap = await db.capabilities_col.find_one({"exchange": exchange, "currency": asset}, {"_id": 0})
    deposit_open = (cap or {}).get("deposit_enabled")

    legs = []

    def add(key, label, ok, manual_reason, action):
        legs.append({"leg": key, "label": label, "automatable": bool(ok),
                     "status": "AUTO" if ok else "MANUAL",
                     "reason": None if ok else manual_reason,
                     "manual_action": None if ok else action})

    add("portal_purchase", "Buy BDAG on BlockDAG portal", wallet_ready,
        "No dedicated automation wallet enabled (wallet_enabled=false)",
        "Manually buy BDAG on the BlockDAG portal at the live portal price.")
    add("bdag_transfer", "Receive BDAG + transfer to exchange",
        wallet_ready and bool(auto.get("deposit_address_api")) and deposit_open is True,
        ("BDAG deposit gate CLOSED on this venue" if deposit_open is not True
         else "No dedicated automation wallet enabled"),
        "Transfer BDAG from your wallet to the exchange BDAG deposit address.")
    add("deposit_detection", "Detect exchange deposit credit",
        bool(auto.get("deposit_history_api")) and deposit_open is True,
        ("BDAG deposit gate CLOSED on this venue" if deposit_open is not True
         else "No deposit-history API on this venue"),
        "Watch the exchange deposit history until BDAG is credited.")
    add("exchange_sell", "Sell BDAG on exchange", bool(auto.get("trade_api")),
        "No trading API available on this venue",
        "Place a liquidity-bounded spot sell on the exchange.")
    add("usdt_settlement", "Withdraw / settle USDT to wallet",
        bool(auto.get("withdraw_api")) and whitelist_ready,
        ("No withdrawal whitelist configured" if not whitelist_ready
         else "No withdrawal API on this venue"),
        "Withdraw USDT to your whitelisted wallet and settle manually.")

    coverage = sum(spec["weight"] for spec, leg in zip(LEGS, legs) if leg["automatable"])
    manual_steps = sum(1 for leg in legs if not leg["automatable"])
    cls, label = CLASS.get(manual_steps, ("C", "Manual Opportunity"))
    return {
        "exchange": exchange, "asset": asset,
        "automation_coverage_pct": coverage,
        "manual_steps": manual_steps,
        "classification": cls, "classification_label": label,
        "deposit_gate_open": deposit_open,
        "wallet_ready": wallet_ready, "whitelist_ready": whitelist_ready,
        "audit_score": auto.get("audit_score"),
        "legs": legs,
    }


async def classify_route(route: dict) -> dict:
    """Classify every comparison venue for a route, tagged with its registry role."""
    role_map = await venue_registry.get_role_map()
    venues = []
    for ex in route.get("comparison_exchanges", []):
        c = await classify(route, ex)
        c["role"] = role_map.get(ex, "watch")
        venues.append(c)
    # surface the best (highest coverage) path first
    venues.sort(key=lambda v: (-v["automation_coverage_pct"], v["manual_steps"]))
    return {"route_id": route["id"], "route_name": route.get("name"),
            "asset": (route.get("purchase") or {}).get("asset", "BDAG"),
            "venues": venues,
            "note": "Read-only classification. No execution, no fund movement."}
