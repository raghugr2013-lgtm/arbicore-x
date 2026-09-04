"""Regression — multichain readiness gate (explicit, honest per-network status).

Guards the P0-4 requirement: a network is NEVER represented as limited-live
eligible merely because its code exists or an RPC is configured. Deterministic +
offline (no RPC, no signing, no broadcast, no Mongo). Logically separate from
P0-3 and the gas-model seam.
"""
from __future__ import annotations

from arbicore.runtime import multichain_readiness as mr

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


def test_arbicore_rpc_url_base_alone_does_not_open_economic_gate(monkeypatch):
    # ARBICORE_RPC_URL_BASE is a discovery-level operator key but is NOT synced
    # into the provider registry the all-in-cost gate uses. The report must be
    # HONEST: rpc_configured True, but economic gate blocked with the exact
    # reason — consistent with base_all_in_cost.base_rpc_explicitly_configured.
    for k in ("PROVIDER_RPC_URLS_BASE", "PROVIDER_RPC_URL_BASE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://base.example.operator")
    from arbicore.searcher.base_all_in_cost import base_rpc_explicitly_configured
    assert base_rpc_explicitly_configured() is False       # economic gate closed
    base = mr.build_multichain_readiness_report()["networks"]["base"]
    assert base["rpc_configured"] is True                  # discovery-level yes
    assert base["economic_rpc_configured"] is False
    assert base["economic_eligibility"]["status"] == "blocked"
    assert base["blocker"] == "economic_gate_rpc_not_configured"
    assert base["limited_live_eligible"] is False


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
