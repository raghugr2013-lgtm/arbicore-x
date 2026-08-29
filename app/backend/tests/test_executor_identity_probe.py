"""Deterministic tests for the read-only executor identity probe and the
canonical readiness assembler (gather_and_build). No network / no DB / no
broadcast; the on-chain inspector is injected.
"""
import pytest

from arbicore.scanners.flash_loan_arbitrage.live_readiness_probes import (
    probe_executor_identity,
)
from arbicore.scanners.flash_loan_arbitrage.limited_live_readiness_matrix import (
    gather_and_build,
)

EXE = "0x99c0b64e8F24fc1aADb07dAbA938d9f11dCD1052"
OWNER = "0x1111111111111111111111111111111111111111"
VAULT = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"
ROUTER = "0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4"
EXPECT = {"vault": VAULT, "router": ROUTER}


def _mk(ok=True, owner=OWNER, router=ROUTER, vault=VAULT, entry=True, reason=None):
    async def _insp(rpc_url, executor):
        if not ok:
            return {"ok": False, "reason": reason or "no bytecode at executor address"}
        return {"ok": True, "bytecode_size_bytes": 321, "owner": owner,
                "router": router, "vault": vault,
                "entrypoint_selector_present": entry, "signed": False, "broadcast": False}
    return _insp


async def test_identity_executor_absent_blocked():
    r = await probe_executor_identity(executor_address=None, rpc_url="http://rpc")
    assert r["status"] == "BLOCKED" and r["exists"] is False
    assert r["reason"] == "executor_address_absent"


async def test_identity_no_rpc_unknown():
    r = await probe_executor_identity(executor_address=EXE, rpc_url="")
    assert r["status"] == "UNKNOWN" and "rpc" in r["reason"]


async def test_identity_present_and_matching_ready():
    r = await probe_executor_identity(executor_address=EXE, rpc_url="http://rpc",
                                      expected=EXPECT, inspector=_mk())
    assert r["status"] == "READY" and r["owner"] == OWNER
    assert r["bytecode_present"] is True and r["mismatches"] == []
    assert r["signed"] is False and r["broadcast"] is False


async def test_identity_no_bytecode_blocked():
    r = await probe_executor_identity(executor_address=EXE, rpc_url="http://rpc",
                                      expected=EXPECT, inspector=_mk(ok=False))
    assert r["status"] == "BLOCKED" and r["bytecode_present"] is False


async def test_identity_router_mismatch_blocked():
    r = await probe_executor_identity(
        executor_address=EXE, rpc_url="http://rpc", expected=EXPECT,
        inspector=_mk(router="0x0000000000000000000000000000000000009999"))
    assert r["status"] == "BLOCKED" and r["mismatches"] == ["router"]


async def test_identity_missing_entrypoint_blocked():
    r = await probe_executor_identity(executor_address=EXE, rpc_url="http://rpc",
                                      expected=EXPECT, inspector=_mk(entry=False))
    assert r["status"] == "BLOCKED" and "entrypoint" in r["reason"]


async def test_identity_inspector_exception_unknown():
    async def _boom(rpc_url, executor):
        raise RuntimeError("rpc down")
    r = await probe_executor_identity(executor_address=EXE, rpc_url="http://rpc",
                                      expected=EXPECT, inspector=_boom)
    assert r["status"] == "UNKNOWN" and "inspection_error" in r["reason"]


# --- canonical assembler ----------------------------------------------------
async def test_gather_and_build_shadow_posture(monkeypatch):
    monkeypatch.delenv("ARBICORE_EXECUTOR_ADDRESS_BASE", raising=False)
    monkeypatch.delenv("ARBICORE_EXECUTOR_SIGNER_ADDRESS", raising=False)
    out = await gather_and_build(
        db=None, rpc_url="http://rpc", chain="84532",
        confirmed_count=0, inspector=_mk())  # registry supplies Sepolia address
    assert out["executor_address_resolved"] is True
    assert out["executor_identity"]["status"] == "READY"
    m = out["matrix"]
    assert m["signed"] is False and m["broadcast"] is False
    assert m["limited_live_enabled"] is False
    # db=None => mode UNKNOWN => mode_allows denied; signer absent => blocked
    assert "operator_mode_allows" in m["blocked"]
    assert "signer_authorization" in m["blocked"]


async def test_gather_and_build_no_executor_blocked(monkeypatch):
    monkeypatch.delenv("ARBICORE_EXECUTOR_ADDRESS_BASE", raising=False)
    out = await gather_and_build(
        db=None, rpc_url="", chain="8453", confirmed_count=0)  # mainnet not deployed
    assert out["executor_address_resolved"] is False
    assert "executor_deployed" in out["matrix"]["blocked"]
    assert out["matrix"]["signed"] is False and out["matrix"]["broadcast"] is False
