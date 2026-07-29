"""Observation Recorder (Sprint 4.5) — PURE DATA CAPTURE for the observation
phase. Persists the time-series evidence the future engines (Readiness Trend,
Exchange Trust Score, Survivability Analysis, Gate Cost Analysis, Confidence
Calibration) will be built on. No execution, no trading, no transfers.

Captures:
  1. readiness_snapshots — hourly per-venue readiness score + all factors + health
  2. episodes            — every raw/exec opportunity episode incl. decay profile
  3. gate_cost_ledger    — blocked opportunities with estimated missed profit
  4. calibration_log     — predicted confidence vs realized horizon survival
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from core.models import new_id, now_iso
from engines import quality
from engines.economics import ts_secs
from services import db

logger = logging.getLogger("observation")

SNAPSHOT_EVERY_S = 3600
FIRST_SNAPSHOT_DELAY_S = 300
SWEEP_EVERY_S = 60
EPISODE_GAP_S = 180        # close an open episode if no samples arrive this long
MAX_EPISODE_HOURS = 12     # roll persistent opportunities over to keep docs bounded
MAX_PROFILE_POINTS = 120
PREDICTION_THROTTLE_S = 300
RESOLVE_GRACE_S = 600


class ObservationRecorder:
    def __init__(self):
        self._open = {}        # (route_id, exchange, kind) -> episode accumulator
        self._last_pred = {}   # (route_id, exchange) -> monotonic
        self._tasks = []
        self._running = False
        self.started_at = None
        self.last_snapshot_at = None
        self.snapshot_docs = 0

    # ---------- lifecycle ----------
    async def start(self):
        if self._running:
            return
        self._running = True
        self.started_at = now_iso()
        self._tasks = [asyncio.create_task(self._snapshot_loop()),
                       asyncio.create_task(self._sweep_loop())]
        logger.info("Observation recorder started (snapshots hourly)")

    async def stop(self):
        self._running = False
        for key in list(self._open):
            try:
                await self._finalize(key, end_reason="shutdown")
            except Exception:
                pass
        for t in self._tasks:
            t.cancel()
        self._tasks = []

    # ---------- 1. hourly readiness snapshots ----------
    async def _snapshot_loop(self):
        await asyncio.sleep(FIRST_SNAPSHOT_DELAY_S)
        while self._running:
            try:
                await self.snapshot_now()
            except Exception as e:
                logger.warning("readiness snapshot failed: %s", e)
            await asyncio.sleep(SNAPSHOT_EVERY_S)

    async def snapshot_now(self) -> int:
        routes = await db.routes_col.find({"active": True}, {"_id": 0}).to_list(50)
        total = 0
        for route in routes:
            rep = await quality.route_quality_report(route, 24)
            ts = now_iso()
            docs = []
            for v in rep["venues"]:
                h = rep["health"].get(v["exchange"]) or {}
                docs.append({"id": new_id(), "ts": ts, "created_at": ts,
                             "route_id": route["id"], "hours_window": 24,
                             "mode": route.get("mode", "live"),
                             "exchange": v["exchange"],
                             "readiness_score": v["readiness_score"],
                             "readiness_label": v["readiness_label"],
                             "factors": v["factors"], "metrics": v["metrics"],
                             "reliability_score": h.get("reliability_score"),
                             "api_uptime_pct": h.get("api_uptime_pct"),
                             "deposit_uptime_pct": h.get("deposit_uptime_pct"),
                             "withdraw_uptime_pct": h.get("withdraw_uptime_pct"),
                             "flips_per_day": h.get("flips_per_day")})
            if docs:
                await db.readiness_snapshots.insert_many(docs)
                total += len(docs)
        self.last_snapshot_at = now_iso()
        self.snapshot_docs += total
        return total

    # ---------- 2+3. episode tracking / gate cost ----------
    async def on_evaluation(self, route, ev):
        """Hook from the collector after each persisted evaluation. Never raises."""
        try:
            if route.get("mode", "live") != "live":
                return  # observation records real-world evidence only
            rid = route["id"]
            min_net = route.get("risk_profile", {}).get("min_net_spread_pct", 2.0)
            ts = ev["ts"]
            bp = (ev.get("inputs") or {}).get("buy_price")
            hold = ev.get("hold_probability") or {}
            for entry in ev.get("venue_matrix", []):
                ex = entry["exchange"]
                net = entry.get("net_spread_pct")
                raw_open = net is not None and net >= min_net
                exec_open = entry.get("verdict") == "GO"
                await self._track(rid, ex, "raw", raw_open, ts, entry, bp, min_net)
                await self._track(rid, ex, "exec", exec_open, ts, entry, bp, min_net)
                if raw_open:
                    await self._maybe_predict(rid, ex, ts, entry, hold, min_net)
        except Exception as e:
            logger.warning("observation on_evaluation failed: %s", e)

    async def _track(self, rid, ex, kind, is_open, ts, entry, bp, min_net):
        key = (rid, ex, kind)
        ep = self._open.get(key)
        if not is_open:
            if ep is not None:
                await self._finalize(
                    key, end_reason="spread_decayed" if kind == "raw" else "verdict_closed")
            return
        net = entry.get("net_spread_pct")
        rec = entry.get("recommended")
        if ep is None:
            ep = {"id": new_id(), "route_id": rid, "exchange": ex, "kind": kind,
                  "start": ts, "end": ts, "min_net": min_net, "samples": 0,
                  "net_sum": 0.0, "net_n": 0, "peak_net": net, "start_net": net,
                  "end_net": net, "rec_sum": 0.0, "rec_n": 0,
                  "profit_sum": 0.0, "profit_n": 0, "go_samples": 0,
                  "blocking": {}, "profile": [],
                  "_mono0": time.monotonic(), "_last_mono": time.monotonic()}
            self._open[key] = ep
        ep["end"] = ts
        ep["samples"] += 1
        ep["_last_mono"] = time.monotonic()
        if net is not None:
            ep["net_sum"] += net
            ep["net_n"] += 1
            ep["end_net"] = net
            if ep["peak_net"] is None or net > ep["peak_net"]:
                ep["peak_net"] = net
            ep["profile"].append([round(time.monotonic() - ep["_mono0"]), round(net, 3)])
            if len(ep["profile"]) > MAX_PROFILE_POINTS:
                ep["profile"] = ep["profile"][::2]  # thin while keeping shape
        if rec:
            ep["rec_sum"] += rec
            ep["rec_n"] += 1
            if net is not None and bp:
                ep["profit_sum"] += rec * bp * net / 100
                ep["profit_n"] += 1
        verdict = entry.get("verdict")
        if verdict == "GO":
            ep["go_samples"] += 1
        elif kind == "raw":
            blocker = ("deposit_gate" if entry.get("deposit_enabled") is False
                       else f"verdict_{(verdict or 'unknown').lower()}")
            ep["blocking"][blocker] = ep["blocking"].get(blocker, 0) + 1
        if time.monotonic() - ep["_mono0"] > MAX_EPISODE_HOURS * 3600:
            await self._finalize(key, end_reason="rollover")

    async def _finalize(self, key, end_reason):
        ep = self._open.pop(key, None)
        if ep is None or ep["samples"] == 0:
            return
        duration_min = round((ts_secs(ep["start"], ep["end"]) + 10) / 60, 2)
        avg_net = round(ep["net_sum"] / ep["net_n"], 3) if ep["net_n"] else None
        avg_rec = round(ep["rec_sum"] / ep["rec_n"], 1) if ep["rec_n"] else None
        est_profit = round(ep["profit_sum"] / ep["profit_n"], 2) if ep["profit_n"] else None
        had_go = ep["go_samples"] > 0
        if ep["kind"] == "exec":
            outcome = "completed"
        else:
            outcome = "captured_window" if had_go else "blocked"
        doc = {"id": ep["id"], "route_id": ep["route_id"], "exchange": ep["exchange"],
               "kind": ep["kind"], "start": ep["start"], "end": ep["end"], "ts": ep["start"],
               "duration_min": duration_min, "samples": ep["samples"],
               "peak_net_pct": round(ep["peak_net"], 3) if ep["peak_net"] is not None else None,
               "avg_net_pct": avg_net,
               "start_net_pct": round(ep["start_net"], 3) if ep["start_net"] is not None else None,
               "end_net_pct": round(ep["end_net"], 3) if ep["end_net"] is not None else None,
               "decay_profile": ep["profile"][:MAX_PROFILE_POINTS],
               "avg_capacity_base": avg_rec, "est_profit_quote": est_profit,
               "had_go": had_go, "go_samples": ep["go_samples"],
               "outcome": outcome, "end_reason": end_reason,
               "blocking": ep["blocking"], "min_net": ep["min_net"],
               "created_at": now_iso()}
        await db.episodes_col.insert_one(dict(doc))
        if ep["kind"] == "raw" and not had_go:
            primary = max(ep["blocking"], key=ep["blocking"].get) if ep["blocking"] else "unknown"
            await db.gate_cost_ledger.insert_one({
                "id": new_id(), "ts": ep["start"], "route_id": ep["route_id"],
                "exchange": ep["exchange"], "start": ep["start"], "end": ep["end"],
                "blocked_minutes": duration_min,
                "est_missed_profit_quote": est_profit,
                "peak_net_pct": doc["peak_net_pct"], "avg_net_pct": avg_net,
                "avg_capacity_base": avg_rec, "blocking": ep["blocking"],
                "primary_blocker": primary, "episode_id": ep["id"],
                "created_at": now_iso()})

    # ---------- 4. confidence calibration ----------
    async def _maybe_predict(self, rid, ex, ts, entry, hold, min_net):
        key = (rid, ex)
        now = time.monotonic()
        if now - self._last_pred.get(key, -1e9) < PREDICTION_THROTTLE_S:
            return
        self._last_pred[key] = now
        horizon_min = int(hold.get("horizon_min") or 30)
        resolve_after = (datetime.fromisoformat(ts) + timedelta(minutes=horizon_min)).isoformat()
        await db.calibration_log.insert_one({
            "id": new_id(), "ts": ts, "created_at": now_iso(),
            "route_id": rid, "exchange": ex,
            "predicted_confidence": entry.get("confidence"),
            "hold_probability": hold.get("probability"),
            "net_pct_at_prediction": round(entry["net_spread_pct"], 3)
            if entry.get("net_spread_pct") is not None else None,
            "min_net": min_net, "horizon_min": horizon_min,
            "resolve_after": resolve_after, "status": "pending"})

    async def _sweep_loop(self):
        while self._running:
            await asyncio.sleep(SWEEP_EVERY_S)
            try:
                for key, ep in list(self._open.items()):
                    if time.monotonic() - ep["_last_mono"] > EPISODE_GAP_S:
                        await self._finalize(key, end_reason="data_gap")
                await self._resolve_due()
            except Exception as e:
                logger.warning("observation sweep failed: %s", e)

    async def _resolve_due(self):
        now = datetime.now(timezone.utc)
        due = await db.calibration_log.find(
            {"status": "pending", "resolve_after": {"$lte": now.isoformat()}},
            {"_id": 0}).to_list(200)
        for d in due:
            target = d["resolve_after"]
            window_end = (datetime.fromisoformat(target) + timedelta(minutes=3)).isoformat()
            ev = await db.evaluations.find_one(
                {"route_id": d["route_id"], "ts": {"$gte": target, "$lte": window_end},
                 "mode": "live"},
                {"_id": 0, "venue_matrix": 1, "ts": 1}, sort=[("ts", 1)])
            entry = None
            if ev:
                entry = next((e for e in ev.get("venue_matrix", [])
                              if e["exchange"] == d["exchange"]), None)
            if entry is not None and entry.get("net_spread_pct") is not None:
                realized = entry["net_spread_pct"]
                await db.calibration_log.update_one({"id": d["id"]}, {"$set": {
                    "status": "resolved", "realized_net_pct": round(realized, 3),
                    "survived": realized >= d["min_net"], "resolved_at": now_iso()}})
            elif (now - datetime.fromisoformat(target)).total_seconds() > RESOLVE_GRACE_S:
                await db.calibration_log.update_one({"id": d["id"]}, {"$set": {
                    "status": "unresolved", "resolved_at": now_iso()}})

    # ---------- status ----------
    async def status(self):
        snaps = await db.readiness_snapshots.count_documents({})
        raw_eps = await db.episodes_col.count_documents({"kind": "raw"})
        exec_eps = await db.episodes_col.count_documents({"kind": "exec"})
        ledger_n = await db.gate_cost_ledger.count_documents({})
        agg = await db.gate_cost_ledger.aggregate([
            {"$group": {"_id": None, "minutes": {"$sum": "$blocked_minutes"},
                        "profit": {"$sum": "$est_missed_profit_quote"}}}]).to_list(1)
        pending = await db.calibration_log.count_documents({"status": "pending"})
        resolved = await db.calibration_log.count_documents({"status": "resolved"})
        unresolved = await db.calibration_log.count_documents({"status": "unresolved"})
        survived = await db.calibration_log.count_documents({"status": "resolved", "survived": True})
        return {"running": self._running, "started_at": self.started_at,
                "last_snapshot_at": self.last_snapshot_at,
                "snapshot_interval_s": SNAPSHOT_EVERY_S,
                "counters": {
                    "readiness_snapshots": snaps,
                    "episodes_raw": raw_eps, "episodes_exec": exec_eps,
                    "gate_cost_entries": ledger_n,
                    "blocked_minutes_total": round((agg[0]["minutes"] if agg else 0) or 0, 1),
                    "missed_profit_total_quote": round((agg[0]["profit"] if agg else 0) or 0, 2),
                    "calibration_pending": pending,
                    "calibration_resolved": resolved,
                    "calibration_unresolved": unresolved,
                    "calibration_survival_rate_pct":
                        round(survived / resolved * 100, 1) if resolved else None},
                "open_episodes": [
                    {"route_id": k[0], "exchange": k[1], "kind": k[2], "start": ep["start"],
                     "samples": ep["samples"],
                     "peak_net_pct": round(ep["peak_net"], 3) if ep["peak_net"] is not None else None}
                    for k, ep in self._open.items()],
                "note": "Pure data capture — no execution, no transfers, no trading."}


observation = ObservationRecorder()
