"""Phase 10.7 · Guided Flash Loan Journey — unit tests (offline)."""
from __future__ import annotations
import asyncio
from arbicore.execution.operator_journey import build_journey


def _run(coro):
    return asyncio.run(coro)


def _wizard(steps):
    return {"steps": [{"key": k, "status": v} for k, v in steps.items()]}


def _prereqs():
    return {"checks": []}


def _pt(receipts=None):
    return {"receipts": receipts or []}


class TestJourneyAggregator:
    def test_all_blocked_shows_current_at_earliest_blocker(self):
        r = _run(build_journey(
            wizard_state=_wizard({"rpc": "BLOCKED", "wallet": "BLOCKED",
                                    "secret": "BLOCKED", "executor": "BLOCKED",
                                    "executor_verify": "BLOCKED"}),
            prereqs=_prereqs(), post_trade=_pt(),
            scanner_family_enabled=False, operational_flags={},
        ))
        assert len(r["stages"]) == 14
        assert r["completed"] is False
        # Stage 1 (settings) always READY; current stage index points to first non-READY.
        assert r["current_stage_index"] >= 1

    def test_family_enable_reflects_scanner_state(self):
        r = _run(build_journey(
            wizard_state=_wizard({"rpc": "READY", "wallet": "READY",
                                    "secret": "READY", "executor": "READY",
                                    "executor_verify": "READY"}),
            prereqs=_prereqs(), post_trade=_pt(),
            scanner_family_enabled=True, operational_flags={},
        ))
        fam = next(s for s in r["stages"] if s["key"] == "family_on")
        assert fam["status"] == "READY"

    def test_first_live_ready_after_broadcast(self):
        r = _run(build_journey(
            wizard_state=_wizard({"rpc": "READY", "wallet": "READY",
                                    "secret": "READY", "executor": "READY",
                                    "executor_verify": "READY"}),
            prereqs=_prereqs(),
            post_trade=_pt([{"mode": "LIMITED_LIVE", "broadcast_sent": True,
                               "tx_hash": "0xabc"}]),
            scanner_family_enabled=True, operational_flags={},
        ))
        stage = next(s for s in r["stages"] if s["key"] == "first_live")
        assert stage["status"] == "READY"

    def test_journey_complete_after_vps_ready_flag(self):
        r = _run(build_journey(
            wizard_state=_wizard({"rpc": "READY", "wallet": "READY",
                                    "secret": "READY", "executor": "READY",
                                    "executor_verify": "READY"}),
            prereqs=_prereqs(),
            post_trade=_pt([
                {"mode": "LIMITED_LIVE", "broadcast_sent": True,
                 "tx_hash": "0xabc", "preflight_ok": True},
                # A revert-test receipt: tx_hash present but preflight_ok=False
                {"mode": "LIMITED_LIVE", "broadcast_sent": True,
                 "tx_hash": "0xdef", "preflight_ok": False},
            ]),
            scanner_family_enabled=True,
            operational_flags={"vps_ready": True},
        ))
        stage = next(s for s in r["stages"] if s["key"] == "post_trade")
        assert stage["status"] == "READY"
        assert r["completed"] is True

    def test_fix_paths_populated(self):
        r = _run(build_journey(wizard_state=_wizard({}), prereqs=_prereqs(),
                                 post_trade=_pt(), scanner_family_enabled=False,
                                 operational_flags={}))
        # Every stage should have a fix_path (some are info-only but still populated)
        for s in r["stages"]:
            assert "fix_path" in s

    def test_progressive_unlock(self):
        r = _run(build_journey(
            wizard_state=_wizard({"rpc": "BLOCKED"}),
            prereqs=_prereqs(), post_trade=_pt(),
            scanner_family_enabled=False, operational_flags={},
        ))
        # First stage (settings) always READY → unlocked; blocker stops progression
        assert r["stages"][0]["unlocked"] is True
        # Later stages should be locked
        assert r["stages"][-1]["unlocked"] is False
