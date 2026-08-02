# Phase 10 · Configuration & Operations — Canonical Audit

**Date:** 2026-08-01 · **Mode:** READ-ONLY audit; no code was modified
**Philosophy:** VERIFY → REUSE → REFINE → ACTIVATE → MERGE → NEW
**Baseline:** ArbiCore X v1.1.0-candidate · 418 passing + 2 skipped
**Objective:** determine which operator-configuration surfaces already
exist (in current backend, in current frontend, or DORMANT inside the
canonical bundle) so that new work is limited to activation / UI
exposure / refinement — **not rebuilding.**

Target: **90–95 % of operational configuration editable from the UI**,
with only true infra secrets (`MONGO_URL`, `VAULT_KEY`,
`SIGNING_ED25519_PRIVATE_V1`, `DB_NAME`, JWT/CORS) staying in `.env`.

---

## 0. Executive verdict

| Bucket | Count | Note |
|---|---|---|
| **A. Already live in current backend + frontend** | 6 | Wallets, Kill Switch, Capital Policy, Mode, Certification config, Discovery start/stop |
| **B. Backend live, UI absent or stub** | 8 | Secrets (POST), Capital Policy PATCH, Executor Verify, RPC Check, Wallet audit history, Kill switch audit, Discovery interval, Post-Trade |
| **C. Config exists in canonical bundle — DORMANT** | 12 | Scanner config repo (all 6 scanner families), scanner CRUD REST, Telegram alerts, exchange API-key vault, execution config service, key-health tester, venue capabilities repo, discovery-source enable/disable, launch scanner sources, cross-chain bridges, flash-loan providers, gate-analysis |
| **D. Stub-only (in-process dict) in current backend, needs persistence** | 7 | `_V2_ACCOUNT`, `_V2_EXECUTION`, `_V2_NOTIFICATIONS`, `_V2_OPERATIONAL`, `_V2_SCANNERS`, exchanges list, vaults list |
| **E. Genuinely new work** | 5 | Network config repo (`.env` replacement for RPC + executor + gas), Draft/Apply/Rollback state machine on all config endpoints, Import/Export bundle, Version-history browser, VPS restart REST |
| **F. Must remain infra (never UI)** | 5 | `MONGO_URL`, `DB_NAME`, `VAULT_KEY`, `SIGNING_ED25519_PRIVATE_V1`, `CORS_ORIGINS` |

**Reuse ratio (existing / total surface):** **~72 %** — the majority of
Phase 10's asked-for surface is already implemented somewhere in the
codebase and only needs activation / UI wiring.

---

## 1. Detailed audit by area

### 1.1 Network Configuration

| Item | Current backend | Current frontend | Canonical bundle | Verdict |
|---|---|---|---|---|
| Primary RPC URL | ENV `ARBICORE_RPC_URL` (`wallet_balance.py:70`) | none | none | **NEW** — Mongo `network_config` collection (~30 LOC) |
| Backup / multi RPC | ENV supports comma-separated in `_rpc_urls_for` | none | none | **REFINE** — same repo, list field |
| Active chain | Hard-coded 5-chain map (`BALANCER_V2_VAULT_BY_CHAIN`) | Chain picker in Flash Loan Operator page | none | **REFINE** — surface chain enable/disable in UI |
| Chain enable/disable | none | none | none | **NEW** — boolean per chain in `network_config` |
| Provider failover | `WalletBalanceReader._rpc_urls_for` already iterates list | none | none | **EXPOSE** — surface the ordered list in UI |
| RPC health check | **EXISTS** — `GET /api/arbicore/rpc/check` (Phase 9) | none | none | **EXPOSE** — new Settings > Network panel |

**Estimated effort:** 1 backend repo (~80 LOC) + 1 UI panel (~120 LOC) + 3 tests.

### 1.2 Wallet Management

| Item | Current backend | Current frontend | Canonical bundle | Verdict |
|---|---|---|---|---|
| Wallet Registry | **EXISTS** — `WalletRegistryRepo` in Mongo; CRUD via REST | Flash Loan Operator page | (same code) | **ACTIVATED** |
| Gas Wallet | Role `execution_role: "gas"` supported | list + register form in Operator page | (same) | **LIVE** |
| Receiving / Funding / Watch-only | Roles `treasury`, `watch_only` supported in `EXECUTION_ROLES` | Role picker in Operator page | (same) | **LIVE** |
| Multi-wallet | Registry supports N wallets per chain × role | Operator page lists all | (same) | **LIVE** |
| Wallet balance | `GET /api/arbicore/execution/wallets/{id}/balance` | rendered in Wallet Health card | (same) | **LIVE** |
| Wallet audit history | `GET /api/arbicore/execution/wallets/audit/history` | ❌ **not surfaced** | (same) | **EXPOSE** — add tab in Settings > Wallets |

**Estimated effort:** 1 UI panel (~80 LOC) — no backend work.

### 1.3 Secret Management

| Item | Current backend | Current frontend | Canonical bundle | Verdict |
|---|---|---|---|---|
| Fernet backend | `FernetSecretBackend` on `arbicore_secrets` — encrypt at rest | none | (same) | **LIVE** but has no POST |
| Secret Registry | `SecretRegistry.list_handles / put / delete / resolve` | none | (same) | **LIVE**; UI needed |
| Add secret (POST) | ❌ **REST missing** — `SecretRegistry.put()` exists but not wired | none | Canonical has `services/vault.py` POST for exchange keys | **REFINE** — add `POST /api/arbicore/execution/secrets` (~15 LOC wrap around registry.put) |
| Private key wrap | `FernetSecretBackend.put(scope='broadcast')` | none | (same) | **EXPOSE** |
| API keys (CEX) | ❌ absent | Exchanges list is STUB (in-process dict) | **DORMANT** — `services/vault.py` + `services/key_health.py` in canonical bundle (5 exchanges: xt, mexc, gate, bitmart, coinstore) | **ACTIVATE** from bundle |
| RPC tokens | ENV only | none | none | **NEW** — piggyback on `network_config` |
| Telegram tokens | ❌ absent in current | Stubbed | **DORMANT** — `services/telegram_alerts.py` uses `vault.encrypt/decrypt` | **ACTIVATE** from bundle |
| Encryption | Fernet (VAULT_KEY env) | none | (same) | **LIVE** |
| Rotation | `SecretRegistry.delete + put` (versioned via signing_config for Ed25519 only) | none | none | **REFINE** — add REST alias + audit trail (~30 LOC) |
| Backup / export | none | none | none | **NEW** — encrypted export bundle |

**Estimated effort:** 2 REST endpoints (~60 LOC) + activation of canonical vault (~120 LOC integration) + UI Secrets panel (~150 LOC) + 6 tests.

### 1.4 Discovery Configuration

| Item | Current backend | Current frontend | Canonical bundle | Verdict |
|---|---|---|---|---|
| Scan interval | Hard-coded `interval_s=60.0` in `server.py:210`; no per-family override | none | **DORMANT** — `scanner_config_repo.py` stores `interval_s` per scanner | **ACTIVATE** |
| Discovery cadence | Same as above | none | **DORMANT** — includes per-source `cadence_s` | **ACTIVATE** |
| Scanner enable/disable | `POST /api/arbicore/operations/scanners/{family}/action` (STUB — reads `_V2_SCANNERS` in-process list, no persistence) | Operations > Scanners page (renders 8 fake scanners) | **DORMANT** — `POST /api/arbicore/scanners/{family}/kill\|resume` on real `scanner_state_repo` | **ACTIVATE** — replace stub with canonical repo |
| Pair selection (tier A / B) | none | none | **DORMANT** — `tier_a_pairs[]`, `tier_b_pairs[]` per scanner in `DEFAULT_CEX_ARB_CONFIG` | **ACTIVATE** |
| Token allowlists / denylists | none | none | **DORMANT** — `target_coins[]` for CoinGecko source; `discovery_sources.*.enabled` toggles | **ACTIVATE** + REFINE (add explicit deny list, ~20 LOC) |
| Verifier concurrency, gate thresholds | none | none | **DORMANT** — full per-pair `gate_thresholds` map in `DEFAULT_CEX_ARB_CONFIG` | **ACTIVATE** |
| PUT scanner config | none | none | **DORMANT** — `PUT /api/arbicore/scanners/{family}/config` in `routes/scanners.py` | **ACTIVATE** |
| Gate analysis (post-hoc) | none | none | **DORMANT** — `GET /api/arbicore/scanners/{family}/gate-analysis` | **ACTIVATE** |

**Estimated effort:** Import canonical `scanner_config_repo` + `routes/scanners.py` under an adapter (~200 LOC integration; heavy diff-review); replace stub UI (~250 LOC); ~15 tests.

### 1.5 Opportunity Engines

| Engine | Current backend | Canonical bundle | Verdict |
|---|---|---|---|
| Flash Loan | **LIVE** — Phase 8/9 full stack | `arbicore/scanners/flash_loan_arbitrage/` also present (thin activator uses it) | Config already exists; **DORMANT sources+providers** (Aave, Balancer, Uniswap) enable/disable |
| Triangular Arbitrage | Not present in current backend | Not directly present (DEX arbitrage covers hop-chains) | **NEW** if user wants a distinct engine — but see Note below |
| Cross-chain Arbitrage | ENV flag in `_V2_OPERATIONAL.feature_flags` (fake) | **DORMANT** — full `CrossChainArbitrageScanner` w/ bridge intelligence, chain liveness, transfer providers (LiFi + Stargate) | **ACTIVATE** |
| CEX–DEX Arbitrage | Not present in current | **DORMANT** — DEX arbitrage scanner + CEX arbitrage scanner + venue capability repo → composing CEX+DEX is trivial when both are activated | **ACTIVATE** both |
| Funding Arbitrage | Not present in current | **DORMANT** — `FundingArbitrageScanner` (`_id: "funding_arb"`, min APR diff, break-even hours) | **ACTIVATE** |
| Launch Arbitrage | Not present in current | **DORMANT** — `LaunchArbitrageScanner` + Helius venue provider + wallet profile intel (`intel/launch/` w/ 11 modules incl. smart_money, cluster_detector, phase_classifier) | **ACTIVATE** (heaviest — pulls in the `intel/` subtree) |
| Presale Engine | Not present anywhere | Not in canonical bundle | **GENUINELY NEW** — deferred until launch engine validated |

> **Note (triangular vs DEX arb):** the canonical DEX arb scanner is
> route-search-based and already handles multi-hop cycles (WETH → USDC
> → WETH). A dedicated "triangular" engine is only justified if the
> operator wants a strict 3-hop cyclic finder distinct from generic DEX
> arb. Recommend deferring.

**Estimated effort:** activation-only work, but must be sequenced. See §3 order.

### 1.6 Risk & Safety

| Item | Current backend | Current frontend | Canonical bundle | Verdict |
|---|---|---|---|---|
| Kill Switch | **LIVE** — `KillSwitchRepo` + engage/disengage/audit REST | Persistent banner on Flash Loan Operator | (same) | **LIVE** |
| Daily gas budget | ❌ not modelled distinctly | none | canonical `execution_config.limits.max_daily_loss_usd` (proxy) | **REFINE** — add `daily_gas_budget_native` to `capital_policy` |
| Capital limits | **LIVE** — `CapitalPolicyRepo` with `min_of` pool% / wallet% / per-plan / daily-notional | ❌ **read-only** in Settings > Execution (stub) | (same) | **EXPOSE + wire PATCH** |
| Max slippage | ENV `SlippageEstimator` uses hardcoded default; Certifier reads `capital_policy.slippage_bps` — **but slippage_bps not in DEFAULT_POLICY** yet | Read-only in Settings stub | none | **REFINE** — add `slippage_bps` to policy schema |
| Max gas | ENV `ARBICORE_MAX_FEE_GWEI`, `ARBICORE_PRIO_FEE_GWEI` | none | canonical `execution_config.limits` | **REFINE** — add fields to capital policy |
| Retry policy | Certifier stages have per-stage retry inline | none | canonical `services/http_retry.py` (scanner side) | **NEW** — add persistent retry-config per stage |
| Timeout | Same — inline | none | (same) | **NEW** — add persistent timeout config |
| Emergency stop | Kill Switch covers this | Banner covers this | (same) | **LIVE** |

**Estimated effort:** extend `DEFAULT_POLICY` schema (~40 LOC), UI PATCH form (~180 LOC), ~6 tests.

### 1.7 Learning System

| Item | Current backend | Current frontend | Canonical bundle | Verdict |
|---|---|---|---|---|
| Calibration cadence | ENV `CALIBRATION_TICK_INTERVAL_S` (default 3600) via `CalibrationConfig.from_env()` | none | (same) | **REFINE** — mirror into Mongo `learning_config` (~40 LOC) so UI-editable |
| Adaptive Weights cadence | ENV `ADAPTIVE_WEIGHTS_MODE` | none | (same) | **REFINE** — same pattern |
| Confidence thresholds | ENV `CalibrationConfig.min_samples_isotonic/platt` | none | (same) | **REFINE** — same |
| Learning retention | ENV `CalibrationConfig.window_days` | none | (same) | **REFINE** — same |
| Recommendation vs Apply | ENV `ADAPTIVE_WEIGHTS_MODE=OBSERVE|APPLY` | none | (same) | **REFINE** + UI |
| Learning-eligible provenance guard | `is_learning_eligible()` — already reads correctly | Read-only display in Intelligence page | (same) | **LIVE** |

**Estimated effort:** one `learning_config` Mongo collection (~80 LOC) + REST + UI Learning panel (~200 LOC) + 4 tests.

### 1.8 Flash Loan Configuration

| Item | Current backend | Current frontend | Canonical bundle | Verdict |
|---|---|---|---|---|
| Flash loan providers (Balancer/Aave) | Hardcoded `BALANCER_V2_VAULT_BY_CHAIN` + `AdapterRegistry` seeded at boot | none | canonical `scanner_config_repo` has per-provider enable per chain | **REFINE** — expose enable/disable |
| Router selection | Hardcoded `UNISWAP_V3_ROUTER_BY_CHAIN` | none | (same) | **REFINE** — add DEX config repo |
| Executor address | ENV `ARBICORE_EXECUTOR_ADDRESS_BASE` + `plan_doc.recipient` fallback (Phase 9) | Executor Verify page (Phase 9) surfaces it read-only | none | **REFINE** — mirror env into Mongo `network_config` |
| Gas settings | ENV `ARBICORE_GAS_PRICE_GWEI`, `ARBICORE_MAX_FEE_GWEI`, `ARBICORE_PRIO_FEE_GWEI` | none | none | **REFINE** — Mongo-persist per chain |
| Profit thresholds / Min ROI | Certifier reads from capital policy `roi_min_bps` (present in `DEFAULT_POLICY`) | Read-only stub | none | **EXPOSE + wire PATCH** |
| Certification threshold | Same as above | Same | none | **EXPOSE** |

**Estimated effort:** ~120 LOC schema + ~150 LOC UI + 5 tests.

### 1.9 DEX Configuration

| Item | Current backend | Canonical bundle | Verdict |
|---|---|---|---|
| Enable/disable DEXes | `AdapterRegistry` seeded at boot from ENV; no persistence | **DORMANT** — canonical `scanner_config_repo` + venue capability repo covers this per chain | **ACTIVATE** venue capability repo |
| Router addresses | Hardcoded `UNISWAP_V3_ROUTER_BY_CHAIN` + `AERODROME_ROUTER` via ENV | Aerodrome, Uniswap, Curve, Balancer adapters in bundle | **REFINE** — Mongo-persist per chain |
| Fee tiers | Passed per-hop via `plan_doc.hops[].fee_tier_bps` | canonical has per-scanner defaults | **EXPOSE** — Settings > DEX panel |
| Preferred routes | none | canonical `route_search.py` in each scanner | **ACTIVATE + REFINE** — add operator "prefer these routes" hints |

**Estimated effort:** ~150 LOC integration + ~200 LOC UI + 6 tests.

### 1.10 Notifications

| Item | Current backend | Current frontend | Canonical bundle | Verdict |
|---|---|---|---|---|
| Telegram | ❌ stub only | Read-only stub in Settings > Notifications | **DORMANT — FULLY BUILT** — `services/telegram_alerts.py` (encrypted bot token via vault, rules matrix, per-kind cooldown) + `routes/alerts.py` (GET/PUT settings, POST test, GET log) | **ACTIVATE** — highest ROI activation in the audit |
| Discord | none | none | none | **NEW** — mirror Telegram pattern (~120 LOC) |
| Email | Stubbed `email_enabled/email_to` in `_V2_NOTIFICATIONS` | Stub | none | **NEW** — SMTP or SendGrid (~80 LOC) |
| Push (mobile) | none | none | none | **NEW** — defer to backlog |
| Alert routing (severities × events matrix) | Stub schema present in `_V2_NOTIFICATIONS.severities/events` | Read-only stub | **DORMANT** — full `DEFAULT_RULES` matrix in `telegram_alerts.py` | **ACTIVATE** — canonical DEFAULT_RULES supersedes stub |

**Estimated effort:** Telegram is a straight port (~180 LOC integration + ~150 UI); Discord/Email are new (~200 LOC each). Ship Telegram first.

### 1.11 VPS Operations

| Item | Current backend | Current frontend | Canonical bundle | Verdict |
|---|---|---|---|---|
| Restart services | ❌ none (supervisorctl requires shell) | none | none | **NEW** — REST endpoint that shells `supervisorctl restart <name>` behind operator auth |
| Clear queues | ❌ none | none | canonical `discovery_queue` has `_coll.delete_many` but no REST | **REFINE** — expose |
| Health checks | Existing `/api/` returns 200 | none | canonical `services/health_analytics.py` (~95 LOC) | **ACTIVATE** — richer health page |
| Mongo status | `db.command('ping')` unused | none | canonical has it in health_analytics | **REFINE** |
| Redis status | ❌ Redis not present in current stack | none | not present in canonical either | **N/A** |
| Scheduler status | Discovery status endpoint | Read-only | (same) | **LIVE** |
| Worker status | Calibration/AdaptiveWeights/Evidence workers log via `logger` but no REST status | none | (same) | **NEW** — one `GET /api/arbicore/workers/status` (~40 LOC) |

**Estimated effort:** ~100 LOC backend + ~120 LOC UI + 4 tests. VPS restart endpoint is the ONLY item that needs subprocess/shell access — everything else is pure Python.

### 1.12 Environment Management (`.env` residency audit)

Every `.env` value in the current backend, classified:

| Env var | Currently required? | Can move to UI? | Recommendation |
|---|---|---|---|
| `MONGO_URL` | yes | ❌ | **STAY** — bootstrap-only |
| `DB_NAME` | yes | ❌ | **STAY** |
| `CORS_ORIGINS` | yes | ❌ | **STAY** — reload requires restart anyway |
| `VAULT_KEY` | yes | ❌ | **STAY** — encryption master |
| `SIGNING_ACTIVE_KEY_VERSION` | yes | ⚠️ partial | **STAY** — key rotation is a distinct P1 flow |
| `SIGNING_ED25519_PRIVATE_V1` | yes | ❌ | **STAY** — root key material |
| `REACT_APP_BACKEND_URL` | yes (frontend) | ❌ | **STAY** — Kubernetes ingress binding |
| `ARBICORE_RPC_URL` | yes for LIMITED_LIVE | ✅ | **MOVE** → `network_config.rpc_urls[]` |
| `ARBICORE_RPC_URL_BASE` | optional | ✅ | **MOVE** → same |
| `ARBICORE_EXECUTOR_ADDRESS_BASE` | yes for LIMITED_LIVE | ✅ | **MOVE** → `network_config.executor_addresses{}` |
| `ARBICORE_GAS_PRICE_GWEI` | optional | ✅ | **MOVE** → per-chain gas config |
| `ARBICORE_MAX_FEE_GWEI` | optional | ✅ | **MOVE** → same |
| `ARBICORE_PRIO_FEE_GWEI` | optional | ✅ | **MOVE** → same |
| `ARBICORE_NATIVE_PRICE_USD` | optional | ✅ | **MOVE** → per-chain economic config |
| `ARBICORE_MEV_RELAY_URL` | optional | ✅ | **MOVE** → per-chain MEV config |
| `ARBICORE_SIMULATOR` | optional | ✅ | **MOVE** → learning_config |
| `ARBICORE_DISCOVERY_AUTOSTART` | optional | ✅ | **MOVE** → operational config |
| `BASE_AERODROME_ROUTER` | optional | ✅ | **MOVE** → DEX config |
| `CALIBRATOR_VERSION` | optional | ✅ | **MOVE** → learning_config |
| `EVIDENCE_BUNDLE_VERSION` | optional | ✅ | **MOVE** → learning_config |
| `CALIBRATION_TICK_INTERVAL_S` | optional | ✅ | **MOVE** → learning_config |
| `ADAPTIVE_WEIGHTS_MODE` | optional | ✅ | **MOVE** → learning_config |

**Result:** of 22 backend env vars, **17 can move to UI-managed Mongo config** (77 %). The remaining 5 are true infra secrets (`MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`, `VAULT_KEY`, `SIGNING_ED25519_PRIVATE_V1`).

### 1.13 Configuration Safety (cross-cutting)

| Feature | Current backend | Canonical bundle | Verdict |
|---|---|---|---|
| Validate before apply | ✅ per-endpoint (Wallet Registry `_validate`, Capital Policy sanity checks) | ✅ same pattern | **LIVE per endpoint** — need a unified pattern |
| Save Draft | ❌ | ❌ | **NEW** — one draft doc per config kind (~60 LOC) |
| Apply | ✅ inline PATCH | ✅ inline | **LIVE** — but not two-phase |
| Rollback | ⚠️ possible from audit trail but no one-click | audit trail identical | **REFINE** — one endpoint per config family (~40 LOC) |
| Version History | ✅ **EXISTS** — audit collections: `wallet_registry_audit`, `capital_policy_audit`, `kill_switch_audit`, `execution_mode_audit` | (same) | **EXPOSE** in UI |
| Import | ❌ | ❌ | **NEW** — bundle import (~80 LOC) |
| Export | ❌ | ❌ | **NEW** — same bundle format (~40 LOC) |
| Audit Trail | ✅ per endpoint | ✅ same | **LIVE** — collapse into a single Settings > Audit page (~120 LOC UI) |

---

## 2. Frontend audit — Settings + Operations coverage

Current `SettingsPage.jsx` (461 LOC) has **7 sub-tabs**: Account, Vault,
Execution, Exchanges, Notifications, Documentation, Operational.

**All 7 are backed by in-process dicts (`_V2_*`) in `server.py` — every
edit is lost on backend restart.** Adjacent Mongo-backed truth exists
for at least 5 of these but is not wired.

Current `OperationsPage.jsx` has 7 sub-tabs (Scanners, Cycles, Venues,
Interlock, Integrations, Queues, Alerts) — Scanners is backed by the
in-process `_V2_SCANNERS` list (8 fake families), not the real
scanner_config_repo (which is DORMANT).

**Delta to reach the target:**

| New / refined Settings tab | Backing | Effort |
|---|---|---|
| **Network** (new) | `network_config` repo (NEW) + existing `/rpc/check` | 120 LOC UI |
| **Wallets** (refined — replace stub Vault) | existing `WalletRegistryRepo` | 100 LOC UI |
| **Secrets** (new) | existing `SecretRegistry` + new REST POST/DELETE | 150 LOC UI |
| **Scanners & Discovery** (activate) | canonical `scanner_config_repo` | 250 LOC UI |
| **Risk & Safety** (refine — replace stub Execution) | existing `CapitalPolicyRepo` PATCH | 180 LOC UI |
| **Learning** (refine) | new `learning_config` repo | 150 LOC UI |
| **Flash Loan / DEX** (refine) | new `network_config` + venue capability repo | 200 LOC UI |
| **Notifications** (activate Telegram) | canonical `telegram_alerts.py` service | 150 LOC UI |
| **Exchanges** (activate) | canonical `vault.py` + `key_health.py` | 200 LOC UI |
| **VPS Ops** (new) | new supervisorctl REST | 120 LOC UI |
| **Audit / History** (expose) | existing audit collections | 150 LOC UI |
| **Account / Documentation** (keep as-is) | in-process (documentation is truly static) | 0 LOC |

Total UI delta ≈ **1,770 LOC across 11 tabs** — but the Settings shell
already provides sub-nav + async loader helpers, so this is
line-copy-adapt, not new architecture.

---

## 3. Recommended implementation order

Sequenced so **each phase leaves the app in a green, testable state**;
early phases unblock later ones; nothing depends on Solidity or on
network access.

### Phase 10.1 — Foundation (Week 1) [SMALL]

Goal: introduce the persistent config substrate; every subsequent phase
plugs into it.

1. `network_config` Mongo collection + repo (~80 LOC)
   - fields: `rpc_urls`, `backup_rpcs`, `chain_enabled{}`, `executor_addresses{}`, `gas_settings{}`
   - migration reads current env vars ONCE on boot as seed
2. `GET/PUT /api/arbicore/settings/network` (~40 LOC)
3. Draft / Apply / Rollback state machine — one module reused everywhere (~90 LOC)
4. Version-history browser endpoint that unions all `*_audit` collections (~40 LOC)
5. UI: **Settings > Network** tab (~120 LOC)
6. Tests: 8 unit + 3 API

**Deliverable:** `ARBICORE_RPC_URL` + `ARBICORE_EXECUTOR_ADDRESS_BASE` +
gas gwei knobs are all UI-editable. First `.env` items retired from the
day-to-day surface.

### Phase 10.2 — Wire the existing stubs (Week 1) [SMALL]

Goal: kill the `_V2_*` in-process dicts and back them with Mongo.

1. Retire `_V2_EXECUTION` → wire to `CapitalPolicyRepo.update()` (~40 LOC)
2. Retire `_V2_NOTIFICATIONS` (stub) — leave alive until Phase 10.6
3. Retire `_V2_ACCOUNT` → new `operator_account` collection (~50 LOC)
4. Retire `_V2_OPERATIONAL` → new `operational_flags` collection (~40 LOC)
5. UI: **Settings > Risk & Safety** replaces "Execution" tab (~180 LOC)
6. Tests: 6 unit + 4 API

**Deliverable:** every existing Settings tab now persists across restarts.

### Phase 10.3 — Activate canonical Telegram alerts (Week 2) [MEDIUM]

Goal: the single highest-value canonical activation.

1. Port `services/telegram_alerts.py` + `routes/alerts.py` → `arbicore/notifications/telegram.py` + REST (~180 LOC)
2. Fernet-encrypted bot token via existing `SecretRegistry` (no new crypto)
3. Emit alerts from the six existing wave-6/7 hooks (kill switch, mode ladder, verdict flip, capital deny, executor verified, first broadcast) — via `EmissionBus` (already present)
4. UI: **Settings > Notifications** — replace stub with real Telegram config (~150 LOC)
5. Tests: 5 unit (send is mocked)

**Deliverable:** operator gets a Telegram DM the first time LIMITED_LIVE
lands, and every time kill switch flips.

### Phase 10.4 — Activate canonical scanner config (Week 2–3) [LARGE]

Goal: replace the scanner stub with real DB-backed multi-family config.

1. Port `arbicore/data/scanner_config_repo.py` + `scanner_state_repo` (~450 LOC copy)
2. Adapter shim: canonical uses `core.models`; current uses inline `_iso_now` — 30 LOC shim
3. Port `arbicore/routes/scanners.py` selectively — only the two scanners we want live first (flash_loan_arb + dex_arb) (~250 LOC)
4. UI: **Settings > Scanners & Discovery** with per-family cadence, tier A/B pairs, gate thresholds, allowlists, source enable/disable (~250 LOC)
5. Tests: 10 unit + 6 API

**Deliverable:** scanner cadence, pairs, gate thresholds are UI-editable
per family. Retires `ARBICORE_DISCOVERY_AUTOSTART` env dependency.

### Phase 10.5 — Secrets management REST + UI (Week 3) [MEDIUM]

1. `POST /api/arbicore/execution/secrets` — wrap around existing `SecretRegistry.put` (~20 LOC)
2. `DELETE /api/arbicore/execution/secrets/{handle}` — around `SecretRegistry.delete` (~15 LOC)
3. Rotation endpoint (delete + put atomic) (~30 LOC)
4. Encrypted export bundle (~60 LOC)
5. UI: **Settings > Secrets** (~150 LOC)
6. Tests: 6 unit + 4 API

**Deliverable:** operator adds/rotates private keys and API keys
entirely from the UI. `.env` no longer receives handwritten hex.

### Phase 10.6 — Learning config + Workers status (Week 3) [SMALL]

1. `learning_config` collection + repo (~80 LOC)
   - fields: `calibration_tick_interval_s`, `adaptive_weights_mode`, `min_samples_isotonic`, `min_samples_platt`, `window_days`, `calibrator_version`
2. Existing Configs read from Mongo first, ENV as fallback (backwards compat)
3. `GET /api/arbicore/workers/status` — aggregate calibration + adaptive + evidence workers
4. UI: **Settings > Learning + Workers** (~200 LOC)
5. Tests: 4 unit + 2 API

**Deliverable:** cadence + confidence thresholds + apply-mode UI-editable.

### Phase 10.7 — VPS Ops + Health page (Week 4) [SMALL]

1. `POST /api/arbicore/system/service/{name}/restart` — subprocess `supervisorctl` behind operator role check (~30 LOC)
2. Port `services/health_analytics.py` (~95 LOC)
3. `GET /api/arbicore/system/health` — Mongo ping, worker heartbeats, disk, RPC ping
4. UI: **Settings > VPS Ops** (~120 LOC)
5. Tests: 4 unit + 2 API

**Deliverable:** operator restarts services, sees system health, clears
discovery queue — no SSH needed.

### Phase 10.8 — Draft / Apply / Rollback + Import / Export (Week 4) [MEDIUM]

1. Two-phase apply on all config endpoints — `?draft=true` writes to
   sibling `*_draft` collection; `POST /apply` promotes; audit trail
   already exists (~90 LOC total, reused across every endpoint)
2. Export bundle: Mongo `mongodump` filtered by config collections (~40 LOC)
3. Import bundle: validated restore (~60 LOC)
4. UI: **Settings > Audit / History** with per-family rollback button and Import/Export buttons (~200 LOC)
5. Tests: 8 unit + 4 API

**Deliverable:** every operator-editable knob has Draft → Validate → Apply → Rollback and a one-click Export.

### Phase 10.9 — Additional scanners (Week 5+) [SEQUENTIAL, OPERATOR-GATED]

Only after 10.4's scaffolding is proven:

- 10.9a Activate DEX arb (already done via 10.4 sample)
- 10.9b Activate Funding arb
- 10.9c Activate CEX arb (needs the canonical CEX API-key vault → Phase 10.5 delivered it)
- 10.9d Activate Cross-chain arb
- 10.9e Activate Launch arb (heaviest — pulls `intel/launch` tree)
- 10.9z Discord notifications, Email SMTP — after Telegram proven

Each of these is ≈150–300 LOC of activation + ~100 LOC UI + 5–8 tests
and can ship **behind a feature flag** so operator turns them on one at
a time.

---

## 4. Effort summary

| Phase | LOC (backend + frontend) | Tests | Duration estimate |
|---|---|---|---|
| 10.1 Foundation | ~300 + 120 | 11 | 2–3 days |
| 10.2 Stub replacement | ~130 + 180 | 10 | 1–2 days |
| 10.3 Telegram activation | ~180 + 150 | 5 | 2 days |
| 10.4 Scanner config | ~700 + 250 | 16 | 4–5 days |
| 10.5 Secrets REST + UI | ~125 + 150 | 10 | 2 days |
| 10.6 Learning + Workers | ~120 + 200 | 6 | 2 days |
| 10.7 VPS Ops | ~130 + 120 | 6 | 2 days |
| 10.8 Draft/Apply/Rollback | ~190 + 200 | 12 | 3 days |
| **Subtotal (10.1–10.8)** | **~1,875 + 1,370 ≈ 3,245 LOC** | **76 tests** | **~18 dev-days** |
| 10.9 Scanner activations (each) | ~300 + 100 | 6 | 2 days per family |

**~90 % of the effort is glue + UI, not new algorithms** — the underlying
capability already lives in the codebase or the canonical bundle.

---

## 5. What must NOT be built

Per the philosophy and per this audit, **do not**:

1. Rebuild the Wallet Registry, Secret Registry, Kill Switch, Capital
   Policy, Mode Ladder, Discovery, Certifier, or Evidence pipeline —
   they exist and are green.
2. Rebuild a scanner framework — the canonical bundle has a full
   `scanner_config_repo` + 6 scanner families. Activate.
3. Rebuild Telegram alerting — the canonical `telegram_alerts.py`
   works.
4. Rebuild CEX API-key management — the canonical `vault.py` +
   `key_health.py` cover 5 exchanges already.
5. Design a new secrets format — the existing Fernet `arbicore_secrets`
   collection is sufficient; only REST + UI are missing.
6. Move `MONGO_URL`, `DB_NAME`, `VAULT_KEY`, `SIGNING_ED25519_PRIVATE_V1`,
   `CORS_ORIGINS` to UI — infrastructure bootstrap must stay in `.env`.
7. Build a Presale engine or a distinct Triangular Arbitrage engine —
   both are out-of-scope until Launch arb (which subsumes 90 % of
   Presale intelligence) and DEX arb (which handles cyclic hops) are
   validated LIVE.

---

## 6. Recommendation

**Proceed with Phase 10.1 → 10.2 → 10.3 first**, then hold for operator
validation of the Telegram alert stream on the first LIMITED_LIVE
transaction. This delivers, in ~5 dev-days:

- Network config UI (retires `ARBICORE_RPC_URL` + executor + gas env vars)
- Persistent Settings tabs (no more lost edits on restart)
- Live Telegram alerts for kill switch, mode flips, verdict flips, capital denies, first broadcast

That milestone alone converts ~9 environment variables to UI-managed
and gives the operator real-time visibility. Phases 10.4+ activate the
dormant scanner tree once the operator confirms the Telegram + network
UX is what they want.

Await go-ahead before implementing any phase.
