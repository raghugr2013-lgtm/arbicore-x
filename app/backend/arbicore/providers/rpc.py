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

import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from .base import ProviderError, ProviderKind

logger = logging.getLogger(__name__)


_DEFAULT_TIMEOUT = 8.0


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

    async def _call(self, method: str, params: List[Any]) -> Any:
        self._req_id += 1
        client = await self._http()
        payload = {"jsonrpc": "2.0", "id": self._req_id,
                   "method": method, "params": params}
        try:
            r = await client.post(self.url, json=payload)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as e:
            raise ProviderError(
                f"{self.provider_id} {method} -> {e.response.status_code}",
                retryable=(e.response.status_code >= 500),
                provider_id=self.provider_id) from e
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.provider_id} {method} network: {e}",
                                retryable=True,
                                provider_id=self.provider_id) from e
        if "error" in data:
            err = data["error"]
            raise ProviderError(
                f"{self.provider_id} {method} rpc_error: "
                f"{err.get('code')} {err.get('message')}",
                retryable=False, provider_id=self.provider_id)
        return data.get("result")

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
