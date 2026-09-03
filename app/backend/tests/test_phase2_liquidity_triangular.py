"""Phase-2 Steps 2/3 — provider liquidity feasibility + triangular discovery.

Offline, deterministic, fail-closed. No network (fake provider / injected quote
function). Live on-chain reads are exercised separately by the VPS harness.
"""
from __future__ import annotations

import asyncio

import pytest

from arbicore.models.enums import StrategyType
from arbicore.scanners.flash_loan_arbitrage import provider_liquidity as PL
from arbicore.scanners.flash_loan_arbitrage.provider_liquidity import (
    ProviderStatus, decode_atoken_from_reserve_data,
)
from arbicore.scanners.flash_loan_arbitrage.triangular import (
    enumerate_cycles, evaluate_cycle, discover_triangular,
)


# ---------------------------------------------------------------------------
# Step 2 — provider liquidity status ladder (never assume capacity)
# ---------------------------------------------------------------------------
class _FakeRpc:
    """Programmable eth_call / eth_getCode fake."""

    def __init__(self, *, code=True, balances=None, reserve_atoken=None):
        self._code = code
        self._balances = balances or {}
        self._atoken = reserve_atoken

    async def _call(self, method, params):
        if method == "eth_getCode":
            if self._code is None:
                raise RuntimeError("rpc down")
            return "0x60006000" if self._code else "0x"
        raise RuntimeError("unexpected")

    async def eth_call(self, tx, block="latest"):
        data = tx["data"]
        if data.startswith(PL.SEL_GET_RESERVE_DATA):
            if self._atoken is None:
                return "0x" + "00" * 32
            body = ["00" * 32] * 9
            body[8] = self._atoken.lower().replace("0x", "").rjust(64, "0")
            return "0x" + "".join(body)
        if data.startswith(PL.SEL_BALANCE_OF):
            holder = "0x" + data[-40:]
            bal = self._balances.get(holder.lower())
            if bal is None:
                raise RuntimeError("balance read failed")
            return hex(bal)
        return "0x"


def test_balancer_confirmed_when_liquidity_covers_borrow():
    vault = PL.BALANCER_V2_VAULT.lower()
    rpc = _FakeRpc(balances={vault: 100 * 10**18})  # 100 WETH
    r = asyncio.run(PL.read_balancer_liquidity(
        rpc, chain="arbitrum", token_address="0xWETH", token_decimals=18,
        token_price_usd=3000.0, borrow_amount_usd=50_000.0))
    assert r.status == ProviderStatus.ON_CHAIN_CONFIRMED
    assert r.liquidity_usd == pytest.approx(300_000.0)
    assert r.fee_bps == 0                                   # verified 0-bps
    assert r.feasible_usd == pytest.approx(300_000.0)


def test_balancer_unavailable_when_liquidity_below_borrow():
    vault = PL.BALANCER_V2_VAULT.lower()
    rpc = _FakeRpc(balances={vault: 1 * 10**18})           # 1 WETH = $3k
    r = asyncio.run(PL.read_balancer_liquidity(
        rpc, chain="arbitrum", token_address="0xWETH", token_decimals=18,
        token_price_usd=3000.0, borrow_amount_usd=50_000.0))
    assert r.status == ProviderStatus.UNAVAILABLE
    assert r.reason == "insufficient_liquidity"
    assert r.feasible_usd is None                          # fail-closed


def test_balancer_unknown_when_contract_missing():
    r = asyncio.run(PL.read_balancer_liquidity(
        _FakeRpc(code=False), chain="bnb", token_address="0xWETH",
        token_decimals=18, token_price_usd=3000.0, borrow_amount_usd=50_000.0))
    assert r.status == ProviderStatus.UNAVAILABLE
    assert r.reason == "vault_not_deployed_on_chain"


def test_balancer_unknown_when_rpc_down():
    r = asyncio.run(PL.read_balancer_liquidity(
        _FakeRpc(code=None), chain="arbitrum", token_address="0xWETH",
        token_decimals=18, token_price_usd=3000.0, borrow_amount_usd=50_000.0))
    assert r.status == ProviderStatus.UNKNOWN         # fail-closed, not assumed


def test_balancer_unknown_when_price_missing():
    vault = PL.BALANCER_V2_VAULT.lower()
    rpc = _FakeRpc(balances={vault: 100 * 10**18})
    r = asyncio.run(PL.read_balancer_liquidity(
        rpc, chain="arbitrum", token_address="0xWETH", token_decimals=18,
        token_price_usd=None, borrow_amount_usd=50_000.0))
    assert r.status == ProviderStatus.UNKNOWN
    assert r.reason == "token_price_unavailable"


def test_aave_reads_atoken_then_confirms_liquidity():
    atoken = "0x1111111111111111111111111111111111111111"
    rpc = _FakeRpc(reserve_atoken=atoken,
                   balances={atoken: 10_000 * 10**18})     # 10k WETH
    r = asyncio.run(PL.read_aave_liquidity(
        rpc, chain="arbitrum", token_address="0xWETH", token_decimals=18,
        token_price_usd=3000.0, borrow_amount_usd=50_000.0))
    assert r.status == ProviderStatus.ON_CHAIN_CONFIRMED
    assert r.source_address == atoken
    assert r.fee_bps == 5


def test_aave_unavailable_when_reserve_not_listed():
    rpc = _FakeRpc(reserve_atoken=None)
    r = asyncio.run(PL.read_aave_liquidity(
        rpc, chain="bnb", token_address="0xWETH", token_decimals=18,
        token_price_usd=3000.0, borrow_amount_usd=50_000.0))
    assert r.status == ProviderStatus.UNAVAILABLE
    assert r.reason == "reserve_not_listed"


def test_decode_atoken_offset():
    atoken = "0xabcabcabcabcabcabcabcabcabcabcabcabcabca"
    body = ["00" * 32] * 9
    body[8] = atoken.lower().replace("0x", "").rjust(64, "0")
    raw = "0x" + "".join(body)
    assert decode_atoken_from_reserve_data(raw).lower() == atoken.lower()
    assert decode_atoken_from_reserve_data("0x") is None


# ---------------------------------------------------------------------------
# Step 3 — triangular enumeration + evaluation + gated emit
# ---------------------------------------------------------------------------
def test_enumerate_cycles_shape():
    cycles = enumerate_cycles("WETH", ["USDC", "ARB", "WETH"])
    assert ("WETH", "ARB", "USDC", "WETH") in cycles
    assert all(c[0] == "WETH" and c[-1] == "WETH" and c[1] != c[2] for c in cycles)


def test_evaluate_cycle_skips_unquotable_leg():
    async def quote_fn(a, b, amt):
        return None if b == "ARB" else amt * 1.01
    out = asyncio.run(evaluate_cycle(("WETH", "ARB", "USDC", "WETH"),
                                     start_amount=10.0, quote_fn=quote_fn))
    assert out is None   # fail-closed on an unquotable leg


class _GM:
    chain = "arbitrum"
    supports_l1_data_fee = True

    async def all_in_cost(self, *, gross_profit_usd, borrow_amount_usd,
                          notional_usd, gas_units, eth_usd, **kw):
        cost = 10.0        # small fixed all-in cost for the test
        return {"all_in_cost_usd": cost, "l2_fee_usd": 8.0, "l1_fee_usd": 1.0,
                "slippage_usd": 1.0, "net_profit_all_in_usd": gross_profit_usd - cost}


def test_discover_emits_only_economically_valid_above_35_gate():
    # A profitable cycle (+3% round trip on 10 WETH @ $3000 = ~$9000 gross)
    async def good(a, b, amt):
        return amt * 1.01           # +1% per leg, 3 legs ~ +3%
    res = asyncio.run(discover_triangular(
        chain="arbitrum", chain_id=42161, base_token="WETH",
        intermediates=["USDC", "ARB"], start_amount_tokens=10.0,
        base_token_price_usd=3000.0, quote_fn=good, gas_model=_GM(),
        route_gas_units=300_000, native_usd=3000.0,
        liquidity_by_provider={"balancer_v2": 10_000_000},
        fee_bps_by_provider={"balancer_v2": 0}, min_net_profit_usd=35.0))
    assert res["valid"] >= 1
    assert res["emitted"]
    opp = res["emitted"][0]
    assert opp.strategy == StrategyType.TRIANGULAR
    assert opp.chain == "arbitrum" and opp.chain_id == 42161
    assert opp.expected_profit_usd is not None and opp.expected_profit_usd > 35.0


def test_discover_does_not_emit_when_below_gate():
    # A losing cycle (−1% per leg) must NEVER be emitted.
    async def bad(a, b, amt):
        return amt * 0.99
    res = asyncio.run(discover_triangular(
        chain="arbitrum", chain_id=42161, base_token="WETH",
        intermediates=["USDC", "ARB"], start_amount_tokens=10.0,
        base_token_price_usd=3000.0, quote_fn=bad, gas_model=_GM(),
        route_gas_units=300_000, native_usd=3000.0,
        liquidity_by_provider={"balancer_v2": 10_000_000},
        fee_bps_by_provider={"balancer_v2": 0}, min_net_profit_usd=35.0))
    assert res["valid"] == 0 and res["emitted"] == []


def test_discover_denies_without_base_price():
    async def q(a, b, amt):
        return amt
    res = asyncio.run(discover_triangular(
        chain="arbitrum", chain_id=42161, base_token="WETH",
        intermediates=["USDC", "ARB"], start_amount_tokens=10.0,
        base_token_price_usd=None, quote_fn=q, gas_model=_GM(),
        route_gas_units=300_000, native_usd=3000.0))
    assert res["emitted"] == [] and res["denied"] == "base_token_price_unavailable"
