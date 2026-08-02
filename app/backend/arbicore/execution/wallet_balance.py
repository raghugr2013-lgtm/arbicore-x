"""Wave 7A · Wallet Balance Reader (EVM native, read-only).

Reuse notice (VERIFY → REUSE):

    Mirrors the canonical ``connectors/evm_wallet.py::EVMWatchConnector``
    pattern (53 LOC, RPC failover, never-holds-keys).  Reimplemented
    here so the execution engine has a self-contained balance surface
    that doesn't drag in the whole ``connectors/`` package tree.

Everything is READ-ONLY.  Only ``eth_getBalance``, ``eth_blockNumber``,
``eth_chainId``, and ``eth_gasPrice`` are ever called.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("arbicore.execution.balance")


DEFAULT_RPC_URLS: Dict[str, List[str]] = {
    "ethereum":  ["https://eth.llamarpc.com", "https://rpc.ankr.com/eth"],
    "base":      ["https://mainnet.base.org", "https://base.llamarpc.com"],
    "arbitrum":  ["https://arb1.arbitrum.io/rpc"],
    "optimism":  ["https://mainnet.optimism.io"],
    "polygon":   ["https://polygon-rpc.com"],
}

NATIVE_DECIMALS: Dict[str, int] = {
    "ethereum": 18, "base": 18, "arbitrum": 18, "optimism": 18, "polygon": 18,
}

NATIVE_SYMBOLS: Dict[str, str] = {
    "ethereum": "ETH", "base": "ETH", "arbitrum": "ETH",
    "optimism": "ETH", "polygon": "MATIC",
}

READ_ONLY_METHODS: frozenset = frozenset({
    "eth_getBalance", "eth_blockNumber", "eth_chainId", "eth_gasPrice",
})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class BalanceReading:
    chain: str
    address: str
    symbol: str
    balance_wei: int
    balance_native: float
    balance_usd: Optional[float]
    native_price_usd: Optional[float]
    block_number: Optional[int]
    rpc_endpoint_redacted: Optional[str]
    ok: bool
    error: Optional[str]
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _rpc_urls_for(chain: str) -> List[str]:
    env_key = f"ARBICORE_RPC_URL_{chain.upper()}"
    env = os.environ.get(env_key) or os.environ.get("ARBICORE_RPC_URL")
    urls = [u.strip() for u in (env.split(",") if env else []) if u.strip()]
    urls.extend(DEFAULT_RPC_URLS.get(chain, []))
    # de-dupe, preserve order
    seen: set = set()
    out: List[str] = []
    for u in urls:
        if u not in seen:
            out.append(u)
            seen.add(u)
    return out


def _redact_rpc(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        return f"{p.scheme}://{p.hostname}{':' + str(p.port) if p.port else ''}"
    except Exception:  # noqa: BLE001
        return "***"


class WalletBalanceReader:
    """Read-only EVM balance + gas health reader with RPC failover."""

    def __init__(self, *, timeout_s: float = 6.0,
                 native_price_usd: Optional[float] = None):
        self._timeout = float(timeout_s)
        self._native_price_usd = (
            native_price_usd
            or float(os.environ.get("ARBICORE_NATIVE_PRICE_USD") or 2500.0)
        )

    async def _rpc(self, url: str, method: str,
                   params: Optional[List[Any]] = None) -> Any:
        assert method in READ_ONLY_METHODS, (
            f"WalletBalanceReader refused non-read-only method '{method}'"
        )
        import httpx
        payload = {"jsonrpc": "2.0", "id": 1, "method": method,
                   "params": list(params or [])}
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            r = await c.post(url, json=payload)
            r.raise_for_status()
            body = r.json()
            if "error" in body:
                raise RuntimeError(str(body["error"]))
            return body.get("result")

    async def read(self, *, chain: str, address: str) -> BalanceReading:
        symbol = NATIVE_SYMBOLS.get(chain, "?")
        decimals = NATIVE_DECIMALS.get(chain, 18)
        last_err: Optional[str] = None
        used_url: Optional[str] = None
        block_num: Optional[int] = None
        balance_wei: int = 0

        for url in _rpc_urls_for(chain):
            try:
                bal_hex = await self._rpc(url, "eth_getBalance", [address, "latest"])
                balance_wei = int(bal_hex, 16) if isinstance(bal_hex, str) else int(bal_hex or 0)
                try:
                    blk_hex = await self._rpc(url, "eth_blockNumber")
                    block_num = int(blk_hex, 16) if isinstance(blk_hex, str) else int(blk_hex or 0)
                except Exception:  # noqa: BLE001
                    block_num = None
                used_url = url
                break
            except Exception as exc:  # noqa: BLE001
                last_err = f"{type(exc).__name__}: {str(exc)[:120]}"
                continue

        if used_url is None:
            return BalanceReading(
                chain=chain, address=address, symbol=symbol,
                balance_wei=0, balance_native=0.0,
                balance_usd=None, native_price_usd=self._native_price_usd,
                block_number=None, rpc_endpoint_redacted=None,
                ok=False, error=last_err or "no RPC configured",
                generated_at=_now_iso(),
            )

        balance_native = balance_wei / (10 ** decimals)
        balance_usd = (round(balance_native * self._native_price_usd, 4)
                       if self._native_price_usd else None)
        return BalanceReading(
            chain=chain, address=address, symbol=symbol,
            balance_wei=balance_wei, balance_native=round(balance_native, 8),
            balance_usd=balance_usd, native_price_usd=self._native_price_usd,
            block_number=block_num, rpc_endpoint_redacted=_redact_rpc(used_url),
            ok=True, error=None, generated_at=_now_iso(),
        )
