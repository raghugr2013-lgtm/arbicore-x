"""Opt-in NON-LIVE fork-equivalent certification (live Base mainnet state).

Skipped by default so the offline suite stays deterministic and does not hit a
public RPC. Enable with ``ARBICORE_RUN_FORK_CERT=1`` (optionally set
``ARBICORE_FORK_RPC`` to a preferred Base endpoint). Read-only: no signing, no
broadcast, no deployment, no mainnet transaction.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("ARBICORE_RUN_FORK_CERT") != "1",
    reason="fork cert is opt-in; set ARBICORE_RUN_FORK_CERT=1 to run against live Base state",
)


def test_fork_equivalent_execution_proof():
    from scripts.nonlive_fork_cert import main
    ev = main()
    cc = ev["capability_changes"]
    # Prerequisites that MUST hold on a real Base endpoint.
    assert ev["stages"]["chain_verification"]["passed"] is True
    assert cc["chain_verification"] == "FORK-TESTED"
    assert cc["state_override_capability"] == "FORK-TESTED"
    assert cc["live_univ3_quote"] == "FORK-TESTED"
    assert cc["route_swap_repayment_economics"] == "FORK-TESTED"
    # Truth invariants that must NEVER be upgraded by a fork run.
    assert cc["mainnet_execution_certified"].startswith("FALSE")
    assert cc["economically_valid_real"].startswith("0")
    assert cc["limited_live_eligible"] == "NO"
    assert cc["full_live_eligible"] == "NO"
    assert ev["label"]["signing"] == "OFF" and ev["label"]["broadcast"] == "OFF"
    assert ev["stages"]["fail_closed"]["receiver_supports_balancer_v2_base"] is False
