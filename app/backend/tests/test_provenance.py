"""Tests for the data provenance layer and learning gate."""
import pytest

from arbicore.data import (
    ContaminatedDataError,
    assert_learning_eligible,
    classify,
    is_learning_eligible,
)
from arbicore.models import DataProvenance


def test_real_sources():
    assert classify("uniswap_v3").provenance == DataProvenance.REAL
    assert classify("dexscreener").provenance == DataProvenance.REAL
    assert is_learning_eligible("uniswap_v3") is True


def test_contaminated_sources():
    assert classify("oneinch").provenance == DataProvenance.CONTAMINATED
    assert classify("balancer").provenance == DataProvenance.CONTAMINATED
    assert is_learning_eligible("balancer") is False


def test_dead_sources():
    for s in ("sushiswap", "quickswap", "pancakeswap", "curve"):
        assert classify(s).provenance == DataProvenance.DEAD
        assert is_learning_eligible(s) is False


def test_simulated_and_unknown():
    assert classify("simulated").provenance == DataProvenance.SIMULATED
    assert classify("totally_unknown").provenance == DataProvenance.SIMULATED
    assert is_learning_eligible("totally_unknown") is False


def test_provenance_enum_accepted():
    assert is_learning_eligible(DataProvenance.REAL) is True
    assert is_learning_eligible(DataProvenance.SIMULATED) is False


def test_assert_gate_raises_for_non_real():
    assert_learning_eligible(DataProvenance.REAL)  # no raise
    with pytest.raises(ContaminatedDataError):
        assert_learning_eligible("balancer")
