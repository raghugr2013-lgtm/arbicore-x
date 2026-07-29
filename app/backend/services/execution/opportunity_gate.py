"""Phase E4.7 — Live Opportunity Gate, Freshness Engine, GO-Window Lifecycle &
Alerting (READ-ONLY, NON-EXECUTING).

Composes the Arbitrage Intelligence Engine + Exchange Qualification + live gate
status + data freshness into a single, STRICT opportunity verdict. A GO verdict
is only allowed when ALL hold:
  • positive net ROI after all fees
  • sufficient profitable depth
  • stable buyer liquidity
  • qualified venue (not disabled, gates not closed)
  • fresh data sources (buy price / order book / gate status / qualification)

A background monitor tracks GO-window lifecycle (open/close, duration, peak/avg
ROI, max safe buy), persists every window to `opportunity_windows` for analysis,
and fires Telegram alerts (DORMANT until the operator supplies a bot token):
GO opened, GO closed, venue qualification changed, deposit gate changed,
withdrawal gate changed.

NO execution, NO orders, NO wallet actions, NO fund movement.
"""
import asyncio
import logging
from datetime import datetime, timezone

from core.models import new_id, now_iso
from services import db
from services.execution import arbitrage_intel, exchange_intelligence
from services.execution import fresh_cycle_analytics
from services.telegram_alerts import telegram_alerts

logger = logging.getLogger("opportunity_gate")

CHECK_S = 20

# data-source staleness thresholds (seconds)
FRESHNESS = {
    "buy_price_portal_s": 300,    # only the live PORTAL feed decays; cost-basis/manual are static
    "order_book_s": 120,
    "gate_status_s": 3600,
    "qualification_s": 7 * 86400,
}
# a GO requires the profitable quote depth to at least cover the certification cap
MIN_PROFITABLE_DEPTH_FACTOR = 1.0


def _age(ts):
    if not ts:
        return None
    try:
        return round((datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds(), 1)
    except (ValueError, TypeError):
        return None


def _fresh_item(source, ts, age, threshold, fresh, note=None):
    return {"source": source, "timestamp": ts, "age_s": age, "threshold_s": threshold,
            "fresh": fresh, "note": note}


async def _freshness(route, resolution, venue):
    # --- buy price ---
    bp_src = resolution.get("source")
    bp_ts = resolution.get("timestamp")
    bp_age = _age(bp_ts)
    if bp_src == "portal":
        bp_fresh = bp_age is not None and bp_age <= FRESHNESS["buy_price_portal_s"]
        bp = _fresh_item(f"buy_price:{bp_src}", bp_ts, bp_age, FRESHNESS["buy_price_portal_s"], bp_fresh,
                         "Live portal feed — decays.")
    else:
        bp = _fresh_item(f"buy_price:{bp_src}", bp_ts, bp_age, None, True,
                         "Cost-basis / manual source — static, does not decay.")

    # --- order book ---
    snap = await db.orderbook_snapshots.find_one(
        {"route_id": route["id"], "exchange": venue}, {"_id": 0, "created_at": 1, "ts": 1},
        sort=[("created_at", -1)])
    ob_ts = (snap or {}).get("created_at") or (snap or {}).get("ts")
    ob_age = _age(ob_ts)
    ob_fresh = ob_age is not None and ob_age <= FRESHNESS["order_book_s"]
    ob = _fresh_item(f"order_book:{venue}", ob_ts, ob_age, FRESHNESS["order_book_s"], ob_fresh)

    # --- gate status ---
    cap = await db.capabilities_col.find_one({"exchange": venue, "currency": "BDAG"},
                                             {"_id": 0, "updated_at": 1, "ts": 1})
    if cap:
        g_ts = cap.get("updated_at") or cap.get("ts")
        g_age = _age(g_ts)
        g_fresh = g_age is not None and g_age <= FRESHNESS["gate_status_s"]
        gate = _fresh_item(f"gate_status:{venue}", g_ts, g_age, FRESHNESS["gate_status_s"], g_fresh)
    else:
        gate = _fresh_item(f"gate_status:{venue}", None, None, None, True,
                           "No live capability flips tracked (operator-verified baseline).")

    # --- exchange qualification ---
    qrec = await exchange_intelligence.get_one(venue)
    q_ts = (qrec or {}).get("last_verified")
    q_age = _age(q_ts)
    if (qrec or {}).get("data_source") == "live":
        qual = _fresh_item(f"qualification:{venue}", q_ts, q_age, FRESHNESS["qualification_s"], True,
                           "Live qualification overlay.")
    else:
        q_fresh = q_age is not None and q_age <= FRESHNESS["qualification_s"]
        qual = _fresh_item(f"qualification:{venue}", q_ts, q_age, FRESHNESS["qualification_s"], q_fresh,
                           "Curated audit baseline.")

    items = [bp, ob, gate, qual]
    return {"all_fresh": all(i["fresh"] for i in items),
            "stale_sources": [i["source"] for i in items if not i["fresh"]],
            "buy_price": bp, "order_book": ob, "gate_status": gate, "qualification": qual}


async def evaluate(route_id: str) -> dict:
    """Strict opportunity verdict for one route. GO only when every condition holds."""
    intel = await arbitrage_intel.analyze(route_id)
    route = await db.routes_col.find_one({"id": route_id}, {"_id": 0})
    if not intel.get("available"):
        return {"route_id": route_id, "route_name": (route or {}).get("name"),
                "gate_verdict": "NO_GO", "intel_verdict": intel.get("verdict", "NO_GO"),
                "available": False, "conditions": [],
                "reasons": [intel.get("note", "intel unavailable")],
                "note": "No live opportunity surface.", "generated_at": now_iso()}

    venue = intel["sell_venue"]
    resolution = intel.get("buy_price_resolution", {})
    fresh = await _freshness(route, resolution, venue)
    qrec = await exchange_intelligence.get_one(venue) or {}
    msb = intel.get("max_safe_buy") or {}
    rec = intel.get("recommended") or {}
    roi = rec.get("roi_pct")
    prof_quote = intel["profitable_liquidity"]["profitable_quote"]
    min_roi = intel["limits"]["min_net_spread_pct"]
    cap = intel["limits"]["max_cycle_usd"]
    stability = intel["buyer_stability"]["label"]
    dep_status = qrec.get("deposit_status")
    wd_status = qrec.get("withdrawal_status")

    venue_qualified = (qrec.get("status") != "disabled"
                       and dep_status not in ("closed", "suspended")
                       and wd_status not in ("closed", "suspended"))

    conditions = [
        {"key": "positive_roi", "label": "Positive net ROI after all fees",
         "passed": bool(roi is not None and roi > 0), "detail": f"net ROI {roi}%"},
        {"key": "roi_above_floor", "label": f"ROI ≥ floor {min_roi}%",
         "passed": bool(roi is not None and roi >= min_roi), "detail": f"net ROI {roi}% vs {min_roi}%"},
        {"key": "sufficient_depth", "label": "Sufficient profitable depth",
         "passed": prof_quote >= cap * MIN_PROFITABLE_DEPTH_FACTOR,
         "detail": f"${prof_quote} profitable vs cap ${cap}"},
        {"key": "stable_liquidity", "label": "Stable buyer liquidity",
         "passed": stability in ("STABLE", "MODERATE"), "detail": f"buyer stability {stability}"},
        {"key": "qualified_venue", "label": "Qualified venue (gates open, not disabled)",
         "passed": venue_qualified,
         "detail": f"{venue} status={qrec.get('status')} dep={dep_status} wd={wd_status}"},
        {"key": "fresh_sources", "label": "Fresh data sources",
         "passed": fresh["all_fresh"],
         "detail": "all fresh" if fresh["all_fresh"] else f"stale: {', '.join(fresh['stale_sources'])}"},
    ]
    failed = [c for c in conditions if not c["passed"]]

    # hard blockers force NO_GO; otherwise any failed condition is WAIT
    hard = {"positive_roi", "qualified_venue"}
    if any(c["key"] in hard for c in failed):
        verdict = "NO_GO"
    elif not failed:
        verdict = "GO"
    else:
        verdict = "WAIT"

    reason_codes = [c["key"] for c in failed]
    return {
        "route_id": route_id, "route_name": route.get("name"), "available": True,
        "gate_verdict": verdict, "intel_verdict": intel["verdict"],
        "venue": venue, "venue_status": qrec.get("status"),
        "deposit_status": dep_status, "withdrawal_status": wd_status,
        "roi_pct": roi, "min_roi_pct": min_roi,
        "profitable_liquidity_quote": prof_quote,
        "max_safe_buy_usd": msb.get("max_safe_buy_usd"),
        "recommended_buy_usd": rec.get("investment_usd"),
        "executable_sizing": intel.get("executable_sizing"),
        "min_executable_usd": (intel.get("executable_sizing") or {}).get("min_executable_size_usd"),
        "actual_executable_recommendation_usd": (intel.get("executable_sizing") or {}).get("actual_executable_recommendation_usd"),
        "buyer_stability": stability, "buy_price_source": resolution.get("source"),
        "best_bid": intel.get("best_bid"),
        "dual_roi": intel.get("dual_roi"),
        "conditions": conditions, "failed_conditions": reason_codes,
        "freshness": fresh,
        "reasons": ([c["label"] for c in failed] if failed
                    else [f"All gate conditions hold — net ROI {roi}% on qualified {venue} with fresh data."]),
        "note": "Read-only opportunity gate. NO execution, NO orders, NO fund movement.",
        "generated_at": now_iso(),
    }


# ---------------------------------------------------------------------------
# GO-window lifecycle + history + alerting monitor
# ---------------------------------------------------------------------------
def _reason_opened(g):
    return f"net ROI {g['roi_pct']}% on {g['venue']} (qualified, fresh, stable depth ${g['profitable_liquidity_quote']})"


def _reason_closed(g):
    if not g.get("available"):
        return "opportunity surface unavailable"
    fc = g.get("failed_conditions") or []
    label = {"positive_roi": "ROI turned non-positive", "roi_above_floor": "ROI fell below floor",
             "sufficient_depth": "profitable depth disappeared", "stable_liquidity": "buyer liquidity destabilized",
             "qualified_venue": "venue de-qualified / gate closed", "fresh_sources": "data went stale"}
    return "; ".join(label.get(c, c) for c in fc) or f"gate verdict {g['gate_verdict']}"


class OpportunityGateMonitor:
    def __init__(self):
        self._task = None
        self._running = False
        self._state = {}   # route_id -> {venue, qualification, deposit, withdraw}

    async def start_monitor(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Opportunity gate monitor started (read-only).")

    async def stop_monitor(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self):
        await asyncio.sleep(10)
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.warning("opportunity monitor tick failed: %s", e)
            await asyncio.sleep(CHECK_S)

    async def _routes(self):
        return await db.routes_col.find({"purchase.asset": "BDAG"}, {"_id": 0, "id": 1, "name": 1}).to_list(20)

    async def _tick(self):
        for r in await self._routes():
            try:
                g = await evaluate(r["id"])
            except Exception as e:
                logger.warning("evaluate failed for %s: %s", r["id"], e)
                continue
            try:
                await fresh_cycle_analytics.record(g)
            except Exception as e:
                logger.warning("fresh_cycle_analytics.record failed for %s: %s", r["id"], e)
            await self._track_state_changes(r["id"], g)
            await self._track_window(r["id"], g)

    async def _track_state_changes(self, route_id, g):
        if not g.get("available"):
            return
        prev = self._state.get(route_id)
        cur = {"venue": g["venue"], "qualification": g["venue_status"],
               "deposit": g["deposit_status"], "withdraw": g["withdrawal_status"]}
        if prev is None:
            self._state[route_id] = cur     # seed silently (no alert on first/restart)
            return
        if prev.get("qualification") != cur["qualification"]:
            await telegram_alerts.notify("venue_qualification_changed",
                f"⚠️ {g['venue'].upper()} qualification changed: {prev['qualification']} → {cur['qualification']} ({g['route_name']})")
        if prev.get("deposit") != cur["deposit"]:
            await telegram_alerts.notify("deposit_gate_changed",
                f"🚪 {g['venue'].upper()} DEPOSIT gate changed: {prev['deposit']} → {cur['deposit']} ({g['route_name']})")
        if prev.get("withdraw") != cur["withdraw"]:
            await telegram_alerts.notify("withdrawal_gate_changed",
                f"🚪 {g['venue'].upper()} WITHDRAWAL gate changed: {prev['withdraw']} → {cur['withdraw']} ({g['route_name']})")
        self._state[route_id] = cur

    async def _track_window(self, route_id, g):
        active = await db.opportunity_windows.find_one({"route_id": route_id, "status": "open"}, {"_id": 0})
        is_go = g.get("gate_verdict") == "GO"

        if is_go and not active:
            await self._open_window(g)
        elif is_go and active:
            await self._update_window(active, g)
        elif not is_go and active:
            await self._close_window(active, g)

    async def _open_window(self, g):
        roi = g["roi_pct"]
        win = {
            "id": new_id(), "route_id": g["route_id"], "route_name": g["route_name"],
            "venue": g["venue"], "status": "open",
            "opened_at": now_iso(), "closed_at": None, "duration_s": None,
            "roi_open": roi, "roi_peak": roi, "roi_last": roi,
            "roi_sum": roi or 0, "roi_samples": 1,
            "roi_avg": roi, "profitable_liquidity_quote": g["profitable_liquidity_quote"],
            "safe_buy_size_usd": g.get("max_safe_buy_usd"),
            "buy_price_source": g.get("buy_price_source"),
            "stability_label": g.get("buyer_stability"),
            "reason_opened": _reason_opened(g), "reason_closed": None,
            "created_at": now_iso(), "updated_at": now_iso(),
        }
        await db.opportunity_windows.insert_one(dict(win))
        await telegram_alerts.notify("go_opened",
            f"🟢 GO window OPENED — {g['venue'].upper()} {g['route_name']}: net ROI {roi}%, "
            f"safe buy ${g.get('max_safe_buy_usd')}, profitable depth ${g['profitable_liquidity_quote']}.",
            net_pct=roi)
        logger.info("GO window opened for %s on %s (ROI %s%%)", g["route_name"], g["venue"], roi)

    async def _update_window(self, win, g):
        roi = g["roi_pct"]
        samples = win["roi_samples"] + 1
        roi_sum = (win["roi_sum"] or 0) + (roi or 0)
        await db.opportunity_windows.update_one({"id": win["id"]}, {"$set": {
            "roi_last": roi, "roi_peak": max(win["roi_peak"] or roi, roi) if roi is not None else win["roi_peak"],
            "roi_sum": roi_sum, "roi_samples": samples, "roi_avg": round(roi_sum / samples, 3),
            "profitable_liquidity_quote": g["profitable_liquidity_quote"],
            "safe_buy_size_usd": max(win.get("safe_buy_size_usd") or 0, g.get("max_safe_buy_usd") or 0),
            "updated_at": now_iso()}})

    async def _close_window(self, win, g):
        opened = win["opened_at"]
        dur = _age(opened)
        await db.opportunity_windows.update_one({"id": win["id"]}, {"$set": {
            "status": "closed", "closed_at": now_iso(), "duration_s": dur,
            "reason_closed": _reason_closed(g), "updated_at": now_iso()}})
        await telegram_alerts.notify("go_closed",
            f"🔴 GO window CLOSED — {win['venue'].upper()} {win['route_name']}: lasted {dur}s, "
            f"peak ROI {win['roi_peak']}%, avg ROI {win['roi_avg']}%. Reason: {_reason_closed(g)}.")
        logger.info("GO window closed for %s on %s (%ss)", win["route_name"], win["venue"], dur)

    async def status(self):
        active = await db.opportunity_windows.find({"status": "open"}, {"_id": 0}).to_list(20)
        return {"monitor_running": self._running, "check_interval_s": CHECK_S,
                "active_windows": active, "freshness_thresholds": FRESHNESS}

    async def history(self, limit: int = 100):
        wins = await db.opportunity_windows.find({}, {"_id": 0}, sort=[("created_at", -1)]).to_list(min(limit, 500))
        closed = [w for w in wins if w["status"] == "closed"]
        durations = [w["duration_s"] for w in closed if w.get("duration_s")]
        peaks = [w["roi_peak"] for w in closed if w.get("roi_peak") is not None]
        return {
            "windows": wins,
            "summary": {
                "total_windows": len(wins),
                "open": sum(1 for w in wins if w["status"] == "open"),
                "closed": len(closed),
                "avg_duration_s": round(sum(durations) / len(durations), 1) if durations else None,
                "max_duration_s": max(durations) if durations else None,
                "avg_peak_roi_pct": round(sum(peaks) / len(peaks), 3) if peaks else None,
                "best_peak_roi_pct": max(peaks) if peaks else None,
            },
            "note": "Every GO window is recorded for later analysis. Read-only, no fund movement.",
        }


opportunity_monitor = OpportunityGateMonitor()
