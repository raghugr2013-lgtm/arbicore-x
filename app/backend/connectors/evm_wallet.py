"""EVM watch-only wallet connector — covers BSC, BlockDAG (1404), Polygon, Ethereum
from one implementation + per-network config. RPC failover list, never holds keys.
"""
import time
from typing import Optional

import httpx

from connectors.base import WalletConnector


class EVMWatchConnector(WalletConnector):
    key = "evm_watch"
    capabilities = {"watch_only": True, "networks": "any EVM", "private_keys": "never"}

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=8.0)

    async def close(self):
        await self._client.aclose()

    async def _rpc(self, url: str, method: str, params=None):
        resp = await self._client.post(url, json={"jsonrpc": "2.0", "method": method, "params": params or [], "id": 1})
        data = resp.json()
        if "error" in data:
            raise RuntimeError(data["error"])
        return data["result"]

    async def check_rpc(self, network: dict) -> dict:
        """Try each RPC in the failover list; return first healthy."""
        for url in network.get("rpc_urls", []):
            t0 = time.time()
            try:
                block_hex = await self._rpc(url, "eth_blockNumber")
                return {
                    "healthy": True, "rpc_url": url,
                    "block_number": int(block_hex, 16),
                    "latency_ms": int((time.time() - t0) * 1000),
                }
            except Exception as e:
                last_err = str(e)[:120]
                continue
        return {"healthy": False, "rpc_url": None, "error": last_err if network.get("rpc_urls") else "no RPC configured"}

    async def get_balance(self, network: dict, address: str) -> Optional[float]:
        for url in network.get("rpc_urls", []):
            try:
                bal_hex = await self._rpc(url, "eth_getBalance", [address, "latest"])
                return int(bal_hex, 16) / 10 ** network.get("decimals", 18)
            except Exception:
                continue
        return None
