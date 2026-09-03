"""D-3.6A — Base · Uniswap V3 · QuoterV2 wiring for EVMV3Quoter.

Offline, deterministic tests. The on-chain eth_call is delegated to the
canonical QuoterRegistry/UniV3QuoterV2 backend; here we monkeypatch
QuoterRegistry.quote_route with a real-shaped RouteQuote so we exercise the
D-3.6A wiring (token resolution from the existing registry, fee-tier candidate
selection, best-output pick, DEXQuoteResult shape, fail-closed) with ZERO
network. The real-network proof lives in test_d3_6a_base_univ3_smoke.py.
"""
from __future__ import annotations

import asyncio

import pytest

from arbicore.scanners.dex_arbitrage.quoter import DEXQuoteResult, EVMV3Quoter
from arbicore.execution import quoter as execq


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _hop(*, token_in, token_out, amount_in_wei, amount_out_wei, block=27000000):
    return execq.HopQuote(
        hop_index=0, dex="uniswap_v3", token_in=token_in, token_out=token_out,
        amount_in_wei=int(amount_in_wei), amount_out_wei=int(amount_out_wei),
        sqrt_price_x96_after=123, gas_estimate_units=90000, price_impact_bps=None,
        quoter_contract=execq.BASE_UNIV3_QUOTER_V2, rpc_host="mainnet.base.org",
        block_number=block, status="ok", error=None, generated_at="2026-06-01T00:00:00Z")


def _route_ok(hop):
    return execq.RouteQuote(
        chain="base", hops=[hop], final_amount_out_wei=hop.amount_out_wei,
        aggregate_price_impact_bps=None, aggregate_gas_estimate_units=90000,
        status="ok", generated_at="2026-06-01T00:00:00Z", ttl_seconds=5)


def _route_fail():
    return execq.RouteQuote(
        chain="base", hops=[], final_amount_out_wei=0,
        aggregate_price_impact_bps=None, aggregate_gas_estimate_units=None,
        status="fallback:break_even", generated_at="2026-06-01T00:00:00Z",
        ttl_seconds=5)


def _clear_rpc(monkeypatch):
    for k in ("ARBICORE_RPC_URL_BASE", "ARBICORE_RPC_URL", "BASE_RPC_URL",
              "ALCHEMY_API_KEY"):
        monkeypatch.delenv(k, raising=False)


# ----- credentials / graceful-disable --------------------------------------

def test_base_univ3_enabled_by_base_rpc_env(monkeypatch):
    _clear_rpc(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://mainnet.base.org")
    q = EVMV3Quoter(chain="base", dex="uniswap_v3",
                    source_id="uniswap_v3_quoter_base")
    assert q.credentials_available is True


def test_base_univ3_disabled_when_no_rpc_and_no_key(monkeypatch):
    _clear_rpc(monkeypatch)
    q = EVMV3Quoter(chain="base", dex="uniswap_v3",
                    source_id="uniswap_v3_quoter_base")
    assert q.credentials_available is False
    res = _run(q.quote(pair_canonical="WETH/USDC", size_in_usd=1000.0))
    assert res.ok is False
    assert res.reason.startswith("credentials_missing:")


def test_non_base_evm_still_alchemy_gated(monkeypatch):
    # D-3.6A must NOT change behaviour for other chains/venues.
    _clear_rpc(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://mainnet.base.org")
    q = EVMV3Quoter(chain="ethereum", dex="uniswap_v3",
                    source_id="uniswap_v3_quoter_ethereum")
    # Base RPC set, but ethereum is not the wired path → falls back to ALCHEMY.
    assert q.credentials_available is False


# ----- live wiring (network delegated + monkeypatched) ----------------------

def test_buy_weth_usdc_returns_real_shaped_quote(monkeypatch):
    _clear_rpc(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://mainnet.base.org")
    seen_fees = []

    async def fake_quote_route(self, *, chain, hops, rpc_url=None):
        assert chain == "base"
        h = hops[0]
        assert h["dex"] == "uniswap_v3"
        fee = int(h["fee"]); seen_fees.append(fee)
        # amount_in is USDC (6dec) notional; out is WETH (18dec). Best @ fee 500.
        out = {500: 400_000_000_000_000_00, 3000: 390_000_000_000_000_00,
               10000: 300_000_000_000_000_00}[fee]
        return _route_ok(_hop(token_in=h["token_in"], token_out=h["token_out"],
                              amount_in_wei=h["amount_in_wei"], amount_out_wei=out))

    monkeypatch.setattr(execq.QuoterRegistry, "quote_route", fake_quote_route)
    q = EVMV3Quoter(chain="base", dex="uniswap_v3",
                    source_id="uniswap_v3_quoter_base")
    res = _run(q.quote(pair_canonical="WETH/USDC", size_in_usd=1000.0, direction="buy"))
    assert isinstance(res, DEXQuoteResult)
    assert res.ok is True and res.reason == ""
    # buy = spend USDC to acquire WETH
    assert res.token_in == "USDC" and res.token_out == "WETH"
    assert res.amount_in == 1000.0                        # USD-stable notional
    assert res.amount_out == pytest.approx(0.04)          # 4e16 wei / 1e18
    # effective_price is normalized QUOTE-per-BASE (USDC per WETH) = the ask.
    assert res.effective_price == pytest.approx(1000.0 / 0.04)
    assert res.fee_tier_bps == 5                          # best tier 500 ppm
    assert res.pool_address and res.pool_address.startswith("0x")
    assert res.raw["size_basis"] == "usd_stable_notional"
    assert res.raw["block_number"] == 27000000
    assert res.raw["quoter_contract"] == execq.BASE_UNIV3_QUOTER_V2
    assert set(seen_fees) == {500, 3000, 10000}           # all tiers probed


def test_sell_uses_probe_notional_for_non_stable_input(monkeypatch):
    _clear_rpc(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://mainnet.base.org")

    async def fake_quote_route(self, *, chain, hops, rpc_url=None):
        h = hops[0]
        return _route_ok(_hop(token_in=h["token_in"], token_out=h["token_out"],
                              amount_in_wei=h["amount_in_wei"],
                              amount_out_wei=125_000_000))  # USDC out (6dec)

    monkeypatch.setattr(execq.QuoterRegistry, "quote_route", fake_quote_route)
    q = EVMV3Quoter(chain="base", dex="uniswap_v3",
                    source_id="uniswap_v3_quoter_base")
    res = _run(q.quote(pair_canonical="WETH/USDC", size_in_usd=1000.0, direction="sell"))
    assert res.ok is True
    assert res.token_in == "WETH" and res.token_out == "USDC"
    assert res.raw["size_basis"] == "probe_notional_fallback"
    assert res.amount_out == pytest.approx(125.0)


def test_pair_with_chain_suffix_is_parsed(monkeypatch):
    _clear_rpc(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://mainnet.base.org")

    async def fake_quote_route(self, *, chain, hops, rpc_url=None):
        h = hops[0]
        return _route_ok(_hop(token_in=h["token_in"], token_out=h["token_out"],
                              amount_in_wei=h["amount_in_wei"],
                              amount_out_wei=40_000_000_000_000_000))

    monkeypatch.setattr(execq.QuoterRegistry, "quote_route", fake_quote_route)
    q = EVMV3Quoter(chain="base", dex="uniswap_v3",
                    source_id="uniswap_v3_quoter_base")
    res = _run(q.quote(pair_canonical="WETH/USDC@base", size_in_usd=500.0, direction="buy"))
    assert res.ok is True and res.token_out == "WETH"


def test_all_tiers_revert_fails_closed(monkeypatch):
    _clear_rpc(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://mainnet.base.org")

    async def fake_quote_route(self, *, chain, hops, rpc_url=None):
        return _route_fail()

    monkeypatch.setattr(execq.QuoterRegistry, "quote_route", fake_quote_route)
    q = EVMV3Quoter(chain="base", dex="uniswap_v3",
                    source_id="uniswap_v3_quoter_base")
    res = _run(q.quote(pair_canonical="WETH/USDC", size_in_usd=1000.0, direction="buy"))
    assert res.ok is False
    assert res.reason.startswith("quote_unavailable:")


def test_unknown_token_fails_closed(monkeypatch):
    _clear_rpc(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://mainnet.base.org")
    q = EVMV3Quoter(chain="base", dex="uniswap_v3",
                    source_id="uniswap_v3_quoter_base")
    res = _run(q.quote(pair_canonical="FOO/BAR", size_in_usd=1000.0, direction="buy"))
    assert res.ok is False and res.reason.startswith("unknown_token:")


def test_pair_without_univ3_pool_fails_closed(monkeypatch):
    # AERO/WETH has no deterministic-verified UniV3 pool in the Base registry
    # under this symbol orientation with a resolvable pair set → fail-closed.
    _clear_rpc(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://mainnet.base.org")
    q = EVMV3Quoter(chain="base", dex="uniswap_v3",
                    source_id="uniswap_v3_quoter_base")
    # DEGEN/USDC is not a UniV3 venue pair in the registry.
    res = _run(q.quote(pair_canonical="DEGEN/USDC", size_in_usd=1000.0, direction="buy"))
    assert res.ok is False
    assert res.reason.startswith("no_univ3_pool_for_pair:")


def test_other_base_venue_still_not_yet_wired(monkeypatch):
    _clear_rpc(monkeypatch)
    monkeypatch.setenv("ALCHEMY_API_KEY", "fake-key")
    q = EVMV3Quoter(chain="base", dex="pancake_v3",
                    source_id="pancake_v3_quoter_base")
    res = _run(q.quote(pair_canonical="WETH/USDC", size_in_usd=1000.0, direction="buy"))
    assert res.ok is False
    assert res.reason.startswith("not_yet_wired:")
