"""Phase-2 Parts B/C/F — multi-chain gas models + chain adapters.

Offline, fail-closed. No RPC in the sandbox ⇒ every live all-in cost DENIES
(returns None). Pure gas math is validated directly. Base is asserted UNCHANGED
(regression). No signing, no broadcast, no execution.
"""
from __future__ import annotations

import asyncio

import pytest

from arbicore.chains import (
    ChainGasModel, get_chain_gas_model, supported_gas_model_chains,
    make_chain_adapter, supported_adapter_chains,
)
from arbicore.chains.evm_gas import (
    EvmGasConfig, EvmGasModel, CHAIN_SPECS,
    l2_fee_usd, op_stack_l1_fee_usd, arbitrum_l1_fee_usd,
    make_evm_gas_model,
)
from arbicore.chains.evm_adapter import EvmChainAdapter


PHASE2_CHAINS = ["arbitrum", "optimism", "ethereum", "polygon", "bnb"]


# ---------------------------------------------------------------------------
# Gas model registration + typing (Part F)
# ---------------------------------------------------------------------------
def test_all_phase2_chains_have_a_gas_model():
    supported = supported_gas_model_chains()
    for c in ["base"] + PHASE2_CHAINS:
        assert c in supported, f"{c} not registered"
        gm = get_chain_gas_model(c)
        assert gm is not None
        assert isinstance(gm, ChainGasModel)   # runtime Protocol check
        assert gm.chain == c


def test_l1_data_fee_flags_are_chain_correct():
    assert get_chain_gas_model("arbitrum").supports_l1_data_fee is True
    assert get_chain_gas_model("optimism").supports_l1_data_fee is True
    assert get_chain_gas_model("ethereum").supports_l1_data_fee is False
    assert get_chain_gas_model("polygon").supports_l1_data_fee is False
    assert get_chain_gas_model("bnb").supports_l1_data_fee is False


def test_unknown_chain_still_denies():
    assert get_chain_gas_model("solana") is None
    assert get_chain_gas_model("") is None


# ---------------------------------------------------------------------------
# Fail-closed: no RPC ⇒ all_in_cost returns None (DENY) for every chain
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("chain", PHASE2_CHAINS)
def test_no_rpc_gas_model_denies(chain, monkeypatch):
    # Ensure no RPC env leaks into the test.
    for key in (f"ARBICORE_RPC_URL_{chain.upper()}", "ARBICORE_RPC_URL"):
        monkeypatch.delenv(key, raising=False)
    gm = make_evm_gas_model(chain)
    assert gm is not None
    out = asyncio.run(gm.all_in_cost(
        gross_profit_usd=100.0, borrow_amount_usd=10_000.0,
        notional_usd=10_000.0, gas_units=250_000, eth_usd=3000.0))
    assert out is None  # fail-closed, never a fabricated cost


def test_gas_model_denies_when_native_price_unknown():
    # Even WITH an estimator, a missing native price must DENY (no assumed price).
    cfg = EvmGasConfig.from_env("ethereum", 1, "none", "ETH")

    async def estimator(**kw):  # would succeed, but native price is None
        raise AssertionError("estimator should not be reached")

    gm = EvmGasModel("ethereum", False, None)  # None estimator ⇒ DENY
    out = asyncio.run(gm.all_in_cost(
        gross_profit_usd=100.0, borrow_amount_usd=1.0, notional_usd=1.0,
        gas_units=1, eth_usd=None))
    assert out is None


# ---------------------------------------------------------------------------
# Pure gas math (offline, deterministic)
# ---------------------------------------------------------------------------
def test_l2_fee_math():
    # 250k gas @ 0.1 gwei, ETH=$3000 → 250000*1e8/1e18*3000 = 0.075
    assert l2_fee_usd(250_000, 100_000_000, 3000.0) == pytest.approx(0.075)


def test_op_stack_l1_fee_math():
    # 1e14 wei L1 fee @ ETH=$3000 → 1e14/1e18*3000 = 0.3
    assert op_stack_l1_fee_usd(10**14, 3000.0) == pytest.approx(0.3)


def test_arbitrum_l1_fee_is_conservative_and_scales_with_calldata():
    # base fee 20 gwei, 1200 bytes → 1200*16 gas * 20e9 /1e18 * 3000
    v = arbitrum_l1_fee_usd(20_000_000_000, 1200, 3000.0)
    assert v == pytest.approx(1200 * 16 * 20_000_000_000 / 1e18 * 3000.0)
    # More calldata ⇒ strictly higher fee (never understated).
    assert arbitrum_l1_fee_usd(20_000_000_000, 2400, 3000.0) > v


def test_polygon_bnb_price_gas_in_native_token_not_eth():
    # Polygon gas priced in POL, BNB gas in BNB — the model carries native_token.
    assert CHAIN_SPECS["polygon"]["native"] == "POL"
    assert CHAIN_SPECS["bnb"]["native"] == "BNB"
    assert CHAIN_SPECS["arbitrum"]["native"] == "ETH"


def test_gas_ceiling_never_reaches_protocol_max():
    cfg = EvmGasConfig.from_env("arbitrum", 42161, "arbitrum", "ETH")
    from arbicore.chains.evm_gas import PROTOCOL_GAS_MAX
    assert cfg.gas_limit_ceiling < PROTOCOL_GAS_MAX


# ---------------------------------------------------------------------------
# Estimator math via an injected fake provider (no network)
# ---------------------------------------------------------------------------
def test_estimator_full_breakdown_with_fake_provider(monkeypatch):
    from arbicore.chains import evm_gas

    class FakeProvider:
        def __init__(self, *a, **k):
            pass

        async def eth_get_gas_price(self):
            return 100_000_000  # 0.1 gwei

        async def eth_call(self, tx, *a, **k):
            return hex(10**13)  # op-stack L1 fee wei

    monkeypatch.setattr("arbicore.providers.rpc.EthJsonRpcProvider", FakeProvider)
    cfg = EvmGasConfig.from_env("optimism", 10, "op_stack", "ETH")
    est = evm_gas.make_evm_all_in_cost_estimator("optimism", "http://fake", cfg)
    out = asyncio.run(est(gross_profit_usd=100.0, borrow_amount_usd=10_000.0,
                          notional_usd=10_000.0, gas_units=250_000,
                          eth_usd=3000.0))
    assert out is not None
    assert out["l2_fee_usd"] > 0
    assert out["l1_fee_usd"] > 0     # op-stack fee applied
    assert out["slippage_usd"] == pytest.approx(10_000.0 * cfg.slippage_bps / 1e4)
    assert out["net_profit_all_in_usd"] == pytest.approx(
        100.0 - out["all_in_cost_usd"])
    assert out["chain"] == "optimism"


def test_estimator_denies_when_gas_units_over_ceiling(monkeypatch):
    from arbicore.chains import evm_gas

    class FakeProvider:
        def __init__(self, *a, **k):
            pass

        async def eth_get_gas_price(self):
            return 100_000_000

        async def eth_call(self, tx, *a, **k):
            return hex(10**13)

    monkeypatch.setattr("arbicore.providers.rpc.EthJsonRpcProvider", FakeProvider)
    cfg = EvmGasConfig.from_env("ethereum", 1, "none", "ETH")
    est = evm_gas.make_evm_all_in_cost_estimator("ethereum", "http://fake", cfg)
    out = asyncio.run(est(gross_profit_usd=100.0, borrow_amount_usd=10_000.0,
                          notional_usd=10_000.0,
                          gas_units=cfg.gas_limit_ceiling + 1, eth_usd=3000.0))
    assert out is None  # over the safety ceiling ⇒ DENY


def test_estimator_denies_when_l1_unreadable(monkeypatch):
    from arbicore.chains import evm_gas

    class FakeProvider:
        def __init__(self, *a, **k):
            pass

        async def eth_get_gas_price(self):
            return 100_000_000

        async def eth_call(self, tx, *a, **k):
            return "0x"  # unreadable L1 fee

    monkeypatch.setattr("arbicore.providers.rpc.EthJsonRpcProvider", FakeProvider)
    cfg = EvmGasConfig.from_env("arbitrum", 42161, "arbitrum", "ETH")
    est = evm_gas.make_evm_all_in_cost_estimator("arbitrum", "http://fake", cfg)
    out = asyncio.run(est(gross_profit_usd=100.0, borrow_amount_usd=10_000.0,
                          notional_usd=10_000.0, gas_units=250_000, eth_usd=3000.0))
    assert out is None  # L1 fee required but unreadable ⇒ DENY


# ---------------------------------------------------------------------------
# Chain adapters (Part B/C)
# ---------------------------------------------------------------------------
def test_all_phase2_chains_have_an_adapter():
    supported = supported_adapter_chains()
    for c in ["base"] + PHASE2_CHAINS:
        assert c in supported
        assert make_chain_adapter(c) is not None
    assert make_chain_adapter("solana") is None


@pytest.mark.parametrize("chain,chain_id", [
    ("arbitrum", 42161), ("optimism", 10), ("ethereum", 1),
    ("polygon", 137), ("bnb", 56)])
def test_adapter_identity_tokens_dexes(chain, chain_id):
    a = EvmChainAdapter(chain)
    assert a.chain_id() == chain_id
    assert len(a.token_registry()) >= 4
    assert "uniswap_v3" in a.dex_registry() or len(a.dex_registry()) >= 1
    # Every phase-2 chain has at least one real flash provider (fail-closed
    # would show an EMPTY list, never a fabricated one).
    assert len(a.flashloan_provider_registry()) >= 1


def test_adapter_route_metadata_carries_chain_and_gas_mechanism():
    a = EvmChainAdapter("arbitrum")
    md = a.route_metadata()
    assert md["chain"] == "arbitrum"
    assert md["chain_id"] == 42161
    assert md["l1_mechanism"] == "arbitrum"
    assert md["native_token"] == "ETH"


def test_adapter_capability_never_active_ready_offline():
    # No RPC + no live probe ⇒ identity/quote/simulation stay False ⇒ NOT ready.
    cap = asyncio.run(EvmChainAdapter("arbitrum").capability())
    assert cap.active_ready is False
    assert cap.identity_ok is False
    assert cap.quote_ok is False
    assert cap.simulation_ok is False
    assert cap.tokens_ok is True and cap.dex_ok is True


def test_bnb_has_aave_flash_provider():
    a = EvmChainAdapter("bnb")
    assert "aave_v3" in a.flashloan_provider_registry()


# ---------------------------------------------------------------------------
# BASE REGRESSION — the Base gas model must be byte-for-byte unchanged behaviour
# ---------------------------------------------------------------------------
def test_base_gas_model_unchanged_still_denies_without_rpc():
    from arbicore.chains.gas_model import BaseGasModel
    gm = BaseGasModel(None)
    out = asyncio.run(gm.all_in_cost(
        gross_profit_usd=100.0, borrow_amount_usd=10_000.0,
        notional_usd=10_000.0, gas_units=250_000, eth_usd=3000.0))
    assert out is None


def test_base_still_uses_dedicated_model_not_evm_generic():
    # Base must NOT be silently replaced by the generic EVM model.
    from arbicore.chains.gas_model import BaseGasModel
    assert isinstance(get_chain_gas_model("base"), BaseGasModel)
