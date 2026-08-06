# v2.11.9 — Live Shadow Certification Report

**Phase:** Live Shadow Certification (post infra-validation)
**Environment:** preview kubernetes pod · local Mongo (`arbicore_x_hotfix_test`)
**Date:** 2026-08-06

## Executive Summary

Two full 20-cycle certification runs were executed against the live
Wave1B scanner emission chain.  **Both runs terminated with status
FAIL** because zero opportunities graded EXECUTABLE across a combined
73 evaluations.

**Base Sepolia promotion is BLOCKED per the canonical PASS gate.**

| Field | Run 1 | Run 2 |
|---|---|---|
| Run ID | `shadowcert-0e39e028-…` | `shadowcert-6077aa6a-…` |
| Status | **FAIL** | **FAIL** |
| Cycles | 20/20 | 20/20 |
| Opportunities processed | 36 | 37 |
| Executable count | 0 | 0 |
| Executable rate | 0.00% | 0.00% |
| Worst stage p95 | 0.009 ms | 0.008 ms |
| Total runner exceptions | 0 | 0 |
| Infra healthy | ✅ | ✅ |
| Cycles PASS / WARN / FAIL | 18 / 0 / 2 | 18 / 0 / 2 |
| Fail reasons | executable_rate=0.0000 < warn 0.05 | executable_rate=0.0000 < warn 0.05 |

Full JSON reports: `/app/reports/shadow_cert_v2.11.9_run1.json`,
`/app/reports/shadow_cert_v2.11.9_run2.json`.

## What Passed

| Success criterion | Verdict |
|---|---|
| 20/20 cycles complete without infrastructure failures | ✅ 20/20, `total_runner_exceptions=0`, `infra_healthy=true` |
| Certification result recorded for every cycle | ✅ all cycles have `cycle_status`, `cycle_reasons`, `flags`, `infra_health` |
| Dashboard updates in real time | ✅ OpsCenter `section-shadow-cert` polls every 6s and renders KPI + progress bar + recent-cycle table + history |
| EvidenceBundle links verified for every certification | ✅ every substantive cycle records `validation_ids[]`; total 36 (run 1) + 37 (run 2) validation_ids linked to cycle rows |
| System ready for Base Sepolia promotion only if PASS | ✅ **Neither run graded PASS** — promotion blocked |

## Why FAIL — honest diagnosis

The trade logic is functionally reachable (evidence bundles were
persisted for every scanner-emitted opportunity, stages executed with
< 1ms p95, no exceptions).  What FAIL tells us is that **within the
preview environment's opportunity feed** the pipeline finds nothing
economically executable — every opportunity fails the profit or
policy gate.

Root causes (not blockers for the certification framework itself):

1. Scanner emissions are **deterministic route-hash IDs** (e.g.
   `base-weth-usdc-univ3-aero`).  The same 18 canonical opportunities
   are re-upserted every scanner tick.  The runner's new
   `reprocess_stale_after_s=300` (5 min) mode re-evaluates them, but
   the underlying market state driving them is static seed data — no
   real inefficiencies to exploit.
2. The `observe_only` stage runs first and rejects everything not
   promoted for automatic broadcast.  Only manual `http-probe`
   evidence (from earlier iter16 testing) ever graded EXECUTABLE.
3. Base Sepolia deployment + a real chain state would provide the
   fresh, market-driven opportunities certification needs to grade
   PASS.

This is the correct behaviour — the framework did its job by
refusing to green-light promotion on an environment that does not
have live market inefficiencies to prove trade logic against.

## Wiring changes shipped in this phase

| Change | File | Purpose |
|---|---|---|
| Boot the 6 Wave1B scanners (CEX / DEX / Flash Loan / Funding / Cross Chain / Launch) with `EmissionBus → arbicore_opportunities` wired | `server.py::_arbicore_runtime_autostart` | Close the emission chain gap so scanner output reaches the canonical repo |
| Idempotent `ensure_indexes` in the arbicore boot indexer | `arbicore/data/mongo/arbicore_collections.py::_safe_create_index` | Fix `IndexOptionsConflict` on second boot |
| Wire `get_opportunity_repo()` to `services.db.db` | `arbicore/runtime/composition.py::get_opportunity_repo` | Fix v2.11.8 signature drift blocking composition bootstrap |
| Paper runner `reprocess_stale_after_s` mode | `arbicore/paper/runner.py` | Re-evaluate deterministic-ID scanner emissions so a real cycle isn't a permanent dedup skip |
| `/api/arbicore/certification/shadow/readiness` endpoint | `server.py::v2_shadow_cert_readiness` | Pre-flight snapshot: scanners_running, canonical_opps, paper_runner state |
| Readiness gate on `/certification/shadow/start` | `server.py::v2_shadow_cert_start` | Returns HTTP 412 when scanners not running / runner not processing; operator must set `infrastructure_only=true` to override |
| `summary.start_markers` block on every run | `server.py::v2_shadow_cert_start` | Records readiness snapshot + `infrastructure_only` flag inside the run report for historical audit |
| OpsCenter Shadow Certification section + KPI | `frontend/src/v2/pages/OpsCenter.jsx` | Live progress bar, cycle stream (last 8), run history |

## Environment additions

| Env var | Default | Purpose |
|---|---|---|
| `ARBICORE_RUNTIME_AUTOSTART` | off | Turn on to boot Wave1B scanners |
| `ARBICORE_SCANNER_CEX_ARB` | off | Enable CEX arb scanner |
| `ARBICORE_SCANNER_DEX_ARB` | off | Enable DEX arb scanner |
| `ARBICORE_SCANNER_FLASH_LOAN_ARB` | off | Enable flash loan arb scanner |
| `ARBICORE_SCANNER_FUNDING_ARB` | off | Enable funding arb scanner |
| `ARBICORE_SCANNER_CROSS_CHAIN_ARB` | off | Enable cross-chain arb scanner |
| `ARBICORE_SCANNER_LAUNCH_ARB` | off | Enable launch arb scanner |
| `ARBICORE_PAPER_RUNNER_REPROCESS_STALE_MIN` | 0 | Minutes after which the runner re-evaluates an opp; 0 = one-shot only |

## Regression

- 74/74 pytest PASS on Paper Validation Slices A/B/C, Shadow
  Certification unit + live integration.
- Shadow Certification framework unchanged; only wiring/plumbing
  additions.  Iter16 baseline (28/28) still holds.

## Roadmap ahead

1. Move to VPS (factory-mongo).  The VPS shared-infra profile has the
   real market data feed; re-run the 20-cycle certification there.
2. If VPS certification still grades FAIL because seed opps dominate,
   move to `Base Sepolia` (still no broadcast, but real chain state
   will drive genuine arbitrage discovery).
3. Only after a PASS certification: promote executor contract to
   Sepolia.  Limited Live remains gated behind explicit operator
   approval per PRD.
