"""TransferModelProvider Protocol + LiFiTransferProvider reference impl.

The transfer provider is the equivalent of D-4's ``LaunchVenueProvider``:
it owns all live HTTP I/O against bridge APIs and returns a normalised
``facts`` dict that the verifier folds into LegEvidence + canonical
metadata.

Reuses the universal ``arbicore/scanners/http_retry.py`` substrate for
retry/backoff + TTL cache (zero behaviour change vs D-4 hotfix wave).

INV-1: returns a dict; never a CanonicalOpportunity.
INV-2: never calls EmissionBus.
INV-3: ``source_id`` returned in the facts dict is one of
       ``lifi_quote_real`` or ``stargate_quote_real`` (REAL provenance).
"""
from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, Dict, Optional, Protocol

import httpx

from ...models.discovery import DiscoveryCandidate
from ..http_retry import (
    DEFAULT_RETRY_INITIAL_BACKOFF_S, DEFAULT_RETRY_MAX_ATTEMPTS,
    DEFAULT_RETRY_MAX_BACKOFF_S, DEFAULT_TIMEOUT_S, DEFAULT_TTL_CACHE_S,
    RetryConfig, TTLCache, get_json_with_retry, post_json_with_retry,
)


# ============================================================================
# Protocol — verifier-facing transfer model surface
# ============================================================================

class TransferModelProvider(Protocol):
    """Read-only authoritative provider. Returns a dict shaped as::

        {
            "bridge": str,                       # 'lifi' | 'stargate'
            "source_chain": str,
            "destination_chain": str,
            "asset": str,
            "primary_venue_id": str,             # 'lifi:<src>:<asset>'
            "secondary_venue_id": str,           # 'lifi:<dst>:<asset>'
            "source_id": str,                    # REAL source_id for INV-3
            "expected_out_amount": float,        # decimal units of asset
            "expected_out_amount_usd": float,
            "slippage_bridge_pct": float,
            "transfer_modelling_confidence": float,  # 0..1
            "primary_fee_bps": int,
            "secondary_fee_bps": int,
            "total_bridge_fee_usd": float,
            "inbound_latency_p50_s": float,
            "inbound_latency_p95_s": float,
            "quote_source": str,                  # endpoint or 'cache'
            "verified_at_ts": float,
        }
    """

    async def __call__(self,
                       candidate: DiscoveryCandidate,
                       ) -> Optional[Dict[str, Any]]:
        ...


async def noop_transfer_provider(
        candidate: DiscoveryCandidate,
        ) -> Optional[Dict[str, Any]]:
    """Cold-start provider — verifier ends as ``denied:venue_unreadable``."""
    return None


# ============================================================================
# LiFiTransferProvider — reference implementation
# ============================================================================

# Chain → LI.FI chain identifier. LI.FI uses chain IDs for EVM and 'SOL'
# for Solana per its public API.
_LIFI_CHAIN_ID = {
    "ethereum": 1, "arbitrum": 42161, "base": 8453,
    "optimism": 10, "polygon": 137, "solana": "SOL",
}

# Token decimals — minimal subset to convert decimal amounts correctly.
_ASSET_DECIMALS = {
    "USDC": 6, "USDT": 6, "WETH": 18, "ETH": 18, "WBTC": 8,
}

# --------------------------------------------------------------------------
# Read-only probe `fromAddress` for bridge /quote endpoints (Subset B fix).
#
# LI.FI's `/quote` validator hardened post-2025 and rejects a syntactically
# null/zero `fromAddress` with HTTP 400 (`Invalid fromAddress: must be a
# non-zero address`). The address is used by the aggregator ONLY for gas-
# cost estimation and approval-flow lookup — it never initiates a
# transaction and never appears on-chain. Any syntactically valid, non-zero
# address suffices for read-only quote probing.
#
# Operator override via env (preferred): `LIFI_PROBE_FROM_ADDRESS_EVM`,
# `LIFI_PROBE_FROM_ADDRESS_SOLANA`. Defaults below are well-known
# non-zero placeholders (EVM: the canonical "dead" burn address; Solana:
# the System Program ID — always exists, deterministic, never holds funds).
#
# INV-3 unaffected: this address is a routing input only. `source_id`
# remains `lifi_quote_real` / `stargate_quote_real`.
_DEFAULT_LIFI_PROBE_EVM = "0x000000000000000000000000000000000000dEaD"
_DEFAULT_LIFI_PROBE_SOLANA = "11111111111111111111111111111111"


def _resolve_probe_from_address(chain: str) -> str:
    """Resolve the read-only probe `fromAddress` for a source chain.

    Selects between EVM and Solana schemes based on the chain key and
    consults operator-supplied env overrides before falling back to the
    documented non-zero defaults above.
    """
    if (chain or "").lower() == "solana":
        return (os.environ.get("LIFI_PROBE_FROM_ADDRESS_SOLANA", "").strip()
                or _DEFAULT_LIFI_PROBE_SOLANA)
    return (os.environ.get("LIFI_PROBE_FROM_ADDRESS_EVM", "").strip()
            or _DEFAULT_LIFI_PROBE_EVM)


class LiFiTransferProvider:
    """Reference LI.FI bridge quote provider.

    Read-only. Uses the universal http_retry substrate. Per-corridor
    TTL cache reduces hot-path duplicate calls.

    Constructor parameters are operator-tunable via composition.py / 
    scanner_config.cross_chain_arb.http_retry.
    """

    def __init__(
        self,
        *,
        http_client: Optional[httpx.AsyncClient] = None,
        retry_config: Optional[RetryConfig] = None,
        ttl_cache_s: float = DEFAULT_TTL_CACHE_S,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        base_url: str = "https://li.quest/v1",
        api_key_env_var: str = "LIFI_API_KEY",
        default_notional_usd: float = 1000.0,
    ) -> None:
        self._client = http_client or httpx.AsyncClient(timeout=timeout_s)
        self._owns_client = http_client is None
        self._retry = retry_config or RetryConfig()
        self._cache = TTLCache(ttl_s=ttl_cache_s)
        self._base_url = base_url.rstrip("/")
        self._api_key_env_var = api_key_env_var
        self._default_notional = float(default_notional_usd)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @property
    def cache(self) -> TTLCache:
        return self._cache

    async def __call__(self,
                       candidate: DiscoveryCandidate,
                       ) -> Optional[Dict[str, Any]]:
        hm = candidate.hint_metric or {}
        bridge = (hm.get("bridge") or "").lower()
        if bridge != "lifi":
            # Provider is bridge-specific. Wrong bridge → soft None.
            return None
        src = (hm.get("source_chain") or "").lower()
        dst = (hm.get("destination_chain") or "").lower()
        asset = (candidate.asset or "").upper()
        if not (src and dst and asset):
            return None
        if src not in _LIFI_CHAIN_ID or dst not in _LIFI_CHAIN_ID:
            return None
        cache_key = f"lifi:{src}→{dst}:{asset}:{self._default_notional}"
        hit, cached = self._cache.get(cache_key)
        if hit:
            return cached
        api_key = os.environ.get(self._api_key_env_var, "").strip()
        url = f"{self._base_url}/quote"
        # Subset C — LI.FI deprecated POST /v1/quote (404 in production);
        # the endpoint is now GET-only. Parameters move from a JSON body to
        # the query string but their names and semantics are unchanged.
        params: Dict[str, Any] = {
            "fromChain": _LIFI_CHAIN_ID[src],
            "toChain": _LIFI_CHAIN_ID[dst],
            "fromToken": asset,
            "toToken": asset,
            "fromAmount": _to_smallest_units(asset, self._default_notional),
            # Subset B — post-2025 LI.FI `/quote` validator rejects a
            # zero/null `fromAddress`. We supply a chain-aware non-zero
            # read-only probe address (operator-overridable via env).
            "fromAddress": _resolve_probe_from_address(src),
            "slippage": 0.005,
        }
        if api_key:
            self._client.headers["x-lifi-api-key"] = api_key
        payload = await get_json_with_retry(
            self._client, url, params=params, config=self._retry,
        )
        facts: Optional[Dict[str, Any]] = None
        if payload and isinstance(payload, dict):
            facts = _project_lifi_quote(
                payload, bridge=bridge, src_chain=src, dst_chain=dst,
                asset=asset, notional_usd=self._default_notional,
            )
        self._cache.set(cache_key, facts)
        return facts


def _to_smallest_units(asset: str, notional_usd: float) -> str:
    """Best-effort conversion to a `fromAmount` string the LI.FI quote
    endpoint expects. Stable-coin assets are assumed to be 1 USD; non-
    stables use a conservative spot ratio of 1 USD = 1 unit so the live
    quote can still resolve. The provider does not depend on the price
    being accurate — it consumes the LI.FI-returned out_amount."""
    decimals = _ASSET_DECIMALS.get(asset.upper(), 18)
    units = int(max(1.0, notional_usd) * (10 ** decimals))
    return str(units)


def _project_lifi_quote(payload: Dict[str, Any], *,
                         bridge: str, src_chain: str, dst_chain: str,
                         asset: str, notional_usd: float,
                         ) -> Dict[str, Any]:
    """Project a LI.FI quote response into the universal facts shape."""
    import time
    est = payload.get("estimate") or {}
    to_amt = est.get("toAmount") or "0"
    try:
        to_amt_dec = float(to_amt) / (10 ** _ASSET_DECIMALS.get(
            asset.upper(), 18))
    except (TypeError, ValueError):
        to_amt_dec = 0.0
    fee_costs = est.get("feeCosts") or []
    bridge_fee_usd = 0.0
    for fc in fee_costs:
        try:
            bridge_fee_usd += float(fc.get("amountUSD") or 0.0)
        except (TypeError, ValueError):
            continue
    gas_costs = est.get("gasCosts") or []
    gas_usd_src = 0.0
    gas_usd_dst = 0.0
    for gc in gas_costs:
        try:
            usd = float(gc.get("amountUSD") or 0.0)
        except (TypeError, ValueError):
            usd = 0.0
        if gc.get("type") == "SEND":
            gas_usd_src += usd
        else:
            gas_usd_dst += usd
    slip_pct = float(est.get("slippage") or 0.005) * 100.0
    out_usd = to_amt_dec   # stable-asset approximation
    return {
        "bridge": bridge,
        "source_chain": src_chain,
        "destination_chain": dst_chain,
        "asset": asset,
        "primary_venue_id": f"{bridge}:{src_chain}:{asset}",
        "secondary_venue_id": f"{bridge}:{dst_chain}:{asset}",
        "source_id": "lifi_quote_real",
        "expected_out_amount": to_amt_dec,
        "expected_out_amount_usd": out_usd,
        "slippage_bridge_pct": slip_pct,
        "transfer_modelling_confidence": 0.85,
        "primary_fee_bps": 5,
        "secondary_fee_bps": 5,
        "total_bridge_fee_usd": bridge_fee_usd,
        "gas_source_chain_usd": gas_usd_src or None,
        "gas_destination_chain_usd": gas_usd_dst or None,
        "inbound_latency_p50_s": float(est.get(
            "executionDuration") or 180.0),
        "inbound_latency_p95_s": float(est.get(
            "executionDuration") or 180.0) * 3.0,
        "quote_source": "lifi:/quote",
        "verified_at_ts": time.time(),
        "notional_usd": notional_usd,
    }



# ============================================================================
# StargateTransferProvider — D-5.2 completion (absorbed into existing module)
# ============================================================================

# Stargate v2 (LayerZero) chain IDs. Solana is intentionally absent —
# Stargate does not currently support it. ChainId mapping mirrors Stargate's
# own endpoint identifier scheme (EVM only) per their public v1 quote API.
_STARGATE_CHAIN_ID = {
    "ethereum": 30101, "arbitrum": 30110, "base": 30184,
    "optimism": 30111, "polygon": 30109,
}

# Stargate ships native USDC/USDT/ETH cross-chain. Other assets degrade
# gracefully to None.
_STARGATE_ASSETS = frozenset({"USDC", "USDT", "ETH", "WETH"})


class StargateTransferProvider:
    """Reference Stargate (LayerZero v2) bridge quote provider.

    Mirrors ``LiFiTransferProvider`` 1:1 — reuses ``http_retry`` substrate
    + ``TTLCache``. INV-3 ``source_id="stargate_quote_real"`` (REAL).

    Posture:
    - Read-only. Operator-attached only when ``STARGATE_API_KEY`` is set
      (composition opt-in mirrors LI.FI).
    - Wrong-bridge candidates returned as ``None`` (soft route to the
      LI.FI provider in dual-provider deployments).
    - Solana corridors returned as ``None`` (Stargate does not support).
    """

    def __init__(
        self,
        *,
        http_client: Optional[httpx.AsyncClient] = None,
        retry_config: Optional[RetryConfig] = None,
        ttl_cache_s: float = DEFAULT_TTL_CACHE_S,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        base_url: str = "https://stargate.finance/api/v1",
        api_key_env_var: str = "STARGATE_API_KEY",
        default_notional_usd: float = 1000.0,
    ) -> None:
        self._client = http_client or httpx.AsyncClient(timeout=timeout_s)
        self._owns_client = http_client is None
        self._retry = retry_config or RetryConfig()
        self._cache = TTLCache(ttl_s=ttl_cache_s)
        self._base_url = base_url.rstrip("/")
        self._api_key_env_var = api_key_env_var
        self._default_notional = float(default_notional_usd)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @property
    def cache(self) -> TTLCache:
        return self._cache

    async def __call__(self,
                       candidate: DiscoveryCandidate,
                       ) -> Optional[Dict[str, Any]]:
        hm = candidate.hint_metric or {}
        bridge = (hm.get("bridge") or "").lower()
        if bridge != "stargate":
            return None
        src = (hm.get("source_chain") or "").lower()
        dst = (hm.get("destination_chain") or "").lower()
        asset = (candidate.asset or "").upper()
        if not (src and dst and asset):
            return None
        if src not in _STARGATE_CHAIN_ID or dst not in _STARGATE_CHAIN_ID:
            return None
        if asset not in _STARGATE_ASSETS:
            return None
        cache_key = f"stargate:{src}→{dst}:{asset}:{self._default_notional}"
        hit, cached = self._cache.get(cache_key)
        if hit:
            return cached
        api_key = os.environ.get(self._api_key_env_var, "").strip()
        url = f"{self._base_url}/quotes"
        body: Dict[str, Any] = {
            "srcChainId":  _STARGATE_CHAIN_ID[src],
            "dstChainId":  _STARGATE_CHAIN_ID[dst],
            "srcToken":    asset,
            "dstToken":    asset,
            "srcAmount":   _to_smallest_units(asset, self._default_notional),
            # Subset B — symmetrical maintenance with LI.FI provider.
            # Stargate is currently dormant via `bridges.stargate.deprecated`
            # but we keep the body shape valid for any future un-deprecation.
            "fromAddress": _resolve_probe_from_address(src),
            "slippageBps": 50,
        }
        if api_key:
            self._client.headers["x-stargate-api-key"] = api_key
        payload = await post_json_with_retry(
            self._client, url, body, config=self._retry,
        )
        facts: Optional[Dict[str, Any]] = None
        if payload and isinstance(payload, dict):
            facts = _project_stargate_quote(
                payload, src_chain=src, dst_chain=dst,
                asset=asset, notional_usd=self._default_notional,
            )
        self._cache.set(cache_key, facts)
        return facts


def _project_stargate_quote(payload: Dict[str, Any], *,
                              src_chain: str, dst_chain: str,
                              asset: str, notional_usd: float,
                              ) -> Dict[str, Any]:
    """Project a Stargate quote response into the universal facts shape.

    Tolerant to multiple response shapes — Stargate's public quote API
    has evolved across v1/v2. We probe for the most stable fields and
    fall back to deterministic defaults derived from the BridgeRouteCatalog
    when projection partially fails (verifier then gates on those defaults
    via Gates 7/8/9).
    """
    import time
    # Best-effort field probe — handle both v1 and v2 quote shapes.
    quotes = payload.get("quotes") or payload.get("routes") or []
    if quotes and isinstance(quotes, list):
        q = quotes[0] or {}
    else:
        q = payload  # newer endpoints inline the top-level quote
    dst_amount = q.get("dstAmount") or q.get("toAmount") or "0"
    try:
        out_dec = float(dst_amount) / (10 ** _ASSET_DECIMALS.get(
            asset.upper(), 18))
    except (TypeError, ValueError):
        out_dec = 0.0
    bridge_fee_usd = 0.0
    for fee in (q.get("fees") or q.get("feeCosts") or []):
        try:
            bridge_fee_usd += float(fee.get("amountUSD") or 0.0)
        except (TypeError, ValueError):
            continue
    gas_usd_src = 0.0
    gas_usd_dst = 0.0
    for gc in (q.get("gasCosts") or []):
        try:
            usd = float(gc.get("amountUSD") or 0.0)
        except (TypeError, ValueError):
            usd = 0.0
        if (gc.get("type") or "").upper() == "SEND":
            gas_usd_src += usd
        else:
            gas_usd_dst += usd
    slip_pct = (float(q.get("slippageBps") or 50) / 100.0)
    duration = float(q.get("estimatedTime") or q.get("executionDuration")
                      or 60.0)
    return {
        "bridge": "stargate",
        "source_chain": src_chain,
        "destination_chain": dst_chain,
        "asset": asset,
        "primary_venue_id": f"stargate:{src_chain}:{asset}",
        "secondary_venue_id": f"stargate:{dst_chain}:{asset}",
        "source_id": "stargate_quote_real",
        "expected_out_amount": out_dec,
        "expected_out_amount_usd": out_dec,
        "slippage_bridge_pct": slip_pct,
        "transfer_modelling_confidence": 0.90,
        "primary_fee_bps": 5,
        "secondary_fee_bps": 5,
        "total_bridge_fee_usd": bridge_fee_usd,
        "gas_source_chain_usd": gas_usd_src or None,
        "gas_destination_chain_usd": gas_usd_dst or None,
        "inbound_latency_p50_s": duration,
        "inbound_latency_p95_s": duration * 7.0,
        "quote_source": "stargate:/quotes",
        "verified_at_ts": time.time(),
        "notional_usd": notional_usd,
    }
