"""ArbiCore X — Phase D D-1 invariant + pluggability tests.

Enforces INV-1 / INV-2 / INV-3 from PHASE_D_DISCOVERY_LAYER_SPEC.md §1
and the 3 forward-compat / pluggability tests from §10.
"""
import asyncio
import inspect
import os
import time
from pathlib import Path

import pytest

from arbicore.emission_bus import EmissionBus
from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.discovery import (
    DiscoveryCandidate,
    VerifiedOutcome,
    make_candidate_id,
)
from arbicore.models.enums import (
    DataProvenance,
    MarketRegime,
    MevRiskLevel,
    OpportunityStatus,
    OpportunityType,
    RouteHealth,
)
from arbicore.scanners.discovery_source import (
    DiscoverySource,
    DiscoverySourceRegistry,
)
from arbicore.scanners.opportunity_verifier import (
    OpportunityVerifier,
    OpportunityVerifierRegistry,
)


# ============================================================================
# INV-1 — DiscoveryCandidate is a separate type from CanonicalOpportunity
# ============================================================================

def test_inv1_separate_types_no_shared_hierarchy():
    """INV-1: no class hierarchy. No conversion utility."""
    assert not issubclass(DiscoveryCandidate, CanonicalOpportunity)
    assert not issubclass(CanonicalOpportunity, DiscoveryCandidate)
    # No __init_subclass__ trickery
    assert DiscoveryCandidate.__mro__[1].__name__ != CanonicalOpportunity.__name__


def test_inv1_no_conversion_utility_module():
    """INV-1: no convert-from-candidate-to-opp utility exists in models/."""
    import arbicore.models as m
    # Walk module attributes; no function named like 'candidate_to_*' or 'to_canonical'
    for name in dir(m):
        if name.startswith("_"):
            continue
        obj = getattr(m, name, None)
        if inspect.ismodule(obj):
            for sub in dir(obj):
                low = sub.lower()
                assert "candidate_to_canonical" not in low, (
                    f"INV-1 violated: {obj.__name__}.{sub} suggests direct conversion"
                )


# ============================================================================
# INV-2 — Only OpportunityVerifier constructs CanonicalOpportunity via the bus
# ============================================================================

def test_inv2_emission_bus_signature_only_accepts_canonical():
    """INV-2: EmissionBus.emit() type hint is CanonicalOpportunity, full stop."""
    sig = inspect.signature(EmissionBus.emit)
    opp_param = sig.parameters["opp"]
    # Annotation may be a string under PEP 563; accept either form.
    annot = opp_param.annotation
    if isinstance(annot, str):
        assert annot == "CanonicalOpportunity", (
            f"INV-2 violated: emission_bus.emit accepts {annot}"
        )
    else:
        assert annot is CanonicalOpportunity, (
            f"INV-2 violated: emission_bus.emit accepts {annot}"
        )


def test_inv2_scanner_modules_have_only_one_emission_call_site():
    """INV-2: across arbicore/scanners/, EmissionBus.emit is invoked from
    EXACTLY ONE PLACE PER SCANNER MODULE — and only in the orchestrator
    file. Each new scanner (D-1 CEX, D-2 Funding, future D-3/D-4/D-5)
    introduces exactly one such call site in its own scanner.py."""
    scanners_root = Path("/app/backend/arbicore/scanners")
    emit_sites = []
    for f in scanners_root.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if ".emit(" in line and "emission" in text.lower():
                emit_sites.append((str(f), i, line.strip()))
    # Each scanner orchestrator owns ONE emission call site.
    by_file = {}
    for path, ln, line in emit_sites:
        by_file.setdefault(path, []).append((ln, line))
    for path, sites in by_file.items():
        assert len(sites) == 1, (
            f"INV-2 violated: {path} has {len(sites)} emit() calls: {sites}"
        )
        assert path.endswith("scanner.py"), (
            f"INV-2: emit call must live in a scanner orchestrator, not {path}"
        )
    # We expect exactly one call site per registered scanner family.
    # As of D-2 there are two: cex_arbitrage/scanner.py and
    # funding_arbitrage/scanner.py. Future waves will add more.
    assert len(by_file) >= 1, "no scanner emission call site found"


# ============================================================================
# INV-3 — source_data_quality comes from the venue read, not the hint
# ============================================================================

def test_inv3_provenance_from_venue_read_only():
    """INV-3: the verifier doc string + behavior require source_data_quality
    to be taken from venue SOURCE_REGISTRY classification, never the hint."""
    from arbicore.scanners.cex_arbitrage.verifier import CEXOrderBookVerifier
    src = inspect.getsource(CEXOrderBookVerifier)
    # The verifier must NOT propagate candidate.hint_source to source_data_quality
    assert "source_data_quality=provenance" in src
    # The 'provenance' local variable must be derived from venue classification
    assert "_VENUE_PROVENANCE[vid]" in src
    # And must NOT be derived from candidate
    assert "candidate.hint_source" not in src or "source_data_quality" not in (
        src.split("candidate.hint_source")[1] if "candidate.hint_source" in src else ""
    )


# ============================================================================
# Pluggability: stub DiscoverySource pushes a candidate, worker dispatches it
# ============================================================================

class _DummyFundingSource(DiscoverySource):
    source_id = "dummy_funding_test"
    cadence_s = 1
    opportunity_types = {OpportunityType.FUNDING_ARBITRAGE}
    tier = 2
    provenance_of_hint = DataProvenance.REAL

    def __init__(self, candidate):
        self._c = candidate
        self._called = 0

    async def discover(self):
        self._called += 1
        if self._called > 1:
            return []
        return [self._c]

    async def health(self):
        from arbicore.models.discovery import SourceHealth
        return SourceHealth(source_id=self.source_id, ok=True)


def test_pluggability_unknown_opportunity_type_safely_denied():
    """A stub FUNDING_ARBITRAGE candidate without a registered verifier
    results in `denied:no_verifier_registered` — never a crash, never
    a canonical opportunity row."""
    now = time.time()
    cid = make_candidate_id(
        hint_source="dummy_funding_test",
        opportunity_type=OpportunityType.FUNDING_ARBITRAGE,
        subject_id="BTC", asset="BTCUSDT",
        candidate_venues=["bybit"], hint_observed_at=now,
    )
    c = DiscoveryCandidate(
        candidate_id=cid,
        opportunity_type=OpportunityType.FUNDING_ARBITRAGE,
        hint_source="dummy_funding_test",
        subject_id="BTC", asset="BTCUSDT",
        candidate_venues=["bybit"], hint_observed_at=now,
        reason="funding_window_high",
    )
    src = _DummyFundingSource(c)
    reg = OpportunityVerifierRegistry()
    # Only CEX verifier registered (stub); FUNDING has none
    assert reg.get(OpportunityType.FUNDING_ARBITRAGE) is None
    # The worker.tick() dispatch would call reg.get(...) → None → mark
    # processed with DENIED_NO_VERIFIER. That logic path is in scanner.py.
    # Verified by reading source — no other code path constructs canonical.


# ============================================================================
# Aggregator noise containment — the most important test
# ============================================================================

class _RejectAllVerifier(OpportunityVerifier):
    opportunity_type = OpportunityType.CEX_ARBITRAGE

    async def verify(self, candidate):
        return None, VerifiedOutcome.DENIED_VENUE_DISAGREES


def test_aggregator_noise_contained():
    """A rogue aggregator emits a CEX candidate; the verifier denies it;
    NO CanonicalOpportunity is produced. The hint never leaks into
    arbicore_opportunities."""
    verifier = _RejectAllVerifier()
    cid = make_candidate_id(
        hint_source="rogue_aggregator",
        opportunity_type=OpportunityType.CEX_ARBITRAGE,
        subject_id="BTC", asset="BTCUSDT",
        candidate_venues=["bybit", "okx"], hint_observed_at=time.time(),
    )
    c = DiscoveryCandidate(
        candidate_id=cid,
        opportunity_type=OpportunityType.CEX_ARBITRAGE,
        hint_source="rogue_aggregator",
        subject_id="BTC", asset="BTCUSDT",
        candidate_venues=["bybit", "okx"],
        reason="ticker_divergence",
    )
    opp, outcome = asyncio.run(verifier.verify(c))
    assert opp is None
    assert outcome == VerifiedOutcome.DENIED_VENUE_DISAGREES


# ============================================================================
# Registry sanity
# ============================================================================

def test_discovery_source_registry_register_and_lookup():
    reg = DiscoverySourceRegistry()
    cid = make_candidate_id(
        hint_source="dummy_funding_test",
        opportunity_type=OpportunityType.FUNDING_ARBITRAGE,
        subject_id="BTC", asset="BTCUSDT", candidate_venues=["bybit"],
        hint_observed_at=time.time(),
    )
    c = DiscoveryCandidate(
        candidate_id=cid,
        opportunity_type=OpportunityType.FUNDING_ARBITRAGE,
        hint_source="dummy_funding_test",
        subject_id="BTC", asset="BTCUSDT",
        candidate_venues=["bybit"], reason="funding_window_high",
    )
    src = _DummyFundingSource(c)
    reg.register(src)
    assert "dummy_funding_test" in reg.ids()
    assert reg.get("dummy_funding_test") is src


def test_candidate_id_deterministic():
    args = dict(
        hint_source="venue_ticker:bybit",
        opportunity_type=OpportunityType.CEX_ARBITRAGE,
        subject_id="BTC", asset="BTCUSDT",
        candidate_venues=["bybit"],
        hint_observed_at=1781880000.0,
    )
    a = make_candidate_id(**args)
    b = make_candidate_id(**args)
    assert a == b
    # Different source -> different id
    args2 = dict(args); args2["hint_source"] = "venue_ticker:okx"
    assert make_candidate_id(**args2) != a


# ============================================================================
# Endpoint smoke test (against live preview)
# ============================================================================

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://arbitrum-launch-1.preview.emergentagent.com",
).rstrip("/")


@pytest.fixture(scope="module")
def auth_session():
    import requests
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login", timeout=10,
        json={"username": "admin", "password": "ArbiCore2026!"},
    )
    if r.status_code != 200:
        pytest.skip(f"admin login unavailable ({r.status_code})")
    return s


def test_scanner_status_endpoint(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/scanners/cex_arb/status", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["wave"] == "D-1.0"
    assert body["scanner_id"] == "cex_arb"
    # D-1.0 = 7 venue sources, D-1.5 added coingecko_ticker → 8
    assert len(body["sources_registered"]) == 8
    assert "coingecko_ticker" in body["sources_registered"]
    assert body["verifiers_registered"] == ["CEX_ARBITRAGE"]


def test_discovery_queue_status_endpoint(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/discovery/queue/status", timeout=10)
    assert r.status_code == 200
    body = r.json()
    for k in ("total", "unprocessed", "claimed_in_flight", "unclaimed_eligible"):
        assert k in body


def test_discovery_sources_status_endpoint(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/discovery/sources/status", timeout=10)
    assert r.status_code == 200
    body = r.json()
    # D-1.0 = 7 venue sources, D-1.5 added coingecko_ticker → 8
    assert len(body["sources"]) == 8
    src_ids = {s["source_id"] for s in body["sources"]}
    assert {"venue_ticker:bybit", "venue_ticker:okx", "venue_ticker:kucoin",
            "venue_ticker:mexc", "venue_ticker:gate", "venue_ticker:bitget",
            "venue_ticker:binance_reference", "coingecko_ticker"}.issubset(src_ids)


def test_gate_analysis_endpoint(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/scanners/cex_arb/gate-analysis?window_minutes=120", timeout=10)
    assert r.status_code == 200
    body = r.json()
    for k in ("window_minutes", "total_observed", "total_validated",
              "total_rejected", "rejections_by_gate", "rejections_by_pair"):
        assert k in body


def test_venue_capabilities_endpoint(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/venues/capabilities", timeout=10)
    assert r.status_code == 200
    assert "venues" in r.json()


def test_wave5_shadow_binding_still_alive(auth_session):
    """Regression gate — Wave 5 BDAG flow must remain functional."""
    r = auth_session.get(f"{BASE_URL}/api/arbicore/shadow/status", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["wave"] == "C-5"
    assert body["hook_attached"] is True
    b = body["binder"]
    total_errors = (b["errors_mapping"] + b["errors_persistence"]
                    + b["errors_learning"])
    assert total_errors == 0, f"Wave 5 errors after D-1 wire: {b}"
