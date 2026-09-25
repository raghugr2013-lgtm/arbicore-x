"""Hermetic unit tests for the pure readiness core (no arbicore imports).

Loads ``readiness_core.py`` directly by file path so it runs with plain
``python3`` in any environment (no Mongo, no RPC, no package boot).
"""
import importlib.util
import os
import sys

_CORE = os.path.join(os.path.dirname(__file__), "..", "arbicore",
                     "certification", "readiness_core.py")
_spec = importlib.util.spec_from_file_location("readiness_core", _CORE)
rc = importlib.util.module_from_spec(_spec)
sys.modules["readiness_core"] = rc          # dataclass introspection needs this
_spec.loader.exec_module(rc)


def _item(domain, subject, status, category=rc.Category.NONE, **kw):
    return rc.ReadinessItem(domain=domain, subject=subject, status=status,
                            category=category, **kw)


def test_ready_item_forces_none_category():
    it = _item("RPC", "base", rc.Status.READY, category=rc.Category.CODE)
    assert it.category == rc.Category.NONE


def test_non_ready_requires_real_category():
    ok = False
    try:
        _item("RPC", "ethereum", rc.Status.BLOCKED)  # NONE default → invalid
    except ValueError:
        ok = True
    assert ok


def test_roll_up_worst_first():
    assert rc.roll_up([]) == rc.Status.UNKNOWN
    assert rc.roll_up([rc.Status.READY, rc.Status.READY]) == rc.Status.READY
    assert rc.roll_up([rc.Status.READY, rc.Status.DEGRADED]) == rc.Status.DEGRADED
    assert rc.roll_up([rc.Status.DEGRADED, rc.Status.UNKNOWN]) == rc.Status.UNKNOWN
    assert rc.roll_up([rc.Status.UNKNOWN, rc.Status.BLOCKED]) == rc.Status.BLOCKED


def test_aggregate_overall_and_splits():
    items = [
        _item("RPC", "base", rc.Status.READY),
        _item("RPC", "ethereum", rc.Status.BLOCKED, rc.Category.ENVIRONMENT,
              what_missing="ARBICORE_RPC_URL_ETHEREUM", required_value="https://…"),
        _item("VENUE", "polygon/curve", rc.Status.BLOCKED, rc.Category.CODE,
              why_blocked="no curve resolver"),
        _item("MARKET", "edge", rc.Status.BLOCKED, rc.Category.MARKET,
              why_blocked="no >=$25 net edge yet"),
        _item("SAFETY", "kill_switch", rc.Status.READY),
    ]
    rep = rc.aggregate(items, head_sha="2a6fadb8")
    assert rep["overall"] == rc.Status.BLOCKED
    assert rep["counts"][rc.Status.READY] == 2
    assert rep["counts"][rc.Status.BLOCKED] == 3
    assert rep["by_domain"]["RPC"] == rc.Status.BLOCKED   # base READY but eth BLOCKED
    assert rep["by_domain"]["SAFETY"] == rc.Status.READY
    assert len(rep["operator_actionable"]) == 1           # eth RPC
    assert len(rep["code_remainder"]) == 1                # curve resolver
    assert len(rep["market_pending"]) == 1
    assert rep["full_live_ready"] is False
    # BLOCKED sorts before others in the blocker list
    assert rep["blockers"][0]["status"] == rc.Status.BLOCKED


def test_aggregate_all_ready_is_full_live():
    items = [_item("RPC", "base", rc.Status.READY),
             _item("SAFETY", "kill_switch", rc.Status.READY)]
    rep = rc.aggregate(items)
    assert rep["overall"] == rc.Status.READY
    assert rep["full_live_ready"] is True


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} readiness-core tests passed")
