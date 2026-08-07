"""Reusable Flash-Loan Technical Validation (engineering self-test).

Proves the Flash-Loan execution engine works END-TO-END on-chain, without
requiring a profitable market opportunity. It runs the smallest practical
Aave V3 flash loan through the deployed ``FlashLoanReceiver``:

    borrow WETH  →  one real Uniswap V3 swap (WETH→USDC)  →  repay
    (amount + 5bps premium)  →  no revert  →  EvidenceBundle.

The executor deliberately rejects a zero-hop flash (`EmptyHops()`), so a
faithful validation includes one real swap leg — exercising the FULL
path (Aave borrow + Uniswap V3 SwapRouter02 + repay). The tiny Aave
premium + swap cost are covered by wrapping a sliver of the signer's own
native ETH into WETH; no external test-token faucet is needed.

Design goals:
  * **Reusable** — one call re-runs the exact proof after any contract
    change, backend upgrade, or new-chain deploy. Exposed as
    ``POST /api/arbicore/wizard/technical-validation``.
  * **Governance-safe** — does NOT touch the strategy mode ladder. The
    trading engine stays in SHADOW. Dedicated engineering signer.
  * **Safe dry mode** — ``execute=false`` uses an ``eth_call`` state
    override to simulate the fully-funded run with zero on-chain cost.

Env:
  ARBICORE_RPC_URL                 — chain RPC (chain id auto-detected)
  ARBICORE_EXECUTOR_ADDRESS_BASE   — deployed FlashLoanReceiver
  ARBICORE_VALIDATION_SIGNER_KEY   — executor OWNER key (testnet only)
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from eth_abi import encode as abi_encode
from eth_account import Account
from eth_utils import to_checksum_address, keccak

from .calldata import encode_executor_execute_aave, build_user_data_from_hops

logger = logging.getLogger("arbicore.execution.technical_validation")

# Canonical WETH (same on Base + Base Sepolia). Its ERC20 balanceOf lives
# at storage slot 3 (WETH9 layout) — used for the dry-run override.
_WETH = "0x4200000000000000000000000000000000000006"
_WETH_BALANCE_SLOT = 3
# USDC on Base Sepolia (a live Uniswap V3 pair vs WETH).
_USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"

_SEL_DEPOSIT = "0xd0e30db0"                       # WETH.deposit()
_SEL_TRANSFER = "0xa9059cbb"                      # ERC20.transfer(address,uint256)
_SEL_BALANCEOF = "0x70a08231"                     # ERC20.balanceOf(address)
_EXEC_COMPLETED_TOPIC = "0x" + keccak(
    text="ExecutionCompleted(bytes32,address,address,uint256,uint256,uint256)"
).hex()
_UA = "Mozilla/5.0 (ArbiCore-X technical-validation)"


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TechnicalValidationError(Exception):
    pass


class TechnicalValidator:
    """Orchestrates one end-to-end Aave-V3 flash-loan self-test."""

    def __init__(self, *, rpc_url: str, executor_address: str,
                 signer_key: Optional[str], db=None):
        if not rpc_url:
            raise TechnicalValidationError("ARBICORE_RPC_URL not configured")
        if not executor_address:
            raise TechnicalValidationError("executor address not configured")
        self._rpc_url = rpc_url
        self._executor = to_checksum_address(executor_address)
        self._signer_key = signer_key
        self._db = db

    # ---- low-level RPC ----------------------------------------------------

    async def _rpc(self, method: str, params: List[Any]) -> Any:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(self._rpc_url,
                             headers={"Content-Type": "application/json",
                                      "User-Agent": _UA},
                             json={"jsonrpc": "2.0", "id": 1,
                                   "method": method, "params": params})
            r.raise_for_status()
            body = r.json()
        if "error" in body:
            raise TechnicalValidationError(f"{method}: {body['error']}")
        return body.get("result")

    async def _chain_id(self) -> int:
        return int(await self._rpc("eth_chainId", []), 16)

    # ---- calldata builders ------------------------------------------------

    def _userdata(self, *, profit_recipient: str, swap_in_wei: int,
                  swap_out_token: str, fee_tier_bps: int) -> str:
        # One real Uniswap V3 hop: WETH -> swap_out_token. amountOutMin=0
        # (profitability is not the goal). Residual is forwarded to owner.
        hop = {
            "token_in": _WETH,
            "token_out": to_checksum_address(swap_out_token),
            "fee_tier_bps": int(fee_tier_bps),
            "amount_in_wei": int(swap_in_wei),
            "amount_out_min_wei": 0,
            "sqrt_price_limit_x96": 0,
        }
        return build_user_data_from_hops(
            hops=[hop], profit_recipient=to_checksum_address(profit_recipient))

    def _execute_aave_calldata(self, *, asset: str, amount_wei: int,
                               user_data_hex: str) -> str:
        return encode_executor_execute_aave(
            executor_address=self._executor, asset=asset,
            amount_wei=amount_wei, user_data_hex=user_data_hex,
        ).calldata_hex

    def _weth_override(self, balance_wei: int) -> Dict[str, Any]:
        key = "0x" + keccak(abi_encode(
            ["address", "uint256"],
            [self._executor, _WETH_BALANCE_SLOT])).hex()
        return {to_checksum_address(_WETH): {
            "stateDiff": {key: "0x" + hex(balance_wei)[2:].zfill(64)}}}

    # ---- preflight (safe, no state change) --------------------------------

    async def preflight(self, *, owner: str, asset: str, amount_wei: int,
                        user_data_hex: str,
                        sim_buffer_wei: Optional[int] = None) -> Dict[str, Any]:
        data = self._execute_aave_calldata(
            asset=asset, amount_wei=amount_wei, user_data_hex=user_data_hex)
        params: List[Any] = [{"from": to_checksum_address(owner),
                              "to": self._executor, "data": data}, "latest"]
        if sim_buffer_wei is not None:
            params.append(self._weth_override(sim_buffer_wei))
        try:
            await self._rpc("eth_call", params)
            return {"ok": True, "revert": None}
        except TechnicalValidationError as exc:
            return {"ok": False, "revert": str(exc)}

    # ---- signing + submit -------------------------------------------------

    async def _send_raw(self, tx: Dict[str, Any]) -> str:
        signed = Account.sign_transaction(tx, self._signer_key)
        raw = signed.raw_transaction.hex()
        return await self._rpc("eth_sendRawTransaction",
                               [raw if raw.startswith("0x") else "0x" + raw])

    async def _wait_receipt(self, tx_hash: str, *, timeout_s: int = 120) -> Dict[str, Any]:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            rcpt = await self._rpc("eth_getTransactionReceipt", [tx_hash])
            if rcpt:
                return rcpt
            time.sleep(3)
        raise TechnicalValidationError(f"receipt timeout for {tx_hash}")

    async def _gas_price(self) -> int:
        return int(int(await self._rpc("eth_gasPrice", []), 16) * 1.25) + 1

    async def _estimate(self, frm: str, to: str, data: str, value: int,
                        fallback: int) -> int:
        try:
            g = int(await self._rpc("eth_estimateGas", [
                {"from": frm, "to": to, "data": data, "value": hex(value)}]), 16)
            return int(g * 1.3)
        except TechnicalValidationError:
            return fallback

    # ---- full run ---------------------------------------------------------

    async def run(self, *, asset: str = _WETH, amount_wei: int = 10**13,
                  swap_in_wei: int = 10**12, fee_tier_bps: int = 5,
                  swap_out_token: str = _USDC_BASE_SEPOLIA,
                  auto_prefund: bool = True, execute: bool = False,
                  ) -> Dict[str, Any]:
        acct = Account.from_key(self._signer_key) if self._signer_key else None
        owner = acct.address if acct else os.environ.get("ARBICORE_VALIDATION_OWNER", "")

        premium = (amount_wei * 5) // 10000 + 1                 # Aave 5 bps
        buffer_wei = swap_in_wei + premium * 2 + swap_in_wei    # swap cost + premium + margin

        user_data = self._userdata(profit_recipient=owner, swap_in_wei=swap_in_wei,
                                    swap_out_token=swap_out_token, fee_tier_bps=fee_tier_bps)

        trace: Dict[str, Any] = {
            "kind": "technical_validation", "provider": "aave_v3",
            "chain_id": await self._chain_id(), "executor": self._executor,
            "asset": to_checksum_address(asset), "amount_wei": int(amount_wei),
            "swap": {"token_in": _WETH, "token_out": to_checksum_address(swap_out_token),
                     "fee_tier_bps": fee_tier_bps, "amount_in_wei": swap_in_wei},
            "owner": owner, "premium_wei": premium, "prefund_buffer_wei": buffer_wei,
            "steps": [], "started_at": _iso(),
        }

        # (1) DRY simulate the fully-funded run via state override (no tx).
        sim = await self.preflight(owner=owner, asset=asset, amount_wei=amount_wei,
                                   user_data_hex=user_data, sim_buffer_wei=buffer_wei)
        trace["steps"].append({"stage": "preflight_funded_sim", **sim})

        if not execute:
            trace["mode"] = "preflight_only"
            trace["engine_ready"] = sim["ok"]
            trace["note"] = ("Dry simulation via eth_call state override "
                             "(fully-funded path). Set execute=true to broadcast.")
            trace["ended_at"] = _iso()
            await self._record(trace)
            return trace

        if not self._signer_key:
            raise TechnicalValidationError(
                "ARBICORE_VALIDATION_SIGNER_KEY not set — cannot broadcast")
        if not sim["ok"]:
            trace["mode"] = "aborted_sim_revert"
            trace["engine_ready"] = False
            trace["ended_at"] = _iso()
            await self._record(trace)
            return trace

        nonce = int(await self._rpc("eth_getTransactionCount", [owner, "pending"]), 16)
        gas_price = await self._gas_price()
        chain_id = trace["chain_id"]

        # (2) prefund executor with the WETH buffer (wrap ETH -> WETH -> transfer).
        if auto_prefund:
            g = await self._estimate(owner, _WETH, _SEL_DEPOSIT, buffer_wei, 80_000)
            h = await self._send_raw({"to": to_checksum_address(_WETH), "value": buffer_wei,
                                      "gas": g, "gasPrice": gas_price, "nonce": nonce,
                                      "chainId": chain_id, "data": _SEL_DEPOSIT})
            r = await self._wait_receipt(h)
            trace["steps"].append({"stage": "wrap_weth", "tx_hash": h,
                                   "status": int(r.get("status", "0x0"), 16),
                                   "gas_used": int(r.get("gasUsed", "0x0"), 16)})
            nonce += 1
            xfer = _SEL_TRANSFER + abi_encode(
                ["address", "uint256"], [self._executor, buffer_wei]).hex()
            g = await self._estimate(owner, _WETH, xfer, 0, 80_000)
            h = await self._send_raw({"to": to_checksum_address(_WETH), "value": 0,
                                      "gas": g, "gasPrice": gas_price, "nonce": nonce,
                                      "chainId": chain_id, "data": xfer})
            r = await self._wait_receipt(h)
            trace["steps"].append({"stage": "prefund_premium", "tx_hash": h,
                                   "status": int(r.get("status", "0x0"), 16),
                                   "gas_used": int(r.get("gasUsed", "0x0"), 16)})
            nonce += 1

        # (3) real preflight against actual chain state, then broadcast.
        pf = await self.preflight(owner=owner, asset=asset, amount_wei=amount_wei,
                                  user_data_hex=user_data)
        trace["steps"].append({"stage": "preflight_onchain", **pf})
        if not pf["ok"]:
            trace["mode"] = "aborted_preflight_revert"
            trace["engine_ready"] = False
            trace["ended_at"] = _iso()
            await self._record(trace)
            return trace

        data = self._execute_aave_calldata(
            asset=asset, amount_wei=amount_wei, user_data_hex=user_data)
        g = await self._estimate(owner, self._executor, data, 0, 1_200_000)
        tx_hash = await self._send_raw({"to": self._executor, "value": 0, "gas": g,
                                        "gasPrice": gas_price, "nonce": nonce,
                                        "chainId": chain_id, "data": data})
        rcpt = await self._wait_receipt(tx_hash)
        status = int(rcpt.get("status", "0x0"), 16)
        gas_used = int(rcpt.get("gasUsed", "0x0"), 16)
        logs = rcpt.get("logs", []) or []
        exec_completed = any(
            (lg.get("topics") or [None])[0] == _EXEC_COMPLETED_TOPIC
            and to_checksum_address(lg.get("address")) == self._executor
            for lg in logs)
        trace["steps"].append({
            "stage": "flash_loan_broadcast", "tx_hash": tx_hash, "status": status,
            "gas_used": gas_used, "block_number": int(rcpt.get("blockNumber", "0x0"), 16),
            "log_count": len(logs), "execution_completed_event": exec_completed})

        trace["mode"] = "executed"
        trace["tx_hash"] = tx_hash
        trace["gas_used"] = gas_used
        trace["engine_ready"] = bool(status == 1 and exec_completed)
        trace["ended_at"] = _iso()
        trace["evidence_bundle"] = self._evidence_bundle(trace)
        await self._record(trace)
        return trace

    # ---- evidence + persistence ------------------------------------------

    @staticmethod
    def _evidence_bundle(trace: Dict[str, Any]) -> Dict[str, Any]:
        ok = bool(trace.get("engine_ready"))
        return {
            "kind": "technical_validation", "provider": "aave_v3",
            "chain_id": trace.get("chain_id"), "executor": trace.get("executor"),
            "asset": trace.get("asset"), "amount_wei": trace.get("amount_wei"),
            "premium_wei": trace.get("premium_wei"), "swap": trace.get("swap"),
            "tx_hash": trace.get("tx_hash"), "gas_used": trace.get("gas_used"),
            "aave_borrow_ok": ok, "swap_executed_ok": ok, "repayment_ok": ok,
            "no_contract_revert": ok,
            "execution_completed_event": any(
                s.get("execution_completed_event") for s in trace.get("steps", [])),
            "generated_at": _iso(),
        }

    async def _record(self, trace: Dict[str, Any]) -> None:
        if self._db is None:
            return
        try:
            await self._db["arbicore_technical_validations"].insert_one(
                {**trace, "recorded_at": _iso()})
            trace.pop("_id", None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("technical_validation record failed: %s", exc)
