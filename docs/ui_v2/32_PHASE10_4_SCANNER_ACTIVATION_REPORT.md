# Phase 10.4 · Scanner Configuration Activation — Consolidated Report

**Date:** 2026-08-01
**Baseline:** 440 passing → **460 passing** + 2 skipped (**462 total**)
**Philosophy:** VERIFY → REUSE → REFINE → ACTIVATE → MERGE → NEW
**Result:** Canonical multi-family scanner configuration ACTIVATED · full Draft/Apply/Rollback/Audit inherited from Phase 10.1 · Flash Loan LIMITED_LIVE readiness unchanged.

---

## A. VERIFY → REUSE audit findings honoured

The Phase 10 audit report identified the dormant canonical
`arbicore/data/scanner_config_repo.py` (581 LOC) with per-family
defaults for six scanner families. This phase activates those
canonical defaults directly rather than reinventing them.

### Canonical modules activated

| Canonical source | Landed at | Delta |
|---|---|---|
| `app/backend/arbicore/data/scanner_config_repo.py` (defaults section, lines 1–446) | `backend/arbicore/data/scanner_config_defaults.py` | Exact copy of the six `DEFAULT_*_ARB_CONFIG` constants + a small registry mapping (`CANONICAL_FAMILIES`, `FAMILY_DEFAULTS`, `FAMILY_LABELS`). ~448 LOC ported verbatim. |
| `ScannerConfigRepository` class (lines 449–582) | **NOT imported** | Intentionally superseded — the Phase 10 `ConfigRepo` substrate already provides a superior Draft/Apply/Rollback/Audit surface. |
| `ScannerStateRepository` class | **NOT imported** | Same reason — `paused` / `enabled` / `runtime` fields now live inside the global scanner config. |

### Preview / stub code retired

| Retired | Location | Reason |
|---|---|---|
| Prior single-family `ScannerConfigRepo` (Phase 10.4 attempt v1) | `backend/arbicore/config/scanner_config.py` | Refactored into a multi-family surface. |
| Prior single-family Scanner UI (Phase 10.4 attempt v1) | `frontend/src/v2/pages/SettingsPage.jsx` | Replaced by the multi-family `<Scanner />` component. |
| `_V2_SCANNERS` in-process stub | `backend/server.py` (Operations page — untouched) | **Deliberately left** — Operations page's scanner list is used elsewhere; the Settings › Scanner surface is the authoritative *config* surface. |

---

## B. What was delivered

### B.1 Backend — new module `arbicore/config/scanner_config.py` (~370 LOC)

Multi-family façade layered on the Phase-10 `ConfigRepo`:

**Kinds used** (all inside the shared `arbicore_config` collection):

- `scanner` — cross-family global controls (worker concurrency, cache, expiry, chains, DEX families, token families, runtime)
- `scanner.flash_loan_arb` — Flash Loan family
- `scanner.cex_arb` — CEX Arbitrage
- `scanner.dex_arb` — DEX Arbitrage
- `scanner.cross_chain_arb` — Cross-chain Arbitrage
- `scanner.funding_arb` — Funding Arbitrage
- `scanner.launch_arb` — Launch Arbitrage

**Public API** (canonical + inherited):

| Method | Purpose |
|---|---|
| `snapshot()` | Return global + every family in one payload — UI initial-load path |
| `ensure_seeded()` | Seed global + all six families ONCE from canonical defaults; never overwrites |
| `get_global()` / `get_family(fid)` | Read current |
| `validate_global(patch)` / `validate_family(fid, patch)` | Structural validation — numeric ranges, chain identifiers, DEX enum, gate type checks |
| `validate_global_live(patch)` | Structural + cross-check against `NetworkConfigRepo` (RPC missing → warning, not error) |
| `save_global_draft` / `save_family_draft` | Persist a validated draft |
| `apply_global` / `apply_family` | Promote patch (or pending draft) to LIVE with audit row |
| `rollback_global` / `rollback_family` | Restore previous revision snapshot |
| `global_history` / `family_history` | Per-kind audit stream |
| `pause()` / `resume()` / `reload()` | Runtime controls — thin wrappers on top of `apply_global` |

### B.2 Backend — 15 REST endpoints

All rooted under `/api/arbicore/settings/scanner/`:

- `GET  /` — snapshot (global + all families + drafts + labels + supported DEX list)
- `POST /global/validate` — live validation (cross-refs Network config)
- `POST /global/draft`
- `POST /global/apply`
- `POST /global/rollback`
- `GET  /global/history?limit=N`
- `GET  /family/{family_id}` — one family config + draft
- `POST /family/{family_id}/validate`
- `POST /family/{family_id}/draft`
- `POST /family/{family_id}/apply`
- `POST /family/{family_id}/rollback`
- `GET  /family/{family_id}/history?limit=N`
- `POST /pause` · `POST /resume` · `POST /reload`

Every unsupported `family_id` returns a diagnostic error with the list
of supported families.

### B.3 Boot seed

Wired into the startup hook alongside the other Phase-10 seeds:

```python
await _SCANNER_CONFIG.ensure_seeded()
```

Idempotent — writes canonical defaults only when no config exists.
Verified by `test_seed_is_idempotent` in the regression suite.

### B.4 Frontend — `Settings › Scanner` tab

- Added SCANNER sub-tab to `SettingsPage.jsx` (position 3 of 11).
- Component structure:
  - **Runtime bar** — RUNNING/PAUSED/DISABLED pill + Pause/Resume/Reload buttons + last_reload metadata.
  - **Global panel** — scanner enable toggle, worker concurrency, max concurrent scans, cache_s, expiry_s.
  - **Chains grid** — five chains (base, ethereum, arbitrum, optimism, polygon), each with enable toggle, RPC priority, max_gas_gwei, max_latency_ms.
  - **DEX / market families** — seven canonical DEXes (Uniswap V2/V3, Aerodrome, Sushi, Pancake, Curve, Balancer V2) each with individual toggles.
  - **Token / pair families** — 6 lists (stables, eth_pairs, wbtc_pairs, blue_chips, custom_whitelist, blacklist) with chip-based editors (add/remove).
  - **Global action bar** — Validate / Apply Global / Rollback Global.
  - **Family selector** — 6 tabs with active-tab highlight + enabled-dot indicator.
  - **Family detail panel** — for the selected family:
    - enable toggle + interval_s + verifier_concurrency inputs
    - Flash Loan → providers panel (aave_v3, balancer_v2, uniswap_v3 toggles + fee_bps display)
    - CEX / Funding → Tier A pairs chips
    - All families → gate_thresholds grid (nested pair → gate name → numeric input)
  - **Family action bar** — Validate / Apply / Rollback (per family).

- Every interactive element has a stable `data-testid` for the testing agent (49 test IDs total across the tab).

### B.5 Regression coverage

Added `backend/tests/test_phase10_4_scanner.py` — **20 tests**:

- Seed: canonical defaults populate every family, idempotence, actual canonical values (`balancer_v2.fee_bps == 0`, `flash_loan.enabled == False`, `cex_arb.tier_a_pairs includes BTCUSDT`).
- Global validation: valid patch, rejects negative worker concurrency, unknown market family, unknown chain, out-of-range confidence; warning when no chain / no DEX enabled.
- Live validation: warns on chain enabled with no RPC in Network config.
- Family validation: valid patch, rejects unknown family, negative interval, bad gate type; Flash Loan warning when no provider enabled.
- Apply / Rollback: per-family + global; pause/resume; reload stamps runtime; draft → apply flow; per-family history isolation; snapshot integrity.

Every test is offline-safe (in-process fake Mongo, no HTTP).

Full suite: **460 passed, 2 skipped in 85.70s**. Zero regressions.

---

## C. Backend → UI migration recap (Phase 10 total)

| Migrated to persistent UI | Count |
|---|---|
| Phase 10.1 (Network config) | 9 knobs |
| Phase 10.2 (Stubs → Mongo) | 4 in-process dicts + full audit trail |
| Phase 10.3 (Telegram alerts) | 22 rule toggles + bot token + chat + cooldown |
| **Phase 10.4 (Scanner config)** | **~70 knobs** across 6 families (worker concurrency, chains × 5, DEX × 7, token families × 6, gates × 4–8 per family, per-family providers/pairs/interval) |

Everything above is now operator-editable **without SSH, without `.env`
edits, and without a backend restart** — with full Draft, Validate,
Apply, Rollback, and Audit trail on every knob.

---

## D. `.env` residency check — unchanged

Phase 10.4 introduced ZERO new environment variables. The seven infra-
only env vars from Phase 10.3 remain the only ones required:

`MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`, `VAULT_KEY`,
`SIGNING_ACTIVE_KEY_VERSION`, `SIGNING_ED25519_PRIVATE_V1`,
`REACT_APP_BACKEND_URL` (frontend build).

---

## E. Flash Loan LIMITED_LIVE readiness — UNCHANGED

Verified by `GET /api/arbicore/wizard/state`:

```
overall_status: BLOCKED
blockers: ['rpc', 'wallet', 'executor']
step_count: 10
```

Identical to the Phase 10.3 report. Phase 10.4 introduced:
- 0 new blockers
- 0 mutations to the broadcast pipeline
- 0 schema changes on any existing collection
- 0 API contract breaks

The Flash Loan family ships **disabled by default** (per canonical
D-4.1 institutional safety) — the operator must opt in via
Settings › Scanner › Family: Flash Loan → toggle enabled → APPLY.

---

## F. Screenshots

`/v2/settings/scanner` renders (visually confirmed):

- Runtime bar: `RUNNING` pill + PAUSE / RELOAD buttons
- Global (cross-family) panel: enabled toggle, 4-column knobs (workers=4, max=4, cache=30s, expiry=300s)
- Chains grid: base (ON, gas 0.1) · ethereum (OFF, gas 30) · arbitrum · optimism · polygon (all OFF)
- DEX / market families: 7 toggles — uniswap_v2 ON, uniswap_v3 ON, aerodrome ON, sushi OFF, pancake OFF, curve ON, balancer_v2 ON
- Token/pair families header visible; scrolling continues with 6 category chip editors
- Family selector row (6 tabs) + family-specific detail
- Per-family action bar: VALIDATE / APPLY / ROLLBACK

Every element is data-testid-tagged for the testing agent.

---

## G. Verdict

Phase 10.4 is **complete and non-invasive**. Canonical multi-family
scanner configuration is now editable from the UI while preserving
every existing runtime behaviour (families default-disabled where the
canonical bundle marked them disabled; interval/gate defaults are
canonical values, not made-up).

Deferred, as instructed:
- Secrets Management UI (Phase 10.5)
- VPS Operations (Phase 10.7)
- Import / Export bundle (Phase 10.8)
- Autonomous scanner tuning (post-1.2)
