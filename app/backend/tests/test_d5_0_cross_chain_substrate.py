"""D-5.0 — Cross-Chain Intelligence substrate seeding tests.

D-5.0 ships substrate ONLY. The orchestrator, verifier, sources, gates,
economics, transfer-model provider, and chain-liveness registry all land
in waves D-5.1 → D-5.5. At this wave we verify:

  1. category_metadata vocab extended for CROSS_CHAIN_ARBITRAGE
  2. SOURCE_REGISTRY carries the 8 new D-5 sources
  3. scanner_config seeded with operator-scope decisions
     (LI.FI + Stargate bridges, 6 chains, all enable flags = False)
  4. scanner_state.cross_chain_arb defaults to enabled=False
  5. Boot env gate recording (inert at D-5.0 — no orchestrator wired yet)
  6. Wave-progression negative assertions: scanner.py, verifier.py,
     sources.py, helius_-style provider, composition factory do NOT yet
     import — they land at D-5.1+
  7. INV-1/2/3 still preserved — no new emit path, no new canonical
     construction site, no new provenance source for any non-D-5 type
"""
from __future__ import annotations

import os
from typing import Any, Dict

import pytest

from arbicore.models.category_metadata import KNOWN_CATEGORY_METADATA_KEYS
from arbicore.models.enums import OpportunityType


# ============================================================================
# 1. category_metadata vocab extension
# ============================================================================

CROSS_CHAIN_KEYS = KNOWN_CATEGORY_METADATA_KEYS[
    OpportunityType.CROSS_CHAIN_ARBITRAGE]


def test_cross_chain_metadata_has_phase_b_baseline_keys():
    """Phase B baseline keys must be preserved (back-compat)."""
    baseline = {"source_chain", "destination_chain", "bridge_provider",
                  "bridge_latency_s", "bridge_fee_usd"}
    assert baseline <= CROSS_CHAIN_KEYS


def test_cross_chain_metadata_has_corridor_keys():
    """D-5.0 corridor identity surface for the canonical projection."""
    assert {"bridge_route_id", "bridge_corridor_id",
             "source_chain_id", "destination_chain_id"} <= CROSS_CHAIN_KEYS


def test_cross_chain_metadata_has_gate7_bridge_liveness_inputs():
    assert {"bridge_health_score", "bridge_liveness_score",
             "inbound_latency_p50_s", "inbound_latency_p95_s",
             "bridge_inventory_pct"} <= CROSS_CHAIN_KEYS


def test_cross_chain_metadata_has_gate8_chain_liveness_inputs():
    assert {"source_chain_finality_s", "destination_chain_finality_s",
             "source_chain_congestion_score",
             "destination_chain_congestion_score"} <= CROSS_CHAIN_KEYS


def test_cross_chain_metadata_has_transfer_modelling_outputs():
    assert {"expected_out_amount", "expected_out_amount_usd",
             "slippage_bridge_pct",
             "transfer_modelling_confidence"} <= CROSS_CHAIN_KEYS


def test_cross_chain_metadata_has_cost_surface_keys():
    assert {"gas_source_chain_usd", "gas_destination_chain_usd",
             "total_bridge_fee_usd",
             "total_round_trip_cost_pct"} <= CROSS_CHAIN_KEYS


def test_cross_chain_metadata_has_mev_class_input():
    """Gate 9 input — cross-chain MEV risk classification."""
    assert "cross_chain_mev_risk_class" in CROSS_CHAIN_KEYS


def test_cross_chain_metadata_has_audit_keys():
    assert {"verified_at_ts", "transfer_quote_source"} <= CROSS_CHAIN_KEYS


def test_cross_chain_metadata_total_key_count():
    """Sanity bound — D-5.0 expands to ~28 keys; if this trips, double-check
    against D5_REUSE_AUDIT.md §4.1 + D-5.0 implementation plan."""
    assert 25 <= len(CROSS_CHAIN_KEYS) <= 35


def test_validate_category_metadata_accepts_d5_keys():
    """Soft validator must not warn for any D-5.0 vocabulary key."""
    from arbicore.models.category_metadata import (
        reset_unknown_key_warnings, unknown_key_warnings,
        validate_category_metadata,
    )
    reset_unknown_key_warnings()
    fake_payload = {k: 0.0 for k in CROSS_CHAIN_KEYS}
    validate_category_metadata(
        OpportunityType.CROSS_CHAIN_ARBITRAGE, fake_payload)
    warnings = [w for w in unknown_key_warnings()
                if w["opportunity_type"] == "CROSS_CHAIN_ARBITRAGE"]
    assert warnings == []


# ============================================================================
# 2. SOURCE_REGISTRY entries
# ============================================================================

def test_source_registry_has_lifi_quote_real():
    from arbicore.data.provenance import SOURCE_REGISTRY, DataProvenance
    assert "lifi_quote_real" in SOURCE_REGISTRY
    assert SOURCE_REGISTRY["lifi_quote_real"].provenance == DataProvenance.REAL


def test_source_registry_has_stargate_quote_real():
    from arbicore.data.provenance import SOURCE_REGISTRY, DataProvenance
    assert "stargate_quote_real" in SOURCE_REGISTRY
    assert SOURCE_REGISTRY["stargate_quote_real"].provenance == \
        DataProvenance.REAL


def test_source_registry_has_all_six_chain_rpcs():
    from arbicore.data.provenance import SOURCE_REGISTRY, DataProvenance
    expected = {
        "ethereum_rpc_real", "arbitrum_rpc_real", "base_rpc_real",
        "optimism_rpc_real", "polygon_rpc_real", "solana_rpc_real",
    }
    assert expected <= set(SOURCE_REGISTRY.keys())
    for k in expected:
        assert SOURCE_REGISTRY[k].provenance == DataProvenance.REAL, \
            f"{k} must be REAL"


def test_source_registry_does_not_include_out_of_scope_bridges():
    """Operator scope decision: D-5.1 ships LI.FI + Stargate only.
    Out-of-scope bridges (Hop, Across, deBridge, Synapse, Wormhole, CCTP)
    must NOT have SOURCE_REGISTRY entries at D-5.0."""
    from arbicore.data.provenance import SOURCE_REGISTRY
    for excluded in ("hop_quote_real", "across_quote_real",
                       "debridge_quote_real", "synapse_quote_real",
                       "wormhole_quote_real", "cctp_quote_real"):
        assert excluded not in SOURCE_REGISTRY


def test_source_registry_does_not_include_out_of_scope_chains():
    """Operator scope decision: 6 chains only. BNB / Avalanche / Aptos /
    Cosmos chain-RPC entries must NOT be in the registry at D-5.0."""
    from arbicore.data.provenance import SOURCE_REGISTRY
    for excluded in ("bsc_rpc_real", "avalanche_rpc_real",
                       "aptos_rpc_real", "cosmos_rpc_real"):
        assert excluded not in SOURCE_REGISTRY


# ============================================================================
# 3. scanner_config seed defaults
# ============================================================================

def test_default_cross_chain_arb_config_exists():
    from arbicore.data.scanner_config_repo import DEFAULT_CROSS_CHAIN_ARB_CONFIG
    cfg = DEFAULT_CROSS_CHAIN_ARB_CONFIG
    assert cfg["_id"] == "cross_chain_arb"
    assert cfg["enabled"] is False
    assert "interval_s" in cfg


def test_default_config_bridges_include_lifi_and_stargate():
    from arbicore.data.scanner_config_repo import DEFAULT_CROSS_CHAIN_ARB_CONFIG
    bridges = DEFAULT_CROSS_CHAIN_ARB_CONFIG["bridges"]
    assert set(bridges.keys()) == {"lifi", "stargate"}, \
        "operator-scope: D-5.1 ships LI.FI + Stargate only"


def test_default_config_all_bridges_disabled():
    from arbicore.data.scanner_config_repo import DEFAULT_CROSS_CHAIN_ARB_CONFIG
    for name, b in DEFAULT_CROSS_CHAIN_ARB_CONFIG["bridges"].items():
        assert b["enabled"] is False, f"bridge {name} must default disabled"
        assert "credentials_env_var" in b
        assert "base_url" in b


def test_default_config_chains_are_exactly_six():
    from arbicore.data.scanner_config_repo import DEFAULT_CROSS_CHAIN_ARB_CONFIG
    chains = DEFAULT_CROSS_CHAIN_ARB_CONFIG["chains"]
    assert set(chains.keys()) == {
        "ethereum", "arbitrum", "base", "optimism", "polygon", "solana",
    }, "operator-scope: 6 chains only"


def test_default_config_all_chains_disabled_with_finality_metadata():
    from arbicore.data.scanner_config_repo import DEFAULT_CROSS_CHAIN_ARB_CONFIG
    for name, c in DEFAULT_CROSS_CHAIN_ARB_CONFIG["chains"].items():
        assert c["enabled"] is False, f"chain {name} must default disabled"
        # EVM chains have finality_blocks; Solana uses finality_slots
        assert "finality_blocks" in c or "finality_slots" in c
        assert "rpc_env_var" in c
        assert "gas_token" in c


def test_default_config_gate_thresholds_present():
    from arbicore.data.scanner_config_repo import DEFAULT_CROSS_CHAIN_ARB_CONFIG
    g = DEFAULT_CROSS_CHAIN_ARB_CONFIG["gate_thresholds"]
    assert "default" in g
    d = g["default"]
    for key in ("min_net_spread_after_costs_pct", "min_bridge_health_score",
                  "min_bridge_liveness_score", "max_chain_congestion_score",
                  "max_inbound_latency_p95_s", "min_confidence",
                  "max_cross_chain_mev_risk_class"):
        assert key in d
    # Per-bridge override for stargate (tighter latency p95)
    assert g["stargate"]["max_inbound_latency_p95_s"] < \
        d["max_inbound_latency_p95_s"]


def test_default_config_http_retry_block_present():
    """D-5.0 config seeds the http_retry parameters that the D-5.3
    TransferModelProvider will consume from arbicore/scanners/http_retry.py.
    This ensures operator-tunable parameters are exposed via /config PUT."""
    from arbicore.data.scanner_config_repo import DEFAULT_CROSS_CHAIN_ARB_CONFIG
    r = DEFAULT_CROSS_CHAIN_ARB_CONFIG["http_retry"]
    assert {"max_attempts", "initial_backoff_s",
             "max_backoff_s", "ttl_cache_s"} <= set(r.keys())


def test_default_config_transfer_model_block_present():
    from arbicore.data.scanner_config_repo import DEFAULT_CROSS_CHAIN_ARB_CONFIG
    t = DEFAULT_CROSS_CHAIN_ARB_CONFIG["transfer_model"]
    assert "max_slippage_estimate_pct" in t
    assert "default_notional_usd" in t
    assert "corridor_overrides" in t


def test_repo_get_returns_default_when_doc_missing():
    """ScannerConfigRepository.get('cross_chain_arb') must fall back to the
    DEFAULT_CROSS_CHAIN_ARB_CONFIG when no document exists in Mongo."""
    from arbicore.data.scanner_config_repo import (
        DEFAULT_CROSS_CHAIN_ARB_CONFIG, ScannerConfigRepository,
    )

    class _StubCollection:
        async def find_one(self, *a, **k):
            return None

    class _StubDb:
        def __getitem__(self, _name):
            return _StubCollection()
    import asyncio
    repo = ScannerConfigRepository(_StubDb())
    out = asyncio.run(repo.get("cross_chain_arb"))
    assert out.get("interval_s") == DEFAULT_CROSS_CHAIN_ARB_CONFIG["interval_s"]


# ============================================================================
# 4. scanner_state default
# ============================================================================

def test_scanner_state_get_defaults_to_disabled():
    from arbicore.data.scanner_config_repo import ScannerStateRepository

    class _StubCollection:
        async def find_one(self, *a, **k):
            return None

    class _StubDb:
        def __getitem__(self, _name):
            return _StubCollection()
    import asyncio
    repo = ScannerStateRepository(_StubDb())
    state = asyncio.run(repo.get("cross_chain_arb"))
    assert state.get("enabled") is False


# ============================================================================
# 5. Boot env gate (inert at D-5.0)
# ============================================================================

def test_boot_env_gate_constant_documented():
    """The composition module documents ARBICORE_SCANNER_CROSS_CHAIN_ARB
    as the operator-intent flag — even though the orchestrator lands at
    D-5.5, the gate is parseable at D-5.0 boot."""
    src = open(
        "/app/backend/arbicore/runtime/composition.py").read()
    assert "ARBICORE_SCANNER_CROSS_CHAIN_ARB" in src
    # And the gate must reference set_enabled "cross_chain_arb"
    assert 'set_enabled(\n            "cross_chain_arb"' in src or \
        'set_enabled("cross_chain_arb"' in src


# ============================================================================
# 6. Wave-progression — D-5.0 negatives flipped to positives at D-5.1
#    (the modules that didn't exist at D-5.0 now ship at D-5.1)
# ============================================================================

def test_cross_chain_scanner_module_ships_at_d5_1():
    """D-5.1 ships the orchestrator."""
    import arbicore.scanners.cross_chain_arbitrage.scanner as _m  # noqa: F401
    assert hasattr(_m, "CrossChainArbitrageScanner")


def test_cross_chain_verifier_ships_at_d5_1():
    import arbicore.scanners.cross_chain_arbitrage.verifier as _m  # noqa: F401
    assert hasattr(_m, "CrossChainOpportunityVerifier")


def test_cross_chain_sources_ship_at_d5_1():
    import arbicore.scanners.cross_chain_arbitrage.sources as _m  # noqa: F401
    assert hasattr(_m, "LiFiAggregatorSource")
    assert hasattr(_m, "StargateSource")


def test_cross_chain_transfer_provider_ships_at_d5_1():
    import arbicore.scanners.cross_chain_arbitrage.transfer_provider as _m
    assert hasattr(_m, "TransferModelProvider")
    assert hasattr(_m, "LiFiTransferProvider")


def test_chain_liveness_registry_ships_at_d5_1():
    import arbicore.scanners.cross_chain_arbitrage.chain_liveness as _m
    assert hasattr(_m, "ChainLivenessRegistry")


def test_cross_chain_arbitrage_package_ships_at_d5_1():
    import arbicore.scanners.cross_chain_arbitrage as _m  # noqa: F401
    assert hasattr(_m, "CrossChainArbitrageScanner")


def test_get_cross_chain_arb_scanner_factory_ships_at_d5_1():
    """The composition factory lands at D-5.1."""
    from arbicore.runtime import composition as comp
    assert hasattr(comp, "get_cross_chain_arb_scanner")


# ============================================================================
# 7. INV-1 / INV-2 / INV-3 still hold at D-5.1
# ============================================================================

def test_inv2_scanner_tree_emit_count_at_d5_1():
    """At D-5.1, the scanner-tree emit-site count rises to 5
    (cex_arb, funding_arb, dex_arb, launch_arb, cross_chain_arb).
    D-6.1 lifts it to 6 (flash_loan_arb). This assertion accepts both
    for forward-compat as subsequent waves ship."""
    from pathlib import Path
    scanners_root = Path("/app/backend/arbicore/scanners")
    emit_files = [
        f for f in scanners_root.rglob("scanner.py")
        if "self._bus.emit(" in f.read_text(encoding="utf-8")
    ]
    assert len(emit_files) in (5, 6), (
        f"INV-2: scanner-tree emit count must be 5 or 6; "
        f"got {len(emit_files)}: {[f.name for f in emit_files]}"
    )


def test_inv3_cross_chain_sources_classified_real():
    """All 8 D-5.0 substrate entries must carry REAL provenance.
    HINT-only classification at this layer would violate INV-3 (the
    verifier re-derives source_data_quality from leg source_id)."""
    from arbicore.data.provenance import SOURCE_REGISTRY, DataProvenance
    for source_id in ("lifi_quote_real", "stargate_quote_real",
                       "ethereum_rpc_real", "arbitrum_rpc_real",
                       "base_rpc_real", "optimism_rpc_real",
                       "polygon_rpc_real", "solana_rpc_real"):
        assert SOURCE_REGISTRY[source_id].provenance == DataProvenance.REAL


def test_inv1_cross_chain_package_present_at_d5_1():
    """The cross_chain_arbitrage package now exists. Only the verifier is
    authorised to construct CanonicalOpportunity inside the package."""
    from pathlib import Path
    p = Path("/app/backend/arbicore/scanners/cross_chain_arbitrage")
    assert p.exists()
    # Only verifier.py + scanner.py may reference the canonical builder
    auth = {"verifier.py"}
    for f in p.glob("*.py"):
        if f.name in {"__init__.py"}:
            continue
        text = f.read_text(encoding="utf-8")
        if "build_canonical_from_evidence" in text:
            assert f.name in auth, (
                f"INV-1: unauthorised canonical construction site: {f.name}")

