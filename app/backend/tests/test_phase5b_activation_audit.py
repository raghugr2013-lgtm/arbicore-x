"""Phase-5b regression coverage — certification blockers 1–4.

  (1) Docker provenance: the source Git SHA cannot silently become ``unknown``
      or a different SHA (``scripts.gen_build_info`` strict resolution).
  (2) Multichain operator RPC certification: all six supported chains consume
      ``PROVIDER_RPC_URLS_<CHAIN>`` / ``ARBICORE_RPC_URL_<CHAIN>`` and fail closed
      when unset — never fabricated.
  (3) Executor-capability classification is honest: ``execution_capable`` is a
      strict subset of the deployed executor's ``SUPPORTED_DEXES`` and no
      synthetic capability is invented.
  (4) The read-only M3 broadcast-ladder proof is Mongo-isolated: when the
      execution-policy Mongo is unreachable it DEFERS with an explicit status
      (never hangs, never fakes a broadcast, never hides the dependency).

Offline, deterministic, no RPC / signing / broadcast / real Mongo.
"""
from __future__ import annotations

import asyncio

import pytest

VALID_SHA = "3dbf947857cd5646476a5e5a84ece7a6e7259ebc"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ─────────────────────── (1) Docker provenance ─────────────────────────────
from scripts.gen_build_info import (  # noqa: E402
    build_info, resolve_git_identity, is_valid_full_sha)


def test_valid_full_sha_matcher():
    assert is_valid_full_sha(VALID_SHA)
    assert not is_valid_full_sha("unknown")
    assert not is_valid_full_sha("3dbf947")           # short
    assert not is_valid_full_sha(VALID_SHA + "ff")    # too long
    assert not is_valid_full_sha(None)


def test_provided_sha_is_embedded_exactly():
    info = build_info(env={"ARBICORE_GIT_SHA": VALID_SHA}, live_sha=None,
                      live_tag=None, strict=True)
    assert info["git_sha"] == VALID_SHA


def test_strict_refuses_unknown_sha():
    with pytest.raises(ValueError):
        resolve_git_identity(env={}, live_sha=None, live_tag=None, strict=True)


def test_malformed_sha_always_rejected_even_non_strict():
    with pytest.raises(ValueError):
        resolve_git_identity(env={"ARBICORE_GIT_SHA": "bd969ee"}, live_sha=None,
                             live_tag=None, strict=False)


def test_live_git_used_when_no_env_and_strict():
    info = build_info(env={}, live_sha=VALID_SHA, live_tag="v-test", strict=True)
    assert info["git_sha"] == VALID_SHA and info["git_tag"] == "v-test"


# ───────────────── (2) Multichain operator RPC certification ────────────────
from arbicore.runtime import multichain_readiness as MR  # noqa: E402

SIX_CHAINS = ["base", "ethereum", "arbitrum", "optimism", "polygon", "bnb"]


def test_all_six_chains_supported():
    supported = MR.supported_networks()
    for c in SIX_CHAINS:
        assert c in supported, f"{c} missing from supported_networks()"


def test_rpc_fail_closed_when_unset(monkeypatch):
    for c in SIX_CHAINS:
        for k in (f"PROVIDER_RPC_URLS_{c.upper()}", f"PROVIDER_RPC_URL_{c.upper()}",
                  f"ARBICORE_RPC_URL_{c.upper()}", f"{c.upper()}_RPC_URL"):
            monkeypatch.delenv(k, raising=False)
        assert MR.rpc_explicitly_configured(c) is False
        assert MR.provider_registry_rpc_configured(c) is False


def test_provider_rpc_urls_consumed_per_chain(monkeypatch):
    for c in SIX_CHAINS:
        monkeypatch.setenv(f"PROVIDER_RPC_URLS_{c.upper()}", "https://rpc.example/" + c)
        assert MR.rpc_explicitly_configured(c) is True
        # PROVIDER_RPC_URLS_* also backs the economic gate.
        assert MR.provider_registry_rpc_configured(c) is True
        monkeypatch.delenv(f"PROVIDER_RPC_URLS_{c.upper()}")


def test_arbicore_rpc_url_consumed_for_discovery_only(monkeypatch):
    for c in SIX_CHAINS:
        for k in (f"PROVIDER_RPC_URLS_{c.upper()}", f"PROVIDER_RPC_URL_{c.upper()}"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv(f"ARBICORE_RPC_URL_{c.upper()}", "https://rpc.example/" + c)
        assert MR.rpc_explicitly_configured(c) is True          # discovery seam
        assert MR.provider_registry_rpc_configured(c) is False  # NOT economic gate
        monkeypatch.delenv(f"ARBICORE_RPC_URL_{c.upper()}")


# ─────────────── (3) Executor-capability classification honesty ─────────────
from scripts.executor_capability_audit import (  # noqa: E402
    audit_execution_capability, EXECUTOR_SUPPORTED_FLASH)
from arbicore.scanners.flash_loan_arbitrage.executor_capability import (  # noqa: E402
    SUPPORTED_DEXES)


def test_execution_capable_is_subset_of_supported_dexes():
    rep = audit_execution_capability()
    exec_dexes = {d.strip().lower() for d in SUPPORTED_DEXES}
    for v in rep["venues"]:
        if v["execution_capable"]:
            assert v["venue"].strip().lower() in exec_dexes, (
                f"{v['venue']} marked execution_capable but not in SUPPORTED_DEXES")


def test_aerodrome_route_constructable_but_not_execution_capable():
    rep = audit_execution_capability()
    aero = [v for v in rep["venues"]
            if v["venue"] == "aerodrome" and v["chain"] == "base"]
    assert aero, "aerodrome/base venue missing from audit"
    a = aero[0]
    assert a["route_constructable"] is True     # adapter exists
    assert a["execution_capable"] is False      # on-chain receiver = UniV3 only
    assert "uniswap_v3 swap hops only" in a["blocker"]


def test_curve_and_solidly_reported_not_discoverable_not_dropped():
    rep = audit_execution_capability()
    venues = {(v["chain"], v["venue"]): v for v in rep["venues"]}
    # Preserved in the surface (not silently removed) but honestly not runnable.
    assert ("ethereum", "curve_stable") in venues
    assert venues[("ethereum", "curve_stable")]["discoverable"] is False
    assert ("optimism", "velodrome_v2") in venues
    assert venues[("optimism", "velodrome_v2")]["discoverable"] is False


def test_flash_provider_execution_capability_honest():
    rep = audit_execution_capability()
    fp = {f["provider"]: f for f in rep["flash_providers"]}
    assert fp["balancer_v2"]["execution_capable"] is True
    # Reconciled to the deployed receiver ABI: Balancer V2 AND Aave V3 flash.
    assert fp["aave_v3"]["adapter_available"] is True
    assert fp["aave_v3"]["execution_capable"] is True
    assert fp["uniswap_v3"]["execution_capable"] is False
    assert set(EXECUTOR_SUPPORTED_FLASH) == {"balancer_v2", "aave_v3"}


# ─────────────── (4) M3 broadcast-ladder Mongo isolation ────────────────────
from scripts.m3_0_real_candidate_scan import (  # noqa: E402
    _broadcast_ladder_proof, _mongo_reachable)


def test_mongo_unreachable_defers_ladder(monkeypatch):
    # Point MONGO_URL at a black-hole host with a tiny timeout → unreachable.
    monkeypatch.setenv("MONGO_URL", "mongodb://10.255.255.1:27017")
    monkeypatch.setenv("DB_NAME", "arbicore_x_test")
    reachable, _detail = _run(_mongo_reachable(timeout_ms=300))
    assert reachable is False
    candidates = [{"plan": {"strategy": "flash_loan_arbitrage", "chain": "base"}}]
    res = _run(_broadcast_ladder_proof(candidates, validator=None, breaker=None))
    assert res["status"] == "deferred_mongo_unavailable"
    assert res["broadcast_sent"] is False


def test_ladder_skipped_with_no_candidates():
    res = _run(_broadcast_ladder_proof([], validator=None, breaker=None))
    assert res["status"] == "skipped_no_candidates"
    assert res["broadcast_sent"] is False
