"""SP-2 — Canonical multichain pool-spec / token-address registry (fail-closed).

A thin, explicit, READ-ONLY facade over the two ALREADY-VERIFIED data sources
that ship in the repo:

  * Base (mainnet)    → ``discovery/base_venues.py`` (curated, on-chain-verified
                        tokens + curated venue specs). Delegated verbatim so Base
                        behavior is preserved EXACTLY (SP-2 introduces no new Base
                        data and does not touch ``base_venues``).
  * The 5 EVM chains  → ``chains/registries.py`` (verified public token contract
    (ethereum,          addresses + DEX factory addresses). No pool contract
     arbitrum,          addresses are fabricated: concrete pools are resolved
     optimism,          on-chain LATER (SP-3+) and stay UNAVAILABLE here.
     polygon, bnb)

Contract / invariants (per SP-2 requirements):
  * Every canonical chain has an EXPLICIT configuration state
    (``CONFIGURED`` / ``KNOWN_NO_REGISTRY`` / ``UNCONFIGURED``).
  * An unconfigured chain, an unknown chain, or a missing token/pool spec returns
    an EMPTY / ``None`` result — never a fabricated address, fee tier, pool, or
    liquidity value, and never a Base-derived fallback (no cross-chain leakage).
  * Base-Sepolia keeps its EXISTING behavior: it has a QuoterV2 address (SP-1) but
    NO token/pool registry, so it is ``KNOWN_NO_REGISTRY`` and returns empty here.
  * Pure/offline: this module performs NO RPC / eth_call / network I/O and does NOT
    read ``PROVIDER_RPC_URL[S]_<CHAIN>`` (provider precedence/semantics untouched).
  * SP-2 does NOT wire this registry to the live scanner, live quote provider, or
    TVL provider (that is SP-3/SP-4).

Provenance:
  * Token + DEX-factory addresses are the repo's pre-existing VERIFIED public
    constants (see the source-module docstrings).
  * Pool CANDIDATE specs carry ``pool_contract_address=None`` +
    ``resolution="onchain_pending"`` — RUNTIME-VERIFICATION-PENDING; they are
    candidate (dex, pair, fee-tier) tuples, not claims that a specific pool exists.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..chains import registries
from . import base_venues

# ---- explicit chain configuration states ---------------------------------- #
CONFIGURED = "CONFIGURED"                 # verified tokens + dexes available
KNOWN_NO_REGISTRY = "KNOWN_NO_REGISTRY"   # recognised chain, but no token/pool registry
UNCONFIGURED = "UNCONFIGURED"             # not a canonical/known chain → fail closed

# The six canonical mainnet chains ArbiCore targets.
CANONICAL_CHAINS = ("ethereum", "arbitrum", "base", "optimism", "polygon", "bnb")

# Recognised chains that intentionally have NO token/pool registry (fail closed).
_KNOWN_NO_REGISTRY = frozenset({"base-sepolia"})


def _norm(chain: str) -> str:
    return (chain or "").strip().lower()


def chain_state(chain: str) -> str:
    """Explicit configuration state for ``chain`` (never raises)."""
    c = _norm(chain)
    if c == "base":
        return CONFIGURED
    if c in registries.CHAIN_REGISTRIES:
        return CONFIGURED
    if c in _KNOWN_NO_REGISTRY:
        return KNOWN_NO_REGISTRY
    return UNCONFIGURED


def is_chain_configured(chain: str) -> bool:
    return chain_state(chain) == CONFIGURED


def configured_chains() -> List[str]:
    """Sorted list of chains with a verified token/pool registry."""
    return sorted(c for c in CANONICAL_CHAINS if is_chain_configured(c))


# ---- token layer ----------------------------------------------------------- #

def tokens(chain: str) -> Dict[str, Dict[str, Any]]:
    """All registered token specs for ``chain`` as ``{symbol: {address, decimals}}``.

    Fail-closed empty dict for unconfigured/unknown chains. Base delegates to the
    curated ``base_venues`` map (preserved exactly); the 5 EVM chains use the
    verified ``chains/registries`` constants.
    """
    c = _norm(chain)
    if c == "base":
        return {sym: {"address": meta["address"], "decimals": meta["decimals"]}
                for sym, meta in base_venues.TOKENS.items()}
    if c in registries.CHAIN_REGISTRIES:
        return {sym: {"address": meta["address"], "decimals": meta["decimals"]}
                for sym, meta in registries.tokens_for(c).items()}
    return {}


def _lookup_symbol(chain_tokens: Dict[str, Any], symbol: str) -> Optional[str]:
    """Case-insensitive symbol resolution within a SINGLE chain's token map."""
    if not symbol:
        return None
    if symbol in chain_tokens:
        return symbol
    upper = {s.upper(): s for s in chain_tokens}
    return upper.get(symbol.upper())


def token_spec(chain: str, symbol: str) -> Optional[Dict[str, Any]]:
    """``{address, decimals}`` for ``symbol`` on ``chain`` (case-insensitive), or
    ``None`` when the chain is unconfigured or the symbol is not registered.
    No cross-chain fallback."""
    chain_tokens = tokens(chain)
    canon = _lookup_symbol(chain_tokens, symbol)
    return dict(chain_tokens[canon]) if canon else None


def token_address(chain: str, symbol: str) -> Optional[str]:
    """Verified on-chain token address for ``symbol`` on ``chain``, else ``None``.

    Base delegates to ``base_venues.token_address`` to preserve its genuinely
    mixed-case symbol handling (cbETH/USDbC/…) exactly."""
    if _norm(chain) == "base":
        return base_venues.token_address(symbol)
    spec = token_spec(chain, symbol)
    return spec["address"] if spec else None


# ---- DEX layer (verified factory addresses; no pool addresses) ------------- #

def dex_specs(chain: str) -> List[Dict[str, Any]]:
    """Registered DEX specs for ``chain``.

    * 5 EVM chains → verified ``{dex, kind, factory}`` from ``chains/registries``.
    * Base        → dex NAMES derived from the curated Base venue list; Base
                    factory addresses are not tracked in ``base_venues`` (its live
                    path resolves pools via the on-chain quoter/router), so
                    ``factory`` is ``None`` here (never fabricated).
    * otherwise   → empty (fail closed).
    """
    c = _norm(chain)
    if c in registries.CHAIN_REGISTRIES:
        return [dict(d) for d in registries.dexes_for(c)]
    if c == "base":
        seen: List[str] = []
        for dex, _a, _b, _p in base_venues.VENUES:
            if dex not in seen:
                seen.append(dex)
        return [{"dex": d, "kind": None, "factory": None} for d in seen]
    return []


# ---- pool CANDIDATE specs (no concrete pool addresses; onchain_pending) ---- #

def pool_candidate_specs(chain: str) -> List[Dict[str, Any]]:
    """Candidate (dex, token-pair, fee-tier) venue specs for ``chain``.

    These are NOT claims that a specific pool exists: each carries
    ``pool_contract_address=None`` and ``resolution="onchain_pending"``. Concrete
    pool addresses + TVL are resolved on-chain later (SP-3/SP-4), fail-closed.

    * Base → the curated ``base_venues`` venue specs (delegated verbatim).
    * 5 EVM chains → the existing pure/offline ``multichain_venues`` enumeration.
    * otherwise → empty (fail closed).
    """
    c = _norm(chain)
    out: List[Dict[str, Any]] = []
    if c == "base":
        _pools, specs = base_venues.build_pool_graph()
        for venue_id, spec in specs.items():
            row = {"venue_id": venue_id,
                   "pool_contract_address": None,
                   "resolution": "onchain_pending"}
            row.update(spec)
            out.append(row)
        return out
    if c in registries.CHAIN_REGISTRIES:
        from .multichain_venues import build_pool_graph
        for node in build_pool_graph(c):
            out.append({
                "venue_id": node.pool_address,   # synthetic id, not a contract
                "dex": node.dex_protocol,
                "token_a": node.token_a,
                "token_b": node.token_b,
                "fee_bps": node.fee_bps,
                "pool_contract_address": None,
                "resolution": "onchain_pending",
            })
        return out
    return []


def provenance(chain: str) -> Dict[str, Any]:
    """Explicit provenance / verification status for ``chain`` (never raises)."""
    state = chain_state(chain)
    configured = state == CONFIGURED
    c = _norm(chain)
    token_src = ("base_venues (on-chain verified)" if c == "base"
                 else "chains/registries (verified public constants)"
                 if c in registries.CHAIN_REGISTRIES else None)
    return {
        "chain": c,
        "state": state,
        "configured": configured,
        "token_address_provenance": token_src,
        "dex_factory_provenance": (
            "chains/registries (verified)" if c in registries.CHAIN_REGISTRIES
            else "base_venues (names only; factory not tracked)" if c == "base"
            else None),
        "pool_address_status": ("onchain_pending" if configured else "unavailable"),
        "runtime_verified": False,   # SP-2 is offline; live proof is SP-3+/VPS
    }


__all__ = [
    "CONFIGURED", "KNOWN_NO_REGISTRY", "UNCONFIGURED", "CANONICAL_CHAINS",
    "chain_state", "is_chain_configured", "configured_chains",
    "tokens", "token_spec", "token_address", "dex_specs",
    "pool_candidate_specs", "provenance",
]
