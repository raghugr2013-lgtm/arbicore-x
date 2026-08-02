"""Flash Loan LIMITED_LIVE · userData helper + plan_doc pass-through tests.

Adds coverage for the P0 refinement that unblocks the value-producing
LIMITED_LIVE Flash Loan transaction:

    * :func:`build_user_data_from_hops` — ABI-encodes swap hop sequences
      into the ``userData`` blob consumed by
      ``FlashLoanReceiver.receiveFlashLoan`` on the executor contract.
    * :func:`encode_plan_head_call` — now sources ``userData`` from
      ``plan_doc["user_data_hex"]`` (explicit) or from
      ``plan_doc["hops"]`` + ``plan_doc["profit_recipient"]`` (derived).
    * Env-var fallback for the executor address on chain=base
      (``ARBICORE_EXECUTOR_ADDRESS_BASE``).

Every case is deterministic — same inputs, identical bytes.
"""
from __future__ import annotations

import pytest
from eth_abi import decode as abi_decode

from arbicore.execution.calldata import (
    build_user_data_from_hops,
    encode_balancer_v2_flash_loan,
    encode_executor_execute,
    encode_plan_head_call,
)


TOKEN_WETH_BASE = "0x4200000000000000000000000000000000000006"
TOKEN_USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
TOKEN_DAI_BASE  = "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb"
RECIPIENT_EXEC  = "0x00000000000000000000000000000000cAfeBAbE"
PROFIT_WALLET   = "0x11111111111111111111111111111111DeAdBeEf"


def _plan_base_balancer():
    return {
        "plan_id": "plan-userdata-test",
        "chain": "base",
        "flash_loan_provider": "balancer_v2",
        "borrow_token": TOKEN_WETH_BASE,
        "borrow_amount_wei": 10 ** 17,
        "recipient": RECIPIENT_EXEC,
        "steps": [
            {"kind": "borrow", "token": TOKEN_WETH_BASE,
             "amount_wei": 10 ** 17, "recipient": RECIPIENT_EXEC},
        ],
    }


# ---------------------------------------------------------------------------
# build_user_data_from_hops
# ---------------------------------------------------------------------------

class TestBuildUserDataFromHops:
    def test_encodes_two_hops_roundtrip(self):
        hops = [
            {"token_in": TOKEN_WETH_BASE, "token_out": TOKEN_USDC_BASE,
             "fee_tier_bps": 5, "amount_in_wei": 10 ** 17,
             "amount_out_min_wei": 249_500_000},
            {"token_in": TOKEN_USDC_BASE, "token_out": TOKEN_WETH_BASE,
             "fee_tier_bps": 30, "amount_in_wei": 0,   # forward previous
             "amount_out_min_wei": 100_500_000_000_000_000},
        ]
        hx = build_user_data_from_hops(hops=hops, profit_recipient=PROFIT_WALLET)
        assert hx.startswith("0x") and len(hx) > 2

        raw = bytes.fromhex(hx[2:])
        hops_out, profit_out = abi_decode(
            ["(address,address,uint24,uint256,uint256,uint160)[]", "address"],
            raw,
        )
        assert len(hops_out) == 2
        # fee_ppm = bps × 100
        assert hops_out[0][2] == 5 * 100
        assert hops_out[1][2] == 30 * 100
        # amount_in preserved
        assert hops_out[0][3] == 10 ** 17
        assert hops_out[1][3] == 0
        # profit recipient preserved (case-insensitive)
        assert profit_out.lower() == PROFIT_WALLET.lower()

    def test_deterministic(self):
        hops = [{"token_in": TOKEN_WETH_BASE, "token_out": TOKEN_USDC_BASE,
                 "fee_tier_bps": 5, "amount_in_wei": 10 ** 17,
                 "amount_out_min_wei": 249_500_000}]
        a = build_user_data_from_hops(hops=hops, profit_recipient=PROFIT_WALLET)
        b = build_user_data_from_hops(hops=hops, profit_recipient=PROFIT_WALLET)
        assert a == b

    def test_empty_hops_rejected(self):
        with pytest.raises(ValueError):
            build_user_data_from_hops(hops=[], profit_recipient=PROFIT_WALLET)

    def test_bad_hop_rejected(self):
        with pytest.raises(ValueError):
            build_user_data_from_hops(
                hops=[{"token_in": TOKEN_WETH_BASE, "token_out": TOKEN_USDC_BASE}],
                profit_recipient=PROFIT_WALLET,
            )


# ---------------------------------------------------------------------------
# encode_plan_head_call userData resolution
# ---------------------------------------------------------------------------

class TestPlanHeadUserData:
    def test_default_user_data_is_empty(self):
        """Backward-compat: plan without hops/user_data yields empty userData.
        Stage 13 fix: encoder now targets FlashLoanReceiver.execute() on the
        executor, so the reference builder is `encode_executor_execute`."""
        r = encode_plan_head_call(_plan_base_balancer())
        ref = encode_executor_execute(
            executor_address=RECIPIENT_EXEC,
            tokens=[TOKEN_WETH_BASE], amounts=[10 ** 17],
            user_data_hex="0x",
        )
        assert r.calldata_hex == ref.calldata_hex

    def test_explicit_user_data_hex_passthrough(self):
        plan = _plan_base_balancer()
        payload = build_user_data_from_hops(
            hops=[{"token_in": TOKEN_WETH_BASE, "token_out": TOKEN_USDC_BASE,
                   "fee_tier_bps": 5, "amount_in_wei": 10 ** 17,
                   "amount_out_min_wei": 249_500_000}],
            profit_recipient=PROFIT_WALLET,
        )
        plan["user_data_hex"] = payload
        r = encode_plan_head_call(plan)
        ref = encode_executor_execute(
            executor_address=RECIPIENT_EXEC,
            tokens=[TOKEN_WETH_BASE], amounts=[10 ** 17],
            user_data_hex=payload,
        )
        assert r.calldata_hex == ref.calldata_hex
        # And the calldata MUST differ from the empty-userData baseline.
        empty = encode_plan_head_call(_plan_base_balancer())
        assert r.calldata_hex != empty.calldata_hex

    def test_hops_derive_user_data(self):
        plan = _plan_base_balancer()
        plan["hops"] = [
            {"token_in": TOKEN_WETH_BASE, "token_out": TOKEN_USDC_BASE,
             "fee_tier_bps": 5, "amount_in_wei": 10 ** 17,
             "amount_out_min_wei": 249_500_000},
            {"token_in": TOKEN_USDC_BASE, "token_out": TOKEN_WETH_BASE,
             "fee_tier_bps": 30, "amount_in_wei": 0,
             "amount_out_min_wei": 100_500_000_000_000_000},
        ]
        plan["profit_recipient"] = PROFIT_WALLET
        r = encode_plan_head_call(plan)

        # Same plan with explicit user_data_hex should produce identical bytes.
        payload = build_user_data_from_hops(
            hops=plan["hops"], profit_recipient=PROFIT_WALLET,
        )
        plan_explicit = _plan_base_balancer()
        plan_explicit["user_data_hex"] = payload
        r2 = encode_plan_head_call(plan_explicit)
        assert r.calldata_hex == r2.calldata_hex

    def test_explicit_wins_over_hops(self):
        """user_data_hex is explicit → hops are IGNORED (operator override)."""
        plan = _plan_base_balancer()
        plan["user_data_hex"] = "0xdeadbeef"
        plan["hops"] = [{"token_in": TOKEN_WETH_BASE, "token_out": TOKEN_USDC_BASE,
                          "fee_tier_bps": 5, "amount_in_wei": 10 ** 17,
                          "amount_out_min_wei": 249_500_000}]
        plan["profit_recipient"] = PROFIT_WALLET
        r = encode_plan_head_call(plan)
        ref = encode_executor_execute(
            executor_address=RECIPIENT_EXEC,
            tokens=[TOKEN_WETH_BASE], amounts=[10 ** 17],
            user_data_hex="0xdeadbeef",
        )
        assert r.calldata_hex == ref.calldata_hex


# ---------------------------------------------------------------------------
# Executor address env-var fallback
# ---------------------------------------------------------------------------

class TestExecutorAddressEnvFallback:
    ENV_ADDR = "0x00000000000000000000000000000000feedFACE"

    def test_env_var_used_when_recipient_missing(self, monkeypatch):
        monkeypatch.setenv("ARBICORE_EXECUTOR_ADDRESS_BASE", self.ENV_ADDR)
        plan = _plan_base_balancer()
        plan["recipient"] = ""
        plan["steps"][0]["recipient"] = ""
        r = encode_plan_head_call(plan)
        # Stage 13 fix: encoder now targets FlashLoanReceiver.execute() on the
        # executor, not the Vault.  The env-supplied address becomes the
        # contract_address (tx.to), not an argument inside calldata.
        assert r.contract_kind == "flash_loan_receiver"
        assert r.contract_address.lower() == self.ENV_ADDR.lower()

    def test_missing_recipient_and_env_rejected(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_EXECUTOR_ADDRESS_BASE", raising=False)
        plan = _plan_base_balancer()
        plan["recipient"] = ""
        plan["steps"][0]["recipient"] = ""
        with pytest.raises(ValueError):
            encode_plan_head_call(plan)

    def test_env_ignored_on_non_base_chain(self, monkeypatch):
        monkeypatch.setenv("ARBICORE_EXECUTOR_ADDRESS_BASE", self.ENV_ADDR)
        plan = _plan_base_balancer()
        plan["chain"] = "arbitrum"
        plan["recipient"] = ""
        plan["steps"][0]["recipient"] = ""
        with pytest.raises(ValueError):
            encode_plan_head_call(plan)
