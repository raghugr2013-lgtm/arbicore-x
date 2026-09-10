"""Track 8 — readiness reflects ACTUAL flash-loan capability (no false GREEN).

Proves the FLASH_LOAN_ENGINE check is evidence-driven:
  * it reports the runtime liquidity probe that genuinely exists,
  * it NO LONGER statically claims "Aave V3 executable / Balancer V2 executable",
  * execution capability stays UNPROVEN until a deployed receiver EXPLICITLY
    supports a flash head (receiver_capability fail-closed),
  * LIMITED_LIVE remains RED / non-activatable while mandatory evidence absent.
"""
from __future__ import annotations

import pytest

from arbicore.control.readiness import ExecutionReadinessEngine, GREEN, RED
from arbicore.execution.receiver_capability import receiver_capability


def test_flash_check_is_evidence_driven_not_static_executable():
    eng = ExecutionReadinessEngine()
    chk = eng._flash()
    assert chk["name"] == "FLASH_LOAN_ENGINE"
    blob = " ".join(chk["passed"] + chk["warnings"]).lower()
    # Must describe the real runtime probe...
    assert "runtime liquidity probe implemented" in blob
    assert "balancer_v2" in blob and "aave_v3" in blob
    # ...and must NOT resurrect the old static "executable" claim.
    assert "aave v3 executable" not in blob
    assert "balancer v2 executable" not in blob


def test_flash_execution_unproven_without_deployed_receiver():
    # No receiver deployment recorded ⇒ execution capability is fail-closed.
    cap = receiver_capability("base")
    assert cap.deployed is False
    assert cap.supports("aave_v3") is False
    assert cap.supports("balancer_v2") is False

    chk = ExecutionReadinessEngine()._flash()
    warn = " ".join(chk["warnings"]).lower()
    assert "execution capability unproven" in warn
    # Engine is implemented (GREEN) but honest about not being "executable".
    assert chk["status"] == GREEN


@pytest.mark.asyncio
async def test_limited_live_stays_red_without_mandatory_evidence():
    report = await ExecutionReadinessEngine().evaluate()
    ll = report["modes"]["LIMITED_LIVE"]
    assert ll["status"] == RED
    assert ll["can_activate"] is False
    assert ll["blockers"]   # concrete blockers enumerated, never empty


@pytest.mark.asyncio
async def test_limited_live_transition_always_refused():
    guard = await ExecutionReadinessEngine().can_transition("LIMITED_LIVE")
    assert guard["allowed"] is False
