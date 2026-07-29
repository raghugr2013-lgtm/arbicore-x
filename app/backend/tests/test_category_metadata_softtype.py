"""Phase B — Soft-typed category_metadata validator tests."""
import logging

from arbicore.models import (
    CanonicalOpportunity,
    KNOWN_CATEGORY_METADATA_KEYS,
    OpportunityType,
    reset_unknown_key_warnings,
    unknown_key_warnings,
)


def test_every_opportunity_type_has_registry_entry():
    for t in OpportunityType:
        assert t in KNOWN_CATEGORY_METADATA_KEYS


def test_unknown_key_does_not_raise():
    # Validator never raises.
    CanonicalOpportunity(
        opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
        asset="X",
        category_metadata={"a_brand_new_signal": 42},
    )


def test_dedup_works_per_type_and_key(caplog):
    reset_unknown_key_warnings()
    with caplog.at_level(logging.WARNING, logger="arbicore.category_metadata"):
        for _ in range(20):
            CanonicalOpportunity(
                opportunity_type=OpportunityType.DEX_ARBITRAGE,
                asset="X",
                category_metadata={"a_dex_specific_unknown": 1},
            )
        # Same key under a different type emits its own (one) warning.
        for _ in range(5):
            CanonicalOpportunity(
                opportunity_type=OpportunityType.FUNDING_ARBITRAGE,
                asset="Y",
                category_metadata={"a_dex_specific_unknown": 1},
            )
    relevant = [r for r in caplog.records if "a_dex_specific_unknown" in r.getMessage()]
    assert len(relevant) == 2
    keys_seen = {w["opportunity_type"] for w in unknown_key_warnings()
                 if w["key"] == "a_dex_specific_unknown"}
    assert keys_seen == {OpportunityType.DEX_ARBITRAGE.value,
                          OpportunityType.FUNDING_ARBITRAGE.value}
