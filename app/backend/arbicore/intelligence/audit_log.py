"""ArbiCore X — Audit Logging service.

Generalised from ArbitrageX ``TradeLog`` + ``add_log`` (server.py L413, L2376).
Renamed to ``EventLog`` (no trade/execution semantics). Persistence is pluggable
via ``AuditStore`` so it works without a database in tests.

Dependency map: stdlib only (dataclasses, datetime, uuid) + AuditStore.

Example:
    >>> logger = AuditLogger()
    >>> e = logger.log("info", "scan complete", source="dex_scanner")
    >>> e.type
    'info'
    >>> len(logger.query(limit=10))
    1
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EventLog:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = "info"            # info | warning | error | event
    message: str = ""
    source: Optional[str] = None  # which engine/module emitted it
    details: Optional[Dict[str, Any]] = None
    timestamp: str = field(default_factory=_utc_now)

    def as_dict(self) -> dict:
        return asdict(self)


class AuditStore(Protocol):
    def append(self, event: EventLog) -> None: ...
    def query(self, *, limit: int, source: Optional[str], type: Optional[str]) -> List[EventLog]: ...
    def count(self) -> int: ...
    def trim(self, max_records: int) -> int: ...


class InMemoryAuditStore:
    def __init__(self) -> None:
        self._events: List[EventLog] = []

    def append(self, event: EventLog) -> None:
        self._events.append(event)

    def query(self, *, limit: int, source: Optional[str], type: Optional[str]) -> List[EventLog]:
        items = self._events
        if source is not None:
            items = [e for e in items if e.source == source]
        if type is not None:
            items = [e for e in items if e.type == type]
        # newest first
        return list(reversed(items))[:limit]

    def count(self) -> int:
        return len(self._events)

    def trim(self, max_records: int) -> int:
        overflow = len(self._events) - max_records
        if overflow > 0:
            del self._events[:overflow]
            return overflow
        return 0


class AuditLogger:
    MAX_RECORDS = 2000

    def __init__(self, store: Optional[AuditStore] = None) -> None:
        self.store: AuditStore = store or InMemoryAuditStore()

    def log(
        self,
        type: str,
        message: str,
        *,
        source: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> EventLog:
        event = EventLog(type=type, message=message, source=source, details=details)
        self.store.append(event)
        if self.store.count() > self.MAX_RECORDS:
            self.store.trim(self.MAX_RECORDS)
        return event

    def query(
        self,
        *,
        limit: int = 100,
        source: Optional[str] = None,
        type: Optional[str] = None,
    ) -> List[EventLog]:
        return self.store.query(limit=limit, source=source, type=type)
