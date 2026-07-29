"""ArbiCore X — Soft-typed ``category_metadata`` registry (Phase B).

The canonical opportunity object carries a free-form ``category_metadata``
dict whose keys depend on the ``OpportunityType``. We document the *known*
keys per type here. Unknown keys are accepted (the validator never raises)
but emit exactly one ``logger.warning`` per ``(opportunity_type, key)`` pair
per process lifetime so the operator can monitor schema drift via the
``/api/arbicore/health`` endpoint.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, Optional

from .enums import OpportunityType

logger = logging.getLogger("arbicore.category_metadata")


# Frozen vocabulary of known keys per OpportunityType. Source: master
# architecture §6.4. Adding a new key here is a deliberate vocabulary
# extension — do it in a versioned commit, not by drift.
KNOWN_CATEGORY_METADATA_KEYS: Dict[OpportunityType, frozenset] = {
    OpportunityType.CEX_ARBITRAGE: frozenset({
        "best_bid_price", "best_ask_price", "profitable_buyer_depth_usd",
        "venue_health_score", "verified_quote_age_s", "fee_drag_pct",
        "drift_risk_label", "drift_regime", "combined_survival_prob",
        "expected_cycle_s",
    }),
    OpportunityType.DEX_ARBITRAGE: frozenset({
        # Heritage D-3 vocabulary (Phase B baseline — preserved)
        "pool_address", "tvl_usd", "estimated_slippage_pct",
        "mev_competition_count", "snipers_in_pool",
        # D-3.0 quoter-specific extensions (per D3_AUTHORIZATION_PACKAGE.md §2.2)
        "chain", "buy_dex", "sell_dex",
        "buy_pool_address", "sell_pool_address",
        "fee_tier_bps", "route_path",
        "gas_estimate_usd", "gas_drag_pct",
        "quote_age_ms",
        "slippage_at_size_usd", "total_slippage_pct",
        "effective_buy_price_at_size", "effective_sell_price_at_size",
        "net_spread_after_slip_pct", "net_spread_after_slip_after_gas_pct",
        "mev_penalty_pct", "mev_adjusted_net_pct",
    }),
    OpportunityType.FUNDING_ARBITRAGE: frozenset({
        # D-1 legacy keys (pre-D-2 — retained for back-compat with planning docs)
        "funding_rate_pct", "funding_interval_hours",
        "perp_index_basis_pct", "open_interest_usd",
        # D-2.0 funding-differential keys (added 2026-06-19 per the D-2 plan §4.2)
        "long_venue_funding_rate_pct", "short_venue_funding_rate_pct",
        "long_funding_interval_h", "short_funding_interval_h",
        "long_funding_apr_pct", "short_funding_apr_pct",
        "funding_diff_apr_pct",
        "next_funding_time_long_iso", "next_funding_time_short_iso",
        "long_perp_mark_price",  "short_perp_mark_price",
        "long_perp_index_price", "short_perp_index_price",
        "long_open_interest_usd", "short_open_interest_usd",
        "long_depth_usd",        "short_depth_usd",
        "total_round_trip_cost_pct", "break_even_hours",
    }),
    OpportunityType.LAUNCH_ARBITRAGE: frozenset({
        # Phase B baseline keys (preserved)
        "launch_phase", "presale_price", "public_price",
        "vesting_tge_pct", "expected_roi_probability",
        "wallet_cluster_ids", "insider_signals",
        # D-4.0 substrate extensions — Solana rug-risk indicators
        # (per D4_AUTHORIZATION_PACKAGE.md §2.2)
        "mint_authority_revoked", "freeze_authority_revoked",
        "lp_burned_pct", "lp_locked_until_ts",
        "bonding_curve_progress_pct", "migration_ready",
        "holder_concentration_top10_pct", "holder_count",
        # Discovery / phase classifier surface
        "chain", "launchpad", "token_address",
        "age_hours", "first_seen_at_ts",
        "phase_confidence", "phase_rationale",
        # Smart-money / wallet intel surface
        "smart_money_entry_count", "cluster_size_max",
        "early_quality_wallet_count", "whale_rotation_count",
        # Timeline / narrative surface
        "timeline_confidence", "timeline_label",
        "narrative_daily_cost_usd", "narrative_llm_used",
        # ROI probability surface (winsorized historical)
        "roi_base_low_pct", "roi_base_high_pct",
        "roi_breakout_probability", "roi_drawdown_probability",
        "roi_sample_size",
    }),
    OpportunityType.CROSS_CHAIN_ARBITRAGE: frozenset({
        # Phase B baseline (preserved)
        "source_chain", "destination_chain", "bridge_provider",
        "bridge_latency_s", "bridge_fee_usd",
        # D-5.0 substrate extensions — corridor identity + canonical projection
        "bridge_route_id", "bridge_corridor_id",
        "source_chain_id", "destination_chain_id",
        # Bridge liveness + health (Gate 7 inputs — D-5.4)
        "bridge_health_score", "bridge_liveness_score",
        "inbound_latency_p50_s", "inbound_latency_p95_s",
        "bridge_inventory_pct",
        # Chain liveness (Gate 8 inputs — D-5.2 + D-5.4)
        "source_chain_finality_s", "destination_chain_finality_s",
        "source_chain_congestion_score", "destination_chain_congestion_score",
        # Transfer modelling outputs (D-5.3)
        "expected_out_amount", "expected_out_amount_usd",
        "slippage_bridge_pct", "transfer_modelling_confidence",
        # Cost surface (BridgeEconomicsAssessor — D-5.4)
        "gas_source_chain_usd", "gas_destination_chain_usd",
        "total_bridge_fee_usd", "total_round_trip_cost_pct",
        # Cross-chain MEV class (Gate 9 input — D-5.4)
        "cross_chain_mev_risk_class",
        # Verification audit
        "verified_at_ts", "transfer_quote_source",
    }),
    OpportunityType.FLASH_LOAN_ARBITRAGE: frozenset({
        # D-6.0 substrate vocabulary — atomic multi-hop flash-loan
        # arbitrage. Detection-only. Provider scope (operator-locked):
        # Aave V3 / Balancer V2 / Uniswap V3. Chain scope: Ethereum /
        # Arbitrum / Base / Optimism / Polygon.
        # ── Provider + chain identity ────────────────────────────────
        "flash_loan_provider", "chain",
        "flash_loan_pool_address",
        # ── Loan economics ───────────────────────────────────────────
        "flash_loan_borrow_token", "flash_loan_borrow_amount_usd",
        "flash_loan_fee_bps", "flash_loan_fee_usd",
        # ── Route surface (multi-hop) ────────────────────────────────
        "route_pools",          # ordered list of pool addresses
        "route_dex_protocols",  # ordered list of DEX protocols per hop
        "cycle_token_path",     # ordered token path (closed cycle)
        "hop_count",
        # ── Per-hop economics (aggregated) ───────────────────────────
        "total_swap_fee_pct", "total_slippage_pct",
        "gas_cost_usd", "gas_drag_pct",
        "min_pool_tvl_usd_in_route",
        # ── Atomic profit ────────────────────────────────────────────
        "atomic_profit_usd", "atomic_profit_pct",
        "expected_net_after_costs_usd",
        # ── Route-search telemetry ───────────────────────────────────
        "route_search_wall_ms", "route_search_candidates_explored",
        # ── MEV / atomicity ──────────────────────────────────────────
        "flash_loan_mev_risk_class", "simulated_atomicity_ok",
        # ── Verification audit ───────────────────────────────────────
        "verified_at_ts", "verifier_id",
    }),
}


# Process-local dedupe state for unknown-key warnings + an observability
# log surfaced via /api/arbicore/health.
_warned_unknown_keys: set = set()
_unknown_key_log: Dict[tuple, Dict[str, Any]] = {}
_lock = Lock()


def validate_category_metadata(opportunity_type: OpportunityType,
                               category_metadata: Optional[Dict[str, Any]]) -> None:
    """Soft validator: never raises. Warns once per (type, unknown_key) pair.

    Args:
        opportunity_type: the opportunity's type
        category_metadata: optional dict carrying category-specific extras

    Side effects:
        - Emits exactly one ``logger.warning`` per unique (type, key) per
          process lifetime when an unknown key is seen.
        - Records each first-seen unknown key in the module-level audit log
          consumed by /api/arbicore/health.category_metadata.unknown_key_warnings.
    """
    if not category_metadata:
        return
    known = KNOWN_CATEGORY_METADATA_KEYS.get(opportunity_type, frozenset())
    for key in category_metadata.keys():
        if key in known:
            continue
        # Unknown key path — dedupe + warn + record.
        signature = (opportunity_type, key)
        with _lock:
            if signature in _warned_unknown_keys:
                continue
            _warned_unknown_keys.add(signature)
            _unknown_key_log[signature] = {
                "opportunity_type": opportunity_type.value
                if hasattr(opportunity_type, "value") else str(opportunity_type),
                "key": key,
                "first_seen_at": datetime.now(timezone.utc).isoformat(),
            }
        logger.warning(
            "unknown_category_metadata_key opportunity_type=%s key=%s",
            opportunity_type.value if hasattr(opportunity_type, "value") else str(opportunity_type),
            key,
        )


def unknown_key_warnings() -> list:
    """Snapshot of the unknown-key audit log for /api/arbicore/health."""
    with _lock:
        return list(_unknown_key_log.values())


def reset_unknown_key_warnings() -> None:
    """Test-only: clear the dedupe state."""
    with _lock:
        _warned_unknown_keys.clear()
        _unknown_key_log.clear()
