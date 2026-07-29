"""HeliusLaunchVenueProvider — reference implementation (D-4 hotfix wave).

This module is a **reference** ``LaunchVenueProvider`` implementation for the
``LaunchOpportunityVerifier``. It is purely additive: it does NOT alter the
verifier, the orchestrator, the gates, the economics, or any invariant.

Wiring posture:
  - The orchestrator continues to default to ``_noop_venue_provider``.
  - When ``HELIUS_API_KEY`` is provisioned, ``composition.py`` may opt in to
    construct this provider and call ``scanner.set_venue_provider(provider)``.
  - The scanner state remains ``enabled=False`` until the operator flips it
    via ``POST /scanners/launch_arb/resume``. Wiring this provider does NOT
    auto-enable the scanner.

What this provider does (REAL on-chain reads — INV-3 ``helius_token_rpc``):
  1. ``getAccountInfo(mint, encoding=jsonParsed)`` →
     ``mintAuthority`` (null → revoked), ``freezeAuthority`` (null → revoked),
     ``supply``, ``decimals``.
  2. ``getTokenLargestAccounts(mint)`` → top-20 holder addresses+balances,
     consumed by ``HolderAnalytics`` for ``top_10_concentration_pct``.
  3. DexScreener ``/tokens/v1/solana/{mint}`` → best pool by USD liquidity,
     yields ``primary_venue_id``, ``secondary_venue_id``, ``listing_price_usd``,
     ``liquidity_usd``, ``launchpad``, ``age_hours``.

D-4 Hotfix Wave (June 2026) — production-grade hardening added on top:
  - LP burn / lock percentage: pump.fun graduation flag (``complete=True`` →
    100% protocol-locked) + Solana incinerator balance check for any
    operator-supplied ``lp_mint`` hint. Pre-graduation pump.fun tokens
    return ``100.0`` because their LP cannot yet exist (bonding-curve
    custodial). Tokens without a known LP mint AND not on pump.fun fall
    back to ``0.0`` (fail-closed — operator must supply ``lp_mint`` or
    lower the gate threshold).
  - Pump.fun bonding-curve progress: authoritative read against the
    pump.fun coin API (``/coins/{mint}``). Returns the live
    ``bonding_curve_progress_pct`` derived from ``usd_market_cap`` / 690.0
    (matches the existing pump.fun discovery source mechanic).
  - Wallet profiles: operator-injectable ``wallet_profile_loader``
    callable. Reuses the D-4.2 ``WalletEnrichmentOrchestrator`` cache when
    wired by composition.
  - Outcome history: operator-injectable ``outcome_history_loader``
    callable. Reuses ``OutcomeRepository.list_for_subject`` when wired.
  - Helius RPC hardening: jittered exponential backoff over ``429`` and
    ``5xx`` responses, ``DEFAULT_RETRY_MAX_ATTEMPTS`` (3) attempts, plus a
    per-mint TTL cache (``DEFAULT_TTL_CACHE_S`` 60s) to deduplicate hot
    reads across the scanner's tick interval.

INV-1: This provider returns a dict — never a ``CanonicalOpportunity``.
INV-2: This provider does NOT call EmissionBus.
INV-3: ``source_id = "helius_token_rpc"`` (REAL) is hard-coded so the
       universal ``derive_provenance(legs)`` substrate yields
       ``DataProvenance.REAL``, never aggregator HINT.

The provider is purely read-only. No signing, no execution, no state
mutation outside the per-call retry-cache.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import (
    Any, Awaitable, Callable, Dict, List, Optional, Tuple,
)

import httpx

from ...models.discovery import DiscoveryCandidate
# D-4 hotfix-2: HTTP retry / TTL cache substrate promoted to a universal
# helper module so D-5 (and any future scanner) can consume it without
# duplicating the logic. Behaviourally identical to the hotfix-1 inline
# implementation; this is a pure DRY refactor.
from ..http_retry import (
    DEFAULT_RETRY_INITIAL_BACKOFF_S, DEFAULT_RETRY_MAX_ATTEMPTS,
    DEFAULT_RETRY_MAX_BACKOFF_S, DEFAULT_TIMEOUT_S, DEFAULT_TTL_CACHE_S,
    RETRYABLE_STATUS_CODES, RetryConfig, TTLCache, post_json_with_retry,
    sleep_with_jitter,
)

HELIUS_RPC_URL_FMT = "https://mainnet.helius-rpc.com/?api-key={key}"
DEXSCREENER_TOKEN_URL_FMT = "https://api.dexscreener.com/tokens/v1/solana/{mint}"

DEFAULT_PRIMARY_FEE_BPS = 100      # pumpfun ~1%; raydium ~0.25%; operator-tunable
DEFAULT_SECONDARY_FEE_BPS = 25
DEFAULT_NOTIONAL_USD = 250.0

# ── D-4 hotfix-2: retry/cache constants now sourced from http_retry ──
# (re-exported here so existing test imports keep working unchanged)
__all__ = [
    "HeliusLaunchVenueProvider",
    "RETRYABLE_STATUS_CODES", "SOLANA_INCINERATOR",
    "PUMPFUN_GRADUATION_MARKET_CAP_USD",
    "DEFAULT_RETRY_MAX_ATTEMPTS", "DEFAULT_RETRY_INITIAL_BACKOFF_S",
    "DEFAULT_RETRY_MAX_BACKOFF_S", "DEFAULT_TTL_CACHE_S",
    "WalletProfileLoader", "OutcomeHistoryLoader",
]

SOLANA_INCINERATOR = "1nc1nerator11111111111111111111111111111111"

# pump.fun authoritative coin state endpoints (mirrored across hosts).
PUMPFUN_COIN_URL_TEMPLATES = (
    "https://frontend-api-v3.pump.fun/coins/{mint}",
)
# pump.fun graduates to Raydium at ~$69k USD market cap.
PUMPFUN_GRADUATION_MARKET_CAP_USD = 69_000.0

# Optional operator-injected substrate hooks
WalletProfileLoader = Callable[[List[str]],
                                Awaitable[Dict[str, Dict[str, Any]]]]
OutcomeHistoryLoader = Callable[[str], Awaitable[List[Dict[str, Any]]]]


class HeliusLaunchVenueProvider:
    """Reference ``LaunchVenueProvider``.

    Reads Helius RPC + DexScreener + pump.fun and projects to the verifier's
    ``facts`` dict. Returns ``None`` (→ ``denied:venue_unreadable``) only
    when ``HELIUS_API_KEY`` is absent OR the mint account does not exist
    OR critical reads exhaust their retry budget.

    All non-critical gaps degrade to conservative defaults that make the
    gates fail-closed rather than false-positive confirm. The hotfix wave
    significantly narrows the set of "default" code paths — LP-burn and
    bonding-curve progress are now real for pump.fun and incinerator-
    detectable for tokens with known LP mints.
    """

    source_id = "helius_token_rpc"   # INV-3 — REAL classification

    def __init__(
        self,
        *,
        helius_api_key: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        default_primary_fee_bps: int = DEFAULT_PRIMARY_FEE_BPS,
        default_secondary_fee_bps: int = DEFAULT_SECONDARY_FEE_BPS,
        default_notional_usd: float = DEFAULT_NOTIONAL_USD,
        retry_max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS,
        retry_initial_backoff_s: float = DEFAULT_RETRY_INITIAL_BACKOFF_S,
        retry_max_backoff_s: float = DEFAULT_RETRY_MAX_BACKOFF_S,
        ttl_cache_s: float = DEFAULT_TTL_CACHE_S,
        wallet_profile_loader: Optional[WalletProfileLoader] = None,
        outcome_history_loader: Optional[OutcomeHistoryLoader] = None,
    ) -> None:
        self._key = helius_api_key or os.environ.get(
            "HELIUS_API_KEY", "").strip()
        self._client = http_client or httpx.AsyncClient(timeout=timeout_s)
        self._owns_client = http_client is None
        self._primary_fee_bps = default_primary_fee_bps
        self._secondary_fee_bps = default_secondary_fee_bps
        self._default_notional_usd = default_notional_usd
        self._rpc_url = (
            HELIUS_RPC_URL_FMT.format(key=self._key) if self._key else "")

        # D-4 hotfix-2: retry/backoff config now lives in the universal
        # substrate (arbicore/scanners/http_retry.py). Behaviour unchanged.
        self._retry_config = RetryConfig.from_kwargs(
            retry_max_attempts=retry_max_attempts,
            retry_initial_backoff_s=retry_initial_backoff_s,
            retry_max_backoff_s=retry_max_backoff_s,
        )
        # D-4 hotfix-2: per-mint TTL cache is now a TTLCache instance from
        # the universal substrate. Cache semantics unchanged.
        self._cache = TTLCache(ttl_s=ttl_cache_s)

        # D-4 hotfix wave — operator substrate hooks
        self._wallet_profile_loader = wallet_profile_loader
        self._outcome_history_loader = outcome_history_loader

    @property
    def credentials_available(self) -> bool:
        return bool(self._key)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ----- protocol entrypoint --------------------------------------------

    async def __call__(self, candidate: DiscoveryCandidate,
                       ) -> Optional[Dict[str, Any]]:
        if not self.credentials_available:
            return None
        mint = self._extract_mint(candidate)
        if not mint:
            return None

        # ---- 1. Helius mint state (CRITICAL — failure → None) -------------
        mint_state = await self._rpc_get_mint_state(mint)
        if mint_state is None:
            return None

        # ---- 2. Helius largest holders (best-effort; default empty) -------
        holders = await self._rpc_get_largest_holders(mint)

        # ---- 3. DexScreener pool/price/liquidity (best-effort) ------------
        pool = await self._dexscreener_best_pool(mint)
        primary_venue_id, secondary_venue_id, launchpad = self._build_venues(
            mint, pool)
        chain = "solana"

        listing_price_usd = (
            float(pool["priceUsd"]) if pool and pool.get("priceUsd")
            else None
        )
        liquidity_usd = (
            float(pool["liquidity"]["usd"]) if pool
            and pool.get("liquidity", {}).get("usd") is not None
            else 0.0
        )
        age_hours = self._derive_age_hours(pool)
        volume_h24 = (
            float(pool["volume"]["h24"]) if pool
            and pool.get("volume", {}).get("h24") is not None
            else 0.0
        )
        price_change_24h = (
            float(pool["priceChange"]["h24"]) if pool
            and pool.get("priceChange", {}).get("h24") is not None
            else 0.0
        )

        # ---- 4. D-4 HOTFIX: pump.fun authoritative coin state -------------
        pumpfun_state: Optional[Dict[str, Any]] = None
        hint_launchpad = (candidate.hint_metric or {}).get("launchpad")
        if hint_launchpad == "pumpfun" or launchpad == "pumpfun":
            pumpfun_state = await self._pumpfun_coin_state(mint)
            # Refine launchpad attribution if hint says pumpfun
            if not launchpad or launchpad == "unknown":
                launchpad = "pumpfun"

        # ---- 5. D-4 HOTFIX: bonding-curve progress ------------------------
        bonding_curve_progress_pct = self._derive_bonding_curve_progress(
            candidate, pumpfun_state)

        # ---- 6. D-4 HOTFIX: LP burn / lock detection ----------------------
        lp_burned_or_locked_pct = await self._detect_lp_burn(
            mint=mint,
            launchpad=launchpad,
            pumpfun_state=pumpfun_state,
            candidate=candidate,
        )

        # ---- 7. Carry forward hint-side signals from the candidate --------
        hint = candidate.hint_metric or {}
        buyer_wallets: List[str] = list(
            hint.get("buyer_wallets_sample") or hint.get("buyer_wallets")
            or []
        )
        signal_categories: List[str] = list(
            hint.get("signal_categories") or [])

        # ---- 8. D-4 HOTFIX: wallet enrichment cache pre-warm --------------
        wallet_profiles: Dict[str, Dict[str, Any]] = {}
        if buyer_wallets and self._wallet_profile_loader is not None:
            try:
                wallet_profiles = await self._wallet_profile_loader(
                    buyer_wallets) or {}
            except Exception:  # noqa: BLE001
                # Wallet enrichment is non-critical; on loader error degrade
                # to empty (the smart-money term in composite drops to 0
                # but confirmation can still happen via other terms).
                wallet_profiles = {}

        # ---- 9. D-4 HOTFIX: outcome history bootstrap ---------------------
        real_outcomes: List[Dict[str, Any]] = []
        if self._outcome_history_loader is not None:
            try:
                real_outcomes = await self._outcome_history_loader(
                    candidate.subject_id) or []
            except Exception:  # noqa: BLE001
                real_outcomes = []

        # ---- 10. Slippage estimate from notional/liquidity ratio ----------
        notional = self._default_notional_usd
        slip = self._estimate_slippage_pct(notional, liquidity_usd)

        # ---- 11. Token-intel block consumed by PhaseClassifier+Timeline ---
        # D-4 Hotfix-4 (Helius holder_count fact-projection fallback) —
        # `getTokenLargestAccounts` RPC returns only the top-N (≤ 20)
        # accounts, so ``len(holders)`` understates the true on-chain
        # holder count and unconditionally trips Gate-1's
        # ``holders < min`` denial (default ``min_holders=25``) on
        # otherwise healthy tokens. When the candidate's hint carries
        # an authoritative ``holder_count`` (sourced from Jupiter
        # DataAPI's on-chain ``base_asset.holderCount`` field at
        # ``sources.py:420``), and the Helius-side count is at the
        # API-cap sentinel (≤ 20), prefer the hint value.
        #
        # INV-3 preservation: this is a fact projection, not a soft
        # hint — the hint here is the authoritative on-chain holder
        # count from a different venue read (Jupiter DataAPI). Source
        # provenance (``source_id="helius_token_rpc"``) is unchanged
        # because the holders LIST itself (used for concentration
        # analysis) is still the Helius-sourced top-N. Only the count
        # term moves from known-underestimate to chain-authoritative.
        helius_holder_count = len(holders)
        hint_holder_count = int(hint.get("holder_count") or 0)
        if helius_holder_count <= 20 and hint_holder_count > helius_holder_count:
            holder_count = hint_holder_count
        else:
            holder_count = helius_holder_count
        token_intel = {
            "score": float(hint.get("score") or 0.0),
            "score_delta_24h": float(hint.get("score_delta_24h") or 0.0),
            "liquidity_usd": liquidity_usd,
            "volume_h24": volume_h24,
            "holders": holder_count,
            "age_hours": age_hours,
            "price_change_24h": price_change_24h,
            "launchpad_id": launchpad,
        }

        return {
            "primary_venue_id":           primary_venue_id,
            "secondary_venue_id":         secondary_venue_id,
            "chain":                      chain,
            "source_id":                  self.source_id,
            "listing_price_usd":          listing_price_usd,
            "liquidity_usd":              liquidity_usd,
            "primary_fee_bps":            self._primary_fee_bps,
            "secondary_fee_bps":          self._secondary_fee_bps,
            "slippage_primary_pct":       slip,
            "slippage_secondary_pct":     slip,
            "mint_authority_revoked":     mint_state["mint_authority_revoked"],
            "freeze_authority_revoked":   mint_state["freeze_authority_revoked"],
            "lp_burned_or_locked_pct":    lp_burned_or_locked_pct,
            "total_supply":               mint_state["supply"],
            "holders":                    holders,
            "launchpad":                  launchpad,
            "age_hours":                  age_hours,
            "buyer_wallets":              buyer_wallets,
            "wallet_profiles":            wallet_profiles,
            "signal_categories":          signal_categories,
            "real_outcomes":              real_outcomes,
            "synthetic_outcomes":         [],
            "token_intel":                token_intel,
            "signals":                    list(hint.get("signals") or []),
            "token_address":              mint,
            "verified_at_ts":             time.time(),
            "notional_usd":               notional,
            "bonding_curve_progress_pct": bonding_curve_progress_pct,
            "composite_score":            float(hint.get("composite_score") or 0.0),
            "confidence_score":           float(hint.get("confidence_score") or 0.0),
        }

    # ======================================================================
    # Internals — mint-extraction
    # ======================================================================

    @staticmethod
    def _extract_mint(candidate: DiscoveryCandidate) -> Optional[str]:
        sid = candidate.subject_id or ""
        if sid.startswith("solana:"):
            return sid.split(":", 1)[1] or None
        return (candidate.hint_metric or {}).get("token_mint") \
            or (candidate.hint_metric or {}).get("token_address")

    # ======================================================================
    # Internals — Helius RPC with retry/backoff + TTL cache
    # (D-4 hotfix-2: retry loop + cache now live in arbicore/scanners/
    #  http_retry.py — these methods are thin delegates so the rest of the
    #  provider's call sites can stay unchanged.)
    # ======================================================================

    def _cache_get(self, key: str) -> Tuple[bool, Any]:
        return self._cache.get(key)

    def _cache_set(self, key: str, value: Any) -> None:
        self._cache.set(key, value)

    async def _rpc_call(self, method: str, params: Any,
                        ) -> Optional[Dict[str, Any]]:
        """Helius JSON-RPC call. Delegates the retry/backoff loop to the
        universal ``post_json_with_retry`` helper and then unwraps the
        JSON-RPC envelope (``result``/``error`` keys).
        """
        body = {"jsonrpc": "2.0", "id": method,
                "method": method, "params": params}
        payload = await post_json_with_retry(
            self._client, self._rpc_url, body, config=self._retry_config)
        if not isinstance(payload, dict) or payload.get("error"):
            return None
        return payload.get("result")

    async def _sleep_with_jitter(self, base_s: float) -> None:
        """Retained for backward compat — delegates to the universal
        ``sleep_with_jitter`` helper."""
        await sleep_with_jitter(base_s)

    async def _rpc_get_mint_state(self, mint: str
                                   ) -> Optional[Dict[str, Any]]:
        """Parses ``getAccountInfo`` (jsonParsed) for an SPL mint.

        Returns ``{mint_authority_revoked, freeze_authority_revoked, supply,
        decimals}`` or ``None`` on failure / non-mint account. Per-mint TTL
        cached.
        """
        cache_key = f"mint_state:{mint}"
        hit, value = self._cache_get(cache_key)
        if hit:
            return value
        result = await self._rpc_call(
            "getAccountInfo",
            [mint, {"encoding": "jsonParsed", "commitment": "confirmed"}],
        )
        if not result:
            return None
        value = result.get("value")
        if not value:
            return None
        parsed = (((value or {}).get("data") or {}).get("parsed") or {})
        if parsed.get("type") != "mint":
            return None
        info = parsed.get("info") or {}
        try:
            supply_str = info.get("supply") or "0"
            decimals = int(info.get("decimals") or 0)
            supply = float(supply_str) / (10 ** decimals) if decimals \
                else float(supply_str)
        except (TypeError, ValueError):
            supply = 0.0
        out = {
            "mint_authority_revoked":   info.get("mintAuthority") is None,
            "freeze_authority_revoked": info.get("freezeAuthority") is None,
            "supply":                   supply,
            "decimals":                 int(info.get("decimals") or 0),
        }
        self._cache_set(cache_key, out)
        return out

    async def _rpc_get_largest_holders(self, mint: str
                                        ) -> List[Dict[str, Any]]:
        """``getTokenLargestAccounts`` → top-20 entries. TTL-cached."""
        cache_key = f"largest_holders:{mint}"
        hit, value = self._cache_get(cache_key)
        if hit:
            return value
        result = await self._rpc_call(
            "getTokenLargestAccounts",
            [mint, {"commitment": "confirmed"}],
        )
        if not result:
            return []
        value = result.get("value") or []
        out: List[Dict[str, Any]] = []
        now = time.time()
        for row in value:
            try:
                addr = (row.get("address") or "").strip()
                if not addr:
                    continue
                amount_str = row.get("amount") or "0"
                ui = row.get("uiAmount")
                bal = float(ui) if ui is not None else float(amount_str)
                out.append({
                    "address":      addr,
                    "balance":      bal,
                    "last_seen_ts": now,
                })
            except (TypeError, ValueError):
                continue
        self._cache_set(cache_key, out)
        return out

    async def _rpc_get_token_supply(self, mint: str) -> Optional[float]:
        """``getTokenSupply`` → uiAmount as float. Used by LP-burn detection."""
        cache_key = f"supply:{mint}"
        hit, value = self._cache_get(cache_key)
        if hit:
            return value
        result = await self._rpc_call(
            "getTokenSupply",
            [mint, {"commitment": "confirmed"}],
        )
        if not result:
            return None
        value = result.get("value") or {}
        try:
            ui = value.get("uiAmount")
            if ui is not None:
                out = float(ui)
            else:
                out = float(value.get("amount") or 0.0)
        except (TypeError, ValueError):
            return None
        self._cache_set(cache_key, out)
        return out

    async def _rpc_get_largest_holder_balance_for_owner(
            self, mint: str, owner: str) -> float:
        """Sum of ``mint`` holdings held by ``owner``. Walks
        ``getTokenLargestAccounts`` (top-20) and uses the account-owner
        substring projection that ``getTokenLargestAccounts`` returns; for
        ``mint`` LP tokens this is sufficient because the incinerator always
        holds 100% in a single ATA when burns happen.
        """
        # The Helius getTokenAccountsByOwner approach is the precise tool,
        # but it requires an additional round-trip. For LP burn checks
        # against the incinerator we instead iterate the top-20 holders and
        # match by *account address* if the largest accounts list includes
        # owner-account pairs (which it does for `getTokenLargestAccounts`
        # encoded with jsonParsed=False — we use the parsed form).
        accts = await self._rpc_call(
            "getTokenAccountsByOwner",
            [owner, {"mint": mint},
             {"encoding": "jsonParsed", "commitment": "confirmed"}],
        )
        if not accts:
            return 0.0
        rows = accts.get("value") or []
        total = 0.0
        for r in rows:
            try:
                info = (((r or {}).get("account") or {}).get("data") or {})\
                    .get("parsed", {}).get("info", {})
                ta = info.get("tokenAmount") or {}
                ui = ta.get("uiAmount")
                total += float(ui) if ui is not None else 0.0
            except (TypeError, ValueError):
                continue
        return total

    # ======================================================================
    # Internals — DexScreener (best-effort)
    # ======================================================================

    async def _dexscreener_best_pool(self, mint: str
                                      ) -> Optional[Dict[str, Any]]:
        cache_key = f"dexs:{mint}"
        hit, value = self._cache_get(cache_key)
        if hit:
            return value
        try:
            resp = await self._client.get(
                DEXSCREENER_TOKEN_URL_FMT.format(mint=mint))
            if resp.status_code != 200:
                return None
            payload = resp.json()
        except (httpx.HTTPError, ValueError):
            return None
        if isinstance(payload, list):
            pairs = payload
        elif isinstance(payload, dict):
            pairs = payload.get("pairs") or []
        else:
            self._cache_set(cache_key, None)
            return None
        if not pairs:
            self._cache_set(cache_key, None)
            return None
        def _liq(p: Dict[str, Any]) -> float:
            try:
                return float(((p or {}).get("liquidity") or {})
                               .get("usd") or 0.0)
            except (TypeError, ValueError):
                return 0.0
        pairs.sort(key=_liq, reverse=True)
        self._cache_set(cache_key, pairs[0])
        return pairs[0]

    # ======================================================================
    # D-4 HOTFIX — pump.fun authoritative coin state
    # ======================================================================

    async def _pumpfun_coin_state(self, mint: str
                                   ) -> Optional[Dict[str, Any]]:
        """Read ``/coins/{mint}`` against the pump.fun frontend-api.

        Returns the raw coin dict (``complete``, ``usd_market_cap``,
        ``virtual_sol_reserves``, ``real_sol_reserves`` …) or ``None`` on
        any HTTP failure across all mirror hosts.
        """
        cache_key = f"pumpfun_coin:{mint}"
        hit, value = self._cache_get(cache_key)
        if hit:
            return value
        for tmpl in PUMPFUN_COIN_URL_TEMPLATES:
            try:
                resp = await self._client.get(tmpl.format(mint=mint))
            except httpx.HTTPError:
                continue
            if resp.status_code != 200:
                continue
            try:
                data = resp.json()
            except ValueError:
                continue
            if isinstance(data, dict):
                self._cache_set(cache_key, data)
                return data
        self._cache_set(cache_key, None)
        return None

    @staticmethod
    def _derive_bonding_curve_progress(
            candidate: DiscoveryCandidate,
            pumpfun_state: Optional[Dict[str, Any]],
    ) -> Optional[float]:
        """Live pump.fun progress takes precedence over hint metadata."""
        if pumpfun_state:
            if pumpfun_state.get("complete"):
                return 100.0
            mc = pumpfun_state.get("usd_market_cap")
            try:
                if mc is not None:
                    return min(100.0,
                                float(mc) / (PUMPFUN_GRADUATION_MARKET_CAP_USD
                                              / 100.0))
            except (TypeError, ValueError):
                pass
        hint = candidate.hint_metric or {}
        hp = hint.get("bonding_curve_progress_pct")
        if hp is not None:
            try:
                return float(hp)
            except (TypeError, ValueError):
                pass
        return None

    # ======================================================================
    # D-4 HOTFIX — LP burn / lock detection
    # ======================================================================

    async def _detect_lp_burn(
            self, *, mint: str, launchpad: str,
            pumpfun_state: Optional[Dict[str, Any]],
            candidate: DiscoveryCandidate,
    ) -> float:
        """Returns ``lp_burned_or_locked_pct`` in 0..100.

        Decision tree:
          1. pump.fun graduated (``complete=True``) → 100.0 (LP auto-burned
             by pump.fun's smart contract at graduation).
          2. pump.fun pre-graduation → 100.0 (LP doesn't exist yet; the
             bonding curve is protocol-custodial — operationally
             zero-rug-vector for LP withdrawal).
          3. Operator-supplied ``hint_metric.lp_mint`` → real
             ``getTokenSupply`` + incinerator balance check.
          4. Otherwise → 0.0 (fail-closed; operator must supply ``lp_mint``
             or lower ``rug_gate.min_lp_burned_or_locked_pct``).
        """
        # Case 1+2 — pump.fun special case
        if pumpfun_state is not None or launchpad == "pumpfun":
            if pumpfun_state and pumpfun_state.get("complete"):
                return 100.0
            # Pre-graduation: LP doesn't exist yet — protocol-custodial.
            if pumpfun_state is not None:
                return 100.0
            # If pumpfun_state is None (API unreachable) but launchpad
            # attribution says pumpfun, we can't confirm graduation status;
            # fall through to lp_mint hint path or fail-closed.

        # Case 3 — explicit LP mint hint
        hint = candidate.hint_metric or {}
        lp_mint = (hint.get("lp_mint") or "").strip()
        if lp_mint:
            return await self._incinerator_burned_pct(lp_mint)

        # Case 4 — fail-closed
        return 0.0

    async def _incinerator_burned_pct(self, lp_mint: str) -> float:
        """Compute burn % from ``getTokenSupply`` (LP mint total supply) +
        incinerator-owned balance for that mint.

        Burn % = 100 * incinerator_balance / total_supply, bounded [0, 100].
        Returns 0.0 if any read fails (fail-closed).
        """
        total = await self._rpc_get_token_supply(lp_mint)
        if not total or total <= 0:
            return 0.0
        burned = await self._rpc_get_largest_holder_balance_for_owner(
            mint=lp_mint, owner=SOLANA_INCINERATOR)
        if burned <= 0:
            return 0.0
        pct = 100.0 * burned / total
        return float(max(0.0, min(100.0, pct)))

    # ======================================================================
    # Internals — venue ID composition, slippage, age
    # ======================================================================

    @staticmethod
    def _build_venues(mint: str, pool: Optional[Dict[str, Any]]
                       ) -> tuple[str, str, str]:
        if not pool:
            return (
                f"unknown:solana:{mint}",
                f"unknown:solana:{mint}_alt",
                "unknown",
            )
        dex_id = (pool.get("dexId") or "unknown").lower()
        pair_addr = pool.get("pairAddress") or mint
        sec = f"{dex_id}_secondary:solana:{mint}"
        return f"{dex_id}:solana:{pair_addr}", sec, dex_id

    @staticmethod
    def _derive_age_hours(pool: Optional[Dict[str, Any]]) -> float:
        if not pool:
            return 0.0
        try:
            ms = float(pool.get("pairCreatedAt") or 0)
        except (TypeError, ValueError):
            return 0.0
        if ms <= 0:
            return 0.0
        now_ms = time.time() * 1000.0
        return max(0.0, (now_ms - ms) / 3_600_000.0)

    @staticmethod
    def _estimate_slippage_pct(notional_usd: float,
                                liquidity_usd: float) -> float:
        if liquidity_usd <= 0:
            return 10.0
        slip = 50.0 * notional_usd / liquidity_usd
        return float(min(max(slip, 0.0), 10.0))
