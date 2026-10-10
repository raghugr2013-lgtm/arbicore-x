# P2 Release Manifest — Instrumentation + Option D

**Status:** Release package prepared. **Deployment NOT authorised.**

**Package root:** `artifacts/performance/p2_release/`

**Prepared:** 2026-10-09

## Purpose

Minimal, reviewable, **P2-only** instrumentation package that:

1. Keeps candidate `claimed_at` durable after `mark_processed` (clears lock fields only).
2. Records fail-safe per-stage timings in flash-loan evidence `diagnostics.timing`.
3. Resolves `evidence_persisted` as true/false/null without altering verdicts.
4. Stamps `diagnostics.timing.evidence_persisted = true` at `EvidenceBundlesRepo.insert` time (Option D) so Mongo stores confirmed insert success.

## Exact included files (authorised set)

| # | Path | Purpose |
|---|---|---|
| 1 | `app/backend/arbicore/data/discovery_queue.py` | Durable `claimed_at` + docstring **only** (isolated from unrelated `queue_status` hunks) |
| 2 | `app/backend/arbicore/models/discovery.py` | Durable `claimed_at` docstring |
| 3 | `app/backend/arbicore/scanners/flash_loan_arbitrage/verifier.py` | Fail-safe stage timing + `evidence_persisted` ternary |
| 4 | `app/backend/arbicore/data/mongo/evidence_bundles_repo.py` | Option D insert-time stamp |
| 5 | `app/backend/tests/test_flashloan_diagnostic_provenance.py` | Additive timing assertions |
| 6 | `app/backend/tests/test_p2_flashloan_timing_instrumentation.py` | Focused instrumentation tests |
| 7 | `app/backend/tests/test_p2_evidence_persisted_mongo.py` | Persistence / Mongo round-trip tests |

## Release artifacts in this directory

| Artifact | Description |
|---|---|
| `P2_ONLY_COMBINED.patch` | Unified P2-only patch (apply against clean tree / HEAD) |
| `01_discovery_queue_P2_ONLY.patch` … `07_*.patch` | Per-file patches |
| `discovery_queue_P2_ONLY.py` | Full file content = HEAD + P2 hunks only (reference; excludes WT `queue_status`) |
| `P2_RELEASE_MANIFEST.md` | This file |
| `P2_DIFF_AUDIT.md` | Included vs excluded hunks |
| `P2_TEST_RESULTS.md` | Exact test commands and results |
| `P2_RELEASE_CHECKSUMS.txt` | SHA-256 checksums |
| `pytest_focused_output.txt` | Raw focused pytest output |

## Explicitly excluded

- Unrelated `queue_status` / backlog-reporting hunks in working-tree `discovery_queue.py`
- Scanner, frontend, ledger, server, worker-pool, and other dirty-tree edits
- Migrations, deploy compose, image rebuilds, production config

## Apply guidance (human / future deploy authorisation only)

1. Start from clean `HEAD` (or a clean branch from the deployment base).
2. Apply `P2_ONLY_COMBINED.patch` (or the numbered per-file patches in order).
3. Do **not** copy the dirty working-tree `discovery_queue.py` wholesale.
4. Re-run focused tests against an isolated Mongo before any production deploy.

## Marker semantics

`diagnostics.timing.evidence_persisted = true` on a stored evidence row means **this audit document was successfully inserted**. It does **not** mean the opportunity was profitable, confirmed for trading, or captured.
