"""Phase B — OutcomeRepository ABC contract test (in-memory mock)."""
import asyncio
import time

from arbicore.data._inmemory import InMemoryOutcomeRepository
from arbicore.data.outcome_repo import OutcomeRow, StateRow, make_outcome_rows_for


def _row(**kw):
    base = dict(id="opp-1::5m", opportunity_id="opp-1", subject_id="S-1",
                horizon_label="5m", horizon_s=300,
                due_at=time.time() - 1.0, provenance="REAL")
    base.update(kw)
    return OutcomeRow(**base)


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_upsert_and_list_due():
    repo = InMemoryOutcomeRepository()
    _run(repo.upsert_outcome(_row()))
    due = _run(repo.list_due(now_ts=time.time()))
    assert len(due) == 1
    assert due[0].opportunity_id == "opp-1"


def test_only_insert_does_not_overwrite():
    repo = InMemoryOutcomeRepository()
    r = _row(evaluated=True, realized_metric=1.234)
    _run(repo.upsert_outcome(r))
    replaced = _row(evaluated=False, realized_metric=9.99)
    written = _run(repo.upsert_outcome(replaced, only_insert=True))
    assert written is False
    rows = _run(repo.list_for_subject("S-1"))
    assert len(rows) == 1
    assert rows[0].evaluated is True
    assert rows[0].realized_metric == 1.234


def test_state_snapshot_append_and_latest():
    repo = InMemoryOutcomeRepository()
    t = time.time()
    _run(repo.append_state_snapshot(StateRow(
        subject_id="S-1", opportunity_type="CEX_ARBITRAGE",
        captured_at_ts=t - 10, primary_metric=1.0,
        source="coinstore_public_depth", provenance="REAL",
    )))
    _run(repo.append_state_snapshot(StateRow(
        subject_id="S-1", opportunity_type="CEX_ARBITRAGE",
        captured_at_ts=t, primary_metric=1.5,
        source="coinstore_public_depth", provenance="REAL",
    )))
    latest = _run(repo.latest_state("S-1"))
    assert latest is not None
    assert latest.primary_metric == 1.5
    series = _run(repo.list_states("S-1", t0=t - 100, t1=t + 100))
    assert len(series) == 2


def test_provenance_filter_on_list_for_subject():
    from arbicore.models import DataProvenance
    repo = InMemoryOutcomeRepository()
    _run(repo.upsert_outcome(_row(id="r-real", provenance="REAL")))
    _run(repo.upsert_outcome(_row(id="r-sim", provenance="SIMULATED")))
    real_only = _run(repo.list_for_subject(
        "S-1",
        provenance_filter=frozenset({DataProvenance.REAL, DataProvenance.VERIFIED_REAL}),
    ))
    assert {r.id for r in real_only} == {"r-real"}


def test_make_outcome_rows_horizons():
    rows = make_outcome_rows_for("opp-1", subject_id="S-1", emission_ts=1000.0)
    labels = [r.horizon_label for r in rows]
    assert labels == ["5m", "15m", "1h", "6h", "24h"]
    assert all(r.evaluated is False for r in rows)


def test_count_outcomes_by_evaluated():
    repo = InMemoryOutcomeRepository()
    _run(repo.upsert_outcome(_row(id="a", evaluated=True)))
    _run(repo.upsert_outcome(_row(id="b")))
    counts = _run(repo.count_outcomes_by_evaluated())
    assert counts == {"evaluated": 1, "unevaluated": 1}
