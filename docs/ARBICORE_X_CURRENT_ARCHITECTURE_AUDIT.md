# ArbiCore X — Current Architecture Audit

Snapshot taken during the FINAL MASTER pass. Evidence-based; no fabrication.

## Runtime baseline

- Branch: `main` (`43230f6`); **canonical = `c284183`** (see archaeology report).
- App version: `VERSION` = **2.9.2** (matches image `2.9.2-c284183`).
- Frontend login footer hardcodes **"v2.9.3"** (label string in
  `v2/pages/LoginPage.jsx`). **This is the source of the historical 2.9.3-vs-2.9.2
  discrepancy** — a hardcoded UI label, not a live-sourced version. Canonical truth
  is `VERSION`=2.9.2 (backend). Not changed cosmetically per directive §5/§38;
  recommended follow-up: source the UI version from a backend `/api/version`.
- Services (supervisor): backend (FastAPI/uvicorn :8001), frontend (CRA :3000),
  mongodb :27017 — all RUNNING.

## Blocker found & fixed

- **All `.env` files were missing** after clone (gitignored, never created) →
  backend crash-looped on `KeyError: 'MONGO_URL'`. Created `backend/.env`
  (Mongo/DB/JWT + explicit **fail-closed** safety flags) and `frontend/.env`
  (`REACT_APP_BACKEND_URL`). Backend now boots cleanly; external ingress verified.

## Safety / execution posture (verified via `/api/arbicore/safety/status`)

```
live_execution_enabled : false
require_approval_gate   : true
require_paper_validation: true
kill_switch.engaged     : true   (reason: boot_default)   ← fail-closed on boot
capital_policy          : max/trade $500, max/chain $5000, max/day $25000
```
Execution mode defaults (`arbicore/execution/mode.py::default_mode_map`):
`flash_loan_arbitrage=SHADOW`, all other strategies `PAPER`. LIMITED_LIVE /
FULL_LIVE require explicit operator promotion + readiness. **System is fail-closed.**

`.env` flags set fail-closed (verified vs directive §3 expected state):
`ARBICORE_AUTOEXEC_AUTOSTART=false`, `ARBICORE_RUNTIME_AUTOSTART=false`,
`ARBICORE_DISCOVERY_AUTOSTART=false`, `ARBICORE_SCANNER_AUTOSTART=true`,
`ARBICORE_SCANNER_{CEX,DEX,FUNDING,LAUNCH}_ARB=false`,
`ARBICORE_SHADOW_CERT_ENABLED=true`.

## Subsystem inventory (present in code — depth re-audit tracked as remaining)

- **API**: ~250 routes in `server.py` (356 KB) + mounted routers (auth, scanners).
- **arbicore/** packages: `economics` (expected_value, net_profit, size_optimizer,
  opportunity_decision/engine, quote_provider), `execution` (mode, capital_policy,
  adapters, aerodrome_settlement, discovery), `flashloan`, `learning` (isotonic
  calibrator, adaptive weights observer/worker, sequence miner, survival, regime,
  outcome/route trackers, ledger), `providers` (rpc, bootstrap), `scanner(s)`,
  `safety`, `validation`, `wallets`, `secrets`, `evidence`, `certification`,
  `postvalidation`, `paper`, `shadow`, `intel(ligence)`, `analytics`.
- **Learning collections referenced**: `decision_history`, `mid_decisions`,
  `adaptive_weight_recommendations`, `calibration_log`, `arbicore_outcomes`,
  `route_recurrence`, `evidence_bundles`, `arbicore_opportunity_journal`,
  `arbicore_paper_evidence`.
- **Executor/signer** historical addresses (`0x91c0bf28…`, `0x998d6efF…`) appear in
  tests as expected constants; live values are environment/config-sourced (not
  hardcoded into runtime). Deep executor/fork re-verification tracked as remaining.

## Auth architecture (audited in depth)

Single canonical tree: `routes/auth.py` + `services/auth.py`, collection `users`,
httpOnly JWT cookies, session-version revocation, bcrypt hashing, brute-force
lockout. Legacy Tree-B (`auth_users`) retired/gated off (`/auth/diagnostics`→404).
First-admin bootstrap hardened to fail-closed (see P0 audit).
