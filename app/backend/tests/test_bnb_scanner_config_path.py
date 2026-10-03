"""BNB is a known flash-loan chain, and providers stay chain-scoped.

The persisted scanner document can omit ``chains.bnb``. The enable path
creates that one key from the code default and does not replace the other
chains, write an RPC URL, or flip scanner state. Provider flags stay
disabled in the defaults. Discovery pairs a provider only when the catalog
lists that chain. These tests do not write production Mongo and do not
resume the scanner.
"""
from __future__ import annotations

import asyncio
import inspect
import os

# composition reads MONGO_URL at import. A dummy URL lets this file import
# the config helpers offline. The tests never connect and never write.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_test")

import pytest
from fastapi import HTTPException

from arbicore.data.scanner_config_defaults import (
    DEFAULT_FLASH_LOAN_ARB_CONFIG, chain_config_patch,
)
from arbicore.runtime.composition import _deep_merge_cfg
from arbicore.scanners.flash_loan_arbitrage.activation_sources import (
    BalancerV2DiscoverySource, GenericDexDiscoverySource,
    TriangularDiscoverySource,
)
from arbicore.scanners.flash_loan_arbitrage.economics import (
    FLASH_LOAN_PROVIDERS, providers_for_chain,
)
from arbicore.scanners.flash_loan_arbitrage.route_search import (
    PoolNode, RouteSearchEngine,
)
from arbicore.scanners.flash_loan_arbitrage.scanner import FlashLoanArbitrageScanner
from arbicore.scanners.flash_loan_arbitrage.sources import RouteSearchDiscoverySource


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_defaults_keep_bnb_and_providers_disabled():
    chains = DEFAULT_FLASH_LOAN_ARB_CONFIG["chains"]
    assert "bnb" in chains
    assert chains["bnb"]["enabled"] is False
    assert chains["bnb"]["chain_id"] == 56
    assert chains["bnb"]["rpc_env_var"] == "BNB_RPC_URL"
    assert "rpc_url" not in chains["bnb"]
    providers = DEFAULT_FLASH_LOAN_ARB_CONFIG["providers"]
    assert providers["aave_v3"]["enabled"] is False
    assert providers["balancer_v2"]["enabled"] is False
    assert providers["uniswap_v3"]["enabled"] is False
    assert DEFAULT_FLASH_LOAN_ARB_CONFIG["route_search"]["min_pool_tvl_usd"] == 100_000


def test_missing_persisted_bnb_stays_disabled_in_the_merge():
    boot = {
        "chains": {
            "ethereum": {"enabled": False},
            "bnb": {"enabled": False, "chain_id": 56},
        },
        "route_search": {"min_pool_tvl_usd": 100_000},
    }
    persisted = {"chains": {"ethereum": {"enabled": True, "chain_id": 1}}}
    merged = _deep_merge_cfg(boot, persisted)
    assert merged["chains"]["bnb"]["enabled"] is False
    assert merged["chains"]["ethereum"]["enabled"] is True
    assert merged["route_search"]["min_pool_tvl_usd"] == 100_000


def test_chain_patch_adds_bnb_without_replacing_siblings():
    persisted = {"ethereum": {"enabled": True, "chain_id": 1,
                              "rpc_env_var": "ETH_RPC_URL"}}
    patch = chain_config_patch(persisted, "bnb", enabled=True)
    assert set(patch) == {"chains.bnb"}
    block = patch["chains.bnb"]
    assert block["enabled"] is True
    assert block["chain_id"] == 56
    assert block["gas_token"] == "BNB"
    assert block["rpc_env_var"] == "BNB_RPC_URL"
    assert "rpc_url" not in block
    assert persisted["ethereum"]["enabled"] is True
    with pytest.raises(KeyError):
        chain_config_patch(persisted, "solana", enabled=True)
    # The code default itself is unchanged.
    assert DEFAULT_FLASH_LOAN_ARB_CONFIG["chains"]["bnb"]["enabled"] is False


def test_enable_route_sets_only_the_missing_chain(monkeypatch):
    import arbicore.routes.scanners as routes

    class _Repo:
        def __init__(self):
            self.doc = {"chains": {"ethereum": {"enabled": True, "chain_id": 1}}}
            self.patch = None
            self.scanner_state_writes = 0

        async def get(self, scanner_id):
            assert scanner_id == "flash_loan_arb"
            return self.doc

        async def update(self, scanner_id, patch):
            assert scanner_id == "flash_loan_arb"
            self.patch = patch
            return {"updated": True}

        async def set_enabled(self, *_a, **_k):
            self.scanner_state_writes += 1

    repo = _Repo()
    monkeypatch.setattr(routes, "get_scanner_config_repo", lambda: repo)
    out = _run(routes.flash_loan_chain_enable("bnb"))
    assert out["updated"] is True
    assert set(repo.patch) == {"chains.bnb"}
    assert repo.patch["chains.bnb"]["enabled"] is True
    assert repo.doc["chains"]["ethereum"]["enabled"] is True
    assert repo.scanner_state_writes == 0
    with pytest.raises(HTTPException) as exc:
        _run(routes.flash_loan_chain_enable("solana"))
    assert exc.value.status_code == 404


def _pools(chain):
    return [
        PoolNode(f"uniswap_v3:USDC:WETH:500:{chain}", "uniswap_v3", chain,
                 "USDC", "WETH", 200_000.0, 5),
        PoolNode(f"uniswap_v3:USDC:WETH:3000:{chain}", "uniswap_v3", chain,
                 "USDC", "WETH", 200_000.0, 30),
    ]


def _engine(chain):
    engine = RouteSearchEngine(
        pool_loader=lambda c: _pools(chain) if c == chain else [])
    assert engine.min_pool_tvl_usd == 100_000.0
    return engine


def _cfg(chain, providers):
    return {
        "chains": {chain: {"enabled": True}},
        "providers": {name: {"enabled": on} for name, on in providers.items()},
        "discovery_sources": {
            "generic_dex": {"enabled": True},
            "triangular": {"enabled": True},
            "balancer_v2": {"enabled": True},
        },
    }


def test_disabled_providers_emit_no_candidates():
    cfg = _cfg("ethereum", {"aave_v3": False, "balancer_v2": False,
                            "uniswap_v3": False})
    engine = _engine("ethereum")
    loader = lambda: cfg
    assert _run(RouteSearchDiscoverySource(
        route_engine=engine, config_loader=loader).discover()) == []
    assert _run(GenericDexDiscoverySource(
        route_engine=engine, config_loader=loader).discover()) == []
    assert _run(TriangularDiscoverySource(
        route_engine=engine, config_loader=loader,
        borrow_token_set=["USDC"], intermediates=["WETH", "DAI"]).discover()) == []
    assert _run(BalancerV2DiscoverySource(
        route_engine=engine, config_loader=loader).discover()) == []


def test_bnb_is_not_labeled_with_a_provider_that_omits_it():
    assert providers_for_chain(
        "bnb", ["aave_v3", "balancer_v2", "uniswap_v3"]) == ["aave_v3"]
    assert "bnb" not in FLASH_LOAN_PROVIDERS["balancer_v2"]["supports_chains"]
    assert "bnb" not in FLASH_LOAN_PROVIDERS["uniswap_v3"]["supports_chains"]
    assert "bnb" in FLASH_LOAN_PROVIDERS["aave_v3"]["supports_chains"]

    cfg = _cfg("bnb", {"aave_v3": True, "balancer_v2": True, "uniswap_v3": True})
    engine = _engine("bnb")
    cands = _run(RouteSearchDiscoverySource(
        route_engine=engine, config_loader=lambda: cfg,
        borrow_token_set=["USDC"]).discover())
    assert cands
    assert {c.hint_metric["provider"] for c in cands} == {"aave_v3"}

    only_balancer = _cfg("bnb", {"aave_v3": False, "balancer_v2": True,
                                 "uniswap_v3": False})
    assert _run(RouteSearchDiscoverySource(
        route_engine=engine, config_loader=lambda: only_balancer,
        borrow_token_set=["USDC"]).discover()) == []


def test_ethereum_still_pairs_balancer_when_the_catalog_lists_it():
    cfg = _cfg("ethereum", {"balancer_v2": True, "aave_v3": False,
                            "uniswap_v3": False})
    cands = _run(RouteSearchDiscoverySource(
        route_engine=_engine("ethereum"), config_loader=lambda: cfg,
        borrow_token_set=["USDC"]).discover())
    assert cands
    assert {c.hint_metric["provider"] for c in cands} == {"balancer_v2"}


def test_tick_does_not_build_flash_calldata():
    src = inspect.getsource(FlashLoanArbitrageScanner._tick)
    assert "borrow_step" not in src
    assert "set_enabled" not in src
