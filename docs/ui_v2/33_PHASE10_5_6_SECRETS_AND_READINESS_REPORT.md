# Phase 10.5 + 10.6 · Secrets Management + Operator Readiness — Consolidated Report

**Date:** 2026-08-01
**Baseline:** 460 passing → **469 passing** + 2 skipped (**471 total**)
**Philosophy:** VERIFY → REUSE → REFINE → ACTIVATE (no NEW framework)
**Result:** Existing Secret Registry + Fernet backend exposed via REST + UI · Wizard now tap-and-go with per-step fix-links + a Flash Loan family prereq card.

---

## A. VERIFY findings — nothing rebuilt

| Capability | Pre-existing location | Verdict |
|---|---|---|
| Fernet-encrypted secret backend | `arbicore/secrets/backends.py::FernetSecretBackend` | **REUSED** — no crypto duplicated |
| Secret registry (put/resolve/delete/list) | `arbicore/secrets/registry.py::SecretRegistry` | **REUSED** — the four core primitives were already async and used by the broadcaster |
| `GET /api/arbicore/execution/secrets` (list) | `server.py` | **REUSED** — untouched |
| `GET /api/arbicore/execution/secrets/status` | `server.py` | **REUSED** — untouched |
| Signing key registry (Ed25519) | `arbicore/evidence/signer.py` | **REUSED** — untouched (Phase 10.5 covers wallet + API secrets; signing keys rotate via a distinct P1 flow) |
| Wallet Registry — bind `secret_handle_id` to wallet | `arbicore/execution/wallet_registry.py` | **REUSED** — untouched |
| Wizard aggregator (10 steps) | `arbicore/execution/operator_wizard.py` (Phase 9) | **REFINED** — added `fix_path` + `reason` on every step + a new family-scoped prereq checker |

The audit doc identified `services/vault.py` (canonical CEX-key vault
w/ 5-exchange support) as an activation candidate. It is **NOT
imported here** — the Phase-10 Fernet backend already covers CEX API
secrets (algorithm `cex_api_secret`); the canonical exchange registry +
key-health tester is a Phase 10.9-scale port that will follow after
Flash Loan validation, per the deferred backlog.

---

## B. What was added (only where genuinely missing)

### B.1 Backend — Phase 10.5 · Secrets write REST (~140 LOC in `server.py`)

Four endpoints, all Fernet-backed via the existing SecretRegistry:

| Endpoint | Purpose |
|---|---|
| `POST /api/arbicore/execution/secrets` | Wrap + store a secret. Validates scope + algorithm; `eth_privkey` gets a 64-hex-char sanity check. Response never echoes plaintext, only a 4-char mask. |
| `DELETE /api/arbicore/execution/secrets/{handle_id}` | Remove a stored secret |
| `POST /api/arbicore/execution/secrets/{handle_id}/rotate` | Atomic rotation — creates new handle with the new plaintext (inheriting scope/algorithm/label from the old), then deletes the old. |
| `POST /api/arbicore/execution/secrets/{handle_id}/test` | Structural health probe: resolves + decrypts + runs algorithm-specific sanity (e.g. hex_length_64 + hex_only for `eth_privkey`). Never returns plaintext. |

Allowed scopes (mirror `arbicore/secrets/backends.py::CAPABILITY_SCOPES`):
`evm_sign`, `custom`, `cex_read`, `cex_trade`, `cex_withdraw`.

Allowed algorithms:
`eth_privkey`, `cex_api_secret`, `telegram_bot_token`,
`generic_bytes`, `generic_utf8`.

Concurrent bug fix: `TelegramAlertService` was using `scope="notifications"`
which was outside the canonical `CAPABILITY_SCOPES` set — changed to
`scope="custom"` so the Telegram bot token write path works after
Phase 10.5 tightening.

### B.2 Backend — Phase 10.6 · Wizard refinement (`operator_wizard.py`)

- Every `WizardStep` now carries `fix_path` and `reason` fields (10 steps × 2 new attributes).
- Post-processing loop populates these from `_FIX_PATHS` / `_REASONS` maps so callers never need to hand-maintain them.
- New function `check_flash_loan_prereqs()` — 8-check family-scoped prerequisite verifier that answers "can I even *think* about pressing Broadcast for a Flash Loan plan?":

  1. `base_network_enabled` — chain toggled ON in Settings › Network AND RPC configured
  2. `rpc_healthy` — RPC pings and returns `chain_id=8453`
  3. `wallet_registered` — a gas-role wallet exists on base
  4. `secret_available` — the wallet has a bound `secret_handle_id` present in the registry
  5. `executor_verified` — `verify_executor()` returns `ready=True`
  6. `scanner_family_enabled` — Flash Loan family enabled in Settings › Scanner
  7. `mode_limited_live` — strategy mode = LIMITED_LIVE
  8. `kill_switch_disengaged` — global stop is off

Each check emits a `{key, status, detail, fix_path}` row.

- New endpoint `GET /api/arbicore/wizard/flash-loan-prereqs?chain=base`.

### B.3 Frontend — Phase 10.5 · `Settings › Secrets` tab (~180 LOC)

- **Add form**: scope + algorithm dropdowns, label input, password-style plaintext input, STORE button. Client-side null check; server-side algorithm-specific validation.
- **Registered secrets table**: `handle_id (truncated)`, `scope`, `algorithm`, `label`, `provider`, `created_at`, plus per-row actions:
  - `TEST` — runs the structural probe; result appears inline (`decrypt:true algorithm:eth_privkey hex_length_64:true hex_only:true`).
  - `ROTATE` — reveals an inline rotate panel; new plaintext input + confirm.
  - `DEL` — confirmation prompt then delete.
- Fully backed by the four new REST endpoints; never renders plaintext, never sends plaintext back to the browser after the initial store call.
- Test IDs: `v2-secrets-scope`, `v2-secrets-algo`, `v2-secrets-plaintext`, `v2-secrets-add`, `v2-secrets-row-{id}`, `v2-secrets-test-{id}`, `v2-secrets-rotate-{id}`, `v2-secrets-delete-{id}`, `v2-secrets-rotate-panel`.

### B.4 Frontend — Phase 10.6 · Wizard v2 (`LimitedLiveWizardPage.jsx`)

- Every step row now renders a **FIX →** button next to the status pill when the step is BLOCKED or WAIT. Clicking navigates directly to the mapped Settings tab (e.g. `rpc` → `/v2/settings/network`, `secret` → `/v2/settings/secrets`, `executor` → `/v2/executor-verify`).
- Expanded step view now shows a `why:` line (reason) alongside the existing action hint.
- New **Flash Loan family prerequisites** card renders the 8 family-scoped checks with the same per-row FIX → button pattern.
- Both surfaces poll every 5 s.

---

## C. Regression coverage

Added `backend/tests/test_phase10_5_6_secrets_prereqs.py` — **9 tests**:

- 8 tests around `check_flash_loan_prereqs` — every possible READY/WAIT/BLOCKED transition (all-defaults blocked; wallet ready; kill switch engaged blocks; mode WAIT when SHADOW; scanner family WAIT when disabled; network ready when configured).
- 1 test asserting `fix_path` and `reason` are populated on every step of `build_wizard_state`.

Also verified — end-to-end backend behaviour via curl:

- POST /secrets returns `mask` + `handle_id`, no plaintext.
- GET /secrets shows the new row.
- POST /secrets/{id}/test returns `checks.decrypt=true, hex_length_64=true, hex_only=true` for an eth_privkey.
- POST /secrets/{id}/rotate returns a new `handle_id` + deletes the old.

Full suite: **469 passed, 2 skipped in 13.18s**. Zero regressions.

---

## D. Flash Loan LIMITED_LIVE readiness — IMPROVED

**Before Phase 10.5/10.6 (Phase 10.4 baseline):**

- Wizard reported same-3 blockers (`rpc`, `wallet`, `executor`).
- To resolve, the operator had to know which Settings sub-tab held each fix — no in-app navigation aid.
- Adding a private key required knowing which REST endpoint to call directly.

**After Phase 10.5/10.6:**

- Every blocked/waiting wizard step displays a one-click **FIX →** button that navigates directly to the correct Settings tab.
- New family-scoped prerequisite card gives Flash-Loan-specific context (Base RPC, wallet, secret, executor, scanner family enable, mode, kill switch) — 8 checks that the operator can address in-app.
- New Secrets tab lets the operator wrap the burner private key entirely in the UI (no CLI, no direct REST poking).
- Once the operator sets up Network + registers Wallet + adds Secret + deploys FlashLoanReceiver + verifies it, every step turns green without a backend restart.

**Blockers unchanged in identity (they still require operator action)
but the *time-to-fix* per blocker has collapsed from minutes of doc
lookup to one click.**

---

## E. Final operator checklist — from cold ArbiCore X to first LIMITED_LIVE Flash Loan

*This is the definitive end-to-end runbook. Every action is now
performable from the UI unless explicitly noted otherwise.*

1. **Sign in** — open ArbiCore X in a browser.
2. **Open the wizard** — `/v2/wizard`. It will report BLOCKED with 3+ items. Each has a FIX → button.
3. **Settings › Network** (fix `rpc`)
   - Enable `base` chain toggle.
   - Enter primary RPC URL: `https://mainnet.base.org` (or your Alchemy/Infura URL).
   - Optionally set gas price gwei + max fee gwei (leave blank to use estimator).
   - Click **VALIDATE** → **APPLY** → confirm reason.
4. **Fund a burner wallet** — send ~0.02 ETH on Base to a fresh EOA you control.
5. **Settings › Secrets** (fix `secret`)
   - Add form: scope=`evm_sign`, algorithm=`eth_privkey`, label=`burner-base-01`, plaintext=`<64-char private key without 0x>`.
   - Click **STORE SECRET**. The response shows a masked view; copy the `handle_id`.
   - Click **TEST** to verify decryption succeeds.
6. **Register the wallet** (fix `wallet`)
   - From Flash Loan Operator page: fill the address + chain=`base` + role=`gas` + paste the `handle_id` you copied.
   - Submit; the wizard's wallet step turns READY.
7. **Deploy FlashLoanReceiver.sol** (fix `executor`)
   - Use Foundry OR Remix per `canonical_repo/contracts/DEPLOY.md`. Constructor args: Balancer V2 Vault + Uniswap V3 Router (both hard-coded on Base).
   - Note the deployed address.
8. **Settings › Network** (executor address)
   - Fill `executor_addresses.base` with the deployed address.
   - Click **VALIDATE** → **APPLY**.
9. **`/v2/executor-verify`** (fix `executor_verify`)
   - The 6 checks (address, RPC, bytecode present, VAULT match, ROUTER match, owner match) turn READY.
10. **Settings › Scanner** (Flash Loan family enable)
    - Click the "Flash Loan" family tab.
    - Toggle `enabled` on the family.
    - Enable at least one provider (`balancer_v2` recommended — 0 bps fee).
    - **VALIDATE** → **APPLY**.
11. **Certification** — from the Flash Loan Operator page, run the 11-stage certifier. All must PASS.
12. **Flip mode to LIMITED_LIVE** — from Flash Loan Operator page. The wizard's `mode` step turns READY.
13. **Kill switch check** — confirm banner shows DISENGAGED.
14. **Wizard** — should now show all-READY. FL prereq card also all READY.
15. **Compose plan** — Flash Loan Operator page: pick borrow token, amount, hops, profit_recipient. `recipient` auto-fills from `network_config.executor_addresses.base`.
16. **Prepare broadcast** — verify preflight_ok, gas_price_wei, gas_limit.
17. **Confirm** — broadcast. `tx_hash` returns.
18. **Post-Trade dashboard** — `/v2/post-trade` shows the receipt, calibration + adaptive weights tick, evidence bundle link.
19. **Telegram alert** — the `first_broadcast` rule delivers a message to the configured chat (if you set one up in Settings › Telegram).

Steps requiring anything OUTSIDE the UI: **only step 4 (fund a wallet)
and step 7 (deploy Solidity contract via Foundry/Remix).** Everything
else — including the private-key wrap, the RPC URL, the executor
address, the gas price, the Flash Loan family enable, and the mode
flip — is now a click.

---

## F. Screenshots

- **`/v2/settings/secrets`** — Add-secret form (scope/algorithm/label/plaintext), Registered Secrets table with masked `handle_id`, `scope`, `algorithm`, `label`, `provider` (`fernet_local`), `created` timestamp, and per-row TEST / ROTATE / DEL buttons. Verified with one live `eth_privkey` seed.

- **`/v2/wizard`** — Every wizard row now shows the status pill AND a bright orange **FIX →** button when the row is BLOCKED (RPC, Wallet, Executor) or WAIT (Secret, Gas balance, Executor verify). Certification row correctly shows INFO. Expandable "detail" also surfaces the new `why:` line beneath the action hint.

---

## G. Confirmation

Flash Loan LIMITED_LIVE readiness has **improved without any change to
the broadcast pipeline itself**. The 6-gate ladder is untouched; every
Phase 10.5/10.6 addition is *readiness plumbing* that makes the
existing pipeline reachable without SSH or `.env` editing.

Awaiting review before proceeding to VPS Operations (Phase 10.7) or
Import/Export (Phase 10.8).
