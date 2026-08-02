# Phase 10.1 → 10.3 · Consolidated Implementation Report

**Date:** 2026-08-01
**Baseline:** 418 passing → **440 passing** + 2 skipped (**442 total**)
**Philosophy:** VERIFY → REUSE → REFINE → ACTIVATE → MERGE → NEW
**Result:** Configuration foundation live · in-memory stubs replaced · Telegram alerts activated · Flash Loan LIMITED_LIVE readiness unchanged

---

## A. What was delivered (three phases, one review point)

### Phase 10.1 — Configuration Foundation

- `backend/arbicore/config/persistent.py` (~330 LOC) — brand-new substrate:
  - `ConfigRepo` — generic Draft / Apply / Rollback / Audit primitives
    backed by three Mongo collections (`arbicore_config`,
    `arbicore_config_drafts`, `arbicore_config_audit`). Every apply
    generates a `revision_id`; every rollback records a new row that
    references the restored revision.
  - `NetworkConfigRepo` — per-chain RPC URLs (list, primary + failover),
    chain enable/disable, executor addresses, gas settings, native price,
    MEV relay URL. Boot-time env-seed: reads `ARBICORE_RPC_URL`,
    `ARBICORE_EXECUTOR_ADDRESS_BASE`, `ARBICORE_GAS_PRICE_GWEI`, etc.
    once on first boot and never overwrites afterward — perfect
    backward compat.
  - `validate()` — non-mutating; returns `{ok, errors, warnings}`.
  - `resolve_rpc_url` / `resolve_executor_address` env-fallback helpers
    for legacy call sites during the migration window.
- 6 REST endpoints:
  - `GET  /api/arbicore/settings/network`
  - `POST /api/arbicore/settings/network/validate`
  - `POST /api/arbicore/settings/network/draft`
  - `POST /api/arbicore/settings/network/apply`
  - `POST /api/arbicore/settings/network/rollback`
  - `GET  /api/arbicore/settings/network/history`
- `GET  /api/arbicore/settings/config/history?kind=…` — one endpoint
  to browse every config kind's audit trail.

### Phase 10.2 — Persistent replacements for `_V2_*` stubs

- `backend/arbicore/config/stubs_migration.py` (~200 LOC):
  - `OperatorAccountRepo` (`operator_account`) — display name, email,
    MFA, session TTL
  - `ExecutionSettingsRepo` (`execution_settings`) — max position,
    daily notional, slippage_bps, min_confidence, min_safety,
    auto-execute knobs
  - `OperationalFlagsRepo` (`operational_flags`) — maintenance mode,
    trading pause, read-only, dev mode, verbose logging, feature flags
- Each wraps the same `ConfigRepo` — inherits Draft/Apply/Rollback/Audit.
- The five existing endpoints (`GET/PATCH /settings/account`,
  `/settings/execution`, `/settings/notifications`, `/settings/operational`)
  were swapped **in place** — the response shape is unchanged so the
  existing `SettingsPage.jsx` tabs work without modification.

### Phase 10.3 — Telegram alerts activation

- `backend/arbicore/notifications/telegram.py` (~230 LOC) — faithful
  port of the canonical `services/telegram_alerts.py` from the v1.0.2
  bundle, adapted to reuse the existing `SecretRegistry` for bot-token
  encryption (no duplicate crypto). Ships **DORMANT**: `enabled=false`,
  no token, no chat.
- Config stored under kind `telegram_alerts` in `arbicore_config`, so
  it inherits the same Draft/Apply/Rollback/Audit primitives as every
  other setting.
- Alert log persists in `telegram_alerts_log` (one row per send
  attempt, sent-or-not).
- 5 REST endpoints:
  - `GET  /api/arbicore/settings/telegram`
  - `PUT  /api/arbicore/settings/telegram`
  - `POST /api/arbicore/settings/telegram/test`
  - `GET  /api/arbicore/settings/telegram/log`
  - `POST /api/arbicore/settings/telegram/emit` — used by tests +
    integrations that want to notify without a live event
- 18-rule matrix (verdict_flip, kill_switch_engaged, first_broadcast,
  broadcast_sent, capital_denied, executor_verified, etc.) with
  per-kind cooldown ledger + operator-editable cooldown seconds.

### Frontend

- `frontend/src/v2/pages/SettingsPage.jsx` — added three new sub-tabs
  (**Network**, **Telegram**, **Audit**) alongside the existing seven.
  Total sub-tabs now: 10.
- `frontend/src/v2/lib/api.js` — added 11 helper functions for the
  Phase-10 REST surface.
- Every new interactive element carries `data-testid` for the testing
  agent.

### Backend regression

```
$ cd /app/backend && pytest tests/ -q
440 passed, 2 skipped in 80.25s
```

Progression:
- Phase 8 baseline: 396 + 2 skipped = 398
- Phase 9a: 407 + 2 skipped = 409
- Phase 9b: 418 + 2 skipped = 420
- **Phase 10.1–10.3: 440 + 2 skipped = 442** (+22 new tests, 0 regressions)

---

## B. Backend → UI migration table

Configurations moved from environment / in-process stubs to persistent UI-managed settings:

| Source | Was | Now | UI location |
|---|---|---|---|
| `ARBICORE_RPC_URL` (env) | env only | `network.rpc_urls[chain][]` (list, failover) | Settings › Network |
| `ARBICORE_RPC_URL_BASE` (env) | env only | `network.rpc_urls.base[]` | Settings › Network |
| `ARBICORE_EXECUTOR_ADDRESS_BASE` (env) | env only | `network.executor_addresses.base` | Settings › Network |
| `ARBICORE_GAS_PRICE_GWEI` (env) | env only | `network.gas_settings.base.gas_price_gwei` | Settings › Network |
| `ARBICORE_MAX_FEE_GWEI` (env) | env only | `network.gas_settings.base.max_fee_gwei` | Settings › Network |
| `ARBICORE_PRIO_FEE_GWEI` (env) | env only | `network.gas_settings.base.prio_fee_gwei` | Settings › Network |
| `ARBICORE_NATIVE_PRICE_USD` (env) | env only | `network.native_price_usd.base` | Settings › Network |
| `ARBICORE_MEV_RELAY_URL` (env) | env only | `network.mev_relay_urls.base` | Settings › Network |
| Chain enable/disable | hard-coded | `network.chains_enabled[chain]` | Settings › Network |
| `_V2_ACCOUNT` (in-process) | lost on restart | `operator_account` Mongo doc | Settings › Account |
| `_V2_EXECUTION` (in-process) | lost on restart | `execution_settings` Mongo doc | Settings › Execution |
| `_V2_NOTIFICATIONS` (in-process) | lost on restart | `telegram_alerts` Mongo doc | Settings › Notifications (legacy) + Telegram |
| `_V2_OPERATIONAL` (in-process) | lost on restart | `operational_flags` Mongo doc | Settings › Operational |
| Telegram bot token | not present | Fernet-wrapped in `arbicore_secrets`, handle in `telegram_alerts.token_handle_id` | Settings › Telegram |
| Telegram chat ID | not present | `telegram_alerts.chat_id` | Settings › Telegram |
| Telegram alert rules (18) | not present | `telegram_alerts.rules{}` | Settings › Telegram |
| Per-kind cooldown | not present | `telegram_alerts.rules.cooldown_s` | Settings › Telegram |

**Total: 17 knobs promoted from `.env` / in-memory to UI-managed
persistent config.**

---

## C. Configurations intentionally kept in `.env`

Only true infrastructure / bootstrap / cryptographic-root values remain
in `backend/.env`:

| Env var | Why it stays |
|---|---|
| `MONGO_URL` | Bootstrap — the config layer itself lives in Mongo |
| `DB_NAME` | Bootstrap — same as above |
| `CORS_ORIGINS` | Ingress + CORS bind at process start; changing requires a restart |
| `VAULT_KEY` (Fernet master) | Encryption master; if compromised, every wrapped secret is lost |
| `SIGNING_ACTIVE_KEY_VERSION` | Key rotation is a distinct P1 flow (deliberately not one-click) |
| `SIGNING_ED25519_PRIVATE_V1` | Root signing key material |
| `REACT_APP_BACKEND_URL` (frontend) | Kubernetes ingress binding — build-time |

Every other environment variable is either:
- Retired (Phase 10.1 migration table above), or
- Still honoured as a boot-time seed default for backward compat but
  overridden by any Mongo-side value.

---

## D. Flash Loan LIMITED_LIVE readiness — unchanged

Verified by hitting `GET /api/arbicore/wizard/state`:

```
overall_status: BLOCKED
blockers: ['rpc', 'wallet', 'executor']
step_count: 10
```

Same three operator-side blockers as Phase 9 (Section E of the readiness
audit). Phase 10 introduced zero new blockers, zero deployment-surface
changes, and left the certifier + broadcaster + evidence pipeline
untouched.

The remaining operator actions before VPS deployment are identical to
Phase 9:

1. **Set an RPC** — now via Settings › Network (no more `.env` edit needed).
2. **Fund a burner** with ~0.02 ETH on Base.
3. **Register the wallet + wrap key** via existing REST (Secrets UI
   ships in Phase 10.5).
4. **Deploy `FlashLoanReceiver.sol`** on Base (one-time, ~$0.10 gas).
5. **Set executor address** — now via Settings › Network (no more `.env` edit).
6. **Kill-switch off → mode LIMITED_LIVE → certification pass → Confirm.**

Steps 1 and 5 no longer require SSH into the VPS or hand-editing
`.env`. The operator can do them from the Settings › Network page and
apply with one click — Draft, Validate, Apply, Rollback all supported.

---

## E. Screenshots

The full render of each new tab has been captured; the highlights:

- **Settings › Network** — per-chain cards (base, ethereum, arbitrum, optimism, polygon) each with enable toggle, RPC URL list, executor address, MEV relay URL, gas price (gwei), native price (USD). Validate / Save Draft / Apply / Rollback action bar. Base is seeded to `https://mainnet.base.org` from the boot env.
- **Settings › Telegram** — Bot Configuration card (enabled toggle, chat ID input, bot token input, SAVE + SEND TEST). Alert Rules card with 18 individual toggles + cooldown seconds + min-spread threshold. Alert History table.
- **Settings › Audit** — every configuration change with `at / kind / action / actor / reason / revision`; filter by kind. Rollback rows highlighted amber.

All three tabs match the existing v2 design language (obsidian + amber
+ Plex Mono).

---

## F. Test coverage delta

| File | Tests added | Coverage |
|---|---|---|
| `tests/test_phase10_config.py` | **22** | ConfigRepo (Draft/Apply/Rollback/History) · NetworkConfigRepo (seed-from-env + idempotence + validate + rollback) · StubsMigration (execution/operational/account patches) · TelegramAlertService (disabled/enabled/rule-gated/cooldown-gated/log persistence) |

Every test is offline-safe (no HTTP, no network). Full suite:
`440 passed, 2 skipped in 80.25s`. Zero regressions.

---

## G. Recommendation

Ready for review. When approved, proceed to **Phase 10.4** (activate
canonical scanner_config_repo tree) — but as this audit noted, hold that
step until the operator has validated the Network + Telegram config UI on
the first LIMITED_LIVE transaction so we don't stack activations before
proving the substrate.
