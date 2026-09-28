"""SP-1 — UniV3 QuoterV2 adapter generalized to the six canonical chains.

Scope (isolated, offline): verify the ADDRESS-AWARENESS + FAIL-CLOSED contract of
``UniV3QuoterV2._CONTRACT_BY_CHAIN`` only. No RPC, no eth_call, no execution,
no signing/broadcast, no threshold/readiness change.

RUNTIME-VERIFICATION-PENDING: these tests do NOT prove live quoting on any
non-Base chain — a real per-chain eth_call round-trip (Codex/VPS) is required
for that. Here we only assert the adapter now KNOWS the canonical QuoterV2
address per chain and still fails closed for unknown/unconfigured chains.
"""
from __future__ import annotations

import pytest

from arbicore.execution.quoter import (
    UniV3QuoterV2,
    UNIV3_QUOTER_V2_CANONICAL,
    BNB_UNIV3_QUOTER_V2,
    BASE_UNIV3_QUOTER_V2,
    BASE_SEPOLIA_UNIV3_QUOTER_V2,
)

CANONICAL_SIX = ("ethereum", "arbitrum", "base", "optimism", "polygon", "bnb")


def test_all_six_canonical_chains_are_address_aware():
    m = UniV3QuoterV2._CONTRACT_BY_CHAIN
    for chain in CANONICAL_SIX:
        assert chain in m, f"{chain} missing from UniV3 QuoterV2 map"
        assert isinstance(m[chain], str) and m[chain].startswith("0x")


def test_base_behavior_unchanged():
    """Regression: the runtime-verified Base + Base-Sepolia addresses are intact."""
    m = UniV3QuoterV2._CONTRACT_BY_CHAIN
    assert m["base"] == BASE_UNIV3_QUOTER_V2
    assert m["base-sepolia"] == BASE_SEPOLIA_UNIV3_QUOTER_V2


def test_canonical_quoterv2_shared_deployment():
    """Ethereum/Arbitrum/Optimism/Polygon share the deterministic QuoterV2 addr."""
    m = UniV3QuoterV2._CONTRACT_BY_CHAIN
    for chain in ("ethereum", "arbitrum", "optimism", "polygon"):
        assert m[chain] == UNIV3_QUOTER_V2_CANONICAL


def test_bnb_uses_its_own_deployment():
    m = UniV3QuoterV2._CONTRACT_BY_CHAIN
    assert m["bnb"] == BNB_UNIV3_QUOTER_V2
    assert m["bnb"] != UNIV3_QUOTER_V2_CANONICAL


def test_addresses_are_checksummed():
    from eth_utils import to_checksum_address
    for addr in set(UniV3QuoterV2._CONTRACT_BY_CHAIN.values()):
        assert addr == to_checksum_address(addr), f"{addr} not checksummed"


@pytest.mark.parametrize("unknown_chain", ["solana", "avalanche", "zksync", "", "BASE "])
def test_unknown_chain_absent_from_map(unknown_chain):
    """Fail-closed: unconfigured chains are NOT in the map (adapter returns the
    ``fallback:no_adapter`` HopQuote for them — asserted below without any RPC)."""
    assert unknown_chain not in UniV3QuoterV2._CONTRACT_BY_CHAIN


@pytest.mark.asyncio
@pytest.mark.parametrize("unknown_chain", ["solana", "avalanche", "zksync"])
async def test_unknown_chain_fails_closed(unknown_chain):
    """An unconfigured chain yields a fail-closed fallback quote (no fabricated
    amount_out, status != ok) WITHOUT any network call, because the contract
    lookup short-circuits before eth_call."""
    q = UniV3QuoterV2()
    hop = await q.quote_hop(
        hop_index=0, chain=unknown_chain,
        token_in="0x" + "11" * 20, token_out="0x" + "22" * 20,
        amount_in_wei=10**18, hop_spec={"fee": 3000}, rpc_url="http://unused.invalid",
    )
    assert hop.status != "ok"
    assert hop.amount_out_wei == 0
    assert "no_adapter" in (hop.error or "") or "no_adapter" in (hop.status or "")
