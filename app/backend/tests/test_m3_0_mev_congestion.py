"""M3.0 — MEV congestion source + stage-probe alignment (offline, fail-closed).

Locks in the fixes for:
  * mev.classify(source_chain_congestion=None) TypeError blocker
  * str-enum ``level <= 2`` latent comparison bug (policy: HIGH denies)
  * eth_feeHistory gasUsedRatio → congestion(0..100), fail-closed
  * FIRST_BLOCKING_STAGE mirroring composition.fresh_fn (incl. stage=mev)
No network, no signing, no broadcast.
"""
from unittest.mock import patch

import pytest

import arbicore.config.persistent as persist
import arbicore.providers.rpc as rpcmod
from arbicore.scanners.cross_chain_arbitrage.bridge_intelligence import MevRiskScorer
from arbicore.searcher import runtime as rt
from arbicore.searcher.aero_resolver import resolve_and_propagate
from scripts.m3_0_vps_validate import _first_blocking_stage


class _FeeHist:
    def __init__(self, ratios=None, raise_exc=None):
        self._ratios = ratios
        self._exc = raise_exc

    async def eth_get_fee_history(self, blocks=10, newest="latest"):
        if self._exc is not None:
            raise self._exc
        return {"gasUsedRatio": self._ratios}


def _provider_factory(ratios=None, raise_exc=None):
    def _factory(*_a, **_k):
        return _FeeHist(ratios=ratios, raise_exc=raise_exc)
    return _factory


# ---- congestion source (real gasUsedRatio, fail-closed) --------------------

@pytest.mark.asyncio
async def test_congestion_maps_gas_used_ratio_to_pct():
    with patch.object(persist, "resolve_rpc_url_from_env", lambda c: "http://x"):
        with patch.object(rpcmod, "EthJsonRpcProvider",
                          _provider_factory([0.2, 0.4, 0.6, 0.4, 0.2])):
            src = rt.make_base_congestion_source_from_env()
            assert abs(await src() - 36.0) < 1e-9


@pytest.mark.asyncio
async def test_congestion_fail_closed_on_rpc_error():
    with patch.object(persist, "resolve_rpc_url_from_env", lambda c: "http://x"):
        with patch.object(rpcmod, "EthJsonRpcProvider",
                          _provider_factory(raise_exc=RuntimeError("rpc down"))):
            src = rt.make_base_congestion_source_from_env()
            assert await src() is None


@pytest.mark.asyncio
async def test_congestion_fail_closed_on_empty_ratios():
    with patch.object(persist, "resolve_rpc_url_from_env", lambda c: "http://x"):
        with patch.object(rpcmod, "EthJsonRpcProvider",
                          _provider_factory([])):
            src = rt.make_base_congestion_source_from_env()
            assert await src() is None


def test_congestion_source_none_without_rpc():
    with patch.object(persist, "resolve_rpc_url_from_env", lambda c: None):
        assert rt.make_base_congestion_source_from_env() is None


# ---- MEV classifier policy (real float, HIGH denies) -----------------------

def test_mev_classify_real_float_no_crash_medium_ok():
    mv = MevRiskScorer().classify(
        source_chain_congestion=30.0, destination_chain_congestion=30.0,
        asset="USDT", notional_usd=10_000.0, is_atomic=True)
    assert mv["label"] in ("LOW", "MEDIUM")
    assert (mv["label"] != "HIGH") is True     # mev_ok policy


def test_mev_classify_high_denies():
    mv = MevRiskScorer().classify(
        source_chain_congestion=95.0, destination_chain_congestion=95.0,
        asset="WETH", notional_usd=200_000.0, is_atomic=True)
    assert mv["label"] == "HIGH"
    assert (mv["label"] != "HIGH") is False    # DENY


# ---- Aerodrome propagation fail-closed -------------------------------------

@pytest.mark.asyncio
async def test_resolve_and_propagate_no_eth_call_is_zero():
    assert await resolve_and_propagate(None, ["x"]) == 0


# ---- stage-probe mirrors fresh_fn (mev included) ---------------------------

def _base_ok_probe():
    """A probe dict where every pre-mev stage passes."""
    return {
        "stage_1_plan_shape": {"shape_ok": True},
        "stage_6_facts": {"route_quote_status": "ok", "n_hop_legs": 3},
        "stage_3_head_block": 123,
        "stage_4_borrow_price_usd": 1.0,
        "stage_7_flashloan_availability": {"available": True},
    }


def test_first_blocking_stage_mev_congestion_unavailable():
    o = _base_ok_probe()
    o["stage_8_mev"] = {"congestion_pct": None, "mev_ok": None}
    assert "stage=mev" in _first_blocking_stage(o)


def test_first_blocking_stage_mev_high_denies():
    o = _base_ok_probe()
    o["stage_8_mev"] = {"congestion_pct": 90.0, "label": "HIGH",
                        "score": 100.0, "mev_ok": False}
    assert "mev_ok gate will DENY" in _first_blocking_stage(o)


def test_first_blocking_stage_green_when_all_resolve():
    o = _base_ok_probe()
    o["stage_8_mev"] = {"congestion_pct": 20.0, "label": "LOW",
                        "score": 20.0, "mev_ok": True}
    assert _first_blocking_stage(o).startswith("none - all fresh stages")


def test_first_blocking_stage_quote_before_mev():
    """fresh_fn evaluates live_quote BEFORE mev — probe must agree."""
    o = _base_ok_probe()
    o["stage_6_facts"] = None
    o["stage_8_mev"] = {"congestion_pct": None}
    assert "stage_6_facts=None" in _first_blocking_stage(o)


def test_first_blocking_stage_quote_error_string_not_mev():
    """A stage_6 ERROR string must be reported as the live_quote blocker, NOT
    misattributed to stage_8_mev (mirrors fresh_fn ordering)."""
    o = _base_ok_probe()
    o["stage_6_facts"] = "ERROR KeyError: 'CBETH'"
    o["stage_8_mev"] = {"congestion_pct": None}
    stage = _first_blocking_stage(o)
    assert "stage=live_quote" in stage and "stage=mev" not in stage


# ---- mixed-case Base token symbols resolve (no KeyError) -------------------

@pytest.mark.parametrize("raw,canon", [
    ("CBETH", "cbETH"), ("cbETH", "cbETH"), ("USDBC", "USDbC"),
    ("CBBTC", "cbBTC"), ("RETH", "rETH"), ("WSTETH", "wstETH"),
    ("WEETH", "weETH"), ("weth", "WETH"), ("usdc", "USDC"),
])
def test_token_symbols_case_insensitive(raw, canon):
    from arbicore.discovery.base_venues import (
        canonical_symbol, token_address, probe_amount)
    assert canonical_symbol(raw) == canon
    assert token_address(raw) is not None       # no KeyError
    assert probe_amount(raw) > 0


def test_unknown_token_fails_closed_none():
    from arbicore.discovery.base_venues import token_address, canonical_symbol
    assert canonical_symbol("NOPE") is None
    assert token_address("NOPE") is None         # None, not KeyError


# ---- TVL reserves_fn aligns with runtime-resolved Aerodrome addresses ------

@pytest.mark.asyncio
async def test_reserves_fn_registry_fallback_for_runtime_resolved_pool():
    """When pool_meta (snapshotted at build time) lacks a runtime-resolved
    Aerodrome/Slipstream address, reserves_fn must resolve the token metadata
    from the canonical registry and still measure reserves."""
    from types import SimpleNamespace
    from arbicore.searcher.v3_state import make_base_v3_reserves_fn
    import arbicore.discovery.base_pool_registry as reg
    fake = SimpleNamespace(
        token0_symbol="WETH", token0_address="0xW", token0_decimals=18,
        token1_symbol="USDC", token1_address="0xU", token1_decimals=6)

    async def fake_eth(to, data):
        return hex(2 * 10 ** 18) if to == "0xW" else hex(6000 * 10 ** 6)

    with patch.object(reg, "canonical_pool_by_address", lambda a: fake):
        rfn = make_base_v3_reserves_fn(fake_eth, {})   # EMPTY meta → fallback
        res = await rfn("base", "0xPOOL")
    assert res == ("WETH", 2.0, "USDC", 6000.0)


@pytest.mark.asyncio
async def test_reserves_fn_none_when_pool_unknown():
    from arbicore.searcher.v3_state import make_base_v3_reserves_fn
    import arbicore.discovery.base_pool_registry as reg

    async def fake_eth(to, data):
        return "0x" + "0" * 64

    with patch.object(reg, "canonical_pool_by_address", lambda a: None):
        rfn = make_base_v3_reserves_fn(fake_eth, {})
        assert await rfn("base", "0xUNKNOWN") is None
