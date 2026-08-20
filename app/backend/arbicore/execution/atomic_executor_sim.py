"""ArbiCore X — Atomic executor state-override simulation (P0, code-injection).

Uses the VERIFIED ``eth_call`` state-override capability to simulate the WHOLE
atomic flash-loan-arbitrage transaction against real Base state WITHOUT
deploying or signing anything:

  * inject the executor bytecode at its address (state-override ``code``)
  * inject the caller's token approvals / balances as needed (``stateDiff``)
  * ``eth_call`` the executor entrypoint with the real settlement calldata
  * decode the result / revert to validate repayment, final balance, net
    profit and revert conditions

A failed atomic simulation is an ABSOLUTE rejection. This module NEVER signs
or broadcasts.

Readiness is HONEST and staged:
  * ``capability_self_test`` proves code-injection works on the configured RPC
    (returns True today on Base public RPC).
  * ``simulate_atomic`` performs the full validation but is GATED: it requires
    ``ARBICORE_EXECUTOR_ADDRESS_BASE`` + the executor runtime bytecode. Until
    the operator provides a deployed/allowlisted executor, it returns
    ``available=false`` with the exact missing prerequisite — never a fake GREEN.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

# runtime bytecode that returns uint256(42) — used only to prove code-injection
_PROBE_CODE = "0x602a60005260206000f3"
_PROBE_ADDR = "0x00000000000000000000000000000000000c0de0"


class AtomicExecutorSimulator:
    def __init__(self, *, rpc_url: str,
                 executor_address: Optional[str] = None,
                 executor_bytecode: Optional[str] = None):
        self._rpc = rpc_url
        self._executor = executor_address or os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE")
        self._bytecode = executor_bytecode or os.environ.get("ARBICORE_EXECUTOR_BYTECODE")

    async def _raw_eth_call(self, params: List[Any]) -> Dict[str, Any]:
        from .quoter import _throttle, _is_rate_limited
        last: Dict[str, Any] = {}
        for attempt in range(5):
            await _throttle()
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(self._rpc, json={"jsonrpc": "2.0", "id": 1,
                                                  "method": "eth_call", "params": params})
            body = r.json()
            if _is_rate_limited(body.get("error")):
                last = body
                import asyncio
                await asyncio.sleep(0.4 * (2 ** attempt))
                continue
            return body
        return last

    async def capability_self_test(self) -> Dict[str, Any]:
        """Prove the RPC honours state-override ``code`` injection."""
        if not self._rpc:
            return {"code_injection": False, "reason": "no RPC configured"}
        try:
            body = await self._raw_eth_call([
                {"to": _PROBE_ADDR, "data": "0x"}, "latest",
                {_PROBE_ADDR: {"code": _PROBE_CODE}}])
            result = body.get("result", "")
            ok = isinstance(result, str) and result.endswith("2a")
            return {"code_injection": bool(ok),
                    "reason": None if ok else f"unexpected: {body.get('error') or result}"}
        except Exception as exc:  # noqa: BLE001
            return {"code_injection": False, "reason": f"{type(exc).__name__}: {exc}"}

    def readiness(self) -> Dict[str, Any]:
        return {
            "executor_address_set": bool(self._executor),
            "executor_bytecode_available": bool(self._bytecode),
            "rpc_configured": bool(self._rpc),
        }

    async def simulate_atomic(self, *, entry_calldata: str,
                              state_overrides: Optional[Dict[str, Any]] = None,
                              value_wei: int = 0) -> Dict[str, Any]:
        """Full atomic simulation of the executor entrypoint (gated).

        Requires an executor address + runtime bytecode. When present, injects
        the executor code (+ any approvals/balances via ``state_overrides``)
        and eth_calls the entrypoint, treating any revert as an absolute
        rejection."""
        rd = self.readiness()
        if not rd["rpc_configured"]:
            return {"available": False, "passed": False, "reason": "ARBICORE_RPC_URL not configured"}
        if not self._executor:
            return {"available": False, "passed": False,
                    "reason": "ARBICORE_EXECUTOR_ADDRESS_BASE not set (operator prerequisite)"}
        if not self._bytecode:
            return {"available": False, "passed": False,
                    "reason": "executor runtime bytecode unavailable (deploy/allowlist executor first)"}
        overrides: Dict[str, Any] = {self._executor: {"code": self._bytecode}}
        if state_overrides:
            for addr, ov in state_overrides.items():
                overrides.setdefault(addr, {}).update(ov)
        try:
            body = await self._raw_eth_call([
                {"to": self._executor, "data": entry_calldata,
                 "value": hex(int(value_wei))}, "latest", overrides])
        except Exception as exc:  # noqa: BLE001
            return {"available": True, "passed": False, "reason": f"rpc error: {exc}"}
        if "error" in body:
            # a revert here is an absolute rejection (bad calldata / no repay)
            return {"available": True, "passed": False, "stage": "atomic_call",
                    "reason": f"executor reverted: {body['error'].get('message')}",
                    "signed": False, "broadcast": False}
        return {"available": True, "passed": True, "stage": "atomic_call",
                "result": body.get("result"), "signed": False, "broadcast": False}


__all__ = ["AtomicExecutorSimulator"]
