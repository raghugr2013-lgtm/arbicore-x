"""D-3.6A controlled REAL-NETWORK smoke test — Base · Uniswap V3 · QuoterV2.

Proves the wired path can obtain an ACTUAL on-chain quote:
    Base → Uniswap V3 → QuoterV2 → eth_call → real amountOut → DEXQuoteResult

Skipped automatically unless a Base RPC is configured via the canonical
resolver (ARBICORE_RPC_URL_BASE / ARBICORE_RPC_URL / BASE_RPC_URL). READ-ONLY:
issues eth_call only — never signs, never broadcasts. No Limited-Live.
"""
from __future__ import annotations

import asyncio

import pytest

from arbicore.config.persistent import resolve_rpc_url_from_env
from arbicore.scanners.dex_arbitrage.quoter import EVMV3Quoter

_RPC = resolve_rpc_url_from_env("base")

pytestmark = pytest.mark.skipif(
    not _RPC,
    reason="no Base RPC configured (set ARBICORE_RPC_URL_BASE to run the live smoke)")


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_live_base_univ3_weth_usdc_buy_quote():
    q = EVMV3Quoter(chain="base", dex="uniswap_v3",
                    source_id="uniswap_v3_quoter_base")
    assert q.credentials_available is True
    res = _run(q.quote(pair_canonical="WETH/USDC", size_in_usd=1000.0,
                       direction="buy"))
    assert res.ok is True, f"live quote failed: {res.reason}"
    assert res.token_in == "USDC" and res.token_out == "WETH"
    assert res.amount_out and res.amount_out > 0
    assert res.effective_price and res.effective_price > 0
    assert res.fee_tier_bps in (1, 5, 30, 100)
    assert res.pool_address and res.pool_address.startswith("0x")
    assert isinstance(res.raw.get("block_number"), int)
    assert res.raw.get("route_status") == "ok"
    # effective_price is normalized QUOTE-per-BASE (USDC per WETH), plausible band.
    implied_weth_usd = res.effective_price
    assert 200.0 < implied_weth_usd < 100_000.0
