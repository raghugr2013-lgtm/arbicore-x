"""KillSwitch — single global safety gate."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .config import PolicyConfig


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class KillSwitch:
    def __init__(self, cfg: PolicyConfig) -> None:
        self._engaged = cfg.kill_engaged_by_default
        self._reason: Optional[str] = (
            "boot_default" if self._engaged else None)
        self._engaged_at: Optional[str] = _now_iso() if self._engaged else None
        self._history: list = []

    def is_engaged(self) -> bool:
        return self._engaged

    def reason(self) -> Optional[str]:
        return self._reason

    def engage(self, *, by: str, reason: str) -> dict:
        self._engaged = True
        self._reason = reason
        self._engaged_at = _now_iso()
        entry = {"action": "ENGAGE", "ts": self._engaged_at,
                 "by": by, "reason": reason}
        self._history.append(entry)
        return entry

    def disengage(self, *, by: str, reason: str) -> dict:
        self._engaged = False
        self._reason = None
        entry = {"action": "DISENGAGE", "ts": _now_iso(),
                 "by": by, "reason": reason}
        self._history.append(entry)
        return entry

    def to_dict(self) -> dict:
        return {
            "engaged": self._engaged,
            "reason": self._reason,
            "engaged_at": self._engaged_at,
            "history": self._history[-20:],
        }
