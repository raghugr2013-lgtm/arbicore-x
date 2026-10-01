"""P1 — Balancer V2 automatic candidate-pool discovery / enumeration.

This layer sits AROUND the frozen P0 adapter
(``balancer_v2_pool_discovery``). It answers *"which Balancer V2 pools exist for
this token pair?"* and then re-validates every candidate through the exact P0
on-chain path before pricing it. It NEVER re-implements P0 validation and NEVER
introduces a second incompatible quote path.

Flow
----
    token pair
      -> discovery source (candidate pool identities only)
      -> dedupe
      -> [per candidate] Vault check -> P0 discover_and_quote() (identity /
         membership / balances / decimals / fee / staleness / liquidity /
         queryBatchSwap)
      -> rank valid exact-size quote candidates

Fail-closed contract
--------------------
* Discovery is CANDIDATE-ONLY. It is never authoritative — every candidate must
  pass the on-chain P0 validation before it can produce a quote.
* A discovery source that is down / unconfigured / erroring yields an explicit
  ``DISCOVERY_UNAVAILABLE`` state. This is NOT the same as "no pools" and is
  NEVER collapsed into zero liquidity / zero output.
* ``OK`` with an empty ``quotes`` list means discovery worked but no candidate
  survived on-chain validation — also honest, also not fabricated.
* Chain-aware: only chains where the Balancer V2 Vault is deployed
  (Ethereum/Base/Arbitrum/Optimism/Polygon). BNB is UNSUPPORTED.
* No pool address is ever fabricated/hardcoded to satisfy a quote. No signing,
  no broadcast, no execution — read-only.

The discovery source is an injected abstraction (``BalancerV2PoolSource``) so
the enumeration logic is fully unit-testable offline and the real source
(subgraph / on-chain event log) can evolve independently.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from eth_utils import to_checksum_address

from .balancer_v2_pool_discovery import (
    BALANCER_V2_VAULT_BY_CHAIN,
    OK as P0_OK,
    BalancerV2Quote,
    EthCallFn,
    discover_and_quote,
)

# --------------------------------------------------------------------------- #
# Status vocabulary                                                           #
# --------------------------------------------------------------------------- #

# Discovery-source statuses
SRC_OK = "ok"
SRC_DISCOVERY_UNAVAILABLE = "discovery_unavailable"
SRC_UNSUPPORTED_CHAIN = "unsupported_chain"
SRC_MALFORMED = "malformed_discovery"

# Enumeration result statuses
ENUM_OK = "ok"
ENUM_DISCOVERY_UNAVAILABLE = "discovery_unavailable"
ENUM_UNSUPPORTED_CHAIN = "unsupported_chain"
ENUM_MALFORMED_DISCOVERY = "malformed_discovery"

# Extra per-candidate rejection reason (beyond the P0 statuses)
WRONG_VAULT = "wrong_vault"
MISSING_POOL_IDENTITY = "missing_pool_identity"


# --------------------------------------------------------------------------- #
# Data model                                                                  #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class PoolCandidate:
    chain: str
    pool_id: Optional[str] = None
    pool_address: Optional[str] = None
    declared_vault: Optional[str] = None
    source: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

    def identity_key(self) -> Optional[str]:
        if self.pool_id:
            return ("id:" + str(self.pool_id)).lower()
        if self.pool_address:
            return ("addr:" + str(self.pool_address)).lower()
        return None


@dataclass(frozen=True)
class DiscoverySourceResult:
    status: str
    candidates: List[PoolCandidate] = field(default_factory=list)
    source_name: str = "unknown"
    error: Optional[str] = None
    provenance: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class RejectedCandidate:
    candidate: PoolCandidate
    status: str
    error: Optional[str] = None


@dataclass(frozen=True)
class EnumeratedQuote:
    candidate: PoolCandidate
    quote: BalancerV2Quote   # quote.status == OK guaranteed for entries here

    @property
    def amount_out_wei(self) -> int:
        return int(self.quote.amount_out_wei)


@dataclass(frozen=True)
class EnumerationResult:
    status: str
    chain: str
    token_in: str
    token_out: str
    amount_in_wei: int
    source_name: str = "unknown"
    quotes: List[EnumeratedQuote] = field(default_factory=list)   # ranked, best first
    rejected: List[RejectedCandidate] = field(default_factory=list)
    error: Optional[str] = None
    discovery_provenance: Optional[Dict[str, Any]] = None

    @property
    def best(self) -> Optional[EnumeratedQuote]:
        return self.quotes[0] if self.quotes else None


# --------------------------------------------------------------------------- #
# Discovery source abstraction                                                #
# --------------------------------------------------------------------------- #

class BalancerV2PoolSource(Protocol):
    async def find_pools(self, chain: str, token_a: str,
                         token_b: str) -> DiscoverySourceResult:
        ...


class SubgraphBalancerV2PoolSource:
    """Balancer V2 subgraph-backed candidate source.

    Configuration is EXPLICIT and env-driven — no endpoint or credential is
    hardcoded:

    * per-chain URL: ``ARBICORE_BALANCER_SUBGRAPH_URL_<CHAIN>``
    * optional bearer key: ``ARBICORE_BALANCER_SUBGRAPH_API_KEY``

    Fail-closed: a chain with no configured URL, a transport error, a non-200
    response, or a malformed body yields an explicit unavailable/malformed
    status (never a fabricated pool, never silent zero). Returned data is
    CANDIDATE-ONLY and must still pass on-chain P0 validation downstream.
    """

    source_name = "balancer_v2_subgraph"

    def __init__(self, *, url_by_chain: Optional[Dict[str, str]] = None,
                 api_key: Optional[str] = None, http_post: Optional[Any] = None,
                 timeout_s: float = 8.0, limit: int = 25):
        self._explicit_urls = url_by_chain
        self._explicit_key = api_key
        self._http_post = http_post      # async (url, payload_json, headers) -> (status, obj)
        self._timeout_s = timeout_s
        self._limit = int(limit)

    def _url_for(self, chain: str) -> Optional[str]:
        if self._explicit_urls is not None:
            return self._explicit_urls.get(chain)
        return os.environ.get(f"ARBICORE_BALANCER_SUBGRAPH_URL_{chain.upper()}")

    def _api_key(self) -> Optional[str]:
        if self._explicit_key is not None:
            return self._explicit_key
        return os.environ.get("ARBICORE_BALANCER_SUBGRAPH_API_KEY")

    async def _default_http_post(self, url, payload, headers):
        import httpx
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.post(url, json=payload, headers=headers)
            try:
                obj = resp.json()
            except Exception:  # noqa: BLE001
                obj = None
            return resp.status_code, obj

    async def find_pools(self, chain: str, token_a: str,
                         token_b: str) -> DiscoverySourceResult:
        c = (chain or "").strip().lower()
        if c not in BALANCER_V2_VAULT_BY_CHAIN:
            return DiscoverySourceResult(SRC_UNSUPPORTED_CHAIN, source_name=self.source_name,
                                         error=f"Balancer V2 not on chain '{chain}'")
        url = self._url_for(c)
        if not url:
            return DiscoverySourceResult(
                SRC_DISCOVERY_UNAVAILABLE, source_name=self.source_name,
                error=f"no subgraph URL configured for chain '{c}' "
                      f"(ARBICORE_BALANCER_SUBGRAPH_URL_{c.upper()})")

        ta, tb = token_a.lower(), token_b.lower()
        query = (
            "query($t:[String!]){pools(first:%d,where:{tokensList_contains:$t,"
            "poolType_not_in:[\"Element\",\"AaveLinear\",\"Linear\"]}){id address}}" % self._limit
        )
        payload = {"query": query, "variables": {"t": [ta, tb]}}
        headers = {"Content-Type": "application/json"}
        key = self._api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"

        poster = self._http_post or self._default_http_post
        try:
            status_code, obj = await poster(url, payload, headers)
        except Exception as exc:  # noqa: BLE001 — transport fails closed
            return DiscoverySourceResult(SRC_DISCOVERY_UNAVAILABLE, source_name=self.source_name,
                                         error=f"{type(exc).__name__}: {exc}")
        if status_code != 200:
            return DiscoverySourceResult(SRC_DISCOVERY_UNAVAILABLE, source_name=self.source_name,
                                         error=f"subgraph HTTP {status_code}")
        if not isinstance(obj, dict) or "data" not in obj or obj.get("errors"):
            return DiscoverySourceResult(SRC_MALFORMED, source_name=self.source_name,
                                         error="subgraph body missing 'data' or contains 'errors'")
        pools = (obj.get("data") or {}).get("pools")
        if pools is None or not isinstance(pools, list):
            return DiscoverySourceResult(SRC_MALFORMED, source_name=self.source_name,
                                         error="subgraph 'data.pools' missing / not a list")
        candidates: List[PoolCandidate] = []
        for p in pools:
            if not isinstance(p, dict):
                continue
            candidates.append(PoolCandidate(
                chain=c, pool_id=p.get("id"), pool_address=p.get("address"),
                source=self.source_name, raw=p))
        return DiscoverySourceResult(
            SRC_OK, candidates=candidates, source_name=self.source_name,
            provenance={"url_configured": True, "query_tokens": [ta, tb],
                        "returned": len(candidates)})


# --------------------------------------------------------------------------- #
# Enumeration + quoting (reuses P0 for every on-chain step)                    #
# --------------------------------------------------------------------------- #

_SRC_TO_ENUM = {
    SRC_UNSUPPORTED_CHAIN: ENUM_UNSUPPORTED_CHAIN,
    SRC_DISCOVERY_UNAVAILABLE: ENUM_DISCOVERY_UNAVAILABLE,
    SRC_MALFORMED: ENUM_MALFORMED_DISCOVERY,
}


async def enumerate_and_quote(
    source: BalancerV2PoolSource, eth_call_fn: EthCallFn, chain: str,
    token_in: str, token_out: str, amount_in_wei: int, *,
    current_block: Optional[int] = None, max_age_blocks: Optional[int] = None,
    max_candidates: Optional[int] = None,
) -> EnumerationResult:
    """Discover Balancer V2 candidate pools for the pair, validate every
    candidate on-chain via the frozen P0 path, and return the ranked list of
    valid exact-size quote candidates. Fail-closed throughout."""
    c = (chain or "").strip().lower()
    base = dict(chain=c, token_in=token_in, token_out=token_out,
                amount_in_wei=int(amount_in_wei))

    vault = BALANCER_V2_VAULT_BY_CHAIN.get(c)
    if not vault:
        return EnumerationResult(ENUM_UNSUPPORTED_CHAIN, source_name="n/a",
                                 error=f"Balancer V2 not deployed on chain '{chain}'", **base)

    src = await source.find_pools(c, token_in, token_out)
    if src.status != SRC_OK:
        return EnumerationResult(
            _SRC_TO_ENUM.get(src.status, ENUM_MALFORMED_DISCOVERY),
            source_name=src.source_name, error=src.error,
            discovery_provenance=src.provenance, **base)

    # Dedupe candidates by identity, preserving discovery order.
    seen: set = set()
    ordered: List[PoolCandidate] = []
    for cand in src.candidates:
        key = cand.identity_key()
        if key is None:
            ordered.append(cand)   # no identity → will be rejected below (auditable)
            continue
        if key in seen:
            continue
        seen.add(key)
        ordered.append(cand)

    if max_candidates is not None:
        ordered = ordered[: int(max_candidates)]

    valid: List[EnumeratedQuote] = []
    rejected: List[RejectedCandidate] = []
    for cand in ordered:
        if not (cand.pool_id or cand.pool_address):
            rejected.append(RejectedCandidate(cand, MISSING_POOL_IDENTITY,
                                               "candidate has no pool_id or pool_address"))
            continue
        if cand.declared_vault:
            try:
                declared = to_checksum_address(cand.declared_vault)
            except Exception:  # noqa: BLE001
                declared = None
            if declared != vault:
                rejected.append(RejectedCandidate(
                    cand, WRONG_VAULT,
                    "candidate vault does not match the canonical Balancer V2 Vault"))
                continue
        # Authoritative on-chain re-validation + quote — the SAME P0 path.
        q = await discover_and_quote(
            eth_call_fn, c, token_in, token_out, int(amount_in_wei),
            pool_id=cand.pool_id, pool_address=cand.pool_address,
            current_block=current_block, max_age_blocks=max_age_blocks)
        if q.status == P0_OK:
            valid.append(EnumeratedQuote(cand, q))
        else:
            rejected.append(RejectedCandidate(cand, q.status, q.error))

    # Deterministic ranking: best output first, tie-break on pool address.
    valid.sort(key=lambda e: (-int(e.quote.amount_out_wei),
                              (e.quote.meta.pool_address if e.quote.meta else "")))

    return EnumerationResult(
        ENUM_OK, source_name=src.source_name, quotes=valid, rejected=rejected,
        discovery_provenance=src.provenance, **base)
