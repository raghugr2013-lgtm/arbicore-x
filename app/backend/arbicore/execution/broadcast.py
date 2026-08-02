"""Wave 7C · Broadcast Pipeline (LIMITED_LIVE bytes-level).

The **only** path in the entire codebase where ``eth_sendRawTransaction``
is ever invoked.  Six independent gates protect the call:

    1. Kill switch                   (Wave 6D)
    2. Strategy mode ladder          (Wave 6A) — must be LIMITED_LIVE / FULL_LIVE
    3. Capital policy allocator      (Wave 6D)
    4. Secret resolution             (Wave 6A) — length-only proof
    5. eth_call PREFLIGHT SIMULATION (Wave 7C) — the tx must succeed off-chain
    6. Operator "confirm" flag       (Wave 7C) — explicit boolean in the request

Only when ALL SIX gates PASS does the signer sign the raw transaction
and submit it to the RPC endpoint via ``eth_sendRawTransaction``.  The
resulting receipt (tx hash, nonce, gas price, mined block) is
persisted as an evidence tap under Wave 5's bundle signing pipeline.

**One-shot posture**: this module is designed for the operator's
first one-or-two validation broadcasts.  It DOES NOT support
concurrent transactions, mempool replacement, or bundle-level
scheduling — those are LIMITED_LIVE follow-on refinements.
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .calldata import EncodedCall, encode_plan_head_call
from .kill_switch import KillSwitchEngagedError

logger = logging.getLogger("arbicore.execution.broadcast")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


CHAIN_IDS: Dict[str, int] = {
    "ethereum": 1, "base": 8453, "arbitrum": 42_161,
    "optimism": 10, "polygon": 137,
}


# Preflight revert selector decoder — well-known 4-byte selectors from the
# LIMITED_LIVE contract stack (FlashLoanReceiver, Balancer V2 Vault,
# Uniswap V3 router+pool, standard Solidity panic + Error(string)).  When
# an eth_call revert returns "data" we look up the first 4 bytes here.
_REVERT_SELECTORS: Dict[str, str] = {
    # FlashLoanReceiver (canonical_repo/contracts/FlashLoanReceiver.sol)
    "0x30cd7471": "FlashLoanReceiver.NotOwner()",
    "0x62df0545": "FlashLoanReceiver.NotVault()",
    "0xea8e4eb5": "FlashLoanReceiver.NotAuthorized()",
    "0xaf36925d": "FlashLoanReceiver.HopFailed(uint256)",
    "0x175edf10": "FlashLoanReceiver.RepayFailed(address)",
    # Balancer V2 Vault common
    "0xe08b8af0": "BalancerV2.SwapDeadline()",
    "0x8beb9d16": "BalancerV2.ReentrancyGuard()",
    "0xf4d678b8": "InsufficientBalance() [Balancer or ERC20]",
    # Uniswap V3 router + pool
    "0x39d35496": "UniV3.V3TooLittleReceived()",
    "0x817275ab": "UniV3.STF() [SafeTransferFrom]",
    "0x24df576f": "UniV3.TooMuchRequested()",
    "0x20db8267": "UniV3.InvalidPath()",
    "0x2083cd40": "UniV3.InvalidPool()",
    # Standard Solidity
    "0x08c379a0": "Error(string)   [Solidity require()]",
    "0x4e487b71": "Panic(uint256)   [Solidity assert/overflow/etc.]",
    # ERC20 std
    "0x13be252b": "ERC20.InsufficientAllowance()",
    "0xe450d38c": "ERC20InsufficientBalance(address,uint256,uint256)",
    "0xfb8f41b2": "ERC20InsufficientAllowance(address,uint256,uint256)",
}


def decode_revert_data(data: Optional[str]) -> Optional[str]:
    """Best-effort revert selector → human name.  Returns None when the
    data is empty/unknown so the caller can surface the raw bytes."""
    if not data or not isinstance(data, str) or not data.startswith("0x"):
        return None
    sel = data[:10].lower()
    name = _REVERT_SELECTORS.get(sel)
    if name:
        # Error(string) → try to extract the string payload
        if sel == "0x08c379a0" and len(data) > 138:
            try:
                from eth_abi import decode as _ad
                payload = bytes.fromhex(data[10:])
                (msg,) = _ad(["string"], payload)
                return f"{name}: {msg!r}"
            except Exception:  # noqa: BLE001
                pass
        return name
    return f"unknown selector {sel}"


# Component / origin extraction from a decoded name like
# "FlashLoanReceiver.NotAuthorized()" → ("FlashLoanReceiver",
# "NotAuthorized()").  Falls back gracefully for atypical labels.
def revert_component(decoded: Optional[str]) -> Optional[str]:
    if not decoded or not isinstance(decoded, str):
        return None
    # "unknown selector 0x…" or "Error(string): …" — no explicit component.
    if decoded.startswith("unknown selector"):
        return None
    if "." in decoded:
        return decoded.split(".", 1)[0]
    if "(" in decoded:
        return decoded.split("(", 1)[0]
    return None


# Human-readable explanations for each known selector.  Kept intentionally
# terse so the operator UI can render them inline without cluttering the
# preflight panel.
_REVERT_EXPLANATIONS: Dict[str, str] = {
    "0x30cd7471": "Only the wallet stored as owner may call this executor.",
    "0x62df0545": "Only the Balancer Vault may invoke receiveFlashLoan on this contract.",
    "0xea8e4eb5": "The caller is not authorised to invoke the executor entry point.",
    "0xaf36925d": "A swap hop returned zero or reverted; the aggregate route failed.",
    "0x175edf10": "Flash loan repayment token transfer to the Vault failed.",
    "0xe08b8af0": "Balancer swap failed the request deadline check.",
    "0x8beb9d16": "Balancer refused a nested/re-entrant call.",
    "0xf4d678b8": "Insufficient balance to cover the required transfer.",
    "0x39d35496": "Uniswap V3 output amount fell below minAmountOut — slippage tripped.",
    "0x817275ab": "Uniswap V3 safeTransferFrom failed (token balance / allowance / hook).",
    "0x24df576f": "Uniswap V3 sqrtPrice bounds violated (path too aggressive).",
    "0x20db8267": "Uniswap V3 route path is malformed.",
    "0x2083cd40": "Uniswap V3 pool address is not initialised or wrong fee tier.",
    "0x08c379a0": "Contract reverted with a require()/revert(string) message.",
    "0x4e487b71": "Solidity panic (arithmetic overflow, div-by-zero, invalid opcode…).",
    "0x13be252b": "ERC20 allowance is smaller than the requested spend.",
    "0xe450d38c": "ERC20 balance smaller than the requested transfer.",
    "0xfb8f41b2": "ERC20 allowance smaller than the requested transferFrom.",
}


def revert_explanation(data: Optional[str]) -> Optional[str]:
    """Human sentence for the operator UI.  None when we have no mapping."""
    if not data or not isinstance(data, str) or not data.startswith("0x"):
        return None
    return _REVERT_EXPLANATIONS.get(data[:10].lower())


@dataclass
class BroadcastReceipt:
    receipt_id: str
    plan_id: str
    strategy: str
    mode: str
    chain: str
    signer_wallet_id: Optional[str]
    signer_address: Optional[str]
    tx_hash: Optional[str]
    nonce: Optional[int]
    gas_price_wei: Optional[int]
    gas_limit: Optional[int]
    value_wei: int
    encoded_call: Optional[Dict[str, Any]]
    preflight_ok: bool
    preflight_error: Optional[str]
    broadcast_sent: bool
    denied_reasons: List[str]
    gate_ladder: Dict[str, str]
    rpc_endpoint_redacted: Optional[str]
    generated_at: str
    # Phase 10.10.3 — preserved for operator visibility on preflight revert.
    # Optional with defaults so all pre-existing constructor call sites
    # keep working unchanged.
    preflight_revert_data: Optional[str] = None
    preflight_revert_decoded: Optional[str] = None
    # Phase 10.10.4 — added when the RPC omits `data` from an eth_call
    # error and we recovered the selector via a debug_traceCall fallback,
    # plus operator-facing metadata for the preflight error panel.
    preflight_revert_source: Optional[str] = None  # 'eth_call' | 'debug_traceCall' | 'unavailable'
    preflight_revert_component: Optional[str] = None  # e.g. 'FlashLoanReceiver', 'UniV3', 'BalancerV2'
    preflight_revert_explanation: Optional[str] = None
    # Phase 10.10.6.1 — per-attempt trace diagnostics (populated only when
    # the eth_call omitted `error.data` and we tried debug_traceCall).
    # Each entry: {tracer, outcome, rpc_code?, rpc_message?, source?, …}
    preflight_trace_diagnostic: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BroadcastError(RuntimeError):
    pass


class LimitedLiveBroadcaster:
    """Real EVM broadcaster gated by every prior safety layer."""

    def __init__(self, *,
                 kill_switch,
                 mode_repo,
                 wallet_registry,
                 secret_registry,
                 capital_allocator,
                 evidence_signer=None,
                 rpc_url_env: str = "ARBICORE_RPC_URL",
                 preflight_only_default: bool = True):
        self._kill = kill_switch
        self._mode = mode_repo
        self._wallets = wallet_registry
        self._secrets = secret_registry
        self._alloc = capital_allocator
        self._evidence = evidence_signer
        self._rpc_url_env = rpc_url_env
        self._preflight_only_default = bool(preflight_only_default)

    # ------------------------------------------------------------------
    # RPC helpers — every method allowlisted
    # ------------------------------------------------------------------

    def _rpc_url(self) -> Optional[str]:
        return os.environ.get(self._rpc_url_env)

    async def _rpc(self, method: str, params: Optional[List[Any]] = None,
                    *, url: Optional[str] = None,
                    read_only: bool = True) -> Any:
        allowed_read = {"eth_call", "eth_estimateGas", "eth_chainId",
                        "eth_blockNumber", "eth_getBalance",
                        "eth_getTransactionCount", "eth_gasPrice",
                        "debug_traceCall"}
        allowed_write = {"eth_sendRawTransaction"}
        if read_only:
            if method not in allowed_read:
                raise PermissionError(f"read-only RPC refused method '{method}'")
        else:
            if method not in allowed_write:
                raise PermissionError(f"write-side RPC refused method '{method}'")
        rpc_url = url or self._rpc_url()
        if not rpc_url:
            raise BroadcastError("ARBICORE_RPC_URL not configured")
        import httpx
        # Phase 10.10.6.2 · verification log — masks API key, prints only
        # scheme+host and a truncated path stub so we can prove the
        # broadcast pipeline is hitting the Alchemy endpoint and not a
        # fallback.  One line per RPC call.
        try:
            from urllib.parse import urlparse as _up
            _p = _up(rpc_url)
            _host = _p.hostname or "unknown"
            _path = _p.path or ""
            _path_stub = (_path[:12] + "…<REDACTED>") if len(_path) > 12 else _path
            logger.info(
                "RPC dispatch method=%s scheme=%s host=%s path=%s",
                method, _p.scheme, _host, _path_stub,
            )
        except Exception:  # noqa: BLE001
            pass
        payload = {"jsonrpc": "2.0", "id": 1, "method": method,
                   "params": list(params or [])}
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post(rpc_url, json=payload)
            r.raise_for_status()
            body = r.json()
            if "error" in body:
                err = body["error"] or {}
                # Preserve revert data (selector bytes) if the RPC returned
                # it — many nodes return {"code":3,"message":"execution
                # reverted","data":"0x..."} where data carries the revert
                # selector.  A public node without debug data returns just
                # code+message.  Attach whatever we have to the exception
                # so the receipt / operator UI can decode it.
                exc = BroadcastError(f"rpc error: {err}")
                exc.rpc_error = err  # type: ignore[attr-defined]
                exc.revert_data = (err.get("data") if isinstance(err, dict) else None)
                raise exc
            return body.get("result")

    async def _trace_call_revert_data(
        self, call_obj: Dict[str, Any],
    ) -> "tuple[Optional[str], List[Dict[str, Any]]]":
        """Fallback: recover the revert selector via ``debug_traceCall``.

        Some public RPC endpoints (Base / Ankr / drpc.org) strip the
        ``data`` field from JSON-RPC ``eth_call`` errors, so all the
        operator sees is a generic ``execution reverted``.  Nodes that
        DO expose the ``debug_*`` namespace will still hand us the
        return bytes when we replay the same call under a tracer.

        Returns ``(recovered_hex, diagnostics)`` where ``diagnostics`` is
        a per-attempt list — one entry per tracer flavour we tried — so
        the operator UI can render precisely WHY the fallback did or
        didn't work (method_not_found, forbidden, empty output, …).

        Non-raising: this is best-effort and MUST NOT mask the original
        ``BroadcastError``.
        """
        # Two tracer flavours are tried in order:
        #   1. callTracer  → { output, error }
        #   2. default structLog tracer → { returnValue, failed }
        # Both return the revert bytes when the top-level call reverts.
        logger.info(
            "debug_traceCall fallback engaged for preflight (rpc omitted error.data)"
        )
        candidates = (
            ("callTracer", [call_obj, "latest", {"tracer": "callTracer"}]),
            ("structLog",  [call_obj, "latest", {}]),
        )
        diagnostics: List[Dict[str, Any]] = []
        for tracer_name, params in candidates:
            entry: Dict[str, Any] = {"tracer": tracer_name}
            try:
                result = await self._rpc("debug_traceCall", params)
            except BroadcastError as exc:
                err = getattr(exc, "rpc_error", {}) or {}
                code = err.get("code") if isinstance(err, dict) else None
                message = (err.get("message") if isinstance(err, dict) else None) or str(exc)
                entry["rpc_code"] = code
                entry["rpc_message"] = message
                if code == -32601 or "method" in (message or "").lower() and "not" in (message or "").lower():
                    entry["outcome"] = "method_not_found"
                elif code in (-32000, -32002, -32601) and any(
                    tok in (message or "").lower() for tok in ("forbidden", "unauthorized", "unauthorised", "not allowed", "paid plan")
                ):
                    entry["outcome"] = "forbidden"
                else:
                    entry["outcome"] = "rpc_error"
                logger.warning(
                    "debug_traceCall fallback failed [%s]: code=%s message=%s",
                    tracer_name, code, message,
                )
                diagnostics.append(entry)
                continue
            except Exception as exc:  # noqa: BLE001
                entry["outcome"] = "transport_error"
                entry["rpc_message"] = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "debug_traceCall transport error [%s]: %s", tracer_name, exc,
                )
                diagnostics.append(entry)
                continue

            if not isinstance(result, dict):
                entry["outcome"] = "empty_response"
                entry["result_type"] = type(result).__name__
                diagnostics.append(entry)
                continue

            # callTracer style
            out = result.get("output")
            if isinstance(out, str) and out.startswith("0x") and len(out) >= 10:
                entry["outcome"] = "recovered"
                entry["source"] = "output"
                diagnostics.append(entry)
                return out, diagnostics
            # structLog style
            ret = result.get("returnValue")
            if isinstance(ret, str) and ret:
                normalized = ret if ret.startswith("0x") else "0x" + ret
                if len(normalized) >= 10:
                    entry["outcome"] = "recovered"
                    entry["source"] = "returnValue"
                    diagnostics.append(entry)
                    return normalized, diagnostics
            # callTracer sometimes nests reverted sub-calls; scan one level.
            for sub in (result.get("calls") or []):
                sub_out = sub.get("output") if isinstance(sub, dict) else None
                if isinstance(sub_out, str) and sub_out.startswith("0x") and len(sub_out) >= 10:
                    entry["outcome"] = "recovered"
                    entry["source"] = "nested_call"
                    diagnostics.append(entry)
                    return sub_out, diagnostics

            entry["outcome"] = "empty_output"
            entry["top_level_output"] = out if isinstance(out, str) else None
            entry["nested_call_count"] = len(result.get("calls") or [])
            diagnostics.append(entry)

        return None, diagnostics

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def broadcast_plan(self,
                              plan_doc: Dict[str, Any],
                              *,
                              actor: str = "operator",
                              confirm: bool = False,
                              force_broadcast: bool = False,
                              expected_net_profit_usd: Optional[float] = None,
                              ) -> BroadcastReceipt:
        """Run the 6-gate ladder + preflight and (optionally) submit.

        ``confirm`` defaults to ``False`` — the operator must supply
        ``{"confirm": true}`` to move past the preflight step.  Without
        it, the pipeline emits a fully-populated receipt with
        ``preflight_ok=True`` (or an error) and ``broadcast_sent=False``.

        ``force_broadcast=False`` combined with ``confirm=True`` and
        every gate PASS is the only combination that ever emits
        ``eth_sendRawTransaction``.
        """
        receipt_id = f"bcast-{uuid.uuid4().hex}"
        plan_id = plan_doc.get("plan_id") or ""
        strategy = plan_doc.get("strategy") or ""
        chain = plan_doc.get("chain") or "base"
        signer_wallet_id = plan_doc.get("signer_wallet_id")
        gate_ladder: Dict[str, str] = {}
        denied: List[str] = []

        # ----------------- Gate 1: kill switch ---------------------------
        try:
            await self._kill.guard()
            gate_ladder["kill_switch"] = "PASS"
        except KillSwitchEngagedError as exc:
            gate_ladder["kill_switch"] = "DENIED"
            denied.append(f"kill_switch_engaged: {exc}")

        # ----------------- Gate 2: mode ladder ---------------------------
        try:
            row = await self._mode.get(strategy)
            mode = (row or {}).get("mode") or "OBSERVE"
        except Exception:  # noqa: BLE001
            mode = "OBSERVE"
        if mode in ("LIMITED_LIVE", "FULL_LIVE"):
            gate_ladder["mode"] = "PASS"
        else:
            gate_ladder["mode"] = "DENIED"
            denied.append(f"mode_gate: strategy '{strategy}' is '{mode}'")

        # ----------------- Gate 3: capital policy ------------------------
        alloc = await self._alloc.evaluate(
            strategy=strategy,
            proposed_usd=float(plan_doc.get("borrow_amount_usd") or 0),
            expected_net_profit_usd=expected_net_profit_usd,
        )
        if alloc.approved:
            gate_ladder["capital_policy"] = "PASS"
        else:
            gate_ladder["capital_policy"] = "DENIED"
            denied.append(f"capital_policy: {alloc.binding_constraint}")

        # ----------------- Gate 4: secret resolution ---------------------
        wallet_doc = None
        priv_hex: Optional[str] = None
        signer_address: Optional[str] = None
        try:
            if not signer_wallet_id:
                raise BroadcastError("plan has no signer_wallet_id")
            wallet_doc = await self._wallets.get(signer_wallet_id)
            if not wallet_doc:
                raise BroadcastError(f"wallet '{signer_wallet_id}' not registered")
            if wallet_doc.get("execution_role") != "gas":
                raise BroadcastError(
                    f"wallet role '{wallet_doc.get('execution_role')}' — must be 'gas'"
                )
            handle = wallet_doc.get("secret_handle_id")
            if not handle:
                raise BroadcastError("wallet has no secret_handle_id")
            material = await self._secrets.resolve(handle)
            if not material:
                raise BroadcastError("secret_handle_id did not resolve")
            # Accept either raw 32-byte key or 0x-prefixed hex.
            if isinstance(material, bytes):
                if len(material) == 32:
                    priv_hex = "0x" + material.hex()
                else:
                    priv_hex = material.decode("utf-8", errors="strict").strip()
            else:
                priv_hex = str(material).strip()
            if not priv_hex.startswith("0x"):
                priv_hex = "0x" + priv_hex
            from eth_account import Account
            signer_address = Account.from_key(priv_hex).address
            wallet_addr = wallet_doc.get("address")
            if wallet_addr and wallet_addr.lower() != signer_address.lower():
                raise BroadcastError(
                    f"resolved secret produces address {signer_address} "
                    f"but wallet is registered as {wallet_addr}"
                )
            gate_ladder["secret_resolution"] = "PASS"
        except Exception as exc:  # noqa: BLE001
            gate_ladder["secret_resolution"] = "DENIED"
            denied.append(f"secret_resolution: {type(exc).__name__}: {exc}")

        # ----------------- Encode calldata (needed by preflight) ---------
        encoded: Optional[EncodedCall] = None
        try:
            encoded = encode_plan_head_call(plan_doc, signer_address=signer_address)
        except Exception as exc:  # noqa: BLE001
            gate_ladder["calldata"] = "DENIED"
            denied.append(f"calldata_encoding: {type(exc).__name__}: {exc}")
        else:
            gate_ladder["calldata"] = "PASS"

        # Short-circuit if any of the first four gates + calldata fail.
        if denied:
            return BroadcastReceipt(
                receipt_id=receipt_id, plan_id=plan_id, strategy=strategy,
                mode=mode, chain=chain,
                signer_wallet_id=signer_wallet_id,
                signer_address=signer_address, tx_hash=None,
                nonce=None, gas_price_wei=None, gas_limit=None,
                value_wei=0,
                encoded_call=(encoded.to_dict() if encoded else None),
                preflight_ok=False, preflight_error=None,
                preflight_revert_data=None, preflight_revert_decoded=None,
                broadcast_sent=False,
                denied_reasons=denied, gate_ladder=gate_ladder,
                rpc_endpoint_redacted=None,
                generated_at=_now_iso(),
            )

        assert encoded is not None
        # ----------------- Gate 5: eth_call preflight --------------------
        preflight_ok = False
        preflight_error: Optional[str] = None
        preflight_revert_data: Optional[str] = None
        preflight_revert_decoded: Optional[str] = None
        preflight_revert_source: Optional[str] = None
        preflight_revert_component: Optional[str] = None
        preflight_revert_explanation: Optional[str] = None
        preflight_trace_diagnostic: Optional[List[Dict[str, Any]]] = None
        # Defined here so the debug_traceCall fallback in the except
        # block can reference it even when the exception originates
        # before the call object is constructed.
        call_obj: Optional[Dict[str, Any]] = None
        gas_price_wei: Optional[int] = None
        nonce: Optional[int] = None
        gas_limit: Optional[int] = encoded.gas_limit_hint
        rpc_url_hint: Optional[str] = None
        try:
            rpc_url_hint = self._rpc_url()
            # sanity: chain_id
            chain_id_hex = await self._rpc("eth_chainId")
            observed = int(chain_id_hex, 16) if isinstance(chain_id_hex, str) else int(chain_id_hex)
            expected = CHAIN_IDS.get(chain)
            if expected and observed != expected:
                raise BroadcastError(
                    f"chain-id mismatch — plan says '{chain}' ({expected}) but RPC reports {observed}"
                )
            # gas price
            gp_hex = await self._rpc("eth_gasPrice")
            gas_price_wei = int(gp_hex, 16) if isinstance(gp_hex, str) else int(gp_hex or 0)
            # nonce
            nc_hex = await self._rpc("eth_getTransactionCount",
                                       [signer_address, "pending"])
            nonce = int(nc_hex, 16) if isinstance(nc_hex, str) else int(nc_hex or 0)
            # eth_call preflight — MUST return without revert
            call_obj = {
                "from": signer_address,
                "to": encoded.contract_address,
                "data": encoded.calldata_hex,
                "value": hex(encoded.value_wei),
            }
            await self._rpc("eth_call", [call_obj, "latest"])
            # eth_estimateGas — a second sanity check
            try:
                eg_hex = await self._rpc("eth_estimateGas", [call_obj])
                estimated = int(eg_hex, 16) if isinstance(eg_hex, str) else int(eg_hex or 0)
                if estimated > 0:
                    gas_limit = int(estimated * 1.2)  # 20% headroom
            except Exception:  # noqa: BLE001
                pass
            preflight_ok = True
            gate_ladder["preflight"] = "PASS"
        except Exception as exc:  # noqa: BLE001
            preflight_error = f"{type(exc).__name__}: {exc}"
            # Extract revert selector bytes if the RPC returned them.
            preflight_revert_data = getattr(exc, "revert_data", None)
            if preflight_revert_data:
                preflight_revert_source = "eth_call"
            else:
                # Public / free RPC nodes frequently omit the `data`
                # field from eth_call errors.  Attempt a debug_traceCall
                # replay of the exact call to recover the revert bytes.
                traced = None
                trace_diag: List[Dict[str, Any]] = []
                if call_obj is not None:
                    try:
                        traced, trace_diag = await self._trace_call_revert_data(call_obj)
                    except Exception as diag_exc:  # noqa: BLE001 — trace must never mask
                        traced = None
                        trace_diag = [{
                            "tracer": "outer",
                            "outcome": "transport_error",
                            "rpc_message": f"{type(diag_exc).__name__}: {diag_exc}",
                        }]
                preflight_trace_diagnostic = trace_diag or None
                if traced:
                    preflight_revert_data = traced
                    preflight_revert_source = "debug_traceCall"
                else:
                    preflight_revert_source = "unavailable" if call_obj else "no_call_obj"
            preflight_revert_decoded = decode_revert_data(preflight_revert_data)
            preflight_revert_component = revert_component(preflight_revert_decoded)
            preflight_revert_explanation = revert_explanation(preflight_revert_data)
            gate_ladder["preflight"] = "DENIED"
            detail = preflight_error
            if preflight_revert_decoded:
                detail = f"{preflight_error} — decoded: {preflight_revert_decoded}"
            denied.append(f"preflight: {detail}")

        # Redact RPC url for the receipt
        try:
            from urllib.parse import urlparse
            p = urlparse(rpc_url_hint or "")
            rpc_redacted = (f"{p.scheme}://{p.hostname}"
                             + (f":{p.port}" if p.port else "")) if p.hostname else None
        except Exception:  # noqa: BLE001
            rpc_redacted = None

        # ----------------- Gate 6: operator confirm ----------------------
        if confirm:
            gate_ladder["operator_confirm"] = "PASS"
        else:
            gate_ladder["operator_confirm"] = "DENIED"
            denied.append(
                "operator_confirm: missing — set confirm=true to authorise broadcast"
            )

        broadcast_sent = False
        tx_hash: Optional[str] = None
        if not denied and preflight_ok and confirm and not force_broadcast:
            # All six gates PASS — sign + broadcast.
            try:
                from eth_account import Account
                acct = Account.from_key(priv_hex)  # type: ignore[arg-type]
                # Legacy tx envelope (chain-independent; simplest for Base).
                tx = {
                    "to": encoded.contract_address,
                    "value": encoded.value_wei,
                    "gas": int(gas_limit or encoded.gas_limit_hint),
                    "gasPrice": int(gas_price_wei or 0),
                    "nonce": int(nonce or 0),
                    "data": encoded.calldata_hex,
                    "chainId": CHAIN_IDS.get(chain, 0),
                }
                signed = acct.sign_transaction(tx)
                raw_hex = signed.raw_transaction.hex()
                if not raw_hex.startswith("0x"):
                    raw_hex = "0x" + raw_hex
                # ---- THE ONE AND ONLY BROADCAST CALL SITE ----
                tx_hash = await self._rpc(
                    "eth_sendRawTransaction", [raw_hex], read_only=False,
                )
                broadcast_sent = True
                gate_ladder["broadcast"] = "SENT"
            except Exception as exc:  # noqa: BLE001
                gate_ladder["broadcast"] = "FAILED"
                denied.append(f"broadcast: {type(exc).__name__}: {exc}")
        else:
            gate_ladder["broadcast"] = "HELD"

        return BroadcastReceipt(
            receipt_id=receipt_id, plan_id=plan_id, strategy=strategy,
            mode=mode, chain=chain,
            signer_wallet_id=signer_wallet_id,
            signer_address=signer_address, tx_hash=tx_hash,
            nonce=nonce, gas_price_wei=gas_price_wei, gas_limit=gas_limit,
            value_wei=encoded.value_wei,
            encoded_call=encoded.to_dict(),
            preflight_ok=preflight_ok, preflight_error=preflight_error,
            preflight_revert_data=preflight_revert_data,
            preflight_revert_decoded=preflight_revert_decoded,
            preflight_revert_source=preflight_revert_source,
            preflight_revert_component=preflight_revert_component,
            preflight_revert_explanation=preflight_revert_explanation,
            preflight_trace_diagnostic=preflight_trace_diagnostic,
            broadcast_sent=broadcast_sent,
            denied_reasons=denied, gate_ladder=gate_ladder,
            rpc_endpoint_redacted=rpc_redacted,
            generated_at=_now_iso(),
        )
