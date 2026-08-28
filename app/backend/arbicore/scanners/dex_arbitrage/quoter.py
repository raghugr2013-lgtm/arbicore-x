"""ArbiCore X — Phase D D-3.1 DEX quoter abstractions.

Defines the contract every D-3 on-chain quoter must satisfy. Quoters are
PURE VALUE-OBJECT PRODUCERS — they return DEXQuoteResult instances, never
CanonicalOpportunity, never DiscoveryCandidate. INV-2 is preserved by
construction (no EmissionBus reachable from this module — no scanner
orchestrator imports the quoter to drive an emit call).

Two reference implementations are included:

  - EVMV3Quoter — Uniswap V3 / PancakeSwap V3 / Aerodrome share the V3
                  QuoterV2 ABI surface (`quoteExactInputSingle` /
                  `quoteExactInput`). One class parameterised by
                  (chain, dex, rpc_env_var, quoter_address) handles all
                  three DEX families across all target EVM chains.
  - RaydiumQuoter — Solana / Raydium AMM pool-state reads via Helius RPC,
                    off-chain quote math.

Both implementations are **graceful-disable**: if the required RPC env var is
absent the quoter returns DEXQuoteResult(ok=False, reason="credentials_missing")
without raising, so the rest of the system continues to work during D-3
shadow rollout when only some providers are provisioned.

Live HTTP is intentionally NOT exercised in D-3.1 unit tests — credentials
land at D-3.6. The quoter contract + graceful-disable + provenance attribution
are the surface tested at this wave.
"""
from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ============================================================================
# Result value object
# ============================================================================

@dataclass
class DEXQuoteResult:
    """Single-leg quote outcome. Pure value object — never persisted."""

    ok: bool
    chain: str
    dex: str
    pool_address: Optional[str] = None
    token_in: Optional[str] = None
    token_out: Optional[str] = None
    size_in_usd: Optional[float] = None
    amount_in: Optional[float] = None
    amount_out: Optional[float] = None
    effective_price: Optional[float] = None      # amount_out / amount_in
    mid_price: Optional[float] = None             # mid at the pool (no size impact)
    slippage_pct: Optional[float] = None
    fee_tier_bps: Optional[int] = None
    pool_liquidity_usd: Optional[float] = None
    gas_estimate_usd: Optional[float] = None
    quoted_at_ts: float = field(default_factory=lambda: time.time())
    age_ms: Optional[int] = None
    reason: Optional[str] = None                  # "" on ok; explanation otherwise
    source_id: Optional[str] = None               # SOURCE_REGISTRY id (INV-3 attribution)
    raw: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Quoter ABC
# ============================================================================

class BaseDEXQuoter(ABC):
    """Contract every D-3 on-chain quoter satisfies.

    Subclasses MUST set:
      - chain, dex            (str identifiers)
      - source_id             (key in arbicore.data.provenance.SOURCE_REGISTRY)
      - rpc_env_var           (e.g. "ALCHEMY_API_KEY"); None ⇒ no creds required
    Subclasses MUST implement:
      - _quote_impl(...)      (live integration; only invoked when credentials present)
    """

    chain: str = ""
    dex: str = ""
    source_id: str = ""
    rpc_env_var: Optional[str] = None

    def __init__(self) -> None:
        if not self.chain or not self.dex or not self.source_id:
            raise TypeError(
                f"{type(self).__name__} must set chain, dex, source_id at class scope"
            )

    # ----- public API -------------------------------------------------------

    @property
    def credentials_available(self) -> bool:
        if not self.rpc_env_var:
            return True
        return bool(os.environ.get(self.rpc_env_var, "").strip())

    async def quote(self, *, pair_canonical: str, size_in_usd: float,
                    direction: str = "buy") -> DEXQuoteResult:
        """Return a DEXQuoteResult. NEVER raises.

        Graceful disable: if rpc_env_var is set but absent from os.environ,
        returns ok=False with reason='credentials_missing'. Live-integration
        errors are also caught and returned as ok=False results.
        """
        if not self.credentials_available:
            return DEXQuoteResult(
                ok=False, chain=self.chain, dex=self.dex,
                source_id=self.source_id,
                reason=f"credentials_missing:{self.rpc_env_var}",
            )
        if direction not in ("buy", "sell"):
            return DEXQuoteResult(
                ok=False, chain=self.chain, dex=self.dex,
                source_id=self.source_id, reason="invalid_direction",
            )
        try:
            return await self._quote_impl(
                pair_canonical=pair_canonical,
                size_in_usd=size_in_usd,
                direction=direction,
            )
        except Exception as exc:  # noqa: BLE001
            return DEXQuoteResult(
                ok=False, chain=self.chain, dex=self.dex,
                source_id=self.source_id,
                reason=f"quoter_error:{type(exc).__name__}:{exc}",
            )

    # ----- subclass contract -----------------------------------------------

    @abstractmethod
    async def _quote_impl(self, *, pair_canonical: str,
                          size_in_usd: float, direction: str) -> DEXQuoteResult:
        """Live integration. Invoked only when credentials_available is True."""


# ============================================================================
# EVM V3 quoter (Uniswap V3 / PancakeSwap V3 / Aerodrome share ABI surface)
# ============================================================================

# QuoterV2 contract addresses per (dex, chain). Used by _quote_impl when wired
# in D-3.6; D-3.1 tests do not exercise these.
EVM_V3_QUOTER_CONTRACTS: Dict[tuple, str] = {
    ("uniswap_v3", "ethereum"): "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",
    ("uniswap_v3", "arbitrum"): "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",
    ("uniswap_v3", "base"):     "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",
    ("pancake_v3", "bnb"):       "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997",
    ("pancake_v3", "arbitrum"):  "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997",
    ("pancake_v3", "base"):      "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997",
    ("aerodrome",  "base"):      "0xA8AAd9a89CD8AD68BcE5A4eaF5CB75f4Fb15D89F",
}


class EVMV3Quoter(BaseDEXQuoter):
    """Uniswap V3 / PancakeSwap V3 / Aerodrome quoter (shared ABI).

    rpc_env_var defaults to ALCHEMY_API_KEY. When live integration lands in
    D-3.6 the implementation will issue eth_call against
    EVM_V3_QUOTER_CONTRACTS[(dex, chain)].quoteExactInputSingle for the
    fee-tier candidate set, picking the best output. Until then _quote_impl
    returns ok=False with reason='not_yet_wired' — discoverable, tested,
    documented; no surprises.
    """

    rpc_env_var = "ALCHEMY_API_KEY"

    def __init__(self, *, chain: str, dex: str, source_id: str) -> None:
        self.chain = chain
        self.dex = dex
        self.source_id = source_id
        super().__init__()
        if (dex, chain) not in EVM_V3_QUOTER_CONTRACTS:
            raise ValueError(
                f"EVMV3Quoter has no QuoterV2 address for ({dex}, {chain})"
            )
        self.quoter_address = EVM_V3_QUOTER_CONTRACTS[(dex, chain)]

    # D-3.6A/B: the wired live paths. Every other (dex, chain) stays
    # explicitly not-yet-wired (we do NOT implement all venues/chains yet).
    _WIRED_LIVE = {("uniswap_v3", "base"), ("aerodrome", "base")}

    @property
    def credentials_available(self) -> bool:
        # The wired Base paths are reachable through the SAME canonical RPC
        # precedence resolver the rest of the architecture uses
        # (ARBICORE_RPC_URL_<CHAIN> > ARBICORE_RPC_URL > <CHAIN>_RPC_URL), so they
        # are enabled whenever a Base RPC is configured — no separate key needed.
        # Every other (dex, chain) keeps the legacy ALCHEMY_API_KEY gate exactly.
        if (self.dex, self.chain) in self._WIRED_LIVE:
            try:
                from ...config.persistent import resolve_rpc_url_from_env
                if resolve_rpc_url_from_env(self.chain):
                    return True
            except Exception:  # noqa: BLE001
                pass
        return super().credentials_available

    async def _quote_impl(self, *, pair_canonical: str,
                          size_in_usd: float, direction: str) -> DEXQuoteResult:
        if (self.dex, self.chain) in self._WIRED_LIVE:
            if self.dex == "uniswap_v3":
                return await self._quote_base_univ3(
                    pair_canonical=pair_canonical, size_in_usd=size_in_usd,
                    direction=direction)
            if self.dex == "aerodrome":
                return await self._quote_base_aerodrome(
                    pair_canonical=pair_canonical, size_in_usd=size_in_usd,
                    direction=direction)
        # Other venues/chains land in later D-3.6 sub-waves — explicit, tested.
        return self._fail(pair_canonical, size_in_usd,
                          "not_yet_wired:only_base_uniswap_v3_and_aerodrome_wired")

    # ----- D-3.6A live implementation (Base · Uniswap V3 · QuoterV2) --------

    def _fail(self, pair_canonical: str, size_in_usd: float,
              reason: str) -> DEXQuoteResult:
        """Fail-closed result — never fabricates a price. Preserves token
        identity for observability."""
        pair = (pair_canonical or "").split("@", 1)[0]
        base_sym = pair.split("/")[0] if "/" in pair else (pair or None)
        quote_sym = pair.split("/")[1] if "/" in pair else None
        return DEXQuoteResult(
            ok=False, chain=self.chain, dex=self.dex, source_id=self.source_id,
            token_in=base_sym, token_out=quote_sym, size_in_usd=size_in_usd,
            reason=reason)

    async def _quote_base_univ3(self, *, pair_canonical: str,
                                size_in_usd: float, direction: str
                                ) -> DEXQuoteResult:
        """Real Base → Uniswap V3 → QuoterV2 → eth_call → amountOut.

        Delegates the on-chain read to the canonical ``QuoterRegistry`` /
        ``UniV3QuoterV2`` backend (single source of truth — no parallel RPC or
        ABI logic). Token identity + the fee-tier candidate set come from the
        existing canonical Base registry (no duplicate token list). Fail-closed:
        any unknown token / unpriceable pool / reverted quote returns
        ok=False with a distinct reason — never a fabricated price.
        """
        from ...discovery import base_venues as bv
        from ...discovery import base_pool_registry as reg
        from ...execution.quoter import QuoterRegistry

        pair = (pair_canonical or "").split("@", 1)[0]
        if "/" not in pair:
            return self._fail(pair_canonical, size_in_usd, "malformed_pair")
        base_raw, quote_raw = (s.strip() for s in pair.split("/", 1))
        base_sym = bv.canonical_symbol(base_raw)
        quote_sym = bv.canonical_symbol(quote_raw)
        if not base_sym or not quote_sym:
            return self._fail(pair_canonical, size_in_usd,
                              f"unknown_token:{base_raw}/{quote_raw}")

        # buy = acquire BASE spending QUOTE; sell = dispose BASE receiving QUOTE.
        if direction == "buy":
            tin_sym, tout_sym = quote_sym, base_sym
        else:
            tin_sym, tout_sym = base_sym, quote_sym
        tin_addr = bv.token_address(tin_sym)
        tout_addr = bv.token_address(tout_sym)
        dec_in = int(bv.TOKENS[tin_sym]["decimals"])
        dec_out = int(bv.TOKENS[tout_sym]["decimals"])

        # Fee-tier candidate set + pool addresses from the canonical registry
        # (deterministic-verified UniV3 pools only — no fabricated addresses).
        want = frozenset({base_sym.upper(), quote_sym.upper()})
        pool_by_tier: Dict[int, str] = {}
        for p in reg.get_canonical_pools():
            if (p.dex == "uniswap_v3"
                    and p.address_resolution == reg.DETERMINISTIC_VERIFIED
                    and p.fee_ppm is not None and p.address
                    and frozenset({p.token0_symbol.upper(),
                                   p.token1_symbol.upper()}) == want):
                pool_by_tier[int(p.fee_ppm)] = p.address
        tiers = sorted(pool_by_tier)
        if not tiers:
            return self._fail(pair_canonical, size_in_usd,
                              f"no_univ3_pool_for_pair:{base_sym}/{quote_sym}")

        # Size the input leg. USD-stable input → exact USD notional; otherwise
        # fall back to the canonical marginal probe notional (both are REAL
        # inputs — the returned amountOut is always a genuine on-chain quote).
        if bv.is_stable(tin_sym):
            amount_in_wei = int(round(float(size_in_usd) * (10 ** dec_in)))
            size_basis = "usd_stable_notional"
        else:
            amount_in_wei = int(bv.probe_amount(tin_sym))
            size_basis = "probe_notional_fallback"
        if amount_in_wei <= 0:
            return self._fail(pair_canonical, size_in_usd, "nonpositive_amount_in")

        registry = QuoterRegistry()
        best: Optional[Dict[str, Any]] = None
        for fee_ppm in tiers:
            rq = await registry.quote_route(chain="base", hops=[{
                "dex": "uniswap_v3", "token_in": tin_addr, "token_out": tout_addr,
                "amount_in_wei": amount_in_wei, "fee": int(fee_ppm)}])
            if rq.status != "ok" or not rq.hops:
                continue
            out_wei = int(rq.final_amount_out_wei or 0)
            if out_wei <= 0:
                continue
            if best is None or out_wei > best["out_wei"]:
                best = {"out_wei": out_wei, "fee_ppm": int(fee_ppm),
                        "hop": rq.hops[0]}
        if best is None:
            return self._fail(pair_canonical, size_in_usd,
                              "quote_unavailable:all_tiers_reverted_or_zero")

        amount_in = amount_in_wei / (10 ** dec_in)
        amount_out = best["out_wei"] / (10 ** dec_out)
        eff = (amount_out / amount_in) if amount_in > 0 else None
        hop = best["hop"]
        return DEXQuoteResult(
            ok=True, chain=self.chain, dex=self.dex, source_id=self.source_id,
            pool_address=pool_by_tier.get(best["fee_ppm"]),
            token_in=tin_sym, token_out=tout_sym,
            size_in_usd=float(size_in_usd),
            amount_in=amount_in, amount_out=amount_out, effective_price=eff,
            fee_tier_bps=int(best["fee_ppm"] // 100),
            quoted_at_ts=time.time(), reason="",
            raw={
                "amount_in_wei": str(amount_in_wei),
                "amount_out_wei": str(best["out_wei"]),
                "fee_ppm": best["fee_ppm"],
                "size_basis": size_basis,
                "direction": direction,
                "winning_backend": "uniswap_v3",
                "quoter_contract": hop.quoter_contract,
                "rpc_host": hop.rpc_host,
                "block_number": hop.block_number,
                "gas_estimate_units": hop.gas_estimate_units,
                "route_status": "ok",
                "candidate_fee_tiers_ppm": list(tiers),
            },
        )

    # ----- D-3.6B live implementation (Base · Aerodrome classic + SlipStream) --

    async def _quote_base_aerodrome(self, *, pair_canonical: str,
                                    size_in_usd: float, direction: str
                                    ) -> DEXQuoteResult:
        """Real Base → Aerodrome → amountOut across BOTH Aerodrome pool families.

        For a dex="aerodrome" request we query every Aerodrome venue the
        existing canonical registry knows for the pair — classic AMM
        (Router.getAmountsOut) and SlipStream concentrated liquidity
        (QuoterV2-style) — each delegated to the canonical ``QuoterRegistry``
        backend (single source of truth: no parallel RPC / ABI / pool-address
        resolver). The best VALID amountOut wins; provenance records which
        Aerodrome family/backend produced it and every backend attempt.
        Fail-closed: a quote is returned only when ≥1 authoritative backend
        succeeds with a positive amountOut — never a synthesized fallback.
        """
        from ...discovery import base_venues as bv
        from ...discovery import base_pool_registry as reg
        from ...execution.quoter import QuoterRegistry

        pair = (pair_canonical or "").split("@", 1)[0]
        if "/" not in pair:
            return self._fail(pair_canonical, size_in_usd, "malformed_pair")
        base_raw, quote_raw = (s.strip() for s in pair.split("/", 1))
        base_sym = bv.canonical_symbol(base_raw)
        quote_sym = bv.canonical_symbol(quote_raw)
        if not base_sym or not quote_sym:
            return self._fail(pair_canonical, size_in_usd,
                              f"unknown_token:{base_raw}/{quote_raw}")

        if direction == "buy":
            tin_sym, tout_sym = quote_sym, base_sym
        else:
            tin_sym, tout_sym = base_sym, quote_sym
        tin_addr = bv.token_address(tin_sym)
        tout_addr = bv.token_address(tout_sym)
        dec_in = int(bv.TOKENS[tin_sym]["decimals"])
        dec_out = int(bv.TOKENS[tout_sym]["decimals"])

        # Size the input leg (identical policy to the UniV3 path).
        if bv.is_stable(tin_sym):
            amount_in_wei = int(round(float(size_in_usd) * (10 ** dec_in)))
            size_basis = "usd_stable_notional"
        else:
            amount_in_wei = int(bv.probe_amount(tin_sym))
            size_basis = "probe_notional_fallback"
        if amount_in_wei <= 0:
            return self._fail(pair_canonical, size_in_usd, "nonpositive_amount_in")

        # Enumerate Aerodrome candidates for the pair from the canonical registry
        # (classic + SlipStream). Neither backend needs a pre-resolved pool
        # address (Router / QuoterV2 resolve the pool internally), so the
        # unresolved-address blocker does not apply here.
        want = frozenset({base_sym.upper(), quote_sym.upper()})
        candidates: List[Tuple[str, Dict[str, Any]]] = []
        for p in reg.get_canonical_pools():
            if frozenset({p.token0_symbol.upper(),
                          p.token1_symbol.upper()}) != want:
                continue
            if p.dex == "aerodrome":
                candidates.append(("aerodrome_classic", {
                    "dex": "aerodrome", "token_in": tin_addr,
                    "token_out": tout_addr, "amount_in_wei": amount_in_wei,
                    "stable": bool(p.stable)}))
            elif p.dex == "aerodrome_slipstream":
                candidates.append(("aerodrome_slipstream", {
                    "dex": "aerodrome_slipstream", "token_in": tin_addr,
                    "token_out": tout_addr, "amount_in_wei": amount_in_wei,
                    "tick_spacing": int(p.tick_spacing or 0)}))
        if not candidates:
            return self._fail(pair_canonical, size_in_usd,
                              f"no_aerodrome_pool_for_pair:{base_sym}/{quote_sym}")

        registry = QuoterRegistry()
        attempts: List[Dict[str, Any]] = []
        best: Optional[Dict[str, Any]] = None
        for label, hop in candidates:
            rq = await registry.quote_route(chain="base", hops=[hop])
            out_wei = int(rq.final_amount_out_wei or 0) if rq.hops else 0
            if rq.status == "ok" and rq.hops and out_wei > 0:
                hopq = rq.hops[0]
                attempts.append({
                    "backend": label, "dex": hop["dex"], "status": "ok",
                    "amount_out_wei": str(out_wei),
                    "quoter_contract": hopq.quoter_contract,
                    "block_number": hopq.block_number,
                    "stable": hop.get("stable"),
                    "tick_spacing": hop.get("tick_spacing")})
                if best is None or out_wei > best["out_wei"]:
                    best = {"out_wei": out_wei, "label": label, "hop": hop,
                            "hopq": hopq}
            else:
                err = (rq.hops[0].error if rq.hops else None)
                attempts.append({
                    "backend": label, "dex": hop["dex"],
                    "status": rq.status, "error": err,
                    "stable": hop.get("stable"),
                    "tick_spacing": hop.get("tick_spacing")})
        if best is None:
            return self._fail(pair_canonical, size_in_usd,
                              "quote_unavailable:all_aerodrome_backends_failed")

        amount_in = amount_in_wei / (10 ** dec_in)
        amount_out = best["out_wei"] / (10 ** dec_out)
        eff = (amount_out / amount_in) if amount_in > 0 else None
        hopq = best["hopq"]
        return DEXQuoteResult(
            ok=True, chain=self.chain, dex=self.dex, source_id=self.source_id,
            pool_address=None,   # Aerodrome pool address is resolved on-chain by
                                 # the Router/Quoter; not fabricated here.
            token_in=tin_sym, token_out=tout_sym,
            size_in_usd=float(size_in_usd),
            amount_in=amount_in, amount_out=amount_out, effective_price=eff,
            fee_tier_bps=None,   # Aerodrome fees are dynamic — not asserted.
            quoted_at_ts=time.time(), reason="",
            raw={
                "amount_in_wei": str(amount_in_wei),
                "amount_out_wei": str(best["out_wei"]),
                "size_basis": size_basis,
                "direction": direction,
                "winning_backend": best["label"],
                "winning_dex": best["hop"]["dex"],
                "winning_stable": best["hop"].get("stable"),
                "winning_tick_spacing": best["hop"].get("tick_spacing"),
                "quoter_contract": hopq.quoter_contract,
                "rpc_host": hopq.rpc_host,
                "block_number": hopq.block_number,
                "gas_estimate_units": hopq.gas_estimate_units,
                "route_status": "ok",
                "backend_attempts": attempts,
            },
        )


# ============================================================================
# Solana / Raydium quoter
# ============================================================================

class RaydiumQuoter(BaseDEXQuoter):
    """Solana / Raydium AMM quoter (off-chain math against on-chain pool state).

    rpc_env_var = HELIUS_API_KEY. _quote_impl is stubbed for D-3.1 like the
    EVM quoter — wiring lands at D-3.6.
    """

    chain = "solana"
    dex = "raydium"
    source_id = "raydium_quoter_solana"
    rpc_env_var = "HELIUS_API_KEY"

    async def _quote_impl(self, *, pair_canonical: str,
                          size_in_usd: float, direction: str) -> DEXQuoteResult:
        return DEXQuoteResult(
            ok=False, chain=self.chain, dex=self.dex,
            source_id=self.source_id,
            token_in=pair_canonical.split("/")[0],
            token_out=pair_canonical.split("/")[1] if "/" in pair_canonical else None,
            size_in_usd=size_in_usd,
            reason="not_yet_wired:D-3.6_will_wire_helius_pool_reads",
        )


# ============================================================================
# Factory
# ============================================================================

def build_default_quoters() -> List[BaseDEXQuoter]:
    """Instantiate one quoter per (dex, chain) in the D-3 universe.

    Total 8 quoters: 7 EVM V3 (uniswap_v3 × 3, pancake_v3 × 3, aerodrome × 1)
    + 1 Solana Raydium. Each instance is independently graceful-disabled if
    its rpc_env_var is missing.
    """
    out: List[BaseDEXQuoter] = []
    for (dex, chain), _addr in EVM_V3_QUOTER_CONTRACTS.items():
        source_id = f"{dex}_quoter_{chain}"
        out.append(EVMV3Quoter(chain=chain, dex=dex, source_id=source_id))
    out.append(RaydiumQuoter())
    return out
