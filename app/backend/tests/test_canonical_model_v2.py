"""Phase B — CanonicalOpportunity v2 schema tests."""
from __future__ import annotations

from arbicore.models import (
    CanonicalOpportunity,
    DataProvenance,
    OpportunityType,
    reset_unknown_key_warnings,
    unknown_key_warnings,
)


def _bdag_opp(**kw):
    base = dict(opportunity_type=OpportunityType.CEX_ARBITRAGE, asset="BDAG/USDT")
    base.update(kw)
    return CanonicalOpportunity(**base)


def test_optional_trade_exec_fields_default_none():
    o = _bdag_opp()
    assert o.buy_venue is None
    assert o.sell_venue is None
    assert o.buy_price is None
    assert o.sell_price is None
    assert o.spread_pct is None
    assert o.expected_profit_usd is None
    assert o.capital_required_usd is None


def test_subject_id_round_trips():
    o = _bdag_opp(subject_id="BDAG/USDT-CEX-SPOT")
    d = o.model_dump(mode="json")
    o2 = CanonicalOpportunity.model_validate(d)
    assert o2.subject_id == "BDAG/USDT-CEX-SPOT"


def test_category_metadata_known_key_silent():
    reset_unknown_key_warnings()
    _bdag_opp(category_metadata={"best_bid_price": 0.001, "fee_drag_pct": 0.5})
    assert unknown_key_warnings() == []


def test_category_metadata_unknown_key_warns_once(caplog):
    import logging
    reset_unknown_key_warnings()
    with caplog.at_level(logging.WARNING, logger="arbicore.category_metadata"):
        for _ in range(50):
            _bdag_opp(category_metadata={"definitely_not_a_known_key": "x"})
    relevant = [r for r in caplog.records if "definitely_not_a_known_key" in r.getMessage()]
    assert len(relevant) == 1
    audit = unknown_key_warnings()
    assert any(w["key"] == "definitely_not_a_known_key" for w in audit)


def test_market_regime_tags_optional_list():
    o = _bdag_opp(market_regime_tags=["high_volatility", "thin_liquidity"])
    assert o.market_regime_tags == ["high_volatility", "thin_liquidity"]


def test_learning_eligibility_includes_verified_real():
    o_real = _bdag_opp(source_data_quality=DataProvenance.REAL)
    o_verified = _bdag_opp(source_data_quality=DataProvenance.VERIFIED_REAL)
    o_sim = _bdag_opp(source_data_quality=DataProvenance.SIMULATED)
    assert o_real.is_learning_eligible
    assert o_verified.is_learning_eligible
    assert not o_sim.is_learning_eligible
