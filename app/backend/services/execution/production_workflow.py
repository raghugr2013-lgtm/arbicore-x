"""Production Workflow Blueprint + Next-Cycle Readiness Engine (READ-ONLY).

A complete, NON-EXECUTING design surface for the full BDAG production loop:

  MetaMask funding → BlockDAG Live Swap → BDAG wallet receipt → exchange deposit
  → multi-level order-book liquidation → USDT withdrawal → final wallet receipt
  → next-cycle readiness → next cycle

Every stage is described with its preconditions, verification method, automation
readiness (derived LIVE from config + venue API surface + deposit/withdraw gates
+ whitelist), failure modes, recovery path, and estimated duration — so when E5
is eventually approved the SAME blueprint maps 1:1 onto the live executor without
re-architecting anything.

The Next-Cycle Readiness Engine replaces a fixed cooldown: after a configurable
minimum cooldown (default 60s) it continuously checks withdrawal-confirmed,
wallet-balance-updated, exchange-balances-reconciled, no-assets-in-transit, and
opportunity-still-GO. When all pass the last cycle is marked READY and the next
cycle is allowed immediately — no unnecessary delay.

NO execution, NO API keys, NO wallet actions, NO fund movement.
"""
from datetime import datetime, timezone

from services import db
from services.execution import arbitrage_intel, config, venue_registry
from services.execution.fund_tracker import FUND_LOCATION

# ---------------------------------------------------------------------------
# Static blueprint — 9 lifecycle stages. `states` maps each stage to the durable
# fund_tracker state(s) it corresponds to, so the live executor (E5) reuses this.
# ---------------------------------------------------------------------------
STAGES = [
    {
        "key": "metamask_funding", "stage": 1, "name": "MetaMask Funding",
        "states": ["CREATED"], "fund_location": FUND_LOCATION["CREATED"],
        "description": "Operator funds the dedicated automation wallet with the funding asset "
                       "(USDT/BNB/ETH on BSC) sized to the certification per-cycle cap.",
        "preconditions": ["Dedicated automation wallet provisioned",
                          "Funding asset balance ≥ cycle size", "wallet_enabled flag ON (E5)"],
        "verification_method": "On-chain wallet balance read (BSC RPC) ≥ required funding amount.",
        "failure_modes": ["Insufficient gas/funding balance", "Wrong network", "RPC outage"],
        "recovery_path": "Top up wallet / switch RPC; cycle never leaves CREATED until funded.",
        "est_duration": "instant–2 min (on-chain confirmation)",
        "automation_leg": "wallet",
    },
    {
        "key": "blockdag_swap", "stage": 2, "name": "BlockDAG Live Swap Purchase",
        "states": ["PURCHASE_ORDER_CREATED", "PAYMENT_SENT", "WAITING_FOR_BDAG"],
        "fund_location": FUND_LOCATION["PAYMENT_SENT"],
        "description": "Buy BDAG on the BlockDAG live swap at the resolved buy price; pay-coin is "
                       "sent to the portal pay-address and the portal processes the swap.",
        "preconditions": ["Funded wallet", "Live portal swap reachable", "Buy price resolved (cost basis)"],
        "verification_method": "Portal swap quote + pay-tx hash on BSC + portal processing status.",
        "failure_modes": ["Portal quote drift", "Pay-tx underpriced/stuck", "Portal processing delay"],
        "recovery_path": "STUCK_WAITING_FOR_BDAG → check processor + pay-tx on bdagscan; never re-pay.",
        "est_duration": "1–10 min",
        "automation_leg": "wallet",
    },
    {
        "key": "bdag_receipt", "stage": 3, "name": "BDAG Wallet Receipt Verification",
        "states": ["BDAG_RECEIVED"], "fund_location": FUND_LOCATION["BDAG_RECEIVED"],
        "description": "Confirm BDAG credited to the automation wallet on the BlockDAG chain "
                       "(exact quantity received vs expected).",
        "preconditions": ["Swap submitted", "BlockDAG chain reachable"],
        "verification_method": "BlockDAG explorer balance/tx read; received qty within tolerance of expected.",
        "failure_modes": ["Partial credit", "Bonus-token discrepancy", "Explorer lag"],
        "recovery_path": "Reconcile received vs expected; if short, MANUAL_REVIEW before transfer.",
        "est_duration": "instant–5 min",
        "automation_leg": "wallet",
    },
    {
        "key": "transfer_to_exchange", "stage": 4, "name": "Transfer BDAG to Exchange",
        "states": ["TRANSFER_SENT", "WAITING_DEPOSIT"], "fund_location": FUND_LOCATION["TRANSFER_SENT"],
        "description": "Withdraw BDAG from the wallet to the exchange's BDAG deposit address on the "
                       "correct network.",
        "preconditions": ["BDAG received", "Exchange deposit address (deposit-address API)",
                          "Exchange BDAG deposit gate OPEN"],
        "verification_method": "BlockDAG transfer tx hash + exchange deposit-address match.",
        "failure_modes": ["Deposit gate closed", "Wrong network/memo", "Network congestion"],
        "recovery_path": "If gate closed → re-route to a gate-open backup venue (registry role); else STUCK_WAITING_DEPOSIT.",
        "est_duration": "2–20 min",
        "automation_leg": "transfer",
    },
    {
        "key": "exchange_deposit", "stage": 5, "name": "Exchange Deposit Verification",
        "states": ["DEPOSIT_CONFIRMED"], "fund_location": FUND_LOCATION["DEPOSIT_CONFIRMED"],
        "description": "Confirm BDAG credited to the exchange spot balance and available to trade.",
        "preconditions": ["Transfer broadcast", "Deposit-history/monitoring API", "Confirmations met"],
        "verification_method": "Exchange deposit-record API status = Completed + spot balance increment.",
        "failure_modes": ["Confirmations stuck", "Exchange maintenance", "Credit delay"],
        "recovery_path": "STUCK_WAITING_DEPOSIT → verify on-chain tx + exchange deposit history; contact support if confirmed-not-credited.",
        "est_duration": "5–30 min",
        "automation_leg": "exchange_read",
    },
    {
        "key": "liquidation", "stage": 6, "name": "Multi-Level Order-Book Liquidation",
        "states": ["SELL_SUBMITTED", "SELL_FILLED"], "fund_location": FUND_LOCATION["SELL_FILLED"],
        "description": "Sell BDAG into the live bid ladder using a liquidity-bounded, multi-level "
                       "VWAP plan (no single-price assumption); only profitable buyer levels are consumed.",
        "preconditions": ["BDAG on exchange", "Trading API", "Profitable buyer depth ≥ size", "Verdict GO"],
        "verification_method": "Order-status API fills by level + realized VWAP vs expected break-even.",
        "failure_modes": ["Bid book thins mid-fill", "Price moves below break-even", "Partial fill"],
        "recovery_path": "STUCK_SELL → re-price within net-spread floor or place manually; cap to profitable depth.",
        "est_duration": "instant–5 min",
        "automation_leg": "exchange_trade",
    },
    {
        "key": "usdt_withdrawal", "stage": 7, "name": "USDT Withdrawal",
        "states": ["WITHDRAWAL_SUBMITTED"], "fund_location": FUND_LOCATION["WITHDRAWAL_SUBMITTED"],
        "description": "Withdraw USDT proceeds from the exchange to the operator's pre-verified "
                       "whitelisted wallet address only.",
        "preconditions": ["USDT proceeds on exchange", "Withdrawal API", "Destination in withdrawal whitelist"],
        "verification_method": "Withdrawal-record API status + on-chain withdrawal tx hash to whitelisted address.",
        "failure_modes": ["Withdrawal gate closed", "Address not whitelisted", "Exchange review hold"],
        "recovery_path": "STUCK_WITHDRAWAL → check withdrawal status + whitelist; escalate past exchange SLA.",
        "est_duration": "5–60 min",
        "automation_leg": "exchange_withdraw",
    },
    {
        "key": "wallet_receipt", "stage": 8, "name": "Final Wallet Receipt Verification",
        "states": ["WITHDRAWAL_CONFIRMED", "COMPLETE"], "fund_location": FUND_LOCATION["WITHDRAWAL_CONFIRMED"],
        "description": "Confirm USDT arrival on-chain at the operator wallet and reconcile final "
                       "settled amount vs expected net proceeds.",
        "preconditions": ["Withdrawal submitted", "Wallet reachable"],
        "verification_method": "On-chain wallet balance read; settled USDT within tolerance of expected net.",
        "failure_modes": ["On-chain delay", "Fee variance", "Wrong destination (impossible w/ whitelist)"],
        "recovery_path": "Reconcile settled vs expected; log variance to the immutable ledger.",
        "est_duration": "2–15 min",
        "automation_leg": "wallet",
    },
    {
        "key": "next_cycle_readiness", "stage": 9, "name": "Next-Cycle Readiness",
        "states": ["READY"], "fund_location": "Funds settled at operator wallet — evaluating next-cycle readiness",
        "description": "After a configurable minimum cooldown, continuously verify the system is "
                       "clean and the opportunity still holds, then mark READY and allow the next "
                       "cycle immediately (no forced delay).",
        "preconditions": ["Withdrawal confirmed", "Wallet balance updated", "Exchange balances reconciled",
                          "No assets in transit", "Opportunity verdict still GO", "Min cooldown elapsed"],
        "verification_method": "Next-Cycle Readiness Engine — 6 live checks; READY only when all pass.",
        "failure_modes": ["Opportunity verdict flipped to WAIT/NO_GO", "Residual in-transit cycle",
                          "Balance reconciliation mismatch"],
        "recovery_path": "Hold in COOLDOWN/WAIT until checks pass or operator intervenes.",
        "est_duration": "≥60s (then immediate when ready)",
        "automation_leg": "engine",
    },
]

FUTURE_EXECUTION_PATH = (
    "MetaMask → BlockDAG Live Swap → Exchange (deposit) → Sell (multi-level) → "
    "Withdraw USDT → Wallet Receipt → Next-Cycle Readiness → Next Cycle")


async def _bdag_route(route_id: str = None):
    if route_id:
        return await db.routes_col.find_one({"id": route_id}, {"_id": 0})
    return await db.routes_col.find_one({"purchase.asset": "BDAG"}, {"_id": 0})


def _leg_readiness(leg: str, cfg: dict, auto: dict, deposit_open, whitelist_ready: bool) -> dict:
    """Live automation readiness for a stage's automation leg (E5 precondition)."""
    wallet = bool(cfg.get("wallet_enabled"))
    if leg == "wallet":
        ok, reason = wallet, None if wallet else "Automation wallet signing disabled (wallet_enabled=false)"
    elif leg == "transfer":
        ok = wallet and bool(auto.get("deposit_address_api")) and deposit_open is True
        reason = (None if ok else "BDAG deposit gate not OPEN on venue" if deposit_open is not True
                  else "Automation wallet disabled")
    elif leg == "exchange_read":
        ok = bool(auto.get("deposit_history_api")) and deposit_open is True
        reason = None if ok else ("BDAG deposit gate not OPEN" if deposit_open is not True
                                  else "No deposit-history API on venue")
    elif leg == "exchange_trade":
        ok = bool(auto.get("trade_api"))
        reason = None if ok else "No trading API on venue"
    elif leg == "exchange_withdraw":
        ok = bool(auto.get("withdraw_api")) and whitelist_ready
        reason = None if ok else ("Withdrawal whitelist not configured" if not whitelist_ready
                                  else "No withdrawal API on venue")
    elif leg == "engine":
        ok, reason = True, None
    else:
        ok, reason = False, "unknown leg"
    return {"automatable": ok, "status": "AUTOMATABLE" if ok else "MANUAL", "blocking_reason": reason}


async def blueprint(route_id: str = None) -> dict:
    cfg = await config.get_config()
    route = await _bdag_route(route_id)
    venue = (await venue_registry.primary()) or (route or {}).get("exit", {}).get("exchange") or "coinstore"
    vdoc = await db.venue_registry.find_one({"exchange": venue}, {"_id": 0})
    auto = (vdoc or {}).get("automation") or venue_registry.VENUE_AUTOMATION.get(venue, {})
    cap = await db.capabilities_col.find_one({"exchange": venue, "currency": "BDAG"}, {"_id": 0})
    deposit_open = (cap or {}).get("deposit_enabled")
    if cap is None and venue == "coinstore":
        deposit_open = True  # user-verified, no live capability flips tracked for Coinstore
    whitelist_ready = bool(cfg.get("withdrawal_whitelist"))

    stages = []
    automatable = 0
    for s in STAGES:
        r = _leg_readiness(s["automation_leg"], cfg, auto, deposit_open, whitelist_ready)
        if r["automatable"]:
            automatable += 1
        stages.append({**s, "automation_readiness": r})

    readiness = await next_cycle_readiness(route_id=(route or {}).get("id"))
    coverage = round(automatable / len(STAGES) * 100)
    return {
        "phase": "Production Workflow Blueprint (read-only, non-executing)",
        "target_venue": venue, "route_id": (route or {}).get("id"), "route_name": (route or {}).get("name"),
        "stages": stages, "total_stages": len(STAGES),
        "automatable_now": automatable, "automation_coverage_pct": coverage,
        "execution_gates": {"execution_enabled": cfg["execution_enabled"],
                            "wallet_enabled": cfg["wallet_enabled"],
                            "withdrawal_whitelist_configured": whitelist_ready},
        "next_cycle_readiness": readiness,
        "future_execution_path": FUTURE_EXECUTION_PATH,
        "future_execution_note": "When E5 is approved, each stage's automation_leg connects to its live "
                                 "executor with NO architecture change — the durable state machine, "
                                 "fund-location ledger, recovery paths, and this blueprint are already wired.",
        "note": "Blueprint + live automation-readiness. NO execution, NO API keys, NO wallet actions, "
                "NO fund movement. execution_enabled/wallet_enabled remain false.",
    }


async def _last_completed_cycle():
    rows = await db.execution_cycles.find(
        {"mode": "shadow", "state": "COMPLETE"}, {"_id": 0},
        sort=[("updated_at", -1)]).to_list(1)
    return rows[0] if rows else None


def _completed_ts(c: dict):
    for h in reversed(c.get("history", [])):
        if h.get("state") == "COMPLETE":
            return h.get("ts")
    return c.get("updated_at")


async def next_cycle_readiness(route_id: str = None) -> dict:
    """Next-Cycle Readiness Engine. Min cooldown (default 60s) then 5 live checks."""
    cfg = await config.get_config()
    min_cooldown = cfg["limits"].get("min_cooldown_s", 60)
    last = await _last_completed_cycle()

    # no assets in transit = no open (non-terminal) shadow cycle
    open_shadow = await db.execution_cycles.count_documents(
        {"mode": "shadow", "state": {"$nin": ["COMPLETE", "ABORTED"]}})

    route = await _bdag_route(route_id)
    verdict = None
    if route:
        try:
            intel = await arbitrage_intel.analyze(route["id"])
            verdict = intel.get("verdict")
        except Exception:
            verdict = None

    if not last:
        return {"verdict": "NO_HISTORY", "min_cooldown_s": min_cooldown,
                "checks": [], "ready": False,
                "note": "No completed cycle yet — readiness evaluated after the first completed cycle."}

    ledger = last.get("ledger") or {}
    completed_at = _completed_ts(last)
    try:
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(completed_at)).total_seconds()
    except (ValueError, TypeError):
        elapsed = min_cooldown + 1
    cooldown_remaining = max(0, round(min_cooldown - elapsed, 1))

    def _leg_ok(leg):
        return (ledger.get(leg) or {}).get("status") == "confirmed"

    checks = [
        {"key": "withdrawal_confirmed", "label": "Withdrawal confirmed",
         "passed": _leg_ok("withdrawal") or last["state"] == "COMPLETE",
         "detail": "Last cycle reached WITHDRAWAL_CONFIRMED/COMPLETE."},
        {"key": "wallet_balance_updated", "label": "Wallet balance updated",
         "passed": _leg_ok("wallet_receipt"),
         "detail": "Final USDT receipt confirmed at operator wallet."},
        {"key": "exchange_balances_reconciled", "label": "Exchange balances reconciled",
         "passed": _leg_ok("usdt_balance") and (_leg_ok("withdrawal") or last["state"] == "COMPLETE"),
         "detail": "Proceeds sold and withdrawn — no residual on exchange."},
        {"key": "no_assets_in_transit", "label": "No assets in transit",
         "passed": open_shadow == 0,
         "detail": f"{open_shadow} open cycle(s) in flight."},
        {"key": "opportunity_still_go", "label": "Opportunity verdict still GO",
         "passed": verdict == "GO",
         "detail": f"Live intel verdict = {verdict or 'unknown'}."},
    ]
    all_pass = all(c["passed"] for c in checks)
    cooldown_done = cooldown_remaining <= 0

    if open_shadow > 0:
        v = "BLOCKED"
    elif not cooldown_done:
        v = "COOLDOWN"
    elif all_pass:
        v = "READY"
    else:
        v = "WAIT"

    return {
        "verdict": v, "ready": v == "READY",
        "last_cycle_id": last["id"], "completed_at": completed_at,
        "min_cooldown_s": min_cooldown, "elapsed_s": round(elapsed, 1),
        "cooldown_remaining_s": cooldown_remaining, "cooldown_elapsed": cooldown_done,
        "checks": checks, "checks_passed": sum(1 for c in checks if c["passed"]),
        "opportunity_verdict": verdict,
        "note": "After the minimum cooldown, the next cycle is allowed the moment all checks pass — "
                "no unnecessary delay. READY is informational only; nothing auto-executes.",
    }
