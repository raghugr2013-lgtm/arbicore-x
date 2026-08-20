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


# Signatures we can recognise inside the deployed executor's dispatcher.
_KNOWN_SELECTORS: Dict[str, str] = {
    "5c38449e": "flashLoan(address,address[],uint256[],bytes)",   # operator entrypoint
    "f04f2707": "receiveFlashLoan(address[],uint256[],uint256[],bytes)",  # Balancer callback
    "04e45aaf": "exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))",  # UniV3
    "32fe7b26": "ROUTER()", "411557d1": "VAULT()", "8da5cb5b": "owner()",
    "62c06767": "sweep(address,address,uint256)",
    "095ea7b3": "approve(address,uint256)", "70a08231": "balanceOf(address)",
    "a9059cbb": "transfer(address,uint256)",
}


def _extract_selectors(bytecode_hex: str) -> List[str]:
    b = bytes.fromhex(bytecode_hex[2:]) if bytecode_hex and len(bytecode_hex) > 2 else b""
    sels, i = set(), 0
    while i < len(b):
        op = b[i]
        if op == 0x63 and i + 5 <= len(b):        # PUSH4 <selector>
            sels.add(b[i + 1:i + 5].hex()); i += 5; continue
        if 0x60 <= op <= 0x7f:                    # skip other PUSHn operands
            i += 1 + (op - 0x5f); continue
        i += 1
    return sorted(sels)


async def inspect_executor(rpc_url: str, executor: str) -> Dict[str, Any]:
    """READ-ONLY on-chain inspection of the deployed executor: extract its
    function selectors from bytecode and read its owner()/ROUTER()/VAULT()
    getters. Determines the real entrypoint signature instead of guessing.

    Never signs/broadcasts — only eth_getCode + eth_call getters."""
    import asyncio
    import httpx
    H = {"Content-Type": "application/json", "User-Agent": "arbicore/1.0"}

    async def _rpc(method: str, params: List[Any]):
        last = {}
        for attempt in range(4):
            try:
                async with httpx.AsyncClient(timeout=25) as c:
                    r = await c.post(rpc_url, json={"jsonrpc": "2.0", "id": 1,
                                                    "method": method, "params": params}, headers=H)
                body = r.json()
            except Exception:  # noqa: BLE001
                await asyncio.sleep(0.4 * (2 ** attempt)); continue
            err = body.get("error") or {}
            if isinstance(err, dict) and err.get("code") in (-32016, -32005, 429):
                await asyncio.sleep(0.4 * (2 ** attempt)); last = body; continue
            return body
        return last

    if not (rpc_url and executor):
        return {"ok": False, "reason": "rpc/executor not configured"}
    code = (await _rpc("eth_getCode", [executor, "latest"])).get("result") or "0x"
    if len(code) <= 2:
        return {"ok": False, "reason": "no bytecode at executor address"}
    sels = _extract_selectors(code)
    recognised = {s: _KNOWN_SELECTORS[s] for s in sels if s in _KNOWN_SELECTORS}
    unknown = [s for s in sels if s not in _KNOWN_SELECTORS]

    async def _getter(sig: str):
        await asyncio.sleep(0.25)  # spacing to respect public-RPC rate limits
        j = await _rpc("eth_call", [{"to": executor, "data": "0x" + _selector(sig).hex()}, "latest"])
        res = j.get("result")
        return to_checksum_address("0x" + res[-40:]) if (res and len(res) >= 42) else None

    owner = await _getter("owner()")
    router = await _getter("ROUTER()")
    vault = await _getter("VAULT()")

    entry_present = "5c38449e" in sels
    return {
        "ok": True, "executor": executor,
        "bytecode_size_bytes": (len(code) - 2) // 2,
        "selectors": sels,
        "recognised": recognised, "unknown_selectors": unknown,
        "entrypoint_signature": "flashLoan(address,address[],uint256[],bytes)" if entry_present else None,
        "entrypoint_selector_present": entry_present,
        "flash_provider": "balancer_v2" if "f04f2707" in sels else None,
        "swap_venue": "uniswap_v3" if "04e45aaf" in sels else None,
        "owner": owner, "router": router, "vault": vault,
        "userdata_schema_recoverable": False,  # decoded internally; needs source/ABI
        "signed": False, "broadcast": False,
    }


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
