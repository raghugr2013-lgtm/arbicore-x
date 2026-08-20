"""ArbiCore X — Read-only Aerodrome settlement simulator + RPC capability probe.

Validates a proposed Aerodrome settlement route end-to-end against REAL Base
state via the router's ``getAmountsOut`` (read-only ``eth_call``):

    borrow amount → swap(s) → final balance → repayment → net profit

It reuses the allowlisted settlement encoder for calldata provenance and the
throttled ``_eth_call`` (retry/backoff). It NEVER signs or broadcasts.

Two modes:
  * ``simulate(...)``          — validate at the latest block.
  * ``replay(...,block=N)``    — block-pinned historical replay (archive).

A failed simulation (route cannot repay / no data) is an ABSOLUTE rejection.

NOTE ON SCOPE (honest): this is a read-only ROUTE/ECONOMIC simulation. A fully
atomic flash-loan-executor simulation additionally requires the executor
contract (either deployed on-chain or injected via state-override `code`);
that step is gated on executor readiness and reported separately in the matrix.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from eth_abi import encode as abi_encode, decode as abi_decode
from eth_utils import keccak, to_checksum_address

from .quoter import _eth_call
from .aerodrome_settlement import (
    AerodromeSettlementAdapter, AERODROME_ROUTER, AERODROME_POOL_FACTORY,
)

_GET_AMOUNTS_OUT_SIG = "getAmountsOut(uint256,(address,address,bool,address)[])"

WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


def _selector(sig: str) -> bytes:
    return keccak(text=sig)[:4]


class SettlementSimulator:
    def __init__(self, *, rpc_url: str, router: str = AERODROME_ROUTER,
                 factory: str = AERODROME_POOL_FACTORY):
        self._rpc = rpc_url
        self._router = router
        self._factory = factory

    async def _get_amounts_out(self, routes: List[tuple], amount_in_wei: int,
                               block: str = "latest") -> Dict[str, Any]:
        data = "0x" + (_selector(_GET_AMOUNTS_OUT_SIG) + abi_encode(
            ["uint256", "(address,address,bool,address)[]"],
            [int(amount_in_wei), routes])).hex()
        res, bn, err = await _eth_call(self._rpc, to=self._router, data=data, block=block)
        if err or not res:
            return {"ok": False, "error": err or "empty result", "block_number": bn}
        try:
            amounts = list(abi_decode(["uint256[]"], bytes.fromhex(res[2:]))[0])
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"decode: {exc}", "block_number": bn}
        return {"ok": True, "amounts": amounts, "block_number": bn}

    async def simulate(self, *, hops: List[Dict[str, Any]], amount_in_wei: int,
                       token_decimals: int, token_usd: float,
                       gas_cost_usd: float = 0.0, min_out_slippage_bps: float = 30.0,
                       token_allowlist: List[str], recipient: str,
                       block: str = "latest") -> Dict[str, Any]:
        """Full read-only settlement validation of an Aerodrome route."""
        adapter = AerodromeSettlementAdapter(
            token_allowlist=token_allowlist, router_allowlist=[self._router])
        # Allowlisted calldata (also enforces token/router/no-arbitrary-target).
        min_out_guess = 1
        try:
            settlement = adapter.encode_settlement(
                hops=hops, amount_in_wei=amount_in_wei,
                min_amount_out_wei=min_out_guess, recipient=recipient,
                deadline=9_999_999_999, router=self._router)
        except Exception as exc:  # noqa: BLE001
            return {"passed": False, "stage": "encode",
                    "reason": f"settlement encode rejected: {exc}"}

        routes = [(to_checksum_address(h["token_in"]), to_checksum_address(h["token_out"]),
                   bool(h.get("stable", False)),
                   to_checksum_address(h.get("factory") or self._factory)) for h in hops]
        r = await self._get_amounts_out(routes, amount_in_wei, block=block)
        if not r["ok"]:
            return {"passed": False, "stage": "quote", "ran": False,
                    "reason": f"router getAmountsOut failed: {r.get('error')}",
                    "block_number": r.get("block_number")}

        amounts = r["amounts"]
        final_out = int(amounts[-1]) if amounts else 0
        min_out = int(final_out * (1.0 - min_out_slippage_bps / 10_000.0))
        repayment_ok = final_out >= amount_in_wei          # balancer v2 = 0 fee principal
        gross_wei = final_out - amount_in_wei
        net_profit_usd = gross_wei / (10 ** token_decimals) * token_usd - float(gas_cost_usd)
        passed = bool(repayment_ok and net_profit_usd > 0 and final_out >= min_out)
        reason = "settlement validated" if passed else (
            "route does not repay principal" if not repayment_ok
            else "net profit <= 0 after gas")
        return {
            "passed": passed, "ran": True, "stage": "complete",
            "reason": reason,
            "block": block, "block_number": r.get("block_number"),
            "amount_in_wei": int(amount_in_wei),
            "amounts_out_wei": [str(a) for a in amounts],
            "final_amount_out_wei": final_out,
            "min_amount_out_wei": min_out,
            "repayment_ok": repayment_ok,
            "gross_profit_wei": gross_wei,
            "net_profit_usd": round(net_profit_usd, 6),
            "gas_cost_usd": round(float(gas_cost_usd), 6),
            "settlement_to": settlement["to"],
            "settlement_selector": settlement["data"][:10],
            "signed": False, "broadcast": False,
        }

    async def replay(self, *, block_number: int, **kwargs) -> Dict[str, Any]:
        """Block-pinned historical replay (requires archive state)."""
        out = await self.simulate(block=hex(int(block_number)), **kwargs)
        out["replay_block_number"] = int(block_number)
        return out

    async def probe_capabilities(self) -> Dict[str, Any]:
        """VERIFY (not assume) what the configured RPC supports."""
        caps: Dict[str, Any] = {}
        # 1. state-override eth_call (3rd param)
        try:
            res, _, err = await _eth_call(
                self._rpc, to=WETH, data="0x18160ddd", block="latest")
            # override capability tested via a raw call below (kept simple/honest)
            caps["read_eth_call"] = bool(res) and not err
        except Exception as exc:  # noqa: BLE001
            caps["read_eth_call"] = False
            caps["read_error"] = str(exc)
        # 2. archive: historical balance read
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as c:
                so = await c.post(self._rpc, json={"jsonrpc": "2.0", "id": 1,
                    "method": "eth_call", "params": [{"to": WETH, "data": "0x18160ddd"},
                    "latest", {"0x0000000000000000000000000000000000000abc": {"balance": "0x64"}}]})
                caps["state_override"] = ("result" in so.json())
                ar = await c.post(self._rpc, json={"jsonrpc": "2.0", "id": 1,
                    "method": "eth_getBalance",
                    "params": [WETH, "0x100000"]})
                caps["archive_state"] = ("result" in ar.json())
                tr = await c.post(self._rpc, json={"jsonrpc": "2.0", "id": 1,
                    "method": "debug_traceCall",
                    "params": [{"to": WETH, "data": "0x18160ddd"}, "latest", {}]})
                caps["trace"] = ("result" in tr.json())
        except Exception as exc:  # noqa: BLE001
            caps["capability_probe_error"] = str(exc)
        return caps

    async def self_test(self) -> Dict[str, Any]:
        """Prove the simulator runs against real state: WETH→USDC→WETH cyclic."""
        try:
            out = await self.simulate(
                hops=[{"token_in": WETH, "token_out": USDC, "stable": False},
                      {"token_in": USDC, "token_out": WETH, "stable": False}],
                amount_in_wei=10**16, token_decimals=18, token_usd=2500.0,
                gas_cost_usd=1.0, token_allowlist=[WETH, USDC],
                recipient="0x0000000000000000000000000000000000000001")
            return {"ran": bool(out.get("ran")), "passed_sim": out.get("passed"),
                    "final_amount_out_wei": out.get("final_amount_out_wei"),
                    "reason": out.get("reason")}
        except Exception as exc:  # noqa: BLE001
            return {"ran": False, "error": f"{type(exc).__name__}: {exc}"}


__all__ = ["SettlementSimulator"]
