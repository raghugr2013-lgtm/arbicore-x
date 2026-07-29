"""ArbiCore X — Async in-process Event Bus (Phase C Wave 1).

Minimal pub/sub used to decouple opportunity emission from learning consumers.
Topics are free-form strings. Subscribers are async callables ``(topic, payload) -> None``.

The bus is **synchronous in delivery order** but ``await``-s each subscriber
sequentially. There is no persistence — restart drops in-flight events.

Phase B / Phase C governance: no automatic subscriptions are wired here. A
concrete learner registers itself with the bus from the composition root.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List

logger = logging.getLogger("arbicore.event_bus")

Handler = Callable[[str, Dict[str, Any]], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._subs: Dict[str, List[Handler]] = {}
        self._lock = asyncio.Lock()

    def subscribe(self, topic: str, handler: Handler) -> None:
        """Register a handler for a topic. Handlers run sequentially in the
        order they were registered."""
        if not asyncio.iscoroutinefunction(handler):
            raise TypeError("EventBus.subscribe requires an async handler")
        self._subs.setdefault(topic, []).append(handler)

    def topic_count(self) -> int:
        return len(self._subs)

    def subscriber_count(self, topic: str) -> int:
        return len(self._subs.get(topic, []))

    async def publish(self, topic: str, payload: Dict[str, Any]) -> int:
        """Deliver payload to all subscribers of ``topic``. Returns the number
        of subscribers invoked. Handler exceptions are logged and swallowed
        (one bad subscriber must not break the pipeline)."""
        handlers = list(self._subs.get(topic, []))
        if not handlers:
            return 0
        for h in handlers:
            try:
                await h(topic, payload)
            except Exception as exc:  # noqa: BLE001
                logger.exception("event_bus subscriber failed topic=%s err=%s",
                                 topic, exc)
        return len(handlers)


# Canonical topic names — keep these as constants so misspellings break loudly.
TOPIC_OPPORTUNITY_UPSERTED = "opportunity.upserted"
TOPIC_OPPORTUNITY_DECISION = "opportunity.decision"
TOPIC_OUTCOME_EVALUATED    = "outcome.evaluated"
