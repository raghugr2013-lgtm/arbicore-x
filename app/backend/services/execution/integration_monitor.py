"""Phase E4 — Execution-venue health monitor (READ-ONLY).

A lightweight periodic monitor that probes PUBLIC connectivity (reachability +
latency) for the primary/backup execution venues, keeping a rolling success-rate
and latency window and persisting snapshots. Complements the balance poller's
signed read telemetry. No authenticated calls here; never moves funds.
"""
import asyncio
import logging
from collections import deque

from core.models import new_id, now_iso
from services import db
from services.execution import venue_registry
from services.execution.integration_prep import probe_connectivity

logger = logging.getLogger("integration_monitor")

PROBE_EVERY_S = 120
WINDOW = 30


class IntegrationMonitor:
    def __init__(self):
        self._task = None
        self._running = False
        self.samples = {}      # exchange -> deque[{ts, ok, latency_ms}]
        self.last_probe_at = None

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Integration monitor started (public connectivity probes every %ss).", PROBE_EVERY_S)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self):
        await asyncio.sleep(10)
        while self._running:
            try:
                await self._probe()
            except Exception as e:
                logger.warning("integration probe failed: %s", e)
            await asyncio.sleep(PROBE_EVERY_S)

    async def _probe(self):
        role_map = await venue_registry.get_role_map()
        targets = [ex for ex, role in role_map.items() if role in ("primary", "backup")]
        docs = []
        for ex in targets:
            r = await probe_connectivity(ex)
            self.samples.setdefault(ex, deque(maxlen=WINDOW)).append(
                {"ts": now_iso(), "ok": r["ok"], "latency_ms": r["latency_ms"]})
            docs.append({"id": new_id(), "ts": now_iso(), "created_at": now_iso(),
                         "exchange": ex, "ok": r["ok"], "latency_ms": r["latency_ms"],
                         "detail": r["detail"]})
        if docs:
            await db.integration_health_snaps.insert_many(docs)
        self.last_probe_at = now_iso()

    def _window_stats(self, ex):
        dq = self.samples.get(ex)
        if not dq:
            return {"samples": 0, "success_rate_pct": None, "avg_latency_ms": None, "last_ok": None}
        n = len(dq)
        oks = sum(1 for s in dq if s["ok"])
        lat = [s["latency_ms"] for s in dq if s["latency_ms"] is not None]
        return {"samples": n,
                "success_rate_pct": round(oks / n * 100, 1),
                "avg_latency_ms": round(sum(lat) / len(lat), 1) if lat else None,
                "last_ok": dq[-1]["ok"], "last_latency_ms": dq[-1]["latency_ms"]}

    async def status(self):
        role_map = await venue_registry.get_role_map()
        targets = [ex for ex, role in role_map.items() if role in ("primary", "backup")]
        return {
            "running": self._running, "probe_interval_s": PROBE_EVERY_S,
            "last_probe_at": self.last_probe_at,
            "venues": {ex: {"role": role_map.get(ex), **self._window_stats(ex)} for ex in targets},
            "note": "Public connectivity health only. Signed-read health comes from the balance poller.",
        }


integration_monitor = IntegrationMonitor()
