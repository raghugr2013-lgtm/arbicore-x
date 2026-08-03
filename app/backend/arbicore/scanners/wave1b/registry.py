"""ScannerRegistry — enumerates every activated scanner + its live status."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class ScannerStatus:
    id: str                            # 'dex_arbitrage' or 'flash_loan_arbitrage'
    description: str
    mode: str                          # always "shadow" in Wave 1B-β
    dependencies: List[str] = field(default_factory=list)
    activated_at: Optional[str] = None
    error: Optional[str] = None
    _adapter: Any = None               # ShadowScannerAdapter instance

    def to_dict(self, include_live: bool = True) -> Dict[str, Any]:
        # NOTE: cannot use ``asdict(self)`` here because ``_adapter``
        # holds ``asyncio.Queue`` / ``asyncio.Event`` primitives which
        # cannot be deep-copied. Build the dict explicitly.
        d: Dict[str, Any] = {
            "id": self.id,
            "description": self.description,
            "mode": self.mode,
            "dependencies": list(self.dependencies),
            "activated_at": self.activated_at,
            "error": self.error,
        }
        if include_live and self._adapter is not None:
            try:
                d["running"] = self._adapter.is_running()
                d["enabled"] = self._adapter.is_enabled()
                d["stats"] = self._adapter.stats
            except Exception as exc:  # noqa: BLE001
                d["running"] = False
                d["stats_error"] = f"{type(exc).__name__}: {exc}"
        return d


class ScannerRegistry:
    def __init__(self) -> None:
        self._scanners: Dict[str, ScannerStatus] = {}
        self._activated_at = _now_iso()

    def register(
        self,
        *,
        scanner_id: str,
        description: str,
        adapter: Any = None,
        dependencies: Optional[List[str]] = None,
        error: Optional[str] = None,
    ) -> ScannerStatus:
        status = ScannerStatus(
            id=scanner_id,
            description=description,
            mode="shadow",
            dependencies=list(dependencies or []),
            activated_at=_now_iso() if error is None else None,
            error=error,
            _adapter=adapter,
        )
        self._scanners[scanner_id] = status
        return status

    def get(self, scanner_id: str) -> Optional[ScannerStatus]:
        return self._scanners.get(scanner_id)

    def all(self) -> List[ScannerStatus]:
        return list(self._scanners.values())

    def summary(self) -> Dict[str, Any]:
        return {
            "activated_at": self._activated_at,
            "scanner_count": len(self._scanners),
            "running": [s.id for s in self._scanners.values()
                         if s._adapter and s._adapter.is_running()],
            "errored": [
                {"id": s.id, "error": s.error}
                for s in self._scanners.values() if s.error
            ],
            "scanners": [s.to_dict() for s in self._scanners.values()],
        }
