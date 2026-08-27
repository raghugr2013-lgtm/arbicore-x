"""Observability-only tests (audit 2026-08): precise DENY/TVL reasons.

Proves each failing input yields a DISTINCT diagnostic reason while STILL
failing closed (None), valid inputs are unchanged, and no synthetic value can
make either path pass. No behavioural/threshold change.
"""
from __future__ import annotations

import logging
import os
import pytest

from arbicore.searcher.v3_state import make_base_v3_reserves_fn
from arbicore.searcher.base_all_in_cost import (
    make_base_all_in_cost_estimator_from_env,
)

META = {"0xpool": ("USDC", "0xusdc", 6, "cbETH", "0xcbeth", 18)}


def _hex(n):  # ERC20 balanceOf return word
    return "0x" + f"{n:064x}"


# ---------- cbETH / UniV3 TVL reserves reasons ----------
@pytest.mark.asyncio
async def test_tvl_valid_path_unchanged():
    async def eth_call(addr, data):
        return _hex(1000 * 10**6) if addr == "0xusdc" else _hex(2 * 10**18)
    rf = make_base_v3_reserves_fn(eth_call, META)
    assert await rf("base", "0xpool") == ("USDC", 1000.0, "cbETH", 2.0)


@pytest.mark.asyncio
async def test_tvl_balanceof_token0_empty_reason(caplog):
    async def eth_call(addr, data):
        return None if addr == "0xusdc" else _hex(2 * 10**18)
    rf = make_base_v3_reserves_fn(eth_call, META)
    with caplog.at_level(logging.WARNING):
        assert await rf("base", "0xpool") is None
    assert "tvl_error=balanceOf_token0_empty" in caplog.text


@pytest.mark.asyncio
async def test_tvl_balanceof_token1_empty_reason(caplog):
    async def eth_call(addr, data):
        return _hex(10**6) if addr == "0xusdc" else None
    rf = make_base_v3_reserves_fn(eth_call, META)
    with caplog.at_level(logging.WARNING):
        assert await rf("base", "0xpool") is None
    assert "tvl_error=balanceOf_token1_empty" in caplog.text


@pytest.mark.asyncio
async def test_tvl_unknown_pool_metadata_reason(caplog):
    async def eth_call(addr, data):
        return _hex(1)
    rf = make_base_v3_reserves_fn(eth_call, META)
    with caplog.at_level(logging.WARNING):
        assert await rf("base", "0xUNKNOWN") is None  # not in meta, not in registry
    assert "tvl_error=pool_metadata_unresolved" in caplog.text


@pytest.mark.asyncio
async def test_tvl_nonpositive_reserves_reason(caplog):
    async def eth_call(addr, data):
        return _hex(0)
    rf = make_base_v3_reserves_fn(eth_call, META)
    with caplog.at_level(logging.WARNING):
        assert await rf("base", "0xpool") is None
    assert "tvl_error=nonpositive_reserves" in caplog.text


# ---------- M3 all-in cost deny reasons ----------
@pytest.mark.asyncio
async def test_all_in_eth_usd_and_gas_units_reasons(monkeypatch, caplog):
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "http://127.0.0.1:9")  # closed port
    est = make_base_all_in_cost_estimator_from_env()
    assert est is not None
    # eth_usd missing -> DENY with reason (returns before any RPC call)
    with caplog.at_level(logging.WARNING):
        r = await est(gross_profit_usd=100.0, borrow_amount_usd=10_000.0,
                      notional_usd=10_000.0, gas_units=800_000, eth_usd=None)
    assert r is None and "reason=eth_usd_unavailable" in caplog.text
    caplog.clear()
    # gas_units invalid -> distinct reason (still before RPC call)
    with caplog.at_level(logging.WARNING):
        r = await est(gross_profit_usd=100.0, borrow_amount_usd=10_000.0,
                      notional_usd=10_000.0, gas_units=0, eth_usd=2500.0)
    assert r is None and "reason=gas_units_invalid" in caplog.text
    caplog.clear()
    # valid eth_usd + gas_units, dummy RPC -> gas_price read fails -> distinct reason
    with caplog.at_level(logging.WARNING):
        r = await est(gross_profit_usd=100.0, borrow_amount_usd=10_000.0,
                      notional_usd=10_000.0, gas_units=800_000, eth_usd=2500.0)
    assert r is None and "reason=gas_price_read_failed" in caplog.text
