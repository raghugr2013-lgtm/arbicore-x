# Sprint 1B-α — Intelligence Activation

**Release date:** 2026-08-03
**Wave:** 1B-α (of 3)
**Charter:** Wire six dormant intelligence engines into the runtime and give
every one of them a single, validated write path into the Market
Intelligence Database (MID).  **Scanners are NOT activated in this wave.**

---

## Engines activated

| Engine ID        | Class                          | Description                                                    | Status |
|------------------|--------------------------------|----------------------------------------------------------------|--------|
| `confidence`     | `SignalConfidenceEngine`       | Persistence-based per-route confidence in [0, 100]             | active |
| `roi`            | `ROIProbabilityEngine`         | Winsorised ROI distribution + breakout probability             | active |
| `route_ranking`  | `ScoringEngine`                | Spread × persistence × liquidity ÷ gas·mev route scoring       | active |
| `economics`      | `CapitalSizer`                 | Pool / wallet / per-trade capital sizing                       | active |
| `entity_scoring` | `EntityScorer`                 | Universal per-entity outcome tracker                           | active |
| `regime`         | `HeuristicRegimeClassifier`    | Dominant regime + multi-label context tags                     | active |

Startup log:

```
intelligence: activated engine=confidence
intelligence: activated engine=roi
intelligence: activated engine=route_ranking
intelligence: activated engine=economics
intelligence: activated engine=entity_scoring
intelligence: activated engine=regime
intelligence: activation complete — 6/6 engines active
intelligence: Wave 1B-α activation summary — active=['confidence', 'roi',
    'route_ranking', 'economics', 'entity_scoring', 'regime'] errored=[]
```

## MidEvidenceBridge — the single write path

Every engine publishes evidence through
`arbicore.intelligence.wave1b.bridge.MidEvidenceBridge`.  The bridge:

1. Accepts each engine's native output shape.
2. Delegates to the appropriate `MidWriter.write_*` method with a
   caller-supplied `MidMetadata` (defaults filled in only for missing keys).
3. Mirrors every emission into `mid_opportunities` with
   `event_type = "intel.<engine>.<event>"` so the intelligence stream is
   replayable as a timeline even before scanners are active.
4. Records the write in `BridgeStats` (surfaced via
   `/api/arbicore/intelligence/status`).

### MID collections receiving evidence

| Engine           | Primary MID domain    | Mirror event type                          |
|------------------|-----------------------|--------------------------------------------|
| `confidence`     | `mid_confidence`      | `intel.confidence.score_written`           |
| `roi`            | `mid_opportunities`   | `intel.roi.probability`                    |
| `route_ranking`  | `mid_routes`          | `intel.route_ranking.scored`               |
| `economics`      | `mid_decisions`       | `intel.economics.capital_sizing`           |
| `entity_scoring` | `mid_opportunities`   | `intel.entity_scoring.outcome_recorded`    |
| `regime`         | `mid_providers`       | `intel.regime.classified`                  |

## New API endpoints

* `GET  /api/arbicore/intelligence/status`
  — Wave version, per-engine activation state, dependency list, error field,
    aggregate `BridgeStats`.
* `GET  /api/arbicore/intelligence/{engine_id}/snapshot`
  — Live public state of one engine (routes tracked, weights, limits,
    latest regime snapshot, etc.).

## Backward-compatibility guarantees

* No existing endpoint is removed or altered.
* Engines only run when explicitly invoked (no background workers).
* Scanners remain DORMANT (Wave 1B-β).
* Full regression suite: **1478 passed, 76 skipped, 0 failures**
  (previous baseline 1469; +9 new Wave 1B-α tests).

## Evidence-flow verification (live)

Ran end-to-end from CLI (writer connected to the running Mongo):

```
WROTE: total_writes=3
  by_engine   = {confidence: 1, economics: 1, regime: 1}
  by_domain   = {confidence: 1, decisions: 1, providers: 1}
```

Query results via public API:

```
/api/arbicore/mid/query/confidence  → 1 row  (opp_id=opp-live-1, score=76.4)
/api/arbicore/mid/query/decisions   → 1 row  (opp_id=opp-live-1, gate=capital_sizing,
                                              reason="binding=pool suggested_usd=2000.0")
/api/arbicore/mid/query/providers   → 1 row  (provider_id=regime:live-verify)
/api/arbicore/mid/query/opportunities → 3 rows (mirror events for
                                                confidence, economics, regime)
```

## Sprint 1B constraints honoured

* No live blockchain RPC calls.
* No live DEX queries.
* No live exchange APIs.
* No production quote providers.
* No production execution.
* All engines use pure computation or in-memory scratch state; the durable
  evidence path is MID.

## Files added

* `arbicore/intelligence/wave1b/__init__.py`
* `arbicore/intelligence/wave1b/bridge.py`         (`MidEvidenceBridge`)
* `arbicore/intelligence/wave1b/registry.py`       (`IntelligenceRegistry`)
* `arbicore/intelligence/wave1b/activation.py`     (`activate_all`)
* `arbicore/intelligence/wave1b/inmemory_repos.py` (test-scoped ABC shims)
* `tests/test_wave1b_alpha.py`                     (9 integration tests)

## Files modified

* `app/backend/server.py` — added Wave 1B-α startup event + 2 endpoints.

## Runtime-layout alignment

Wave 1B-α also brought several files from the canonical repo into the
running `/app/backend/` tree so the activation could load its transitive
dependencies:

* `arbicore/intelligence/{__init__.py, audit_log.py, capital.py, confidence.py,
   roi_probability.py, scoring.py, validators/*}`
* `arbicore/intel/` (full package)
* `arbicore/data/{metrics_repo.py, outcome_repo.py, regime_snapshot_repo.py,
   scanner_config_repo.py, state_observer.py, venue_capability_repo.py,
   wallet_profile_repo.py, _inmemory.py, discovery_source_metrics_repo.py}`
* `arbicore/data/mongo/{arbicore_collections, metrics_repo_mongo,
   outcome_repo_mongo, regime_snapshot_repo_mongo, wallet_profile_repo_mongo}.py`
* `arbicore/learning/concrete/regime_classifier.py`
* Minimal `services/db.py` shim (re-exports the FastAPI `db` handle) so the
   Mongo-backed repositories under `arbicore/data/mongo/` can construct
   without dragging in the full legacy collection registry.

None of the newly-copied modules are activated by default; they only exist
to satisfy transitive imports.

## Next: Wave 1B-β

Awaiting user acceptance of Wave 1B-α before wiring
`DEXArbitrageScanner` + `FlashLoanArbitrageScanner` in shadow mode.
