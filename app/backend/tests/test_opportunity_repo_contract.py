"""Phase B — OpportunityRepository ABC contract test (in-memory mock).

Uses asyncio.run() wrappers so no pytest-asyncio dependency is required.
"""
import asyncio

import pytest

from arbicore.data._inmemory import InMemoryOpportunityRepository
from arbicore.models import (
    CanonicalOpportunity,
    DataProvenance,
    OpportunityStatus,
    OpportunityType,
)


def _opp(**kw):
    base = dict(opportunity_type=OpportunityType.CEX_ARBITRAGE, asset="BDAG/USDT",
                source_data_quality=DataProvenance.REAL,
                subject_id="BDAG/USDT-CEX-SPOT")
    base.update(kw)
    return CanonicalOpportunity(**base)


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_upsert_and_get_roundtrip():
    repo = InMemoryOpportunityRepository()
    o = _opp(opportunity_id="opp-001")
    _run(repo.upsert(o))
    fetched = _run(repo.get("opp-001"))
    assert fetched is not None
    assert fetched.opportunity_id == "opp-001"
    assert fetched.subject_id == "BDAG/USDT-CEX-SPOT"


def test_upsert_generates_id_if_absent():
    repo = InMemoryOpportunityRepository()
    o = _opp()
    o.opportunity_id = ""
    _run(repo.upsert(o))
    assert o.opportunity_id and len(o.opportunity_id) >= 16


def test_upsert_rejects_dead_provenance():
    repo = InMemoryOpportunityRepository()
    with pytest.raises(ValueError):
        _run(repo.upsert(_opp(source_data_quality=DataProvenance.DEAD)))


def test_list_for_subject_provenance_filter():
    repo = InMemoryOpportunityRepository()
    _run(repo.upsert(_opp(opportunity_id="o-real",
                          source_data_quality=DataProvenance.REAL)))
    _run(repo.upsert(_opp(opportunity_id="o-sim",
                          source_data_quality=DataProvenance.SIMULATED)))
    all_for_subject = _run(repo.list_for_subject("BDAG/USDT-CEX-SPOT"))
    assert len(all_for_subject) == 2
    real_only = _run(repo.list_for_subject(
        "BDAG/USDT-CEX-SPOT",
        provenance_filter=frozenset({DataProvenance.REAL, DataProvenance.VERIFIED_REAL}),
    ))
    assert len(real_only) == 1
    assert real_only[0].opportunity_id == "o-real"


def test_find_filter_by_type_and_status():
    repo = InMemoryOpportunityRepository()
    o1 = _opp(opportunity_id="o-cex-1", opportunity_type=OpportunityType.CEX_ARBITRAGE)
    o2 = _opp(opportunity_id="o-dex-1", opportunity_type=OpportunityType.DEX_ARBITRAGE)
    _run(repo.upsert(o1))
    _run(repo.upsert(o2))
    cex = _run(repo.find({"opportunity_type": OpportunityType.CEX_ARBITRAGE}))
    assert len(cex) == 1 and cex[0].opportunity_id == "o-cex-1"


def test_count_by_type_status():
    repo = InMemoryOpportunityRepository()
    _run(repo.upsert(_opp(opportunity_id="a")))
    _run(repo.upsert(_opp(opportunity_id="b", status=OpportunityStatus.VALIDATED)))
    counts = _run(repo.count_by_type_status())
    assert counts["CEX_ARBITRAGE"]["candidate"] == 1
    assert counts["CEX_ARBITRAGE"]["validated"] == 1
