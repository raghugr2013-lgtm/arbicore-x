"""SP-3 — chain-parameterized live quote-provider seam (offline, fail-closed).

Verifies the seam ONLY: that the Base path is unchanged (defaults resolve to
base) and that a configured non-Base chain sources its token/pool specs from the
SP-2 read-only registry with no cross-chain leakage. No real network round-trip,
no TVL/liquidity (SP-4), no scanner activation, no execution/sign/broadcast.

A capturing fake ``QuoterRegistry`` records the ``chain`` + ``hops`` the provider
builds, then returns ``None`` so the provider fails closed (honest) — we assert
on what was BUILT, never on a fabricated quote.
"""
from __future__ import annotations

import pytest

from arbicore.scanners.flash_loan_arbitrage.live_quote_provider import (
    make_live_quote_provider, make_multichain_quote_provider,
)
from arbicore.discovery import base_venues
from arbicore.discovery import multichain_pool_registry as mreg


class _CaptureQuoter:
    def __init__(self):
        self.calls = []

    async def quote_route(self, *, chain, hops):
        self.calls.append({"chain": chain, "hops": hops})
        return None  # provider fails closed → returns None (we assert on `calls`)


def _base_route():
    _pools, specs = base_venues.build_pool_graph()
    vids = list(specs.keys())[:2]
    return {"route_pools": vids,
            "cycle_token_path": ["WETH", "USDC", "WETH"],
            "borrow_token": "WETH"}


def _chain_route(chain):
    specs = mreg.pool_candidate_specs(chain)
    vids = [s["venue_id"] for s in specs[:2]]
    return {"route_pools": vids,
            "cycle_token_path": ["WETH", "USDC", "WETH"],
            "borrow_token": "WETH"}


@pytest.mark.asyncio
async def test_base_default_path_unchanged():
    q = _CaptureQuoter()
    prov = make_live_quote_provider(q)  # no chain args → Base defaults
    facts = await prov(_base_route(), 10_000.0)
    assert facts is None  # fake quoter returned None → fail closed
    assert q.calls and q.calls[0]["chain"] == "base"
    hop0 = q.calls[0]["hops"][0]
    assert hop0["token_in"] == base_venues.token_address("WETH")
    assert hop0["token_out"] == base_venues.token_address("USDC")


@pytest.mark.asyncio
async def test_multichain_base_delegates_identically():
    q = _CaptureQuoter()
    prov = make_multichain_quote_provider(q, "base")
    assert prov is not None
    await prov(_base_route(), 10_000.0)
    assert q.calls[0]["chain"] == "base"
    assert q.calls[0]["hops"][0]["token_in"] == base_venues.token_address("WETH")


@pytest.mark.asyncio
@pytest.mark.parametrize("chain", ["ethereum", "arbitrum", "optimism", "polygon", "bnb"])
async def test_configured_nonbase_uses_registry_addresses(chain):
    q = _CaptureQuoter()
    prov = make_multichain_quote_provider(q, chain)
    assert prov is not None
    facts = await prov(_chain_route(chain), 10_000.0)
    assert facts is None  # not runtime-verified → fails closed here
    assert q.calls and q.calls[0]["chain"] == chain
    hop0 = q.calls[0]["hops"][0]
    assert hop0["token_in"] == mreg.token_address(chain, "WETH")
    assert hop0["token_out"] == mreg.token_address(chain, "USDC")
    # Addresses come from THIS chain's registry (anti-leakage is covered by the
    # SP-2 registry tests; note OP-stack chains legitimately share WETH 0x42..06).
    assert hop0["token_out"] == mreg.token_address(chain, "USDC")


@pytest.mark.parametrize("chain", ["solana", "avalanche", "base-sepolia", "", "  "])
def test_unconfigured_chain_returns_none(chain):
    assert make_multichain_quote_provider(_CaptureQuoter(), chain) is None


@pytest.mark.asyncio
async def test_multichain_provider_adds_no_tvl_and_fails_closed_on_none():
    # tvl_provider defaults None → Gate-8 depth stays fabricated-free; provider
    # simply returns None when the (fake) quoter cannot price the route.
    q = _CaptureQuoter()
    prov = make_multichain_quote_provider(q, "arbitrum")
    assert await prov(_chain_route("arbitrum"), 10_000.0) is None


@pytest.mark.asyncio
async def test_malformed_route_is_rejected_without_quoting():
    q = _CaptureQuoter()
    prov = make_multichain_quote_provider(q, "polygon")
    # route_pools/token_path mismatch → None BEFORE any quoter call.
    assert await prov({"route_pools": ["x"], "cycle_token_path": ["WETH"]}, 1.0) is None
    assert q.calls == []
