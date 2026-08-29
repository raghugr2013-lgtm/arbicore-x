"""Deterministic tests: executor-address resolution, signer readiness, the
end-to-end Limited-Live readiness matrix, and the Aerodrome-denied executor
capability rule. No network / no DB / no broadcast / no env mutation left behind.
"""
import os

import pytest

from arbicore.scanners.flash_loan_arbitrage.live_readiness_probes import (
    resolve_executor_address, probe_signer_readiness,
)
from arbicore.scanners.flash_loan_arbitrage.limited_live_readiness_matrix import (
    build_readiness_matrix, READY, BLOCKED, UNKNOWN, MARKET,
)
from arbicore.scanners.flash_loan_arbitrage.executor_capability import (
    evaluate_executor_capability, ExecutorCapabilityStatus,
)

SEPOLIA_ADDR = "0x99c0b64e8F24fc1aADb07dAbA938d9f11dCD1052"


# --- executor address resolution (env first, then registry) ---------------
def test_resolve_prefers_env(monkeypatch):
    monkeypatch.setenv("ARBICORE_EXECUTOR_ADDRESS_BASE", "0x" + "ab" * 20)
    assert resolve_executor_address() == "0x" + "ab" * 20


def test_resolve_falls_back_to_registry_for_sepolia(monkeypatch):
    monkeypatch.delenv("ARBICORE_EXECUTOR_ADDRESS_BASE", raising=False)
    assert resolve_executor_address(84532) == SEPOLIA_ADDR


def test_resolve_none_for_mainnet_when_not_deployed(monkeypatch):
    monkeypatch.delenv("ARBICORE_EXECUTOR_ADDRESS_BASE", raising=False)
    assert resolve_executor_address(8453) is None


# --- signer readiness (no keys) --------------------------------------------
def test_signer_absent_is_not_ready(monkeypatch):
    monkeypatch.delenv("ARBICORE_EXECUTOR_SIGNER_ADDRESS", raising=False)
    r = probe_signer_readiness()
    assert r["ready"] is False and r["signer_present"] is False
    assert r["signed"] is False and r["broadcast"] is False


def test_signer_present_but_owner_unverified_not_ready(monkeypatch):
    monkeypatch.setenv("ARBICORE_EXECUTOR_SIGNER_ADDRESS", "0x" + "cd" * 20)
    r = probe_signer_readiness(executor_owner=None)
    assert r["signer_present"] is True and r["ready"] is False
    assert r["owner_match"] is None


def test_signer_mismatch_denies(monkeypatch):
    monkeypatch.setenv("ARBICORE_EXECUTOR_SIGNER_ADDRESS", "0x" + "cd" * 20)
    r = probe_signer_readiness(executor_owner="0x" + "ef" * 20)
    assert r["owner_match"] is False and r["ready"] is False


def test_signer_matches_owner_is_ready(monkeypatch):
    addr = "0x" + "cd" * 20
    monkeypatch.setenv("ARBICORE_EXECUTOR_SIGNER_ADDRESS", addr)
    r = probe_signer_readiness(executor_owner=addr.upper())
    assert r["owner_match"] is True and r["ready"] is True


# --- Aerodrome must remain denied ------------------------------------------
def test_executor_capability_aerodrome_denied():
    cap = evaluate_executor_capability(
        route_pools=["p1", "p2"],
        pool_specs={"p1": {"dex": "uniswap_v3"}, "p2": {"dex": "aerodrome_slipstream"}},
        executor_address=SEPOLIA_ADDR)
    assert cap.status == ExecutorCapabilityStatus.UNSUPPORTED


def test_executor_capability_univ3_only_supported():
    cap = evaluate_executor_capability(
        route_pools=["p1", "p2"],
        pool_specs={"p1": {"dex": "uniswap_v3"}, "p2": {"dex": "uniswap_v3"}},
        executor_address=SEPOLIA_ADDR)
    assert cap.status == ExecutorCapabilityStatus.SUPPORTED


def test_executor_capability_unknown_venue_unverifiable():
    cap = evaluate_executor_capability(
        route_pools=["p1"], pool_specs={"p1": {}}, executor_address=SEPOLIA_ADDR)
    assert cap.status == ExecutorCapabilityStatus.UNVERIFIABLE


# --- readiness matrix -------------------------------------------------------
def _op(mode="SHADOW", mode_allows=False, kill_ok=True, engaged=False):
    return {"mode": mode, "mode_allows": mode_allows,
            "kill_switch_ok": kill_ok, "kill_switch_engaged": engaged}


def _find(matrix, name):
    return next(i for i in matrix["items"] if i["prerequisite"] == name)


def test_matrix_current_shadow_posture():
    m = build_readiness_matrix(
        rpc_configured=True, mongo_ok=True, executor_address=None,
        executor_identity_ok=None, signer={"ready": False, "reason": "absent"},
        operator_state=_op(), confirmed_count=0)
    assert _find(m, "rpc_base")["status"] == READY
    assert _find(m, "executor_deployed")["status"] == BLOCKED
    assert _find(m, "operator_mode_allows")["status"] == BLOCKED  # SHADOW
    assert _find(m, "kill_switch_ok")["status"] == READY
    assert _find(m, "confirmed_candidate")["status"] == MARKET
    assert _find(m, "atomic_simulation")["status"] == BLOCKED  # no signer
    assert _find(m, "economics_gate7")["status"] == MARKET
    assert m["overall"] == "AWAITING_OPERATOR_AND_ONCHAIN_ACTIONS"
    assert m["signed"] is False and m["broadcast"] is False
    assert m["limited_live_enabled"] is False


def test_matrix_software_incomplete_when_rpc_missing():
    m = build_readiness_matrix(
        rpc_configured=False, mongo_ok=True, executor_address=SEPOLIA_ADDR,
        executor_identity_ok=True, signer={"ready": True, "reason": "ok"},
        operator_state=_op(mode="LIMITED_LIVE", mode_allows=True), confirmed_count=1)
    assert _find(m, "rpc_base")["status"] == BLOCKED
    assert m["overall"] == "SOFTWARE_INCOMPLETE"


def test_matrix_all_infra_ready_awaiting_market():
    # Executor + signer + mode + kill all ready; only market remains.
    m = build_readiness_matrix(
        rpc_configured=True, mongo_ok=True, executor_address=SEPOLIA_ADDR,
        executor_identity_ok=True, signer={"ready": True, "reason": "matches owner"},
        operator_state=_op(mode="LIMITED_LIVE", mode_allows=True), confirmed_count=0)
    assert _find(m, "executor_deployed")["status"] == READY
    assert _find(m, "signer_authorization")["status"] == READY
    assert _find(m, "operator_mode_allows")["status"] == READY
    assert _find(m, "atomic_simulation")["status"] == MARKET  # signer ready -> per-candidate
    assert m["counts"]["blocked"] == 0 and m["counts"]["unknown"] == 0
    assert m["overall"] == "SOFTWARE_READY_MARKET_AND_OPERATOR_PENDING"
