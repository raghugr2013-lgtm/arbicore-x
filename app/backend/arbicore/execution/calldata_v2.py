"""Executor V2 deterministic calldata encoders (ADDITIVE).

Builds the V2 ``userData`` payload + the three flash-head entrypoint calldata
blobs for FlashLoanReceiverV2 (Interface Freeze v1.1). Mirrors the style of the
V1 ``calldata.py`` but is a SEPARATE module: V1 encoders are untouched.

Deterministic: identical inputs -> identical bytes (test-verifiable). Zero chain
contact. These bytes are inputs to a signed tx; this module NEVER signs or
broadcasts. Unsupported venue/provider -> raises (fail-closed); the settlement
dispatcher upstream is the authority on whether a route is executable at all.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from eth_abi import encode as abi_encode
from eth_utils import keccak, to_bytes, to_checksum_address

from .executor_interface_v2 import (
    ENTRY_BALANCER_SIG, ENTRY_AAVE_SIG, ENTRY_MORPHO_SIG,
    VenueV2, family_for_backend_venue, V2_FLASH_HEADS,
)


def _sel(sig: str) -> bytes:
    return keccak(text=sig)[:4]


def _addr(a: str) -> str:
    if not isinstance(a, str) or not a.startswith("0x") or len(a) != 42:
        raise ValueError(f"invalid EVM address: {a!r}")
    return to_checksum_address(a)


# SwapHopV2 tuple type — MUST match the Solidity struct field order exactly:
# (uint8 venue, address router, address tokenIn, address tokenOut,
#  uint24 feeOrTickSpacing, bool stable, address factory, uint256 amountIn,
#  uint256 amountOutMinimum, uint160 sqrtPriceLimitX96, uint256 deadline)
_HOP_TUPLE = "(uint8,address,address,address,uint24,bool,address,uint256,uint256,uint160,uint256)"
_USERDATA_TYPES = [f"{_HOP_TUPLE}[]", "address", "uint256", "uint256"]


@dataclass(frozen=True)
class EncodedCallV2:
    contract_kind: str
    function_signature: str
    selector_hex: str
    calldata_hex: str
    value_wei: int = 0
    deterministic: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _hop_to_tuple(h: Dict[str, Any]) -> tuple:
    venue = h.get("venue")
    if isinstance(venue, str):
        fam = int(family_for_backend_venue(venue))
    elif isinstance(venue, VenueV2):
        fam = int(venue)
    elif isinstance(venue, int):
        fam = int(VenueV2(venue))
    else:
        raise ValueError(f"hop.venue must be backend-id/VenueV2/int, got {venue!r}")
    return (
        fam,
        _addr(h["router"]),
        _addr(h["token_in"]),
        _addr(h["token_out"]),
        int(h.get("fee_or_tick_spacing") or 0),
        bool(h.get("stable") or False),
        _addr(h["factory"]) if h.get("factory") else "0x" + "00" * 20,
        int(h.get("amount_in_wei") or 0),
        int(h.get("amount_out_min_wei") or 0),
        int(h.get("sqrt_price_limit_x96") or 0),
        int(h["deadline"]),
    )


def build_user_data_v2(*,
                       hops: List[Dict[str, Any]],
                       profit_recipient: str,
                       min_profit_wei: int,
                       deadline: int) -> str:
    """ABI-encode the V2 callback payload (deterministic)."""
    if not hops:
        raise ValueError("build_user_data_v2: hops must be non-empty")
    tuples = [_hop_to_tuple(h) for h in hops]
    encoded = abi_encode(
        _USERDATA_TYPES,
        [tuples, _addr(profit_recipient), int(min_profit_wei), int(deadline)],
    )
    return "0x" + encoded.hex()


def _encode_head(sig: str, arg_types: list, args: list, kind: str) -> EncodedCallV2:
    sel = _sel(sig)
    calldata = sel + abi_encode(arg_types, args)
    return EncodedCallV2(
        contract_kind=kind,
        function_signature=sig,
        selector_hex="0x" + sel.hex(),
        calldata_hex="0x" + calldata.hex(),
    )


def encode_execute_balancer_v2(*, tokens: List[str], amounts: List[int],
                               user_data_hex: str) -> EncodedCallV2:
    if len(tokens) != len(amounts) or not tokens:
        raise ValueError("tokens[] and amounts[] must be equal-length and non-empty")
    return _encode_head(
        ENTRY_BALANCER_SIG, ["address[]", "uint256[]", "bytes"],
        [[_addr(t) for t in tokens], [int(a) for a in amounts],
         to_bytes(hexstr=user_data_hex)],
        "flash_loan_receiver_v2")


def encode_execute_aave_v2(*, asset: str, amount_wei: int,
                           user_data_hex: str) -> EncodedCallV2:
    if amount_wei <= 0:
        raise ValueError("amount_wei must be > 0")
    return _encode_head(
        ENTRY_AAVE_SIG, ["address", "uint256", "bytes"],
        [_addr(asset), int(amount_wei), to_bytes(hexstr=user_data_hex)],
        "flash_loan_receiver_v2")


def encode_execute_morpho_v2(*, token: str, amount_wei: int,
                             user_data_hex: str) -> EncodedCallV2:
    if amount_wei <= 0:
        raise ValueError("amount_wei must be > 0")
    return _encode_head(
        ENTRY_MORPHO_SIG, ["address", "uint256", "bytes"],
        [_addr(token), int(amount_wei), to_bytes(hexstr=user_data_hex)],
        "flash_loan_receiver_v2")


def encode_v2_head_for_provider(*, provider: str, token: str, amount_wei: int,
                                user_data_hex: str) -> EncodedCallV2:
    """Version-aware V2 flash-head selector. Fail-closed for non-V2 heads."""
    p = (provider or "").strip().lower()
    if p not in V2_FLASH_HEADS:
        raise NotImplementedError(
            f"V2 calldata supports {sorted(V2_FLASH_HEADS)}; got '{provider}'")
    if p == "balancer_v2":
        return encode_execute_balancer_v2(
            tokens=[token], amounts=[amount_wei], user_data_hex=user_data_hex)
    if p == "aave_v3":
        return encode_execute_aave_v2(
            asset=token, amount_wei=amount_wei, user_data_hex=user_data_hex)
    return encode_execute_morpho_v2(
        token=token, amount_wei=amount_wei, user_data_hex=user_data_hex)


__all__ = [
    "EncodedCallV2", "build_user_data_v2",
    "encode_execute_balancer_v2", "encode_execute_aave_v2",
    "encode_execute_morpho_v2", "encode_v2_head_for_provider",
]
