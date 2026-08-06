"""Shadow Certification runner (v2.11.9).

Long-running coroutine that ticks the :class:`ShadowCertificationEngine`
at a fixed cadence.  Kept independent of the Paper Validation runner so
they can be enabled / disabled separately during Base Sepolia prep.

Environment gates:

* ``ARBICORE_SHADOW_CERT_ENABLED`` — must be truthy for the runner to
  auto-start at boot.  Endpoints still work when this is off (an
  operator can drive the engine manually via ``/certification/shadow/*``).
* ``ARBICORE_SHADOW_CERT_CYCLE_S`` — cycle cadence in seconds
  (default 60).
* ``ARBICORE_SHADOW_CERT_AUTOSTART_RUN`` — if truthy AND no run is
  currently RUNNING, the runner auto-starts a new run on boot.  Default
  off so runs are always operator-initiated in production.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from .engine import ShadowCertificationEngine
from .models import ShadowCertificationRun

logger = logging.getLogger(__name__)


def _truthy(name: str) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def is_shadow_cert_enabled_via_env() -> bool:
    return _truthy("ARBICORE_SHADOW_CERT_ENABLED")


class ShadowCertificationRunner:
    """Owns the tick loop for a single :class:`ShadowCertificationEngine`."""

    DEFAULT_CYCLE_S = 60.0

    def __init__(
        self,
        *,
        engine: ShadowCertificationEngine,
        cycle_s: Optional[float] = None,
    ) -> None:
        self._engine = engine
        env_cycle = os.environ.get("ARBICORE_SHADOW_CERT_CYCLE_S")
        if cycle_s is not None:
            self._cycle_s = float(cycle_s)
        elif env_cycle:
            try:
                self._cycle_s = float(env_cycle)
            except ValueError:
                self._cycle_s = self.DEFAULT_CYCLE_S
        else:
            self._cycle_s = self.DEFAULT_CYCLE_S
        self._task: Optional[asyncio.Task] = None
        self._stop_flag: bool = False

    @property
    def cycle_s(self) -> float:
        return self._cycle_s

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.is_running():
            return
        self._stop_flag = False
        self._task = asyncio.create_task(
            self._run_forever(), name="shadow-certification-runner"
        )
        logger.info(
            "ShadowCertificationRunner started (cycle_s=%.1f)", self._cycle_s
        )

    async def stop(self) -> None:
        self._stop_flag = True
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                logger.warning(
                    "ShadowCertificationRunner did not stop within 10s; cancelled"
                )

    async def _run_forever(self) -> None:
        while not self._stop_flag:
            try:
                run = await self._engine.tick()
                if run is not None and run.is_terminal:
                    logger.info(
                        "Shadow Certification run %s terminal → %s",
                        run.run_id, run.status,
                    )
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001
                logger.exception("ShadowCertificationRunner tick failed")
            try:
                await asyncio.sleep(self._cycle_s)
            except asyncio.CancelledError:
                break
