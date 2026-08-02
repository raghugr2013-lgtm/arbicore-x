# Operator Experience Audit — v1.0

**Date:** 2026-08-01
**Scope:** Complete LIMITED_LIVE Flash Loan operator walkthrough on the Emergent Preview environment.
**Method:** Read-only audit of every page/endpoint/wire in the workflow (`FlashLoanJourneyPage.jsx`, `FlashLoanOperatorPage.jsx`, `SettingsPage.jsx`, `ExecutorVerifyPage.jsx`, `PostTradeDashboardPage.jsx`, `server.py` §wallets/§secrets/§network/§scanner/§telegram/§wizard, `operator_journey.py`, `operator_wizard.py`, `calldata.py`, `broadcast.py`, `gas.py`, `wallet_balance.py`, `mev.py`).

---

## Executive summary

The Preview build is **software-complete** for LIMITED_LIVE execution, but the operator UX has **4 gaps that will trip a first-time operator** and 5 minor polish items. Two of the four gaps must be closed before the walkthrough can run end-to-end without CLI intervention:

* **G3** (wallet form label + response shape) — 2-line fix.
* **G4** (no manual plan composer) — without auto-discovery there is currently no UI path to compose the first LIMITED_LIVE plan.

The remaining gaps have documented workarounds and can be documented in the walkthrough manual.

---

## Findings

### 🔴 G1 — Persistent Network config is DISPLAY-ONLY (does not drive broadcast)

* **Classification:** Missing but required
* **Where seen:** `/v2/settings/network`
* **Symptom:** Operator saves `rpc_urls.base = [https://mainnet.base.org]` and `executor_addresses.base = 0x…` and clicks APPLY. Settings save cleanly, badge goes green, history writes an entry. But the broadcast pipeline still reads `os.environ`:
  * `arbicore/execution/broadcast.py` line 122 → `ARBICORE_RPC_URL`
  * `arbicore/execution/gas.py` line 180 → `ARBICORE_RPC_URL`
  * `arbicore/execution/wallet_balance.py` line 71 → `ARBICORE_RPC_URL[_BASE]`
  * `arbicore/execution/mev.py` line 80 → `ARBICORE_RPC_URL`
  * `arbicore/execution/operator_wizard.py` line 149 → `ARBICORE_EXECUTOR_ADDRESS_BASE`
  * `arbicore/execution/calldata.py` line 312 → `ARBICORE_EXECUTOR_ADDRESS_BASE`
* **Consequence:** If the operator relies only on the UI, the first broadcast will error out with "ARBICORE_RPC_URL not configured".
* **Workaround (documented in the walkthrough):** add `ARBICORE_RPC_URL=…` and `ARBICORE_EXECUTOR_ADDRESS_BASE=…` to `/app/backend/.env` and `sudo supervisorctl restart backend`.
* **Proper fix (future):** on backend startup, load persistent network config and export/mirror into `os.environ` before any module import; hot-reload the same on APPLY. Small backend shim (~40 LOC), no schema change.

### 🔴 G2 — Flash Loan Operator page has a broken duplicate Secret Registry form

* **Classification:** Already exists but not wired (correct implementation lives at `/v2/settings/secrets`)
* **Where seen:** `/v2/flash-loan-operator` → Card "2 · Secret Registry"
* **Symptom:** The card posts `{ handle_id, provider: "fernet", value_plaintext }` to `POST /api/arbicore/execution/secrets`, but the endpoint requires `{ plaintext, scope, algorithm, label }`. Every submission fails with `"scope must be one of [...]"`.
* **Consequence:** Operator hits ERROR on their very first Secret action.
* **Fix (recommended):** replace the card with a one-line `Link → /v2/settings/secrets` explaining "Store the burner private key in Settings › Secrets, then copy the returned handle_id into the Wallet form above."

### 🔴 G3 — Flash Loan Operator page — Wallet registration has 2 wire bugs

* **Classification:** Already exists but not wired
* **Where seen:** `/v2/flash-loan-operator` → Card "1 · Wallets"
* **Symptom (a):** Field labelled "Wallet name" sends `newWallet.name` in the body, but `POST /api/arbicore/execution/wallets` expects `label` — the value is silently dropped.
* **Symptom (b):** After the POST the code checks `data.wallet` but the backend returns `{ item: row }`. Consequence: the success toast never fires and `setSelectedWalletId` never runs, so the operator sees no confirmation and cannot proceed to health check.
* **Fix (recommended):** rename UI field to "Wallet label" and send `label` in the payload; check `data.item` (fallback to `data.wallet` for defensive back-compat).

### 🔴 G4 — No manual plan composer (blocks first LIMITED_LIVE broadcast)

* **Classification:** Missing but required
* **Where seen:** `/v2/flash-loan-operator` → Card "6 · Certification & Broadcast" — `certifyPlan()` requires `selectedOpp` and reads from `opps[]`
* **Symptom:** Auto-discovery for the Flash Loan family is intentionally deferred to Phase 10.9. Discovery `tick` returns 0 opportunities. With no opportunity, `selectedOpp` is null → the "Run full certification" button is disabled → no plan → no broadcast.
* **Consequence:** The operator physically has no UI path to compose the first LIMITED_LIVE plan. The only workaround today is to `curl POST /api/arbicore/execution/certification/run` from the shell — not acceptable for a first-time operator.
* **Fix (recommended, minimal):** add a **"Manual plan composer"** card to the Operator page with these fields, wired to the same `/certification/run` endpoint the auto path uses:
  * strategy (locked to `flash_loan_arbitrage`)
  * chain (locked to `base`)
  * flash_loan_provider (locked to `balancer_v2`)
  * borrow_token (`WETH`|`USDC`|…), borrow_amount_wei
  * hops[] (min 1: token_in, token_out, fee_tier_bps, amount_in_wei, amount_out_min_wei)
  * signer_wallet_id (dropdown of registered wallets)
  * profit_recipient (default: signer_wallet.address)
  * PRESETS: **"Intentional-revert Tx#1"** (bad hop that must revert) and **"Minimal viable Tx#2"** (tiny WETH→USDC round-trip). One click each.

### 🟡 G5 — Executor Verify page ignores persistent Network config

* **Classification:** Already exists but not wired
* **Symptom:** If the operator saves executor address in Settings › Network → APPLY, the Executor Verify page still shows an empty address field and falls back to `ARBICORE_EXECUTOR_ADDRESS_BASE` env. Not a functional block (they can paste the address into the form), but confusing.
* **Fix (future polish):** auto-populate `address` input from `GET /api/arbicore/settings/network` `executor_addresses.base`.

### 🟡 G6 — Journey stage 2 label is misleading

* **Classification:** Already exists but not wired
* **Symptom:** Stage 2 says "Configure Network (Base RPC)" and fixes to `/v2/settings/network`. But saving there does not activate the RPC (see G1). The status pill toggles READY only when the env var is set.
* **Fix (immediate — documentation):** update the walkthrough manual to state exactly this.
* **Fix (future):** couple with G1 shim.

### 🟡 G7 — Journey polling is passive (~5s)

* **Classification:** Working as designed, but should be documented
* **Symptom:** After completing a step, the operator waits ~5s for the badge to flip.
* **Fix:** document it. (Optionally add a "Refresh now" button.)

### 🟡 G8 — Wallets tab absent from Settings

* **Classification:** Known future item (P2 in handoff)
* **Symptom:** Wallet registration is only on the Operator page. Journey stage 4 fixes there — this works but is slightly inconsistent with the Settings-centric mental model.
* **Fix:** deferred per handoff plan.

### 🟢 G9 — Kill switch not visible on Journey page

* **Classification:** Already exists but only visible on Operator page
* **Symptom:** Operator viewing the Journey doesn't see kill-switch state; it's wrapped inside `wizard_state.steps[key='kill_switch']`. If ENGAGED, the Journey will show BLOCKED but not with the same visual weight as on the Operator page.
* **Fix (future polish):** surface a kill-switch banner at the top of the Journey page too.

---

## Recommendation

Fix **G3** and **G4** now (both are required to run the walkthrough without a shell). Everything else is documentable in the walkthrough manual and can be scheduled for later polish. G1 will be needed before VPS deployment (so the operator can drive the whole thing from the UI without editing `.env`), but for the first LIMITED_LIVE tests on the Preview it is acceptable to document the `.env` workaround.
