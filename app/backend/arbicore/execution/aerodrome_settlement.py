"""ArbiCore X — Allowlisted Aerodrome on-chain settlement adapter (P0-3).

Produces REAL ABI-encoded calldata for the Aerodrome Router
``swapExactTokensForTokens`` so a proposed flash-loan arbitrage can be
simulated end-to-end. It is intentionally NARROW:

  * The only permitted target is the allowlisted Aerodrome Router — the
    adapter refuses to encode a call to any other address (no arbitrary
    contract execution).
  * Every hop token must be on the operator token allowlist.
  * The default pool factory is the verified canonical Base Aerodrome
    PoolFactory.

This module NEVER signs or broadcasts. It only builds the transaction
`(to, data, value)` that the state-override simulator will validate. The
`recipient` is supplied by the caller (the executor contract) at build time.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from eth_abi import encode as abi_encode
from eth_utils import keccak, to_checksum_address

# Canonical Base constants (verified on-chain: both addresses carry bytecode).
AERODROME_ROUTER = "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43"
AERODROME_POOL_FACTORY = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"

# swapExactTokensForTokens(uint256,uint256,(address,address,bool,address)[],address,uint256)
_SWAP_SIG = ("swapExactTokensForTokens(uint256,uint256,"
             "(address,address,bool,address)[],address,uint256)")


def _selector(signature: str) -> bytes:
    return keccak(text=signature)[:4]


class AerodromeSettlementError(ValueError):
    """Raised when a settlement request violates the allowlist / shape rules."""


class AerodromeSettlementAdapter:
    dex = "aerodrome"
    version = "aerodrome_settlement@1"
    router = AERODROME_ROUTER
    factory = AERODROME_POOL_FACTORY

    def __init__(self, *, token_allowlist: Optional[List[str]] = None,
                 router_allowlist: Optional[List[str]] = None):
        self._tokens = {t.lower() for t in (token_allowlist or [])}
        self._routers = {r.lower() for r in (router_allowlist or [AERODROME_ROUTER])}

    def _check_token(self, addr: str) -> str:
        if self._tokens and addr.lower() not in self._tokens:
            raise AerodromeSettlementError(f"token not allowlisted: {addr}")
        return to_checksum_address(addr)

    def _check_router(self, router: str) -> str:
        if router.lower() not in self._routers:
            raise AerodromeSettlementError(
                f"settlement target '{router}' is not an allowlisted Aerodrome router")
        return to_checksum_address(router)

    def encode_settlement(
        self, *, hops: List[Dict[str, Any]], amount_in_wei: int,
        min_amount_out_wei: int, recipient: str, deadline: int,
        router: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build `(to, data, value)` for a 1..n-hop Aerodrome swap.

        Each hop: {token_in, token_out, stable(bool), factory(optional)}.
        Consecutive hops must chain (hop[i].token_out == hop[i+1].token_in).
        """
        if not hops:
            raise AerodromeSettlementError("at least one hop is required")
        if amount_in_wei <= 0 or min_amount_out_wei <= 0:
            raise AerodromeSettlementError("amount_in and min_amount_out must be > 0")

        target = self._check_router(router or self.router)
        routes = []
        for i, h in enumerate(hops):
            tin = self._check_token(h["token_in"])
            tout = self._check_token(h["token_out"])
            if i > 0 and hops[i - 1]["token_out"].lower() != h["token_in"].lower():
                raise AerodromeSettlementError("hops do not chain (token mismatch)")
            factory = to_checksum_address(h.get("factory") or self.factory)
            routes.append((tin, tout, bool(h.get("stable", False)), factory))

        args = abi_encode(
            ["uint256", "uint256", "(address,address,bool,address)[]", "address", "uint256"],
            [int(amount_in_wei), int(min_amount_out_wei), routes,
             to_checksum_address(recipient), int(deadline)],
        )
        data = "0x" + (_selector(_SWAP_SIG) + args).hex()
        return {
            "to": target,
            "data": data,
            "value_wei": 0,
            "function_signature": _SWAP_SIG,
            "route_hops": [{"from": r[0], "to": r[1], "stable": r[2], "factory": r[3]}
                           for r in routes],
            "amount_in_wei": int(amount_in_wei),
            "min_amount_out_wei": int(min_amount_out_wei),
            "recipient": to_checksum_address(recipient),
            "deadline": int(deadline),
            "adapter_version": self.version,
            "signed": False, "broadcast": False,
        }

    def self_test(self) -> Dict[str, Any]:
        """Deterministic encode of a canonical WETH→USDC volatile hop.

        Used by the readiness matrix to flip DEX_ADAPTERS_SETTLE GREEN only
        when the encoder genuinely produces well-formed calldata."""
        weth = "0x4200000000000000000000000000000000000006"
        usdc = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        try:
            probe = AerodromeSettlementAdapter(
                token_allowlist=[weth, usdc], router_allowlist=[AERODROME_ROUTER])
            out = probe.encode_settlement(
                hops=[{"token_in": weth, "token_out": usdc, "stable": False}],
                amount_in_wei=10**16, min_amount_out_wei=1,
                recipient="0x0000000000000000000000000000000000000001",
                deadline=1_900_000_000)
            ok = (out["data"].startswith("0x" + _selector(_SWAP_SIG).hex())
                  and out["to"].lower() == AERODROME_ROUTER.lower()
                  and len(out["data"]) > 200)
            return {"passed": bool(ok), "selector": "0x" + _selector(_SWAP_SIG).hex(),
                    "calldata_len": len(out["data"])}
        except Exception as exc:  # noqa: BLE001
            return {"passed": False, "error": f"{type(exc).__name__}: {exc}"}


__all__ = ["AerodromeSettlementAdapter", "AerodromeSettlementError",
           "AERODROME_ROUTER", "AERODROME_POOL_FACTORY"]
