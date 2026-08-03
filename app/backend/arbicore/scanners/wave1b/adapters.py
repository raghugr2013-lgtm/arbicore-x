"""ShadowScannerAdapter — operator-controlled shadow lifecycle.

Implements the same public contract as the real
``DEXArbitrageScanner`` / ``FlashLoanArbitrageScanner`` classes without
performing any live I/O. When ``start()`` is called by an operator the
adapter runs a periodic background tick that:

  1. Reads the MID for recent intelligence rows (already-persisted
     confidence, route, regime evidence produced by Wave 1B-α).
  2. Produces a *shadow emission* — a synthetic ``opportunity_event``
     describing the tick — and hands it to
     :class:`ScannerEvidenceBridge` for persistence.
  3. Bumps its own operator-visible ``stats``: iterations, emissions,
     last_run_at, errors, backlog size, etc.

The adapter never touches the network. All state is in-process. The
duration between ticks is configurable and defaults to 10s so backlog
growth is trivial to observe on the ``/status`` endpoint.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ...data.mid.readers import MidReader
from .bridge import ScannerEvidenceBridge

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class ShadowScannerConfig:
    tick_interval_seconds: float = 10.0
    max_backlog: int = 1_000       # cap the internal queue for safety


class ShadowScannerAdapter:
    """One instance per scanner. Only the operator can start/stop it."""

    def __init__(
        self,
        *,
        scanner_id: str,
        description: str,
        opportunity_type: str,
        bridge: ScannerEvidenceBridge,
        mid_reader: MidReader,
        config: Optional[ShadowScannerConfig] = None,
    ) -> None:
        self._id = scanner_id
        self._description = description
        self._opp_type = opportunity_type
        self._bridge = bridge
        self._mid = mid_reader
        self._cfg = config or ShadowScannerConfig()

        self._enabled = False        # operator flag
        self._task: Optional[asyncio.Task] = None
        self._stop_evt = asyncio.Event()
        self._backlog: asyncio.Queue = asyncio.Queue(
            maxsize=self._cfg.max_backlog)

        self._stats: Dict[str, Any] = {
            "iterations":       0,
            "rows_emitted":     0,
            "backlog_size":     0,
            "backlog_dropped":  0,
            "last_run_at":      None,
            "last_error":       None,
            "started_at":       None,
            "stopped_at":       None,
            "uptime_seconds":   0,
        }

    # ------------------------------------------------------------------
    # public contract (mirrors DEXArbitrageScanner / FlashLoanArbitrageScanner)
    # ------------------------------------------------------------------

    @property
    def scanner_id(self) -> str:
        return self._id

    @property
    def stats(self) -> Dict[str, Any]:
        # refresh live counters
        self._stats["backlog_size"] = self._backlog.qsize()
        if self._stats.get("started_at") and self.is_running():
            started = datetime.fromisoformat(
                self._stats["started_at"].replace("Z", "+00:00")
            )
            self._stats["uptime_seconds"] = int(
                (datetime.now(timezone.utc) - started).total_seconds()
            )
        return dict(self._stats)

    def is_enabled(self) -> bool:
        return self._enabled

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> Dict[str, Any]:
        if self.is_running():
            return {"already_running": True, "started_at":
                    self._stats["started_at"]}
        self._enabled = True
        self._stop_evt.clear()
        self._task = asyncio.create_task(self._run())
        self._stats["started_at"] = _now_iso()
        self._stats["stopped_at"] = None
        logger.info(
            "wave1b-β: scanner started id=%s mode=shadow", self._id)
        return {"started": True, "started_at": self._stats["started_at"]}

    async def stop(self) -> Dict[str, Any]:
        if not self.is_running():
            self._enabled = False
            return {"already_stopped": True}
        self._enabled = False
        self._stop_evt.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except asyncio.TimeoutError:
            self._task.cancel()
        self._stats["stopped_at"] = _now_iso()
        logger.info("wave1b-β: scanner stopped id=%s", self._id)
        return {"stopped": True, "stopped_at": self._stats["stopped_at"]}

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        while not self._stop_evt.is_set():
            t0 = time.time()
            try:
                await self._tick()
            except Exception as exc:  # noqa: BLE001
                self._stats["last_error"] = (
                    f"tick[{self._id}]: {exc!r}")
                logger.exception("wave1b-β tick failed: %s", exc)
            self._stats["iterations"] += 1
            self._stats["last_run_at"] = _now_iso()
            # wait either interval or stop
            elapsed = time.time() - t0
            remaining = max(
                0.0, self._cfg.tick_interval_seconds - elapsed)
            try:
                await asyncio.wait_for(
                    self._stop_evt.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                pass

    async def _tick(self) -> None:
        """One shadow discover→verify→emit cycle.

        In Wave 1B-β we do NOT perform any live discovery. Instead we
        consume the latest MID intelligence rows and produce ONE
        deterministic shadow emission per tick that references those
        upstream rows. That emission is the concrete evidence that the
        scanner activation path (composition → bridge → MID) is wired
        end-to-end.
        """
        # 1. read latest MID confidence rows (Wave 1B-α evidence)
        recent = await self._mid.query("confidence", limit=1)
        upstream = recent[0] if recent else None

        # 2. build a shadow opportunity payload
        opp_id = f"shadow:{self._id}:{uuid.uuid4().hex[:12]}"
        payload = {
            "opportunity_type": self._opp_type,
            "chain": "unknown",
            "protocol": None,
            "market_regime": "UNKNOWN",
            "shadow": True,
            "reason": (
                "wave1b-β shadow tick; no live I/O; upstream_confidence="
                f"{upstream.get('score') if upstream else None}"
            ),
            "upstream_opp_id": (
                upstream.get("opp_id") if upstream else None),
            "tick_at": _now_iso(),
        }
        route = {
            "route_id": f"shadow-route:{self._id}:{uuid.uuid4().hex[:8]}",
            "fingerprint_parts": {
                "kind": "shadow",
                "scanner": self._id,
                "opportunity_type": self._opp_type,
            },
        }

        # 3. enqueue and emit (queue is bounded — drops if operator lets
        #    the scanner run too long without downstream consumers)
        try:
            self._backlog.put_nowait((opp_id, payload, route))
        except asyncio.QueueFull:
            self._stats["backlog_dropped"] += 1
            return

        # drain one item per tick (bounded to keep the scanner honest)
        try:
            item = self._backlog.get_nowait()
        except asyncio.QueueEmpty:
            return
        oid, pl, rt = item
        result = await self._bridge.publish_emission(
            scanner_id=self._id, opp_id=oid, payload=pl, route=rt,
        )
        if result["opportunity_event_id"]:
            self._stats["rows_emitted"] += 1
