"""D-3.6B controlled REAL-NETWORK smoke — Base · Aerodrome classic + SlipStream.

Proves both Aerodrome pool families return an ACTUAL on-chain quote through the
canonical QuoterRegistry backends, and that the wired dex="aerodrome" quoter
picks the best valid amountOut with backend provenance. READ-ONLY (eth_call
only) — no signing, no broadcast, no Limited-Live. Auto-skips without a Base RPC.
"""
from __future__ import annotations

import asyncio

import pytest

from arbicore.config.persistent import resolve_rpc_url_from_env
from arbicore.discovery import base_venues as bv
from arbicore.execution.quoter import QuoterRegistry
from arbicore.scanners.dex_arbitrage.quoter import EVMV3Quoter

_RPC = resolve_rpc_url_from_env("base")

pytestmark = pytest.mark.skipif(
    not _RPC,
    reason="no Base RPC configured (set ARBICORE_RPC_URL_BASE to run the live smoke)")


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_live_aerodrome_classic_weth_usdc():
    reg = QuoterRegistry()
    # WETH -> USDC classic (volatile) via Router.getAmountsOut.
    rq = _run(reg.quote_route(chain="base", hops=[{
        "dex": "aerodrome", "token_in": bv.token_address("WETH"),
        "token_out": bv.token_address("USDC"),
        "amount_in_wei": int(bv.probe_amount("WETH")), "stable": False}]))
    assert rq.status == "ok", f"classic quote status={rq.status}"
    assert int(rq.final_amount_out_wei) > 0


def test_live_aerodrome_slipstream_weth_usdc():
    reg = QuoterRegistry()
    rq = _run(reg.quote_route(chain="base", hops=[{
        "dex": "aerodrome_slipstream", "token_in": bv.token_address("WETH"),
        "token_out": bv.token_address("USDC"),
        "amount_in_wei": int(bv.probe_amount("WETH")), "tick_spacing": 100}]))
    assert rq.status == "ok", f"slipstream quote status={rq.status}"
    assert int(rq.final_amount_out_wei) > 0


def test_live_wired_aerodrome_quoter_best_of_both():
    q = EVMV3Quoter(chain="base", dex="aerodrome",
                    source_id="aerodrome_quoter_base")
    assert q.credentials_available is True
    res = _run(q.quote(pair_canonical="WETH/USDC", size_in_usd=1000.0,
                       direction="buy"))
    assert res.ok is True, f"aerodrome quote failed: {res.reason}"
    assert res.token_in == "USDC" and res.token_out == "WETH"
    assert res.amount_out and res.amount_out > 0
    assert res.raw["winning_backend"] in ("aerodrome_classic", "aerodrome_slipstream")
    assert isinstance(res.raw.get("block_number"), int)
    # provenance records every backend attempt
    assert res.raw["backend_attempts"]
    implied_weth_usd = 1.0 / res.effective_price
    assert 200.0 < implied_weth_usd < 100_000.0
