"""EVM JSON-RPC provider + Solana RPC provider (Stage 2 · v2.5.0).

Both are thin read-only wrappers around the public RPC endpoints for
the requested chains. All calls go through ``httpx``. Zero signing.
The registry treats them as ``ProviderKind.RPC``.

Chains supported (EVM):
  - ethereum   (mainnet)
  - arbitrum   (arb1)
  - base       (base)
  - polygon    (matic)
  - optimism   (op)
  - bnb        (bsc)

Non-EVM:
  - solana     (mainnet-beta)

Endpoint URLs come from env — see ``providers/bootstrap.py`` — with
sensible free-tier public defaults. Consumers should set
``PROVIDER_RPC_URL_<CHAIN>`` for higher-throughput / authed URLs.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from typing import Any, Dict, List, Optional

import httpx

from .base import ProviderError, ProviderKind

logger = logging.getLogger(__name__)


_DEFAULT_TIMEOUT = 8.0


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, default)).strip())
    except (TypeError, ValueError):
        return default


def _parse_retry_after(headers: Any) -> Optional[float]:
    """Honor a numeric Retry-After header (seconds). Ignore HTTP-date form."""
    try:
        raw = headers.get("Retry-After") or headers.get("retry-after")
    except Exception:  # noqa: BLE001
        return None
    if raw is None:
        return None
    try:
        val = float(str(raw).strip())
        return val if val >= 0 else None
    except (TypeError, ValueError):
        return None


class EthJsonRpcProvider:
    """Generic Ethereum-style JSON-RPC provider. One per chain URL."""

    kind = ProviderKind.RPC

    def __init__(self, *, chain: str, url: str,
                 provider_id: Optional[str] = None,
                 timeout: float = _DEFAULT_TIMEOUT) -> None:
        self.chain = chain
        self.url = url
        self.provider_id = provider_id or f"rpc_{chain}_{_short(url)}"
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._req_id = 0
        # Bounded-backoff reliability policy (fail-closed on exhaustion).
        self._max_retries = max(0, _env_int("ARBICORE_RPC_MAX_RETRIES", 3))
        self._backoff_base_ms = max(0, _env_int("ARBICORE_RPC_BACKOFF_BASE_MS", 200))
        self._backoff_cap_ms = max(0, _env_int("ARBICORE_RPC_BACKOFF_CAP_MS", 4000))

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers={"Content-Type": "application/json",
                          "User-Agent": "arbicore-x/2.5.0 (+rpc)"})
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _sleep_backoff(self, attempt: int, retry_after_s: Optional[float]) -> None:
        cap = self._backoff_cap_ms / 1000.0
        if retry_after_s is not None:
            delay = min(retry_after_s, cap)
        else:
            base = self._backoff_base_ms / 1000.0
            delay = min(base * (2 ** attempt), cap)
            delay += random.uniform(0, base / 2.0)  # jitter avoids thundering herd
        await asyncio.sleep(delay)

    async def _call(self, method: str, params: List[Any]) -> Any:
        """Read-only JSON-RPC call with bounded exponential backoff.

        Retryable (up to ARBICORE_RPC_MAX_RETRIES): HTTP 429 (honors Retry-After),
        HTTP 5xx, network/timeout errors, malformed JSON. Non-retryable: other 4xx
        and JSON-RPC error objects. On exhaustion a ProviderError is raised so
        callers FAIL CLOSED — a rate-limited/unavailable RPC is NEVER treated as
        valid market data. Never logs URLs/secrets (only host-derived provider_id)."""
        client = await self._http()
        last_exc: Optional[ProviderError] = None
        for attempt in range(self._max_retries + 1):
            self._req_id += 1
            payload = {"jsonrpc": "2.0", "id": self._req_id,
                       "method": method, "params": params}
            try:
                r = await client.post(self.url, json=payload)
            except httpx.HTTPError as e:
                last_exc = ProviderError(f"{self.provider_id} {method} network: {e}",
                                         retryable=True, provider_id=self.provider_id)
                if attempt < self._max_retries:
                    await self._sleep_backoff(attempt, None)
                    continue
                raise last_exc from e

            status = r.status_code
            if status == 429 or status >= 500:
                last_exc = ProviderError(
                    f"{self.provider_id} {method} -> {status}",
                    retryable=True, provider_id=self.provider_id)
                if attempt < self._max_retries:
                    await self._sleep_backoff(attempt, _parse_retry_after(r.headers))
                    continue
                raise last_exc

            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise ProviderError(
                    f"{self.provider_id} {method} -> {status}",
                    retryable=False, provider_id=self.provider_id) from e

            try:
                data = r.json()
            except ValueError as e:
                last_exc = ProviderError(
                    f"{self.provider_id} {method} malformed_json",
                    retryable=True, provider_id=self.provider_id)
                if attempt < self._max_retries:
                    await self._sleep_backoff(attempt, None)
                    continue
                raise last_exc from e

            if not isinstance(data, dict):
                raise ProviderError(
                    f"{self.provider_id} {method} malformed_response",
                    retryable=False, provider_id=self.provider_id)
            if "error" in data:
                err = data["error"] or {}
                raise ProviderError(
                    f"{self.provider_id} {method} rpc_error: "
                    f"{err.get('code')} {err.get('message')}",
                    retryable=False, provider_id=self.provider_id)
            if "result" not in data:
                raise ProviderError(
                    f"{self.provider_id} {method} missing_result",
                    retryable=False, provider_id=self.provider_id)
            return data.get("result")

        # Unreachable in practice; fail closed.
        raise last_exc or ProviderError(
            f"{self.provider_id} {method} exhausted",
            retryable=True, provider_id=self.provider_id)

    # ---- eth_* surface -------------------------------------------------

    async def eth_call(self, tx: Dict[str, Any],
                       block: str = "latest") -> str:
        return await self._call("eth_call", [tx, block])

    async def eth_get_block_number(self) -> int:
        v = await self._call("eth_blockNumber", [])
        return int(v, 16)

    async def eth_get_gas_price(self) -> int:
        v = await self._call("eth_gasPrice", [])
        return int(v, 16)

    async def eth_max_priority_fee_per_gas(self) -> Optional[int]:
        try:
            v = await self._call("eth_maxPriorityFeePerGas", [])
            return int(v, 16)
        except ProviderError:
            return None

    async def eth_get_fee_history(self, blocks: int = 5,
                                   newest: str = "latest",
                                   percentiles: Optional[List[int]] = None
                                   ) -> Dict[str, Any]:
        return await self._call(
            "eth_feeHistory",
            [hex(blocks), newest, percentiles or [20, 50, 80]])

    async def eth_chain_id(self) -> int:
        v = await self._call("eth_chainId", [])
        return int(v, 16)

    async def verify_chain_id(self, expected: int) -> bool:
        """Fail-closed chain identity check: False on any RPC error/mismatch."""
        try:
            actual = await self.eth_chain_id()
        except ProviderError:
            return False
        try:
            return int(actual) == int(expected)
        except (TypeError, ValueError):
            return False

    async def health_probe(self) -> Dict[str, Any]:
        t0 = time.time()
        try:
            block = await self.eth_get_block_number()
            latency = (time.time() - t0) * 1000
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": True, "block": block,
                     "latency_ms": round(latency, 2)}
        except Exception as e:                                       # noqa
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": False, "error": str(e)[:200]}


class SolanaRpcProvider:
    """Solana JSON-RPC read-only provider."""

    kind = ProviderKind.RPC
    chain = "solana"

    def __init__(self, *, url: str,
                 provider_id: Optional[str] = None,
                 timeout: float = _DEFAULT_TIMEOUT) -> None:
        self.url = url
        self.provider_id = provider_id or f"rpc_solana_{_short(url)}"
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._req_id = 0

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers={"Content-Type": "application/json",
                          "User-Agent": "arbicore-x/2.5.0 (+solana)"})
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _call(self, method: str, params: List[Any]) -> Any:
        self._req_id += 1
        client = await self._http()
        payload = {"jsonrpc": "2.0", "id": self._req_id,
                   "method": method, "params": params}
        try:
            r = await client.post(self.url, json=payload)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.provider_id} {method}: {e}",
                                retryable=True,
                                provider_id=self.provider_id) from e
        if "error" in data:
            raise ProviderError(
                f"{self.provider_id} {method}: {data['error']}",
                retryable=False, provider_id=self.provider_id)
        return data.get("result")

    async def get_slot(self) -> int:
        return int(await self._call("getSlot", []))

    async def get_health(self) -> str:
        return await self._call("getHealth", [])

    async def get_account_info(self, pubkey: str,
                                 encoding: str = "base64"
                                 ) -> Optional[Dict[str, Any]]:
        r = await self._call("getAccountInfo",
                              [pubkey, {"encoding": encoding,
                                         "commitment": "confirmed"}])
        return (r or {}).get("value")

    # Registry-required stubs — EVM methods do not apply on Solana; they
    # exist so the registry can list this provider under RPCProvider
    # without a KeyError. Callers that need Solana-specific methods use
    # the concrete SolanaRpcProvider directly.
    async def eth_call(self, *_a, **_k) -> str:                     # noqa
        raise ProviderError("eth_call not supported on solana",
                             retryable=False, provider_id=self.provider_id)
    async def eth_get_block_number(self) -> int:
        return await self.get_slot()
    async def eth_get_gas_price(self) -> int:
        return 0

    async def health_probe(self) -> Dict[str, Any]:
        t0 = time.time()
        try:
            slot = await self.get_slot()
            latency = (time.time() - t0) * 1000
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": True, "slot": slot,
                     "latency_ms": round(latency, 2)}
        except Exception as e:                                       # noqa
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": False, "error": str(e)[:200]}


# Sensible free-tier public defaults. Consumers override via env.
DEFAULT_RPC_URLS: Dict[str, str] = {
    "ethereum": "https://ethereum-rpc.publicnode.com",
    "arbitrum": "https://arbitrum-one-rpc.publicnode.com",
    "base":     "https://mainnet.base.org",
    "polygon":  "https://polygon-bor-rpc.publicnode.com",
    "optimism": "https://optimism-rpc.publicnode.com",
    "bnb":      "https://bsc-rpc.publicnode.com",
    "solana":   "https://api.mainnet-beta.solana.com",
}


def _short(url: str) -> str:
    h = url.split("//", 1)[-1].split("/", 1)[0]
    return h.replace(".", "_")[:24]


__all__ = [
    "EthJsonRpcProvider", "SolanaRpcProvider", "DEFAULT_RPC_URLS",
]
