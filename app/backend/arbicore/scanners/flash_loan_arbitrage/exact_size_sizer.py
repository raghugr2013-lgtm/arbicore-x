"""H05 · Chain-aware EXACT-SIZE borrow sizer (+ multichain on-chain USD price feed).

Turns a requested USD notional into an EXACT integer borrow amount (token base
units) for a given (chain, borrow_token), using GENUINE on-chain price evidence
and the VERIFIED token decimals from the canonical registry — or fails closed.

Design (roadmap-clean, no per-chain duplication):
  * ``ExactSizeBorrowSizer`` is pure sizing logic over an injected async price
    source + a decimals resolver. It performs NO I/O itself and never fabricates
    a price. It is the implementation behind the existing H05 callback contract
    ``borrow_sizer(chain, borrow_token, borrow_amount_usd) -> Optional[int]``.
  * ``MultichainUsdPriceFeed`` REUSES the Base M2.5 ``OnChainUsdPriceFeed``
    pricing/peg/freshness/provenance logic unchanged, overriding only the
    Base-specific pool index so it accepts generic REAL-address pools (resolved
    on-chain by SP-5). It is NOT a second price-feed architecture and adds no
    hardcoded/CEX/native-proxy prices.
  * ``MultichainPriceSource`` fans per-chain feeds behind a ``(chain, token)``
    async accessor.

FAIL-CLOSED everywhere: unknown chain/token/decimals, missing/zero/negative/
non-finite price, stale/wrong-chain/invalid quote, or an unsafe/zero wei
conversion → ``None``. H05 is DISABLED unless the operator explicitly enables it
(``ARBICORE_BORROW_SIZER_ENABLED`` + ``ARBICORE_PRICE_FEED_ENABLED``); the
builders return ``None`` otherwise. No execution/signing/broadcast/thresholds.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ...searcher.price_feed import OnChainUsdPriceFeed

_MAX_UINT256 = (1 << 256) - 1

DecimalsFn = Callable[[str, str], Optional[int]]                 # (chain, token) -> decimals
PriceUsdFn = Callable[[str, str], Awaitable[Optional[float]]]    # async (chain, token) -> usd


def _finite_positive(x: Any) -> bool:
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return False
    return math.isfinite(xf) and xf > 0.0


class ExactSizeBorrowSizer:
    """requested USD → exact integer borrow amount (base units), fail-closed.

    ROUNDING POLICY — floor (round DOWN):
        wei = floor(requested_usd / price_usd * 10**decimals)
    so the REALIZED notional (wei / 10**decimals * price_usd) is always ≤ the
    requested USD and can never exceed the verified economic basis. A request
    that floors to 0 base units is rejected (None), never rounded up.
    """

    def __init__(self, price_usd_fn: PriceUsdFn, decimals_fn: DecimalsFn) -> None:
        self._price = price_usd_fn
        self._decimals = decimals_fn

    async def size(self, chain: str, borrow_token: str,
                   borrow_amount_usd: float) -> Optional[int]:
        c = (chain or "").strip().lower()
        tok = (borrow_token or "").strip().upper()
        if not c or not tok:
            return None
        if not _finite_positive(borrow_amount_usd):
            return None
        dec = self._decimals(c, tok)
        if dec is None:
            return None
        try:
            dec_i = int(dec)
        except (TypeError, ValueError):
            return None
        if dec_i < 0 or dec_i > 36:
            return None
        try:
            price = await self._price(c, tok)
        except Exception:  # noqa: BLE001 — never fabricate on error
            return None
        if not _finite_positive(price):
            return None
        amount_token = float(borrow_amount_usd) / float(price)
        if not (math.isfinite(amount_token) and amount_token > 0.0):
            return None
        wei = int(math.floor(amount_token * (10 ** dec_i)))
        if wei <= 0 or wei > _MAX_UINT256:
            return None
        return wei

    def as_callback(self) -> Callable[[str, str, float], Awaitable[Optional[int]]]:
        async def borrow_sizer(chain: str, borrow_token: str,
                               borrow_amount_usd: float) -> Optional[int]:
            return await self.size(chain, borrow_token, borrow_amount_usd)
        return borrow_sizer


@dataclass
class PricePool:
    """Minimal REAL-address pool spec consumed by ``MultichainUsdPriceFeed``.
    Every address is a genuine on-chain pool resolved by SP-5 — never fabricated.
    """
    token0_symbol: str
    token0_address: str
    token0_decimals: int
    token1_symbol: str
    token1_address: str
    token1_decimals: int
    dex: str
    fee_bps: int
    address: str


class MultichainUsdPriceFeed(OnChainUsdPriceFeed):
    """M2.5 price feed for a non-Base chain: reuses ALL of ``OnChainUsdPriceFeed``
    (route-to-USDC, stable peg guard, freshness, provenance, fail-closed) and only
    overrides the Base-specific pool index so it accepts generic real-address
    ``PricePool`` objects (no ``base_pool_registry`` import, no fabricated pools)."""

    @staticmethod
    def _pair_index(pools) -> Dict[frozenset, Dict[str, Any]]:
        out: Dict[frozenset, Dict[str, Any]] = {}
        for p in pools:
            if getattr(p, "dex", None) != "uniswap_v3":
                continue
            addr = getattr(p, "address", None)
            fee_bps = getattr(p, "fee_bps", None)
            if not addr or fee_bps is None:
                continue
            key = frozenset({p.token0_symbol.upper(), p.token1_symbol.upper()})
            spec = {"address": addr, "fee_bps": int(fee_bps), "dex": p.dex}
            cur = out.get(key)
            if cur is None or spec["fee_bps"] < cur["fee_bps"]:
                out[key] = spec
        return out


class MultichainPriceSource:
    """Fan per-chain :class:`OnChainUsdPriceFeed` instances behind a
    ``(chain, token)`` async accessor. Unknown chain → None (fail closed)."""

    def __init__(self, feeds: Dict[str, OnChainUsdPriceFeed]) -> None:
        self._feeds = {(k or "").strip().lower(): v for k, v in (feeds or {}).items()}

    def configured_chains(self) -> List[str]:
        return sorted(self._feeds.keys())

    async def price_usd(self, chain: str, token: str) -> Optional[float]:
        feed = self._feeds.get((chain or "").strip().lower())
        if feed is None:
            return None
        try:
            return await feed.price_source(token)
        except Exception:  # noqa: BLE001
            return None


# ── env gating (H05 DISABLED by default; builders fail closed to None) ────────
def _flag(key: str) -> bool:
    return (os.environ.get(key) or "").strip().lower() in ("1", "true", "yes", "on")


def price_feed_enabled() -> bool:
    return _flag("ARBICORE_PRICE_FEED_ENABLED")


def borrow_sizer_enabled() -> bool:
    return _flag("ARBICORE_BORROW_SIZER_ENABLED")


def registry_decimals(chain: str, token: str) -> Optional[int]:
    """Verified token decimals from the SP-2 read-only registry (all six chains),
    or None (unknown/unconfigured → fail closed). No arbitrary default."""
    from ...discovery import multichain_pool_registry as mreg
    spec = mreg.token_spec((chain or "").strip().lower(), token)
    if not spec:
        return None
    d = spec.get("decimals")
    try:
        return int(d) if d is not None else None
    except (TypeError, ValueError):
        return None


def build_borrow_sizer_from_env(*, price_usd_fn: Optional[PriceUsdFn] = None,
                                decimals_fn: Optional[DecimalsFn] = None):
    """Return the async ``borrow_sizer`` callback ONLY when the operator has
    explicitly enabled H05 AND a genuine price source is supplied; otherwise
    ``None`` (fail closed — never a fabricated sizer). ``decimals_fn`` defaults
    to the verified registry resolver."""
    if not (borrow_sizer_enabled() and price_feed_enabled()):
        return None
    if price_usd_fn is None:
        return None  # no genuine price source ⇒ no sizer (never fabricate)
    sizer = ExactSizeBorrowSizer(price_usd_fn, decimals_fn or registry_decimals)
    return sizer.as_callback()


__all__ = [
    "ExactSizeBorrowSizer", "MultichainUsdPriceFeed", "MultichainPriceSource",
    "PricePool", "registry_decimals", "price_feed_enabled", "borrow_sizer_enabled",
    "build_borrow_sizer_from_env",
]
