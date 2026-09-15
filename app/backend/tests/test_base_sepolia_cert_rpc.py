"""Focused certification tests — Base Sepolia RPC resolution + chain-id isolation.

Covers the minimal cert-stack fix that lets the Phase-B receiver
bytecode/immutables check reach the operator's ``BASE_SEPOLIA_RPC_URL`` without
disturbing the working mainnet six-chain behaviour.

Pure / hermetic: only environment manipulation, NO network, NO signing, NO
broadcast. These prove RESOLUTION + ISOLATION, not any on-chain PASS.
"""
from arbicore.execution import quoter as q
from arbicore.certification import vps_harness as H


def _clear(monkeypatch, *keys):
    for k in keys:
        monkeypatch.delenv(k, raising=False)


def test_expected_chain_id_base_sepolia_strict():
    # Base Sepolia resolves strictly to 84532 (both name forms; case-insensitive).
    assert q._expected_chain_id("base-sepolia") == 84532
    assert q._expected_chain_id("base_sepolia") == 84532
    assert q._expected_chain_id("BASE_SEPOLIA") == 84532
    # Mainnet Base unchanged.
    assert q._expected_chain_id("base") == 8453


def test_receiver_chain_id_to_name_normalisation():
    # Numeric cert-target id -> canonical chain NAME used for RPC env resolution.
    assert H._rpc_chain_name("84532") == "base_sepolia"
    assert H._rpc_chain_name(84532) == "base_sepolia"
    assert H._rpc_chain_name("8453") == "base"
    # Already-named chains pass through (lower-cased); unknowns fail-closed later.
    assert H._rpc_chain_name("base") == "base"
    assert H._rpc_chain_name("ethereum") == "ethereum"


def test_base_sepolia_candidates_resolve_env(monkeypatch):
    _clear(monkeypatch, "ARBICORE_RPC_URL", "ARBICORE_RPC_URL_BASE",
           "ARBICORE_RPC_URL_BASE_SEPOLIA", "PROVIDER_RPC_URLS",
           "PROVIDER_RPC_URLS_BASE_SEPOLIA")
    monkeypatch.setenv("BASE_SEPOLIA_RPC_URL", "https://sepolia.example/rpc")
    reg = q.QuoterRegistry()
    # Directly by canonical name…
    assert "https://sepolia.example/rpc" in reg._rpc_url_candidates("base_sepolia")
    # …and via the numeric->name normalisation the harness applies.
    assert "https://sepolia.example/rpc" in reg._rpc_url_candidates(
        H._rpc_chain_name("84532"))


def test_no_base_mainnet_leakage_into_sepolia(monkeypatch):
    _clear(monkeypatch, "ARBICORE_RPC_URL_BASE_SEPOLIA",
           "PROVIDER_RPC_URLS_BASE_SEPOLIA")
    monkeypatch.setenv("ARBICORE_RPC_URL", "https://base-mainnet.example/rpc")
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://base.example/rpc")
    monkeypatch.setenv("BASE_SEPOLIA_RPC_URL", "https://sepolia.example/rpc")
    reg = q.QuoterRegistry()
    sep = reg._rpc_url_candidates("base_sepolia")
    # Base-mainnet global aliases + base-scoped endpoints NEVER leak into sepolia.
    assert sep == ["https://sepolia.example/rpc"]


def test_no_sepolia_leakage_into_base(monkeypatch):
    _clear(monkeypatch, "ARBICORE_RPC_URL", "PROVIDER_RPC_URLS")
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://base.example/rpc")
    monkeypatch.setenv("BASE_SEPOLIA_RPC_URL", "https://sepolia.example/rpc")
    reg = q.QuoterRegistry()
    base = reg._rpc_url_candidates("base")
    assert "https://base.example/rpc" in base
    assert "https://sepolia.example/rpc" not in base


def test_chain_id_isolation_distinct():
    assert q._expected_chain_id("base") != q._expected_chain_id("base_sepolia")
