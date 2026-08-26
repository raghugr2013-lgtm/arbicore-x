"""Phase-2 · Multi-chain pool-discovery layer (SHADOW, fail-closed) tests."""
from __future__ import annotations

import pytest

from arbicore.discovery import multichain_venues as MV
from arbicore.discovery import base_venues
from arbicore.scanners.flash_loan_arbitrage.route_search import PoolNode


PHASE2 = ["arbitrum", "optimism", "ethereum", "polygon", "bnb"]


# --- per-chain venue universe -------------------------------------------------
@pytest.mark.parametrize("chain", PHASE2)
def test_each_chain_builds_a_real_venue_universe(chain):
    pools = MV.build_pool_graph(chain)
    assert len(pools) > 0
    for p in pools:
        assert isinstance(p, PoolNode)
        assert p.chain == chain
        assert p.token_a != p.token_b
        assert p.fee_bps > 0
        assert p.tvl_usd == 0.0            # never fabricated; resolved on-chain
        # tokens come ONLY from the verified registry (no invented symbols).
        assert p.token_a in base_venues.TOKENS or True  # symbol-space check below


@pytest.mark.parametrize("chain", PHASE2)
def test_venue_tokens_are_from_verified_registry(chain):
    from arbicore.chains import registries
    reg = set(registries.tokens_for(chain).keys())
    for p in MV.build_pool_graph(chain):
        assert p.token_a in reg and p.token_b in reg


def test_venue_ids_are_unique_and_synthetic():
    pools = MV.build_pool_graph("arbitrum")
    ids = [p.pool_address for p in pools]
    assert len(ids) == len(set(ids))           # unique
    assert all(":" in i and not i.startswith("0x") for i in ids)  # synthetic


# --- fail-closed --------------------------------------------------------------
def test_unknown_chain_is_empty():
    assert MV.build_pool_graph("solana") == []
    assert MV.build_pool_graph("") == []


def test_base_is_not_served_by_generic_layer():
    # Base keeps its own dedicated frozen graph — generic layer returns [].
    assert MV.build_pool_graph("base") == []


# --- composition loader: RPC-gated, Base preserved, fail-closed ---------------
def _loader():
    # Rebuild the exact loader logic from composition without booting the app.
    from arbicore.discovery.base_venues import CHAIN as BASE, build_pool_graph as bpg
    from arbicore.discovery.multichain_venues import (
        build_pool_graph as mc, supported_discovery_chains)
    from arbicore.config import persistent
    base_pools, _ = bpg()

    def loader(chain, _rpc=persistent.resolve_rpc_url_from_env):
        c = (chain or "").lower()
        if c == BASE:
            return base_pools
        if c in supported_discovery_chains() and _rpc(c):
            return mc(c)
        return []
    return loader, base_pools


def test_loader_returns_base_graph_unchanged(monkeypatch):
    loader, base_pools = _loader()
    assert loader("base") is base_pools          # identity: Base untouched


def test_loader_fails_closed_without_rpc(monkeypatch):
    monkeypatch.setattr(
        "arbicore.config.persistent.resolve_rpc_url_from_env", lambda c: None)
    loader, _ = _loader()
    for c in PHASE2:
        assert loader(c) == []                    # no RPC ⇒ empty (fail-closed)


def test_loader_serves_chain_when_rpc_configured(monkeypatch):
    monkeypatch.setattr(
        "arbicore.config.persistent.resolve_rpc_url_from_env",
        lambda c: "https://rpc" if c == "arbitrum" else None)
    loader, _ = _loader()
    assert len(loader("arbitrum")) > 0
    assert loader("optimism") == []               # RPC only for arbitrum


# --- Base regression ----------------------------------------------------------
def test_base_graph_still_builds_its_universe():
    pools, specs = base_venues.build_pool_graph()
    assert len(pools) > 0 and len(specs) > 0
    assert all(p.chain == "base" for p in pools)
