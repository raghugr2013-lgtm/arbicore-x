"""Stage 13 preflight-revert investigation — encoder fix regression.

Verifies the LIMITED_LIVE broadcast path targets
``FlashLoanReceiver.execute(...)`` on the executor contract, NOT the
Balancer V2 Vault directly.

The old encoder emitted calldata for ``Vault.flashLoan(recipient, ...)``
which triggers the receiver's ``NotAuthorized()`` guard
(selector ``0xea8e4eb5``) because ``_authorized`` is only ``true``
inside an owner-initiated ``execute()`` window.

These tests lock in the corrected behaviour and preserve
:func:`encode_balancer_v2_flash_loan` for future use cases.
"""
from __future__ import annotations

from eth_utils import keccak

from arbicore.execution.calldata import (
    BALANCER_V2_VAULT_BY_CHAIN,
    encode_balancer_v2_flash_loan,
    encode_executor_execute,
    encode_plan_head_call,
)

EXECUTOR = "0x91c0bf28E32b76889BB2B61E1A2dDE9F7e4f3DE3"
WETH_BASE = "0x4200000000000000000000000000000000000006"


# -------------------------------------------------------------------------- #
# encode_executor_execute — direct unit                                       #
# -------------------------------------------------------------------------- #

def test_executor_execute_selector_matches_solidity():
    """``execute(address[],uint256[],bytes)`` selector must match the
    on-chain FlashLoanReceiver ABI."""
    expected_sel = "0x" + keccak(text="execute(address[],uint256[],bytes)")[:4].hex()
    call = encode_executor_execute(
        executor_address=EXECUTOR,
        tokens=[WETH_BASE],
        amounts=[10**16],
        user_data_hex="0x",
    )
    assert call.selector_hex == expected_sel
    assert call.function_signature == "execute(address[],uint256[],bytes)"


def test_executor_execute_targets_the_executor_not_the_vault():
    call = encode_executor_execute(
        executor_address=EXECUTOR,
        tokens=[WETH_BASE], amounts=[10**16], user_data_hex="0x",
    )
    assert call.contract_kind == "flash_loan_receiver"
    # to == EXECUTOR (checksummed), NOT the Balancer Vault
    assert call.contract_address.lower() == EXECUTOR.lower()
    assert call.contract_address != BALANCER_V2_VAULT_BY_CHAIN["base"]


def test_executor_execute_calldata_starts_with_correct_selector():
    call = encode_executor_execute(
        executor_address=EXECUTOR,
        tokens=[WETH_BASE], amounts=[10**16], user_data_hex="0x",
    )
    # Selector = keccak256("execute(address[],uint256[],bytes)")[:4]
    expected_sel = "0x" + keccak(text="execute(address[],uint256[],bytes)")[:4].hex()
    assert call.calldata_hex.startswith(expected_sel)
    assert expected_sel == "0x64ba4bc1"  # locked-in constant for the deployed ABI


def test_executor_execute_rejects_mismatched_arrays():
    import pytest
    with pytest.raises(ValueError, match="equal-length and non-empty"):
        encode_executor_execute(
            executor_address=EXECUTOR, tokens=[WETH_BASE], amounts=[],
        )


def test_executor_execute_rejects_bad_executor_address():
    import pytest
    with pytest.raises(ValueError, match="invalid EVM address"):
        encode_executor_execute(
            executor_address="not-an-address",
            tokens=[WETH_BASE], amounts=[10**16],
        )


# -------------------------------------------------------------------------- #
# encode_plan_head_call — the rewired LIMITED_LIVE entry point                #
# -------------------------------------------------------------------------- #

def _sample_plan(recipient: str = EXECUTOR) -> dict:
    return {
        "chain": "base",
        "flash_loan_provider": "balancer_v2",
        "recipient": recipient,
        "borrow_token": WETH_BASE,
        "borrow_amount_wei": "10000000000000000",  # 0.01 WETH
        "steps": [
            {"kind": "borrow", "token": WETH_BASE, "amount_wei": 10**16},
        ],
        "user_data_hex": "0x",
    }


def test_plan_head_call_now_targets_executor_execute():
    """Regression: LIMITED_LIVE broadcast head must target the executor,
    not the Balancer Vault (which would revert with NotAuthorized())."""
    call = encode_plan_head_call(_sample_plan())
    assert call.contract_kind == "flash_loan_receiver"
    assert call.contract_address.lower() == EXECUTOR.lower()
    assert call.function_signature == "execute(address[],uint256[],bytes)"


def test_plan_head_call_recipient_equals_executor():
    """The ``recipient`` field on the plan resolves to the ``to`` on the tx."""
    call = encode_plan_head_call(_sample_plan(recipient=EXECUTOR))
    assert call.contract_address.lower() == EXECUTOR.lower()


def test_plan_head_call_does_not_call_the_vault_directly():
    call = encode_plan_head_call(_sample_plan())
    assert call.contract_address != BALANCER_V2_VAULT_BY_CHAIN["base"]
    # And the selector is NOT the Vault's flashLoan selector.
    vault_flashloan_sel = "0x" + keccak(
        text="flashLoan(address,address[],uint256[],bytes)",
    )[:4].hex()
    assert call.selector_hex != vault_flashloan_sel


def test_plan_head_call_uses_env_var_when_recipient_missing(monkeypatch):
    """Env-var fallback still works — Phase 10.10 sync writes here."""
    monkeypatch.setenv("ARBICORE_EXECUTOR_ADDRESS_BASE", EXECUTOR)
    plan = _sample_plan()
    plan.pop("recipient")
    call = encode_plan_head_call(plan)
    assert call.contract_address.lower() == EXECUTOR.lower()
    assert call.contract_kind == "flash_loan_receiver"


# -------------------------------------------------------------------------- #
# encode_balancer_v2_flash_loan — preserved for future reuse                  #
# -------------------------------------------------------------------------- #

def test_balancer_v2_flash_loan_still_works_and_targets_the_vault():
    """The direct-vault encoder MUST still exist and still target the
    Vault — used only by future code paths / tests, never by
    :func:`encode_plan_head_call`."""
    call = encode_balancer_v2_flash_loan(
        chain="base", recipient=EXECUTOR,
        tokens=[WETH_BASE], amounts=[10**16], user_data_hex="0x",
    )
    assert call.contract_kind == "balancer_v2_vault"
    assert call.contract_address == BALANCER_V2_VAULT_BY_CHAIN["base"]
    assert call.function_signature == "flashLoan(address,address[],uint256[],bytes)"


def test_balancer_v2_flash_loan_selector_unchanged():
    call = encode_balancer_v2_flash_loan(
        chain="base", recipient=EXECUTOR,
        tokens=[WETH_BASE], amounts=[10**16],
    )
    expected = "0x" + keccak(
        text="flashLoan(address,address[],uint256[],bytes)",
    )[:4].hex()
    assert call.selector_hex == expected
