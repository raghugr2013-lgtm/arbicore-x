"""v2.11.7 · Aave V3 calldata encoder unit tests.

Covers the three new encoders added when the executor package landed:

    * :func:`encode_aave_v3_flash_loan_simple`   — direct-to-Pool.
    * :func:`encode_aave_v3_flash_loan`          — direct-to-Pool multi-asset.
    * :func:`encode_executor_execute_aave`       — executor-relayed.

The direct-to-Pool encoders are preserved for future receiver contracts
that pre-authorise themselves in the Aave callback.  The executor-relayed
encoder is what LIMITED_LIVE plans use.

Selector parity is asserted against the values reported by Foundry's
``cast sig`` (see /app/contracts/docs/DEPLOYMENT.md §1).
"""
from __future__ import annotations

import pytest

from arbicore.execution.calldata import (
    AAVE_V3_POOL_BY_CHAIN,
    encode_aave_v3_flash_loan,
    encode_aave_v3_flash_loan_simple,
    encode_executor_execute_aave,
    encode_plan_head_call,
)

_REC = "0x1111111111111111111111111111111111111111"
_TOK = "0x2222222222222222222222222222222222222222"


class TestFlashLoanSimple:
    def test_selector_and_target(self):
        c = encode_aave_v3_flash_loan_simple(
            chain="base", receiver=_REC, asset=_TOK, amount_wei=1_000_000
        )
        assert c.selector_hex == "0x42b0b77c"
        assert c.contract_kind == "aave_v3_pool"
        assert c.contract_address == AAVE_V3_POOL_BY_CHAIN["base"]
        assert c.value_wei == 0
        assert c.calldata_hex.startswith("0x42b0b77c")

    def test_amount_must_be_positive(self):
        with pytest.raises(ValueError):
            encode_aave_v3_flash_loan_simple(
                chain="base", receiver=_REC, asset=_TOK, amount_wei=0
            )

    def test_unsupported_chain_rejected(self):
        with pytest.raises(ValueError):
            encode_aave_v3_flash_loan_simple(
                chain="bnb", receiver=_REC, asset=_TOK, amount_wei=1
            )

    def test_referral_code_upper_bound(self):
        # 0xFFFF is valid, 0x10000 is not.
        encode_aave_v3_flash_loan_simple(
            chain="base", receiver=_REC, asset=_TOK, amount_wei=1,
            referral_code=0xFFFF,
        )
        with pytest.raises(ValueError):
            encode_aave_v3_flash_loan_simple(
                chain="base", receiver=_REC, asset=_TOK, amount_wei=1,
                referral_code=0x10000,
            )

    def test_deterministic_output(self):
        a = encode_aave_v3_flash_loan_simple(
            chain="base", receiver=_REC, asset=_TOK, amount_wei=1_000_000
        )
        b = encode_aave_v3_flash_loan_simple(
            chain="base", receiver=_REC, asset=_TOK, amount_wei=1_000_000
        )
        assert a.calldata_hex == b.calldata_hex


class TestFlashLoanMulti:
    def test_selector_and_target(self):
        c = encode_aave_v3_flash_loan(
            chain="base", receiver=_REC,
            assets=[_TOK], amounts_wei=[1_000_000],
        )
        assert c.selector_hex == "0xab9c4b5d"
        assert c.contract_kind == "aave_v3_pool"
        assert c.contract_address == AAVE_V3_POOL_BY_CHAIN["base"]

    def test_length_mismatch_rejected(self):
        with pytest.raises(ValueError):
            encode_aave_v3_flash_loan(
                chain="base", receiver=_REC,
                assets=[_TOK], amounts_wei=[],
            )

    def test_interest_rate_modes_length_must_match(self):
        with pytest.raises(ValueError):
            encode_aave_v3_flash_loan(
                chain="base", receiver=_REC,
                assets=[_TOK], amounts_wei=[1],
                interest_rate_modes=[0, 0],
            )

    def test_on_behalf_defaults_to_receiver(self):
        c = encode_aave_v3_flash_loan(
            chain="base", receiver=_REC,
            assets=[_TOK], amounts_wei=[1],
        )
        # Receiver address should appear twice in the calldata payload
        # (receiverAddress + onBehalfOf both = _REC when unspecified).
        assert c.calldata_hex.lower().count(_REC[2:].lower()) >= 2


class TestExecutorExecuteAave:
    def test_selector_and_target(self):
        c = encode_executor_execute_aave(
            executor_address=_REC, asset=_TOK, amount_wei=1_000_000
        )
        assert c.selector_hex == "0x4343d8b2"
        assert c.contract_kind == "flash_loan_receiver"
        # Executor is _REC (per docstring), NOT the Aave Pool.
        assert c.contract_address.lower() == _REC.lower()

    def test_amount_must_be_positive(self):
        with pytest.raises(ValueError):
            encode_executor_execute_aave(
                executor_address=_REC, asset=_TOK, amount_wei=0
            )

    def test_deterministic_output(self):
        a = encode_executor_execute_aave(
            executor_address=_REC, asset=_TOK, amount_wei=42,
            user_data_hex="0xdeadbeef",
        )
        b = encode_executor_execute_aave(
            executor_address=_REC, asset=_TOK, amount_wei=42,
            user_data_hex="0xdeadbeef",
        )
        assert a.calldata_hex == b.calldata_hex


class TestPlanHeadAaveRouting:
    """``encode_plan_head_call`` must route aave_v3 plans through
    the executor-relayed encoder (selector 0x4343d8b2), matching the
    behaviour asserted by ``test_wave7_calldata_and_broadcast.py``."""

    def _plan(self):
        return {
            "chain": "base",
            "flash_loan_provider": "aave_v3",
            "recipient": _REC,
            "steps": [{
                "kind": "borrow",
                "token": _TOK,
                "amount_wei": 1_000_000,
            }],
        }

    def test_routes_to_executor_executeAave(self):
        r = encode_plan_head_call(self._plan())
        assert r.selector_hex == "0x4343d8b2"
        assert r.contract_kind == "flash_loan_receiver"
        assert r.contract_address.lower() == _REC.lower()

    def test_missing_recipient_rejected_for_aave(self):
        plan = self._plan()
        plan["recipient"] = ""
        with pytest.raises(ValueError):
            encode_plan_head_call(plan)

    def test_borrow_amount_must_be_positive(self):
        plan = self._plan()
        plan["steps"][0]["amount_wei"] = 0
        with pytest.raises(ValueError):
            encode_plan_head_call(plan)
