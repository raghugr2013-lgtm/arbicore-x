"""IntelligenceRegistry — per-engine metadata + activation status."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class EngineStatus:
    """One row per activated (or attempted) intelligence engine."""

    id: str                     # 'confidence', 'roi', 'route_ranking', ...
    description: str
    active: bool
    dependencies: List[str] = field(default_factory=list)
    activated_at: Optional[str] = None
    error: Optional[str] = None
    # A caller-provided snapshot function that returns the engine's current
    # public state. Not serialised — used by /snapshot endpoint only.
    _snapshot_fn: Optional[Callable[[], Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("_snapshot_fn", None)
        return d

    def snapshot(self) -> Dict[str, Any]:
        if self._snapshot_fn is None:
            return {"id": self.id, "snapshot_available": False}
        try:
            return {"id": self.id, "snapshot_available": True,
                    "snapshot": self._snapshot_fn()}
        except Exception as exc:  # noqa: BLE001
            return {"id": self.id, "snapshot_available": False,
                    "error": f"{type(exc).__name__}: {exc}"}


class IntelligenceRegistry:
    """Holds every engine's activation status.

    Immutable-ish: callers add engines during activation, then only read.
    """

    def __init__(self) -> None:
        self._engines: Dict[str, EngineStatus] = {}
        self._activated_at: str = _now_iso()

    def register(
        self,
        *,
        engine_id: str,
        description: str,
        instance: Any = None,
        dependencies: Optional[List[str]] = None,
        error: Optional[str] = None,
        snapshot_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> EngineStatus:
        status = EngineStatus(
            id=engine_id,
            description=description,
            active=instance is not None and error is None,
            dependencies=list(dependencies or []),
            activated_at=_now_iso() if error is None else None,
            error=error,
            _snapshot_fn=snapshot_fn,
        )
        self._engines[engine_id] = status
        return status

    def get(self, engine_id: str) -> Optional[EngineStatus]:
        return self._engines.get(engine_id)

    def all(self) -> List[EngineStatus]:
        return list(self._engines.values())

    def summary(self) -> Dict[str, Any]:
        active = [e.id for e in self._engines.values() if e.active]
        errored = [
            {"id": e.id, "error": e.error}
            for e in self._engines.values() if e.error
        ]
        return {
            "activated_at": self._activated_at,
            "engine_count": len(self._engines),
            "active_count": len(active),
            "active": active,
            "errored": errored,
            "engines": [e.to_dict() for e in self._engines.values()],
        }
