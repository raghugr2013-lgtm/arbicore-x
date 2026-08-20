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

    def __init__(self, *, fork_rpc_url: Optional[str] = None,
                 port: int = 8546):
        self._fork_rpc = fork_rpc_url or os.environ.get("ARBICORE_ARCHIVE_RPC_URL") \
            or os.environ.get("ARBICORE_FORK_RPC_URL")
        self._port = int(os.environ.get("ARBICORE_ANVIL_PORT", port))

    def readiness(self) -> Dict[str, Any]:
        anvil = shutil.which("anvil")
        return {
            "anvil_installed": bool(anvil),
            "anvil_path": anvil,
            "fork_rpc_configured": bool(self._fork_rpc),
            "port": self._port,
            "ready_to_run": bool(anvil and self._fork_rpc),
            "reason": (None if (anvil and self._fork_rpc) else
                       ("anvil binary not installed" if not anvil
                        else "archive/fork RPC not configured (ARBICORE_ARCHIVE_RPC_URL)")),
        }

    async def _rpc(self, url: str, method: str, params: List[Any]) -> Dict[str, Any]:
        import httpx
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(url, json={"jsonrpc": "2.0", "id": 1,
                                        "method": method, "params": params})
        return r.json()

    async def run_fork_validation(self, *, block_number: Optional[int] = None,
                                  checks: Optional[List[str]] = None) -> Dict[str, Any]:
        """Spawn a real anvil fork, run read-only validation eth_calls against
        it, then tear it down. Returns passed=True ONLY after real checks run
        against the live fork — never a config-presence GREEN."""
        import asyncio

        rd = self.readiness()
        if not rd["ready_to_run"]:
            return {"ran": False, "passed": False, "reason": rd["reason"]}

        local_url = f"http://127.0.0.1:{self._port}"
        cmd = [rd["anvil_path"], "--fork-url", self._fork_rpc,
               "--port", str(self._port), "--silent"]
        if block_number is not None:
            cmd += ["--fork-block-number", str(int(block_number))]

        proc: Optional[Any] = None
        evidence: Dict[str, Any] = {"fork_url_masked": True, "block_number": block_number}
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL)

            # Wait for the fork JSON-RPC to accept connections.
            up = False
            for _ in range(40):  # ~20s max
                if proc.returncode is not None:
                    return {"ran": False, "passed": False,
                            "reason": f"anvil exited early (code {proc.returncode})"}
                try:
                    body = await self._rpc(local_url, "eth_blockNumber", [])
                    if isinstance(body.get("result"), str):
                        evidence["fork_block"] = int(body["result"], 16)
                        up = True
                        break
                except Exception:  # noqa: BLE001
                    pass
                await asyncio.sleep(0.5)
            if not up:
                return {"ran": False, "passed": False,
                        "reason": "anvil fork did not become ready within timeout"}

            # ---- real validation checks against the controllable fork ----
            results: Dict[str, Any] = {}

            # 1. chain id reachable
            cid = await self._rpc(local_url, "eth_chainId", [])
            results["chain_id_ok"] = isinstance(cid.get("result"), str)

            # 2. executor bytecode present on the fork (if configured)
            executor = os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE")
            if executor:
                code = await self._rpc(local_url, "eth_getCode", [executor, "latest"])
                results["executor_has_code"] = bool(
                    isinstance(code.get("result"), str) and len(code["result"]) > 2)

            # 3. state-override supported on the fork (fork gives us trace/override)
            probe = await self._rpc(local_url, "eth_call", [
                {"to": "0x00000000000000000000000000000000000c0de0", "data": "0x"},
                "latest",
                {"0x00000000000000000000000000000000000c0de0":
                    {"code": "0x602a60005260206000f3"}}])
            results["state_override_ok"] = (
                isinstance(probe.get("result"), str) and probe["result"].endswith("2a"))

            evidence["checks"] = results
            passed = bool(results.get("chain_id_ok") and results.get("state_override_ok")
                          and (results.get("executor_has_code", True)))
            return {"ran": True, "passed": passed, "evidence": evidence,
                    "signed": False, "broadcast": False}
        except FileNotFoundError:
            return {"ran": False, "passed": False, "reason": "anvil binary not found"}
        except Exception as exc:  # noqa: BLE001
            return {"ran": False, "passed": False, "reason": f"{type(exc).__name__}: {exc}"}
        finally:
            if proc is not None and proc.returncode is None:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except Exception:  # noqa: BLE001
                    try:
                        proc.kill()
                    except Exception:  # noqa: BLE001
                        pass


__all__ = ["build_executor_entrypoint_calldata", "AnvilForkHarness"]
