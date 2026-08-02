"""Tests for audit logging."""
from arbicore.intelligence import AuditLogger, InMemoryAuditStore


def test_log_and_query():
    logger = AuditLogger()
    logger.log("info", "scan started", source="dex_scanner")
    logger.log("warning", "rate limited", source="dex_scanner")
    logger.log("error", "boom", source="rpc")

    assert len(logger.query(limit=10)) == 3
    assert len(logger.query(limit=10, source="dex_scanner")) == 2
    assert len(logger.query(limit=10, type="error")) == 1


def test_query_newest_first():
    logger = AuditLogger()
    logger.log("info", "first")
    logger.log("info", "second")
    results = logger.query(limit=10)
    assert results[0].message == "second"


def test_auto_trim():
    store = InMemoryAuditStore()
    logger = AuditLogger(store=store)
    logger.MAX_RECORDS = 5
    for i in range(8):
        logger.log("info", f"msg {i}")
    assert store.count() == 5
