"""D-5.2 Completion — composition auto-attach + invariants tests."""
from __future__ import annotations

from pathlib import Path


def test_composition_imports_d5_2_modules():
    """Composition references the new opt-in providers + loader."""
    from arbicore.runtime import composition
    src = open(composition.__file__).read()
    assert "LiFiTransferProvider" in src
    assert "StargateTransferProvider" in src
    assert "RpcChainLivenessLoader" in src


def test_composition_uses_register_transfer_provider():
    """Composition opt-in attach uses the D-5.2 multi-bridge API."""
    from arbicore.runtime import composition
    src = open(composition.__file__).read()
    assert "register_transfer_provider(" in src
    assert '"lifi"' in src or "'lifi'" in src
    assert '"stargate"' in src or "'stargate'" in src


def test_composition_attaches_rpc_chain_liveness_loader():
    from arbicore.runtime import composition
    src = open(composition.__file__).read()
    assert "set_chain_liveness_loader(" in src
    assert "RpcChainLivenessLoader(" in src


def test_d5_2_no_new_top_level_modules():
    """Absorption discipline: no new top-level modules under
    ``arbicore/scanners/cross_chain_arbitrage/`` beyond the 9 shipped
    in D-5.1. D-5.2 lives entirely inside existing files."""
    pkg = Path("/app/backend/arbicore/scanners/cross_chain_arbitrage")
    py_files = sorted(f.name for f in pkg.glob("*.py"))
    assert py_files == sorted([
        "__init__.py", "bridge_intelligence.py", "chain_liveness.py",
        "economics.py", "filter.py", "scanner.py",
        "sources.py", "transfer_provider.py", "verifier.py",
    ]), f"unexpected files: {py_files}"


def test_d5_2_no_new_databases_or_workers():
    """The D-5.2 wave introduced no new background workers, no new
    DB collections, no separate dashboards."""
    pkg = Path("/app/backend/arbicore/scanners/cross_chain_arbitrage")
    for f in pkg.glob("*.py"):
        text = f.read_text(encoding="utf-8")
        # No motor/AsyncIOMotorClient construction at this layer.
        assert "AsyncIOMotorClient(" not in text, (
            f"{f.name}: forbidden direct Mongo client construction")
        # No asyncio.create_task at module-import scope (workers should
        # be lifecycled by the scanner orchestrator).
        for ln in text.splitlines():
            stripped = ln.lstrip()
            if stripped.startswith("#") or stripped.startswith('"'):
                continue
            assert not (stripped.startswith("asyncio.create_task(")
                        and ln.startswith(stripped)), (
                f"{f.name}: module-level create_task forbidden")


def test_d5_2_inv2_emit_count_still_five():
    """INV-2: at D-5.2 emit count is 5; D-6.1 raises it to 6. Both ok."""
    scanners = Path("/app/backend/arbicore/scanners")
    emit_files = [f for f in scanners.rglob("scanner.py")
                  if "self._bus.emit(" in f.read_text(encoding="utf-8")]
    assert len(emit_files) in (5, 6)


def test_d5_2_package_reexports_complete():
    """Both new D-5.2 surfaces re-exported through the package init."""
    import arbicore.scanners.cross_chain_arbitrage as pkg
    assert hasattr(pkg, "StargateTransferProvider")
    assert hasattr(pkg, "RpcChainLivenessLoader")


def test_d5_2_inv3_provenance_unchanged():
    """INV-3: both lifi_quote_real and stargate_quote_real remain REAL
    after D-5.2 (no provenance regressions)."""
    from arbicore.data.provenance import SOURCE_REGISTRY, DataProvenance
    assert SOURCE_REGISTRY["lifi_quote_real"].provenance == DataProvenance.REAL
    assert SOURCE_REGISTRY["stargate_quote_real"].provenance == \
        DataProvenance.REAL


def test_d5_2_only_verifier_constructs_canonical():
    """INV-1: only verifier.py may invoke build_canonical_from_evidence
    inside the cross_chain_arbitrage package."""
    pkg = Path("/app/backend/arbicore/scanners/cross_chain_arbitrage")
    for f in pkg.glob("*.py"):
        if f.name in {"__init__.py", "verifier.py"}:
            continue
        text = f.read_text(encoding="utf-8")
        assert "build_canonical_from_evidence" not in text, (
            f"{f.name}: canonical construction outside verifier")
        assert "CanonicalOpportunity(" not in text, (
            f"{f.name}: raw CanonicalOpportunity construction")
