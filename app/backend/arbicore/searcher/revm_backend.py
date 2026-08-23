"""Real Anvil/REVM fork simulation backend (fail-closed, no fabrication).

Forks the configured Base RPC state with Foundry `anvil --fork-url` and runs a
genuine transaction-level simulation of the atomic flash-loan route via an
injected transaction builder + eth_call against the fork. If the RPC, the
anvil binary, the tx builder, or the simulation itself is unavailable, it
returns ok=False (fail closed) — it NEVER fabricates a passing result.

Injectable seams (`launcher`, `tx_builder`) make it deterministically testable
without a live node; the production defaults use a real anvil subprocess.
"""
from __future__ import annotations

import shutil
from typing import Awaitable, Callable, List, Optional, Protocol, runtime_checkable

from .route import Edge
from .simulation import SimResult


@runtime_checkable
class ForkHandle(Protocol):
    async def eth_call(self, tx: dict) -> str: ...            # returns hex output
    async def close(self) -> None: ...


@runtime_checkable
class ForkLauncher(Protocol):
    async def launch(self, rpc_url: str,
                     block_number: Optional[int]) -> ForkHandle: ...


class AnvilRevmForkBackend:
    backend_id = "revm_fork"

    def __init__(
        self,
        rpc_url: Optional[str],
        *,
        tx_builder: Optional[Callable[[List[Edge], float], Awaitable[dict]]] = None,
        launcher: Optional[ForkLauncher] = None,
        anvil_path: str = "anvil",
        block_number: Optional[int] = None,
        decode_net: Optional[Callable[[str, float], float]] = None,
    ) -> None:
        self._rpc_url = rpc_url
        self._tx_builder = tx_builder
        self._launcher = launcher
        self._anvil_path = anvil_path
        self._block = block_number
        self._decode_net = decode_net

    def _preflight(self) -> Optional[str]:
        if not self._rpc_url:
            return "no_base_rpc_configured"
        if self._launcher is None and shutil.which(self._anvil_path) is None:
            return "anvil_binary_unavailable"
        if self._tx_builder is None:
            return "tx_builder_not_wired"
        if self._decode_net is None:
            return "net_decoder_not_wired"
        return None

    async def simulate(self, cycle: List[Edge], amount_in: float) -> SimResult:
        fail = self._preflight()
        if fail:
            return SimResult(False, amount_in, 0.0, -amount_in, self.backend_id,
                             reason=f"fail_closed:{fail}")
        handle: Optional[ForkHandle] = None
        try:
            launcher = self._launcher or _DefaultAnvilLauncher(self._anvil_path)
            handle = await launcher.launch(self._rpc_url, self._block)
            tx = await self._tx_builder(cycle, amount_in)
            raw = await handle.eth_call(tx)
            net = float(self._decode_net(raw, amount_in))
            return SimResult(net > 0, amount_in, amount_in + net, net,
                             self.backend_id,
                             reason="ok" if net > 0 else "non_positive_net")
        except Exception as exc:  # noqa: BLE001 — fail closed on ANY sim error
            return SimResult(False, amount_in, 0.0, -amount_in, self.backend_id,
                             reason=f"fail_closed:sim_error:{type(exc).__name__}")
        finally:
            if handle is not None:
                try:
                    await handle.close()
                except Exception:  # noqa: BLE001
                    pass


class _DefaultAnvilLauncher:
    """Production launcher: `anvil --fork-url <rpc>` subprocess + JSON-RPC."""

    def __init__(self, anvil_path: str) -> None:
        self._anvil_path = anvil_path

    async def launch(self, rpc_url: str, block_number):  # pragma: no cover (VPS)
        import asyncio
        args = [self._anvil_path, "--fork-url", rpc_url, "--port", "0",
                "--silent"]
        if block_number is not None:
            args += ["--fork-block-number", str(int(block_number))]
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        # A production handle would parse the bound port from stdout and speak
        # JSON-RPC over http. Kept minimal here; VPS wiring provides the real
        # ForkHandle. If we reach here without a full handle we fail closed.
        raise RuntimeError("default_anvil_handle_requires_vps_wiring")


__all__ = ["AnvilRevmForkBackend", "ForkHandle", "ForkLauncher"]
