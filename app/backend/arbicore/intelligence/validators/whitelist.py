"""ArbiCore X — Pair / Asset Whitelist (universe allowlist).

Migrated from ArbitrageX PAIR_WHITELIST + is_pair_whitelisted (server.py L132, L154).
Config-driven and bidirectional. Execution-free.

Example:
    >>> wl = PairWhitelist.default()
    >>> wl.is_allowed("USDC/WETH")   # reversed of WETH/USDC
    True
    >>> wl.is_allowed("DOGE/PEPE")
    False
"""
from __future__ import annotations

from typing import Iterable, Set

DEFAULT_PAIRS: Set[str] = {
    # Core pairs (all chains)
    "WETH/USDC", "ETH/USDC", "WETH/USDT", "ETH/USDT",
    "WBTC/WETH", "WBTC/ETH", "WBTC/USDC",
    # Stablecoin pairs
    "USDC/USDT", "USDT/USDC", "USDC/DAI", "DAI/USDC", "DAI/USDT", "USDT/DAI",
    # Chain-specific native token pairs
    "WMATIC/USDC", "MATIC/USDC", "WMATIC/WETH", "MATIC/WETH",
    "WBNB/USDT", "BNB/USDT", "WBNB/BUSD", "BNB/BUSD",
    "ARB/USDC", "ARB/WETH", "CAKE/WBNB", "CAKE/BNB",
}


class PairWhitelist:
    def __init__(self, pairs: Iterable[str], active: bool = True) -> None:
        self.active = active
        self._pairs: Set[str] = {p.upper().replace(" ", "") for p in pairs}

    @classmethod
    def default(cls) -> "PairWhitelist":
        return cls(DEFAULT_PAIRS)

    @property
    def size(self) -> int:
        return len(self._pairs)

    def is_allowed(self, pair: str) -> bool:
        if not self.active:
            return True
        normalized = pair.upper().replace(" ", "")
        if normalized in self._pairs:
            return True
        parts = normalized.split("/")
        if len(parts) == 2 and f"{parts[1]}/{parts[0]}" in self._pairs:
            return True
        return False

    def add(self, pair: str) -> None:
        self._pairs.add(pair.upper().replace(" ", ""))

    def remove(self, pair: str) -> None:
        self._pairs.discard(pair.upper().replace(" ", ""))
