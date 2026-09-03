"""D-3.6 cross-direction price reconciliation — the UniV3 vs Aerodrome spread
must be mathematically correct.

Proves (a) EVMV3Quoter._quote_per_base normalizes both directions to
QUOTE-per-BASE, and (b) with real-shaped quotes from two wired Base venues the
DEXQuoteVerifier computes the true arbitrage spread (lowest ask vs highest bid),
not a unit-mismatched reciprocal. Network is monkeypatched (deterministic).
"""
from __future__ import annotations

import asyncio

import pytest

from arbicore.scanners.dex_arbitrage.quoter import EVMV3Quoter
from arbicore.execution import quoter as execq
from arbicore.scanners.dex_arbitrage import DEXQuoteVerifier
from arbicore.models.discovery import DiscoveryCandidate, VerifiedOutcome
from arbicore.models.enums import OpportunityType
from arbicore.discovery import base_venues as bv

USDC = bv.token_address("USDC").lower()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _hop(dex, tin, tout, ain, aout):
    return execq.HopQuote(
        hop_index=0, dex=dex, token_in=tin, token_out=tout, amount_in_wei=int(ain),
        amount_out_wei=int(aout), sqrt_price_x96_after=None, gas_estimate_units=80000,
        price_impact_bps=None, quoter_contract="0xq", rpc_host="mainnet.base.org",
        block_number=27000000, status="ok", error=None, generated_at="t")


def _route(hop):
    return execq.RouteQuote(
        chain="base", hops=[hop], final_amount_out_wei=hop.amount_out_wei,
        aggregate_price_impact_bps=None, aggregate_gas_estimate_units=80000,
        status="ok", generated_at="t", ttl_seconds=5)


# ----- unit: normalization ---------------------------------------------------

def test_quote_per_base_is_quote_per_base_both_directions():
    # buy: spend 1000 QUOTE to get 0.4 BASE → ask = 2500 QUOTE/BASE
    assert EVMV3Quoter._quote_per_base("buy", 1000.0, 0.4) == pytest.approx(2500.0)
    # sell: sell 0.05 BASE to get 125 QUOTE → bid = 2500 QUOTE/BASE
    assert EVMV3Quoter._quote_per_base("sell", 0.05, 125.0) == pytest.approx(2500.0)
    # fail-closed on non-positive
    assert EVMV3Quoter._quote_per_base("buy", 0.0, 1.0) is None
    assert EVMV3Quoter._quote_per_base("sell", 1.0, 0.0) is None


# ----- verifier spread correctness across two wired venues -------------------

class _StubCaps:
    async def is_gate_3_pass(self, venue_id, base, quote):
        return True, "ok"


def test_cross_venue_spread_is_mathematically_correct(monkeypatch):
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://mainnet.base.org")
    monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)

    # Target book (QUOTE/BASE = USDC per WETH):
    #   UniV3    ask=2480, bid=2500
    #   Aerodrome ask=2510, bid=2530
    # => buy UniV3 @2480, sell Aerodrome @2530; spread=(2530-2480)/2480 = 2.01613%
    def _out(dex, is_sell):
        if not is_sell:  # buy: 1000 USDC -> WETH; ask = 1000/weth_out
            ask = {"uniswap_v3": 2480.0, "aerodrome": 2510.0,
                   "aerodrome_slipstream": 2510.0}[dex]
            return int((1000.0 / ask) * 1e18)        # WETH wei
        bid = {"uniswap_v3": 2500.0, "aerodrome": 2530.0,
               "aerodrome_slipstream": 2530.0}[dex]
        return int(bid * 0.05 * 1e6)                 # USDC wei (0.05 WETH probe)

    async def fake(self, *, chain, hops, rpc_url=None):
        h = hops[0]
        is_sell = h["token_out"].lower() == USDC
        return _route(_hop(h["dex"], h["token_in"], h["token_out"],
                           h["amount_in_wei"], _out(h["dex"], is_sell)))

    monkeypatch.setattr(execq.QuoterRegistry, "quote_route", fake)
    verifier = DEXQuoteVerifier(
        quoters=[EVMV3Quoter(chain="base", dex="uniswap_v3",
                             source_id="uniswap_v3_quoter_base"),
                 EVMV3Quoter(chain="base", dex="aerodrome",
                             source_id="aerodrome_quoter_base")],
        venue_caps=_StubCaps(),
        config_loader=lambda: {"default_notional_usd": 1000.0,
                               "gate_thresholds": {"default": {
                                   "min_net_spread_after_slip_after_gas_pct": 0.1,
                                   "min_depth_usd": 5000, "min_confidence": 55}}})
    cand = DiscoveryCandidate(
        candidate_id="c_spread", opportunity_type=OpportunityType.DEX_ARBITRAGE,
        hint_source="venue_dex_pool:uniswap_v3:base", subject_id="WETH/USDC@base",
        asset="WETH", candidate_venues=["uniswap_v3:base", "aerodrome:base"])
    opp, tag = _run(verifier.verify(cand))

    assert opp is not None
    assert opp.buy_venue == "uniswap_v3:base"      # lowest ask
    assert opp.sell_venue == "aerodrome:base"      # highest bid
    assert opp.buy_price == pytest.approx(2480.0, rel=1e-4)
    assert opp.sell_price == pytest.approx(2530.0, rel=1e-4)
    # correct arbitrage spread — NOT a unit-mismatched reciprocal
    assert opp.spread_pct == pytest.approx((2530.0 - 2480.0) / 2480.0 * 100.0, rel=1e-4)
