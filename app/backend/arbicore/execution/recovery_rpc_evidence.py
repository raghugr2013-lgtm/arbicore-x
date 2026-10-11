"""Trusted server-side RPC evidence for stuck-send recovery (WP-C).

Operator-supplied JSON is NEVER treated as proof that an RPC observation
occurred. This module performs read-only JSON-RPC against the configured
per-chain provider and binds results to the durable ``active_send`` record.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlparse

from .presend_invariants import TxByteBinding

logger = logging.getLogger("arbicore.execution.recovery_rpc_evidence")

CHAIN_ID_TO_NAME: Dict[int, str] = {
    1: "ethereum",
    8453: "base",
    42161: "arbitrum",
    10: "optimism",
    137: "polygon",
}

# Minimum age of rpc_entered_at before tx_absent may release (race window).
DEFAULT_ABSENT_MIN_AGE_S = float(
    os.environ.get("ARBICORE_RECOVERY_ABSENT_MIN_AGE_S", "15")
)
DEFAULT_ABSENT_REQUERY_DELAY_S = float(
    os.environ.get("ARBICORE_RECOVERY_ABSENT_REQUERY_DELAY_S", "0.05")
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hex_int(v: Any) -> int:
    if v is None:
        raise ValueError("missing hex int")
    if isinstance(v, int):
        return int(v)
    s = str(v).strip().lower()
    if s.startswith("0x"):
        return int(s, 16)
    return int(s, 10)


def _provider_label(url: str) -> str:
    """Host-only label — never full URL (may contain API keys)."""
    try:
        p = urlparse(url)
        host = p.hostname or "unknown"
        return f"rpc:{host}"
    except Exception:  # noqa: BLE001
        return "rpc:unknown"


def chain_name_for_id(chain_id: int) -> Optional[str]:
    return CHAIN_ID_TO_NAME.get(int(chain_id))


def resolve_trusted_rpc_url(chain_id: int) -> Optional[str]:
    name = chain_name_for_id(chain_id)
    if not name:
        return None
    from ..config.persistent import resolve_rpc_url_from_env

    return resolve_rpc_url_from_env(name)


@dataclass(frozen=True)
class TrustedTxObservation:
    """Server-originated observation of eth_getTransactionByHash."""

    tx_hash: str
    status: str  # found | not_found | error
    tx: Optional[Dict[str, Any]]
    observed_at: str
    provider_label: str
    observed_chain_id: int
    detail: Optional[str] = None


@dataclass(frozen=True)
class TrustedNonceObservation:
    pending_nonce: int
    latest_nonce: int
    observed_at: str
    provider_label: str
    observed_chain_id: int


@dataclass(frozen=True)
class TrustedChainObservation:
    observed_chain_id: int
    expected_chain_id: int
    observed_at: str
    provider_label: str


class RecoveryRpcVerifier:
    """Authoritative read-only chain observer for recovery decisions.

    ``rpc_call`` injectable for tests:
        async def rpc_call(method: str, params: list) -> Any
    When omitted, uses configured ``EthJsonRpcProvider`` for the chain.
    """

    def __init__(
        self,
        *,
        rpc_call: Optional[Callable] = None,
        absent_min_age_s: Optional[float] = None,
        absent_requery_delay_s: Optional[float] = None,
    ):
        self._rpc_call = rpc_call
        self.absent_min_age_s = (
            DEFAULT_ABSENT_MIN_AGE_S
            if absent_min_age_s is None
            else float(absent_min_age_s)
        )
        self.absent_requery_delay_s = (
            DEFAULT_ABSENT_REQUERY_DELAY_S
            if absent_requery_delay_s is None
            else float(absent_requery_delay_s)
        )
        self._providers: Dict[int, Any] = {}

    async def _call(self, chain_id: int, method: str, params: list) -> Any:
        if self._rpc_call is not None:
            return await self._rpc_call(method, params)
        url = resolve_trusted_rpc_url(chain_id)
        if not url:
            raise RuntimeError(
                f"trusted_rpc_unconfigured: no RPC URL for chain_id={chain_id}"
            )
        name = chain_name_for_id(chain_id) or "unknown"
        if chain_id not in self._providers:
            from ..providers.rpc import EthJsonRpcProvider

            self._providers[chain_id] = EthJsonRpcProvider(chain=name, url=url)
        return await self._providers[chain_id]._call(method, params)

    def _label(self, chain_id: int) -> str:
        if self._rpc_call is not None:
            return "rpc:injected"
        url = resolve_trusted_rpc_url(chain_id) or ""
        return _provider_label(url)

    async def observe_chain_id(self, expected_chain_id: int) -> TrustedChainObservation:
        try:
            raw = await self._call(expected_chain_id, "eth_chainId", [])
            observed = _hex_int(raw)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"rpc_chain_id_unavailable: {type(exc).__name__}"
            ) from exc
        return TrustedChainObservation(
            observed_chain_id=observed,
            expected_chain_id=int(expected_chain_id),
            observed_at=_now_iso(),
            provider_label=self._label(expected_chain_id),
        )

    async def observe_transaction(
        self, expected_chain_id: int, tx_hash: str
    ) -> TrustedTxObservation:
        h = (tx_hash or "").strip().lower()
        label = self._label(expected_chain_id)
        at = _now_iso()
        try:
            result = await self._call(
                expected_chain_id, "eth_getTransactionByHash", [h]
            )
        except Exception as exc:  # noqa: BLE001
            return TrustedTxObservation(
                tx_hash=h,
                status="error",
                tx=None,
                observed_at=at,
                provider_label=label,
                observed_chain_id=int(expected_chain_id),
                detail=type(exc).__name__,
            )
        if result is None:
            return TrustedTxObservation(
                tx_hash=h,
                status="not_found",
                tx=None,
                observed_at=at,
                provider_label=label,
                observed_chain_id=int(expected_chain_id),
            )
        if not isinstance(result, dict):
            return TrustedTxObservation(
                tx_hash=h,
                status="error",
                tx=None,
                observed_at=at,
                provider_label=label,
                observed_chain_id=int(expected_chain_id),
                detail="malformed_tx_result",
            )
        return TrustedTxObservation(
            tx_hash=h,
            status="found",
            tx=result,
            observed_at=at,
            provider_label=label,
            observed_chain_id=int(expected_chain_id),
        )

    async def observe_nonces(
        self, expected_chain_id: int, signer: str
    ) -> TrustedNonceObservation:
        addr = (signer or "").strip().lower()
        try:
            pending_raw = await self._call(
                expected_chain_id, "eth_getTransactionCount", [addr, "pending"]
            )
            latest_raw = await self._call(
                expected_chain_id, "eth_getTransactionCount", [addr, "latest"]
            )
            pending = _hex_int(pending_raw)
            latest = _hex_int(latest_raw)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"rpc_nonce_unavailable: {type(exc).__name__}"
            ) from exc
        return TrustedNonceObservation(
            pending_nonce=pending,
            latest_nonce=latest,
            observed_at=_now_iso(),
            provider_label=self._label(expected_chain_id),
            observed_chain_id=int(expected_chain_id),
        )

    async def observe_nonces_consistent(
        self, expected_chain_id: int, signer: str
    ) -> TrustedNonceObservation:
        """Two observations; diverge → fail closed (delayed/pending race)."""
        first = await self.observe_nonces(expected_chain_id, signer)
        delay = max(0.0, float(self.absent_requery_delay_s))
        if delay:
            await asyncio.sleep(delay)
        second = await self.observe_nonces(expected_chain_id, signer)
        if (
            first.pending_nonce != second.pending_nonce
            or first.latest_nonce != second.latest_nonce
        ):
            raise RuntimeError(
                "rpc_nonce_unstable: pending/latest changed between observations"
            )
        return second


def rpc_tx_to_binding_fields(
    rpc_tx: Dict[str, Any], *, fallback_chain_id: int
) -> Dict[str, Any]:
    """Map eth_getTransactionByHash result → TxByteBinding.from_tx fields."""
    data = rpc_tx.get("input")
    if data is None:
        data = rpc_tx.get("data")
    gas_price = rpc_tx.get("gasPrice")
    if gas_price is None:
        # Legacy broadcast path only; EIP-1559 without gasPrice cannot bind.
        raise ValueError("rpc_tx_missing_gasPrice_cannot_bind")
    chain_raw = rpc_tx.get("chainId")
    if chain_raw is None:
        chain_id = int(fallback_chain_id)
    else:
        chain_id = _hex_int(chain_raw)
    return {
        "to": str(rpc_tx.get("to") or "").lower(),
        "data": str(data or "").lower(),
        "value": _hex_int(rpc_tx.get("value") or 0),
        "chainId": chain_id,
        "nonce": _hex_int(rpc_tx.get("nonce")),
        "gas": _hex_int(rpc_tx.get("gas")),
        "gasPrice": _hex_int(gas_price),
    }


def assert_tx_bound_to_stuck(
    rpc_tx: Dict[str, Any],
    *,
    stuck: Dict[str, Any],
) -> str:
    """Verify RPC tx matches durable stuck-send binding. Returns digest.

    Checks: chain_id, nonce, signer(from), tx_binding_digest.
    """
    digest = str(stuck.get("tx_binding_digest") or "").strip().lower()
    if not digest:
        raise PermissionError("stuck_send_missing_tx_binding_digest")
    try:
        stuck_chain = int(stuck["chain_id"])
        stuck_nonce = int(stuck["nonce"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PermissionError("stuck_send_missing_chain_or_nonce") from exc
    signer = str(stuck.get("signer") or "").strip().lower()
    if not signer:
        raise PermissionError("stuck_send_missing_signer")

    from_addr = str(rpc_tx.get("from") or "").strip().lower()
    if from_addr != signer:
        raise PermissionError(
            f"tx_signer_mismatch: rpc_from={from_addr!r} stuck={signer!r}"
        )

    fields = rpc_tx_to_binding_fields(rpc_tx, fallback_chain_id=stuck_chain)
    if int(fields["chainId"]) != stuck_chain:
        raise PermissionError(
            f"tx_chain_mismatch: rpc={fields['chainId']} stuck={stuck_chain}"
        )
    if int(fields["nonce"]) != stuck_nonce:
        raise PermissionError(
            f"tx_nonce_mismatch: rpc={fields['nonce']} stuck={stuck_nonce}"
        )
    bound = TxByteBinding.from_tx(fields)
    if bound.digest.lower() != digest:
        raise PermissionError(
            "tx_binding_digest_mismatch: observed transaction is not the "
            "stuck send (unbound or replaced)"
        )
    return bound.digest


def parse_rpc_entered_age_s(active: Dict[str, Any], *, now: Optional[float] = None) -> float:
    """Age since rpc_entered_at; unknown → 0 (fail closed for min-age checks)."""
    raw = active.get("rpc_entered_at")
    if not raw:
        return 0.0
    try:
        # Support trailing Z
        s = str(raw).replace("Z", "+00:00")
        entered = datetime.fromisoformat(s)
        if entered.tzinfo is None:
            entered = entered.replace(tzinfo=timezone.utc)
        now_ts = time.time() if now is None else float(now)
        return max(0.0, now_ts - entered.timestamp())
    except Exception:  # noqa: BLE001
        return 0.0


def evidence_audit_summary(
    *,
    chain_obs: Optional[TrustedChainObservation] = None,
    tx_obs: Optional[TrustedTxObservation] = None,
    nonce_obs: Optional[TrustedNonceObservation] = None,
    binding_ok: Optional[bool] = None,
    candidate_tx_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Safe audit fields — no RPC URLs, keys, or signed bytes."""
    out: Dict[str, Any] = {
        "evidence_authority": "server_trusted_rpc",
        "candidate_tx_hash_prefix": None,
        "binding_ok": binding_ok,
    }
    if candidate_tx_hash:
        h = candidate_tx_hash.lower()
        out["candidate_tx_hash_prefix"] = (h[:10] + "…") if len(h) > 12 else h
    if chain_obs:
        out["observed_chain_id"] = chain_obs.observed_chain_id
        out["expected_chain_id"] = chain_obs.expected_chain_id
        out["chain_provider"] = chain_obs.provider_label
        out["chain_observed_at"] = chain_obs.observed_at
    if tx_obs:
        out["tx_lookup"] = tx_obs.status
        out["tx_observed_at"] = tx_obs.observed_at
        out["tx_provider"] = tx_obs.provider_label
    if nonce_obs:
        out["pending_nonce"] = nonce_obs.pending_nonce
        out["latest_nonce"] = nonce_obs.latest_nonce
        out["nonce_observed_at"] = nonce_obs.observed_at
        out["nonce_provider"] = nonce_obs.provider_label
    return out
