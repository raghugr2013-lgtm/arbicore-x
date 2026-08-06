"""StageRecorder — async context manager for pipeline stage timing.

Wraps every pipeline stage so start/end/duration are captured
uniformly.  Emits a :class:`StageMetric` on ``__aexit__`` and appends
it to the provided list — callers get a canonical trace with zero
boilerplate.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .evidence import StageMetric


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StageRecorder:
    """Async context manager that records one pipeline stage.

    Usage::

        async with StageRecorder("quote", metrics) as rec:
            payload = await run_quote(...)
            rec.set_result(ok=True, payload=payload)

    On ``__aexit__``:
        * If an exception escaped, ``ok`` is forced to False and the
          exception message becomes ``failure_reason``.
        * A :class:`StageMetric` is appended to ``metrics_list``.
    """

    __slots__ = (
        "stage", "_metrics_list", "_started_at_iso", "_start_perf",
        "_ok", "_detail", "_failure_reason", "_payload",
    )

    def __init__(self, stage: str, metrics_list: List[Dict[str, Any]]):
        self.stage = stage
        self._metrics_list = metrics_list
        self._started_at_iso = ""
        self._start_perf = 0.0
        self._ok: bool = False
        self._detail: str = ""
        self._failure_reason: Optional[str] = None
        self._payload: Dict[str, Any] = {}

    async def __aenter__(self) -> "StageRecorder":
        self._started_at_iso = _iso_now()
        self._start_perf = time.perf_counter()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        ended_at = _iso_now()
        duration_ms = round((time.perf_counter() - self._start_perf) * 1000.0, 3)
        if exc is not None:
            self._ok = False
            self._failure_reason = f"{exc_type.__name__}: {exc}" if exc_type else str(exc)
            self._detail = self._detail or self._failure_reason or ""
        metric = StageMetric(
            stage=self.stage,
            started_at=self._started_at_iso,
            ended_at=ended_at,
            duration_ms=duration_ms,
            ok=self._ok,
            detail=self._detail,
            failure_reason=self._failure_reason,
            payload=dict(self._payload),
        )
        self._metrics_list.append(metric.to_dict())
        # Do not swallow exceptions — the pipeline wraps its own control
        # flow around a raised stage failure only when it deliberately
        # chooses to; unexpected exceptions must propagate.
        return False

    def set_result(self,
                    *,
                    ok: bool,
                    detail: str = "",
                    failure_reason: Optional[str] = None,
                    payload: Optional[Dict[str, Any]] = None) -> None:
        self._ok = bool(ok)
        self._detail = detail or ""
        self._failure_reason = failure_reason if not ok else None
        if payload is not None:
            self._payload = dict(payload)
