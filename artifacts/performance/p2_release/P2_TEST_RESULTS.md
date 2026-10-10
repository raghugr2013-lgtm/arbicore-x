# P2 Test Results

**Prepared:** 2026-10-09  
**Deployment:** not authorised; tests ran against isolated validator Mongo only.

## Command (reproduced for release package)

```bash
cd app/backend && \
MONGO_URL=mongodb://172.26.0.2:27017 PYTHONPATH=. \
  /home/raghu/projects/arbicore-x-v2/.venv/bin/python -m pytest \
  tests/test_p2_evidence_persisted_mongo.py \
  tests/test_p2_flashloan_timing_instrumentation.py \
  tests/test_flashloan_diagnostic_provenance.py \
  tests/test_m2_3_evidence_bundle.py \
  -q --tb=line -o addopts=
```

## Result (this packaging run)

```text
...................................                                      [100%]
35 passed in 4.96s
```

Raw capture: `pytest_focused_output.txt`

**Prior baseline (final review):** 35 passed in 3.68s — same command; timing variance only.

## Mongo target

| Item | Value |
|---|---|
| Host | `172.26.0.2:27017` (`compose-validator-mongo-1` Docker bridge IP) |
| Production Mongo / networking changes | **None** |
| Throwaway DBs | `arbicore_x_p2_evidence_*` (dropped in test teardown) |

If `MONGO_URL` points at unreachable `localhost:27017`, three Mongo round-trip tests in `test_p2_evidence_persisted_mongo.py` skip; offline P2 suites still pass.

## Behaviour checks covered by the 35

| Requirement | Covered |
|---|---|
| Durable `claimed_at`; lock fields cleared | `test_mark_processed_keeps_claimed_at_clears_lock_fields` |
| Null vs zero stage timings | missing-stage / frozen-clock tests |
| Mongo `evidence_persisted=true` on success | `test_mongo_roundtrip_*`, `test_verifier_repo_sink_mongo_marker_true_*` |
| Failed insert / sink raise → no false success | insert failure + sink raise tests |
| Instrumentation failure non-fatal to verdict | fail-safe / unwired / clock-failure tests |
| No new RPC / trading / worker / queue-policy / risk logic in P2 package | Diff audit + suites are observability-only |

## Passed / failed / not run

| Category | Count / notes |
|---|---|
| **Passed** | **35** |
| **Failed** | **0** |
| **Not run** | Full suite, production Mongo, claim-progression against localhost (not required for this package); unrelated dirty-tree suites |

## Pre-existing vs introduced

No failures in this focused run. Nothing attributed as a P2 regression.
