"""Phase C Wave 2 — Concrete StateObservers."""
import asyncio

from arbicore.learning.concrete.state_observers import (
    CategoryMetadataStateObserver,
    DEFAULT_OBSERVER_CONFIGS,
    make_default_observer,
)
from arbicore.models import (
    CanonicalOpportunity,
    DataProvenance,
    OpportunityType,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_default_observer_for_every_opportunity_type():
    for t in OpportunityType:
        obs = make_default_observer(t)
        assert obs.opportunity_type is t


def test_observer_rejects_wrong_type():
    obs = make_default_observer(OpportunityType.CEX_ARBITRAGE)
    opp = CanonicalOpportunity(
        opportunity_type=OpportunityType.DEX_ARBITRAGE,
        asset="X",
    )
    assert _run(obs.fetch_state(opp)) is None


def test_cex_observer_uses_metadata_primary_metric():
    obs = make_default_observer(OpportunityType.CEX_ARBITRAGE)
    opp = CanonicalOpportunity(
        opportunity_type=OpportunityType.CEX_ARBITRAGE,
        asset="A/B",
        subject_id="subj-cex",
        source_data_quality=DataProvenance.REAL,
        category_metadata={"best_bid_price": 1.5, "best_ask_price": 1.6,
                            "profitable_buyer_depth_usd": 500.0},
    )
    state = _run(obs.fetch_state(opp))
    assert state is not None
    assert state.primary_metric == 1.5
    assert state.secondary_metrics.get("best_ask") == 1.6
    assert state.secondary_metrics.get("depth_usd") == 500.0
    assert state.provenance is DataProvenance.REAL
    assert state.source == "category_metadata_observer"


def test_observer_falls_back_to_mid_price():
    """No metadata, but buy/sell prices set — mid price used."""
    obs = make_default_observer(OpportunityType.CEX_ARBITRAGE)
    opp = CanonicalOpportunity(
        opportunity_type=OpportunityType.CEX_ARBITRAGE,
        asset="A/B",
        buy_price=1.0,
        sell_price=2.0,
        source_data_quality=DataProvenance.REAL,
    )
    state = _run(obs.fetch_state(opp))
    assert state is not None
    assert state.primary_metric == 1.5


def test_observer_returns_none_with_no_metric_data():
    obs = make_default_observer(OpportunityType.CEX_ARBITRAGE)
    opp = CanonicalOpportunity(
        opportunity_type=OpportunityType.CEX_ARBITRAGE,
        asset="A/B",
    )
    assert _run(obs.fetch_state(opp)) is None


def test_flash_loan_observer_is_dormant_by_default():
    obs = make_default_observer(OpportunityType.FLASH_LOAN_ARBITRAGE)
    opp = CanonicalOpportunity(
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        asset="X",
        source_data_quality=DataProvenance.REAL,
    )
    # No primary_metric_key configured + no buy/sell prices → None
    assert _run(obs.fetch_state(opp)) is None


def test_funding_observer_reads_funding_rate():
    obs = make_default_observer(OpportunityType.FUNDING_ARBITRAGE)
    opp = CanonicalOpportunity(
        opportunity_type=OpportunityType.FUNDING_ARBITRAGE,
        asset="X",
        subject_id="subj-fund",
        source_data_quality=DataProvenance.REAL,
        category_metadata={
            "funding_rate_pct": 0.05,
            "open_interest_usd": 1e6,
            "perp_index_basis_pct": 0.1,
        },
    )
    state = _run(obs.fetch_state(opp))
    assert state.primary_metric == 0.05
    assert state.secondary_metrics["open_interest"] == 1e6


def test_configurable_observer_with_custom_key():
    obs = CategoryMetadataStateObserver(
        opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
        primary_metric_key="presale_price",
        secondary_metric_keys={"public": "public_price"},
    )
    opp = CanonicalOpportunity(
        opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
        asset="X",
        source_data_quality=DataProvenance.REAL,
        category_metadata={"presale_price": 0.5, "public_price": 1.0},
    )
    state = _run(obs.fetch_state(opp))
    assert state.primary_metric == 0.5
    assert state.secondary_metrics["public"] == 1.0
