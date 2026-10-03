"""Write measured pool TVL onto route-search nodes before the floor.

``RouteSearchEngine.search`` stays synchronous and keeps the comparison
``tvl_usd >= min_pool_tvl_usd`` (default ``$100,000``). Graph builders
store ``tvl_usd=0.0`` as "not yet measured". This module fills that field
from ``OnChainReserveTVLProvider`` (via the existing per-chain builders)
before search runs.

Unknown, missing, or non-positive readings stay ``0.0``, so the existing
floor excludes the pool. Nothing here lowers or bypasses that floor, and
a chain never reads another chain's provider.
"""
from __future__ import annotations

import inspect
import logging
import math
from dataclasses import replace
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Tuple

from .route_search import PoolNode

_LOG = logging.getLogger("arbicore.pool_tvl_propagation")

# (contract address, reserves meta tuple)
ResolvedPool = Tuple[str, tuple]
ResolveFn = Callable[[str, PoolNode, Any], Awaitable[Optional[ResolvedPool]]]


def measured_tvl_usd(value: Any) -> float:
    """Positive finite USD, otherwise ``0.0``. Never a sentinel."""
    if value is None:
        return 0.0
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(v) or v <= 0.0:
        return 0.0
    return v


def apply_measured_tvl(
    pools: List[PoolNode],
    measured: Mapping[str, Optional[float]],
) -> List[PoolNode]:
    """Copy ``pools``, writing a measured USD value onto each known id.

    A missing id keeps the stored ``tvl_usd`` (graph builders store ``0.0``).
    An explicit ``None`` or non-positive reading is written as ``0.0``.
    """
    out: List[PoolNode] = []
    for pool in pools:
        if pool.pool_address not in measured:
            out.append(pool)
            continue
        tvl = measured_tvl_usd(measured[pool.pool_address])
        if tvl == pool.tvl_usd:
            out.append(pool)
        else:
            out.append(replace(pool, tvl_usd=tvl))
    return out


class PoolTVLOverlay:
    """Last measurement per chain, keyed by the graph pool id.

    Applying an empty chain leaves pools untouched. A measurement recorded
    for chain A is never applied to chain B.
    """

    def __init__(self) -> None:
        self._by_chain: Dict[str, Dict[str, Optional[float]]] = {}

    def replace(self, chain: str, measured: Mapping[str, Optional[float]]) -> None:
        self._by_chain[(chain or "").lower()] = dict(measured)

    def snapshot(self, chain: str) -> Dict[str, Optional[float]]:
        return dict(self._by_chain.get((chain or "").lower()) or {})

    def apply(self, chain: str, pools) -> List[PoolNode]:
        measured = self._by_chain.get((chain or "").lower())
        if not measured:
            return list(pools or [])
        return apply_measured_tvl(list(pools or []), measured)


class ChainDispatchTVLProvider:
    """Route ``get_pool_tvl_usd`` to the provider registered for that chain.

    A read for chain C never calls another chain's provider. Chains with
    no provider return ``None`` (fail closed). ``scoped_chains`` is how
    the quote path tells this dispatcher apart from a single-chain provider.
    """

    provider_id = "tvl_chain_dispatch"

    def __init__(self, by_chain: Optional[Mapping[str, Any]] = None) -> None:
        self._by: Dict[str, Any] = {}
        self.scoped_chains = frozenset()
        for chain, provider in (by_chain or {}).items():
            self.set_provider(chain, provider)

    def set_provider(self, chain: str, provider) -> None:
        c = (chain or "").lower()
        if not c or provider is None:
            return
        self._by[c] = provider
        self.scoped_chains = frozenset(self._by)

    async def get_pool_tvl_usd(self, chain: str,
                               pool_address: str) -> Optional[float]:
        provider = self._by.get((chain or "").lower())
        if provider is None:
            return None
        return await provider.get_pool_tvl_usd(chain, pool_address)


def tvl_provider_usable_for_chain(provider, route_chain: str,
                                  scoped_chain: str) -> bool:
    """Whether ``provider`` may supply depth for ``route_chain``.

    A provider that publishes ``scoped_chains`` is usable only on those
    chains. Any other provider stays single-chain (H07): it is usable only
    when ``route_chain`` equals ``scoped_chain``.
    """
    if provider is None:
        return False
    chains = getattr(provider, "scoped_chains", None)
    c = (route_chain or "").lower()
    if chains is not None:
        return c in {str(x).lower() for x in chains}
    return c == (scoped_chain or "").lower()


async def measure_graph_tvl(
    chain: str,
    pools: List[PoolNode],
    *,
    tvl_provider,
    resolve: ResolveFn,
    eth_call=None,
) -> Dict[str, Optional[float]]:
    """Measure each pool. Unresolved or unpriced pools map to ``None``."""
    measured: Dict[str, Optional[float]] = {}
    for pool in pools:
        info: Optional[ResolvedPool] = None
        try:
            got = resolve(chain, pool, eth_call)
            if inspect.isawaitable(got):
                got = await got
            info = got
        except Exception:  # noqa: BLE001 — one pool must not abort the rest
            info = None
        if not info or tvl_provider is None:
            measured[pool.pool_address] = None
            continue
        addr = info[0]
        if not addr:
            measured[pool.pool_address] = None
            continue
        try:
            value = await tvl_provider.get_pool_tvl_usd(chain, addr)
        except Exception:  # noqa: BLE001 — provider never fabricates
            value = None
        tvl = measured_tvl_usd(value)
        measured[pool.pool_address] = tvl if tvl > 0.0 else None
    return measured


def _fee_ppm(pool: PoolNode) -> Optional[int]:
    tail = str(pool.pool_address).rsplit(":", 1)[-1]
    if tail.isdigit():
        ppm = int(tail)
        return ppm if ppm > 0 else None
    return None


def _pair_meta(chain: str, pool: PoolNode, token0: str, token1: str):
    from ...discovery.multichain_pool_registry import token_spec
    spec_a = token_spec(chain, pool.token_a)
    spec_b = token_spec(chain, pool.token_b)
    if not spec_a or not spec_b:
        return None
    try:
        dec_a = int(spec_a["decimals"])
        dec_b = int(spec_b["decimals"])
    except (KeyError, TypeError, ValueError):
        return None
    addr_a = str(spec_a.get("address") or "")
    addr_b = str(spec_b.get("address") or "")
    if not addr_a or not addr_b:
        return None
    wanted = {addr_a.lower(), addr_b.lower()}
    if {str(token0).lower(), str(token1).lower()} != wanted:
        return None
    if str(token0).lower() == addr_a.lower():
        return (pool.token_a, addr_a, dec_a, pool.token_b, addr_b, dec_b)
    return (pool.token_b, addr_b, dec_b, pool.token_a, addr_a, dec_a)


async def resolve_graph_pool_for_tvl(
    chain: str, pool: PoolNode, eth_call,
) -> Optional[ResolvedPool]:
    """Real contract address plus reserves metadata, or ``None``.

    Base uses the canonical registry address (never a synthetic id). Other
    chains use the existing UniV3 / UniV2 / Algebra resolvers. A synthetic
    venue id is not a TVL key.
    """
    c = (chain or "").lower()
    if c == "base":
        from ...discovery.base_pool_registry import canonical_pool_by_id
        cp = canonical_pool_by_id(pool.pool_address)
        if cp is None or not getattr(cp, "address", None):
            return None
        if (cp.token0_decimals is None or cp.token1_decimals is None
                or not cp.token0_address or not cp.token1_address):
            return None
        meta = (
            cp.token0_symbol, cp.token0_address, int(cp.token0_decimals),
            cp.token1_symbol, cp.token1_address, int(cp.token1_decimals),
        )
        return cp.address, meta

    if eth_call is None:
        return None
    from ...chains.registries import dex_abi
    from ...discovery.multichain_pool_registry import token_address
    abi = dex_abi(c, pool.dex_protocol)
    addr_a = token_address(c, pool.token_a)
    addr_b = token_address(c, pool.token_b)
    if not abi or not addr_a or not addr_b:
        return None

    resolved = None
    if abi == "univ3":
        fee = _fee_ppm(pool)
        if fee is None:
            return None
        from ...discovery.univ3_pool_resolver import resolve_univ3_pool
        resolved = await resolve_univ3_pool(
            c, addr_a, addr_b, fee, eth_call=eth_call, dex=pool.dex_protocol)
    elif abi == "univ2":
        from ...discovery.univ3_pool_resolver import resolve_univ2_pool
        resolved = await resolve_univ2_pool(
            c, addr_a, addr_b, eth_call=eth_call, dex=pool.dex_protocol)
    elif abi == "algebra":
        from ...discovery.algebra_pool_resolver import resolve_algebra_pool
        resolved = await resolve_algebra_pool(
            c, addr_a, addr_b, eth_call=eth_call, dex=pool.dex_protocol)
    else:
        return None
    if not resolved or not resolved.get("pool_address"):
        return None
    meta = _pair_meta(c, pool, resolved.get("token0"), resolved.get("token1"))
    if meta is None:
        return None
    return resolved["pool_address"], meta


def _univ3_price_pools(resolved_rows):
    """UniV3 pools with a real address, for the existing USD price feed."""
    from .exact_size_sizer import PricePool
    out = []
    for pool, addr, meta in resolved_rows:
        if str(pool.dex_protocol).lower() != "uniswap_v3":
            continue
        if pool.fee_bps is None or int(pool.fee_bps) <= 0 or not addr:
            continue
        t0s, t0a, d0, t1s, t1a, d1 = meta
        out.append(PricePool(
            t0s, t0a, int(d0), t1s, t1a, int(d1),
            "uniswap_v3", int(pool.fee_bps), addr))
    return out


def _chain_token_price_source(chain: str, quoter_registry, price_pools):
    """Fail-closed per-token USD source. No feed, no pools → ``None``."""
    if quoter_registry is None or not price_pools:
        return None
    from .exact_size_sizer import MultichainUsdPriceFeed

    async def quote_route_fn(hops):
        rq = await quoter_registry.quote_route(chain=chain, hops=hops)
        if getattr(rq, "status", None) != "ok":
            return None
        blocks = [h.block_number for h in getattr(rq, "hops", [])
                  if getattr(h, "block_number", None) is not None]
        quoter = None
        if getattr(rq, "hops", None):
            quoter = getattr(rq.hops[0], "quoter_contract", None)
        return {
            "final_out_wei": rq.final_amount_out_wei,
            "block": (min(blocks) if blocks else None),
            "quoter": quoter,
        }

    feed = MultichainUsdPriceFeed(quote_route_fn=quote_route_fn, pools=price_pools)
    return feed.price_source


def attach_measured_tvl_path(
    scanner,
    *,
    eth_call_for_chain,
    base_tvl_provider,
    quoter_registry,
) -> Optional[ChainDispatchTVLProvider]:
    """Point the scanner's loader overlay and quote provider at one measurer.

    The returned dispatcher is chain-scoped. Refresh runs only when the
    scanner tick calls it, which is after ``is_enabled()``. A missing
    overlay (tests that build a scanner directly) returns ``None`` and
    changes nothing.
    """
    overlay = getattr(scanner, "_pool_tvl_overlay", None)
    raw_loader = getattr(scanner, "_raw_pool_loader", None)
    if overlay is None or raw_loader is None:
        return None

    dispatch = ChainDispatchTVLProvider({})
    if base_tvl_provider is not None:
        dispatch.set_provider("base", base_tvl_provider)

    async def refresh() -> None:
        cfg = scanner.config_loader() or {}
        chains = []
        for name, spec in (cfg.get("chains") or {}).items():
            if isinstance(spec, dict) and spec.get("enabled"):
                chains.append(str(name).lower())
        for chain in chains:
            try:
                await _refresh_chain(chain)
            except Exception as exc:  # noqa: BLE001 — one chain fails closed
                _LOG.warning("pool TVL refresh failed chain=%s err=%s",
                             chain, type(exc).__name__)

    async def _refresh_chain(chain: str) -> None:
        pools = list(raw_loader(chain) or [])
        eth_call = None
        if chain != "base" and eth_call_for_chain is not None:
            eth_call = eth_call_for_chain(chain)
        resolved = []
        meta: Dict[str, tuple] = {}
        unresolved: Dict[str, Optional[float]] = {}
        for pool in pools:
            info = await resolve_graph_pool_for_tvl(chain, pool, eth_call)
            if not info:
                unresolved[pool.pool_address] = None
                continue
            addr, pool_meta = info
            meta[str(addr).lower()] = pool_meta
            resolved.append((pool, addr, pool_meta))

        provider = base_tvl_provider if chain == "base" else None
        if chain != "base" and eth_call is not None and meta:
            price_pools = _univ3_price_pools(resolved)
            price_source = _chain_token_price_source(
                chain, quoter_registry, price_pools)
            if price_source is not None:
                from ...searcher.runtime import build_evm_tvl_provider
                provider = build_evm_tvl_provider(
                    chain, eth_call, price_source, meta)
        if provider is not None:
            dispatch.set_provider(chain, provider)

        measured = await measure_graph_tvl(
            chain, [row[0] for row in resolved],
            tvl_provider=provider,
            resolve=lambda _c, pool, _eth, _rows=resolved: _addr_of(pool, _rows),
            eth_call=eth_call,
        )
        measured.update(unresolved)
        overlay.replace(chain, measured)

    scanner.set_pool_tvl_refresh(refresh)
    return dispatch


def _addr_of(pool: PoolNode, rows) -> Optional[ResolvedPool]:
    for candidate, addr, meta in rows:
        if candidate.pool_address == pool.pool_address:
            return addr, meta
    return None


__all__ = [
    "PoolTVLOverlay", "ChainDispatchTVLProvider",
    "apply_measured_tvl", "measured_tvl_usd", "measure_graph_tvl",
    "resolve_graph_pool_for_tvl", "attach_measured_tvl_path",
    "tvl_provider_usable_for_chain",
]
