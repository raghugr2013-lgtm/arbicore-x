"""T1 regression tests for the M3.0 offline (no-RPC) validation path.

These lock in three things discovered while running the offline harness:
  1. Fail-closed invariants of the audit produced by scripts.m3_0_vps_validate.
  2. ``_first_blocking_stage`` must mirror ``composition.fresh_fn`` ordering even
     when a probe stage recorded an ERROR string (not None/dict).
  3. ``live_quote_provider`` must not explode on mixed-case Base token symbols
     (cbETH / USDbC / cbBTC / rETH / wstETH / weETH) — it uppercases the token
     path and then indexes the case-sensitive TOKENS map.
"""
import asyncio
import json
import os
import subprocess
import sys

import pytest

BACKEND = "/app/app/backend"


# ---------------------------------------------------------------- offline harness
@pytest.fixture(scope="module")
def harness_audit(tmp_path_factory):
    audit = tmp_path_factory.mktemp("m3") / "m3_audit.json"
    env = dict(os.environ)
    env.update({"PYTHONPATH": ".", "ARBICORE_M3_AUDIT_FILE": str(audit)})
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.m3_0_vps_validate"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=300)
    assert audit.exists(), f"no audit file. stderr={proc.stderr[-2000:]}"
    return json.loads(audit.read_text())  # must be pure JSON


class TestOfflineHarnessFailClosed:
    def test_audit_is_valid_json_with_expected_sections(self, harness_audit):
        for key in ("env", "constructions", "m3_final_gates",
                    "broadcast_ladder", "verdict", "fresh_stage_probe"):
            assert key in harness_audit, key

    def test_nothing_signed_or_broadcast(self, harness_audit):
        v = harness_audit["verdict"]
        assert v["signed_or_broadcast"] is False
        assert v["safe"] is True
        assert harness_audit["broadcast_ladder"]["broadcast_sent"] is False

    def test_final_gates_fail_closed_without_validator(self, harness_audit):
        gates = harness_audit["m3_final_gates"]
        assert gates["ok"] is False
        assert "validator is None" in gates["reason"]
        assert harness_audit["verdict"]["controlled_live_layer_constructed"] is False
        assert harness_audit["verdict"]["require_revalidation"] is True

    def test_mev_stage_fails_closed_without_rpc(self, harness_audit):
        mev = harness_audit["fresh_stage_probe"]["stage_8_mev"]
        assert isinstance(mev, dict)
        assert mev["congestion_pct"] is None
        assert mev["congestion_source"] == "no_base_rpc"
        assert mev["mev_ok"] is None

    def test_first_blocking_stage_mirrors_fresh_fn_order(self, harness_audit):
        """fresh_fn evaluates live_quote(facts) BEFORE mev, so with no RPC the
        reported blocker must be the stage-6 quote, not stage_8_mev."""
        probe = harness_audit["fresh_stage_probe"]
        blocker = probe["FIRST_BLOCKING_STAGE"]
        assert blocker != "none - all fresh stages resolved (validation should be GREEN)"
        assert "stage_6" in blocker, (
            f"stage_6_facts={probe.get('stage_6_facts')!r} but blocker={blocker!r}")


# ------------------------------------------------- _first_blocking_stage ordering
def test_first_blocking_stage_handles_error_string_at_stage_6():
    sys.path.insert(0, BACKEND)
    from scripts.m3_0_vps_validate import _first_blocking_stage
    out = {
        "stage_1_plan_shape": {"shape_ok": True},
        "stage_6_facts": "ERROR KeyError: 'CBETH'",
        "stage_8_mev": {"congestion_pct": None, "mev_ok": None},
    }
    assert "stage_6" in _first_blocking_stage(out)


# --------------------------------------------- mixed-case token symbol handling
def test_token_address_lookup_for_mixed_case_symbols():
    sys.path.insert(0, BACKEND)
    from arbicore.discovery.base_venues import TOKENS, token_address
    for sym in ("cbETH", "USDbC", "cbBTC", "rETH", "wstETH", "weETH"):
        assert sym in TOKENS
        # live_quote_provider uppercases before calling token_address()
        assert token_address(sym.upper()), f"{sym.upper()} unresolvable"


def test_live_quote_provider_does_not_raise_on_cbeth_route():
    sys.path.insert(0, BACKEND)
    from arbicore.scanners.flash_loan_arbitrage.live_quote_provider import (
        make_live_quote_provider)

    class _Reg:
        async def quote_route(self, chain, hops):
            return None

    prov = make_live_quote_provider(_Reg())
    hm = {"chain": "base", "provider": "balancer_v2", "borrow_token": "USDC",
          "route_pools": ["uniswap_v3:USDC:cbETH:500",
                          "uniswap_v3:USDC:cbETH:3000"],
          "cycle_token_path": ["USDC", "cbETH", "USDC"]}
    facts = asyncio.run(prov(hm, 1000.0))
    assert facts is None  # honest deny, must NOT raise KeyError
