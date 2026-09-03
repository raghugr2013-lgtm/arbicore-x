"""Phase-3 F1–F4 — Strategy IR provenance / originality governance.

Deterministic. Proves the provenance classification (PUBLIC_RESEARCH / INTERNAL /
GENERATED / MUTATED / HYBRID / PROPRIETARY_EXTERNAL·RESTRICTED), the fail-closed
source_ref requirement for external-origin material, restricted-material quarantine,
identity-only projection (no alpha leak), and that none of this creates execution
authority. Registry cases use the local Mongo (like the sibling IR test).
"""
import asyncio

import pytest

from arbicore.strategy_ir.schema import (
    StrategyIR, StrategyProvenance, SourceClass, StrategyIRValidationError,
    EXTERNAL_ORIGIN_CLASSES, RESTRICTED_CLASSES, FORBIDDEN_KEYS)
from arbicore.strategy_ir.adapter import candidate_to_opportunity_hypothesis


def _ir(source_class, *, source_ref="", lineage=None, **kw):
    base = dict(
        strategy_type="dex_dex",
        parameters={"pair": "WETH/USDC", "min_edge_bps": 15},
        constraints={"max_notional_usd": 50_000, "max_hops": 2},
        required_capabilities=["base", "flash_aave_v3"],
        route_hints=[{"dex": "aerodrome", "token_in": "WETH", "token_out": "USDC"}],
        provenance=StrategyProvenance(source="strategy_factory", source_ref=source_ref,
                                      trust=0.7, confidence=0.6),
        source_class=source_class,
        lineage=lineage or [],
    )
    base.update(kw)
    return StrategyIR(**base)


# ── classification: source_ref requirement (fail-closed for external origin) ──
def test_public_research_with_source_ref_ok():
    ir = _ir(SourceClass.PUBLIC_RESEARCH,
             source_ref="https://arxiv.org/abs/xxxx").validate_non_executable()
    assert ir.validate_provenance_policy().source_class == SourceClass.PUBLIC_RESEARCH
    assert not ir.is_restricted()


def test_internal_needs_no_source_ref():
    ir = _ir(SourceClass.INTERNAL).validate_non_executable()
    assert ir.validate_provenance_policy() is ir
    assert SourceClass.INTERNAL not in EXTERNAL_ORIGIN_CLASSES


def test_generated_needs_no_source_ref():
    ir = _ir(SourceClass.GENERATED).validate_non_executable()
    assert ir.validate_provenance_policy() is ir


def test_mutated_needs_no_source_ref():
    ir = _ir(SourceClass.MUTATED).validate_non_executable()
    assert ir.validate_provenance_policy() is ir


def test_hybrid_requires_source_ref():
    missing = _ir(SourceClass.HYBRID).validate_non_executable()
    with pytest.raises(StrategyIRValidationError):
        missing.validate_provenance_policy()
    ok = _ir(SourceClass.HYBRID, source_ref="https://example.org/x").validate_non_executable()
    assert ok.validate_provenance_policy() is ok


@pytest.mark.parametrize("sc", [SourceClass.PUBLIC_RESEARCH, SourceClass.EXTERNAL,
                                SourceClass.HYBRID, SourceClass.PROPRIETARY_EXTERNAL,
                                SourceClass.RESTRICTED])
def test_external_origin_missing_source_ref_rejected(sc):
    ir = _ir(sc).validate_non_executable()
    with pytest.raises(StrategyIRValidationError):
        ir.validate_provenance_policy()


# ── restricted / proprietary material ──
@pytest.mark.parametrize("sc", [SourceClass.PROPRIETARY_EXTERNAL, SourceClass.RESTRICTED])
def test_restricted_flagged_and_not_adapter_eligible(sc):
    ir = _ir(sc, source_ref="https://vendor.example/private").validate_non_executable()
    assert ir.is_restricted() and sc in RESTRICTED_CLASSES
    with pytest.raises(StrategyIRValidationError):
        candidate_to_opportunity_hypothesis(ir)   # quarantined → not eligible


def test_non_restricted_is_adapter_eligible_but_non_executable():
    ir = _ir(SourceClass.PUBLIC_RESEARCH,
             source_ref="https://arxiv.org/abs/xxxx").validate_non_executable()
    hyp = candidate_to_opportunity_hypothesis(ir)
    assert hyp["executable"] is False and hyp["confidential"] is True
    assert not FORBIDDEN_KEYS.intersection({k.lower() for k in hyp})


# ── F2 identity-only projection: no proprietary alpha leaks ──
def test_public_view_excludes_alpha():
    ir = _ir(SourceClass.PUBLIC_RESEARCH,
             source_ref="https://arxiv.org/abs/xxxx",
             lineage=["sfp_parent"]).validate_non_executable()
    view = ir.public_view()
    for alpha in ("parameters", "constraints", "route_hints", "required_capabilities"):
        assert alpha not in view
    assert view["strategy_fingerprint"].startswith("sfp_")
    assert view["lineage"] == ["sfp_parent"]           # lineage preserved
    assert view["provenance"]["source_ref"] == "https://arxiv.org/abs/xxxx"


# ── registry: quarantine + provenance/lineage persistence (local Mongo) ──
def test_registry_quarantines_restricted_and_persists_provenance():
    from arbicore.strategy_ir import registry as reg

    async def _run():
        ir = _ir(SourceClass.PROPRIETARY_EXTERNAL,
                 source_ref="https://vendor.example/private",
                 lineage=["sfp_root"],
                 parameters={"pair": f"QTN/{id(object())}"}).validate_non_executable()
        await reg._registry.delete_many({"strategy_fingerprint": ir.strategy_fingerprint})
        await reg._candidates.delete_many({"strategy_fingerprint": ir.strategy_fingerprint})
        r = await reg.register(ir)
        assert r["restricted"] is True
        assert r["lifecycle_state"] == reg.LIFECYCLE_QUARANTINED
        entry = await reg.get_registry_entry(r["strategy_id"])
        assert entry["lifecycle_state"] == reg.LIFECYCLE_QUARANTINED
        assert entry["lineage"] == ["sfp_root"]                       # lineage kept
        assert entry["provenance"]["source_ref"] == "https://vendor.example/private"
        cand = await reg.get_candidate(r["strategy_id"])
        assert cand["confidential"] is True and cand["executable"] is False
        await reg._registry.delete_many({"strategy_fingerprint": ir.strategy_fingerprint})
        await reg._candidates.delete_many({"strategy_fingerprint": ir.strategy_fingerprint})

    asyncio.get_event_loop().run_until_complete(_run())


def test_registry_non_restricted_ingested_state():
    from arbicore.strategy_ir import registry as reg

    async def _run():
        ir = _ir(SourceClass.PUBLIC_RESEARCH, source_ref="https://arxiv.org/abs/y",
                 parameters={"pair": f"IN/{id(object())}"}).validate_non_executable()
        await reg._registry.delete_many({"strategy_fingerprint": ir.strategy_fingerprint})
        await reg._candidates.delete_many({"strategy_fingerprint": ir.strategy_fingerprint})
        r = await reg.register(ir)
        assert r["restricted"] is False
        assert r["lifecycle_state"] == reg.LIFECYCLE_INGESTED
        await reg._registry.delete_many({"strategy_fingerprint": ir.strategy_fingerprint})
        await reg._candidates.delete_many({"strategy_fingerprint": ir.strategy_fingerprint})

    asyncio.get_event_loop().run_until_complete(_run())


# ── no execution-authority impact ──
def test_provenance_governance_creates_no_execution_authority():
    ir = _ir(SourceClass.PUBLIC_RESEARCH,
             source_ref="https://arxiv.org/abs/xxxx").validate_non_executable()
    # neither the projection nor the enum set leaks an execution key
    keys = set(ir.public_view().keys())
    assert not FORBIDDEN_KEYS.intersection({k.lower() for k in keys})
    assert RESTRICTED_CLASSES <= set(SourceClass)
