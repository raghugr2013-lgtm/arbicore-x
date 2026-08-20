"""ArbiCore X — Executor entrypoint calldata + Anvil fork harness (scaffold).

No signing/broadcast. Builds the executor entrypoint calldata for atomic
simulation and prepares a fork harness that is READY to run the moment an
archive RPC + anvil are available. Nothing here is marked GREEN without a real
run.
"""
from __future__ import annotations

import os
import shutil
from typing import Any, Dict, List, Optional

from eth_abi import encode as abi_encode
from eth_utils import keccak, to_checksum_address

# Default executor entrypoint (configurable). Plug-and-play: override via
# ARBICORE_EXECUTOR_ENTRYPOINT_SIG once the deployed ABI is confirmed.
_DEFAULT_ENTRY_SIG = os.environ.get(
    "ARBICORE_EXECUTOR_ENTRYPOINT_SIG",
    "executeArbitrage(address,uint256,address,bytes)")


def _selector(sig: str) -> bytes:
    return keccak(text=sig)[:4]


def build_executor_entrypoint_calldata(
    *, borrow_token: str, borrow_amount_wei: int, settlement_target: str,
    settlement_calldata_hex: str, entry_sig: str = _DEFAULT_ENTRY_SIG,
) -> Dict[str, Any]:
    """Encode the executor entrypoint that triggers:
    flash borrow → (settlement swaps via settlement_calldata) → repay.

    Signature default: executeArbitrage(borrowToken, borrowAmount,
    settlementTarget, settlementCalldata). Never signed/broadcast."""
    settlement_bytes = bytes.fromhex(settlement_calldata_hex[2:]
                                     if settlement_calldata_hex.startswith("0x")
                                     else settlement_calldata_hex)
    args = abi_encode(
        ["address", "uint256", "address", "bytes"],
        [to_checksum_address(borrow_token), int(borrow_amount_wei),
         to_checksum_address(settlement_target), settlement_bytes])
    data = "0x" + (_selector(entry_sig) + args).hex()
    return {"entry_signature": entry_sig, "selector": "0x" + _selector(entry_sig).hex(),
            "calldata": data, "borrow_token": to_checksum_address(borrow_token),
            "borrow_amount_wei": int(borrow_amount_wei),
            "settlement_target": to_checksum_address(settlement_target),
            "signed": False, "broadcast": False}


class AnvilForkHarness:
    """Prepares a controllable Base fork. Ready-to-run, gated on archive RPC +
    the ``anvil`` binary. Never claims validation without an actual run."""

    def __init__(self, *, fork_rpc_url: Optional[str] = None):
        self._fork_rpc = fork_rpc_url or os.environ.get("ARBICORE_ARCHIVE_RPC_URL") \
            or os.environ.get("ARBICORE_FORK_RPC_URL")

    def readiness(self) -> Dict[str, Any]:
        anvil = shutil.which("anvil")
        return {
            "anvil_installed": bool(anvil),
            "anvil_path": anvil,
            "fork_rpc_configured": bool(self._fork_rpc),
            "ready_to_run": bool(anvil and self._fork_rpc),
            "reason": (None if (anvil and self._fork_rpc) else
                       ("anvil binary not installed" if not anvil
                        else "archive/fork RPC not configured (ARBICORE_ARCHIVE_RPC_URL)")),
        }

    async def run_fork_validation(self, *, block_number: Optional[int] = None,
                                  checks: Optional[List[str]] = None) -> Dict[str, Any]:
        rd = self.readiness()
        if not rd["ready_to_run"]:
            return {"ran": False, "passed": False, "reason": rd["reason"]}
        # Real fork execution is wired here once infra lands. Until an actual
        # fork run completes we NEVER return passed=True (no fake GREEN).
        return {"ran": False, "passed": False,
                "reason": "fork run not yet executed against configured infra"}


__all__ = ["build_executor_entrypoint_calldata", "AnvilForkHarness"]
