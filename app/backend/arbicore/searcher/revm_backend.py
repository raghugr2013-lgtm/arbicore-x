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

import os
import shutil
from typing import (Any, Awaitable, Callable, Dict, List, Optional, Protocol,
                    runtime_checkable)

from .pool_cache import PoolStateCache
from .route import Edge
from .simulation import SimResult
from ..execution.calldata import (build_user_data_from_hops,
                                  encode_executor_execute)


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


__all__ = ["AnvilRevmForkBackend", "ForkHandle", "ForkLauncher",
           "make_calldata_tx_builder"]


# ---------------------------------------------------------------------------
# Canonical calldata tx builder (Edge cycle → executor eth_call tx)
# ---------------------------------------------------------------------------
#
# Bridges a T2 searcher route (``List[Edge]``) into the deployed executor's
# canonical ``execute(address[],uint256[],bytes)`` entrypoint by REUSING the
# existing ``encode_executor_execute`` + ``build_user_data_from_hops`` encoders
# in ``arbicore/execution/calldata.py`` — no new ABI/execution architecture.
#
# The produced dict is an eth_call transaction (read-only) consumed by
# ``AnvilRevmForkBackend`` against an Anvil/REVM fork. It is NEVER signed and
# NEVER broadcast — SHADOW only.


def make_calldata_tx_builder(
    *,
    cache: PoolStateCache,
    executor_address: Optional[str] = None,
    from_address: Optional[str] = None,
    profit_recipient: Optional[str] = None,
    token_addresses: Dict[str, str],
    token_decimals: Optional[Dict[str, int]] = None,
    default_fee_bps: int = 30,
    chain: str = "base",
) -> Callable[[List[Edge], float], Awaitable[dict]]:
    """Return an async ``tx_builder(cycle, amount)`` producing an executor
    eth_call tx dict via the canonical calldata encoder.

    Args:
        cache: pool-state cache used to resolve each hop's fee tier
            (``PoolState.fee_bps``). Stale/missing pools fall back to
            ``default_fee_bps`` (well-formed calldata is still produced; the
            fork sim decides profitability, never this builder).
        executor_address: deployed ``FlashLoanReceiver`` address. Falls back to
            ``ARBICORE_EXECUTOR_ADDRESS_BASE`` when ``chain == "base"``.
        from_address: eth_call ``from`` (the executor owner / gas wallet). Falls
            back to ``ARBICORE_GAS_WALLET_ADDRESS``.
        profit_recipient: residual-balance recipient encoded into userData.
            Falls back to ``from_address``.
        token_addresses: maps the cache token symbol (``Edge.token_in`` /
            ``token_out``, i.e. ``PoolState.token0/token1``) → checksummable EVM
            address. Required so symbolic routes resolve to real addresses.
        token_decimals: maps token symbol → ERC-20 decimals (default 18).
        default_fee_bps: fee tier used when a pool is stale/uncached.
        chain: execution chain (Base primary).

    The returned builder resolves the borrow token from the FIRST hop's
    ``token_in``, converts ``amount`` → wei with that token's decimals, and
    forwards prior-hop output (``amountIn = 0``) for every subsequent hop.

    Fails closed (raises) on empty cycle, unmapped token, or missing executor
    — it NEVER fabricates a transaction with placeholder addresses.
    """
    token_decimals = token_decimals or {}
    executor = executor_address or (
        os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE") if chain == "base" else None
    )
    frm = from_address or os.environ.get("ARBICORE_GAS_WALLET_ADDRESS")
    recipient = profit_recipient or frm

    def _addr_for(symbol: str) -> str:
        a = token_addresses.get(symbol)
        if not a:
            raise ValueError(f"no address mapping for token symbol {symbol!r}")
        return a

    async def tx_builder(cycle: List[Edge], amount: float) -> dict:
        if not cycle:
            raise ValueError("tx_builder: cycle must be non-empty")
        if not executor:
            raise ValueError(
                "tx_builder: executor address unresolved "
                "(pass executor_address or set ARBICORE_EXECUTOR_ADDRESS_BASE)")
        if not recipient:
            raise ValueError(
                "tx_builder: profit_recipient/from address unresolved "
                "(pass from_address or set ARBICORE_GAS_WALLET_ADDRESS)")

        borrow_symbol = cycle[0].token_in
        borrow_addr = _addr_for(borrow_symbol)
        dec = int(token_decimals.get(borrow_symbol, 18))
        amount_wei = int(round(float(amount) * (10 ** dec)))
        if amount_wei <= 0:
            raise ValueError("tx_builder: borrow amount must be > 0 in wei")

        hops: List[Dict[str, Any]] = []
        for idx, e in enumerate(cycle):
            st = cache.get(e.pool)
            fee_bps = int(st.fee_bps) if st is not None else int(default_fee_bps)
            hops.append({
                "token_in": _addr_for(e.token_in),
                "token_out": _addr_for(e.token_out),
                "fee_tier_bps": fee_bps,
                # First hop injects the borrowed amount; later hops forward the
                # prior hop's realised output (amountIn = 0).
                "amount_in_wei": amount_wei if idx == 0 else 0,
                "amount_out_min_wei": 0,
                "sqrt_price_limit_x96": 0,
            })

        user_data_hex = build_user_data_from_hops(
            hops=hops, profit_recipient=recipient)
        call = encode_executor_execute(
            executor_address=executor,
            tokens=[borrow_addr], amounts=[amount_wei],
            user_data_hex=user_data_hex,
        )
        tx: Dict[str, Any] = {
            "to": call.contract_address,
            "data": call.calldata_hex,
            "value": "0x0",
        }
        if frm:
            tx["from"] = frm
        return tx

    return tx_builder
