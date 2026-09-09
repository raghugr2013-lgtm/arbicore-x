# ArbiCore X v2 — VPS Certification Harness/Runbook — Completion Report

**Date:** 2026-09-09 · **Branch:** `vps-cert-p1b2` (off `p1-batch2-h07-h08-h09`)
**Nature:** in-pod ENGINEERING of a READ-ONLY, fail-closed certification harness + isolated non-production compose + operator runbook. **No VPS access from this pod**, so this batch builds the tooling and proves it fail-closes; the REAL six-RPC / on-chain evidence is produced by the operator running it on the VPS.

**Safety:** signing/broadcast/auto-exec/Full-Live/Limited-Live OFF; no real tx; no receiver deployed; no production container touched; no merge to main; no secrets committed. Protected files untouched.

---

## What was built
- `arbicore/certification/vps_harness.py` — READ-ONLY checks, each returning one of `PASS/FAIL/BLOCKED/UNKNOWN/NOT_CONFIGURED`, reusing existing modules (quoter H06 chain-id, `receiver_capability` H08, `candidate_simulation` H09, `probe_executor_identity` H10, `executor_registry`). VPS-unavailable is never upgraded to PASS. No secret in any output.
- `scripts/vps_certify.py` — CLI runner that assembles the **12-section** report + machine-readable JSON with commit provenance, timestamps, and safety-state; writes to `/app/vps_cert/` (VPS: `./vps_cert_out/`).
- `deployment/compose/docker-compose.certification.yml` — **isolated** non-production stack (project `arbicore-cert`, own containers/network/volume, no published ports, one-shot runner, safety flags forced OFF). Does NOT touch the production compose/container/volume/network (production `docker-compose.yml` is a protected file and was not modified).
- `deployment/cert/cert.env.example` (no secrets; real `cert.env` git-ignored on the VPS) + `deployment/cert/VPS_CERTIFICATION_RUNBOOK.md` (exact operator commands).
- `.gitignore` updated to exclude `deployment/cert/cert.env` and `vps_cert_out/`.

## Check coverage (maps to the required 12 report sections)
1 six-chain RPC · 2 chain-id · 3 H05 exact-size · 4 H07 runtime · 5 H08 receiver capability · 6 H09 simulation · 7 executor/receiver bytecode+immutables (via H10-hardened `probe_executor_identity`) · 8 chain-scoped TVL/pricing · 9 commit/image provenance · 10 safety-state · 11 blockers · 12 exact evidence required before Opportunity Race.

## Fail-closed status model (enforced + tested)
`PASS` real positive evidence · `FAIL` active contradiction (wrong chain id) · `BLOCKED` evidence unreachable/unavailable · `UNKNOWN` reachable but insufficient · `NOT_CONFIGURED` operator input absent. **VPS-unavailable evidence is never PASS** (dedicated end-to-end test).

## In-pod dry-run result (proves honesty)
`python -m scripts.vps_certify` in this pod (no operator RPCs) → `status_counts = {NOT_CONFIGURED: 19, BLOCKED: 3}`, **zero PASS**. Artifacts in `/app/vps_cert/` (see its README). No RPC URL/API key present; only redacted host, public on-chain addresses, booleans, statuses.

## Tests & results
- `tests/test_vps_harness.py` — **14/14** (every status transition: RPC not-configured/blocked/fail/pass±failover; H05 not-configured/pass; H08 undeployed-blocked / no-providers-blocked / declared-unknown; H09 blocked/unknown; **VPS-unavailable-never-PASS** end-to-end).
- `tests/test_p1b2_h07_h08_h09.py` 13/13. Combined P0+P1+cert regression: **76 passed**.
- **testing_agent: N/A** — this batch adds NO live HTTP endpoints (a read-only CLI harness); testing_agent (API/browser) cannot meaningfully exercise a CLI beyond the 14 deterministic unit tests. The only endpoint-affecting change in this whole phase was Batch-1 M07, already verified live in `/app/test_reports/iteration_2.json`.

## Phase B (on-chain) note — target chain 84532
`receiver_capability(84532)` = deployed but **no `supported_providers` declared** ⇒ H08 stays **BLOCKED/FALSE**. It becomes TRUE only when the deployed receiver is on-chain-verified AND explicitly declares the provider(s) (section-7 bytecode/immutable/owner must also verify). **Registry edits alone will not flip it.** No new receiver deployed (requires separate explicit approval).

## EXACT commands you run on the VPS
See `deployment/cert/VPS_CERTIFICATION_RUNBOOK.md`. Summary:
```bash
git checkout p1-batch2-h07-h08-h09 && git rev-parse HEAD
cp deployment/cert/cert.env.example deployment/cert/cert.env   # fill 6 RPCs (VPS only)
mkdir -p vps_cert_out
GITSHA=$(git rev-parse HEAD) docker compose -p arbicore-cert \
  -f deployment/compose/docker-compose.certification.yml \
  --env-file deployment/cert/cert.env up --build --abort-on-container-exit
cat vps_cert_out/certification_report.md
docker compose -p arbicore-cert -f deployment/compose/docker-compose.certification.yml down -v
```

## Remaining blockers / evidence required before Opportunity Race
Operator six-chain RPC PASS (+failover); H05 live exact-size quote (price feed + borrow_sizer); H07 live per-chain composition; H08 on-chain-verified receiver declaring provider(s); H09 complete candidate binding + exact-sim PASS + chain match; section-7 bytecode/immutables/owner verified — plus explicit operator approval with signing/broadcast still gated. **Certification PASS is necessary but NOT sufficient for live trading.**

## Git
Branch `vps-cert-p1b2`. New: `vps_harness.py`, `scripts/vps_certify.py`, `tests/test_vps_harness.py`, `deployment/compose/docker-compose.certification.yml`, `deployment/cert/{cert.env.example,VPS_CERTIFICATION_RUNBOOK.md}`, `/app/vps_cert/*`; modified `.gitignore`. No production source modified. Push via "Save to GitHub" (no merge to main).

**STOP — harness/runbook complete. Awaiting your VPS run results / approval. No Opportunity Race, no Limited Live, no signing/broadcast, no new receiver.**
