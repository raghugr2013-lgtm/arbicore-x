# ArbiCore X — Operator Walkthrough Manual v1.0

**Audience:** First-time operator taking a brand-new ArbiCore X install from zero to a successful LIMITED_LIVE Flash Loan transaction on Base mainnet.
**Scope:** Complete UI-first workflow. Only two tasks require touching the host: (i) *(none — Phase 10.10 closed the last .env requirement)*, (ii) deploying the FlashLoanReceiver contract off-platform (one command via Foundry or a browser click in Remix).
**Validated against:** Preview build 2026-08-01, backend 460/460 relevant tests green (Phase 10.10 shim + G2/G3/G4 fixes applied).
**Base URL used in examples:** `https://p0-3-certification.preview.emergentagent.com`

---

## Legend

| Symbol | Meaning |
|---|---|
| 🟢 READY | Step is complete; Journey badge is green |
| 🟡 WAIT | Step is in progress or waiting on evidence |
| 🔴 BLOCKED | Something required is missing; won't proceed |
| ⚙️ Action | You must click / type / paste |
| 🧭 Verify | How to confirm the step succeeded |
| ⚠️ Common mistake | Documented pitfalls |

**Journey polling.** The Journey page (`/v2/journey`) auto-refreshes every ~5 seconds. After completing a step, wait 5 seconds — or navigate away and back — for the badge to flip.

---

## Prerequisites

- A **burner Ethereum wallet** on Base mainnet (private key you control).
- Small amount of **ETH on Base** (~0.02 ETH covers deploy + several test transactions).
- Optional: **Telegram bot token** and chat_id if you want alerts.
- SSH access to the host running the backend (only for env edits).

---

## Step 0 — Verify Preview is running

**Where:** browser
**Action:** Open the base URL. You should see the ArbiCore header, left icon rail (HOME → DISCOVERY → OPPORTUNITIES → PORTFOLIO → INTELLIGENCE → OPERATIONS → SETTINGS → FLASH LOAN → JOURNEY).
**Verify:** Click JOURNEY (last icon in the left rail). You should land on `/v2/journey` and see **14 stages**. Stage 1 "Configure Settings" should be READY. Stage 2 "Configure Network (Base RPC)" is likely 🔴 BLOCKED — that is the next action.

⚠️ **Common mistake:** if the page is blank, check backend/frontend supervisor status: `sudo supervisorctl status`. Both must be RUNNING.

🟢 **Journey change:** Stage 1 = READY. Move to Step 1.

---

## Step 1 — Configure Base RPC (fully UI-driven, Phase 10.10)

**Where:** `/v2/settings/network`

As of Phase 10.10 (backend commit dated 2026-08-01), the persistent Network config drives the runtime env: **APPLY hot-loads your RPC URL into every subsequent broadcast / gas / wallet-balance / RPC-health / executor-verify call — no backend restart, no `.env` edit.** The only variables still living in `backend/.env` are the bootstrap ones (`MONGO_URL`, `DB_NAME`, `VAULT_KEY`, `CORS_ORIGINS`).

> ### 🚨 REQUIRED: use a private RPC endpoint
>
> The Preview environment's egress IP is **rate-limited / blocked** by the public Base RPC (`mainnet.base.org` returns `HTTP 403`). Every operator MUST provision a **private RPC endpoint** before proceeding. All three of these have free tiers that are more than sufficient:
>
> | Provider | Free tier | Endpoint pattern |
> |---|---|---|
> | Alchemy | 300M compute-units / month | `https://base-mainnet.g.alchemy.com/v2/<key>` |
> | QuickNode | 10M requests / month | `https://<name>.base-mainnet.quiknode.pro/<key>/` |
> | Ankr | Public + upgradable | `https://rpc.ankr.com/base/<key>` |
>
> Sign up, create a Base mainnet endpoint, copy the full URL, and paste it below.

**Fields:**

| Field | Enter | Notes |
|---|---|---|
| `base` — toggle | **ON** | required |
| `base` — RPC URLs | your private endpoint URL (see callout above) | primary first; you can add fallbacks comma-separated |
| `base` — Executor address | *(leave blank until Step 6)* | |
| `base` — MEV relay URL | *(optional)* | leave blank for the first tx |
| `base` — Gas price (gwei) | *(optional)* | leave blank; oracle will estimate |
| `base` — Native price (USD) | *(optional)* | leave blank |
| Other chains | toggle OFF | keeps the surface minimal |

⚙️ **Action:** click **VALIDATE** → expect `✓ VALID`. Then **APPLY**, provide a reason (e.g. `initial Base setup`).

🧭 **Verify:**
- The APPLY response contains `env_synced: ["ARBICORE_RPC_URL", "ARBICORE_RPC_URL_BASE"]` — the runtime just picked up your new URL.
- Run: `GET /api/arbicore/rpc/check` (or wait 5s for Journey to refresh). Expected: `"status": "READY"`, `"chain_id": 8453`, `"is_base_mainnet": true`.
- Settings › Audit tab shows a new entry with kind=`network`.

⚠️ **Common mistakes:**
- Using the public `mainnet.base.org` endpoint — returns HTTP 403 from the Preview egress. Always use a private endpoint (see callout above).
- Forgetting to click APPLY after VALIDATE — the URL stays as a draft and env is not synced.

🟢 **Journey change (wait 5s):** Stage 2 flips from BLOCKED → READY.

---

## Step 2 — Configure Scanner (enable Flash Loan family)

**Where:** `/v2/settings/scanner` (or Journey → stage 3 → OPEN →)

The Scanner has two layers: **Global** (cross-family) and **per-family**. For the first LIMITED_LIVE tx we set minimal values and enable only what's needed. Auto-discovery for Flash Loan is deferred (see step 10 rationale).

### 2a — Global tab

⚙️ **Actions (top card):**
- **Scanner enabled** toggle → **ON**
- **Worker concurrency** → `4` (default is fine)
- **Chains** → toggle `base` **ON**; leave others OFF
- **DEX / market families** → toggle `uniswap_v3` **ON**; `balancer_v2` **ON**; others optional
- **Token / pair families** → `stables`: add `USDC`, `USDbC`. `eth_pairs`: add `WETH`. (These populate the scanner watchlist; not required for a manual plan.)
- Leave "Cache (s)" = 30, "Expiry (s)" = 60 default

Click **VALIDATE** → expect `✓ VALID`. Then **APPLY GLOBAL**, provide reason.

### 2b — Family selector card

⚙️ **Actions:**
- Click **FLASH_LOAN_ARB** tab (should be default-selected)
- Toggle `flash_loan_arb enabled` → **ON**
- **Flash Loan providers** panel → toggle `balancer_v2` → **ON** (this is the provider used by the FlashLoanReceiver contract; fee = 0 bps)
- interval_s: `30`, verifier_concurrency: `2` (defaults)

Click **VALIDATE**, then **APPLY FLASH_LOAN_ARB**, provide reason.

🧭 **Verify:** the runtime pill turns green (RUNNING). The `flash_loan_arb` tab shows a filled dot ●.

⚠️ **Common mistake:** forgetting to APPLY after VALIDATE. Symptom: badge stays yellow (draft only). The Audit tab won't show an "apply" entry.

🟢 **Journey change:** Stages 3 and 10 (Scanner + Flash Loan family enabled) go READY.

---

## Step 3 — Store the burner private key (Secret)

**Where:** `/v2/settings/secrets` (or Journey → stage 5 → OPEN → or Flash Loan Operator → "Open Settings › Secrets →")

⚠️ **Critical:** the secret is stored **write-only**. It is encrypted-at-rest with Fernet (AES-128-CBC + HMAC-SHA256) using the `VAULT_KEY` in `backend/.env`. Plaintext never leaves the request and never appears in any response. **You cannot recover it** — if you lose the key, register a fresh burner.

### Add a new secret

**Card:** "Add a new secret"

| Field | Enter | Notes |
|---|---|---|
| **Scope** | `evm_sign` | selects the "sign EVM transactions" scope |
| **Algorithm** | `eth_privkey` | applies 64-hex validation |
| **Label** | `base-burner-01` | any human tag for your records |
| **Private key (64 hex chars)** | `<paste your 64-hex burner private key WITHOUT 0x prefix>` | e.g. `abc123…def` |

⚠️ **Common mistakes:**
- Pasting `0x…` prefix — the UI accepts it but backend expects canonical (no 0x); the algorithm validator strips it, so it works either way, but keep it clean.
- Wrong scope (e.g. `custom`) — the wallet won't accept it. Must be `evm_sign`.
- Wrong algorithm (e.g. `generic_bytes`) — signing will fail later.

⚙️ **Action:** click **STORE SECRET**.

🧭 **Verify:** the "Registered secrets" table shows a new row with the label and a mask like `abc1…def0`. **Copy the `handle_id`** (long UUID-like string in the first column) — you'll paste it into the wallet form in Step 4.

🟢 **Journey change:** Stage 5 (Store Secret) → READY.

---

## Step 4 — Register the burner wallet AND link the secret in a single form

**Where:** `/v2/flash-loan-operator` → Card **"1 · Wallets"**

You will register the wallet with the `secret_handle_id` **already populated** — the wallet + secret are bound at registration. There is no separate "link" step.

| Field | Enter | Notes |
|---|---|---|
| **Wallet label** | `Base Gas Wallet #1` (any name) | used for display; backend also uses it as label |
| **Chain** | `base` | dropdown |
| **Role** | `gas` | must be `gas` to allow signing; `watch_only` cannot broadcast |
| **Address (0x…)** | `<burner wallet address, checksum-cased>` | e.g. `0xAbC…123` (42 chars) |
| **Secret handle id** | `<handle_id from Step 3, e.g. sec-abc123…>` | paste the full `handle_id` from the "Registered secrets" row — NOT the label |

⚙️ **Action:** click **REGISTER WALLET**.

🧭 **Verify:** a toast shows `Wallet registered — <auto-generated-id>`. The right-side "Registered wallets" panel now includes your wallet with the `gas` chip and `base` chip. Clicking on it highlights it (selects for step 3 health check). Card 3 → **REFRESH** should show `secret_bound: READY`.

⚠️ **Common mistakes:**
- Address without leading `0x` — backend rejects with `invalid address`.
- Wrong role (e.g. `watch_only`) — you'll be unable to sign transactions.
- Copying the **label** (e.g. `base-burner-01`) instead of the actual `handle_id` (long UUID-like string). The wallet form silently accepts either, but the executor will fail to resolve the wrong handle at broadcast time.

🟢 **Journey change:** Stages 4 (Register Wallet), 6 (Link Secret to Wallet) → READY.

---

## Step 5 — *(consolidated into Step 4 above)*

> The previous separate "Link the secret to the wallet" step is no longer needed — Phase 10.10.1 established that wallet registration accepts `secret_handle_id` directly, so the wallet and its secret binding are created in a single form. Continue to Step 6.

---

## Step 6 — Deploy FlashLoanReceiver.sol on Base

**Where:** off-platform (Foundry or Remix). Fully documented at `/app/canonical_repo/contracts/DEPLOY.md`.

**Contract:** `canonical_repo/contracts/FlashLoanReceiver.sol` (~200 LOC, owner-only, no delegatecall, no selfdestruct).
**Constructor args:**
- `_vault = 0xBA12222222228d8Ba445958a75a0704d566BF2C8` (Balancer V2 Vault, Base)
- `_router = 0x2626664c2603336E57B271c5C0b26F421741e481` (Uniswap V3 SwapRouter02, Base)

**Recommended path — Foundry** (from the DEPLOY.md):

```bash
curl -L https://foundry.paradigm.xyz | bash && foundryup
export BASE_RPC_URL=https://mainnet.base.org
export BURNER_KEY=<64 hex private key WITHOUT 0x>
forge create \
    --rpc-url $BASE_RPC_URL \
    --private-key $BURNER_KEY \
    /app/canonical_repo/contracts/FlashLoanReceiver.sol:FlashLoanReceiver \
    --constructor-args \
      0xBA12222222228d8Ba445958a75a0704d566BF2C8 \
      0x2626664c2603336E57B271c5C0b26F421741e481
```

Expected gas cost: **~$0.10** on Base. Note the deployed address — call it `EXECUTOR_ADDR`.

🧭 **Verify (BaseScan):** open `https://basescan.org/address/<EXECUTOR_ADDR>` — you should see the contract creation transaction and 2 read-only functions `VAULT()` and `ROUTER()` returning the addresses above.

⚠️ **Common mistakes:**
- Deploying with the wrong constructor argument order — the contract silently misbehaves at broadcast time (VAULT() returns the router address, verification fails).
- Deploying from a wallet other than your burner — this is fine, but the FlashLoanReceiver's `owner()` will be that other address. The Executor Verify page tolerates this (owner check is INFO, not BLOCKED), but the future `sweep()` escape hatch must be called from the owner.

---

## Step 7 — Wire `EXECUTOR_ADDR` into ArbiCore X (fully UI-driven, Phase 10.10)

**Where:** `/v2/settings/network`

⚙️ **Action:**
1. In the `base` chain block, paste `EXECUTOR_ADDR` (from Step 6) into **Executor address**.
2. Click **VALIDATE** → expect `✓ VALID`.
3. Click **APPLY**, provide a reason (e.g. `initial FlashLoanReceiver deploy`).

🧭 **Verify:**
- The APPLY response contains `env_synced: ["ARBICORE_EXECUTOR_ADDRESS_BASE", ...]` — the runtime just picked up your new address.
- Settings › Audit shows a new `network` entry noting the executor change.
- Executor Verify page (next step) is now ready to run.

No backend restart. No `.env` edit. The persistent config drives the runtime.

---

## Step 8 — Verify the Executor contract

**Where:** `/v2/executor-verify` (or Journey → stage 9 → OPEN →)

The page runs 6 read-only RPC checks against your deployed contract:

1. Address configured ✔
2. RPC available (Base) ✔
3. Contract deployed (bytecode present) ✔
4. `VAULT()` returns `0xBA12…C8` (Balancer V2 Vault) ✔
5. `ROUTER()` returns `0x2626…81` (Uniswap V3 SwapRouter02) ✔
6. `owner()` returns expected (optional) — INFO only

⚙️ **Action:**
- Leave "Executor address" blank to use the env var, OR paste `EXECUTOR_ADDR` directly.
- Optionally paste your burner wallet address into "Expected owner" for check #6.
- Click **VERIFY**.

🧭 **Verify:** every row shows a green READY pill. The header shows an overall **READY** pill and `Ready: YES`.

⚠️ **Common mistakes:**
- Constructor args in wrong order → VAULT()/ROUTER() checks BLOCKED. Redeploy.
- Backend not restarted after `.env` change → checks show WAIT with "RPC error" — restart backend.

🟢 **Journey change:** Stage 7 (Deploy) and Stage 8 (Configure Executor) and Stage 9 (Verify Executor) → READY.

---

## Step 9 — Fund the burner + check gas balance

**Where:** external wallet → burner address, then `/v2/flash-loan-operator` Card **"3 · Wallet Status"**

⚙️ **Action (external):** send ~0.02 ETH (native, on Base) to your burner wallet.

⚙️ **Action (UI):**
1. Click your wallet in Card 1's right panel to select it.
2. Click **REFRESH** in Card 3.

🧭 **Verify:** "Gas balance" shows something like `0.020000 ETH` in green. Health checks show `gas_balance: READY`, `secret_bound: READY`, `overall: READY`.

⚠️ **Common mistake:** sending USDC or WETH instead of native ETH — gas requires native ETH.

🟢 **Journey change:** the internal `gas_balance` wizard step flips READY (surfaces via prereqs banner).

---

## Step 10 — Promote strategy to LIMITED_LIVE

**Where:** `/v2/flash-loan-operator` → Card **"4 · Execution Mode Ladder"**

Find the row `flash_loan_arbitrage`. It probably shows mode = `SHADOW` or `PAPER`.

⚙️ **Action:** click **LIMITED_LIVE** on that row. Confirm the dialog. Provide the reason field a note like `first-tx-audit`.

🧭 **Verify:** the row now shows `LIMITED_LIVE` in place of the previous mode.

⚠️ **Common mistake:** promoting the wrong strategy (there are several — `cex_arbitrage`, `flash_loan_arbitrage`, etc.). Make sure you're on the `flash_loan_arbitrage` row.

🟢 **Journey change:** internal `mode` wizard step → READY.

---

## Step 11 — Compose Tx #1 (Intentional Revert)

**Purpose:** exercise the entire pipeline (planning → certification → all 6 gates → RPC broadcast → on-chain execution → evidence → learning) without producing profit and without risking principal. The Balancer V2 flash loan is atomic — if the swap reverts, the loan is unwound in the same transaction; you lose only gas.

**Where:** `/v2/flash-loan-operator` → Card **"5B · Manual Plan Composer"**

⚙️ **Action:**
1. In Card 1, click your wallet to select it.
2. In Card 5B, click **🅐 LOAD TX#1 · INTENTIONAL REVERT**.

The form auto-populates:
- Chain: `base`
- Provider: `balancer_v2`
- Strategy: `flash_loan_arbitrage`
- Borrow token: `0x4200…0006` (WETH)
- Borrow amount: `10000000000000000` wei (0.01 WETH ≈ $25)
- Hop 1: WETH → USDC via uniswap_v3 fee 5 bps, min_out `24500000` (≈$24.50)
- Hop 2: USDC → WETH via uniswap_v3 fee 5 bps, min_out **`999999999999999999999`** — the impossible min-out that will revert the second swap

3. (Optional) Toggle **Show raw JSON** to inspect the composed plan.
4. Click **RUN FULL CERTIFICATION (MANUAL PLAN)**.

> ⚙️ **What the button actually does (Phase 10.10.1 build-then-certify):**
> 1. First calls `POST /api/arbicore/execution/plans/build` — **persists** the plan into Mongo and returns a `plan_id`.
> 2. Then calls `POST /api/arbicore/execution/certification/run` — runs the 11-stage certifier and returns the verdict for display.
> 3. Merges the persisted `plan_id` from step 1 into the certification report so the broadcast buttons pick up the right (persisted) plan.

🧭 **Verify (certification report — Card 6):**
- Toast: `Plan plan-…14chars… · verdict: PASS` (or `WAIT`, both acceptable — the certifier does not simulate the on-chain revert)
- `plan_id` shown in the report
- All 11 stages listed with statuses; simulation should show PASS or WAIT

If verdict is `HARD_NO`, the plan is inconsistent — reload the preset and try again.

If the toast shows `Build failed: …` → the persisted plan step failed. Common causes: strategy not in an accepted mode (must be OBSERVE/PAPER/SHADOW/LIMITED_LIVE — Phase 10.10.1 lifts LIMITED_LIVE from the block-list), wallet not selected, or a bad payload field. The certification step won't run without a persisted plan.

### Broadcast

⚙️ **Action (Card 6):**
1. Optional: click **PREVIEW BROADCAST (DRY)** first — the preflight will succeed *at gate 5* (because certifier passed) but the actual on-chain `eth_call` simulation will predict the revert. This is expected.
2. Tick the **"I understand this will submit a real transaction"** checkbox.
3. Click **BROADCAST LIMITED_LIVE**.
4. Confirm the "This will submit a REAL transaction..." dialog.

🧭 **Verify:**
- Toast: `Broadcast sent — tx 0x…` **OR** `Broadcast held — <reason>`.
- **broadcast receipt** panel appears at the bottom of Card 6 with `SENT` chip, `tx 0x…`, `signer 0x…`, and the gate ladder each showing `PASS` or `SENT`.
- Click the tx_hash — BaseScan opens; you should see the transaction landed and **reverted** (red status), with the flash loan atomically unwound. Gas is spent (~$0.02).

⚠️ **Common mistakes:**
- Kill switch engaged — gate 1 refuses. Disengage on the top banner.
- Mode still SHADOW — gate 2 refuses. Go back to Step 10.
- Burner has 0 ETH — gate 4 refuses. Fund it.

🟢 **Journey change:** Stage 12 (Intentional Revert test) → READY (auto-detected from the receipt's `broadcast_sent=true` + `preflight_ok=true` combo).

---

## Step 12 — Review Tx #1 receipt + Evidence

**Where:** `/v2/post-trade`

- **Latest broadcast attempts** — you should see your Tx #1 receipt at top with mode=`LIMITED_LIVE`, `broadcast_sent`, `preflight_ok`, `tx_hash` (clickable to BaseScan), gas used, nonce, `evidence_ref`.
- **Calibration** widget — new entry from this tx.
- **Adaptive Weights** widget — new recommendation.
- **Evidence Bundles** widget — new bundle hash.

🧭 **Verify:**
- All 4 widgets refreshed (they poll every 8s).
- Click the tx_hash link — BaseScan shows transaction landed, reverted, flash loan atomically unwound.
- If Telegram is configured, you should have received a `limited_live_broadcast` alert.

⚠️ **Common mistake:** Post-Trade shows empty. This means the plan hit `data.error` before broadcasting. Check the certification stage list in Card 6 on the Operator page for the specific failure.

---

## Step 13 — Compose and execute Tx #2 (Minimal Viable)

Same procedure as Step 11 but click **🅑 LOAD TX#2 · MINIMAL VIABLE** instead.

Preset values:
- Same amounts: 0.01 WETH borrowed
- Hop 2 min_out: `10005000000000000` — realistic (0.010005 WETH). This tx will succeed if the Uniswap V3 WETH/USDC 5-bps pool has a small favourable arbitrage at execution time. If not, the router will still revert on the min_out — that's fine; it means the market is not currently arb'able for you, not that the pipeline is broken.

⚙️ **Action:** Load preset → Certify → confirm → Broadcast.

🧭 **Verify (best case — pool has arb):**
- Broadcast receipt shows `SENT`.
- BaseScan shows the tx **succeeded** with 4 events: Balancer flashLoan, uniswap swap, uniswap swap, Balancer repayment.
- Post-Trade dashboard shows tx_hash, gas used, and any residual profit swept to your wallet.

🧭 **Verify (no-arb case — router reverts):**
- Same as Tx #1: broadcast_sent=true but on-chain reverted. This is a valid outcome — the pipeline worked, the market simply didn't offer profit.

⚠️ **Common mistake:** expecting Tx#2 to always print profit. On a random Base block, the WETH/USDC 5-bps pool is arb-tight; expect several reverts before a profitable landing. If you want guaranteed profit, wait for periods of higher volatility (e.g. after a Fed announcement).

🟢 **Journey change:** Stage 13 (First LIMITED_LIVE Flash Loan) → READY as soon as any `broadcast_sent=true` receipt exists — this includes reverted tx (they still counted as broadcasts).

---

## Step 14 — Final review + mark VPS-ready

**Where:** `/v2/journey`

🧭 **Verify:** Stages 1 through 13 are all READY or INFO. The progress bar shows ≥ 93% (13/14). A large **"MARK VPS-READY"** button appears at the bottom of the page.

⚙️ **Action:**
1. Cross-check the Post-Trade dashboard once more — make sure the evidence bundle exists and the calibration + adaptive-weights ticks fired.
2. If Telegram is configured, confirm you received the broadcast alert.
3. Click **MARK VPS-READY**.
4. Enter a reason (e.g. `first LIMITED_LIVE validated — Tx#1 reverted as designed, Tx#2 executed on 2026-08-…, evidence bundle abc…`).

🧭 **Verify:** Stage 14 flips READY. The banner "✓ Journey Complete" appears. Settings › Operational shows `feature_flags.vps_ready = true`.

You are now ready to freeze the build and provision the Contabo VPS.

---

## Appendix A — Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Journey stage 2 stays BLOCKED | RPC URL not applied via UI OR RPC endpoint unreachable | Settings › Network → paste RPC → VALIDATE → APPLY. Check `GET /api/arbicore/rpc/check` |
| Executor Verify shows RPC error | Same as above | Same |
| VAULT()/ROUTER() BLOCKED | Constructor args swapped at deploy | Redeploy with vault first, router second |
| Wallet registration shows no toast | *(Fixed in this build — G3)* — if it recurs, check browser console | |
| Secret registration errors "scope must be one of…" | Using the wrong page — go to `/v2/settings/secrets`, not the (now redirect-only) card on the Operator page | |
| Manual plan certification `HARD_NO` | Missing `signer_wallet_id` or bad hop shape | Reload preset; ensure a wallet is selected in Card 1 |
| Toast shows "Build failed: strategy is in mode 'FULL_LIVE'…" | strategy is in an unsupported mode | Card 4 → set to LIMITED_LIVE (or SHADOW) |
| Toast shows "Build failed: …" and certification does not run | `/plans/build` rejected the payload | Check the toast detail; usually a missing/invalid field. Certification never runs when build fails. |
| Broadcast held at `gate_kill_switch` | Kill switch engaged | Top banner → Disengage |
| Broadcast held at `gate_mode` | Strategy still SHADOW | Card 4 → promote to LIMITED_LIVE |
| Broadcast held at `gate_gas_balance` | Burner has 0 ETH | Fund burner |
| Broadcast held at `gate_signer_secret` | Wrong `handle_id` on wallet | Re-register wallet with the correct handle |
| Broadcast held at `gate_preflight` | Contract simulation reverted | Check BaseScan for revert reason; adjust hop min_outs |
| tx landed but reverted | Market did not offer arb, OR intentional revert preset used | Expected for Tx#1; retry Tx#2 later |

---

## Appendix B — What each Journey stage actually checks

| # | Stage | Signal | Fix path |
|---|---|---|---|
| 1 | Configure Settings | Static READY (settings shell) | — |
| 2 | Configure Network (Base RPC) | wizard.rpc → RPC returns chain_id 8453 | `/v2/settings/network` |
| 3 | Configure Scanner | scanner_config global enabled | `/v2/settings/scanner` |
| 4 | Register Wallet | wizard.wallet → ≥ 1 gas wallet on base | `/v2/flash-loan-operator` Card 1 |
| 5 | Store Secret | wizard.secret → ≥ 1 secret in registry | `/v2/settings/secrets` |
| 6 | Link Secret to Wallet | wallet.secret_handle_id set AND matches an existing handle | `/v2/flash-loan-operator` Card 1 (registered together in Step 4) |
| 7 | Deploy FlashLoanReceiver | wizard.executor → bytecode + VAULT + ROUTER checks | off-platform Foundry/Remix |
| 8 | Configure Executor Address | executor_addresses.base set (via Settings › Network) | `/v2/settings/network` |
| 9 | Verify Executor | wizard.executor_verify all 5 checks READY | `/v2/executor-verify` |
| 10 | Enable Flash Loan Scanner Family | scanner_config.families.flash_loan_arb.enabled = true | `/v2/settings/scanner` |
| 11 | Manual plan OR await opportunity | INFO — auto-discovery deferred | `/v2/flash-loan-operator` Card 5B |
| 12 | Intentional revert test | Any receipt where broadcast_sent=true AND preflight predicts revert (or on-chain reverted) | `/v2/flash-loan-operator` Card 6 |
| 13 | First LIMITED_LIVE Flash Loan | Any receipt where mode=LIMITED_LIVE AND broadcast_sent=true | Same |
| 14 | Review + Mark VPS-Ready | operational_flags.feature_flags.vps_ready = true | Journey page's own "MARK VPS-READY" button |

---

## Appendix C — Known limitations of this build (v1.0)

Do not confuse these with bugs; they are documented and scheduled.

1. ~~**RPC + executor address are env-driven**~~ **CLOSED in Phase 10.10.**
2. ~~**Certification does not persist plans**~~ **CLOSED in Phase 10.10.1** — the composer now calls `/plans/build` first (persists), then `/certification/run` for the verdict.
3. ~~**Wave 6B guard blocks LIMITED_LIVE plans**~~ **CLOSED in Phase 10.10.1** — `/plans/build` now accepts OBSERVE/PAPER/SHADOW/LIMITED_LIVE. FULL_LIVE remains blocked pending a future review; the broadcast pipeline enforces the LIMITED_LIVE/FULL_LIVE gate at Gate 2 independently.
4. **Auto-discovery for Flash Loan is deferred to Phase 10.9.** Intentional — the first 1–2 LIMITED_LIVE tx must be operator-composed for safety.
5. **No dedicated Wallets tab in Settings.** Wallet registration lives on the Flash Loan Operator page; scheduled as P2 polish.
6. **Executor Verify page does not auto-populate from persistent Network config.** Paste the address manually or leave blank to use the env var (which is now sourced from persistent config anyway).
7. **Journey polling is 5 seconds.** Not real-time — expect a small delay before badges flip.
8. **No wallet DELETE endpoint yet.** If you need to change a wallet's `secret_handle_id`, register a new wallet with a different `wallet_id`. The old row remains in the registry until a future cleanup patch.

---

**Manual version:** 1.0
**Author:** ArbiCore Operator Experience Audit
**Feedback loop:** file findings under `/app/docs/OPERATOR_EXPERIENCE_AUDIT_v1.md`
