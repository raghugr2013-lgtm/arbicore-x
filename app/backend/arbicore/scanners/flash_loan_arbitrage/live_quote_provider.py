"""Live flash-loan route quote provider (canonical, honest, chain/venue-aware).

Bridges the real ``FlashLoanArbitrageScanner`` verifier to the SAME live
``QuoterRegistry`` the OpportunityEngine uses. Given a discovered route cycle it
quotes every hop live and returns the ``facts`` dict the
``FlashLoanOpportunityVerifier`` consumes (``hop_legs`` + ``gross_profit_pct`` +
gas + tvl).

Chain/venue-aware (no longer Base-hardwired):
  * The chain is resolved from the route/candidate context (``chain`` in the
    cycle metadata), defaulting to ``base`` for full backward compatibility.
  * BASE path is behaviour-identical to the certified P0-3 implementation: it
    uses the canonical Base registry (base_venues + base_pool_registry).
  * OTHER registered EVM chains (ethereum/arbitrum/optimism/polygon/bnb) resolve
    token addresses from the chain registry and validate each UniV3 pool
    on-chain via ``univ3_pool_resolver`` before quoting through the correct
    chain in ``QuoterRegistry``. A venue family with no generic pool resolver,
    or a missing/failed RPC, fails CLOSED (returns ``None`` →
    ``denied:venue_unreadable``) — never a fabricated quote/pool/liquidity.

Honesty guarantees (unchanged):
  * No fabricated profit — gross is computed from real on-chain quotes.
  * No signing / no broadcast — quoting is read-only ``eth_call``.
  * Any unreadable hop / partial route / non-closed cycle → ``None``.
"""
from __future__ import annotations

import inspect
import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from .pool_tvl_propagation import tvl_provider_usable_for_chain

_LOG = logging.getLogger("arbicore.live_quote_provider")


def _dex_source_id(dex: str, chain: str) -> str:
    m = {
        "uniswap_v3": f"uniswap_v3_quoter_{chain}",
        "aerodrome_slipstream": f"aerodrome_quoter_{chain}",
        "aerodrome": f"aerodrome_quoter_{chain}",
    }
    return m.get(dex, f"{dex}_quoter_{chain}")


async def _resolve_pool_tvls(route_pools: List[str], tvl_provider,
                             chain: str = "base") -> Dict[str, float]:
    """REAL on-chain pool depth per Base route pool (canonical-registry path,
    behaviour-compatible with P0-3). Missing provider/address/error/non-positive
    read → ABSENT (Gate 8 fails closed). Non-Base plans resolve depth inline."""
    out: Dict[str, float] = {}
    if tvl_provider is None:
        return out
    from ...discovery.base_pool_registry import canonical_pool_by_id
    for pid in route_pools:
        cp = canonical_pool_by_id(pid)
        addr = getattr(cp, "address", None) if cp else None
        if not addr:
            continue
        try:
            v = await tvl_provider.get_pool_tvl_usd(chain, addr)
        except Exception:  # noqa: BLE001 — provider never fabricates
            v = None
        if v is not None and float(v) > 0.0:
            out[pid] = float(v)
    return out


def _route_min_tvl(pool_tvls: Dict[str, float], route_pools: List[str]) -> float:
    """Min measured TVL over the route. FAIL CLOSED (0.0) unless EVERY pool on
    the route has a positive, verified on-chain TVL — never a partial pass."""
    if not route_pools:
        return 0.0
    vals: List[float] = []
    for pid in route_pools:
        v = pool_tvls.get(pid)
        if v is None or v <= 0.0:
            return 0.0
        vals.append(v)
    return min(vals)


# ── per-hop plan: (dex, token_in_addr, token_out_addr, fee, tick_spacing,
#    stable, tvl_key, tvl_addr, fee_bps, pool_id, pool_address) ───────────────
class _HopPlan:
    __slots__ = ("dex", "token_in", "token_out", "fee", "tick_spacing",
                 "stable", "tvl_key", "tvl_addr", "fee_bps",
                 "pool_id", "pool_address")

    def __init__(self, dex, token_in, token_out, fee, tick_spacing, stable,
                 tvl_key, tvl_addr, fee_bps, pool_id=None, pool_address=None):
        self.dex, self.token_in, self.token_out = dex, token_in, token_out
        self.fee, self.tick_spacing, self.stable = fee, tick_spacing, stable
        self.tvl_key, self.tvl_addr, self.fee_bps = tvl_key, tvl_addr, fee_bps
        self.pool_id, self.pool_address = pool_id, pool_address


def _plan_base(hm: Dict[str, Any]) -> Optional[Tuple[List[_HopPlan], List[str], int]]:
    """Behaviour-identical Base plan from the canonical registry."""
    from ...discovery.base_venues import token_address, probe_amount
    from ...discovery.base_pool_registry import (
        canonical_pool_specs, canonical_pool_by_id)
    specs = canonical_pool_specs()
    route_pools: List[str] = list(hm.get("route_pools") or [])
    token_path: List[str] = [str(t).upper() for t in (hm.get("cycle_token_path") or [])]
    borrow_token = (hm.get("borrow_token") or (token_path[0] if token_path else "")).upper()
    if len(route_pools) < 2 or len(token_path) != len(route_pools) + 1:
        return None
    plans: List[_HopPlan] = []
    for i, pool_addr in enumerate(route_pools):
        spec = dict(specs.get(pool_addr) or {})
        addr_in, addr_out = token_address(token_path[i]), token_address(token_path[i + 1])
        if not addr_in or not addr_out:
            return None
        cp = canonical_pool_by_id(pool_addr)
        plans.append(_HopPlan(
            dex=spec.get("dex") or "uniswap_v3",
            token_in=addr_in, token_out=addr_out,
            fee=spec.get("fee"), tick_spacing=spec.get("tick_spacing"),
            stable=spec.get("stable"),
            tvl_key=pool_addr,
            tvl_addr=(getattr(cp, "address", None) if cp else None),
            fee_bps=int(spec.get("fee", 3000)) // 100,
            pool_id=spec.get("pool_id"),
            pool_address=spec.get("pool_address") or (
                getattr(cp, "address", None) if cp else None)))
    return plans, token_path, int(probe_amount(borrow_token))


def _explicit_balancer_identity(rh: Dict[str, Any]) -> Optional[Tuple[Optional[str], Optional[str]]]:
    """Return (pool_id, pool_address) only when an explicit on-chain identity is
    present. Synthetic venue ids (``balancer_v2:TOKEN:...``) are rejected —
    BalancerV2Quoter requires a real pool_id or pool_address (fail-closed)."""
    pool_id = rh.get("pool_id") or rh.get("poolId")
    pool_address = rh.get("pool_address")
    raw_pool = rh.get("pool")
    # ``pool`` may be a real 0x address OR a synthetic venue id — only accept
    # checksummable 20-byte addresses as pool_address.
    if pool_address is None and isinstance(raw_pool, str):
        p = raw_pool.strip()
        if p.startswith("0x") and len(p) == 42:
            pool_address = p
        elif p.startswith("0x") and len(p) == 66 and pool_id is None:
            pool_id = p
    if isinstance(pool_id, str):
        pid = pool_id.strip()
        if not (pid.startswith("0x") and len(pid) == 66):
            pool_id = None
        else:
            pool_id = pid
    else:
        pool_id = None
    if isinstance(pool_address, str):
        pa = pool_address.strip()
        if not (pa.startswith("0x") and len(pa) == 42):
            pool_address = None
        else:
            pool_address = pa
    else:
        pool_address = None
    if not pool_id and not pool_address:
        return None
    return pool_id, pool_address


_QUOTER_BACKENDS: Optional[Dict[str, Any]] = None


def _quoter_backends() -> Dict[str, Any]:
    """Registered quote backends. Local map only — no RPC."""
    global _QUOTER_BACKENDS
    if _QUOTER_BACKENDS is None:
        from ...execution.quoter import QuoterRegistry
        _QUOTER_BACKENDS = QuoterRegistry()._backends
    return _QUOTER_BACKENDS


def quoter_serves(dex: str, chain: str) -> bool:
    """True when an existing backend has a contract for this dex and chain.

    This is the local capability map. It does not resolve pools and it does
    not add a quoter that is not already registered.
    """
    d = (dex or "").lower()
    c = (chain or "").lower()
    if not d or not c:
        return False
    if d == "balancer_v2":
        from ...discovery.balancer_v2_pool_discovery import (
            BALANCER_V2_VAULT_BY_CHAIN)
        return c in BALANCER_V2_VAULT_BY_CHAIN
    backend = _quoter_backends().get(d)
    if backend is None:
        return False
    for attr in ("_CONTRACT_BY_CHAIN", "_ROUTER_BY_CHAIN"):
        mapping = getattr(backend, attr, None)
        if isinstance(mapping, dict) and mapping.get(c):
            return True
    return False


def hop_quote_capable(chain: str, pool) -> bool:
    """True when this pool's DEX can be quoted on ``chain``.

    Selection uses this local map so an unsupported DEX does not occupy a
    candidate slot. The planner still fail-closes a hop whose pool cannot
    be resolved. No RPC.
    """
    return quoter_serves(getattr(pool, "dex_protocol", ""), chain)


def _token_addr(chain: str, sym_or_addr: str) -> Optional[str]:
    s = str(sym_or_addr or "")
    if s.startswith("0x") and len(s) == 42:
        return s
    from ...discovery.multichain_pool_registry import token_address
    return token_address(chain, s)


def _borrow_amount_wei(chain: str, hm: Dict[str, Any],
                       token_path: List[str]) -> int:
    try:
        amount = int(hm.get("borrow_amount_wei") or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount > 0:
        return amount
    # Base route_hops (generic DEX / triangular) do not carry the registry
    # probe. Reuse the same Base probe _plan_base already uses. Unknown
    # symbols stay unquoted — probe_amount's unknown-symbol default is not
    # used.
    if chain in ("base", "base-sepolia"):
        from ...discovery.base_venues import canonical_symbol, probe_amount
        borrow = hm.get("borrow_token") or (token_path[0] if token_path else "")
        if canonical_symbol(str(borrow)):
            return int(probe_amount(str(borrow)) or 0)
    return 0


async def _plan_one_hop(
    chain: str, rh: Dict[str, Any], addr_in: str, addr_out: str, eth_call,
) -> Optional[_HopPlan]:
    """Plan one hop with an existing quoter, or return None (fail closed)."""
    dex_l = str(rh.get("dex") or "").lower()
    if not dex_l or not quoter_serves(dex_l, chain):
        _LOG.debug("quoter_not_on_chain chain=%s dex=%s", chain, dex_l)
        return None

    from ...chains.registries import dex_abi
    abi = dex_abi(chain, dex_l)

    if dex_l in ("aerodrome", "aerodrome_slipstream"):
        return _plan_aerodrome_hop(chain, dex_l, rh, addr_in, addr_out)
    if abi == "univ3" or dex_l == "uniswap_v3":
        return await _plan_univ3_hop(chain, dex_l, rh, addr_in, addr_out, eth_call)
    if abi == "algebra":
        return await _plan_algebra_hop(chain, dex_l, rh, addr_in, addr_out, eth_call)
    if abi == "univ2":
        return await _plan_univ2_hop(chain, dex_l, rh, addr_in, addr_out, eth_call)
    if dex_l == "balancer_v2":
        return _plan_balancer_hop(chain, rh, addr_in, addr_out)
    _LOG.debug("no_pool_resolver_for_venue_family chain=%s dex=%s", chain, dex_l)
    return None


def _plan_base_univ3_from_registry(dex_l, rh, addr_in, addr_out):
    """Base UniV3 identity is the canonical registry, not the generic factory."""
    from ...discovery.base_pool_registry import canonical_pool_by_id
    pool_key = rh.get("pool") or rh.get("pool_address")
    cp = canonical_pool_by_id(pool_key) if pool_key else None
    if cp is None or getattr(cp, "dex", None) != "uniswap_v3":
        return None
    if not getattr(cp, "address", None):
        return None
    fee = rh.get("fee")
    if fee is None:
        fee = getattr(cp, "fee_ppm", None)
    if fee is None:
        return None
    return _HopPlan(
        dex=dex_l, token_in=addr_in, token_out=addr_out, fee=int(fee),
        tick_spacing=rh.get("tick_spacing"), stable=rh.get("stable"),
        tvl_key=cp.address, tvl_addr=cp.address,
        fee_bps=int(fee) // 100, pool_address=cp.address)


async def _plan_univ3_hop(chain, dex_l, rh, addr_in, addr_out, eth_call):
    if chain in ("base", "base-sepolia") and dex_l == "uniswap_v3":
        planned = _plan_base_univ3_from_registry(dex_l, rh, addr_in, addr_out)
        if planned is not None:
            return planned
    fee = rh.get("fee")
    if fee is None or eth_call is None:
        return None
    from ...discovery.univ3_pool_resolver import resolve_univ3_pool
    pool = await resolve_univ3_pool(
        chain, addr_in, addr_out, int(fee), eth_call=eth_call, dex=dex_l)
    if pool is None:
        return None
    return _HopPlan(
        dex=dex_l, token_in=addr_in, token_out=addr_out, fee=int(fee),
        tick_spacing=rh.get("tick_spacing"), stable=rh.get("stable"),
        tvl_key=pool["pool_address"], tvl_addr=pool["pool_address"],
        fee_bps=int(fee) // 100, pool_address=pool["pool_address"])


async def _plan_algebra_hop(chain, dex_l, rh, addr_in, addr_out, eth_call):
    """Dynamic fee stays on the quoter. Do not invent a fee tier."""
    if eth_call is None:
        return None
    from ...discovery.algebra_pool_resolver import resolve_algebra_pool
    pool = await resolve_algebra_pool(
        chain, addr_in, addr_out, eth_call=eth_call, dex=dex_l)
    if pool is None:
        return None
    fee_bps = int(rh["fee_bps"]) if rh.get("fee_bps") is not None else 0
    return _HopPlan(
        dex=dex_l, token_in=addr_in, token_out=addr_out, fee=None,
        tick_spacing=None, stable=None,
        tvl_key=pool["pool_address"], tvl_addr=pool["pool_address"],
        fee_bps=fee_bps, pool_address=pool["pool_address"])


async def _plan_univ2_hop(chain, dex_l, rh, addr_in, addr_out, eth_call):
    """Router quoter. Resolve the pair with getPair, not UniV3 getPool."""
    if eth_call is None:
        return None
    from ...discovery.univ3_pool_resolver import resolve_univ2_pool
    pool = await resolve_univ2_pool(
        chain, addr_in, addr_out, eth_call=eth_call, dex=dex_l)
    if pool is None:
        return None
    fee_bps = int(rh["fee_bps"]) if rh.get("fee_bps") is not None else 30
    return _HopPlan(
        dex=dex_l, token_in=addr_in, token_out=addr_out, fee=None,
        tick_spacing=None, stable=None,
        tvl_key=pool["pool_address"], tvl_addr=pool["pool_address"],
        fee_bps=fee_bps, pool_address=pool["pool_address"])


def _plan_aerodrome_hop(chain, dex_l, rh, addr_in, addr_out):
    """Base canonical identity: address plus tick_spacing or stable."""
    if chain not in ("base", "base-sepolia"):
        return None
    from ...discovery.base_pool_registry import canonical_pool_by_id
    pool_key = rh.get("pool") or rh.get("pool_address")
    cp = canonical_pool_by_id(pool_key) if pool_key else None
    if cp is None or getattr(cp, "dex", None) != dex_l or not getattr(cp, "address", None):
        return None
    if dex_l == "aerodrome_slipstream":
        spacing = getattr(cp, "tick_spacing", None)
        if spacing is None:
            return None
        try:
            spacing_i = int(spacing)
        except (TypeError, ValueError):
            return None
        if spacing_i == 0:
            return None
        return _HopPlan(
            dex=dex_l, token_in=addr_in, token_out=addr_out, fee=None,
            tick_spacing=spacing_i, stable=None,
            tvl_key=cp.address, tvl_addr=cp.address, fee_bps=0,
            pool_address=cp.address)
    stable = getattr(cp, "stable", None)
    if stable is None:
        return None
    return _HopPlan(
        dex=dex_l, token_in=addr_in, token_out=addr_out, fee=None,
        tick_spacing=None, stable=bool(stable),
        tvl_key=cp.address, tvl_addr=cp.address, fee_bps=0,
        pool_address=cp.address)


def _plan_balancer_hop(chain, rh, addr_in, addr_out):
    ident = _explicit_balancer_identity(rh)
    if ident is None:
        _LOG.debug("balancer_v2 hop missing explicit pool identity chain=%s",
                   chain)
        return None
    pool_id, pool_address = ident
    fee_bps = int(rh["fee_bps"]) if rh.get("fee_bps") is not None else 0
    tvl_key = pool_id or pool_address
    return _HopPlan(
        dex="balancer_v2", token_in=addr_in, token_out=addr_out,
        fee=rh.get("fee"), tick_spacing=rh.get("tick_spacing"),
        stable=rh.get("stable"), tvl_key=tvl_key, tvl_addr=pool_address,
        fee_bps=fee_bps, pool_id=pool_id, pool_address=pool_address)


async def _plan_generic_evm(
    chain: str, hm: Dict[str, Any], eth_call,
) -> Optional[Tuple[List[_HopPlan], List[str], int]]:
    """Plan a route whose hops already have venue identities.

    A hop is planned only when ``QuoterRegistry`` already has that DEX on
    this chain, and the existing resolver returns a real pool (UniV3-family,
    Algebra, UniV2) or an explicit Balancer / Base Aerodrome identity.
    Curve, Velodrome, and any other family stay ``None``. One failed hop
    fails the route. No quoter is fabricated.
    """
    route_hops: List[Dict[str, Any]] = list(hm.get("route_hops") or [])
    token_path: List[str] = [str(t).upper() for t in (hm.get("cycle_token_path") or [])]
    if len(route_hops) < 2 or len(token_path) != len(route_hops) + 1:
        return None
    amount_in_wei = _borrow_amount_wei(chain, hm, token_path)
    if amount_in_wei <= 0:                      # no fabricated probe amount
        return None

    plans: List[_HopPlan] = []
    for i, rh in enumerate(route_hops):
        addr_in = _token_addr(chain, rh.get("token_in") or token_path[i])
        addr_out = _token_addr(chain, rh.get("token_out") or token_path[i + 1])
        if not addr_in or not addr_out:
            return None
        planned = await _plan_one_hop(chain, rh, addr_in, addr_out, eth_call)
        if planned is None:
            return None
        plans.append(planned)
    return plans, token_path, amount_in_wei


def make_live_quote_provider(
    quoter_registry,
    *,
    tvl_provider=None,
    tvl_provider_chain: str = "base",
    eth_call_for_chain: Optional[Callable[[str], Optional[Any]]] = None,
    borrow_sizer: Optional[Callable[[str, str, float], Optional[int]]] = None,
    chain: Optional[str] = None,
    token_address_fn: Optional[Callable[[str], Optional[str]]] = None,
    pool_specs: Optional[Dict[str, Dict[str, Any]]] = None,
    probe_amount_fn: Optional[Callable[[str], int]] = None,
) -> Callable[[Dict[str, Any], float], Awaitable[Optional[Dict[str, Any]]]]:
    """Return an async ``QuoteProvider`` bound to a live ``QuoterRegistry``.

    ``tvl_provider`` (M2.2, optional) supplies REAL measured on-chain pool depth
    for Gate 8 (fail-closed when absent). A provider without ``scoped_chains``
    is valid only for ``tvl_provider_chain`` (default ``"base"``). H07: a route
    on any OTHER chain must NOT consume that provider's depth — doing so would
    let Base TVL leak into non-Base economics. A dispatcher that publishes
    ``scoped_chains`` is consulted only for a chain it actually serves, and
    it still cannot answer with another chain's provider. For a mismatched
    chain the depth is left absent, so Gate 8 fails closed.
    ``eth_call_for_chain(chain)`` supplies an async ``eth_call`` for NON-Base
    chains' on-chain pool validation; when it is ``None`` (or returns ``None``
    for a chain), non-Base routes fail closed. Base uses the canonical registry.

    ``borrow_sizer(chain, borrow_token, borrow_amount_usd) -> Optional[int]``
    (H05, optional) converts the requested borrow *dollar* notional into the
    EXACT borrow-token wei amount to quote, using a trustworthy price + decimals.
    When it is supplied and returns a positive size, the route is quoted at that
    EXACT size and the facts are stamped ``size_basis="exact"`` with a bound
    ``quote_notional_usd``. When it is absent (or returns ``None``), the route is
    quoted at a research PROBE size and stamped ``size_basis="probe"`` — the
    verifier then fails closed (``DENIED_SIZE_NOT_QUOTED``) rather than
    extrapolate a probe ratio onto a different dollar notional.
    """
    # SP-3 injected-closure seam (non-Base multichain). When a caller supplies
    # its own chain/token/pool resolvers (see ``make_multichain_quote_provider``,
    # fed by the SP-2 READ-ONLY registry) the self-contained injected provider is
    # returned. The canonical Base / generic-EVM provider below is left COMPLETELY
    # unchanged for the default (non-injected) Base call site.
    if (token_address_fn is not None or pool_specs is not None
            or probe_amount_fn is not None):
        return _make_injected_quote_provider(
            quoter_registry, chain=chain, tvl_provider=tvl_provider,
            token_address_fn=token_address_fn, pool_specs=pool_specs,
            probe_amount_fn=probe_amount_fn, borrow_sizer=borrow_sizer)
    _tvl_chain = str(tvl_provider_chain or "").lower()
    async def _provider(cycle_metadata: Dict[str, Any],
                        borrow_amount_usd: float) -> Optional[Dict[str, Any]]:
        hm = cycle_metadata or {}
        chain = str(hm.get("chain") or "base").lower()

        # M5: when route_hops carry explicit venue identities (GENERIC_DEX /
        # triangular / Balancer activation sources), use the generic planner —
        # including on Base — so balancer_v2 pool_id/pool_address reach
        # QuoterRegistry. Base registry path remains the default when only
        # route_pools is present (regression-frozen).
        if hm.get("route_hops"):
            eth_call = eth_call_for_chain(chain) if eth_call_for_chain else None
            planned = await _plan_generic_evm(chain, hm, eth_call)
        elif chain in ("base", "base-sepolia"):
            planned = _plan_base(hm)
        else:
            eth_call = eth_call_for_chain(chain) if eth_call_for_chain else None
            planned = await _plan_generic_evm(chain, hm, eth_call)
        if planned is None:
            return None
        plans, token_path, amount_in_wei = planned

        # ---- H05: exact-size binding -------------------------------------
        # By default the plan carries a PROBE amount (Base ``probe_amount`` /
        # non-Base ``borrow_amount_wei``). A probe ratio may NOT be applied to
        # the requested dollar notional. If a ``borrow_sizer`` is configured and
        # can price the borrow token, re-size the first hop to the EXACT
        # requested notional and bind ``quote_notional_usd``. Otherwise keep the
        # probe and mark it ``probe`` so the verifier fails closed.
        borrow_token = str(hm.get("borrow_token")
                           or (token_path[0] if token_path else "")).upper()
        size_basis = "probe"
        quote_notional_usd: Optional[float] = None
        if borrow_sizer is not None:
            try:
                sized = borrow_sizer(chain, borrow_token, float(borrow_amount_usd))
                # H05: the sizer may be async (it prices the borrow token via a
                # real on-chain feed). Await it so the EXACT size is resolved
                # before quoting. A sync sizer still works unchanged.
                if inspect.isawaitable(sized):
                    sized = await sized
            except Exception:  # noqa: BLE001 — sizer never fabricates
                sized = None
            if sized is not None and int(sized) > 0:
                amount_in_wei = int(sized)
                size_basis = "exact"
                quote_notional_usd = float(borrow_amount_usd)

        hops: List[Dict[str, Any]] = []
        for i, p in enumerate(plans):
            hop: Dict[str, Any] = {"dex": p.dex, "token_in": p.token_in,
                                   "token_out": p.token_out}
            if i == 0:
                hop["amount_in_wei"] = amount_in_wei
            if p.fee is not None:
                hop["fee"] = p.fee
            if p.tick_spacing is not None:
                hop["tick_spacing"] = p.tick_spacing
            if p.stable is not None:
                hop["stable"] = p.stable
            if getattr(p, "pool_id", None):
                hop["pool_id"] = p.pool_id
            if getattr(p, "pool_address", None):
                hop["pool_address"] = p.pool_address
            hops.append(hop)

        try:
            rq = await quoter_registry.quote_route(chain=chain, hops=hops)
        except Exception:  # noqa: BLE001
            return None

        # QUOTE INTEGRITY — FAIL CLOSED (partial-quote defect, audit 2026-06).
        if rq is None or rq.status != "ok":
            return None
        if any(getattr(h, "status", None) not in (None, "ok") for h in rq.hops):
            return None
        if token_path[0] != token_path[-1]:
            return None  # not a closed cycle → wei ratio meaningless
        final_out = int(rq.final_amount_out_wei or 0)
        if amount_in_wei <= 0 or final_out <= 0:
            return None
        gross_profit_pct = 100.0 * (final_out - amount_in_wei) / amount_in_wei

        # REAL measured on-chain depth (M2.2), keyed per hop via the plan.
        tvl_keys = [p.tvl_key for p in plans]
        pool_tvls: Dict[str, float] = {}
        # H07: only consult the TVL provider for a chain it is scoped to.
        # A route on any other chain must not inherit this provider's depth.
        tvl_usable = tvl_provider_usable_for_chain(
            tvl_provider, chain, _tvl_chain)
        if tvl_provider is not None and not tvl_usable:
            _LOG.warning(
                "live_quote_provider: TVL provider is chain-scoped to %r but "
                "route chain is %r — skipping depth (Gate 8 fails closed) to "
                "avoid cross-chain TVL leakage (H07)", _tvl_chain, chain)
        if tvl_usable:
            for p in plans:
                if not p.tvl_addr:
                    continue
                try:
                    v = await tvl_provider.get_pool_tvl_usd(chain, p.tvl_addr)
                except Exception:  # noqa: BLE001 — provider never fabricates
                    v = None
                if v is not None and float(v) > 0.0:
                    pool_tvls[p.tvl_key] = float(v)

        hop_legs: List[Dict[str, Any]] = []
        for idx, h in enumerate(rq.hops):
            p = plans[idx] if idx < len(plans) else None
            quoted_in = int(getattr(h, "amount_in_wei", 0) or 0)
            quoted_out = int(getattr(h, "amount_out_wei", 0) or 0)

            # Exact quote execution provenance. These values originate directly
            # from the live HopQuote and must never be reconstructed from USD
            # ratios or probe sizes.
            if quoted_in <= 0 or quoted_out <= 0:
                return None

            hop_legs.append({
                "venue_id": f"{getattr(h, 'dex', 'dex')}:{chain}",
                "source_id": _dex_source_id(getattr(h, "dex", ""), chain),
                "price": None,
                "depth_usd": float(pool_tvls.get(p.tvl_key, 0.0)) if p else 0.0,
                "fee_bps": int(p.fee_bps) if p else 0,
                "dex_protocol": getattr(h, "dex", None),
                "status": getattr(h, "status", None),
                "block_number": getattr(h, "block_number", None),

                # B7 exact execution handoff: preserve the authoritative
                # per-hop quote inputs/outputs.
                "token_in": str(getattr(h, "token_in", "") or ""),
                "token_out": str(getattr(h, "token_out", "") or ""),
                "amount_in_wei": quoted_in,
                "amount_out_wei": quoted_out,
            })

        min_tvl = _route_min_tvl(pool_tvls, tvl_keys)
        quote_blocks = [int(h.get("block_number")) for h in hop_legs
                        if isinstance(h.get("block_number"), int)]

        return {
            "hop_legs": hop_legs,
            "gross_profit_pct": gross_profit_pct,
            "tx_gas_units": rq.aggregate_gas_estimate_units,
            "min_pool_tvl_usd_in_route": min_tvl,
            "tvl_provenance": ("onchain_reserves" if tvl_provider is not None
                               else "unverified"),
            "flash_loan_pool_address": "",
            "route_quote_status": rq.status,
            "chain": chain,
            "quote_block": max(quote_blocks) if quote_blocks else None,
            "verified_at_ts": time.time(),
            # H05 exact-size binding provenance.
            "size_basis": size_basis,
            "exact_size": (size_basis == "exact"),
            "quoted_amount_in_wei": int(amount_in_wei),
            "quote_notional_usd": quote_notional_usd,
            "borrow_token": borrow_token,
            # B7 exact route-output provenance.
            "final_amount_out_wei": int(final_out),
        }

    return _provider


def _make_injected_quote_provider(
    quoter_registry,
    *,
    chain=None,
    tvl_provider=None,
    token_address_fn=None,
    pool_specs=None,
    probe_amount_fn=None,
    borrow_sizer=None,
):
    """SP-3 injected-closure quote provider for a CONFIGURED non-Base chain.

    Token addresses + candidate pool specs are supplied by the caller
    (``make_multichain_quote_provider``, fed by the SP-2 READ-ONLY registry);
    nothing is fabricated and no Base data leaks. Adds NO TVL/liquidity logic
    (``tvl_provider`` defaults ``None`` -> Gate 8 fails closed) and claims NO
    runtime verification: a route the live quoter cannot price still yields
    ``None`` (denied:venue_unreadable downstream). H05: an optional async
    ``borrow_sizer`` binds the EXACT first-hop size (``size_basis="exact"``);
    absent/None -> probe sizing. The canonical Base/generic provider is untouched.
    """
    quote_chain = (chain or "base")
    specs = pool_specs if pool_specs is not None else {}

    async def _provider(cycle_metadata: Dict[str, Any],
                        borrow_amount_usd: float) -> Optional[Dict[str, Any]]:
        hm = cycle_metadata or {}
        route_pools: List[str] = list(hm.get("route_pools") or [])
        token_path: List[str] = [str(t).upper() for t in (hm.get("cycle_token_path") or [])]
        borrow_token = (hm.get("borrow_token")
                        or (token_path[0] if token_path else "")).upper()
        if len(route_pools) < 2 or len(token_path) != len(route_pools) + 1:
            return None  # malformed route → unreadable (honest)

        # H05 — EXACT-SIZE binding (fail closed; no probe fallback under exact).
        if borrow_sizer is not None:
            try:
                exact_wei = await borrow_sizer(quote_chain, borrow_token,
                                               borrow_amount_usd)
            except Exception:  # noqa: BLE001 — never fabricate a size
                return None
            if exact_wei is None or int(exact_wei) <= 0:
                return None
            first_amount_wei = int(exact_wei)
            size_basis = "exact"
        else:
            if probe_amount_fn is None:
                return None
            first_amount_wei = int(probe_amount_fn(borrow_token))
            size_basis = "probe"

        hops: List[Dict[str, Any]] = []
        for i, pool_addr in enumerate(route_pools):
            spec = dict(specs.get(pool_addr) or {})
            tin, tout = token_path[i], token_path[i + 1]
            addr_in = token_address_fn(tin) if token_address_fn else None
            addr_out = token_address_fn(tout) if token_address_fn else None
            if not addr_in or not addr_out:
                return None
            hop: Dict[str, Any] = {
                "dex": spec.get("dex") or "uniswap_v3",
                "token_in": addr_in,
                "token_out": addr_out,
            }
            if i == 0:
                hop["amount_in_wei"] = first_amount_wei
            if "fee" in spec:
                hop["fee"] = spec["fee"]
            if "tick_spacing" in spec:
                hop["tick_spacing"] = spec["tick_spacing"]
            if "stable" in spec:
                hop["stable"] = spec["stable"]
            if spec.get("pool_id"):
                hop["pool_id"] = spec["pool_id"]
            addr = spec.get("pool_address") or spec.get("pool_contract_address")
            if addr:
                hop["pool_address"] = addr
            hops.append(hop)

        try:
            rq = await quoter_registry.quote_route(chain=quote_chain, hops=hops)
        except Exception:  # noqa: BLE001
            return None
        # QUOTE INTEGRITY — FAIL CLOSED (partial-quote defect, audit 2026-06).
        if rq is None or rq.status != "ok":
            return None
        if any(getattr(h, "status", None) not in (None, "ok") for h in rq.hops):
            return None
        if token_path[0] != token_path[-1]:
            return None  # not a closed cycle → the wei ratio is meaningless

        amount_in = int(hops[0].get("amount_in_wei") or 0)
        final_out = int(rq.final_amount_out_wei or 0)
        if amount_in <= 0 or final_out <= 0:
            return None
        gross_profit_pct = 100.0 * (final_out - amount_in) / amount_in

        hop_legs: List[Dict[str, Any]] = []
        for h in rq.hops:
            hop_legs.append({
                "venue_id": f"{getattr(h, 'dex', 'dex')}:{quote_chain}",
                "source_id": _dex_source_id(getattr(h, "dex", ""), quote_chain),
                "price": None,
                "depth_usd": 0.0,
                "fee_bps": 0,
                "dex_protocol": getattr(h, "dex", None),
                "status": getattr(h, "status", None),
                "block_number": getattr(h, "block_number", None),
            })
        # REAL measured on-chain depth (M2.2); fail-closed (0.0) without provider.
        pool_tvls = await _resolve_pool_tvls(route_pools, tvl_provider,
                                             chain=quote_chain)
        for leg, pool_addr in zip(hop_legs, route_pools):
            spec = specs.get(pool_addr) or {}
            leg["fee_bps"] = int(spec.get("fee", 3000)) // 100
            leg["depth_usd"] = float(pool_tvls.get(pool_addr, 0.0))

        min_tvl = _route_min_tvl(pool_tvls, route_pools)
        quote_blocks = [int(h.get("block_number")) for h in hop_legs
                        if isinstance(h.get("block_number"), int)]

        return {
            "hop_legs": hop_legs,
            "gross_profit_pct": gross_profit_pct,
            "tx_gas_units": rq.aggregate_gas_estimate_units,
            "min_pool_tvl_usd_in_route": min_tvl,
            "tvl_provenance": ("onchain_reserves" if tvl_provider is not None
                               else "unverified"),
            "flash_loan_pool_address": "",
            "route_quote_status": rq.status,
            "chain": quote_chain,
            "quote_block": max(quote_blocks) if quote_blocks else None,
            "size_basis": size_basis,
            "exact_size": (size_basis == "exact"),
            "quoted_amount_in_wei": int(amount_in),
            "quote_notional_usd": (float(borrow_amount_usd)
                                   if size_basis == "exact" else None),
            "borrow_token": borrow_token,
            "final_amount_out_wei": int(final_out),
            "verified_at_ts": time.time(),
        }

    return _provider


def make_multichain_quote_provider(quoter_registry, chain, *, tvl_provider=None,
                                   borrow_sizer=None):
    """SP-3 — build a live quote provider for a CONFIGURED non-Base chain, sourcing
    token addresses + candidate pool specs from the SP-2 READ-ONLY multichain
    registry (``discovery/multichain_pool_registry``).

    Fail-closed:
      * ``chain == "base"``  → delegate to the canonical Base provider (unchanged).
      * unconfigured/unknown → return ``None`` (no fabricated provider).
    No pool contract address is fabricated (the registry never exposes one), no
    TVL/liquidity logic is added (``tvl_provider`` defaults ``None`` → Gate 8 fails
    closed), and no runtime verification is claimed. H05: an optional async
    ``borrow_sizer(chain, token, usd)`` binds the EXACT first-hop size; default
    ``None`` → probe sizing, behaviour unchanged.
    """
    from ...discovery import multichain_pool_registry as mreg

    c = (chain or "").strip().lower()
    if c == "base":
        return make_live_quote_provider(quoter_registry, tvl_provider=tvl_provider,
                                        borrow_sizer=borrow_sizer)
    if not mreg.is_chain_configured(c):
        return None  # fail closed — never a fabricated non-Base provider

    def _token_addr(sym: str) -> Optional[str]:
        return mreg.token_address(c, sym)  # bound to THIS chain (no leakage)

    def _probe(sym: str) -> int:
        spec = mreg.token_spec(c, sym)
        dec = int(spec["decimals"]) if spec else 18
        return 5 * 10 ** (dec - 2) if dec >= 12 else 200 * 10 ** dec

    pool_specs: Dict[str, Dict[str, Any]] = {}
    for row in mreg.pool_candidate_specs(c):
        vid = row.get("venue_id")
        if not vid:
            continue
        spec: Dict[str, Any] = {"dex": row.get("dex") or "uniswap_v3"}
        fee_bps = row.get("fee_bps")
        if fee_bps is not None:
            spec["fee"] = int(fee_bps) * 100   # bps → ppm for the UniV3 quoter
        pool_specs[vid] = spec

    return make_live_quote_provider(
        quoter_registry, tvl_provider=tvl_provider, chain=c,
        token_address_fn=_token_addr, pool_specs=pool_specs,
        probe_amount_fn=_probe, borrow_sizer=borrow_sizer,
    )
