"""T5 verification probe — M3 fresh_fn all-in-cost wiring (offline, mocked).

Constructs build_controlled_live_safety() with fully mocked Base deps (no
network) and asserts:
  * stage='all_in_cost' runs and RevalidationInputs.net_profit_usd is the
    STRICTER all-in net (gross - all_in), not the pre-L1 atomic profit;
  * fresh_fn DENIES (None) when the all-in cost cannot be determined;
  * fresh_fn DENIES when the estimator itself is unavailable (no RPC);
  * the all-in wiring never relaxes another gate (quote/price/mev preserved).
"""
from unittest.mock import patch

import pytest

import arbicore.runtime.composition as comp
import arbicore.searcher.runtime as srt
import arbicore.searcher.price_feed as pf
import arbicore.searcher.aero_resolver as aero
import arbicore.searcher.base_all_in_cost as aic
import arbicore.scanners.flash_loan_arbitrage.live_quote_provider as lqp


class _FakePriceFeed:
    async def price_source(self, sym):
        return 2500.0 if sym.upper() in ("WETH", "ETH") else 1.0

    async def _head_block(self):
        return 1000


FACTS = {
    "hop_legs": [{"venue_id": "uniswap_v3:base", "fee_bps": 5,
                  "depth_usd": 500_000.0, "dex_protocol": "uniswap_v3"}
                 for _ in range(2)],
    "gross_profit_pct": 3.0,
    "tx_gas_units": 800_000,
    "min_pool_tvl_usd_in_route": 500_000.0,
    "tvl_provenance": "onchain_reserves",
    "route_quote_status": "ok",
    "gas_cost_usd": 0.5,
}

PLAN = {
    "route_pools": ["p1", "p2"],
    "cycle_token_path": ["WETH", "USDC", "WETH"],
    "borrow_token": "WETH",
    "borrow_amount_usd": 10_000.0,
    "flash_loan_provider": "balancer_v2",
    "quoted_block": 999,
    "opportunity_id": "OPP_TEST_ALLIN",
    "deadline_ts": None,
}


def _build(estimator, *, facts=FACTS):
    """Build (validator, breaker) with every Base dependency mocked."""
    async def _eth_call(*_a, **_k):
        return "0x"

    async def _qp(hm, borrow):
        return dict(facts) if facts else None

    async def _congestion():
        return 0.4

    async def _aero(*_a, **_k):
        return None

    with patch.object(srt, "make_base_eth_call_from_env", lambda: _eth_call), \
         patch.object(srt, "build_base_tvl_provider", lambda *a, **k: None), \
         patch.object(srt, "make_base_congestion_source_from_env",
                      lambda: _congestion), \
         patch.object(pf, "build_base_price_feed_from_env",
                      lambda *a, **k: _FakePriceFeed()), \
         patch.object(lqp, "make_live_quote_provider", lambda *a, **k: _qp), \
         patch.object(aic, "make_base_all_in_cost_estimator_from_env",
                      lambda: estimator), \
         patch.object(aero, "resolve_and_propagate", _aero):
        validator, breaker = comp.build_controlled_live_safety(object())
        return validator, breaker


def _good_estimator(all_in_usd=45.0):
    async def _est(*, gross_profit_usd, borrow_amount_usd, notional_usd,
                   gas_units, eth_usd, **_k):
        assert gas_units == FACTS["tx_gas_units"]      # exact route gas used
        assert eth_usd == 2500.0                        # real ETH_USD used
        assert borrow_amount_usd == 10_000.0
        return {"all_in_cost_usd": all_in_usd,
                "net_profit_all_in_usd": float(gross_profit_usd) - all_in_usd,
                "l1_fee_usd": 0.5, "l2_fee_usd": 4.5,
                "flash_loan_fee_usd": 0.0, "slippage_usd": 40.0,
                "gas_units": float(gas_units or 0),
                "gas_price_wei_ceiling": 1.25e8}
    return _est


@pytest.mark.asyncio
async def test_fresh_fn_uses_stricter_all_in_net_profit():
    validator, _ = _build(_good_estimator(45.0))
    assert validator is not None
    inp = await validator._fresh(PLAN)
    assert inp is not None, "fresh_fn denied unexpectedly"
    # gross = 10_000 * 3.0/100 = 300 ; all_in = 45 → net = 255
    assert inp.net_profit_usd == pytest.approx(255.0)
    # other gate inputs untouched by the new stage
    assert inp.quote_ok is True and inp.price_ok is True and inp.mev_ok is True
    assert inp.quoted_block == 999 and inp.block_number == 1000


@pytest.mark.asyncio
async def test_all_in_net_is_stricter_than_gross():
    validator, _ = _build(_good_estimator(120.0))
    inp = await validator._fresh(PLAN)
    gross = 10_000.0 * FACTS["gross_profit_pct"] / 100.0
    assert inp.net_profit_usd == pytest.approx(gross - 120.0)
    assert inp.net_profit_usd < gross


@pytest.mark.asyncio
async def test_deny_when_all_in_cost_indeterminate():
    async def _est(**_k):
        return None
    validator, _ = _build(_est)
    assert await validator._fresh(PLAN) is None


@pytest.mark.asyncio
async def test_deny_when_estimator_unavailable_no_rpc():
    validator, _ = _build(None)
    assert await validator._fresh(PLAN) is None


@pytest.mark.asyncio
async def test_profit_buffer_gate_denies_when_all_in_eats_profit():
    # all-in cost 290 on 300 gross → net 10 < min_profit(25)+buffer(10)
    validator, _ = _build(_good_estimator(290.0))
    decision = await validator.validate(PLAN)
    assert decision.ok is False
    assert decision.gate.get("profit_buffer") == "DENIED"


@pytest.mark.asyncio
async def test_estimator_exception_denies():
    async def _est(**_k):
        raise RuntimeError("rpc down")
    validator, _ = _build(_est)
    assert await validator._fresh(PLAN) is None
