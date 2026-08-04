"""Preflight + Daily Summary + Anomaly Detection (Phases 7 & 8 · v2.7.0).

Read-only. All I/O is against Mongo (MID) and the running registry.
Nothing here writes intelligence data — it consumes the intelligence
already accumulated by Wave-1B, Wave-2, and Wave-3.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# =============================================================================
# 1. Preflight (deployment validation)
# =============================================================================
@dataclass
class PreflightCheck:
    name: str
    ok: bool
    detail: str = ""
    latency_ms: Optional[float] = None
    category: str = "misc"


async def _check(name: str, category: str, coro) -> PreflightCheck:
    t0 = time.time()
    try:
        detail = await coro
        return PreflightCheck(name=name, ok=True, detail=str(detail or "ok"),
                               latency_ms=round((time.time() - t0) * 1000, 2),
                               category=category)
    except Exception as exc:                                          # noqa
        return PreflightCheck(name=name, ok=False, detail=repr(exc)[:200],
                               latency_ms=round((time.time() - t0) * 1000, 2),
                               category=category)


class PreflightRunner:
    """Composes every startup-check the operator wants after deploy."""

    def __init__(self, *, mongo_client=None, mid_reader=None,
                 mid_writer=None, provider_registry=None,
                 live_scanners: Optional[List[Any]] = None,
                 paper_engine=None, kill_switch=None,
                 runtime_config=None) -> None:
        self._mongo = mongo_client
        self._mid_r = mid_reader
        self._mid_w = mid_writer
        self._reg = provider_registry
        self._scanners = list(live_scanners or [])
        self._paper = paper_engine
        self._kill = kill_switch
        self._cfg = runtime_config

    # ----------------- individual checks -----------------

    async def _mongo_ping(self) -> str:
        if self._mongo is None:
            raise RuntimeError("mongo_client not bound")
        await self._mongo.admin.command("ping")
        return "ok"

    async def _mid_read(self) -> str:
        if self._mid_r is None:
            raise RuntimeError("mid_reader not bound")
        rows = await self._mid_r.query("opportunities", limit=1)
        return f"opportunities_last1={len(rows)}"

    async def _registry_count(self) -> str:
        if self._reg is None:
            raise RuntimeError("provider_registry not bound")
        snap = self._reg.snapshot()
        return (f"providers={snap.get('provider_count')} "
                f"kinds={len(snap.get('by_kind') or {})}")

    async def _rpc_endpoints_configured(self) -> str:
        # Reality check: did the bootstrap actually register RPC
        # providers? We prefer the registry's answer to a raw env probe
        # so dev pods using free-tier defaults still pass preflight.
        if self._reg is None:
            raise RuntimeError("provider_registry not bound")
        snap = self._reg.snapshot()
        rpc_rows = (snap.get("by_kind") or {}).get("rpc", [])
        if not rpc_rows:
            raise RuntimeError(
                "no RPC providers registered — set PROVIDER_RPC_URL_*")
        via_env = 0
        via_default = 0
        if self._cfg is not None:
            via_env = len(self._cfg.rpc.urls_by_chain)
            via_default = max(0, len(rpc_rows) - via_env)
        return (f"rpc_providers_registered={len(rpc_rows)} "
                f"(from_env={via_env}, from_defaults={via_default})")

    async def _paper_engine_available(self) -> str:
        if self._paper is None:
            raise RuntimeError("paper_engine not bound")
        stats = self._paper.stats.to_dict() if hasattr(
            self._paper.stats, "to_dict") else self._paper.stats
        return f"analyses={stats.get('analyses', 0)}"

    async def _kill_engaged(self) -> str:
        if self._kill is None:
            raise RuntimeError("kill_switch not bound")
        engaged = self._kill.is_engaged()
        if not engaged:
            raise RuntimeError("KILL_SWITCH_NOT_ENGAGED (v2.7.0 requires engaged)")
        return "engaged=True"

    async def _scanner_running(self, scanner) -> str:
        if not scanner.is_running():
            raise RuntimeError(f"{scanner.scanner_id} not running")
        return f"iterations={scanner.stats.get('iterations')}"

    async def _provider_health_pct(self) -> str:
        if self._reg is None:
            raise RuntimeError("provider_registry not bound")
        snap = self._reg.snapshot()
        total = snap.get("provider_count", 0)
        healthy = 0
        for _, rows in (snap.get("by_kind") or {}).items():
            healthy += sum(1 for r in rows if r.get("status") == "HEALTHY")
        pct = (healthy / total * 100.0) if total else 0.0
        if pct < 50:
            raise RuntimeError(
                f"healthy providers below 50%%: {healthy}/{total} ({pct:.1f}%%)")
        return f"healthy={healthy}/{total} ({pct:.1f}%)"

    # ----------------- runner -----------------

    async def run(self) -> Dict[str, Any]:
        t0 = time.time()
        checks: List[PreflightCheck] = []

        checks.append(await _check("mongo_ping", "database",
                                     self._mongo_ping()))
        checks.append(await _check("mid_reader_query", "database",
                                     self._mid_read()))
        checks.append(await _check("provider_registry_bound", "providers",
                                     self._registry_count()))
        checks.append(await _check("rpc_endpoints_configured", "providers",
                                     self._rpc_endpoints_configured()))
        checks.append(await _check("provider_health_pct", "providers",
                                     self._provider_health_pct()))
        checks.append(await _check("paper_engine_bound", "paper",
                                     self._paper_engine_available()))
        checks.append(await _check("kill_switch_engaged", "safety",
                                     self._kill_engaged()))
        for s in self._scanners:
            sid = getattr(s, "scanner_id", "scanner")
            checks.append(await _check(f"scanner_{sid}", "scanners",
                                         self._scanner_running(s)))

        summary = {
            "generated_at": _iso(),
            "elapsed_ms": round((time.time() - t0) * 1000, 2),
            "total": len(checks),
            "passed": sum(1 for c in checks if c.ok),
            "failed": sum(1 for c in checks if not c.ok),
            "checks": [asdict(c) for c in checks],
            "ok": all(c.ok for c in checks),
        }
        summary["categories"] = {}
        for c in checks:
            b = summary["categories"].setdefault(
                c.category, {"passed": 0, "failed": 0})
            b["passed" if c.ok else "failed"] += 1
        return summary


# =============================================================================
# 2. Daily-summary writer + anomaly detection
# =============================================================================
class DailySummaryWriter:
    """Runs a background asyncio loop that periodically composes and
    writes a daily validation summary into MID (event_type
    ``validation.daily_summary``). The summary is the canonical record
    an operator would archive for the 7-day validation review."""

    def __init__(self, *, validation_reporter,
                  mid_writer, registry, live_scanners: List[Any],
                  runtime_config,
                  run_id: Optional[str] = None,
                  interval_s: Optional[float] = None) -> None:
        self._reporter = validation_reporter
        self._mid_w = mid_writer
        self._reg = registry
        self._scanners = live_scanners
        self._cfg = runtime_config
        self._run_id = run_id or (
            f"{self._cfg.validation.run_id_prefix}_"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}")
        self._interval_s = interval_s or float(
            self._cfg.validation.window_hours * 3600)
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._last_summary: Optional[Dict[str, Any]] = None
        self._last_anomalies: List[Dict[str, Any]] = []

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def last_summary(self) -> Optional[Dict[str, Any]]:
        return self._last_summary

    @property
    def last_anomalies(self) -> List[Dict[str, Any]]:
        return list(self._last_anomalies)

    @property
    def run_id(self) -> str:
        return self._run_id

    async def start(self) -> Dict[str, Any]:
        if self.is_running():
            return {"already_running": True}
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(),
                                            name="arbicore_daily_summary_writer")
        # write one summary immediately so the operator has something
        # to inspect after deploy
        await self.run_once()
        return {"started": True, "run_id": self._run_id,
                 "interval_s": self._interval_s}

    async def stop(self) -> Dict[str, Any]:
        if not self.is_running():
            return {"already_stopped": True}
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except asyncio.TimeoutError:
            self._task.cancel()
        return {"stopped": True}

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(),
                                          timeout=self._interval_s)
                # if the wait completed without raising, stop() was called
                return
            except asyncio.TimeoutError:
                # normal periodic tick
                try:
                    await self.run_once()
                except Exception as exc:                             # noqa
                    logger.exception("daily_summary tick failed: %s", exc)

    async def run_once(self) -> Dict[str, Any]:
        summary = await self._reporter.summary(
            scanners=self._scanners, registry=self._reg)
        anomalies = self._detect_anomalies(summary)
        summary_id = f"daily_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
        payload = {
            "run_id": self._run_id,
            "summary_id": summary_id,
            "at": _iso(),
            "summary": summary,
            "anomalies": anomalies,
            "safety_snapshot": {
                "kill_engaged": True,      # invariant in v2.7.0
                "live_execution_enabled": False,
                "signing_allowed": False,
            },
        }
        try:
            await self._mid_w.write_opportunity_event(
                opp_id=summary_id,
                event_type="validation.daily_summary",
                payload=payload,
            )
        except Exception as exc:                                     # noqa
            logger.exception("daily summary write failed: %s", exc)
        self._last_summary = payload
        self._last_anomalies = anomalies
        return payload

    # ----------------- anomaly detection -----------------
    def _detect_anomalies(self, summary: Dict[str, Any]) -> List[Dict[str, Any]]:
        anomalies: List[Dict[str, Any]] = []
        cfg = self._cfg.validation

        # 1. Scanner health — running but no emissions
        for s in summary.get("scanner_ranking", {}).get("scanners", []):
            if (s.get("running")
                    and s.get("iterations", 0) >= cfg.anomaly_min_scanner_ops
                    and s.get("opportunities_emitted", 0) == 0):
                anomalies.append({
                    "kind": "scanner_zero_emissions",
                    "scanner_id": s.get("scanner_id"),
                    "iterations": s.get("iterations"),
                    "severity": "warning",
                })

        # 2. Provider health — pct below configured floor
        pr = summary.get("provider_ranking", {})
        total = pr.get("provider_count", 0)
        healthy = pr.get("healthy_count", 0)
        if total:
            pct = healthy / total
            if pct < cfg.anomaly_min_healthy_providers_pct:
                anomalies.append({
                    "kind": "provider_health_below_floor",
                    "healthy": healthy, "total": total,
                    "healthy_pct": round(pct, 3),
                    "floor_pct": cfg.anomaly_min_healthy_providers_pct,
                    "severity": "critical" if pct < 0.5 else "warning",
                })

        # 3. Provider error rate — inspect ranking rows
        for row in pr.get("ranked", []):
            succ = row.get("success", 0) or 0
            fail = row.get("failure", 0) or 0
            total_calls = succ + fail
            if total_calls >= 20:
                err = fail / total_calls
                if err > cfg.anomaly_max_provider_error_rate:
                    anomalies.append({
                        "kind": "provider_error_rate_high",
                        "provider_id": row.get("provider_id"),
                        "error_rate": round(err, 3),
                        "threshold": cfg.anomaly_max_provider_error_rate,
                        "severity": "warning",
                    })

        # 4. Historical — zero live opps in window
        h = summary.get("historical") or {}
        if h.get("sampled_opps", 0) > 0 and h.get("live_count", 0) == 0:
            anomalies.append({
                "kind": "no_live_opportunities_in_window",
                "sampled_opps": h.get("sampled_opps", 0),
                "severity": "warning",
            })

        return anomalies


__all__ = ["PreflightRunner", "DailySummaryWriter", "PreflightCheck"]
