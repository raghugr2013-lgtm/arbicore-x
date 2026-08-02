"""Phase B — StateObserverRegistry contract test."""
import asyncio

import pytest

from arbicore.data import (
    NullStateObserver,
    OpportunityState,
    StateObserver,
    StateObserverRegistry,
)
from arbicore.models import (
    CanonicalOpportunity,
    DataProvenance,
    OpportunityType,
)


class _DummyObserver(StateObserver):
    opportunity_type = OpportunityType.CEX_ARBITRAGE

    async def fetch_state(self, opp):
        return OpportunityState(
            subject_id=opp.subject_id or "?",
            opportunity_type=self.opportunity_type,
            captured_at_ts=1234567.0,
            primary_metric=0.001,
            provenance=DataProvenance.REAL,
            source="coinstore_public_depth",
        )


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_unregistered_returns_null_observer():
    reg = StateObserverRegistry()
    observer = reg.get(OpportunityType.LAUNCH_ARBITRAGE)
    assert isinstance(observer, NullStateObserver)
    assert observer.opportunity_type is OpportunityType.LAUNCH_ARBITRAGE


def test_register_and_get():
    reg = StateObserverRegistry()
    reg.register(_DummyObserver())
    assert reg.is_registered(OpportunityType.CEX_ARBITRAGE)
    observer = reg.get(OpportunityType.CEX_ARBITRAGE)
    assert isinstance(observer, _DummyObserver)


def test_register_rejects_non_state_observer():
    reg = StateObserverRegistry()
    with pytest.raises(TypeError):
        reg.register("not an observer")  # type: ignore[arg-type]


def test_null_observer_returns_none():
    null = NullStateObserver(OpportunityType.FUNDING_ARBITRAGE)
    opp = CanonicalOpportunity(opportunity_type=OpportunityType.FUNDING_ARBITRAGE, asset="X")
    assert _run(null.fetch_state(opp)) is None


def test_dummy_observer_carries_provenance_tag():
    obs = _DummyObserver()
    opp = CanonicalOpportunity(opportunity_type=OpportunityType.CEX_ARBITRAGE,
                               asset="BDAG/USDT", subject_id="S-1")
    state = _run(obs.fetch_state(opp))
    assert state.provenance is DataProvenance.REAL
    assert state.source == "coinstore_public_depth"
