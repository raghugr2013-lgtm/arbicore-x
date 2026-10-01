"""SP-2 — multichain pool-spec / token-address registry (offline, fail-closed).

No RPC, no eth_call, no execution/signing/broadcast, no thresholds/readiness, no
TVL/liquidity, no live quote wiring. Verifies the explicit + fail-closed contract
of ``discovery/multichain_pool_registry.py`` only.
"""
from __future__ import annotations

import inspect

import pytest

from arbicore.discovery import multichain_pool_registry as reg
from arbicore.discovery import base_venues
from arbicore.chains import registries

SIX = ("ethereum", "arbitrum", "base", "optimism", "polygon", "bnb")


def test_all_six_canonical_chains_configured():
    assert reg.configured_chains() == sorted(SIX)
    for c in SIX:
        assert reg.is_chain_configured(c)
        assert reg.chain_state(c) == reg.CONFIGURED


def test_base_regression_delegates_to_base_venues():
    # Token addresses + decimals must match base_venues EXACTLY (delegated).
    for sym, meta in base_venues.TOKENS.items():
        assert reg.token_address("base", sym) == meta["address"]
        assert reg.token_spec("base", sym)["decimals"] == meta["decimals"]
    # Base mixed-case handling preserved (cbETH not upper-cased).
    assert reg.token_address("base", "cbeth") == base_venues.TOKENS["cbETH"]["address"]
    # Base pool candidate specs come straight from the curated venue graph.
    _pools, specs = base_venues.build_pool_graph()
    assert len(reg.pool_candidate_specs("base")) == len(specs)


def test_base_sepolia_regression_known_but_no_registry():
    assert reg.chain_state("base-sepolia") == reg.KNOWN_NO_REGISTRY
    assert reg.is_chain_configured("base-sepolia") is False
    assert reg.tokens("base-sepolia") == {}
    assert reg.token_address("base-sepolia", "WETH") is None
    assert reg.pool_candidate_specs("base-sepolia") == []


@pytest.mark.parametrize("chain", ["ethereum", "arbitrum", "optimism", "polygon", "bnb"])
def test_configured_chain_returns_registered_spec(chain):
    toks = reg.tokens(chain)
    assert toks, f"{chain} should have registered tokens"
    # Every token address must match the verified registries constant exactly.
    for sym, meta in registries.tokens_for(chain).items():
        assert reg.token_address(chain, sym) == meta["address"]
    # DEX factory specs are the verified registries constants.
    assert reg.dex_specs(chain) == [dict(d) for d in registries.dexes_for(chain)]


@pytest.mark.parametrize("chain", ["solana", "avalanche", "zksync", "", "  ", "ETHEREUM_TYPO"])
def test_unknown_or_unconfigured_chain_fails_closed(chain):
    assert reg.chain_state(chain) in (reg.UNCONFIGURED,)
    assert reg.is_chain_configured(chain) is False
    assert reg.tokens(chain) == {}
    assert reg.token_address(chain, "WETH") is None
    assert reg.token_spec(chain, "WETH") is None
    assert reg.dex_specs(chain) == []
    assert reg.pool_candidate_specs(chain) == []


def test_no_fabricated_fallback_address():
    # A symbol absent on a configured chain returns None (never a guess).
    assert reg.token_address("bnb", "AERO") is None          # AERO is Base-only
    assert reg.token_address("ethereum", "WBNB") is None      # WBNB is BNB-only
    assert reg.token_spec("polygon", "NON_EXISTENT_TOKEN") is None


def test_no_cross_chain_address_leakage():
    # Base-only symbols must not resolve on other chains.
    assert reg.token_address("arbitrum", "cbETH") is None
    assert reg.token_address("optimism", "AERO") is None
    # ARB (arbitrum) must not leak onto ethereum/base.
    assert reg.token_address("ethereum", "ARB") is None
    assert reg.token_address("base", "ARB") is None
    # Same symbol, different chains → chain-specific addresses (no shared blob).
    weth = {c: reg.token_address(c, "WETH") for c in SIX}
    assert weth["ethereum"] != weth["arbitrum"] != weth["optimism"]
    assert weth["base"] == base_venues.TOKENS["WETH"]["address"]


def test_pool_specs_never_expose_a_concrete_pool_address():
    for chain in SIX:
        for spec in reg.pool_candidate_specs(chain):
            assert spec["pool_contract_address"] is None
            assert spec["resolution"] == "onchain_pending"


def test_provenance_is_explicit_and_not_runtime_verified():
    p = reg.provenance("arbitrum")
    assert p["state"] == reg.CONFIGURED and p["configured"] is True
    assert p["runtime_verified"] is False
    assert p["pool_address_status"] == "onchain_pending"
    u = reg.provenance("solana")
    assert u["state"] == reg.UNCONFIGURED and u["configured"] is False
    assert u["pool_address_status"] == "unavailable"


def test_registry_initiates_no_rpc():
    """The registry must be pure/offline: no network client is imported and no
    RPC/eth_call name is USED in code (docstrings excluded via AST), and its
    public accessors are synchronous (not coroutines)."""
    import ast
    tree = ast.parse(inspect.getsource(reg))
    imported = set()
    used_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
        elif isinstance(node, ast.Name):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            used_names.add(node.attr)
    assert not ({"httpx", "aiohttp", "requests"} & imported), imported
    for forbidden in ("eth_call", "AsyncClient"):
        assert forbidden not in used_names, f"registry code references {forbidden}"
    for fn in (reg.tokens, reg.token_address, reg.token_spec, reg.dex_specs,
               reg.pool_candidate_specs, reg.chain_state, reg.provenance):
        assert not inspect.iscoroutinefunction(fn)


def test_does_not_read_provider_rpc_env(monkeypatch):
    """Provider precedence / PROVIDER_RPC_URL[S]_<CHAIN> semantics are untouched:
    registry results do not depend on those env vars."""
    monkeypatch.setenv("PROVIDER_RPC_URL_ARBITRUM", "https://should-be-ignored")
    monkeypatch.setenv("PROVIDER_RPC_URLS_ARBITRUM", "https://a,https://b")
    before = reg.tokens("arbitrum")
    monkeypatch.delenv("PROVIDER_RPC_URL_ARBITRUM", raising=False)
    monkeypatch.delenv("PROVIDER_RPC_URLS_ARBITRUM", raising=False)
    after = reg.tokens("arbitrum")
    assert before == after
