"""M3 controlled-live · Base all-in transaction-cost estimator (offline, mocked).

Proves the estimator computes L2 + L1(GasPriceOracle) + flash + slippage and,
above all, FAILS CLOSED (returns None ⇒ M3 DENY) whenever a real input is
missing: no gas estimate, gas over ceiling, no gas price, unreadable L1 fee,
or missing ETH_USD. No network.
"""
import os
from unittest.mock import patch

import pytest

import arbicore.config.persistent as persist
import arbicore.providers.rpc_failover as rpcfo
from arbicore.searcher import base_all_in_cost as aic


class _FakeProvider:
    def __init__(self, *, gas_price=100_000_000, l1_raw=None, raise_gp=False,
                 raise_call=False):
        self._gp = gas_price
        self._l1 = l1_raw if l1_raw is not None else hex(2 * 10 ** 14)  # ~0.0002 ETH
        self._raise_gp = raise_gp
        self._raise_call = raise_call

    def _factory(self, *_a, **_k):
        return self

    async def eth_get_gas_price(self):
        if self._raise_gp:
            raise RuntimeError("rpc down")
        return self._gp

    async def eth_call(self, tx, *_a, **_k):
        if self._raise_call:
            raise RuntimeError("oracle down")
        return self._l1


def _mk(provider):
    # Current seam: the estimator requires an EXPLICIT operator Base RPC
    # (PROVIDER_RPC_URL_BASE) and reads the provider via the failover registry.
    # Patch that registry accessor so the FakeProvider drives the math offline.
    with patch.dict(os.environ, {"PROVIDER_RPC_URL_BASE": "http://x"}):
        with patch.object(rpcfo, "get_registry_rpc_provider",
                          lambda *a, **k: provider):
            return aic.make_base_all_in_cost_estimator_from_env()


BASE = dict(gross_profit_usd=200.0, borrow_amount_usd=10000.0,
            notional_usd=10000.0, gas_units=800_000, eth_usd=2500.0)


@pytest.mark.asyncio
async def test_all_in_cost_happy_path_components():
    est = _mk(_FakeProvider())
    r = await est(**BASE)
    assert r is not None
    for k in ("l2_fee_usd", "l1_fee_usd", "flash_loan_fee_usd", "slippage_usd",
              "all_in_cost_usd", "net_profit_all_in_usd"):
        assert k in r
    # slippage default 30 bps on 10k notional = $30
    assert r["slippage_usd"] == pytest.approx(30.0)
    # l1 fee = 2e14 wei * 2500 / 1e18 = $0.5
    assert r["l1_fee_usd"] == pytest.approx(0.5)
    # all_in = l2 + l1 + flash(0) + slippage ; net = gross - all_in
    assert r["all_in_cost_usd"] == pytest.approx(
        r["l2_fee_usd"] + r["l1_fee_usd"] + r["flash_loan_fee_usd"] + r["slippage_usd"])
    assert r["net_profit_all_in_usd"] == pytest.approx(200.0 - r["all_in_cost_usd"])


@pytest.mark.asyncio
async def test_deny_when_no_rpc(monkeypatch):
    # No explicit operator Base RPC configured ⇒ estimator None (fail closed).
    for k in ("PROVIDER_RPC_URLS_BASE", "PROVIDER_RPC_URL_BASE"):
        monkeypatch.delenv(k, raising=False)
    with patch.object(persist, "resolve_rpc_url_from_env", lambda c: None):
        assert aic.make_base_all_in_cost_estimator_from_env() is None


@pytest.mark.asyncio
async def test_deny_when_eth_usd_missing():
    est = _mk(_FakeProvider())
    assert await est(**{**BASE, "eth_usd": None}) is None


@pytest.mark.asyncio
async def test_deny_when_gas_units_missing_or_over_ceiling():
    est = _mk(_FakeProvider())
    assert await est(**{**BASE, "gas_units": None}) is None
    assert await est(**{**BASE, "gas_units": 0}) is None
    assert await est(**{**BASE, "gas_units": 25_000_000}) is None   # > 3M ceiling


@pytest.mark.asyncio
async def test_deny_when_gas_price_unavailable():
    est = _mk(_FakeProvider(raise_gp=True))
    assert await est(**BASE) is None
    est2 = _mk(_FakeProvider(gas_price=0))
    assert await est2(**BASE) is None


@pytest.mark.asyncio
async def test_deny_when_gas_price_above_ceiling_not_capped():
    # real 50 gwei with default 5 gwei ceiling → DENY (must NOT silently cap,
    # which would understate the L2 fee and could approve a loss).
    est = _mk(_FakeProvider(gas_price=50_000_000_000))
    assert await est(**BASE) is None


@pytest.mark.asyncio
async def test_deny_when_l1_fee_unreadable():
    assert await _mk(_FakeProvider(raise_call=True))(**BASE) is None
    assert await _mk(_FakeProvider(l1_raw="0x"))(**BASE) is None


@pytest.mark.asyncio
async def test_estimate_gas_fn_used_and_failure_denies():
    est = _mk(_FakeProvider())

    async def good():
        return 900_000

    r = await est(**{**BASE, "gas_units": None, "estimate_gas_fn": good})
    assert r is not None and r["gas_units"] == pytest.approx(900_000)

    async def boom():
        raise RuntimeError("estimateGas revert")

    assert await est(**{**BASE, "gas_units": None, "estimate_gas_fn": boom}) is None


def test_gas_limit_ceiling_is_not_protocol_max():
    cfg = aic.BaseAllInCostConfig.from_env()
    assert cfg.gas_limit_ceiling < 25_000_000        # never the protocol ceiling


def test_env_clamps_ceiling_below_protocol_max_and_floors_bps():
    import os
    from unittest.mock import patch
    with patch.dict(os.environ, {"ARBICORE_GAS_LIMIT_CEILING": "30000000",
                                 "ARBICORE_SLIPPAGE_BPS": "-500",
                                 "ARBICORE_FLASH_LOAN_FEE_BPS": "-1"}):
        cfg = aic.BaseAllInCostConfig.from_env()
    assert cfg.gas_limit_ceiling < 25_000_000        # clamped below protocol max
    assert cfg.slippage_bps >= 0.0                   # no negative "cost"
    assert cfg.flash_loan_fee_bps >= 0.0


def test_encode_get_l1_fee_shape():
    data = aic._encode_get_l1_fee(4)
    assert data.startswith(aic.SEL_GET_L1_FEE)
    # selector(10) + offset(64) + length(64) + 32-byte-padded body(64)
    assert len(data) == 10 + 64 + 64 + 64
