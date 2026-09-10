"""Regression — multichain readiness gate (explicit, honest per-network status).

Guards the P0-4 requirement: a network is NEVER represented as limited-live
eligible merely because its code exists or an RPC is configured. Deterministic +
offline (no RPC, no signing, no broadcast, no Mongo). Logically separate from
P0-3 and the gas-model seam.
"""
from __future__ import annotations

import os

import pytest

from arbicore.runtime import multichain_readiness as mr

# Env hygiene: the cert→provider RPC sync mutates os.environ directly (so the
# provider registry actually consumes the endpoint). Clean every RPC-related key
# + the sync sentinel before AND after each test so a synced value cannot leak.
_SYNC_KEYS = ["ARBICORE_RPC_URL", "ARBICORE_PROVIDER_RPC_SYNCED"]
for _c in ("BASE", "ETHEREUM", "ARBITRUM", "OPTIMISM", "POLYGON", "BNB"):
    _SYNC_KEYS += [f"ARBICORE_RPC_URL_{_c}", f"PROVIDER_RPC_URL_{_c}",
                   f"PROVIDER_RPC_URLS_{_c}", f"{_c}_RPC_URL"]


@pytest.fixture(autouse=True)
def _clean_rpc_env():
    saved = {k: os.environ.pop(k, None) for k in _SYNC_KEYS}
    yield
    for k in _SYNC_KEYS:
        os.environ.pop(k, None)
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v

_RPC_ENV_KEYS_BASE = ("PROVIDER_RPC_URLS_BASE", "PROVIDER_RPC_URL_BASE",
                      "ARBICORE_RPC_URL_BASE")


def test_supported_networks_are_multichain_not_base_only():
    nets = mr.supported_networks()
    assert "base" in nets
    # Multi-network is preserved — not narrowed to Base.
    for c in ("arbitrum", "bnb", "ethereum", "optimism", "polygon"):
        assert c in nets, c
    assert len(nets) >= 6


def test_report_shape_and_safety_envelope():
    rep = mr.build_multichain_readiness_report()
    assert rep["safety"] == {
        "posture": "SHADOW / detection-only / fail-closed",
        "signed": False, "broadcast": False, "limited_live_enabled": False,
    }
    assert rep["summary"]["limited_live_eligible_count"] == 0
    assert set(rep["networks"]) == set(mr.supported_networks())
    for chain, r in rep["networks"].items():
        assert r["limited_live_eligible"] is False, chain
        for dim in ("discovery", "quoting", "liquidity_tvl", "verification",
                    "simulation", "economic_eligibility"):
            assert dim in r, (chain, dim)
        assert r["blocker"]                     # always an explicit blocker


def test_no_network_is_limited_live_eligible_from_code_or_config():
    rep = mr.build_multichain_readiness_report()
    assert all(r["limited_live_eligible"] is False
               for r in rep["networks"].values())


def test_base_discovery_universe_is_canonical_resolved():
    rep = mr.build_multichain_readiness_report()
    base = rep["networks"]["base"]
    assert base["discovery"]["route_universe_size"] == 19  # offline canonical


def test_unconfigured_rpc_blocks_with_exact_reason(monkeypatch):
    for k in _RPC_ENV_KEYS_BASE + ("BASE_RPC_URL",):
        monkeypatch.delenv(k, raising=False)
    rep = mr.build_multichain_readiness_report()
    base = rep["networks"]["base"]
    assert base["rpc_configured"] is False
    assert base["blocker"] == "no_operator_configured_rpc"
    assert base["economic_eligibility"]["status"] == "blocked"


def test_arbicore_rpc_url_base_alone_opens_economic_gate_via_sync(monkeypatch):
    # CORRECTED CONTRACT: ARBICORE_RPC_URL_<CHAIN> is the single canonical cert
    # input; it is deterministically SYNCED into PROVIDER_RPC_URL_<CHAIN>, so one
    # operator endpoint satisfies BOTH the discovery seam AND the economic gate.
    for k in ("PROVIDER_RPC_URLS_BASE", "PROVIDER_RPC_URL_BASE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://base.example.operator")
    from arbicore.searcher.base_all_in_cost import base_rpc_explicitly_configured
    assert base_rpc_explicitly_configured() is True        # economic gate OPEN via sync
    base = mr.build_multichain_readiness_report()["networks"]["base"]
    assert base["rpc_configured"] is True                  # discovery-level yes
    assert base["economic_rpc_configured"] is True         # synced ⇒ economic yes
    assert base["economic_eligibility"]["status"] == "eligible_pending_runtime"
    assert base["blocker"] == "requires_vps_runtime_proof_and_admin_approval"
    assert base["limited_live_eligible"] is False          # still never auto-eligible


def test_arbicore_rpc_url_base_does_not_leak_to_non_base(monkeypatch):
    # The base-only endpoint must NOT open the economic gate for any other chain.
    for c in ("BASE", "ETHEREUM", "ARBITRUM", "OPTIMISM", "POLYGON", "BNB"):
        for k in (f"PROVIDER_RPC_URLS_{c}", f"PROVIDER_RPC_URL_{c}",
                  f"ARBICORE_RPC_URL_{c}", f"{c}_RPC_URL"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://base.example.operator")
    rep = mr.build_multichain_readiness_report()["networks"]
    assert rep["base"]["economic_rpc_configured"] is True
    for chain in ("ethereum", "arbitrum", "optimism", "polygon", "bnb"):
        assert rep[chain]["economic_rpc_configured"] is False   # no Base leakage


def test_configured_rpc_advances_blocker_to_runtime_proof(monkeypatch):
    monkeypatch.setenv("PROVIDER_RPC_URL_BASE", "https://base.example.operator")
    rep = mr.build_multichain_readiness_report()
    base = rep["networks"]["base"]
    assert base["rpc_configured"] is True
    assert base["economic_rpc_configured"] is True
    # Gas model exists for base + universe non-empty => the ONLY remaining
    # blocker is the genuine runtime proof (never auto-eligible).
    assert base["blocker"] == "requires_vps_runtime_proof_and_admin_approval"
    assert base["limited_live_eligible"] is False
    assert base["economic_eligibility"]["status"] == "eligible_pending_runtime"


def test_public_default_does_not_flip_eligibility(monkeypatch):
    # Even with a configured RPC, eligibility stays False (no runtime proof).
    monkeypatch.setenv("PROVIDER_RPC_URL_BASE", "https://mainnet.base.org")
    rep = mr.build_multichain_readiness_report()
    assert rep["networks"]["base"]["limited_live_eligible"] is False
    assert rep["summary"]["limited_live_eligible_count"] == 0
