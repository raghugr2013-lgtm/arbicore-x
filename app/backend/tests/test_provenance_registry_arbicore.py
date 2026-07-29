"""Phase B — extended SOURCE_REGISTRY tests."""
from arbicore.data import (
    PHASE_B_NATIVE_SOURCES,
    SOURCE_REGISTRY,
    assert_learning_eligible,
    get_classification,
    is_learning_eligible,
    native_coverage_pct,
    registry_counts_by_provenance,
)
from arbicore.models import DataProvenance


def test_phase_b_native_sources_present():
    for name in PHASE_B_NATIVE_SOURCES:
        assert name in SOURCE_REGISTRY


def test_real_native_sources_count():
    real_native = [n for n in PHASE_B_NATIVE_SOURCES
                   if SOURCE_REGISTRY[n].provenance is DataProvenance.REAL]
    assert len(real_native) == 11


def test_simulated_native_sources_count():
    sim_native = [n for n in PHASE_B_NATIVE_SOURCES
                  if SOURCE_REGISTRY[n].provenance is DataProvenance.SIMULATED]
    assert len(sim_native) == 4


def test_unknown_source_returns_dead():
    assert get_classification("nonexistent_source") is DataProvenance.DEAD
    assert get_classification("") is DataProvenance.DEAD


def test_verified_real_is_learning_eligible():
    assert is_learning_eligible(DataProvenance.VERIFIED_REAL) is True


def test_known_source_learning_eligibility_via_helper():
    assert is_learning_eligible(get_classification("blockdag_rpc_primary"))
    assert not is_learning_eligible(get_classification("manual_config_balance"))


def test_no_verified_real_initially():
    counts = registry_counts_by_provenance()
    assert counts.get("VERIFIED_REAL", 0) == 0


def test_native_coverage_pct_is_full():
    # All 15 native sources are non-DEAD by design.
    assert native_coverage_pct() == 100.0


def test_assert_gate_raises_for_dead():
    import pytest
    from arbicore.data import ContaminatedDataError
    with pytest.raises(ContaminatedDataError):
        assert_learning_eligible(DataProvenance.DEAD)
    with pytest.raises(ContaminatedDataError):
        assert_learning_eligible(DataProvenance.SIMULATED)
