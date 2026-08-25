"""Iteration-6 independent re-verification probe for the two iteration-5 defects.

D1 (was HIGH): estimate() must DENY (None) when the buffered real gas price
exceeds ARBICORE_MAX_GAS_PRICE_WEI, instead of silently capping and reporting
an understated l2_fee_usd.
D2 (was MINOR): BaseAllInCostConfig.from_env() must hard-clamp the per-tx gas
limit ceiling strictly below PROTOCOL_GAS_MAX and floor bps values at 0.
"""
import importlib

import pytest

MOD = "arbicore.searcher.base_all_in_cost"


class _Provider:
    def __init__(self, gas_price, l1_fee_wei=10**13):
        self._gp = gas_price
        self._l1 = l1_fee_wei

    async def eth_get_gas_price(self):
        return self._gp

    async def eth_call(self, tx):
        return hex(self._l1)


def _make_estimator(monkeypatch, provider):
    m = importlib.import_module(MOD)
    monkeypatch.setattr(
        "arbicore.config.persistent.resolve_rpc_url_from_env",
        lambda chain: "https://base.example/rpc",
    )
    import arbicore.providers.rpc as rpc
    monkeypatch.setattr(rpc, "EthJsonRpcProvider", lambda **kw: provider)
    return m.make_base_all_in_cost_estimator_from_env()


# --- D1: gas price above ceiling must DENY, never cap -----------------------
@pytest.mark.asyncio
async def test_probe_50gwei_vs_5gwei_ceiling_denies(monkeypatch):
    monkeypatch.setenv("ARBICORE_MAX_GAS_PRICE_WEI", "5000000000")   # 5 gwei
    monkeypatch.setenv("ARBICORE_GAS_PRICE_BUFFER_PCT", "0.25")
    monkeypatch.setenv("ARBICORE_GAS_LIMIT_CEILING", "3000000")
    est = _make_estimator(monkeypatch, _Provider(50_000_000_000))  # 50 gwei
    assert est is not None
    out = await est(gross_profit_usd=1000.0, borrow_amount_usd=10000.0,
                    notional_usd=10000.0, gas_units=800_000, eth_usd=2500.0)
    assert out is None, f"expected DENY, got {out}"


@pytest.mark.asyncio
async def test_probe_gas_price_just_above_ceiling_denies(monkeypatch):
    # real 4.1 gwei * 1.25 = 5.125 gwei > 5 gwei ceiling ⇒ DENY
    monkeypatch.setenv("ARBICORE_MAX_GAS_PRICE_WEI", "5000000000")
    monkeypatch.setenv("ARBICORE_GAS_PRICE_BUFFER_PCT", "0.25")
    est = _make_estimator(monkeypatch, _Provider(4_100_000_000))
    out = await est(gross_profit_usd=100.0, borrow_amount_usd=1000.0,
                    notional_usd=1000.0, gas_units=200_000, eth_usd=2500.0)
    assert out is None


@pytest.mark.asyncio
async def test_probe_gas_price_within_ceiling_uses_real_buffered_price(monkeypatch):
    monkeypatch.setenv("ARBICORE_MAX_GAS_PRICE_WEI", "5000000000")
    monkeypatch.setenv("ARBICORE_GAS_PRICE_BUFFER_PCT", "0.25")
    monkeypatch.setenv("ARBICORE_SLIPPAGE_BPS", "0")
    monkeypatch.setenv("ARBICORE_FLASH_LOAN_FEE_BPS", "0")
    est = _make_estimator(monkeypatch, _Provider(2_000_000_000))  # 2 gwei
    out = await est(gross_profit_usd=100.0, borrow_amount_usd=1000.0,
                    notional_usd=1000.0, gas_units=800_000, eth_usd=2500.0)
    assert out is not None
    assert out["gas_price_wei_ceiling"] == pytest.approx(2_500_000_000)
    expected_l2 = 800_000 * 2_500_000_000 / 1e18 * 2500.0
    assert out["l2_fee_usd"] == pytest.approx(expected_l2, rel=1e-9)
    assert out["all_in_cost_usd"] >= out["l2_fee_usd"]


# --- D2: env clamps --------------------------------------------------------
@pytest.mark.parametrize("env_val", ["25000000", "100000000", "999999999"])
def test_probe_ceiling_clamped_below_protocol_max(monkeypatch, env_val):
    m = importlib.import_module(MOD)
    monkeypatch.setenv("ARBICORE_GAS_LIMIT_CEILING", env_val)
    cfg = m.BaseAllInCostConfig.from_env()
    assert cfg.gas_limit_ceiling < m.PROTOCOL_GAS_MAX
    assert cfg.gas_limit_ceiling == m.PROTOCOL_GAS_MAX - 1


def test_probe_negative_env_values_floored(monkeypatch):
    m = importlib.import_module(MOD)
    monkeypatch.setenv("ARBICORE_SLIPPAGE_BPS", "-50")
    monkeypatch.setenv("ARBICORE_FLASH_LOAN_FEE_BPS", "-9")
    monkeypatch.setenv("ARBICORE_GAS_PRICE_BUFFER_PCT", "-1")
    monkeypatch.setenv("ARBICORE_GAS_LIMIT_CEILING", "-5")
    monkeypatch.setenv("ARBICORE_MAX_GAS_PRICE_WEI", "-1")
    cfg = m.BaseAllInCostConfig.from_env()
    assert cfg.slippage_bps == 0.0
    assert cfg.flash_loan_fee_bps == 0.0
    assert cfg.gas_price_buffer_pct == 0.0
    assert cfg.gas_limit_ceiling >= 1
    assert cfg.max_gas_price_wei >= 1


def test_probe_no_rpc_returns_none_estimator(monkeypatch):
    m = importlib.import_module(MOD)
    monkeypatch.setattr(
        "arbicore.config.persistent.resolve_rpc_url_from_env", lambda chain: None)
    assert m.make_base_all_in_cost_estimator_from_env() is None
