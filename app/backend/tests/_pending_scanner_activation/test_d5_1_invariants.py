"""D-5.1 — Tree-wide INV-1/INV-2/INV-3 invariants and integration tests."""
from __future__ import annotations

from pathlib import Path

import pytest


SCANNER_ROOT = Path("/app/backend/arbicore/scanners")
CROSS_CHAIN_PKG = SCANNER_ROOT / "cross_chain_arbitrage"


def test_emit_site_count_is_five():
    """INV-2: scanner-tree carries one ``self._bus.emit`` site per
    scanner family. D-5.1 raised it to 5; D-6.1 raises to 6."""
    emit_files = [
        f for f in SCANNER_ROOT.rglob("scanner.py")
        if "self._bus.emit(" in f.read_text(encoding="utf-8")
    ]
    assert len(emit_files) in (5, 6)
    names = sorted(f.parent.name for f in emit_files)
    if len(emit_files) == 5:
        assert names == ["cex_arbitrage", "cross_chain_arbitrage",
                          "dex_arbitrage", "funding_arbitrage",
                          "launch_arbitrage"]
    else:
        assert names == ["cex_arbitrage", "cross_chain_arbitrage",
                          "dex_arbitrage", "flash_loan_arbitrage",
                          "funding_arbitrage", "launch_arbitrage"]


def test_cross_chain_package_files_inv2_clean():
    """INV-2: every non-scanner.py module under cross_chain_arbitrage
    must NOT import EmissionBus or call ``_bus.emit``."""
    for f in CROSS_CHAIN_PKG.glob("*.py"):
        if f.name == "scanner.py":
            continue
        text = f.read_text(encoding="utf-8")
        assert "from ...emission_bus" not in text, (
            f"{f.name}: imports EmissionBus")
        assert "_bus.emit(" not in text, f"{f.name}: _bus.emit call"


def test_only_verifier_constructs_canonical():
    """INV-1: only verifier.py may invoke
    ``build_canonical_from_evidence``."""
    for f in CROSS_CHAIN_PKG.glob("*.py"):
        if f.name in {"__init__.py", "verifier.py"}:
            continue
        text = f.read_text(encoding="utf-8")
        assert "build_canonical_from_evidence" not in text, (
            f"{f.name}: canonical construction outside verifier")
        # And no direct CanonicalOpportunity(...) construction.
        # ``Optional[CanonicalOpportunity]`` annotations are fine; explicit
        # constructor calls are not.
        assert "CanonicalOpportunity(" not in text, (
            f"{f.name}: raw CanonicalOpportunity(...) construction")


def test_inv3_d5_substrate_entries_all_real():
    from arbicore.data.provenance import SOURCE_REGISTRY, DataProvenance
    for src in ("lifi_quote_real", "stargate_quote_real",
                  "ethereum_rpc_real", "arbitrum_rpc_real",
                  "base_rpc_real", "optimism_rpc_real",
                  "polygon_rpc_real", "solana_rpc_real"):
        assert SOURCE_REGISTRY[src].provenance == DataProvenance.REAL


def test_d5_1_package_re_exports_everything():
    """The package __init__ must re-export the orchestrator + verifier +
    sources + intelligence + transfer provider."""
    import arbicore.scanners.cross_chain_arbitrage as pkg
    for name in (
        "CrossChainArbitrageScanner", "CrossChainOpportunityVerifier",
        "LiFiAggregatorSource", "StargateSource",
        "ChainLivenessRegistry", "BridgeRouteCatalog", "MevRiskScorer",
        "LiFiTransferProvider", "TransferModelProvider",
        "BridgeEconomicsAssessor",
        "CrossChainGate7BridgeLiveness", "CrossChainGate8ChainLiveness",
        "CrossChainGate9CrossChainMev",
    ):
        assert hasattr(pkg, name), f"package missing {name}"


def test_inv3_no_orchestrator_overrides_provenance():
    """INV-3: orchestrators must rely on verifier's leg-derived
    provenance — never overwrite ``source_data_quality`` directly."""
    for f in SCANNER_ROOT.rglob("scanner.py"):
        text = f.read_text(encoding="utf-8")
        assert "source_data_quality =" not in text, (
            f"{f.name}: scanner overrides source_data_quality")


def test_routes_register_all_d5_1_endpoints():
    """All 11 D-5.1 endpoints must be wired into the router."""
    from arbicore.routes.scanners import router
    paths = {r.path for r in router.routes
              if "cross_chain_arb" in r.path}
    expected = {
        "/api/arbicore/scanners/cross_chain_arb/status",
        "/api/arbicore/scanners/cross_chain_arb/kill",
        "/api/arbicore/scanners/cross_chain_arb/resume",
        "/api/arbicore/scanners/cross_chain_arb/config",
        "/api/arbicore/scanners/cross_chain_arb/gate-analysis",
        "/api/arbicore/scanners/cross_chain_arb/source-health",
        "/api/arbicore/scanners/cross_chain_arb/bridges/{bridge_id}/enable",
        "/api/arbicore/scanners/cross_chain_arb/bridges/{bridge_id}/disable",
        "/api/arbicore/scanners/cross_chain_arb/chains/{chain_id}/enable",
        "/api/arbicore/scanners/cross_chain_arb/chains/{chain_id}/disable",
        "/api/arbicore/scanners/cross_chain_arb/preview",
    }
    assert expected <= paths


def test_composition_factory_present_and_signature():
    from arbicore.runtime import composition
    assert hasattr(composition, "get_cross_chain_arb_scanner")
    # CrossChainArbitrageScanner import path used by the factory.
    src = open(composition.__file__).read()
    assert "CrossChainArbitrageScanner" in src
    assert "ARBICORE_SCANNER_CROSS_CHAIN_ARB" in src
