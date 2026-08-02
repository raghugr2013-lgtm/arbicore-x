"""ArbiCore X — Phase D D-2.0 Funding Differential Verifier.

Scope of this module (operator-locked checkpoint):
  - Funding-rate normalization (per-interval → annualised).
  - Symbol normalization validation (canonical base + canonical perp asset).
  - Funding interval normalization (1h, 4h, 8h — future-proof for any h).
  - Timestamp freshness validation (per-config max age in seconds).
  - Cross-venue funding differential calculation.
  - Verifier evidence generation (the auditable artefact downstream code will consume).

EXPLICITLY NOT in scope yet (per operator direction, next checkpoint):
  - CanonicalOpportunity construction (INV-2 will be honoured here too — this
    module contains zero references to CanonicalOpportunity / EmissionBus /
    source_data_quality, enforced by AST-stripped static tests).
  - Gate pipeline invocation.
  - Confidence engine integration.
  - Learning hook emission.
  - Opportunity ranking, scoring, or persistence.

The next checkpoint will wrap this engine in an `OpportunityVerifier` that
takes a `FundingDifferentialEvidence`, applies the universal gates, and
emits a CanonicalOpportunity exactly once per confirmed candidate.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .sources import FundingObservation, _BaseFundingSource

logger = logging.getLogger("arbicore.scanners.funding_arb.verifier")


# ============================================================================
# Result records — auditable evidence the downstream verifier will consume.
# ============================================================================

@dataclass
class VenueFundingRead:
    """One venue's normalised funding read for one asset.

    Produced from a raw `FundingObservation` after:
      - symbol normalisation validation (subject_id, canonical_asset)
      - funding-rate normalisation (per-interval signed %)
      - funding-interval normalisation (h)
      - annualisation
      - freshness assessment
    """
    venue: str
    venue_symbol: str
    subject_id: str
    canonical_asset: str
    funding_rate_pct_per_interval: float
    funding_interval_h: int
    funding_apr_pct: float
    next_funding_ts: Optional[float]
    next_funding_iso: Optional[str]
    mark_price: Optional[float]
    index_price: Optional[float]
    open_interest_usd: Optional[float]
    venue_observed_at_ts: float
    age_s: float
    freshness_ok: bool
    venue_provenance_id: str
    normalization_notes: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FundingDifferential:
    """Cross-venue funding-rate differential for one asset.

    Convention:
      - ``long_venue``  = venue with the LOWEST funding APR (capital earns
        funding by going long there — funding flows to longs).
      - ``short_venue`` = venue with the HIGHEST funding APR (capital earns
        funding by going short there — funding flows to shorts).
      - ``differential_apr_pct`` = short - long  (always ≥ 0 by construction).

    No opinion about whether the differential is "tradable" is expressed here —
    that's the next checkpoint's job. This struct is pure data.
    """
    asset_base: str
    canonical_asset: str
    long_venue: str
    long_funding_apr_pct: float
    short_venue: str
    short_funding_apr_pct: float
    differential_apr_pct: float
    captured_at_ts: float
    long_read: VenueFundingRead
    short_read: VenueFundingRead


@dataclass
class FundingDifferentialEvidence:
    """Verifier-level audit record of one differential computation.

    The downstream opportunity-emitting verifier (next checkpoint) will
    consume this object verbatim. Every venue attempt is recorded so the
    gate-analysis / learning layer can later audit why a particular
    asset's differential was (or wasn't) actionable.
    """
    asset_base: str
    canonical_asset: str
    requested_at_ts: float
    max_funding_age_s: float
    venue_reads: List[VenueFundingRead]
    stale_reads: List[VenueFundingRead]
    eligible_reads: List[VenueFundingRead]
    differential: Optional[FundingDifferential]
    verifier_notes: List[str] = field(default_factory=list)

    @property
    def eligible_count(self) -> int:
        return len(self.eligible_reads)

    def to_dict(self) -> Dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


# ============================================================================
# The differential engine.
# ============================================================================

class FundingDifferentialVerifier:
    """Pure differential math + evidence engine.

    Constructs are intentionally minimal:
      - takes the list of per-venue funding sources (so it can independently
        re-read each venue per INV-3);
      - takes a config loader (max_funding_age_s, min_eligible_venues).

    The engine does NOT register with `OpportunityVerifierRegistry` yet — that
    registration happens when the next checkpoint adds the
    CanonicalOpportunity-emitting wrapper.
    """

    DEFAULT_MAX_FUNDING_AGE_S = 180.0
    DEFAULT_MIN_ELIGIBLE_VENUES = 2

    def __init__(self, *,
                 sources: List[_BaseFundingSource],
                 config_loader: Callable[[], Dict[str, Any]],
                 ) -> None:
        self._sources = list(sources)
        self._cfg = config_loader

    # ---- public API ------------------------------------------------------

    async def compute_differential(self, asset_base: str,
                                   ) -> FundingDifferentialEvidence:
        """Read every configured venue source for ``asset_base``, normalise,
        apply freshness gate, compute differential, return evidence.

        The function never raises on per-venue failures — those are recorded
        as missing reads in the evidence. Only a programmer-error (bad input)
        propagates."""
        if not asset_base or not isinstance(asset_base, str):
            raise ValueError("asset_base must be a non-empty string")
        base = asset_base.upper()
        cfg = (self._cfg() or {})
        max_age = float(cfg.get("max_funding_age_s", self.DEFAULT_MAX_FUNDING_AGE_S))
        min_elig = int(cfg.get("min_eligible_venues_for_diff",
                                self.DEFAULT_MIN_ELIGIBLE_VENUES))
        notes: List[str] = []
        t_request = time.time()

        # Fan out: each venue's _fetch_observations() returns all assets.
        # We filter to ``base`` and normalise.
        raw_results = await asyncio.gather(
            *[self._read_one_venue(src, base) for src in self._sources],
            return_exceptions=True,
        )

        venue_reads: List[VenueFundingRead] = []
        for src, r in zip(self._sources, raw_results):
            if isinstance(r, Exception):
                notes.append(f"{src.source_id}: exception {r!r}")
                continue
            if r is None:
                err = getattr(src, "_last_verifier_read_error", None)
                if err:
                    notes.append(f"{src.source_id}: exception {err}")
                else:
                    notes.append(f"{src.source_id}: no read for {base}")
                continue
            venue_reads.append(r)

        # Freshness gate.
        eligible: List[VenueFundingRead] = []
        stale: List[VenueFundingRead] = []
        now = time.time()
        for vr in venue_reads:
            vr.age_s = now - vr.venue_observed_at_ts
            vr.freshness_ok = (vr.age_s <= max_age)
            (eligible if vr.freshness_ok else stale).append(vr)

        # Differential.
        diff: Optional[FundingDifferential] = None
        if len(eligible) >= min_elig:
            ordered = sorted(eligible, key=lambda r: r.funding_apr_pct)
            lo, hi = ordered[0], ordered[-1]
            if lo.venue == hi.venue:
                # Degenerate: only one venue produced an eligible read despite
                # the min_eligible_venues threshold; do not emit a differential.
                notes.append("degenerate:lo_venue==hi_venue")
            else:
                diff = FundingDifferential(
                    asset_base=base,
                    canonical_asset=f"{base}-PERP",
                    long_venue=lo.venue,
                    long_funding_apr_pct=lo.funding_apr_pct,
                    short_venue=hi.venue,
                    short_funding_apr_pct=hi.funding_apr_pct,
                    differential_apr_pct=round(
                        hi.funding_apr_pct - lo.funding_apr_pct, 6),
                    captured_at_ts=now,
                    long_read=lo,
                    short_read=hi,
                )
        else:
            notes.append(
                f"insufficient_eligible_venues:{len(eligible)}_lt_{min_elig}")

        return FundingDifferentialEvidence(
            asset_base=base,
            canonical_asset=f"{base}-PERP",
            requested_at_ts=t_request,
            max_funding_age_s=max_age,
            venue_reads=venue_reads,
            stale_reads=stale,
            eligible_reads=eligible,
            differential=diff,
            verifier_notes=notes,
        )

    # ---- helpers --------------------------------------------------------

    async def _read_one_venue(self, src: _BaseFundingSource,
                              base: str) -> Optional[VenueFundingRead]:
        """Read one venue and normalise to ``VenueFundingRead`` for the given
        canonical base. Returns ``None`` if the venue does not list the
        asset or the read fails. The exception (if any) is attached to the
        source as ``_last_verifier_read_error`` so the caller can record it
        in the evidence trail."""
        src._last_verifier_read_error = None  # type: ignore[attr-defined]
        try:
            obs_list = await src._fetch_observations()
        except Exception as exc:  # noqa: BLE001
            src._last_verifier_read_error = repr(exc)  # type: ignore[attr-defined]
            logger.debug("verifier read fail %s: %r", src.source_id, exc)
            return None
        if not obs_list:
            return None
        for obs in obs_list:
            if obs.subject_id == base:
                return _normalise_observation(obs, src.venue_provenance_id)
        return None


# ============================================================================
# Normalisation — pure functions, no I/O. Easy to unit-test in isolation.
# ============================================================================

# Funding-interval-correctness allow-list. Adding a new interval here is a
# deliberate decision — adding a new venue with an unexpected interval
# (e.g., 30-minute) will surface as a normalisation_note rather than a
# silent miscalculation.
KNOWN_FUNDING_INTERVALS_H: tuple = (1, 2, 4, 6, 8, 12, 24)


def annualise_funding(rate_pct_per_interval: float,
                      interval_h: int) -> float:
    """Annualise a per-interval funding rate (in %) to APR (in %).

    Uses the linear convention every venue's docs reference:
        APR = rate_pct * (24 / interval_h) * 365
    Returns 0.0 for non-positive intervals (defensive).
    """
    if interval_h is None or interval_h <= 0:
        return 0.0
    return rate_pct_per_interval * (24.0 / float(interval_h)) * 365.0


def validate_symbol_mapping(obs: FundingObservation) -> List[str]:
    """Return a list of normalisation notes for any symbol-mapping anomaly.

    The expected invariants on every venue observation:
      - ``subject_id`` is non-empty UPPERCASE without separators
      - ``canonical_asset`` == f"{subject_id}-PERP"
      - ``venue_symbol`` non-empty
    Anything that violates these gets recorded in ``normalization_notes``
    on the resulting ``VenueFundingRead``. The verifier does NOT silently
    drop such reads — the next checkpoint's gate pipeline decides.
    """
    notes: List[str] = []
    if not obs.subject_id:
        notes.append("empty_subject_id")
    elif not obs.subject_id.isupper() or any(c in obs.subject_id for c in "-_/"):
        notes.append(f"non_canonical_subject_id:{obs.subject_id!r}")
    expected = f"{obs.subject_id}-PERP"
    if obs.canonical_asset != expected:
        notes.append(
            f"canonical_asset_mismatch:{obs.canonical_asset!r}!={expected!r}")
    if not obs.venue_symbol:
        notes.append("empty_venue_symbol")
    return notes


def validate_funding_interval(interval_h: int) -> List[str]:
    """Note (but do not fail on) intervals outside the known allow-list."""
    notes: List[str] = []
    if interval_h is None or interval_h <= 0:
        notes.append(f"invalid_funding_interval_h:{interval_h!r}")
    elif interval_h not in KNOWN_FUNDING_INTERVALS_H:
        notes.append(
            f"unknown_funding_interval_h:{interval_h}_not_in_"
            f"{KNOWN_FUNDING_INTERVALS_H}")
    return notes


def _normalise_observation(obs: FundingObservation,
                           venue_provenance_id: str) -> VenueFundingRead:
    notes: List[str] = []
    notes.extend(validate_symbol_mapping(obs))
    notes.extend(validate_funding_interval(obs.funding_interval_h))

    apr_pct = annualise_funding(obs.funding_rate_pct, obs.funding_interval_h)
    next_iso = (datetime.fromtimestamp(obs.next_funding_ts,
                                        tz=timezone.utc).isoformat()
                if obs.next_funding_ts else None)
    now = time.time()
    age_s = max(0.0, now - obs.source_observed_at_ts)
    return VenueFundingRead(
        venue=obs.venue,
        venue_symbol=obs.venue_symbol,
        subject_id=obs.subject_id,
        canonical_asset=obs.canonical_asset,
        funding_rate_pct_per_interval=obs.funding_rate_pct,
        funding_interval_h=obs.funding_interval_h,
        funding_apr_pct=round(apr_pct, 6),
        next_funding_ts=obs.next_funding_ts,
        next_funding_iso=next_iso,
        mark_price=obs.mark_price,
        index_price=obs.index_price,
        open_interest_usd=obs.open_interest_usd,
        venue_observed_at_ts=obs.source_observed_at_ts,
        age_s=age_s,
        freshness_ok=True,    # populated by the verifier with config-aware age check
        venue_provenance_id=venue_provenance_id,
        normalization_notes=notes,
        raw=obs.raw,
    )
