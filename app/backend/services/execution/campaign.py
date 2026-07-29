"""Phase E4.5 — Shadow Certification Campaign (hands-off, NON-EXECUTING).

Runs Shadow Mode to a target number of COMPLETED shadow cycles, continuously
tracking the certification metrics, and AUTO-STOPS on a breach (stuck-rate,
variance, or recovery failure). At completion it generates an updated Shadow
Certification Report scoped to the campaign window. The campaign owns the
shadow_enabled flag while running.

E5 (micro-capital) stays blocked until the campaign's final certification verdict
is READY_FOR_MICROCAPITAL_REVIEW. No trading / withdrawals / wallet / fund movement.
"""
import asyncio
import logging

from core.models import new_id, now_iso
from services import db
from services.execution import certification, certification_review, config
from services.telegram_alerts import telegram_alerts

logger = logging.getLogger("shadow_campaign")

CHECK_S = 20
DEFAULT_TARGET = 20
DEFAULT_THRESHOLDS = {
    "max_stuck_rate_pct": 40.0,     # stop if stuck/total exceeds this (once min_sample reached)
    "max_variance_pct": 35.0,       # stop if |avg variance| / avg expected exceeds this (once >=3 completed)
    "min_recovery_rate_pct": 70.0,  # stop if recovery success-rate drops below this (once >=3 ever-stuck)
    "min_sample": 5,
}
ACTIVE = {"running"}


def _merge_thresholds(patch):
    th = dict(DEFAULT_THRESHOLDS)
    for k, v in (patch or {}).items():
        if k in th and isinstance(v, (int, float)):
            th[k] = float(v)
    return th


class ShadowCampaign:
    def __init__(self):
        self._task = None
        self._running = False

    async def start_monitor(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Shadow campaign monitor started.")

    async def stop_monitor(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self):
        await asyncio.sleep(8)
        while self._running:
            try:
                await self._check()
            except Exception as e:
                logger.warning("campaign check failed: %s", e)
            await asyncio.sleep(CHECK_S)

    async def _active(self):
        return await db.shadow_campaigns.find_one({"status": {"$in": list(ACTIVE)}}, {"_id": 0})

    # ---------- evaluation ----------
    async def _check(self):
        camp = await self._active()
        if not camp:
            return
        cfg = await config.get_config()
        if not cfg.get("shadow_enabled"):
            await config.update_config({"shadow_enabled": True})  # campaign owns the flag
        rep = await certification.report(since=camp["start_at"])
        tp, rc, pf = rep["throughput"], rep["recovery"], rep["profit"]
        completed = tp["completed"]
        total = tp["total_shadow_cycles"]
        avg_var = pf["average_variance_quote"]
        avg_exp = pf["average_expected_per_cycle"]
        var_pct = round(abs(avg_var) / avg_exp * 100, 1) if (avg_var is not None and avg_exp) else None
        stuck_rate = round(rc["ever_stuck"] / total * 100, 1) if total else 0

        await db.shadow_campaigns.update_one({"id": camp["id"]}, {"$set": {
            "completed_count": completed, "total_count": total,
            "stuck_rate_pct": stuck_rate, "variance_pct": var_pct,
            "recovery_success_rate_pct": rc["recovery_success_rate_pct"],
            "recovery_failures": rc["recovery_failures"],
            "last_checked_at": now_iso(), "updated_at": now_iso()}})

        th = camp["thresholds"]
        breach = None
        if rc["recovery_failures"] > 0:
            breach = f"recovery failure — {rc['recovery_failures']} cycle(s) aborted while stuck"
        elif total >= th["min_sample"] and stuck_rate > th["max_stuck_rate_pct"]:
            breach = f"stuck-rate {stuck_rate}% exceeds threshold {th['max_stuck_rate_pct']}%"
        elif rc["ever_stuck"] >= 3 and rc["recovery_success_rate_pct"] is not None \
                and rc["recovery_success_rate_pct"] < th["min_recovery_rate_pct"]:
            breach = (f"recovery success-rate {rc['recovery_success_rate_pct']}% below "
                      f"threshold {th['min_recovery_rate_pct']}%")
        elif completed >= 3 and var_pct is not None and var_pct > th["max_variance_pct"]:
            breach = f"variance {var_pct}% exceeds threshold {th['max_variance_pct']}%"

        if breach:
            await self._finalize(camp, "stopped_breach", breach)
        elif completed >= camp["target_completed"]:
            await self._finalize(camp, "completed", None)

    async def _gate_context(self):
        """Snapshot of the E4.7 opportunity-gated architecture for the evidence package."""
        try:
            from services.execution import opportunity_gate, safety_interlock
            route = await db.routes_col.find_one({"purchase.asset": "BDAG"}, {"_id": 0, "id": 1, "name": 1})
            rid = (route or {}).get("id")
            interlock = await safety_interlock.evaluate(rid)
            gate = await opportunity_gate.evaluate(rid) if rid else {}
            return {
                "captured_at": now_iso(), "architecture": "opportunity-gated (E4.7)",
                "route_id": rid, "route_name": (route or {}).get("name"),
                "interlock_verdict": interlock.get("verdict"),
                "interlocks": interlock.get("interlocks"),
                "interlock_blocked_reasons": interlock.get("blocked_reasons"),
                "interlock_wait_reasons": interlock.get("wait_reasons"),
                "gate_verdict": gate.get("gate_verdict"),
                "gate_conditions": gate.get("conditions"),
                "freshness_all_fresh": (gate.get("freshness") or {}).get("all_fresh"),
                "venue": gate.get("venue"), "roi_pct": gate.get("roi_pct"),
            }
        except Exception as e:
            logger.warning("gate_context capture failed: %s", e)
            return None

    async def _finalize(self, camp, status, breach):
        await config.update_config({"shadow_enabled": False})
        final = await certification.report(since=camp["start_at"])
        ended = now_iso()
        gate_context = await self._gate_context()
        camp_final = {**camp, "status": status, "ended_at": ended, "breach_reason": breach,
                      "final_verdict": final["verdict"], "final_report": final,
                      "gate_context": gate_context}
        # Auto-snapshot the comprehensive Certification Review package (read-only evidence layer).
        try:
            review = await certification_review.build(camp_final, report=final)
        except Exception as e:
            logger.warning("certification review build failed: %s", e)
            review = None
        await db.shadow_campaigns.update_one({"id": camp["id"]}, {"$set": {
            "status": status, "ended_at": ended, "updated_at": ended,
            "breach_reason": breach, "final_verdict": final["verdict"],
            "completed_count": final["throughput"]["completed"],
            "total_count": final["throughput"]["total_shadow_cycles"],
            "gate_context": gate_context,
            "final_report": final, "certification_review": review}})
        certified = final["verdict"] == "READY_FOR_MICROCAPITAL_REVIEW"
        review_rec = (review or {}).get("recommendation")
        msg = (f"🏁 Shadow campaign {camp['id'][:8]} {status} — "
               f"{final['throughput']['completed']} completed, verdict {final['verdict']}"
               + (f" (review: {review_rec})" if review_rec else "")
               + (f", BREACH: {breach}" if breach else "")
               + (" ✅ CERTIFIED" if certified else ""))
        await telegram_alerts.notify("cycle_manual_review", msg)
        logger.info(msg)

    # ---------- control ----------
    async def start(self, target_completed: int = DEFAULT_TARGET, thresholds: dict = None,
                    cycle_size_usd: float = None) -> dict:
        if await self._active():
            raise ValueError("a campaign is already running")
        target = int(target_completed) if target_completed else DEFAULT_TARGET
        if target < 1:
            raise ValueError("target_completed must be >= 1")
        # campaign-scoped shadow cycle size (e.g. validate the $50 BlockDAG executable minimum)
        size = None
        if cycle_size_usd is not None:
            size = float(cycle_size_usd)
            if size <= 0:
                raise ValueError("cycle_size_usd must be > 0")
            await config.update_config({"limits": {"shadow_cycle_size_usd": size}})
        await config.update_config({"shadow_enabled": True})
        gate_context_start = await self._gate_context()
        cfg = await config.get_config()
        camp = {
            "id": new_id(), "status": "running",
            "target_completed": target, "thresholds": _merge_thresholds(thresholds),
            "cycle_size_usd": size if size is not None else cfg["limits"].get("shadow_cycle_size_usd"),
            "start_at": now_iso(), "ended_at": None, "last_checked_at": None,
            "completed_count": 0, "total_count": 0,
            "stuck_rate_pct": 0, "variance_pct": None,
            "recovery_success_rate_pct": None, "recovery_failures": 0,
            "breach_reason": None, "final_verdict": None, "final_report": None,
            "gate_context_start": gate_context_start,
            "created_at": now_iso(), "updated_at": now_iso(),
        }
        await db.shadow_campaigns.insert_one(dict(camp))
        camp.pop("_id", None)
        await telegram_alerts.notify(
            "cycle_manual_review",
            f"▶️ Shadow certification campaign started — target {target} completed cycles (SIMULATED).")
        return camp

    async def stop(self) -> dict:
        camp = await self._active()
        if not camp:
            raise ValueError("no running campaign")
        await self._finalize(camp, "stopped_manual", None)
        return await db.shadow_campaigns.find_one({"id": camp["id"]}, {"_id": 0})

    async def status(self) -> dict:
        camp = await db.shadow_campaigns.find_one({}, {"_id": 0, "final_report": 0, "certification_review": 0},
                                                  sort=[("created_at", -1)])
        out = {"monitor_running": self._running, "check_interval_s": CHECK_S,
               "default_target": DEFAULT_TARGET, "default_thresholds": DEFAULT_THRESHOLDS,
               "campaign": camp}
        if camp and camp["status"] in ACTIVE:
            out["live_report"] = await certification.report(since=camp["start_at"])
            out["progress_pct"] = round(min(100, (camp.get("completed_count", 0)
                                                  / camp["target_completed"]) * 100), 1)
        elif camp and camp.get("status"):
            full = await db.shadow_campaigns.find_one({"id": camp["id"]}, {"_id": 0, "final_report": 1})
            out["final_report"] = (full or {}).get("final_report")
        return out

    async def history(self, limit: int = 20):
        return await db.shadow_campaigns.find({}, {"_id": 0, "final_report": 0, "certification_review": 0},
                                              sort=[("created_at", -1)]).to_list(limit)


shadow_campaign = ShadowCampaign()
