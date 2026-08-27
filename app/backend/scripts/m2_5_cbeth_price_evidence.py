#!/usr/bin/env python3
"""M2.5 cbETH pricing evidence — READ-ONLY, real Base RPC, NEVER signs.

Run INSIDE the VPS container (real ARBICORE_RPC_URL[_BASE] + ARBICORE_USD_NUMERAIRE):

    python -m scripts.m2_5_cbeth_price_evidence

Prices each token through the LIVE OnChainUsdPriceFeed (genuine on-chain quotes
via the real QuoterRegistry) and dumps full provenance so an operator can SEE:
  * WETH   → onchain_usdc_direct (control)
  * cbETH  → the direct cbETH/USDC pool quote FAILS (thin liquidity), and the
             feed FALLS THROUGH to the real two-hop cbETH→WETH→USDC route,
             yielding source=onchain_usdc_via_weth with a valid price, the
             resolving block and the chain head (freshness).
Fail-closed is preserved: if BOTH real routes fail, price_usd is null.

This is the live counterpart to tests/test_m2_5_price_feed.py
(test_cbeth_direct_quote_fails_falls_through_to_two_hop).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

TOKENS = ("USDC", "WETH", "cbETH")


async def main() -> None:
    from arbicore.searcher.price_feed import (
        build_base_price_feed_from_env, m2_5_enabled)

    out: dict = {
        "env": {
            "ARBICORE_USD_NUMERAIRE": os.environ.get("ARBICORE_USD_NUMERAIRE"),
            "rpc_configured": bool(
                os.environ.get("ARBICORE_RPC_URL")
                or os.environ.get("ARBICORE_RPC_URL_BASE")),
        },
        "m2_5_enabled": m2_5_enabled(),
        "prices": {},
        "provenance": [],
    }

    feed = build_base_price_feed_from_env()
    if feed is None:
        out["error"] = ("price feed not constructed — set ARBICORE_USD_NUMERAIRE "
                        "and a Base RPC (ARBICORE_RPC_URL / ARBICORE_RPC_URL_BASE)")
        print(json.dumps(out, indent=2, default=str))
        sys.exit(2)

    head = None
    try:
        head = await feed._head_block()
    except Exception as exc:  # noqa: BLE001
        head = f"ERROR {type(exc).__name__}: {exc}"
    out["chain_head_block"] = head

    for sym in TOKENS:
        try:
            out["prices"][sym] = await feed.price_source(sym)
        except Exception as exc:  # noqa: BLE001
            out["prices"][sym] = f"ERROR {type(exc).__name__}: {exc}"

    out["provenance"] = feed.provenance_for(list(TOKENS))

    # Operator verdict — the exact acceptance criteria you asked for.
    prov = {p["token"]: p for p in out["provenance"]}
    cb = prov.get("CBETH", {})
    weth = prov.get("WETH", {})
    out["verdict"] = {
        "weth_direct_ok": (weth.get("source") == "onchain_usdc_direct"
                           and weth.get("status") == "ok"
                           and out["prices"].get("WETH") is not None),
        "cbeth_priced_via_two_hop": (
            cb.get("source") == "onchain_usdc_via_weth"
            and cb.get("status") == "ok"
            and out["prices"].get("cbETH") is not None),
        "cbeth_path": cb.get("path"),
        "cbeth_pools": cb.get("pools"),
        "cbeth_block": cb.get("block"),
        "cbeth_head_block": cb.get("head_block"),
        "cbeth_fresh": (isinstance(cb.get("block"), int)
                        and isinstance(cb.get("head_block"), int)),
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
