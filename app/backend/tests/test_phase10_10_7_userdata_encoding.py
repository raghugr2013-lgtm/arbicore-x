"""Phase 10.10.7 — regression: encoder must build a non-empty ``userData``
from ``plan.steps[kind=swap]`` when the top-level ``hops`` array is
absent, using the signer address as ``profitRecipient``.

Failure mode this test guards against: the encoder previously fell back
to ``userData = "0x"``, causing the on-chain ``receiveFlashLoan``
callback to bare-``revert()`` at the ``abi.decode(userData, (SwapHop[],
address))`` line — a REVERT(0,0) that erases the intended Uniswap V3
slippage revert path.

Proven by direct Alchemy ``debug_traceCall`` on 2026-08-02 (see
``docs/PHASE10_10_7_ROOT_CAUSE.md``): all reverted frames returned
empty output, structLogs terminated in
``RETURNDATASIZE / PUSH0 / REVERT(0,0)``.
"""
from __future__ import annotations

import pytest
from eth_abi import decode as abi_decode
from eth_utils import function_signature_to_4byte_selector

from arbicore.execution.calldata import (
    encode_plan_head_call,
    build_user_data_from_hops,
    _extract_hops_from_steps,
)


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #

WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
EXECUTOR = "0x91c0bf28E32b76889BB2B61E1A2dDE9F7e4f3DE3"
SIGNER = "0x998d6efF2b28b72c44f7a334c42678eb4cCaad25"


def _plan_with_swap_steps() -> dict:
    """Replica of the Preset A "Intentional Revert" plan the operator
    broadcast on 2026-08-02 — WETH → USDC → WETH, with an unreachable
    ``amountOutMinimum`` on the second hop."""
    return {
        "plan_id": "test-plan",
        "strategy": "flash_loan_arbitrage",
        "chain": "base",
        "flash_loan_provider": "balancer_v2",
        "borrow_token": WETH,
        "borrow_amount_wei": 10_000_000_000_000_000,  # 0.01 WETH
        "recipient": EXECUTOR,
        "signer_wallet_id": "base-gas-wallet-1-uokc4p",
        "steps": [
            {
                "step_index": 0, "kind": "borrow",
                "provider": "balancer_v2", "chain": "base",
                "contract_address": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
                "args": ["base-gas-wallet-1-uokc4p", [WETH],
                         [10_000_000_000_000_000], "0x"],
            },
            {
                "step_index": 1, "kind": "swap",
                "provider": "uniswap_v3", "chain": "base",
                "contract_address": "0x2626664c2603336E57B271c5C0b26F421741e481",
                "args": [{
                    "tokenIn": WETH, "tokenOut": USDC,
                    "fee": 500,
                    "recipient": "__signer_wallet__",
                    "amountIn": 10_000_000_000_000_000,
                    "amountOutMinimum": 24_500_000,
                    "sqrtPriceLimitX96": 0,
                }],
            },
            {
                "step_index": 2, "kind": "swap",
                "provider": "uniswap_v3", "chain": "base",
                "contract_address": "0x2626664c2603336E57B271c5C0b26F421741e481",
                "args": [{
                    "tokenIn": USDC, "tokenOut": WETH,
                    "fee": 500,
                    "recipient": "__signer_wallet__",
                    "amountIn": 24_500_000,
                    # 9 WETH — unreachable → intentional slippage revert
                    "amountOutMinimum": 9_000_000_000_000_000_000,
                    "sqrtPriceLimitX96": 0,
                }],
            },
        ],
    }


# --------------------------------------------------------------------------- #
# _extract_hops_from_steps                                                    #
# --------------------------------------------------------------------------- #

class TestExtractHopsFromSteps:
    def test_lifts_two_uniswap_swaps(self):
        plan = _plan_with_swap_steps()
        hops = _extract_hops_from_steps(plan["steps"])
        assert len(hops) == 2
        assert hops[0]["token_in"] == WETH
        assert hops[0]["token_out"] == USDC
        # fee=500 ppm → 5 bps
        assert hops[0]["fee_tier_bps"] == 5
        assert hops[0]["amount_in_wei"] == 10_000_000_000_000_000
        assert hops[0]["amount_out_min_wei"] == 24_500_000
        assert hops[1]["amount_out_min_wei"] == 9_000_000_000_000_000_000

    def test_ignores_borrow_steps(self):
        plan = _plan_with_swap_steps()
        hops = _extract_hops_from_steps(plan["steps"])
        # First step is borrow — must be skipped
        assert all(h["token_in"] != "base-gas-wallet-1-uokc4p" for h in hops)

    def test_empty_steps(self):
        assert _extract_hops_from_steps([]) == []

    def test_swap_without_args_is_skipped(self):
        assert _extract_hops_from_steps([{"kind": "swap", "args": []}]) == []

    def test_swap_with_missing_fee_is_skipped(self):
        step = {"kind": "swap", "args": [{"tokenIn": WETH, "tokenOut": USDC}]}
        assert _extract_hops_from_steps([step]) == []


# --------------------------------------------------------------------------- #
# encode_plan_head_call — the actual regression                               #
# --------------------------------------------------------------------------- #

class TestEncoderUserDataFromSteps:
    def test_userdata_is_non_empty_when_steps_and_signer_present(self):
        plan = _plan_with_swap_steps()
        encoded = encode_plan_head_call(plan, signer_address=SIGNER)
        # Selector must be execute(address[],uint256[],bytes)
        expected_sel = "0x" + function_signature_to_4byte_selector(
            "execute(address[],uint256[],bytes)"
        ).hex()
        assert encoded.calldata_hex.startswith(expected_sel)

        # Decode the outer call and extract userData
        body = bytes.fromhex(encoded.calldata_hex[10:])
        tokens, amounts, user_data = abi_decode(
            ["address[]", "uint256[]", "bytes"], body,
        )
        assert [t.lower() for t in tokens] == [WETH.lower()]
        assert list(amounts) == [10_000_000_000_000_000]
        # THE regression assertion: userData MUST NOT be empty.
        assert len(user_data) > 0, (
            "userData is empty — receiveFlashLoan will REVERT(0,0) "
            "at abi.decode.  Encoder failed to lift swap steps."
        )

    def test_userdata_decodes_to_hops_and_profit_recipient(self):
        plan = _plan_with_swap_steps()
        encoded = encode_plan_head_call(plan, signer_address=SIGNER)
        body = bytes.fromhex(encoded.calldata_hex[10:])
        _, _, user_data = abi_decode(
            ["address[]", "uint256[]", "bytes"], body,
        )
        # userData ABI = (SwapHop[], address) where
        # SwapHop = (address,address,uint24,uint256,uint256,uint160)
        hops, profit_recipient = abi_decode(
            ["(address,address,uint24,uint256,uint256,uint160)[]", "address"],
            user_data,
        )
        assert len(hops) == 2
        # Hop 0: WETH → USDC @ 500 ppm, 0.01 WETH in, 24.5 USDC min out
        h0 = hops[0]
        assert h0[0].lower() == WETH.lower()
        assert h0[1].lower() == USDC.lower()
        assert h0[2] == 500  # fee ppm
        assert h0[3] == 10_000_000_000_000_000
        assert h0[4] == 24_500_000
        # Hop 1: USDC → WETH @ 500 ppm, 24.5 USDC in, 9 WETH min out (unreachable)
        h1 = hops[1]
        assert h1[0].lower() == USDC.lower()
        assert h1[1].lower() == WETH.lower()
        assert h1[4] == 9_000_000_000_000_000_000
        # Profit recipient = signer wallet
        assert profit_recipient.lower() == SIGNER.lower()

    def test_encoder_still_empties_userdata_without_signer_or_steps(self):
        """Backward compat: a plan with no hops/steps and no signer
        still returns userData=0x (previous behaviour)."""
        plan = {
            "flash_loan_provider": "balancer_v2",
            "chain": "base",
            "recipient": EXECUTOR,
            "borrow_token": WETH,
            "borrow_amount_wei": 1,
            "steps": [{"kind": "borrow", "args": []}],
        }
        encoded = encode_plan_head_call(plan)  # no signer
        body = bytes.fromhex(encoded.calldata_hex[10:])
        _, _, user_data = abi_decode(
            ["address[]", "uint256[]", "bytes"], body,
        )
        assert len(user_data) == 0

    def test_explicit_user_data_hex_wins_over_steps(self):
        """When plan_doc.user_data_hex is explicitly set, it MUST NOT
        be overwritten by the auto-lift path."""
        custom = build_user_data_from_hops(
            hops=[{
                "token_in": WETH, "token_out": USDC,
                "fee_tier_bps": 5, "amount_in_wei": 1,
                "amount_out_min_wei": 1, "sqrt_price_limit_x96": 0,
            }],
            profit_recipient=SIGNER,
        )
        plan = _plan_with_swap_steps()
        plan["user_data_hex"] = custom
        encoded = encode_plan_head_call(plan, signer_address=SIGNER)
        body = bytes.fromhex(encoded.calldata_hex[10:])
        _, _, user_data = abi_decode(
            ["address[]", "uint256[]", "bytes"], body,
        )
        # The custom userData had exactly ONE hop; the auto-lift path
        # would have produced two.  Presence of exactly one confirms
        # the explicit override was honoured.
        hops, _ = abi_decode(
            ["(address,address,uint24,uint256,uint256,uint160)[]", "address"],
            user_data,
        )
        assert len(hops) == 1

    def test_explicit_plan_hops_wins_over_steps(self):
        """Top-level plan.hops (legacy path) still wins over auto-lift."""
        plan = _plan_with_swap_steps()
        plan["hops"] = [{
            "token_in": WETH, "token_out": USDC,
            "fee_tier_bps": 5, "amount_in_wei": 42,
            "amount_out_min_wei": 42, "sqrt_price_limit_x96": 0,
        }]
        plan["profit_recipient"] = SIGNER
        encoded = encode_plan_head_call(plan, signer_address="0x0000000000000000000000000000000000000000")
        body = bytes.fromhex(encoded.calldata_hex[10:])
        _, _, user_data = abi_decode(
            ["address[]", "uint256[]", "bytes"], body,
        )
        hops, pr = abi_decode(
            ["(address,address,uint24,uint256,uint256,uint160)[]", "address"],
            user_data,
        )
        # Legacy hops path produced exactly one hop with amountIn=42
        assert len(hops) == 1
        assert hops[0][3] == 42
        assert pr.lower() == SIGNER.lower()
