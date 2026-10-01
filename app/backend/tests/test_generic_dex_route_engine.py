"""GENERIC_DEX route engine — buy on venue A, sell on venue B.

Offline, fail-closed contract tests. No real RPC/network. The economics gate is
the REAL FlashLoanEconomicsAssessor (aggregate_economics) — not a stub — so the
net-profit math is genuine; only quotes/prices/decimals/gas are injected.

MEV risk is set to LOW in these tests so the deterministic gate identity is:
    net = gross_usd - flash_fee_usd - gas_usd
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from eth_utils import to_checksum_address

from arbicore.models.enums import MevRiskLevel
from arbicore.intelligence.roi_probability import ROIProbabilityEngine
from arbicore.scanners.flash_loan_arbitrage.economics import FlashLoanEconomicsAssessor
from arbicore.scanners.generic_dex_route_engine import (
    GenericDexRouteEngine, VenueSpec,
    ELIGIBLE, SAME_TOKEN_VIOLATION, INVALID_ROUTE, UNSUPPORTED_FLASH_PROVIDER,
    UNKNOWN_PRICE, UNKNOWN_DECIMALS, LEG1_QUOTE_FAILED, LEG2_QUOTE_FAILED,
    UNKNOWN_GAS, UNKNOWN_LIQUIDITY, INSUFFICIENT_LIQUIDITY,
    NON_POSITIVE_NET, BELOW_PROFIT_FLOOR, MIN_ATOMIC_PROFIT_USD,
)

pytestmark = pytest.mark.asyncio

USDC = to_checksum_address("0x" + "11" * 20)
WETH = to_checksum_address("0x" + "22" * 20)
USDC_WEI = 10 ** 10          # 10,000 USDC @ 6 decimals
LEG1_OUT = 3 * 10 ** 18      # intermediate WETH out (arbitrary)


# --------------------------------------------------------------------------- #
# Fakes                                                                       #
# --------------------------------------------------------------------------- #
def _route(status, out, block=17_000_000, pool="0xpool"):
    return SimpleNamespace(
        status=status, final_amount_out_wei=int(out),
        hops=[SimpleNamespace(status=status, block_number=block,
                              quoter_contract=pool)])


class FakeQuoter:
    def __init__(self, *routes):
        self._routes = list(routes)
        self.calls = []

    async def quote_route(self, *, chain, hops, rpc_url=None):
        self.calls.append({"chain": chain, "hops": hops, "rpc_url": rpc_url})
        return self._routes.pop(0)


class FakePrice:
    def __init__(self, price=1.0):
        self._price = price

    async def price_usd(self, chain, token):
        return self._price


def _decimals(chain, token):
    return 6 if to_checksum_address(token) == USDC else 18


def _engine(quoter, *, price=1.0, decimals=_decimals, floor=MIN_ATOMIC_PROFIT_USD):
    return GenericDexRouteEngine(
        quoter, FakePrice(price), decimals_fn=decimals,
        economics_assessor=FlashLoanEconomicsAssessor(roi_engine=ROIProbabilityEngine()),
        min_atomic_profit_usd=floor, mev_risk_level=MevRiskLevel.LOW)


UNIV3 = VenueSpec(dex="uniswap_v3", fee=500, venue_id="univ3_500")
BAL = VenueSpec(dex="balancer_v2", pool_id="0x" + "ab" * 32, venue_id="bal_pool")


async def _eval(engine, *, provider="balancer_v2", chain="ethereum",
                gas=2.0, out2=None, buy=UNIV3, sell=BAL, **kw):
    return await engine.evaluate_route(
        chain=chain, borrow_token=USDC, intermediate_token=WETH,
        amount_usd=10_000.0, venue_buy=buy, venue_sell=sell,
        flash_provider=provider, rpc_url="http://rpc.example",
        gas_cost_usd=gas, **kw)


# --------------------------------------------------------------------------- #
# Happy path + decision bands (net = gross - flash - gas, MEV LOW)            #
# --------------------------------------------------------------------------- #
async def test_eligible_route():
    q = FakeQuoter(_route("ok", LEG1_OUT), _route("ok", USDC_WEI + 100 * 10 ** 6))
    r = await _eval(_engine(q), out2=None)
    assert r.status == ELIGIBLE and r.eligible is True
    assert r.strategy == "GENERIC_DEX"
    assert abs(r.gross_profit_usd - 100.0) < 1e-6
    assert r.net_profit_usd >= MIN_ATOMIC_PROFIT_USD
    assert abs(r.net_profit_usd - (100.0 - 0.0 - 2.0)) < 1e-6
    assert r.flash_fee_usd == 0.0


async def test_below_profit_floor():
    q = FakeQuoter(_route("ok", LEG1_OUT), _route("ok", USDC_WEI + 20 * 10 ** 6))
    r = await _eval(_engine(q))
    assert r.status == BELOW_PROFIT_FLOOR and r.eligible is False
    assert 0.0 < r.net_profit_usd < MIN_ATOMIC_PROFIT_USD


async def test_non_positive_net():
    q = FakeQuoter(_route("ok", LEG1_OUT), _route("ok", USDC_WEI + 1 * 10 ** 6))
    r = await _eval(_engine(q))
    assert r.status == NON_POSITIVE_NET and r.eligible is False
    assert r.net_profit_usd <= 0.0


async def test_negative_gross_denies():
    q = FakeQuoter(_route("ok", LEG1_OUT), _route("ok", USDC_WEI - 10 * 10 ** 6))
    r = await _eval(_engine(q))
    assert r.status == NON_POSITIVE_NET and r.eligible is False
    assert r.gross_profit_usd < 0.0


# --------------------------------------------------------------------------- #
# Route validation                                                            #
# --------------------------------------------------------------------------- #
async def test_same_token_violation():
    q = FakeQuoter()
    r = await _engine(q).evaluate_route(
        chain="ethereum", borrow_token=USDC, intermediate_token=USDC,
        amount_usd=10_000.0, venue_buy=UNIV3, venue_sell=BAL,
        flash_provider="balancer_v2", gas_cost_usd=2.0)
    assert r.status == SAME_TOKEN_VIOLATION and r.eligible is False
    assert q.calls == []


async def test_invalid_token_address():
    q = FakeQuoter()
    r = await _engine(q).evaluate_route(
        chain="ethereum", borrow_token="0xNOTVALID", intermediate_token=WETH,
        amount_usd=10_000.0, venue_buy=UNIV3, venue_sell=BAL,
        flash_provider="balancer_v2", gas_cost_usd=2.0)
    assert r.status == INVALID_ROUTE and q.calls == []


# --------------------------------------------------------------------------- #
# Flash provider gate                                                         #
# --------------------------------------------------------------------------- #
async def test_unknown_flash_provider_denies():
    q = FakeQuoter()
    r = await _eval(_engine(q), provider="does_not_exist")
    assert r.status == UNSUPPORTED_FLASH_PROVIDER and q.calls == []


async def test_flash_provider_unsupported_on_chain():
    # morpho_blue only supports ethereum/base -> deny on arbitrum
    q = FakeQuoter()
    r = await _eval(_engine(q), provider="morpho_blue", chain="arbitrum")
    assert r.status == UNSUPPORTED_FLASH_PROVIDER and q.calls == []


# --------------------------------------------------------------------------- #
# Fail-closed on unknown price / decimals                                     #
# --------------------------------------------------------------------------- #
async def test_unknown_price_denies():
    q = FakeQuoter()
    eng = GenericDexRouteEngine(
        q, FakePrice(None), decimals_fn=_decimals,
        economics_assessor=FlashLoanEconomicsAssessor(roi_engine=ROIProbabilityEngine()),
        mev_risk_level=MevRiskLevel.LOW)
    r = await _eval(eng)
    assert r.status == UNKNOWN_PRICE and q.calls == []


async def test_unknown_decimals_denies():
    q = FakeQuoter()
    eng = _engine(q, decimals=lambda c, t: None)
    r = await _eval(eng)
    assert r.status == UNKNOWN_DECIMALS and q.calls == []


# --------------------------------------------------------------------------- #
# Fail-closed on quote failure (unknown/insufficient liquidity surfaces here) #
# --------------------------------------------------------------------------- #
async def test_leg1_quote_failure_denies():
    q = FakeQuoter(_route("fallback:revert", 0))
    r = await _eval(_engine(q))
    assert r.status == LEG1_QUOTE_FAILED and r.eligible is False
    assert len(q.calls) == 1  # never quotes leg 2


async def test_leg2_quote_failure_denies():
    q = FakeQuoter(_route("ok", LEG1_OUT), _route("fallback:rpc_error", 0))
    r = await _eval(_engine(q))
    assert r.status == LEG2_QUOTE_FAILED and r.eligible is False
    assert len(q.calls) == 2


async def test_leg_zero_output_denies():
    q = FakeQuoter(_route("ok", 0))
    r = await _eval(_engine(q))
    assert r.status == LEG1_QUOTE_FAILED


# --------------------------------------------------------------------------- #
# Fail-closed on unknown gas (never a silent default)                         #
# --------------------------------------------------------------------------- #
async def test_unknown_gas_denies():
    q = FakeQuoter(_route("ok", LEG1_OUT), _route("ok", USDC_WEI + 100 * 10 ** 6))
    r = await _eval(_engine(q), gas=None)
    assert r.status == UNKNOWN_GAS and r.eligible is False


async def test_gas_estimator_used():
    q = FakeQuoter(_route("ok", LEG1_OUT), _route("ok", USDC_WEI + 100 * 10 ** 6))

    async def est(chain):
        return 2.0
    r = await _eval(_engine(q), gas=None, gas_estimator=est)
    assert r.status == ELIGIBLE and abs(r.gas_cost_usd - 2.0) < 1e-9


async def test_gas_estimator_unknown_denies():
    q = FakeQuoter(_route("ok", LEG1_OUT), _route("ok", USDC_WEI + 100 * 10 ** 6))

    async def est(chain):
        return None
    r = await _eval(_engine(q), gas=None, gas_estimator=est)
    assert r.status == UNKNOWN_GAS


# --------------------------------------------------------------------------- #
# Optional pool-TVL liquidity gate (fail-closed when requested)               #
# --------------------------------------------------------------------------- #
async def test_min_tvl_unknown_denies():
    q = FakeQuoter(_route("ok", LEG1_OUT), _route("ok", USDC_WEI + 100 * 10 ** 6))
    r = await _eval(_engine(q), min_tvl_usd=100_000.0, route_tvl_usd=None)
    assert r.status == UNKNOWN_LIQUIDITY


async def test_min_tvl_insufficient_denies():
    q = FakeQuoter(_route("ok", LEG1_OUT), _route("ok", USDC_WEI + 100 * 10 ** 6))
    r = await _eval(_engine(q), min_tvl_usd=100_000.0, route_tvl_usd=50_000.0)
    assert r.status == INSUFFICIENT_LIQUIDITY


async def test_min_tvl_ok_eligible():
    q = FakeQuoter(_route("ok", LEG1_OUT), _route("ok", USDC_WEI + 100 * 10 ** 6))
    r = await _eval(_engine(q), min_tvl_usd=100_000.0, route_tvl_usd=250_000.0)
    assert r.status == ELIGIBLE and r.eligible is True


# --------------------------------------------------------------------------- #
# Immutable floor                                                             #
# --------------------------------------------------------------------------- #
async def test_immutable_floor_cannot_be_lowered():
    q = FakeQuoter(_route("ok", LEG1_OUT), _route("ok", USDC_WEI + 20 * 10 ** 6))
    eng = _engine(q, floor=1.0)                      # attempt to weaken
    assert eng.min_atomic == MIN_ATOMIC_PROFIT_USD   # clamped to $25
    r = await _eval(eng)
    assert r.status == BELOW_PROFIT_FLOOR            # $18 net still rejected


async def test_floor_can_be_raised():
    q = FakeQuoter(_route("ok", LEG1_OUT), _route("ok", USDC_WEI + 100 * 10 ** 6))
    eng = _engine(q, floor=200.0)
    r = await _eval(eng)                             # net $98 < $200
    assert eng.min_atomic == 200.0
    assert r.status == BELOW_PROFIT_FLOOR


# --------------------------------------------------------------------------- #
# Flash fee + quote-inclusive (no double fee) + provenance                    #
# --------------------------------------------------------------------------- #
async def test_flash_fee_applied():
    q = FakeQuoter(_route("ok", LEG1_OUT), _route("ok", USDC_WEI + 100 * 10 ** 6))
    r = await _eval(_engine(q), provider="aave_v3")   # 5 bps on $10k = $5
    assert abs(r.flash_fee_usd - 5.0) < 1e-6
    assert abs(r.net_profit_usd - (100.0 - 5.0 - 2.0)) < 1e-6


async def test_quote_inclusive_no_double_swap_fee():
    # venue observed fee 30 bps vs 0 bps must NOT change net (quote-inclusive).
    v_fee = VenueSpec(dex="uniswap_v3", fee=3000, fee_bps=30, venue_id="u30")
    v_zero = VenueSpec(dex="uniswap_v3", fee=100, fee_bps=0, venue_id="u0")
    q1 = FakeQuoter(_route("ok", LEG1_OUT), _route("ok", USDC_WEI + 100 * 10 ** 6))
    q2 = FakeQuoter(_route("ok", LEG1_OUT), _route("ok", USDC_WEI + 100 * 10 ** 6))
    r_fee = await _eval(_engine(q1), buy=v_fee, sell=v_fee)
    r_zero = await _eval(_engine(q2), buy=v_zero, sell=v_zero)
    assert abs(r_fee.net_profit_usd - r_zero.net_profit_usd) < 1e-6
    assert r_fee.economics_metadata["total_swap_fee_pct"] > 0.0


async def test_provenance_and_leg_pipe():
    q = FakeQuoter(_route("ok", LEG1_OUT, block=100), _route("ok", USDC_WEI + 100 * 10 ** 6, block=101))
    r = await _eval(_engine(q))
    assert r.leg1.amount_out_wei == LEG1_OUT
    assert r.leg2.amount_in_wei == LEG1_OUT           # pipe leg1 out -> leg2 in
    assert r.leg1.block_number == 100 and r.leg2.block_number == 101
    assert r.borrow_amount_wei == USDC_WEI and r.borrow_amount_usd == 10_000.0
    assert r.venue_buy == "univ3_500" and r.venue_sell == "bal_pool"


# --------------------------------------------------------------------------- #
# Six-chain architecture preserved (aave_v3 supports all six)                 #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("chain",
                         ["ethereum", "arbitrum", "base", "optimism", "polygon", "bnb"])
async def test_six_chain_eligible(chain):
    q = FakeQuoter(_route("ok", LEG1_OUT), _route("ok", USDC_WEI + 100 * 10 ** 6))
    r = await _eval(_engine(q), provider="aave_v3", chain=chain)
    assert r.status == ELIGIBLE and r.chain == chain
    assert abs(r.net_profit_usd - (100.0 - 5.0 - 2.0)) < 1e-6
