"""GENERIC_DEX — canonical ChainGasModel integration (route-level gas pricing).

Offline, fail-closed tests. The canonical gas-model lookup
(get_chain_gas_model) is monkeypatched to a deterministic fake so no RPC is
needed; the REAL get_chain_gas_model seam is exercised separately for all six
chains. RouteQuote.aggregate_gas_estimate_units is DEX-quote gas, priced via the
canonical all_in_cost() (gas-only = l1_fee_usd + l2_fee_usd).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from eth_utils import to_checksum_address

import arbicore.scanners.generic_dex_route_engine as gde
from arbicore.models.enums import MevRiskLevel
from arbicore.intelligence.roi_probability import ROIProbabilityEngine
from arbicore.scanners.flash_loan_arbitrage.economics import FlashLoanEconomicsAssessor
from arbicore.scanners.generic_dex_route_engine import (
    GenericDexRouteEngine, VenueSpec, ELIGIBLE, UNKNOWN_GAS, MIN_ATOMIC_PROFIT_USD)
from arbicore.chains.gas_model import get_chain_gas_model

pytestmark = pytest.mark.asyncio

USDC = to_checksum_address("0x" + "11" * 20)
WETH = to_checksum_address("0x" + "22" * 20)
USDC_WEI = 10 ** 10
LEG1_OUT = 3 * 10 ** 18
UNIV3 = VenueSpec(dex="uniswap_v3", fee=500, venue_id="univ3_500")
BAL = VenueSpec(dex="balancer_v2", pool_id="0x" + "ab" * 32, venue_id="bal_pool")


def _route(status, out, gas_units=None):
    return SimpleNamespace(
        status=status, final_amount_out_wei=int(out),
        aggregate_gas_estimate_units=gas_units,
        hops=[SimpleNamespace(status=status, block_number=1, quoter_contract="0xp")])


class FakePrice:
    def __init__(self, price=1.0, native=3000.0):
        self._price, self._native = price, native

    async def price_usd(self, chain, token):
        # borrow token (USDC) -> $1 ; wrapped-native -> native price (or None)
        return self._price if to_checksum_address(token) == USDC else self._native


class FakeQuoter:
    def __init__(self, *routes):
        self._routes = list(routes)

    async def quote_route(self, *, chain, hops, rpc_url=None):
        return self._routes.pop(0)


class FakeGasModel:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def all_in_cost(self, **kw):
        self.calls.append(kw)
        return self.result


def _engine(quoter, native=3000.0):
    return GenericDexRouteEngine(
        quoter, FakePrice(1.0, native), decimals_fn=lambda c, t: 6,
        economics_assessor=FlashLoanEconomicsAssessor(roi_engine=ROIProbabilityEngine()),
        mev_risk_level=MevRiskLevel.LOW)


async def _eval(engine, *, chain="base", provider="balancer_v2", gas_cost_usd=None,
                out2=USDC_WEI + 100 * 10 ** 6):
    q = None  # engine already holds quoter
    return await engine.evaluate_route(
        chain=chain, borrow_token=USDC, intermediate_token=WETH,
        amount_usd=10_000.0, venue_buy=UNIV3, venue_sell=BAL,
        flash_provider=provider, rpc_url="http://rpc.example",
        gas_cost_usd=gas_cost_usd)


GAS_OK = {"l1_fee_usd": 1.0, "l2_fee_usd": 1.0, "all_in_cost_usd": 2.0,
          "flash_loan_fee_usd": 0.0, "slippage_usd": 0.0}


# --------------------------------------------------------------------------- #
# 1. both legs gas known -> canonical model called
# --------------------------------------------------------------------------- #
async def test_both_legs_gas_calls_canonical_model(monkeypatch):
    model = FakeGasModel(GAS_OK)
    monkeypatch.setattr(gde, "get_chain_gas_model", lambda c: model)
    q = FakeQuoter(_route("ok", LEG1_OUT, 120_000),
                   _route("ok", USDC_WEI + 100 * 10 ** 6, 130_000))
    r = await _eval(_engine(q))
    assert r.status == ELIGIBLE
    assert len(model.calls) == 1
    assert model.calls[0]["gas_units"] == 250_000          # combined only
    assert abs(r.gas_cost_usd - 2.0) < 1e-9                # l1+l2 exactly once


# --------------------------------------------------------------------------- #
# 2/3/4. partial / missing route gas -> UNKNOWN_GAS (None never == zero)
# --------------------------------------------------------------------------- #
async def test_leg2_gas_none_unknown(monkeypatch):
    model = FakeGasModel(GAS_OK)
    monkeypatch.setattr(gde, "get_chain_gas_model", lambda c: model)
    q = FakeQuoter(_route("ok", LEG1_OUT, 120_000),
                   _route("ok", USDC_WEI + 100 * 10 ** 6, None))
    r = await _eval(_engine(q))
    assert r.status == UNKNOWN_GAS and model.calls == []


async def test_leg1_gas_none_unknown(monkeypatch):
    model = FakeGasModel(GAS_OK)
    monkeypatch.setattr(gde, "get_chain_gas_model", lambda c: model)
    q = FakeQuoter(_route("ok", LEG1_OUT, None),
                   _route("ok", USDC_WEI + 100 * 10 ** 6, 130_000))
    r = await _eval(_engine(q))
    assert r.status == UNKNOWN_GAS and model.calls == []


async def test_both_gas_none_unknown(monkeypatch):
    model = FakeGasModel(GAS_OK)
    monkeypatch.setattr(gde, "get_chain_gas_model", lambda c: model)
    q = FakeQuoter(_route("ok", LEG1_OUT, None),
                   _route("ok", USDC_WEI + 100 * 10 ** 6, None))
    r = await _eval(_engine(q))
    assert r.status == UNKNOWN_GAS and model.calls == []


# --------------------------------------------------------------------------- #
# 5. canonical model returns None -> UNKNOWN_GAS
# --------------------------------------------------------------------------- #
async def test_all_in_cost_none_unknown(monkeypatch):
    model = FakeGasModel(None)
    monkeypatch.setattr(gde, "get_chain_gas_model", lambda c: model)
    q = FakeQuoter(_route("ok", LEG1_OUT, 120_000),
                   _route("ok", USDC_WEI + 100 * 10 ** 6, 130_000))
    r = await _eval(_engine(q))
    assert r.status == UNKNOWN_GAS


async def test_model_missing_unknown(monkeypatch):
    monkeypatch.setattr(gde, "get_chain_gas_model", lambda c: None)
    q = FakeQuoter(_route("ok", LEG1_OUT, 120_000),
                   _route("ok", USDC_WEI + 100 * 10 ** 6, 130_000))
    r = await _eval(_engine(q))
    assert r.status == UNKNOWN_GAS


# --------------------------------------------------------------------------- #
# 6. native USD price unavailable -> UNKNOWN_GAS
# --------------------------------------------------------------------------- #
async def test_native_price_unavailable_unknown(monkeypatch):
    model = FakeGasModel(GAS_OK)
    monkeypatch.setattr(gde, "get_chain_gas_model", lambda c: model)
    q = FakeQuoter(_route("ok", LEG1_OUT, 120_000),
                   _route("ok", USDC_WEI + 100 * 10 ** 6, 130_000))
    eng = _engine(q, native=None)          # native price feed returns None
    r = await _eval(eng)
    assert r.status == UNKNOWN_GAS and model.calls == []


# --------------------------------------------------------------------------- #
# 7. canonical gas included exactly once + net identity
# --------------------------------------------------------------------------- #
async def test_gas_included_exactly_once(monkeypatch):
    model = FakeGasModel({"l1_fee_usd": 0.5, "l2_fee_usd": 1.5})
    monkeypatch.setattr(gde, "get_chain_gas_model", lambda c: model)
    q = FakeQuoter(_route("ok", LEG1_OUT, 100_000),
                   _route("ok", USDC_WEI + 100 * 10 ** 6, 100_000))
    r = await _eval(_engine(q))            # gross $100, balancer flash 0
    assert abs(r.gas_cost_usd - 2.0) < 1e-9
    assert abs(r.net_profit_usd - (100.0 - 0.0 - 2.0)) < 1e-9
    assert len(model.calls) == 1


# --------------------------------------------------------------------------- #
# 8. immutable $25 floor preserved with canonical gas
# --------------------------------------------------------------------------- #
async def test_floor_immutable_with_canonical_gas(monkeypatch):
    model = FakeGasModel(GAS_OK)
    monkeypatch.setattr(gde, "get_chain_gas_model", lambda c: model)
    q = FakeQuoter(_route("ok", LEG1_OUT, 100_000),
                   _route("ok", USDC_WEI + 20 * 10 ** 6, 100_000))
    eng = GenericDexRouteEngine(
        q, FakePrice(1.0, 3000.0), decimals_fn=lambda c, t: 6,
        economics_assessor=FlashLoanEconomicsAssessor(roi_engine=ROIProbabilityEngine()),
        min_atomic_profit_usd=25.0, mev_risk_level=MevRiskLevel.LOW)
    # Operator-raised floor still rejects sub-floor positive nets.
    assert eng.min_atomic == 25.0
    r = await _eval(eng)                   # gross $20 - $2 gas = $18 net
    assert r.status == "below_profit_floor"


# --------------------------------------------------------------------------- #
# 9. flash-loan fee unchanged (aave 5 bps) alongside canonical gas
# --------------------------------------------------------------------------- #
async def test_flash_fee_unchanged_with_canonical_gas(monkeypatch):
    model = FakeGasModel(GAS_OK)
    monkeypatch.setattr(gde, "get_chain_gas_model", lambda c: model)
    q = FakeQuoter(_route("ok", LEG1_OUT, 100_000),
                   _route("ok", USDC_WEI + 100 * 10 ** 6, 100_000))
    r = await _eval(_engine(q), chain="ethereum", provider="aave_v3")
    assert abs(r.flash_fee_usd - 5.0) < 1e-6
    assert abs(r.net_profit_usd - (100.0 - 5.0 - 2.0)) < 1e-6


# --------------------------------------------------------------------------- #
# 10. all six chains resolve through the REAL get_chain_gas_model seam
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("chain",
                         ["base", "ethereum", "arbitrum", "optimism", "polygon", "bnb"])
def test_six_chains_resolve_gas_model(chain):
    assert get_chain_gas_model(chain) is not None


@pytest.mark.parametrize("chain",
                         ["base", "ethereum", "arbitrum", "optimism", "polygon", "bnb"])
def test_native_wrapped_token_resolves(chain):
    assert gde._native_wrapped_token(chain) is not None


# --------------------------------------------------------------------------- #
# 11. no signing/broadcast/execution surface in the engine module
# --------------------------------------------------------------------------- #
def test_no_execution_surface():
    import inspect
    src = inspect.getsource(gde).lower()
    for forbidden in ("send_raw", "sign_transaction", "signtransaction",
                      "eth_sendtransaction", "private_key", "sendrawtransaction"):
        assert forbidden not in src
