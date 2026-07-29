"""Phase C Wave 1 — Event Bus contract test."""
import asyncio

import pytest

from arbicore.runtime.event_bus import (
    EventBus,
    TOPIC_OPPORTUNITY_UPSERTED,
    TOPIC_OUTCOME_EVALUATED,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_subscribe_requires_async_handler():
    bus = EventBus()
    with pytest.raises(TypeError):
        bus.subscribe(TOPIC_OPPORTUNITY_UPSERTED, lambda t, p: None)


def test_publish_with_no_subscribers_returns_zero():
    bus = EventBus()
    assert _run(bus.publish(TOPIC_OPPORTUNITY_UPSERTED, {})) == 0


def test_publish_dispatches_in_order():
    bus = EventBus()
    seen = []

    async def h1(t, p):
        seen.append(("h1", p["v"]))

    async def h2(t, p):
        seen.append(("h2", p["v"]))

    bus.subscribe(TOPIC_OPPORTUNITY_UPSERTED, h1)
    bus.subscribe(TOPIC_OPPORTUNITY_UPSERTED, h2)
    count = _run(bus.publish(TOPIC_OPPORTUNITY_UPSERTED, {"v": 7}))
    assert count == 2
    assert seen == [("h1", 7), ("h2", 7)]


def test_failing_subscriber_is_isolated(caplog):
    import logging
    bus = EventBus()
    seen = []

    async def bad(t, p):
        raise RuntimeError("boom")

    async def good(t, p):
        seen.append(p["v"])

    bus.subscribe(TOPIC_OUTCOME_EVALUATED, bad)
    bus.subscribe(TOPIC_OUTCOME_EVALUATED, good)
    with caplog.at_level(logging.ERROR, logger="arbicore.event_bus"):
        _run(bus.publish(TOPIC_OUTCOME_EVALUATED, {"v": 99}))
    assert seen == [99]
    assert any("event_bus subscriber failed" in r.getMessage() for r in caplog.records)
