"""Phase E3 — Shadow Mode runner (NON-EXECUTING).

Drives SHADOW execution cycles off LIVE market data + LIVE (read-only) APIs that
the collector already polls, recording "would-purchase / would-transfer / would-
sell / would-withdraw" decisions at each state instead of executing anything.

Validates, with zero fund movement:
  • opportunity detection      (opens a cycle when a live net spread clears the floor)
  • route selection            (picks the venue by registry role + live deposit-gate)
  • state transitions          (auto-advances the E2 state machine, one step per tick)
  • recovery logic             (re-routes to a backup venue when the primary gate is shut)
  • stuck-fund detection        (marks STUCK_* when no venue can receive the transfer)
  • profit calculations         (expected-at-detection vs realized-shadow at the sell leg)
  • timeline analysis           (every step + decision + event is journaled for replay)

*** NO wallet transactions. NO exchange transactions. NO withdrawals. NO fund movement. ***
Gated behind execution_config.shadow_enabled (default OFF). Reads only data the
read-only collector already holds — it makes no new write calls of any kind.
"""
import asyncio
import logging

from services import db
from services.collector import collector
from services.execution import config, venue_registry
from services.execution.fund_tracker import FUND_LOCATION, RECOVERY, TERMINAL, fund_tracker
from services.portal_price import portal_price

logger = logging.getLogger("shadow")

TICK_S = 15
ROLE_RANK = {"primary": 0, "backup": 1, "watch": 2, "disabled": 9}

# decision label per next-state (the "would-do" action recorded into the cycle)
ACTION = {
    "PURCHASE_ORDER_CREATED": "would_create_purchase_order",
    "PAYMENT_SENT": "would_pay_blockdag_portal",
    "WAITING_FOR_BDAG": "would_wait_for_bdag_receipt",
    "BDAG_RECEIVED": "would_confirm_bdag_receipt",
    "TRANSFER_SENT": "would_transfer_bdag_to_exchange",
    "WAITING_DEPOSIT": "would_wait_for_exchange_deposit",
    "DEPOSIT_CONFIRMED": "would_confirm_exchange_deposit",
    "SELL_SUBMITTED": "would_submit_spot_sell",
    "SELL_FILLED": "would_fill_spot_sell",
    "WITHDRAWAL_SUBMITTED": "would_withdraw_usdt_to_whitelist",
    "WITHDRAWAL_CONFIRMED": "would_confirm_usdt_withdrawal",
    "COMPLETE": "would_complete_cycle",
}


class ShadowRunner:
    def __init__(self):
        self._task = None
        self._running = False
        self.started_at = None
        self.last_tick = None
        self.ticks = 0

    async def start(self):
        if self._running:
            return
        self._running = True
        from core.models import now_iso
        self.started_at = now_iso()
        self._task = asyncio.create_task(self._loop())
        logger.info("Shadow runner started (idle until shadow_enabled=true). NON-EXECUTING.")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self):
        while self._running:
            await asyncio.sleep(TICK_S)
            try:
                await self._tick()
            except Exception as e:
                logger.warning("shadow tick failed: %s", e)

    async def _tick(self):
        from core.models import now_iso
        cfg = await config.get_config()
        if not cfg.get("shadow_enabled"):
            return
        self.ticks += 1
        self.last_tick = now_iso()
        if cfg.get("hard_freeze"):
            return
        open_cycle = await db.execution_cycles.find_one(
            {"mode": "shadow", "state": {"$nin": list(TERMINAL)}}, {"_id": 0}, sort=[("created_at", -1)])
        if open_cycle:
            await self._drive(open_cycle, cfg)
        else:
            await self._maybe_open(cfg)

    # ---------- venue selection (route selection validation) ----------
    @staticmethod
    def _candidates(rcache, role_map, floor):
        ev = rcache.get("_evaluation") or {}
        out = []
        for entry in ev.get("venue_matrix", []):
            ex = entry["exchange"]
            role = role_map.get(ex, "watch")
            if role == "disabled":
                continue
            if entry.get("listed") is False:
                continue
            net = entry.get("net_spread_pct")
            if net is None or net < floor:
                continue
            gate = ((rcache.get(ex) or {}).get("fee") or {}).get("deposit_enabled")
            out.append({"exchange": ex, "net": net, "gate": gate, "role": role,
                        "recommended": entry.get("recommended")})
        out.sort(key=lambda c: (0 if c["gate"] is True else 1, ROLE_RANK.get(c["role"], 9), -(c["net"] or 0)))
        return out

    # ---------- open a shadow cycle on a live opportunity ----------
    async def _maybe_open(self, cfg):
        """Open a SHADOW cycle only when a FRESH cycle clears the floor — i.e. buying
        brand-new BDAG at the live swap price and selling into the live book is
        profitable RIGHT NOW. Uses the same fresh-cycle engine as the Opportunity
        Gate (NOT the held-position cost basis)."""
        from services.execution import arbitrage_intel
        floor = cfg["limits"].get("min_net_spread_pct", 2.0)
        size_usd = round(cfg["limits"].get("shadow_cycle_size_usd")
                         or cfg["limits"].get("max_cycle_usd", 25.0), 2)
        routes = await db.routes_col.find({"active": True, "mode": "live"}, {"_id": 0}).to_list(50)
        best = None
        for route in routes:
            try:
                intel = await arbitrage_intel.analyze(route["id"], size_usd=size_usd)
            except Exception:
                continue
            if not intel.get("available"):
                continue
            rec = intel.get("recommended") or {}
            roi = rec.get("roi_pct")
            venue = intel.get("sell_venue")
            buy = intel.get("buy_price")  # FRESH live-swap buy price (execution authority)
            if roi is None or roi < floor or not venue or not buy:
                continue
            qty = round(size_usd / buy, 2)
            exp_profit = round(size_usd * roi / 100, 4)
            gate_open = ((collector.cache.get(route["id"], {}).get(venue) or {}).get("fee") or {}).get("deposit_enabled")
            cand = {"route": route, "venue": venue, "buy": buy, "size_usd": size_usd,
                    "qty": qty, "exp_profit": exp_profit, "net": roi, "gate": gate_open}
            if best is None or exp_profit > best["exp_profit"]:
                best = cand
        if not best:
            return
        try:
            cycle = await fund_tracker.create_cycle(
                best["route"]["id"], best["size_usd"], cfg.get("default_funding_asset"),
                mode="shadow", sell_venue=best["venue"],
                expected={"buy_price": best["buy"], "qty_base": best["qty"],
                          "expected_profit_quote": best["exp_profit"], "net_pct": round(best["net"], 3)})
            await fund_tracker.record_decision(cycle["id"], {
                "state": "CREATED", "action": "opportunity_detected",
                "detail": f"FRESH cycle net {best['net']:.2f}% on {best['venue'].upper()} "
                          f"@ ${best['size_usd']} (gate {'open' if best['gate'] else 'closed/unknown'})",
                "sell_venue": best["venue"], "expected_profit_quote": best["exp_profit"],
                "size_usd": best["size_usd"], "qty_base": best["qty"], "buy_price": best["buy"]})
            logger.info("SHADOW cycle opened on %s (FRESH net %.2f%%, $%s)",
                        best["venue"], best["net"], best["size_usd"])
        except ValueError as e:
            logger.info("shadow open skipped: %s", e)

    # ---------- drive one step of an open shadow cycle ----------
    async def _drive(self, cycle, cfg):
        state = cycle["state"]
        rid = cycle["route_id"]
        rcache = collector.cache.get(rid, {})
        venue = cycle.get("sell_venue")
        floor = cfg["limits"].get("min_net_spread_pct", 2.0)

        # resume a gate-stuck cycle when conditions clear (recovery validation)
        if state.startswith("STUCK_"):
            gate = ((rcache.get(venue) or {}).get("fee") or {}).get("deposit_enabled")
            if gate is True:
                await fund_tracker.resume_to(cycle["id"], "BDAG_RECEIVED",
                                             note=f"deposit gate reopened on {venue.upper()} — resuming transfer")
            else:
                role_map = await venue_registry.get_role_map()
                alt = next((c for c in self._candidates(rcache, role_map, floor)
                            if c["gate"] is True), None)
                if alt:
                    await fund_tracker.set_sell_venue(cycle["id"], alt["exchange"])
                    await fund_tracker.record_decision(cycle["id"], {
                        "state": cycle["state"], "action": "recovery_reroute",
                        "detail": f"re-routing to {alt['exchange'].upper()} (gate open) from {venue.upper()}"})
                    await fund_tracker.resume_to(cycle["id"], "BDAG_RECEIVED",
                                                 note=f"re-routed to {alt['exchange'].upper()}; resuming transfer")
            return

        if state == "MANUAL_REVIEW" or state in TERMINAL:
            return

        # gate check before the transfer leg (BDAG_RECEIVED → TRANSFER_SENT)
        if state == "BDAG_RECEIVED":
            gate = ((rcache.get(venue) or {}).get("fee") or {}).get("deposit_enabled")
            if gate is not True:
                role_map = await venue_registry.get_role_map()
                alt = next((c for c in self._candidates(rcache, role_map, floor)
                            if c["gate"] is True and c["exchange"] != venue), None)
                if alt:
                    await fund_tracker.set_sell_venue(cycle["id"], alt["exchange"])
                    await fund_tracker.record_decision(cycle["id"], {
                        "state": state, "action": "recovery_reroute",
                        "detail": f"primary {venue.upper()} deposit gate closed — re-routing to "
                                  f"{alt['exchange'].upper()} ({alt['role']}, gate open)"})
                    venue = alt["exchange"]
                else:
                    await fund_tracker.set_stuck(
                        cycle["id"], "STUCK_WAITING_DEPOSIT",
                        f"deposit gate CLOSED on {venue.upper()} — cannot transfer BDAG; no open-gate venue available",
                        RECOVERY["STUCK_WAITING_DEPOSIT"])
                    return

        decision = await self._decision_for(cycle, state, rcache, venue, cfg)
        await fund_tracker.advance(cycle["id"], decision=decision)

    async def _decision_for(self, cycle, state, rcache, venue, cfg):
        # next state in the flow
        from services.execution.fund_tracker import STATE_FLOW
        try:
            nxt = STATE_FLOW[STATE_FLOW.index(state) + 1]
        except (ValueError, IndexError):
            return None
        action = ACTION.get(nxt, nxt.lower())
        d = {"action": action}
        if nxt == "PURCHASE_ORDER_CREATED":
            d["detail"] = f"portal pay-order for {cycle.get('qty_base')} BDAG @ {cycle.get('buy_price_at_open')}"
        elif nxt == "PAYMENT_SENT":
            d["detail"] = f"pay {cycle.get('funding_amount')} {cycle.get('funding_asset')} to portal"
        elif nxt == "BDAG_RECEIVED":
            d["detail"] = f"confirm {cycle.get('qty_base')} BDAG on BlockDAG chain"
        elif nxt == "TRANSFER_SENT":
            d["detail"] = f"transfer {cycle.get('qty_base')} BDAG to {venue.upper()} deposit address"
        elif nxt == "DEPOSIT_CONFIRMED":
            d["detail"] = f"BDAG credited on {venue.upper()}"
        elif nxt in ("SELL_SUBMITTED", "SELL_FILLED"):
            bid = None
            ob = (rcache.get(venue) or {}).get("orderbook")
            if ob and ob.get("bids"):
                bid = ob["bids"][0][0]
            if nxt == "SELL_SUBMITTED":
                d["detail"] = f"submit spot sell {cycle.get('qty_base')} BDAG on {venue.upper()} @ ~{bid}"
                d["target_price"] = bid
            else:  # SELL_FILLED — realized-shadow profit from live bid
                route = await db.routes_col.find_one({"id": cycle["route_id"]}, {"_id": 0}) or {}
                fee = (rcache.get(venue) or {}).get("fee") or {}
                taker = fee.get("taker_fee_pct") or 0.2
                fixed = (route.get("risk_profile") or {}).get("fixed_fees_quote", 1.0)
                qty = cycle.get("qty_base") or 0
                buy = cycle.get("buy_price_at_open") or 0
                if bid and qty and buy:
                    proceeds = qty * bid * (1 - taker / 100)
                    cost = qty * buy
                    pnl = proceeds - cost - fixed
                    d.update(proceeds_quote=round(proceeds, 4), realized_pnl_quote=round(pnl, 4),
                             realized_net_pct=round(pnl / cost * 100, 3) if cost else None,
                             sell_price=bid,
                             detail=f"filled @ {bid} → proceeds ${proceeds:.2f}, realized PnL ${pnl:+.2f}")
                else:
                    d.update(proceeds_quote=cycle.get("size_usd"), realized_pnl_quote=0.0,
                             realized_net_pct=0.0, detail="no live bid — realized PnL unavailable")
        elif nxt == "WITHDRAWAL_SUBMITTED":
            wl = cfg.get("withdrawal_whitelist") or []
            d["detail"] = (f"withdraw USDT to whitelisted wallet" if wl
                           else "withdraw USDT (NO whitelist configured — manual step)")
            d["whitelist_configured"] = bool(wl)
        elif nxt == "COMPLETE":
            d["detail"] = "cycle would be complete — funds settled to operator wallet"
        return d

    async def status(self):
        open_n = await db.execution_cycles.count_documents({"mode": "shadow", "state": {"$nin": list(TERMINAL)}})
        complete_n = await db.execution_cycles.count_documents({"mode": "shadow", "state": "COMPLETE"})
        stuck_n = await db.execution_cycles.count_documents({"mode": "shadow", "stuck": True})
        total = await db.execution_cycles.count_documents({"mode": "shadow"})
        agg = await db.execution_cycles.aggregate([
            {"$match": {"mode": "shadow", "state": "COMPLETE"}},
            {"$group": {"_id": None, "exp": {"$sum": "$expected_profit_quote"},
                        "real": {"$sum": "$realized_shadow_pnl_quote"}}}]).to_list(1)
        cfg = await config.get_config()
        return {
            "running": self._running, "enabled": cfg.get("shadow_enabled", False),
            "started_at": self.started_at, "last_tick": self.last_tick, "ticks": self.ticks,
            "tick_interval_s": TICK_S,
            "shadow_cycles": {"total": total, "open": open_n, "complete": complete_n, "stuck": stuck_n},
            "shadow_pnl": {"expected_total_quote": round((agg[0]["exp"] if agg else 0) or 0, 2),
                           "realized_total_quote": round((agg[0]["real"] if agg else 0) or 0, 2)},
            "note": "NON-EXECUTING — records would-purchase/transfer/sell/withdraw off live data. "
                    "No wallet/exchange transactions, no fund movement.",
        }


shadow_runner = ShadowRunner()
