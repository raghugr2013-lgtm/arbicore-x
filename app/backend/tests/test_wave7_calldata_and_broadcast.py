"""Wave 7A + 7C · Unit tests for calldata encoder, wallet balance,
wallet health, and broadcaster gate ladder (offline)."""
from __future__ import annotations

import asyncio

import pytest

from arbicore.execution.calldata import (
    EncodedCall,
    encode_balancer_v2_flash_loan,
    encode_plan_head_call,
    encode_uniswap_v3_exact_input_single,
)


def _run(coro):
    return asyncio.run(coro)


TOKEN_WETH_BASE = "0x4200000000000000000000000000000000000006"
TOKEN_USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
RECIPIENT = "0x1234567890123456789012345678901234567890"


class TestBalancerV2Calldata:
    def test_selector_is_known(self):
        r = encode_balancer_v2_flash_loan(
            chain="base", recipient=RECIPIENT,
            tokens=[TOKEN_WETH_BASE], amounts=[10 ** 17],
        )
        # keccak("flashLoan(address,address[],uint256[],bytes)")[:4]
        assert r.selector_hex.lower() == "0x5c38449e"
        assert r.contract_kind == "balancer_v2_vault"
        assert r.contract_address.lower() == "0xba12222222228d8ba445958a75a0704d566bf2c8"

    def test_deterministic(self):
        a = encode_balancer_v2_flash_loan(
            chain="base", recipient=RECIPIENT,
            tokens=[TOKEN_WETH_BASE], amounts=[10 ** 17],
        )
        b = encode_balancer_v2_flash_loan(
            chain="base", recipient=RECIPIENT,
            tokens=[TOKEN_WETH_BASE], amounts=[10 ** 17],
        )
        assert a.calldata_hex == b.calldata_hex

    def test_bad_length_rejected(self):
        with pytest.raises(ValueError):
            encode_balancer_v2_flash_loan(
                chain="base", recipient=RECIPIENT,
                tokens=[TOKEN_WETH_BASE, TOKEN_USDC_BASE], amounts=[10 ** 17],
            )

    def test_unknown_chain_rejected(self):
        with pytest.raises(ValueError):
            encode_balancer_v2_flash_loan(
                chain="solana", recipient=RECIPIENT,
                tokens=[TOKEN_WETH_BASE], amounts=[10 ** 17],
            )


class TestUniswapV3Calldata:
    def test_selector_matches_known(self):
        r = encode_uniswap_v3_exact_input_single(
            chain="base", token_in=TOKEN_WETH_BASE, token_out=TOKEN_USDC_BASE,
            fee_tier_bps=5, recipient=RECIPIENT,
            amount_in_wei=10 ** 17, amount_out_minimum_wei=249_500_000,
        )
        assert r.selector_hex.lower() == "0x04e45aaf"
        assert r.contract_kind == "uniswap_v3_router_02"
        assert r.contract_address.lower() == "0x2626664c2603336e57b271c5c0b26f421741e481"

    def test_fee_tier_multiplied_by_100(self):
        # Fee tier 5 bps → 500 in Uniswap uint24 units.
        a = encode_uniswap_v3_exact_input_single(
            chain="base", token_in=TOKEN_WETH_BASE, token_out=TOKEN_USDC_BASE,
            fee_tier_bps=5, recipient=RECIPIENT,
            amount_in_wei=10 ** 17, amount_out_minimum_wei=249_500_000,
        )
        b = encode_uniswap_v3_exact_input_single(
            chain="base", token_in=TOKEN_WETH_BASE, token_out=TOKEN_USDC_BASE,
            fee_tier_bps=30, recipient=RECIPIENT,
            amount_in_wei=10 ** 17, amount_out_minimum_wei=249_500_000,
        )
        assert a.calldata_hex != b.calldata_hex


class TestPlanHeadEncoder:
    def _plan(self):
        return {
            "plan_id": "plan-test",
            "chain": "base",
            "flash_loan_provider": "balancer_v2",
            "borrow_token": TOKEN_WETH_BASE,
            "borrow_amount_wei": 10 ** 17,
            "recipient": RECIPIENT,
            "steps": [
                {"kind": "borrow", "token": TOKEN_WETH_BASE,
                 "amount_wei": 10 ** 17, "recipient": RECIPIENT},
            ],
        }

    def test_encodes_executor_execute_not_vault(self):
        """Stage 13 fix: LIMITED_LIVE plan heads target FlashLoanReceiver.execute()
        on the executor, not Balancer Vault directly (which would revert with
        NotAuthorized() at the callback guard).  See test_stage13_executor_execute_encoder.py
        for the full regression suite.
        """
        r = encode_plan_head_call(self._plan())
        assert r.contract_kind == "flash_loan_receiver"
        assert r.selector_hex.lower() == "0x64ba4bc1"  # execute(address[],uint256[],bytes)
        assert r.contract_address.lower() == RECIPIENT.lower()

    def test_aave_head_encodes_executor_executeAave(self):
        """v2.11.7: Aave V3 flash heads unlock once the executor is
        deployment-ready. Plan heads with ``flash_loan_provider ==
        "aave_v3"`` now target the executor's ``executeAave(address,
        uint256, bytes)`` entry point (selector 0x4343d8b2), not the
        Aave Pool directly.
        """
        plan = self._plan()
        plan["flash_loan_provider"] = "aave_v3"
        r = encode_plan_head_call(plan)
        assert r.contract_kind == "flash_loan_receiver"
        assert r.selector_hex.lower() == "0x4343d8b2"
        assert r.contract_address.lower() == RECIPIENT.lower()

    def test_unknown_flash_provider_rejected(self):
        plan = self._plan()
        plan["flash_loan_provider"] = "morpho_blue"
        with pytest.raises(NotImplementedError):
            encode_plan_head_call(plan)

    def test_missing_recipient_rejected(self):
        plan = self._plan()
        plan["recipient"] = ""
        plan["steps"][0]["recipient"] = ""
        with pytest.raises(ValueError):
            encode_plan_head_call(plan)


# ---------------------------------------------------------------------------
# Wallet balance reader — offline path only (no network)
# ---------------------------------------------------------------------------

class TestWalletBalanceReader:
    def test_returns_error_when_no_rpc(self, monkeypatch):
        from arbicore.execution.wallet_balance import WalletBalanceReader
        monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
        monkeypatch.delenv("ARBICORE_RPC_URL_BASE", raising=False)
        # Patch default RPC list to something unreachable.
        import arbicore.execution.wallet_balance as wb_mod
        monkeypatch.setattr(wb_mod, "DEFAULT_RPC_URLS",
                            {"base": ["http://127.0.0.1:1"]})
        reader = WalletBalanceReader(timeout_s=0.5)
        reading = _run(reader.read(chain="base", address=RECIPIENT))
        assert reading.ok is False
        assert reading.balance_wei == 0
        assert reading.rpc_endpoint_redacted is None


# ---------------------------------------------------------------------------
# LimitedLiveBroadcaster — gate ladder with fakes (no network)
# ---------------------------------------------------------------------------

class _FakeMode:
    def __init__(self, mode): self._mode = mode
    async def get(self, s): return {"strategy": s, "mode": self._mode}


class _FakeKS:
    def __init__(self, engaged=False, reason=None):
        self._engaged, self._reason = engaged, reason
    async def guard(self):
        if self._engaged:
            from arbicore.execution.kill_switch import KillSwitchEngagedError
            raise KillSwitchEngagedError(self._reason or "engaged")


class _FakeWallets:
    def __init__(self, w): self._w = w
    async def get(self, wid): return self._w


class _FakeSecrets:
    def __init__(self, m): self._m = m
    async def resolve(self, h): return self._m


class _FakeAlloc:
    def __init__(self, approved=True, reason="ok"):
        self._approved, self._reason = approved, reason
    async def evaluate(self, **kw):
        class D:
            approved = self._approved
            approved_usd = 100.0
            binding_constraint = "per_plan_cap" if self._approved else "min_profit"
            reasons = [self._reason]
        d = D()
        d.approved = self._approved
        return d


def _sample_plan():
    return {
        "plan_id": "plan-1", "strategy": "flash_loan_arbitrage",
        "chain": "base", "flash_loan_provider": "balancer_v2",
        "borrow_token": TOKEN_WETH_BASE, "borrow_amount_wei": 10 ** 17,
        "borrow_amount_usd": 250.0, "recipient": RECIPIENT,
        "signer_wallet_id": "wallet-gas-1",
        "steps": [{"kind": "borrow", "token": TOKEN_WETH_BASE,
                   "amount_wei": 10 ** 17, "recipient": RECIPIENT}],
    }


class TestBroadcasterGateLadder:
    def _mk(self, *, mode="SHADOW", engaged=False, wallet=None, secret=None,
             approved=True):
        from arbicore.execution.broadcast import LimitedLiveBroadcaster
        return LimitedLiveBroadcaster(
            kill_switch=_FakeKS(engaged=engaged),
            mode_repo=_FakeMode(mode),
            wallet_registry=_FakeWallets(wallet),
            secret_registry=_FakeSecrets(secret),
            capital_allocator=_FakeAlloc(approved=approved),
        )

    # A stable, non-secret 32-byte dev key.  NEVER used against mainnet.
    DEV_PRIV = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"

    def test_shadow_mode_denies_broadcast(self):
        b = self._mk(mode="SHADOW",
                      wallet={"execution_role": "gas",
                              "secret_handle_id": "h1",
                              "address": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"},
                      secret=self.DEV_PRIV)
        r = _run(b.broadcast_plan(_sample_plan(), confirm=True))
        assert r.broadcast_sent is False
        assert r.gate_ladder["mode"] == "DENIED"
        assert any("mode_gate" in x for x in r.denied_reasons)

    def test_kill_switch_denies_broadcast(self):
        b = self._mk(mode="LIMITED_LIVE", engaged=True,
                      wallet={"execution_role": "gas",
                              "secret_handle_id": "h1",
                              "address": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"},
                      secret=self.DEV_PRIV)
        r = _run(b.broadcast_plan(_sample_plan(), confirm=True))
        assert r.gate_ladder["kill_switch"] == "DENIED"
        assert r.broadcast_sent is False

    def test_missing_confirm_holds(self):
        b = self._mk(mode="LIMITED_LIVE",
                      wallet={"execution_role": "gas",
                              "secret_handle_id": "h1",
                              "address": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"},
                      secret=self.DEV_PRIV)
        # No confirm — even with all other gates PASS, broadcast held.
        r = _run(b.broadcast_plan(_sample_plan(), confirm=False))
        assert r.broadcast_sent is False
        assert "operator_confirm" in r.gate_ladder
        assert r.gate_ladder["operator_confirm"] == "DENIED"

    def test_secret_address_mismatch_denies(self):
        b = self._mk(mode="LIMITED_LIVE",
                      wallet={"execution_role": "gas",
                              "secret_handle_id": "h1",
                              "address": "0x0000000000000000000000000000000000000001"},
                      secret=self.DEV_PRIV)
        r = _run(b.broadcast_plan(_sample_plan(), confirm=True))
        assert r.gate_ladder["secret_resolution"] == "DENIED"
        assert any("secret_resolution" in x for x in r.denied_reasons)

    def test_capital_policy_denies(self):
        b = self._mk(mode="LIMITED_LIVE", approved=False,
                      wallet={"execution_role": "gas",
                              "secret_handle_id": "h1",
                              "address": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"},
                      secret=self.DEV_PRIV)
        r = _run(b.broadcast_plan(_sample_plan(), confirm=True))
        assert r.gate_ladder["capital_policy"] == "DENIED"

    def test_receipt_never_leaks_priv_key(self):
        b = self._mk(mode="SHADOW",
                      wallet={"execution_role": "gas",
                              "secret_handle_id": "h1",
                              "address": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"},
                      secret=self.DEV_PRIV)
        r = _run(b.broadcast_plan(_sample_plan(), confirm=True))
        import json
        raw = json.dumps(r.to_dict())
        assert self.DEV_PRIV not in raw
        assert "private_key" not in raw
