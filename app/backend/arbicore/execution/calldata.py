"""Wave 7C · Bytes-level Calldata Encoder.

Lifts the Wave-6D calldata-encoding barrier for the two adapter call
signatures the LIMITED_LIVE flash-loan validation actually exercises:

    * Balancer V2 Vault ``flashLoan(recipient, tokens[], amounts[], userData)``
      — chosen because it charges **0 bps premium**, minimising the
      operator's cost on the very first validation transaction.
    * Uniswap V3 SwapRouter ``exactInputSingle((tokenIn, tokenOut,
      fee, recipient, deadline, amountIn, amountOutMinimum,
      sqrtPriceLimitX96))`` — the settlement leg.

Design constraints:

    * Deterministic (same inputs → identical bytes; test-verifiable).
    * Zero side effects; no chain contact.
    * Uses ``eth_abi.encode`` + a hand-derived 4-byte selector
      (``keccak256(signature)[:4]``) so the module has no dependency
      on a live web3 provider.
    * Every encoding path is covered by a hand-picked known-vector
      unit test — see ``tests/test_wave7_calldata.py``.

**Important**: bytes emitted by this encoder are the *inputs* to a
signed transaction.  They do not, in themselves, initiate a broadcast.
The Wave 7C broadcast path (``broadcast.py``) takes these bytes, signs
them with the Wave 6A-registered secret, and hands them to a
read-only ``eth_call`` preflight before optionally emitting an
``eth_sendRawTransaction`` — the latter is gated behind
``KILL_SWITCH → MODE → CAPITAL → SECRET → PREFLIGHT`` (five gates).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from eth_abi import encode as abi_encode
from eth_utils import keccak, to_bytes, to_checksum_address


# ---------------------------------------------------------------------------
# Selector helpers
# ---------------------------------------------------------------------------

def _selector(signature: str) -> bytes:
    """4-byte function selector = keccak256(signature)[:4]."""
    return keccak(text=signature)[:4]


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EncodedCall:
    """A single encoded EVM function call, ready to sign."""
    contract_kind: str
    contract_address: str
    function_signature: str
    selector_hex: str
    calldata_hex: str
    value_wei: int
    gas_limit_hint: int
    deterministic: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Address normalisation
# ---------------------------------------------------------------------------

def _addr(a: str) -> str:
    """Return checksummed address, raising on obvious garbage."""
    if not isinstance(a, str) or not a.startswith("0x") or len(a) != 42:
        raise ValueError(f"invalid EVM address: {a!r}")
    return to_checksum_address(a)


# ---------------------------------------------------------------------------
# Balancer V2 flashLoan
# ---------------------------------------------------------------------------

BALANCER_V2_VAULT_BY_CHAIN: Dict[str, str] = {
    # Same address on every chain Balancer supports.
    "ethereum": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    "base":     "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    "arbitrum": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    "optimism": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    "polygon":  "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
}


def encode_balancer_v2_flash_loan(*,
                                   chain: str,
                                   recipient: str,
                                   tokens: List[str],
                                   amounts: List[int],
                                   user_data_hex: str = "0x",
                                   gas_limit_hint: int = 800_000,
                                   ) -> EncodedCall:
    """Encode a Balancer V2 Vault ``flashLoan`` call.

    ``flashLoan(address recipient, address[] tokens, uint256[] amounts,
    bytes userData)`` — selector ``0x5c38449e``.

    .. note::
        This targets the **Balancer V2 Vault directly**.  It is
        preserved for future use cases (e.g. calling the Vault from a
        contract that pre-authorises itself, or unit tests that verify
        the Vault-side ABI shape) but is **not** used by
        :func:`encode_plan_head_call` for LIMITED_LIVE broadcasts — the
        FlashLoanReceiver's ``_authorized`` guard rejects any callback
        that did not originate from its own ``execute()`` window, so
        the LIMITED_LIVE path targets the executor instead.
    """
    if chain not in BALANCER_V2_VAULT_BY_CHAIN:
        raise ValueError(f"Balancer V2 vault not registered for chain '{chain}'")
    if len(tokens) != len(amounts) or not tokens:
        raise ValueError("tokens[] and amounts[] must be equal-length and non-empty")
    sig = "flashLoan(address,address[],uint256[],bytes)"
    sel = _selector(sig)
    tokens_cs = [_addr(t) for t in tokens]
    user_data = to_bytes(hexstr=user_data_hex or "0x")
    encoded = abi_encode(
        ["address", "address[]", "uint256[]", "bytes"],
        [_addr(recipient), tokens_cs, [int(a) for a in amounts], user_data],
    )
    calldata = sel + encoded
    return EncodedCall(
        contract_kind="balancer_v2_vault",
        contract_address=BALANCER_V2_VAULT_BY_CHAIN[chain],
        function_signature=sig,
        selector_hex="0x" + sel.hex(),
        calldata_hex="0x" + calldata.hex(),
        value_wei=0,
        gas_limit_hint=int(gas_limit_hint),
    )


# ---------------------------------------------------------------------------
# FlashLoanReceiver.execute (LIMITED_LIVE entry point)
# ---------------------------------------------------------------------------

def encode_executor_execute(*,
                             executor_address: str,
                             tokens: List[str],
                             amounts: List[int],
                             user_data_hex: str = "0x",
                             gas_limit_hint: int = 1_100_000,
                             ) -> EncodedCall:
    """Encode a call to ``FlashLoanReceiver.execute(...)`` on the executor.

    ``execute(address[] tokens, uint256[] amounts, bytes userData)`` —
    selector ``0x64ba4bc1`` (= ``keccak256("execute(address[],uint256[],bytes)")[:4]``).

    This is the correct LIMITED_LIVE entry point.  The receiver's
    ``execute()`` flips its internal ``_authorized`` flag to ``true``
    immediately before invoking the Balancer Vault, then flips it back
    to ``false`` after the Vault callback returns.  Calling the Vault
    directly (see :func:`encode_balancer_v2_flash_loan`) bypasses this
    window and triggers ``NotAuthorized()`` (selector ``0xea8e4eb5``)
    inside the receiver's callback guard.
    """
    if len(tokens) != len(amounts) or not tokens:
        raise ValueError("tokens[] and amounts[] must be equal-length and non-empty")
    sig = "execute(address[],uint256[],bytes)"
    sel = _selector(sig)
    tokens_cs = [_addr(t) for t in tokens]
    user_data = to_bytes(hexstr=user_data_hex or "0x")
    encoded = abi_encode(
        ["address[]", "uint256[]", "bytes"],
        [tokens_cs, [int(a) for a in amounts], user_data],
    )
    calldata = sel + encoded
    return EncodedCall(
        contract_kind="flash_loan_receiver",
        contract_address=_addr(executor_address),
        function_signature=sig,
        selector_hex="0x" + sel.hex(),
        calldata_hex="0x" + calldata.hex(),
        value_wei=0,
        gas_limit_hint=int(gas_limit_hint),
    )


# ---------------------------------------------------------------------------
# Uniswap V3 SwapRouter exactInputSingle
# ---------------------------------------------------------------------------

UNISWAP_V3_ROUTER_BY_CHAIN: Dict[str, str] = {
    # Uniswap V3 SwapRouter02.
    "ethereum": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
    "base":     "0x2626664c2603336E57B271c5C0b26F421741e481",
    "arbitrum": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
    "optimism": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
    "polygon":  "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
}


def encode_uniswap_v3_exact_input_single(*,
                                          chain: str,
                                          token_in: str,
                                          token_out: str,
                                          fee_tier_bps: int,
                                          recipient: str,
                                          amount_in_wei: int,
                                          amount_out_minimum_wei: int,
                                          sqrt_price_limit_x96: int = 0,
                                          gas_limit_hint: int = 350_000,
                                          ) -> EncodedCall:
    """Encode a Uniswap V3 SwapRouter02 ``exactInputSingle`` call.

    ``exactInputSingle(ExactInputSingleParams)`` where the params
    struct is ``(address tokenIn, address tokenOut, uint24 fee,
    address recipient, uint256 amountIn, uint256 amountOutMinimum,
    uint160 sqrtPriceLimitX96)``.  Selector ``0x04e45aaf``.
    """
    if chain not in UNISWAP_V3_ROUTER_BY_CHAIN:
        raise ValueError(f"Uniswap V3 router not registered for chain '{chain}'")
    # Fee tier in Uniswap is expressed in 1e-6 units — bps × 100.
    fee = int(fee_tier_bps) * 100
    sig = ("exactInputSingle((address,address,uint24,address,uint256,"
           "uint256,uint160))")
    sel = _selector(sig)
    struct = (
        _addr(token_in), _addr(token_out), fee, _addr(recipient),
        int(amount_in_wei), int(amount_out_minimum_wei),
        int(sqrt_price_limit_x96),
    )
    encoded = abi_encode(
        ["(address,address,uint24,address,uint256,uint256,uint160)"],
        [struct],
    )
    calldata = sel + encoded
    return EncodedCall(
        contract_kind="uniswap_v3_router_02",
        contract_address=UNISWAP_V3_ROUTER_BY_CHAIN[chain],
        function_signature=sig,
        selector_hex="0x" + sel.hex(),
        calldata_hex="0x" + calldata.hex(),
        value_wei=0,
        gas_limit_hint=int(gas_limit_hint),
    )


# ---------------------------------------------------------------------------
# userData helper — ABI-encode swap hops for the executor callback
# ---------------------------------------------------------------------------

# Struct passed to the FlashLoanReceiver executor via userData:
#   struct SwapHop {
#       address tokenIn;
#       address tokenOut;
#       uint24  feeTierPpm;      // Uniswap V3 fee tier (bps × 100)
#       uint256 amountIn;        // 0 = auto-forward previous hop output
#       uint256 amountOutMinimum;
#       uint160 sqrtPriceLimitX96;
#   }
#
# userData layout: abi.encode(SwapHop[] hops, address profitRecipient)
_HOP_TUPLE_TYPE = "(address,address,uint24,uint256,uint256,uint160)"
_USER_DATA_TYPE = [f"{_HOP_TUPLE_TYPE}[]", "address"]


def build_user_data_from_hops(*,
                               hops: List[Dict[str, Any]],
                               profit_recipient: str,
                               ) -> str:
    """ABI-encode the executor callback payload.

    Produces the ``userData`` bytes that the Balancer V2 Vault forwards
    verbatim to ``FlashLoanReceiver.receiveFlashLoan`` on the executor
    contract.  The executor decodes it into ``(SwapHop[], address)`` and
    performs one ``SwapRouter02.exactInputSingle`` call per hop, then
    forwards residual balance to ``profitRecipient`` before repaying the
    Vault.

    Deterministic: identical inputs → identical bytes (test-verifiable).

    Args:
        hops: ordered list of hops, each dict:
              ``token_in``, ``token_out``, ``fee_tier_bps`` (Uniswap V3
              tier in bps, e.g. 30 = 0.30 %), ``amount_in_wei``
              (0 = forward previous hop output), ``amount_out_min_wei``,
              optional ``sqrt_price_limit_x96`` (defaults to 0 = no
              price bound).
        profit_recipient: address that receives residual balance.

    Returns:
        Hex string with leading ``0x`` suitable for
        ``encode_plan_head_call``'s ``userData`` blob.
    """
    if not hops:
        raise ValueError("build_user_data_from_hops: hops must be non-empty")
    tuples = []
    for i, h in enumerate(hops):
        try:
            token_in = _addr(h["token_in"])
            token_out = _addr(h["token_out"])
            fee_ppm = int(h["fee_tier_bps"]) * 100
            amount_in = int(h.get("amount_in_wei") or 0)
            amount_out_min = int(h["amount_out_min_wei"])
            sqrt_price_limit = int(h.get("sqrt_price_limit_x96") or 0)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"hop[{i}] malformed: {exc}") from exc
        tuples.append((token_in, token_out, fee_ppm, amount_in,
                       amount_out_min, sqrt_price_limit))
    encoded = abi_encode(
        _USER_DATA_TYPE,
        [tuples, _addr(profit_recipient)],
    )
    return "0x" + encoded.hex()


# ---------------------------------------------------------------------------
# Plan → calls
# ---------------------------------------------------------------------------

def _extract_hops_from_steps(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Translate ``plan.steps[kind=swap]`` into the flat ``hops`` shape
    that :func:`build_user_data_from_hops` expects.

    The Manual Plan Composer + opportunity planner both encode Uniswap V3
    swaps as ``args[0]`` = ``{tokenIn, tokenOut, fee, recipient, amountIn,
    amountOutMinimum, sqrtPriceLimitX96}`` — the ExactInputSingle tuple.
    Balancer callback needs ``{token_in, token_out, fee_tier_bps,
    amount_in_wei, amount_out_min_wei, sqrt_price_limit_x96}``.

    Only swaps with a valid ExactInputSingle-shaped args[0] are lifted;
    anything else is skipped silently (planner-side pipeline concern).

    ``fee`` in the step is Uniswap-V3 raw ppm (e.g. 500 = 0.05 %); the
    downstream ``build_user_data_from_hops`` multiplies bps × 100 to get
    ppm, so we divide back here.
    """
    out: List[Dict[str, Any]] = []
    for s in steps:
        if (s or {}).get("kind") != "swap":
            continue
        args = (s or {}).get("args") or []
        if not args or not isinstance(args[0], dict):
            continue
        p = args[0]
        try:
            fee_ppm = int(p["fee"])
        except (KeyError, TypeError, ValueError):
            continue
        # Uniswap V3 fee tiers are integer ppm values that are exact
        # multiples of 100 (100, 500, 3000, 10000) so lossless.
        fee_bps = fee_ppm // 100
        out.append({
            "token_in": p.get("tokenIn"),
            "token_out": p.get("tokenOut"),
            "fee_tier_bps": fee_bps,
            "amount_in_wei": int(p.get("amountIn") or 0),
            "amount_out_min_wei": int(p.get("amountOutMinimum") or 0),
            "sqrt_price_limit_x96": int(p.get("sqrtPriceLimitX96") or 0),
        })
    return out


def encode_plan_head_call(
    plan_doc: Dict[str, Any],
    *,
    signer_address: Optional[str] = None,
) -> EncodedCall:
    """Encode the *head* (borrow) call for a Wave-6B execution plan.

    LIMITED_LIVE broadcasts target ``FlashLoanReceiver.execute(...)`` on
    the deployed executor (see :func:`encode_executor_execute`).  The
    executor internally invokes the Balancer V2 Vault while its
    ``_authorized`` guard is open — a direct-to-Vault encoding
    (:func:`encode_balancer_v2_flash_loan`, preserved for future use)
    would be rejected by that guard at callback time with
    ``NotAuthorized()`` (selector ``0xea8e4eb5``).

    ``userData`` (Balancer V2 callback payload, decoded by the receiver
    as ``(SwapHop[], address profitRecipient)``) is sourced, in order, from:

        1. ``plan_doc["user_data_hex"]`` — explicit operator-supplied
           payload (hex string, e.g. produced by
           :func:`build_user_data_from_hops`).
        2. Derived automatically from ``plan_doc["hops"]`` +
           ``plan_doc["profit_recipient"]`` if both are present.
        3. Defaults to ``"0x"`` (pipeline-exercise mode — the on-chain
           callback will revert inside ``abi.decode``, but the full
           sign+broadcast+tx-hash path is still exercised).

    The executor address is resolved from, in order:
        1. ``plan_doc["recipient"]``
        2. ``plan_doc["borrow_step"]["recipient"]``
        3. Env var ``ARBICORE_EXECUTOR_ADDRESS_BASE`` (chain=base only)
    """
    provider = plan_doc.get("flash_loan_provider") or ""
    if provider != "balancer_v2":
        raise NotImplementedError(
            f"Wave 7C calldata encoder supports only balancer_v2 flash heads; "
            f"got '{provider}'.  Aave/Uniswap heads unlock once executor is "
            f"deployed & verified."
        )
    borrow_step = next(
        (s for s in (plan_doc.get("steps") or []) if s.get("kind") == "borrow"), None,
    )
    if borrow_step is None:
        raise ValueError("plan has no borrow step")
    chain = plan_doc.get("chain") or "base"

    # Recipient resolution (plan → step → env fallback).
    import os as _os
    recipient = (
        plan_doc.get("recipient")
        or borrow_step.get("recipient")
        or ""
    )
    if not recipient and chain == "base":
        recipient = _os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE", "") or ""
    if not recipient:
        raise ValueError(
            "plan_doc.recipient (or borrow_step.recipient, or "
            "ARBICORE_EXECUTOR_ADDRESS_BASE for chain=base) is required — "
            "this is the executor contract that receives + repays the loan"
        )
    token = borrow_step.get("token") or plan_doc.get("borrow_token") or ""
    amount = int(borrow_step.get("amount_wei")
                  or plan_doc.get("borrow_amount_wei") or 0)
    if amount <= 0:
        raise ValueError("borrow amount must be > 0")

    # userData resolution (explicit → plan.hops+profit → derived from
    # plan.steps[kind=swap] + signer_address → "0x").
    user_data_hex = plan_doc.get("user_data_hex")
    if not user_data_hex:
        hops = plan_doc.get("hops") or []
        profit_recipient = plan_doc.get("profit_recipient") or ""
        # Phase 10.10.7 · fall back to plan.steps[kind=swap] when the
        # top-level ``hops`` array is missing.  Manual Plan Composer +
        # opportunity plans both write their swap details into
        # ``steps`` (each swap step has a Uniswap V3 ExactInputSingle
        # tuple in ``args[0]``); we translate them into the shape
        # expected by ``build_user_data_from_hops``.
        if not hops:
            hops = _extract_hops_from_steps(plan_doc.get("steps") or [])
        # Signer wallet is the natural profit recipient — the executor
        # forwards residual balance to it after repayment.
        if not profit_recipient and signer_address:
            profit_recipient = signer_address
        if hops and profit_recipient:
            user_data_hex = build_user_data_from_hops(
                hops=hops, profit_recipient=profit_recipient,
            )
    if not user_data_hex:
        user_data_hex = "0x"

    return encode_executor_execute(
        executor_address=recipient,
        tokens=[token], amounts=[amount],
        user_data_hex=user_data_hex,
    )
