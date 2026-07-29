"""ArbiCore X — D-4 Subset D · Autonomous token-universe wiring tests.

Subset D wires ``token_universe_loader`` in ``composition.py`` so that
``HeliusWalletSource`` can emit candidates from a non-empty universe
sourced from recent ``LAUNCH_ARBITRAGE`` candidates in
``arbicore_discovery_candidates``.

These tests are pure substrate / static guards. They do NOT exercise
the live Mongo collection — that is observed through
``GET /api/arbicore/scanners/launch_arb/source-health`` after a real
boot window. Here we only enforce the static contract.

INV-1: the loader returns ``List[str]`` of mint addresses, never
       ``DiscoveryCandidate`` or ``CanonicalOpportunity``.
INV-2: the substrate never imports ``EmissionBus``.
INV-3: provenance is unchanged (universe is intelligence input only).
"""
from __future__ import annotations

import inspect

import pytest


def test_subset_d_loader_exists_and_callable():
    from arbicore.runtime import composition as c
    assert callable(c._token_universe_loader_sync)
    assert callable(c._refresh_token_universe_once)
    assert callable(c.get_token_universe_snapshot)


def test_subset_d_loader_returns_list_of_strings():
    from arbicore.runtime import composition as c
    # Force-set the cache to a known list of mints
    c._token_universe_cache = ["MintA111", "MintB222", "MintC333"]
    snap = c._token_universe_loader_sync()
    assert isinstance(snap, list)
    assert all(isinstance(m, str) for m in snap)
    assert snap == ["MintA111", "MintB222", "MintC333"]
    # Defensive copy: mutating the snapshot must not mutate the cache
    snap.clear()
    assert len(c._token_universe_cache) == 3
    # restore for other tests
    c._token_universe_cache = []


def test_subset_d_loader_default_is_empty_list():
    from arbicore.runtime import composition as c
    c._token_universe_cache = []
    assert c._token_universe_loader_sync() == []


def test_subset_d_scanner_factory_wires_real_loader():
    """The launch_arb scanner factory must NOT pass
    ``token_universe_loader=None`` — that was the Subset D regression
    behaviour. Catches re-introduction of the empty-stub during
    refactors."""
    from arbicore.runtime import composition as c
    src = inspect.getsource(c.get_launch_arb_scanner)
    assert "_token_universe_loader_sync" in src, (
        "get_launch_arb_scanner must wire _token_universe_loader_sync "
        "(Subset D regression guard)"
    )
    assert "token_universe_loader=None" not in src, (
        "get_launch_arb_scanner must NOT pass token_universe_loader=None "
        "(Subset D regression guard)"
    )


def test_subset_d_inv1_loader_returns_str_not_candidates():
    """INV-1: loader must return raw mint strings, not DiscoveryCandidate."""
    from arbicore.models.discovery import DiscoveryCandidate
    from arbicore.runtime import composition as c
    c._token_universe_cache = ["BareMintString"]
    out = c._token_universe_loader_sync()
    assert all(not isinstance(x, DiscoveryCandidate) for x in out)
    c._token_universe_cache = []


def test_subset_d_inv2_substrate_no_emission_bus():
    """INV-2: the Subset D helpers never import EmissionBus."""
    import arbicore.runtime.composition as mod
    src = inspect.getsource(mod._refresh_token_universe_once)
    assert "EmissionBus" not in src
    assert ".emit(" not in src
    src2 = inspect.getsource(mod._token_universe_loader_sync)
    assert "EmissionBus" not in src2
    assert ".emit(" not in src2


@pytest.mark.asyncio_compat   # marker (not enforced) — keep visible
def test_subset_d_refresh_handles_mongo_failure_gracefully():
    """``_refresh_token_universe_once`` swallows DB exceptions so a Mongo
    blip cannot crash the cache-refresh loop."""
    import asyncio
    from arbicore.runtime import composition as c
    # Replace _get_db with one that raises
    original_get_db = c._get_db

    def _broken_db():
        raise RuntimeError("simulated mongo failure")

    c._get_db = _broken_db   # type: ignore[assignment]
    try:
        c._token_universe_cache = ["KeepMeAlive"]
        # Must not raise
        asyncio.run(c._refresh_token_universe_once())
        # Cache preserved on failure
        assert c._token_universe_cache == ["KeepMeAlive"]
    finally:
        c._get_db = original_get_db   # type: ignore[assignment]
        c._token_universe_cache = []


def test_subset_d_constants_sensible():
    from arbicore.runtime import composition as c
    assert c._TOKEN_UNIVERSE_MAX > 0
    assert c._TOKEN_UNIVERSE_MAX <= 1000   # sanity ceiling
    assert c._TOKEN_UNIVERSE_LOOKBACK_S > 0
    # Lookback should match or be ≤ the arbicore_discovery_candidates TTL (24 h)
    assert c._TOKEN_UNIVERSE_LOOKBACK_S <= 24 * 3600
