"""Fund Tracking & Recovery Layer (E2 scaffold) — SIMULATED / DRY-RUN ONLY.

A persistent, per-cycle state machine that always answers "Where are the funds
right now?". Survives restarts via a restart-safe sweep loop (same pattern as the
observation recorder). Detects stuck cycles past per-state SLAs, produces recovery
recommendations, and fires Telegram alerts.

*** NO REAL FUND MOVEMENT. NO EXCHANGE API CALLS. NO WALLET TRANSACTIONS. ***
Every cycle is flagged simulated=True / dry_run=True. External references are
placeholder SIM-* ids. This is execution-framework scaffolding only (Phase E2);
live / shadow execution is Phase E3+ and remains disabled (execution_enabled OFF).
"""
import asyncio
import logging
from datetime import datetime, timezone

from core.models import new_id, now_iso
from services import db
from services.execution import audit, config, venue_registry
from services.execution.funding import funding_breakdown
from services.telegram_alerts import telegram_alerts

logger = logging.getLogger("fund_tracker")

SWEEP_EVERY_S = 60

# Happy-path state flow (one durable doc per cycle).
STATE_FLOW = [
    "CREATED", "PURCHASE_ORDER_CREATED", "PAYMENT_SENT", "WAITING_FOR_BDAG",
    "BDAG_RECEIVED", "TRANSFER_SENT", "WAITING_DEPOSIT", "DEPOSIT_CONFIRMED",
    "SELL_SUBMITTED", "SELL_FILLED", "WITHDRAWAL_SUBMITTED", "WITHDRAWAL_CONFIRMED",
    "COMPLETE",
]
TERMINAL = {"COMPLETE", "ABORTED"}

# Durable answer to "where are the funds right now?" per state.
FUND_LOCATION = {
    "CREATED": "Funding asset held in automation wallet (uncommitted)",
    "PURCHASE_ORDER_CREATED": "Portal pay-order created; payment not yet sent",
    "PAYMENT_SENT": "Pay-coin in flight to BlockDAG portal pay-address",
    "WAITING_FOR_BDAG": "BlockDAG portal processing — BDAG not yet received",
    "BDAG_RECEIVED": "BDAG in automation wallet (BlockDAG chain)",
    "TRANSFER_SENT": "BDAG in flight to exchange deposit address",
    "WAITING_DEPOSIT": "BDAG awaiting exchange deposit credit",
    "DEPOSIT_CONFIRMED": "BDAG credited on exchange spot balance",
    "SELL_SUBMITTED": "Sell order open on exchange (BDAG)",
    "SELL_FILLED": "USDT proceeds on exchange spot balance",
    "WITHDRAWAL_SUBMITTED": "USDT withdrawal in flight to whitelisted wallet",
    "WITHDRAWAL_CONFIRMED": "USDT confirmed on-chain at operator wallet",
    "COMPLETE": "Cycle complete — funds settled at operator wallet",
    "ABORTED": "Aborted before any side effect — funding asset intact",
    "MANUAL_REVIEW": "Held for manual review — verify fund location externally",
    "STUCK_WAITING_FOR_BDAG": "Pay-coin sent; BDAG not yet received from portal",
    "STUCK_WAITING_DEPOSIT": "BDAG transferred; exchange deposit not yet credited",
    "STUCK_SELL": "BDAG on exchange; sell order not filled",
    "STUCK_WITHDRAWAL": "USDT on exchange; withdrawal not confirmed",
}

# Per-state SLA seconds; exceeding → the matching STUCK_* state.
SLA_S = {
    "WAITING_FOR_BDAG": 900,
    "WAITING_DEPOSIT": 1800,
    "SELL_SUBMITTED": 600,
    "WITHDRAWAL_SUBMITTED": 1800,
}
STUCK_STATE = {
    "WAITING_FOR_BDAG": "STUCK_WAITING_FOR_BDAG",
    "WAITING_DEPOSIT": "STUCK_WAITING_DEPOSIT",
    "SELL_SUBMITTED": "STUCK_SELL",
    "WITHDRAWAL_SUBMITTED": "STUCK_WITHDRAWAL",
}
RECOVERY = {
    "STUCK_WAITING_FOR_BDAG": "Check the BlockDAG processor (np/getStatus) and the pay tx on bdagscan. "
                              "Do NOT re-pay — the funds may still be in flight.",
    "STUCK_WAITING_DEPOSIT": "Verify the BDAG transfer tx on the BlockDAG explorer and the exchange "
                             "deposit history. Contact exchange support if confirmed on-chain but not credited.",
    "STUCK_SELL": "Re-price the sell order within the net-spread floor or place it manually. "
                  "Check the exchange order status.",
    "STUCK_WITHDRAWAL": "Check the exchange withdrawal status and confirm the destination is whitelisted. "
                        "Escalate to the exchange if stuck past their SLA.",
    "MANUAL_REVIEW": "Hard freeze active — review the cycle, confirm the current fund location externally, "
                     "then resume or abort manually.",
}

# Which fund-location ledger leg each state transition confirms.
LEDGER_ON_ENTER = {
    "PURCHASE_ORDER_CREATED": ("purchase_order", "portal pay-order created"),
    "PAYMENT_SENT": ("payment_tx", "pay-coin transfer broadcast"),
    "BDAG_RECEIVED": ("bdag_receipt", "BDAG on-chain receipt confirmed"),
    "TRANSFER_SENT": ("transfer_tx", "BDAG withdrawal to exchange broadcast"),
    "DEPOSIT_CONFIRMED": ("exchange_deposit", "exchange deposit credited"),
    "SELL_FILLED": ("sell_order", "spot sell filled"),
    "WITHDRAWAL_SUBMITTED": ("withdrawal", "USDT withdrawal submitted"),
    "WITHDRAWAL_CONFIRMED": ("wallet_receipt", "USDT arrival at operator wallet"),
}

LEDGER_KEYS = ("purchase_order", "payment_tx", "bdag_receipt", "transfer_tx",
               "exchange_deposit", "exchange_balance", "sell_order",
               "usdt_balance", "withdrawal", "wallet_receipt")


def _empty_ledger():
    return {k: {"status": "pending", "reference": None, "verified_at": None} for k in LEDGER_KEYS}


class FundTracker:
    def __init__(self):
        self._task = None
        self._running = False
        self.recovered = 0
        self.started_at = None

    # ---------- lifecycle ----------
    async def start(self):
        if self._running:
            return
        self._running = True
        self.started_at = now_iso()
        # restart recovery: re-load every non-terminal cycle from the DB and journal it.
        open_cycles = await db.execution_cycles.find(
            {"state": {"$nin": list(TERMINAL)}}, {"_id": 0, "id": 1, "state": 1}).to_list(500)
        self.recovered = len(open_cycles)
        for c in open_cycles:
            await audit.record(c["id"], c["state"], "recovery",
                               note="cycle re-loaded after restart; state re-derived from DB (SIMULATED)")
        self._task = asyncio.create_task(self._sweep_loop())
        logger.info("Fund tracker started (SIMULATED/DRY-RUN). Recovered %d open cycle(s).", self.recovered)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    # ---------- creation ----------
    async def create_cycle(self, route_id: str, size_usd: float, funding_asset: str = None,
                           mode: str = "scaffold", sell_venue: str = None,
                           expected: dict = None) -> dict:
        cfg = await config.get_config()
        limits = cfg["limits"]
        if not isinstance(size_usd, (int, float)) or size_usd <= 0:
            raise ValueError("size_usd must be a positive number")
        if mode in ("shadow", "recovery_proof"):
            # SHADOW moves no funds — it may test sizes above the real cert cap
            # (e.g. the $50 BlockDAG executable minimum). Real execution caps below stay strict.
            shadow_cap = limits.get("shadow_max_cycle_usd", limits["max_cycle_usd"])
            if size_usd > shadow_cap:
                raise ValueError(f"shadow size ${size_usd} exceeds shadow_max_cycle_usd ${shadow_cap}")
        else:
            if size_usd > limits["max_cycle_usd"]:
                raise ValueError(f"size ${size_usd} exceeds max_cycle_usd ${limits['max_cycle_usd']}")
            if size_usd > limits["max_purchase_usd"]:
                raise ValueError(f"size ${size_usd} exceeds max_purchase_usd ${limits['max_purchase_usd']}")
        funding_asset = (funding_asset or cfg["default_funding_asset"]).upper()
        if funding_asset not in cfg["funding_assets"]:
            raise ValueError(f"unsupported funding asset '{funding_asset}'; allowed: {cfg['funding_assets']}")
        # concurrency is mode-scoped: shadow / recovery_proof / scaffold cap independently.
        if mode == "shadow":
            mode_q = {"mode": "shadow"}
        elif mode == "recovery_proof":
            mode_q = {"mode": "recovery_proof"}
        else:
            mode_q = {"mode": {"$nin": ["shadow", "recovery_proof"]}}
        open_n = await db.execution_cycles.count_documents({**mode_q, "state": {"$nin": list(TERMINAL)}})
        if open_n >= limits["max_concurrent_cycles"]:
            raise ValueError(f"max_concurrent_cycles ({limits['max_concurrent_cycles']}) reached — "
                             f"{open_n} {mode} cycle(s) already open")
        if mode not in ("shadow", "recovery_proof"):  # daily volume cap = (future) real capital only
            day_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0).isoformat()
            agg = await db.execution_cycles.aggregate([
                {"$match": {"created_at": {"$gte": day_start}, "mode": {"$nin": ["shadow", "recovery_proof"]},
                            "state": {"$ne": "ABORTED"}}},
                {"$group": {"_id": None, "vol": {"$sum": "$size_usd"}}}]).to_list(1)
            used = (agg[0]["vol"] if agg else 0) or 0
            if used + size_usd > limits["max_daily_volume_usd"]:
                raise ValueError(f"daily volume cap ${limits['max_daily_volume_usd']} would be exceeded "
                                 f"(used ${round(used, 2)} today)")
        route = await db.routes_col.find_one({"id": route_id}, {"_id": 0})
        if not route:
            raise ValueError("route not found")

        venue = sell_venue or (await venue_registry.primary()) or route["exit"]["exchange"]
        fb = funding_breakdown(size_usd)
        fa = next((a for a in fb["funding_assets"] if a["asset"] == funding_asset), None)
        exp = expected or {}
        cid = new_id()
        ts = now_iso()
        cycle = {
            "id": cid, "route_id": route_id, "route_name": route.get("name"),
            "simulated": True, "dry_run": True, "mode": mode,
            "state": "CREATED", "prev_state": None,
            "size_usd": size_usd, "funding_asset": funding_asset,
            "funding_amount": (fa or {}).get("amount_required"),
            "bdag_price": exp.get("buy_price") or fb["bdag_price"],
            "bdag_qty_expected": exp.get("qty_base") or fb["bdag_qty_gross"],
            "qty_base": exp.get("qty_base") or fb["bdag_qty_gross"],
            "buy_price_at_open": exp.get("buy_price") or fb["bdag_price"],
            "primary_venue": venue, "sell_venue": venue,
            "expected_profit_quote": exp.get("expected_profit_quote"),
            "expected_net_pct": exp.get("net_pct"),
            "realized_shadow_pnl_quote": None, "realized_net_pct": None,
            "fund_location": {"current": FUND_LOCATION["CREATED"], "state": "CREATED"},
            "ledger": _empty_ledger(),
            "history": [{"state": "CREATED", "ts": ts}],
            "shadow_decisions": [],
            "entered_state_at": ts, "stuck": False, "stuck_reason": None,
            "recommended_action": None, "realized_pnl_quote": None,
            "created_at": ts, "updated_at": ts,
        }
        await db.execution_cycles.insert_one(dict(cycle))
        await audit.record(cid, "CREATED", "result",
                           amounts={"size_usd": size_usd, "funding_asset": funding_asset,
                                    "funding_amount": cycle["funding_amount"],
                                    "bdag_qty_expected": cycle["bdag_qty_expected"]},
                           note=f"{'SHADOW' if mode == 'shadow' else 'SIMULATED'} cycle created "
                                f"(dry-run, no funds committed)")
        cycle.pop("_id", None)
        return cycle

    # ---------- transitions ----------
    async def advance(self, cycle_id: str, decision: dict = None) -> dict:
        cycle = await db.execution_cycles.find_one({"id": cycle_id}, {"_id": 0})
        if not cycle:
            raise ValueError("cycle not found")
        cfg = await config.get_config()
        if cfg.get("hard_freeze"):
            return await self._to_manual_review(cycle, "hard freeze active — no new side effects permitted")
        state = cycle["state"]
        if state in TERMINAL:
            raise ValueError(f"cycle is terminal ({state})")
        if state.startswith("STUCK_") or state == "MANUAL_REVIEW":
            return await self._resume(cycle)
        try:
            idx = STATE_FLOW.index(state)
        except ValueError:
            raise ValueError(f"cannot advance from state {state}")
        nxt = STATE_FLOW[idx + 1]
        is_shadow = cycle.get("mode") == "shadow"
        tag = "SHADOW" if is_shadow else "SIMULATED"
        idem = f"{cycle_id}:{nxt}"
        await audit.record(cycle_id, nxt, "intent", idempotency_key=idem,
                           note=f"{tag} transition {state} → {nxt}"
                                + (f" — {decision.get('action')}" if decision else ""))
        ref = f"{'SHD' if is_shadow else 'SIM'}-{nxt[:6]}-{new_id()[:8]}"
        set_ops = {
            "prev_state": state, "state": nxt, "entered_state_at": now_iso(),
            "stuck": False, "stuck_reason": None, "recommended_action": None,
            "updated_at": now_iso(),
            "fund_location": {"current": FUND_LOCATION.get(nxt, "—"), "state": nxt},
        }
        if nxt in LEDGER_ON_ENTER:
            leg, desc = LEDGER_ON_ENTER[nxt]
            set_ops[f"ledger.{leg}"] = {"status": "confirmed", "reference": ref,
                                        "verified_at": now_iso(), "desc": desc}
        if nxt == "DEPOSIT_CONFIRMED":
            set_ops["ledger.exchange_balance"] = {
                "status": "confirmed", "reference": f"{cycle.get('bdag_qty_expected')} BDAG",
                "verified_at": now_iso()}
        if nxt == "SELL_FILLED":
            proceeds = (decision or {}).get("proceeds_quote")
            proceeds = round(proceeds if proceeds is not None else cycle.get("size_usd", 0), 2)
            set_ops["ledger.usdt_balance"] = {
                "status": "confirmed", "reference": f"{proceeds} USDT", "verified_at": now_iso()}
            if decision and decision.get("realized_pnl_quote") is not None:
                set_ops["realized_shadow_pnl_quote"] = round(decision["realized_pnl_quote"], 4)
                set_ops["realized_net_pct"] = decision.get("realized_net_pct")
        if nxt == "COMPLETE":
            set_ops["realized_pnl_quote"] = (cycle.get("realized_shadow_pnl_quote")
                                             if is_shadow else 0.0)
        push = {"history": {"state": nxt, "ts": now_iso()}}
        if decision:
            push["shadow_decisions"] = {**decision, "state": nxt, "ts": now_iso()}
        await db.execution_cycles.update_one(
            {"id": cycle_id},
            {"$set": set_ops, "$push": push})
        await audit.record(cycle_id, nxt, "result", idempotency_key=idem, external_ref=ref,
                           note=f"{tag} {state} → {nxt} (placeholder ref {ref})"
                                + (f" — {decision.get('action')}" if decision else ""))
        if nxt == "COMPLETE":
            try:
                from services.execution import permanent_ledger
                done = await db.execution_cycles.find_one({"id": cycle_id}, {"_id": 0})
                if (done or {}).get("mode") == "shadow":
                    await permanent_ledger.freeze_cycle(done)
            except Exception as e:
                logger.warning("permanent ledger freeze failed for %s: %s", cycle_id, e)
        return await db.execution_cycles.find_one({"id": cycle_id}, {"_id": 0})

    async def abort(self, cycle_id: str, reason: str = "manual abort") -> dict:
        cycle = await db.execution_cycles.find_one({"id": cycle_id}, {"_id": 0})
        if not cycle:
            raise ValueError("cycle not found")
        if cycle["state"] in TERMINAL:
            raise ValueError(f"cycle is already terminal ({cycle['state']})")
        await db.execution_cycles.update_one({"id": cycle_id}, {
            "$set": {"prev_state": cycle["state"], "state": "ABORTED", "stuck": False,
                     "stuck_reason": None, "recommended_action": None, "updated_at": now_iso(),
                     "fund_location": {"current": FUND_LOCATION["ABORTED"], "state": "ABORTED"}},
            "$push": {"history": {"state": "ABORTED", "ts": now_iso()}}})
        await audit.record(cycle_id, "ABORTED", "result", note=f"SIMULATED abort: {reason}")
        return await db.execution_cycles.find_one({"id": cycle_id}, {"_id": 0})

    async def force_manual_review(self, cycle_id: str, reason: str = "operator-forced review") -> dict:
        cycle = await db.execution_cycles.find_one({"id": cycle_id}, {"_id": 0})
        if not cycle:
            raise ValueError("cycle not found")
        if cycle["state"] in TERMINAL:
            raise ValueError(f"cycle is terminal ({cycle['state']})")
        return await self._to_manual_review(cycle, reason)

    async def _to_manual_review(self, cycle: dict, reason: str) -> dict:
        await db.execution_cycles.update_one({"id": cycle["id"]}, {
            "$set": {"prev_state": cycle["state"], "state": "MANUAL_REVIEW", "stuck": True,
                     "stuck_reason": reason, "recommended_action": RECOVERY["MANUAL_REVIEW"],
                     "updated_at": now_iso(),
                     "fund_location": {"current": FUND_LOCATION["MANUAL_REVIEW"], "state": "MANUAL_REVIEW"}},
            "$push": {"history": {"state": "MANUAL_REVIEW", "ts": now_iso()}}})
        await audit.record(cycle["id"], "MANUAL_REVIEW", "result", note=reason)
        await telegram_alerts.notify(
            "cycle_manual_review",
            f"🛑 Cycle {cycle['id'][:8]} → MANUAL_REVIEW: {reason} (SIMULATED)")
        return await db.execution_cycles.find_one({"id": cycle["id"]}, {"_id": 0})

    async def _resume(self, cycle: dict) -> dict:
        target = cycle.get("prev_state") or "CREATED"
        await db.execution_cycles.update_one({"id": cycle["id"]}, {
            "$set": {"state": target, "stuck": False, "stuck_reason": None,
                     "recommended_action": None, "entered_state_at": now_iso(), "updated_at": now_iso(),
                     "fund_location": {"current": FUND_LOCATION.get(target, "—"), "state": target}},
            "$push": {"history": {"state": target, "ts": now_iso()}}})
        await audit.record(cycle["id"], target, "result",
                           note=f"resumed from {cycle['state']} → {target} (SIMULATED)")
        return await db.execution_cycles.find_one({"id": cycle["id"]}, {"_id": 0})

    # ---------- stuck detection (restart-safe sweep) ----------
    async def _sweep_loop(self):
        while self._running:
            await asyncio.sleep(SWEEP_EVERY_S)
            try:
                await self._detect_stuck()
            except Exception as e:
                logger.warning("fund tracker sweep failed: %s", e)

    async def _detect_stuck(self):
        now = datetime.now(timezone.utc)
        candidates = await db.execution_cycles.find(
            {"state": {"$in": list(SLA_S.keys())}, "stuck": False}, {"_id": 0}).to_list(200)
        for c in candidates:
            sla = SLA_S.get(c["state"])
            if not sla:
                continue
            try:
                entered = datetime.fromisoformat(c["entered_state_at"])
            except (ValueError, KeyError, TypeError):
                continue
            elapsed = (now - entered).total_seconds()
            if elapsed <= sla:
                continue
            stuck_state = STUCK_STATE[c["state"]]
            rec = RECOVERY.get(stuck_state)
            await db.execution_cycles.update_one({"id": c["id"]}, {
                "$set": {"prev_state": c["state"], "state": stuck_state, "stuck": True,
                         "stuck_reason": f"no progress in {c['state']} for {int(elapsed)}s (SLA {sla}s)",
                         "recommended_action": rec, "updated_at": now_iso(),
                         "fund_location": {"current": FUND_LOCATION.get(stuck_state, "—"), "state": stuck_state}},
                "$push": {"history": {"state": stuck_state, "ts": now_iso()}}})
            await audit.record(c["id"], stuck_state, "result",
                               note=f"stuck detector: {c['state']} exceeded SLA {sla}s")
            await telegram_alerts.notify(
                "cycle_stuck",
                f"⚠️ Cycle {c['id'][:8]} → {stuck_state}. "
                f"Funds: {FUND_LOCATION.get(stuck_state, '—')}. Action: {rec} (SIMULATED)")

    # ---------- queries ----------
    async def list_cycles(self, limit: int = 100, state: str = None):
        q = {"state": state} if state else {}
        return await db.execution_cycles.find(q, {"_id": 0}, sort=[("created_at", -1)]).to_list(min(limit, 200))

    async def get_cycle(self, cycle_id: str):
        return await db.execution_cycles.find_one({"id": cycle_id}, {"_id": 0})

    # ---------- shadow-runner helpers (used by services.execution.shadow) ----------
    async def record_decision(self, cycle_id: str, decision: dict):
        """Attach a shadow 'would-do' decision without changing state (e.g. a blocked leg)."""
        await db.execution_cycles.update_one(
            {"id": cycle_id},
            {"$push": {"shadow_decisions": {**decision, "ts": now_iso()}},
             "$set": {"updated_at": now_iso()}})
        await audit.record(cycle_id, decision.get("state", "SHADOW"), "result",
                           note=f"SHADOW decision: {decision.get('action')}"
                                + (f" — {decision.get('reason')}" if decision.get("reason") else ""))

    async def set_stuck(self, cycle_id: str, stuck_state: str, reason: str, recommendation: str):
        cycle = await db.execution_cycles.find_one({"id": cycle_id}, {"_id": 0})
        if not cycle or cycle["state"] in TERMINAL or cycle.get("stuck"):
            return cycle
        await db.execution_cycles.update_one({"id": cycle_id}, {
            "$set": {"prev_state": cycle["state"], "state": stuck_state, "stuck": True,
                     "stuck_reason": reason, "recommended_action": recommendation,
                     "updated_at": now_iso(),
                     "fund_location": {"current": FUND_LOCATION.get(stuck_state, "—"), "state": stuck_state}},
            "$push": {"history": {"state": stuck_state, "ts": now_iso()}}})
        await audit.record(cycle_id, stuck_state, "result", note=f"stuck: {reason}")
        await telegram_alerts.notify(
            "cycle_stuck",
            f"⚠️ SHADOW cycle {cycle_id[:8]} → {stuck_state}. {reason}. Action: {recommendation}")
        return await db.execution_cycles.find_one({"id": cycle_id}, {"_id": 0})

    async def resume_to(self, cycle_id: str, target_state: str, note: str = "recovery"):
        await db.execution_cycles.update_one({"id": cycle_id}, {
            "$set": {"state": target_state, "stuck": False, "stuck_reason": None,
                     "recommended_action": None, "entered_state_at": now_iso(), "updated_at": now_iso(),
                     "fund_location": {"current": FUND_LOCATION.get(target_state, "—"), "state": target_state}},
            "$push": {"history": {"state": target_state, "ts": now_iso()}}})
        await audit.record(cycle_id, target_state, "recovery", note=note)
        return await db.execution_cycles.find_one({"id": cycle_id}, {"_id": 0})

    async def set_sell_venue(self, cycle_id: str, venue: str):
        await db.execution_cycles.update_one(
            {"id": cycle_id}, {"$set": {"sell_venue": venue, "updated_at": now_iso()}})

    # ---------- cycle timeline (replay view) ----------
    async def timeline(self, cycle_id: str):
        cycle = await db.execution_cycles.find_one({"id": cycle_id}, {"_id": 0})
        if not cycle:
            return None
        from datetime import datetime as _dt

        def _secs(a, b):
            try:
                return round((_dt.fromisoformat(b) - _dt.fromisoformat(a)).total_seconds(), 1)
            except (ValueError, TypeError):
                return None

        def _kind(s):
            if s in TERMINAL:
                return "terminal"
            if s.startswith("STUCK_"):
                return "stuck"
            if s == "MANUAL_REVIEW":
                return "review"
            if s.startswith("WAITING"):
                return "waiting"
            return "normal"

        hist = cycle.get("history", [])
        decisions = {d.get("state"): d for d in cycle.get("shadow_decisions", [])}
        terminal_now = cycle["state"] in TERMINAL or cycle.get("stuck")
        end_cap = cycle.get("updated_at") if terminal_now else now_iso()
        segments = []
        for i, h in enumerate(hist):
            start = h["ts"]
            end = hist[i + 1]["ts"] if i + 1 < len(hist) else end_cap
            segments.append({
                "state": h["state"], "start": start, "end": end,
                "duration_s": _secs(start, end), "kind": _kind(h["state"]),
                "fund_location": FUND_LOCATION.get(h["state"], "—"),
                "decision": decisions.get(h["state"]),
                "current": (i == len(hist) - 1) and cycle["state"] not in TERMINAL,
            })

        trail = await audit.trail(cycle_id)
        events = []
        for t in trail:
            if t.get("phase") == "recovery":
                events.append({"ts": t["ts"], "type": "recovery", "state": t.get("step"), "note": t.get("note")})
            elif str(t.get("step", "")).startswith("STUCK_"):
                events.append({"ts": t["ts"], "type": "stuck", "state": t.get("step"), "note": t.get("note")})
            elif t.get("step") == "MANUAL_REVIEW":
                events.append({"ts": t["ts"], "type": "manual_review", "state": t.get("step"), "note": t.get("note")})

        total_s = _secs(hist[0]["ts"], end_cap) if hist else None
        return {
            "cycle_id": cycle_id, "mode": cycle.get("mode", "scaffold"),
            "route_name": cycle.get("route_name"), "state": cycle["state"],
            "sell_venue": cycle.get("sell_venue"), "stuck": cycle.get("stuck", False),
            "recommended_action": cycle.get("recommended_action"),
            "size_usd": cycle.get("size_usd"), "qty_base": cycle.get("qty_base"),
            "buy_price_at_open": cycle.get("buy_price_at_open"),
            "expected_profit_quote": cycle.get("expected_profit_quote"),
            "expected_net_pct": cycle.get("expected_net_pct"),
            "realized_shadow_pnl_quote": cycle.get("realized_shadow_pnl_quote"),
            "realized_net_pct": cycle.get("realized_net_pct"),
            "total_duration_s": total_s,
            "segments": segments, "events": events,
            "shadow_decisions": cycle.get("shadow_decisions", []),
            "note": "Replay of state durations, recovery & stuck events, and shadow would-decisions. Read-only.",
        }

    async def status(self):
        total = await db.execution_cycles.count_documents({})
        open_n = await db.execution_cycles.count_documents({"state": {"$nin": list(TERMINAL)}})
        stuck_n = await db.execution_cycles.count_documents({"stuck": True})
        complete_n = await db.execution_cycles.count_documents({"state": "COMPLETE"})
        aborted_n = await db.execution_cycles.count_documents({"state": "ABORTED"})
        return {"running": self._running, "started_at": self.started_at,
                "recovered_on_start": self.recovered, "sweep_interval_s": SWEEP_EVERY_S,
                "state_flow": STATE_FLOW,
                "counters": {"cycles_total": total, "cycles_open": open_n,
                             "cycles_stuck": stuck_n, "cycles_complete": complete_n,
                             "cycles_aborted": aborted_n},
                "note": "SIMULATED / DRY-RUN scaffold — no real fund movement, no exchange/wallet calls."}


fund_tracker = FundTracker()
