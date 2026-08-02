"""ArbiCore X — canonical scanner default configurations.

Activated in Phase 10.4 from ``arbicore-x-v1.0.2.bundle``:
``app/backend/arbicore/data/scanner_config_repo.py``.  ONLY the default
schema constants are ported — the canonical bespoke
``ScannerConfigRepository`` class is intentionally NOT imported because
Phase 10 already provides a superior ``ConfigRepo`` substrate with
Draft/Apply/Rollback/Audit.  These constants become the seed values for
each scanner family under the ``scanner.<family_id>`` config kind.
"""
from __future__ import annotations

from typing import Any, Dict

# Legacy collection names (unused — kept for archaeological reference).

CONFIG_COLLECTION = "arbicore_scanner_config"
STATE_COLLECTION = "arbicore_scanner_state"


DEFAULT_CEX_ARB_CONFIG: Dict[str, Any] = {
    "_id": "cex_arb",
    "enabled": True,
    "interval_s": 30,
    "tier_a_pairs": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                     "DOGEUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT", "TRXUSDT"],
    "tier_b_pairs": [],
    "gate_thresholds": {
        "default": {"min_spread_pct": 0.30, "min_depth_usd": 5000,
                    "min_confidence": 55},
        "BTCUSDT": {"min_spread_pct": 0.15, "min_depth_usd": 20000,
                    "min_confidence": 60},
        "ETHUSDT": {"min_spread_pct": 0.15, "min_depth_usd": 20000,
                    "min_confidence": 60},
    },
    "binance_reference_required": False,
    "rejected_capture_pct": 1.0,
    "discovery_sources": {
        "venue_ticker:bybit":             {"enabled": True, "cadence_s": 30, "ticker_divergence_threshold_bps": 20},
        "venue_ticker:okx":               {"enabled": True, "cadence_s": 30, "ticker_divergence_threshold_bps": 20},
        "venue_ticker:kucoin":            {"enabled": True, "cadence_s": 30, "ticker_divergence_threshold_bps": 20},
        "venue_ticker:mexc":              {"enabled": True, "cadence_s": 30, "ticker_divergence_threshold_bps": 25},
        "venue_ticker:gate":              {"enabled": True, "cadence_s": 30, "ticker_divergence_threshold_bps": 20},
        "venue_ticker:bitget":            {"enabled": True, "cadence_s": 30, "ticker_divergence_threshold_bps": 20},
        "venue_ticker:binance_reference": {"enabled": True, "cadence_s": 30, "reference_only": True},
        # D-1.5 first aggregator (hint-only; verifier reads venues per INV-3)
        "coingecko_ticker": {
            "enabled": True,
            "cadence_s": 90,
            "cg_divergence_threshold_bps": 30,
            "volume_floor_usd": 50000,
            "target_coins": ["bitcoin", "ethereum", "solana", "binancecoin",
                              "ripple", "dogecoin", "cardano", "chainlink",
                              "avalanche-2", "tron"],
        },
    },
    "verifier_concurrency": 4,
}


DEFAULT_FUNDING_ARB_CONFIG: Dict[str, Any] = {
    "_id": "funding_arb",
    "enabled": True,
    "interval_s": 60,
    "max_funding_age_s": 600.0,
    "min_eligible_venues_for_diff": 2,
    "min_diff_apr_pct": 5.0,
    "max_break_even_hours": 24.0,
    "default_notional_usd": 1000.0,
    "depth_safety_factor": 5.0,
    "min_position_usd": 100.0,
    "gate_thresholds": {
        "default": {"min_funding_diff_apr_pct": 5.0,
                    "min_depth_usd": 5000.0,
                    "min_confidence": 55.0},
    },
    "discovery_sources": {
        # All venue funding sources enabled by default. Hyperliquid remains
        # experimental — operator can disable via this same per-source flag.
        "venue_funding:bybit":       {"enabled": True, "cadence_s": 60,
                                       "venue_funding_threshold_apr_pct": 5.0},
        "venue_funding:okx":         {"enabled": True, "cadence_s": 60,
                                       "venue_funding_threshold_apr_pct": 5.0},
        "venue_funding:gate":        {"enabled": True, "cadence_s": 60,
                                       "venue_funding_threshold_apr_pct": 5.0},
        "venue_funding:bitget":      {"enabled": True, "cadence_s": 60,
                                       "venue_funding_threshold_apr_pct": 5.0},
        "venue_funding:mexc":        {"enabled": True, "cadence_s": 60,
                                       "venue_funding_threshold_apr_pct": 5.0},
        "venue_funding:kucoin":      {"enabled": True, "cadence_s": 60,
                                       "venue_funding_threshold_apr_pct": 5.0},
        "venue_funding:hyperliquid": {"enabled": True, "cadence_s": 60,
                                       "venue_funding_threshold_apr_pct": 5.0},
    },
    "verifier_concurrency": 4,
}


# ── Phase D D-3.0 — DEX Arbitrage scanner defaults ───────────────────────
# Substrate seeding only. Discovery sources start DISABLED; scanner state
# starts DISABLED. No verifier registered yet (D-3.2). No emit path until
# the orchestrator ships (D-3.4). Per D3_AUTHORIZATION_PACKAGE.md §2.2 and
# DECISION_RECOMMENDATION_REPORT.md §4.2 / §5.4–§5.6.
DEFAULT_DEX_ARB_CONFIG: Dict[str, Any] = {
    "_id": "dex_arb",
    "enabled": False,
    "interval_s": 60,
    # Tier-1 pair universe (DECISION_RECOMMENDATION_REPORT §4.2 — 10 pairs).
    # Pair notation is canonical "BASE/QUOTE@CHAIN[:DEX]" where the chain and
    # DEX suffixes disambiguate cross-chain duplicates. The verifier-tier
    # implementation lands in D-3.1+; D-3.0 only stores the universe.
    "tier_a_pairs": [
        "WETH/USDC@ethereum",
        "WETH/USDC@arbitrum",
        "WETH/USDC@base",
        "WBTC/WETH@ethereum",
        "WBTC/WETH@arbitrum",
        "WETH/USDT@ethereum",
        "WETH/USDT@arbitrum",
        "WBTC/USDC@ethereum",
        "WBTC/USDC@arbitrum",
        "WETH/wstETH@ethereum",
        "WETH/wstETH@arbitrum",
        "CAKE/WBNB@bnb",
        "AERO/USDC@base",
        "SOL/USDC@solana",
        "ARB/USDC@arbitrum",
    ],
    "tier_b_pairs": [],
    # Gate-1 threshold ramp per DECISION_RECOMMENDATION_REPORT §5.4 / §5.6:
    # launch at 0.30% (learning-first); operator-driven config patches step
    # to 0.40% on day 8 and 0.50% on day 22.
    "gate_thresholds": {
        "default": {
            "min_net_spread_after_slip_after_gas_pct": 0.30,
            "min_depth_usd": 5000,
            "min_confidence": 55,
        },
        # Per-asset overrides (DECISION_RECOMMENDATION_REPORT §5.5).
        "WETH/wstETH@ethereum": {"min_net_spread_after_slip_after_gas_pct": 0.10},
        "WETH/wstETH@arbitrum": {"min_net_spread_after_slip_after_gas_pct": 0.10},
        "AERO/USDC@base":        {"min_net_spread_after_slip_after_gas_pct": 0.60},
        "SOL/USDC@solana":       {"min_net_spread_after_slip_after_gas_pct": 0.40},
    },
    "rejected_capture_pct": 0.5,
    # Default DEX cost assumptions used by D-3.3 DEXEconomicsAssessor when
    # it lands; harmless until then. Operator-tunable.
    "venue_fees": {
        "uniswap_v3":   {"taker_bps": 5},   # default fee tier; overridden per pool
        "pancake_v3":   {"taker_bps": 5},
        "aerodrome":    {"taker_bps": 5},
        "raydium":      {"taker_bps": 25},
    },
    "mev_risk_factor": {"LOW": 0.0, "MEDIUM": 0.5, "HIGH": 1.5},
    "depth_safety_factor": 5.0,
    "default_notional_usd": 1000.0,
    # All sources start DISABLED. Operator enables one-by-one during the
    # D-3.6 shadow rollout via /api/arbicore/discovery/sources/{src_id}/enable.
    "discovery_sources": {
        "venue_dex_pool:uniswap_v3:ethereum": {"enabled": False, "cadence_s": 60,
                                                "pool_divergence_threshold_bps": 30},
        "venue_dex_pool:uniswap_v3:arbitrum": {"enabled": False, "cadence_s": 60,
                                                "pool_divergence_threshold_bps": 30},
        "venue_dex_pool:uniswap_v3:base":     {"enabled": False, "cadence_s": 60,
                                                "pool_divergence_threshold_bps": 30},
        "venue_dex_pool:pancake_v3:bnb":      {"enabled": False, "cadence_s": 60,
                                                "pool_divergence_threshold_bps": 35},
        "venue_dex_pool:pancake_v3:arbitrum": {"enabled": False, "cadence_s": 60,
                                                "pool_divergence_threshold_bps": 35},
        "venue_dex_pool:pancake_v3:base":     {"enabled": False, "cadence_s": 60,
                                                "pool_divergence_threshold_bps": 35},
        "venue_dex_pool:aerodrome:base":      {"enabled": False, "cadence_s": 60,
                                                "pool_divergence_threshold_bps": 35},
        "venue_dex_pool:raydium:solana":      {"enabled": False, "cadence_s": 60,
                                                "pool_divergence_threshold_bps": 50},
        "dexscreener_hint": {
            "enabled": False, "cadence_s": 120,
            "ds_divergence_threshold_bps": 40,
            "volume_floor_usd": 50000,
        },
    },
    "verifier_concurrency": 4,
}


# ── Phase D D-4.0 — Launch Intelligence scanner defaults ─────────────────
# Substrate seeding only per D4_AUTHORIZATION_PACKAGE.md §2.2 / §6 / §4.
# Discovery sources start DISABLED; scanner state starts DISABLED; no
# verifier registered yet (lands D-4.4); no orchestrator yet (lands D-4.5).
# Operator decisions baked in (auth package §4):
#   D1: Helius only for Solana (free tier 100k credits/day)
#   D2: DexScreener fresh-launch + Pump.fun both enabled-in-config
#       (still gated by scanner state.enabled=False at boot)
#   D3: Bitquery scaffolded but stubbed (per-source `enabled=False`)
#   D4: Curated wallet seed lifted verbatim; rug_wallet entries advisory only
#   D5: LLM narrative $1/day hard cap (D-4.7 — optional, off at boot)
DEFAULT_LAUNCH_ARB_CONFIG: Dict[str, Any] = {
    "_id": "launch_arb",
    "enabled": False,
    "interval_s": 30,
    # Discovery cadences and per-source weights — operator-tunable post D-4.1.
    # `cadence_s` is best-effort; the orchestrator (D-4.5) applies its own
    # per-source rate limiter.
    "discovery_sources": {
        "dexscreener_fresh_launch": {
            "enabled": False, "cadence_s": 60,
            "ds_profiles_endpoint": "/token-profiles/latest/v1",
            "ds_boosts_latest_endpoint": "/token-boosts/latest/v1",
            "ds_boosts_top_endpoint": "/token-boosts/top/v1",
            "max_age_hours": 72,
        },
        "pumpfun_launches": {
            "enabled": False, "cadence_s": 30,
            "max_age_hours": 24,
            "min_market_cap_usd": 5_000,
            "max_market_cap_usd": 100_000,  # bonding-curve window
        },
        "jupiter_trending": {
            "enabled": False, "cadence_s": 90,
            "trending_limit": 50,
            "min_volume_usd_24h": 50_000,
        },
        "helius_wallet_source": {
            "enabled": False, "cadence_s": 60,
            "recent_buyers_limit": 50,
            "wallet_tx_lookback_days": 7,
            "max_concurrent_enrichments": 4,
        },
        "bitquery_wallet_source": {
            # Stubbed per Operator Decision 3. Live wiring deferred.
            "enabled": False, "cadence_s": 120,
            "scaffolded_only": True,
        },
    },
    # Composite launch-score Gate 1 thresholds (final formulas land D-4.3/4.4).
    # Initial conservative defaults — operator can ramp post shadow rollout.
    "gate_thresholds": {
        "default": {
            "min_composite_launch_score": 55.0,    # 0-100 composite from D-4.3
            "min_bonding_curve_progress_pct": 5.0,  # avoid pre-launch noise
            "min_holders": 25,
            "min_smart_money_entries": 1,           # at least one quality wallet
            "max_holder_concentration_top10_pct": 50.0,
            "min_confidence": 55.0,
        },
        # Per-launchpad overrides — pumpfun has its own bonding-curve dynamics.
        "pumpfun": {
            "min_composite_launch_score": 50.0,
            "min_bonding_curve_progress_pct": 10.0,
        },
    },
    # Gate 6 (rug-risk) — Solana-specific hard rejections.
    "rug_gate": {
        "require_mint_authority_revoked": True,
        "require_freeze_authority_revoked": True,
        "min_lp_burned_or_locked_pct": 80.0,
        "max_holder_concentration_top10_pct": 60.0,
    },
    # Wallet intelligence runtime knobs.
    "wallet_intelligence": {
        "time_window_cluster_seconds": 300,   # ±5min co-occurrence cluster
        "min_cluster_size": 3,
        "early_entry_threshold_hours": 1.0,
        "quality_wallet_min_score": 60.0,
        "high_conviction_min_usd": 5_000.0,
        "whale_rotation_window_minutes": 30,
    },
    # Phase classifier thresholds (D-4.3 PhaseClassifier — initial values).
    "phase_classifier": {
        "stealth_low_social_threshold": 0.20,
        "early_momentum_min_score_delta": 5.0,
        "overheated_max_price_change_24h_pct": 200.0,
        "overheated_retail_fomo_share_min": 0.40,
        "exhaustion_lp_drop_pct": 30.0,
    },
    # ROI probability engine (winsorized historical).
    "roi_probability": {
        "winsor_low_pct": 5.0,
        "winsor_high_pct": 95.0,
        "min_sample_size": 10,
    },
    # D-4.7 narrative (optional, feature-flagged). Hard daily USD cap
    # enforced in code (operator decision 5).
    "narrative": {
        "enabled": False,
        "daily_usd_cap": 1.00,
        "cache_ttl_seconds": 3600,
        "max_calls_per_token_per_day": 3,
    },
    "rejected_capture_pct": 1.0,
    "default_notional_usd": 250.0,    # smaller default for launches
    "verifier_concurrency": 2,
}


# ── D-5.0 Cross-Chain Intelligence — substrate seeding ──────────────────
# This config doc is seeded with conservative defaults. The orchestrator
# (CrossChainArbitrageScanner) lands at D-5.5; the verifier + gates at
# D-5.4; the transfer-model provider + bridge intelligence at D-5.3;
# chain-liveness registry at D-5.2; discovery sources at D-5.1. At D-5.0
# this config is inert — `enabled=False`, no orchestrator factory exists.
# Operator scope decisions baked in:
#   - Bridges: LI.FI (aggregator-first) + Stargate (optional direct).
#     All bridge enable flags default False.
#   - Chains: ETH, Arbitrum, Base, Optimism, Polygon, Solana (6 chains).
#   - Extension points: per-bridge "enabled" flag + per-chain "enabled"
#     flag let operator graduate incrementally without code changes.
DEFAULT_CROSS_CHAIN_ARB_CONFIG: Dict[str, Any] = {
    "_id": "cross_chain_arb",
    "enabled": False,
    "interval_s": 45,
    "bridges": {
        "lifi": {
            "enabled": False, "cadence_s": 60,
            "credentials_env_var": "LIFI_API_KEY",
            "base_url": "https://li.quest/v1",
            "quote_endpoint": "/quote",
            "max_concurrent_quotes": 4,
        },
        "stargate": {
            # 2026-06: Upstream Stargate v1 API deprecated by vendor
            # (HTTP 410, migrated to LayerZero VT). Operator should route
            # Stargate traffic via the `lifi` bridge (LI.FI internally
            # aggregates Stargate as one of its supported bridges).
            # ``deprecated: true`` causes StargateSource to emit a clean
            # last_error message rather than attempting dead API calls.
            "enabled": False, "deprecated": True, "cadence_s": 90,
            "credentials_env_var": "STARGATE_API_KEY",
            "base_url": "https://api.stargate.finance",
            "quote_endpoint": "/v1/quote",
            "max_concurrent_quotes": 2,
        },
    },
    "chains": {
        "ethereum":  {"enabled": False, "chain_id": 1,
                       "rpc_env_var": "ETH_RPC_URL",
                       "finality_blocks": 64, "gas_token": "ETH"},
        "arbitrum":  {"enabled": False, "chain_id": 42161,
                       "rpc_env_var": "ARBITRUM_RPC_URL",
                       "finality_blocks": 1, "gas_token": "ETH"},
        "base":      {"enabled": False, "chain_id": 8453,
                       "rpc_env_var": "BASE_RPC_URL",
                       "finality_blocks": 1, "gas_token": "ETH"},
        "optimism":  {"enabled": False, "chain_id": 10,
                       "rpc_env_var": "OPTIMISM_RPC_URL",
                       "finality_blocks": 1, "gas_token": "ETH"},
        "polygon":   {"enabled": False, "chain_id": 137,
                       "rpc_env_var": "POLYGON_RPC_URL",
                       "finality_blocks": 128, "gas_token": "MATIC"},
        "solana":    {"enabled": False, "chain_id": 0,
                       "rpc_env_var": "SOLANA_RPC_URL",
                       "finality_slots": 32, "gas_token": "SOL"},
    },
    "gate_thresholds": {
        "default": {
            "min_net_spread_after_costs_pct": 0.40,
            "min_bridge_health_score": 70.0,
            "min_bridge_liveness_score": 75.0,
            "max_chain_congestion_score": 80.0,
            "max_inbound_latency_p95_s": 1800.0,
            "min_confidence": 60.0,
            "max_cross_chain_mev_risk_class": "MEDIUM",
        },
        "stargate": {"max_inbound_latency_p95_s": 600.0},
    },
    "transfer_model": {
        "max_slippage_estimate_pct": 5.0,
        "default_notional_usd": 1000.0,
        "corridor_overrides": {},
    },
    "roi_probability": {
        "winsor_low_pct": 5.0, "winsor_high_pct": 95.0,
        "min_sample_size": 8,
    },
    "http_retry": {
        "max_attempts": 3, "initial_backoff_s": 0.2,
        "max_backoff_s": 2.0, "ttl_cache_s": 45.0,
    },
    "rejected_capture_pct": 1.0,
    "default_notional_usd": 1000.0,
    "verifier_concurrency": 2,
}


# ============================================================================
# D-6.0 — Flash-Loan Detection Framework substrate defaults
# ============================================================================
# Operator-scoped: Aave V3 + Balancer V2 + Uniswap V3 only. Chain scope:
# Ethereum / Arbitrum / Base / Optimism / Polygon (5 chains, no Solana).
# Hop budget: 4. Route-search budget: 5s wall-clock, 64 candidates.
# Atomic-profit floor: 25 USD. Boot posture: DORMANT.

DEFAULT_FLASH_LOAN_ARB_CONFIG: Dict[str, Any] = {
    "_id": "flash_loan_arb",
    "enabled": False,
    "interval_s": 60,
    "providers": {
        "aave_v3": {
            "enabled": False, "fee_bps": 5,
            "credentials_env_var": None,
            "source_id": "aave_v3_flashloan_real",
        },
        "balancer_v2": {
            "enabled": False, "fee_bps": 0,
            "credentials_env_var": None,
            "source_id": "balancer_v2_flashloan_real",
        },
        "uniswap_v3": {
            "enabled": False,
            "fee_bps_by_tier": {"500": 5, "3000": 30, "10000": 100},
            "credentials_env_var": None,
            "source_id": "uniswap_v3_flashloan_real",
        },
    },
    "chains": {
        "ethereum": {"enabled": False, "chain_id": 1,
                      "rpc_env_var": "ETH_RPC_URL",
                      "gas_token": "ETH", "tx_gas_units": 800_000},
        "arbitrum": {"enabled": False, "chain_id": 42161,
                      "rpc_env_var": "ARBITRUM_RPC_URL",
                      "gas_token": "ETH", "tx_gas_units": 1_500_000},
        "base":     {"enabled": False, "chain_id": 8453,
                      "rpc_env_var": "BASE_RPC_URL",
                      "gas_token": "ETH", "tx_gas_units": 800_000},
        "optimism": {"enabled": False, "chain_id": 10,
                      "rpc_env_var": "OPTIMISM_RPC_URL",
                      "gas_token": "ETH", "tx_gas_units": 800_000},
        "polygon":  {"enabled": False, "chain_id": 137,
                      "rpc_env_var": "POLYGON_RPC_URL",
                      "gas_token": "MATIC", "tx_gas_units": 1_000_000},
    },
    "route_search": {
        "max_hops": 4,
        "wall_clock_cap_s": 5.0,
        "candidate_cap": 64,
        "min_pool_tvl_usd": 100_000,
    },
    "gate_thresholds": {
        "default": {
            "min_atomic_profit_usd": 25.0,
            "min_pool_tvl_usd_in_route": 100_000.0,
            "max_flash_loan_mev_risk_class": "MEDIUM",
            "min_confidence": 60.0,
        },
    },
    "roi_probability": {
        "winsor_low_pct": 5.0, "winsor_high_pct": 95.0,
        "min_sample_size": 8,
    },
    "http_retry": {
        "max_attempts": 3, "initial_backoff_s": 0.2,
        "max_backoff_s": 2.0, "ttl_cache_s": 30.0,
    },
    "default_notional_usd": 10_000.0,
    "verifier_concurrency": 2,
}




# ---------------------------------------------------------------------------
# Family registry — used by ScannerConfigRepo.  Order matters for the UI
# family switcher (Flash Loan first because it's the operationally active
# family in v1.1.x).
# ---------------------------------------------------------------------------

CANONICAL_FAMILIES = (
    "flash_loan_arb",
    "cex_arb",
    "dex_arb",
    "cross_chain_arb",
    "funding_arb",
    "launch_arb",
)

FAMILY_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "flash_loan_arb":   DEFAULT_FLASH_LOAN_ARB_CONFIG,
    "cex_arb":          DEFAULT_CEX_ARB_CONFIG,
    "dex_arb":          DEFAULT_DEX_ARB_CONFIG,
    "cross_chain_arb":  DEFAULT_CROSS_CHAIN_ARB_CONFIG,
    "funding_arb":      DEFAULT_FUNDING_ARB_CONFIG,
    "launch_arb":       DEFAULT_LAUNCH_ARB_CONFIG,
}

FAMILY_LABELS: Dict[str, str] = {
    "flash_loan_arb":  "Flash Loan",
    "cex_arb":         "CEX Arbitrage",
    "dex_arb":         "DEX Arbitrage",
    "cross_chain_arb": "Cross-chain",
    "funding_arb":     "Funding Arbitrage",
    "launch_arb":      "Launch Arbitrage",
}
