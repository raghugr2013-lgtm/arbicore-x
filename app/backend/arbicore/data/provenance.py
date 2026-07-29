"""ArbiCore X — Data Provenance Layer (Phase B foundation).

Classifies every data source as VERIFIED_REAL / REAL / SIMULATED / CONTAMINATED / DEAD.

HARD RULE (P2): Only ``VERIFIED_REAL`` and ``REAL`` sources may influence
learning, confidence calibration, adaptive weighting, route success
statistics, or any future AI model. Use ``assert_learning_eligible`` /
``is_learning_eligible`` as the gate at every learning entry point.

Registry composition (Phase B locked baseline):
  - 11 REAL  : ArbiCore live production sources
  - 4  SIMULATED : synthetic / fixture / manual sources
  - 0  VERIFIED_REAL : promotion path lands in Phase D
  - Original ArbitrageX heritage entries are preserved for backwards
    compatibility with the existing test suite (41 Phase A tests).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Dict, List

from ..models.enums import LEARNING_ELIGIBLE_PROVENANCE, DataProvenance


@dataclass(frozen=True)
class SourceClassification:
    source: str
    provenance: DataProvenance
    reason: str

    @property
    def learning_eligible(self) -> bool:
        return self.provenance in LEARNING_ELIGIBLE_PROVENANCE


# ---------------------------------------------------------------------------
# Canonical source registry.
# Format: source-name -> SourceClassification(source, provenance, reason)
# ---------------------------------------------------------------------------
SOURCE_REGISTRY: Dict[str, SourceClassification] = {
    # ── ArbiCore-native REAL sources (Phase B: 11 entries) ────────────────
    "blockdag_rpc_primary": SourceClassification(
        "blockdag_rpc_primary", DataProvenance.REAL,
        "Primary BlockDAG JSON-RPC endpoint (rpc.bdagscan.com)",
    ),
    "bsc_rpc": SourceClassification(
        "bsc_rpc", DataProvenance.REAL,
        "Public BSC mainnet RPC — observer balance reads",
    ),
    "bscscan_api": SourceClassification(
        "bscscan_api", DataProvenance.REAL,
        "BSCScan REST API — tx history + balance auxiliary",
    ),
    "coinstore_public_depth": SourceClassification(
        "coinstore_public_depth", DataProvenance.REAL,
        "Coinstore public order-book endpoint",
    ),
    "azbit_public": SourceClassification(
        "azbit_public", DataProvenance.REAL,
        "Azbit public market-data API",
    ),
    "p2b_public": SourceClassification(
        "p2b_public", DataProvenance.REAL,
        "P2PB2B public market-data API",
    ),
    "pionex_public": SourceClassification(
        "pionex_public", DataProvenance.REAL,
        "Pionex public market-data API",
    ),
    "xt_public": SourceClassification(
        "xt_public", DataProvenance.REAL,
        "XT.com public market-data API",
    ),
    "quote_capture_batch": SourceClassification(
        "quote_capture_batch", DataProvenance.REAL,
        "ArbiCore userscript v2 multi-size verified-quote batch ingestion",
    ),
    "blockdag_live_swap_userscript": SourceClassification(
        "blockdag_live_swap_userscript", DataProvenance.REAL,
        "BlockDAG live-swap portal observed via Tampermonkey userscript",
    ),
    "metamask_observed_address": SourceClassification(
        "metamask_observed_address", DataProvenance.REAL,
        "Operator MetaMask address — read-only chain observation",
    ),

    # ── ArbiCore-native SIMULATED sources (Phase B: 4 entries) ────────────
    "manual_config_balance": SourceClassification(
        "manual_config_balance", DataProvenance.SIMULATED,
        "Operator-typed manual_available_balance_usd — synthetic for sizing fallback",
    ),
    "userscript_test_mode_batch": SourceClassification(
        "userscript_test_mode_batch", DataProvenance.SIMULATED,
        "Userscript v2 TEST MODE — fabricates quotes for end-to-end validation",
    ),
    "historical_replay": SourceClassification(
        "historical_replay", DataProvenance.SIMULATED,
        "Replay of historical snapshots — not live data",
    ),
    "arbicore_seed_fixture": SourceClassification(
        "arbicore_seed_fixture", DataProvenance.SIMULATED,
        "Seed/fixture data — bootstrap and test only",
    ),

    # ── Phase D D-1.0 venue sources (7 entries — operator-mandated D-1 core + 1 reference) ─
    "bybit_public": SourceClassification(
        "bybit_public", DataProvenance.REAL,
        "Bybit public REST API (/v5/market/*) — spot ticker + order book + asset capability",
    ),
    "okx_public": SourceClassification(
        "okx_public", DataProvenance.REAL,
        "OKX public REST API (/api/v5/market/* + /api/v5/asset/currencies)",
    ),
    "kucoin_public": SourceClassification(
        "kucoin_public", DataProvenance.REAL,
        "KuCoin public REST API (/api/v1/market/* + /api/v3/currencies)",
    ),
    "mexc_public": SourceClassification(
        "mexc_public", DataProvenance.REAL,
        "MEXC public REST API (/api/v3/ticker/* + /api/v3/depth)",
    ),
    "gate_public": SourceClassification(
        "gate_public", DataProvenance.REAL,
        "Gate.io public REST API (/api/v4/spot/* + /api/v4/spot/currencies)",
    ),
    "bitget_public": SourceClassification(
        "bitget_public", DataProvenance.REAL,
        "Bitget public REST API (/api/v2/spot/market/* + /api/v2/spot/public/coins)",
    ),
    "binance_public_reference": SourceClassification(
        "binance_public_reference", DataProvenance.REAL,
        "Binance public REST API (/api/v3/ticker/bookTicker) — READ-ONLY market benchmark",
    ),
    # ── Phase D D-1.5 first aggregator DiscoverySource (telemetry only — INV-3) ─
    "coingecko_public": SourceClassification(
        "coingecko_public", DataProvenance.REAL,
        "CoinGecko public REST API (/api/v3/coins/{id}/tickers) — aggregator HINT "
        "source; verifier reads venues directly per INV-3 (provenance is "
        "telemetry only; never propagates to CanonicalOpportunity.source_data_quality)",
    ),

    # ── Phase D D-2.0 venue futures (perp) sources (7 venues + 1 aggregator) ──
    # Used by the funding-arbitrage scanner. Same INV-3 contract: verifier
    # reads each venue's futures API directly; provenance comes from the
    # venue read, never from any aggregator hint. All entries REAL.
    "bybit_futures_public": SourceClassification(
        "bybit_futures_public", DataProvenance.REAL,
        "Bybit public futures REST API (/v5/market/tickers?category=linear) — "
        "perpetual funding rate + mark/index price + next funding time",
    ),
    "okx_futures_public": SourceClassification(
        "okx_futures_public", DataProvenance.REAL,
        "OKX public funding-rate REST API (/api/v5/public/funding-rate, "
        "/api/v5/public/instruments?instType=SWAP)",
    ),
    "gate_futures_public": SourceClassification(
        "gate_futures_public", DataProvenance.REAL,
        "Gate.io USDT-margined futures public REST API "
        "(/api/v4/futures/usdt/contracts, /api/v4/futures/usdt/tickers)",
    ),
    "bitget_futures_public": SourceClassification(
        "bitget_futures_public", DataProvenance.REAL,
        "Bitget mix (perp) public REST API "
        "(/api/v2/mix/market/current-fund-rate, /api/v2/mix/market/tickers)",
    ),
    "mexc_futures_public": SourceClassification(
        "mexc_futures_public", DataProvenance.REAL,
        "MEXC contract public REST API "
        "(/api/v1/contract/funding_rate, /api/v1/contract/ticker)",
    ),
    "kucoin_futures_public": SourceClassification(
        "kucoin_futures_public", DataProvenance.REAL,
        "KuCoin futures public REST API "
        "(/api/v1/funding-rate, /api/v1/contracts/active)",
    ),
    "hyperliquid_public": SourceClassification(
        "hyperliquid_public", DataProvenance.REAL,
        "Hyperliquid public POST /info ({type:metaAndAssetCtxs}) — perp meta + "
        "funding context; hourly funding interval (experimental — optional, "
        "removable via per-source kill switch)",
    ),
    "coinglass_funding_public": SourceClassification(
        "coinglass_funding_public", DataProvenance.REAL,
        "Coinglass funding aggregator (HINT-ONLY; INV-3 — provenance is "
        "telemetry only; verifier confirms against venue futures APIs)",
    ),

    # ── Phase D D-3.0 DEX-arbitrage venue + aggregator sources ────────────
    # All entries REAL. Per-leg provenance comes from the chain-specific
    # quoter / subgraph read; aggregator HINT (dexscreener_hint) is
    # telemetry-only and never propagates to CanonicalOpportunity.
    # source_data_quality (INV-3). See D3_AUTHORIZATION_PACKAGE.md §4.
    "uniswap_v3_quoter_ethereum": SourceClassification(
        "uniswap_v3_quoter_ethereum", DataProvenance.REAL,
        "Uniswap V3 QuoterV2 contract on Ethereum mainnet (eth_call via Alchemy RPC) "
        "— authoritative per-pool quote at requested trade size",
    ),
    "uniswap_v3_quoter_arbitrum": SourceClassification(
        "uniswap_v3_quoter_arbitrum", DataProvenance.REAL,
        "Uniswap V3 QuoterV2 contract on Arbitrum One (eth_call via Alchemy RPC)",
    ),
    "uniswap_v3_quoter_base": SourceClassification(
        "uniswap_v3_quoter_base", DataProvenance.REAL,
        "Uniswap V3 QuoterV2 contract on Base (eth_call via Alchemy RPC)",
    ),
    "pancake_v3_quoter_bnb": SourceClassification(
        "pancake_v3_quoter_bnb", DataProvenance.REAL,
        "PancakeSwap V3 QuoterV2 contract on BNB Chain (eth_call via Alchemy RPC)",
    ),
    "pancake_v3_quoter_arbitrum": SourceClassification(
        "pancake_v3_quoter_arbitrum", DataProvenance.REAL,
        "PancakeSwap V3 QuoterV2 contract on Arbitrum (eth_call via Alchemy RPC)",
    ),
    "pancake_v3_quoter_base": SourceClassification(
        "pancake_v3_quoter_base", DataProvenance.REAL,
        "PancakeSwap V3 QuoterV2 contract on Base (eth_call via Alchemy RPC)",
    ),
    "aerodrome_quoter_base": SourceClassification(
        "aerodrome_quoter_base", DataProvenance.REAL,
        "Aerodrome MixedRouteQuoter contract on Base (eth_call via Alchemy RPC)",
    ),
    "raydium_quoter_solana": SourceClassification(
        "raydium_quoter_solana", DataProvenance.REAL,
        "Raydium AMM pool-state reads on Solana (getMultipleAccounts via Helius RPC) "
        "+ SDK-equivalent off-chain quote math — authoritative per-pool quote",
    ),
    "dexscreener_hint": SourceClassification(
        "dexscreener_hint", DataProvenance.REAL,
        "DexScreener cross-DEX cross-chain divergence aggregator (HINT-ONLY; INV-3 — "
        "provenance is telemetry only; verifier confirms against on-chain quoters "
        "and never propagates this classification to CanonicalOpportunity.source_data_quality)",
    ),

    # ── Phase D D-4.0 Launch Intelligence substrate sources ───────────────
    # Per D4_AUTHORIZATION_PACKAGE.md §2.2. All entries REAL provenance;
    # the three aggregator HINT entries carry an explicit "HINT-ONLY; INV-3"
    # reason marker so the verifier never propagates these classifications
    # to CanonicalOpportunity.source_data_quality (the per-leg on-chain
    # source classification is used instead).
    "dexscreener_fresh_launch": SourceClassification(
        "dexscreener_fresh_launch", DataProvenance.REAL,
        "DexScreener public REST aggregator — /token-profiles/latest/v1 and "
        "/token-boosts/{latest,top}/v1 endpoints for fresh-launch discovery "
        "(HINT-ONLY; INV-3 — provenance is telemetry only; LaunchOpportunityVerifier "
        "re-derives source_data_quality from per-leg on-chain RPC reads)",
    ),
    "pumpfun_launches": SourceClassification(
        "pumpfun_launches", DataProvenance.REAL,
        "Pump.fun frontend-api unofficial public endpoint — Solana bonding-curve "
        "launch discovery (HINT-ONLY; INV-3 — provenance is telemetry only; "
        "verifier re-derives source_data_quality from Helius/Solana RPC. "
        "Operational risk: unofficial endpoint, multi-base fallback required)",
    ),
    "jupiter_trending": SourceClassification(
        "jupiter_trending", DataProvenance.REAL,
        "Jupiter Aggregator REST API — Solana trending pools + token metadata "
        "+ price (HINT-ONLY; INV-3 — provenance is telemetry only; "
        "verifier re-derives source_data_quality from Helius/Solana RPC. "
        "Best-effort multi-host candidate fallback)",
    ),
    "helius_wallet_source": SourceClassification(
        "helius_wallet_source", DataProvenance.REAL,
        "Helius RPC — parsed-tx, balances, DAS getAssetsByOwner, "
        "getTokenLargestAccounts. Authoritative Solana wallet intelligence; "
        "requires HELIUS_API_KEY (graceful-disable when absent)",
    ),
    "helius_token_rpc": SourceClassification(
        "helius_token_rpc", DataProvenance.REAL,
        "Helius RPC — Solana token mint state (mintAuthority, freezeAuthority, "
        "supply, decimals) + pool account reads. Authoritative source for "
        "rug-risk verification keys; requires HELIUS_API_KEY (graceful-disable)",
    ),
    "bitquery_wallet_source": SourceClassification(
        "bitquery_wallet_source", DataProvenance.REAL,
        "Bitquery GraphQL — cross-chain wallet enrichment (BNB / Base / "
        "Polygon launches). Scaffolded but stubbed at D-4.0 per operator "
        "decision (BITQUERY_API_KEY not provisioned; graceful-disable). "
        "Live wiring deferred until cross-chain launch coverage is required",
    ),

    # ── D-5.0 substrate seeding — Cross-Chain Intelligence ──────────────
    # Authoritative bridge transfer-quote sources. Both are REAL classifications
    # because the underlying bridge protocols expose on-chain settlement
    # guarantees through their quote APIs (LI.FI aggregates; Stargate is
    # native LayerZero v2). INV-3 — the verifier (D-5.4) re-derives
    # source_data_quality from per-leg source_id; aggregator hints from
    # DexScreener-equivalents (if any) would carry HINT classification.
    "lifi_quote_real": SourceClassification(
        "lifi_quote_real", DataProvenance.REAL,
        "LI.FI bridge aggregator REST API — multi-bridge transfer quotes "
        "with route, expected_out_amount, slippage, fee_breakdown across "
        "EVM and Solana. Requires LIFI_API_KEY (free tier exists; "
        "graceful-disable when absent). D-5.3 reference TransferModelProvider",
    ),
    "stargate_quote_real": SourceClassification(
        "stargate_quote_real", DataProvenance.REAL,
        "Stargate (LayerZero v2) native bridge quote API — USDC/USDT/ETH "
        "cross-chain routes with deterministic delivery. Optional source — "
        "operator may enable independently of LI.FI for direct settlement",
    ),

    # Per-chain RPC liveness sources (D-5.2 ChainLivenessRegistry). REAL
    # classification — direct chain RPC reads (blockhash, finality, gas).
    # Graceful-disable when the chain's RPC URL env var is unset.
    "ethereum_rpc_real": SourceClassification(
        "ethereum_rpc_real", DataProvenance.REAL,
        "Ethereum mainnet RPC — block height, gas price, base fee, "
        "finality. ETH_RPC_URL env var; graceful-disable when absent",
    ),
    "arbitrum_rpc_real": SourceClassification(
        "arbitrum_rpc_real", DataProvenance.REAL,
        "Arbitrum One RPC — block height + L1 confirmation finality. "
        "ARBITRUM_RPC_URL env var; graceful-disable when absent",
    ),
    "base_rpc_real": SourceClassification(
        "base_rpc_real", DataProvenance.REAL,
        "Base mainnet RPC — block height + L1 confirmation finality. "
        "BASE_RPC_URL env var; graceful-disable when absent",
    ),
    "optimism_rpc_real": SourceClassification(
        "optimism_rpc_real", DataProvenance.REAL,
        "Optimism mainnet RPC — block height + L1 confirmation finality. "
        "OPTIMISM_RPC_URL env var; graceful-disable when absent",
    ),
    "polygon_rpc_real": SourceClassification(
        "polygon_rpc_real", DataProvenance.REAL,
        "Polygon mainnet RPC — block height, gas price, finality. "
        "POLYGON_RPC_URL env var; graceful-disable when absent",
    ),

    # ───────────────────────────────────────────────────────────────────
    # D-6.0 — Flash-Loan Detection Framework substrate (Phase D wave D-6).
    # Operator-scoped to three battle-tested providers (Aave V3, Balancer
    # V2, Uniswap V3 single-sided flash). All REAL — provider state is
    # read directly from on-chain contracts; the verifier consumes the
    # existing D-3 DEX quote substrate per leg.
    # ───────────────────────────────────────────────────────────────────
    "aave_v3_flashloan_real": SourceClassification(
        "aave_v3_flashloan_real", DataProvenance.REAL,
        "Aave V3 Pool contract — flashLoanSimple / flashLoan capacity, "
        "liquidity caps, premium rate (5 bps default). Read directly via "
        "per-chain RPC. Multi-chain: Ethereum / Arbitrum / Base / "
        "Optimism / Polygon. Graceful-disable when chain RPC absent.",
    ),
    "balancer_v2_flashloan_real": SourceClassification(
        "balancer_v2_flashloan_real", DataProvenance.REAL,
        "Balancer V2 Vault — flashLoan endpoint with 0 fee. Liquidity "
        "read directly from vault contract. Multi-chain: Ethereum / "
        "Arbitrum / Base / Optimism / Polygon",
    ),
    "uniswap_v3_flashloan_real": SourceClassification(
        "uniswap_v3_flashloan_real", DataProvenance.REAL,
        "Uniswap V3 single-sided flash via pool.flash() — fee = pool's "
        "swap-fee tier (0.05 / 0.30 / 1.00 %). Liquidity read directly "
        "from pool contracts. Multi-chain coverage",
    ),
    "solana_rpc_real": SourceClassification(
        "solana_rpc_real", DataProvenance.REAL,
        "Solana mainnet RPC — slot/blockhash, finality, recent fees. "
        "SOLANA_RPC_URL env var (or HELIUS_API_KEY-derived); graceful-"
        "disable when absent. Distinct from helius_token_rpc (mint state)",
    ),

    # ── ArbitrageX heritage registry (Phase A baseline — preserved) ──────
    "uniswap_v3": SourceClassification(
        "uniswap_v3", DataProvenance.REAL,
        "The Graph gateway with API key — real on-chain pool data",
    ),
    "dexscreener": SourceClassification(
        "dexscreener", DataProvenance.REAL,
        "Public DexScreener API — real market data",
    ),
    "aerodrome": SourceClassification(
        "aerodrome", DataProvenance.REAL,
        "Real via DexScreener proxy (Base) when matched",
    ),
    "camelot": SourceClassification(
        "camelot", DataProvenance.REAL,
        "Real via DexScreener proxy (Arbitrum) when matched",
    ),
    "oneinch": SourceClassification(
        "oneinch", DataProvenance.CONTAMINATED,
        "Injects random spreads/liquidity while tagging LIVE — unfit for learning",
    ),
    "balancer": SourceClassification(
        "balancer", DataProvenance.CONTAMINATED,
        "Price = BASE_PRICES * random variation — synthetic disguised as LIVE",
    ),
    "sushiswap": SourceClassification(
        "sushiswap", DataProvenance.DEAD,
        "Hosted subgraph decommissioned by The Graph (2024) — returns no data",
    ),
    "quickswap": SourceClassification(
        "quickswap", DataProvenance.DEAD, "Hosted subgraph decommissioned — no data",
    ),
    "pancakeswap": SourceClassification(
        "pancakeswap", DataProvenance.DEAD, "Hosted subgraph decommissioned — no data",
    ),
    "curve": SourceClassification(
        "curve", DataProvenance.DEAD, "Hosted subgraph decommissioned — no data",
    ),
    "simulated": SourceClassification(
        "simulated", DataProvenance.SIMULATED, "Synthetic fallback generator — test use only",
    ),
}


# Sentinel returned by ``classify()`` for unknown sources. ArbitrageX-era
# behaviour: treat unknown as SIMULATED (still excluded from learning).
_UNKNOWN_CLASSIFY = SourceClassification(
    "unknown", DataProvenance.SIMULATED, "Unregistered source — treated as non-real",
)


def classify(source: str) -> SourceClassification:
    """Return the SourceClassification for a source name (case-insensitive).

    Unknown sources are returned with provenance ``SIMULATED`` (heritage
    behaviour preserved for 41 Phase A tests). Use ``get_classification()``
    for the stricter Phase B contract that returns ``DEAD`` for unknowns.
    """
    return SOURCE_REGISTRY.get((source or "").lower(), _UNKNOWN_CLASSIFY)


def get_classification(source: str) -> DataProvenance:
    """Phase B strict classifier — returns DEAD for any unknown source.

    Behavioural contract per master architecture §6.3 and PHASE_B_DESIGN §2.2:
    UNKNOWN sources cannot feed learning. Safer than silent acceptance.
    """
    entry = SOURCE_REGISTRY.get((source or "").lower())
    if entry is None:
        return DataProvenance.DEAD
    return entry.provenance


def is_learning_eligible(source_or_provenance) -> bool:
    """True only for learning-eligible provenances (VERIFIED_REAL or REAL).

    Accepts either a source-name string or a DataProvenance enum.
    """
    if isinstance(source_or_provenance, DataProvenance):
        return source_or_provenance in LEARNING_ELIGIBLE_PROVENANCE
    return classify(str(source_or_provenance)).learning_eligible


class ContaminatedDataError(Exception):
    """Raised when non-learning-eligible data is pushed toward a learning subsystem."""


def assert_learning_eligible(source_or_provenance):
    """Raise ContaminatedDataError unless the value is learning-eligible.

    Returns True on success so callers may use it inside an assertion or
    boolean chain (e.g. ``assert_learning_eligible(opp.source_data_quality)``).
    """
    if not is_learning_eligible(source_or_provenance):
        raise ContaminatedDataError(
            f"Refusing non-learning-eligible data for learning: {source_or_provenance}"
        )
    return True


def registry_counts_by_provenance() -> Dict[str, int]:
    """For /api/arbicore/health and /api/arbicore/provenance — counts per tier."""
    c = Counter(entry.provenance.value for entry in SOURCE_REGISTRY.values())
    # Ensure every tier appears, even with 0
    for tier in DataProvenance:
        c.setdefault(tier.value, 0)
    return dict(c)


def list_sources_by_provenance(provenance: DataProvenance) -> List[str]:
    return sorted([name for name, entry in SOURCE_REGISTRY.items()
                   if entry.provenance == provenance])


def coverage_pct(known_universe: List[str]) -> float:
    """Percentage of an external universe that has a registry entry (and is
    not classified as DEAD by default). Used by /api/arbicore/health."""
    if not known_universe:
        return 0.0
    classified = sum(
        1 for s in known_universe
        if get_classification(s) is not DataProvenance.DEAD
    )
    return round(100.0 * classified / len(known_universe), 2)


# Phase B "native" sources — the 15 newly-classified ArbiCore-native entries
# (excludes ArbitrageX heritage). Used by the health endpoint to report a
# stable coverage metric independent of heritage drift.
PHASE_B_NATIVE_SOURCES: List[str] = [
    # 11 REAL
    "blockdag_rpc_primary", "bsc_rpc", "bscscan_api",
    "coinstore_public_depth", "azbit_public", "p2b_public",
    "pionex_public", "xt_public", "quote_capture_batch",
    "blockdag_live_swap_userscript", "metamask_observed_address",
    # 4 SIMULATED
    "manual_config_balance", "userscript_test_mode_batch",
    "historical_replay", "arbicore_seed_fixture",
]


def native_coverage_pct() -> float:
    """% of Phase B native sources that are NOT classified DEAD."""
    return coverage_pct(PHASE_B_NATIVE_SOURCES)
