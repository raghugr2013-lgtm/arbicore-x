# ArbiCore X · Operator User Manual (Emergent Preview · v1.1.0)

**For:** the operator who is about to execute the first 1–2 controlled LIMITED_LIVE Flash Loan transactions in the current Emergent Preview environment.
**Baseline:** 469 backend tests passing · 11 Settings sub-tabs live · Fernet-wrapped secrets · Ed25519 evidence.
**Scope:** exactly what exists TODAY — nothing speculative.

---

## 1 · Initial Prerequisites

Do these **before opening ArbiCore X**.

### 1.1 Burner wallet

- Create a **fresh** EOA with MetaMask (or `cast wallet new`).
- Treat as disposable — do not reuse a wallet holding significant funds.
- Save the private key privately; you will paste it into `Settings › Secrets` later.

### 1.2 Base mainnet

- Add Base to MetaMask (chain id **8453**, RPC `https://mainnet.base.org`).

### 1.3 ETH for gas

- Bridge or CEX-withdraw **~0.02 ETH on Base** to the burner. Covers 20+ validation transactions.
- Minimum acceptable: 0.005 ETH (wizard flips to WAIT below this).

### 1.4 Contract compile toolchain (choose one)

- **Foundry**: `curl -L https://foundry.paradigm.xyz | bash && foundryup`, OR
- **Remix** (browser only): <https://remix.ethereum.org> — no install.

### 1.5 Optional: Telegram

- If you want alerts, create a bot via `@BotFather` and note the token + chat id.

---

## 2 · Configure Settings — overview of every tab

Left-nav → **SETTINGS**. The sub-tabs, left-to-right:

| Tab | Must configure? | Default acceptable? | Notes |
|---|---|---|---|
| **Account** | no | yes | Display name only; MFA is a placeholder |
| **Network** | **YES** | no | Base RPC + executor address must be set — see §3 |
| **Scanner** | **YES** | no | Enable Flash Loan family — see §4 |
| **Secrets** | **YES** | n/a | Store the burner private key — see §6 |
| **Vault** | no | yes | Legacy stub — not used for LIMITED_LIVE |
| **Execution** | recommended | yes | Position size caps + slippage; defaults are conservative |
| **Exchanges** | no | yes | Not used until CEX scanner activation |
| **Telegram** | optional | yes | Only if you want alerts — see §12.6 |
| **Notifications** | no | yes | Legacy shape; superseded by Telegram tab |
| **Documentation** | no | yes | Static links |
| **Operational** | no | yes | Global feature flags; leave `maintenance_mode=off` |
| **Audit** | no | yes | Read-only change history — check after each Apply |

Every panel exposes the pattern: edit → **VALIDATE** → **SAVE DRAFT** → **APPLY** (with reason) → optional **ROLLBACK** and full **Audit** trail.

---

## 3 · Configure Network

Navigate → **Settings › Network**.

### 3.1 Enable Base chain

- The **BASE** card should already be toggled ON (env-seeded on first boot).
- Ethereum / Arbitrum / Optimism / Polygon: leave OFF for now.

### 3.2 RPC URLs

- **Base RPC URLs** field, comma-separated, primary first:
  - `https://mainnet.base.org` (default, rate-limited)
  - Optional failover: your Alchemy/Infura Base URL

### 3.3 Executor address

- Leave blank until §7 (deploy) is done. Return here after deploying.
- Format: 0x + 40 hex chars.

### 3.4 Gas settings

- **Gas price (gwei)** — leave blank to use estimator, or set `0.05` as a floor.
- **Max fee (gwei)** — optional cap.
- **Prio fee (gwei)** — optional tip.

Recommended for Base beginners: leave all three blank.

### 3.5 Native price (USD)

- Optional. Used only for USD-denominated evidence values. Leave blank for auto.

### 3.6 Apply

1. Click **VALIDATE** — top banner turns green (`✓ VALID`) or shows warnings.
2. Click **APPLY** → prompt "Reason:" → type "initial network config" → OK.
3. **Audit** tab now shows one row: `kind=network, action=apply, actor=operator`.

---

## 4 · Configure Scanner

Navigate → **Settings › Scanner**.

### 4.1 Runtime bar

- Top pill should read **RUNNING**.
- PAUSE / RESUME / RELOAD buttons are for later — leave alone.

### 4.2 Global panel

- **Scanner enabled** — toggle ON.
- **Worker concurrency** — 4 (default) is fine.
- **Max concurrent scans** — 4.
- **Cache (s)** — 30.
- **Expiry (s)** — 300.

### 4.3 Chains grid (inside Global)

- Ensure **base** row is ON with max_gas_gwei = 0.1 and max_latency_ms = 1500.

### 4.4 DEX / market families

Recommended beginner set:
- **uniswap_v3** ON · **balancer_v2** ON · **aerodrome** ON · **curve** ON
- uniswap_v2, sushi, pancake OFF (thin liquidity on Base)

Click **VALIDATE** → **APPLY GLOBAL** → reason "initial scanner globals".

### 4.5 Family selector — Flash Loan

Click the **FLASH_LOAN_ARB** tab.

- **enabled** toggle → **ON** (it ships OFF per canonical D-4.1 safety).
- **interval_s** — 60 is fine for a first run.
- **verifier_concurrency** — 4.

### 4.6 Flash Loan providers

Panel shows three toggles:

| Provider | fee_bps | Recommended |
|---|---|---|
| **balancer_v2** | 0 | **ON** — zero premium, use first |
| aave_v3 | 5 | OFF for first tx (0.05 % premium) |
| uniswap_v3 | 0 (flash swap) | OFF for first tx |

### 4.7 Gate thresholds

Beginner-safe values (already the canonical seed):
- **min_spread_pct**: 0.30 %
- **min_atomic_profit_usd**: 5.00
- **min_confidence**: 55
- **min_pool_tvl_usd_in_route**: 25 000

Click **VALIDATE** → **APPLY FLASH_LOAN_ARB** → reason "enable flash loan family".

---

## 5 · Configure Wallet

**Where:** the Wallet Registration form lives on the **Flash Loan Operator** page (left-nav → **FLASH LOAN**), **not** on a dedicated Settings tab (a Wallets tab is a planned polish item — see §14).

### 5.1 Fill the form

- **wallet_id**: `burner-base-01`
- **address**: paste your burner's 0x…
- **chain**: `base`
- **execution_role**: `gas` — this is the wallet that pays gas AND receives residual profit
- **secret_handle_id**: leave blank for now; you'll come back here after §6.

Click **Register Wallet**. Row appears in the Wallets list.

### 5.2 Roles reference

| Role | Purpose |
|---|---|
| **gas** | Pays gas + signs the tx. First LIMITED_LIVE uses only this |
| treasury | Holds capital; unused for Flash Loan |
| watch_only | Read-only for reporting; unused for first tx |

---

## 6 · Configure Secrets

Navigate → **Settings › Secrets**.

### 6.1 Export the MetaMask private key (safely)

- MetaMask → three dots → Account Details → Show Private Key → enter password.
- Key is 64 hex characters (no `0x` prefix expected by ArbiCore X).
- **Do not paste into any chat, doc, or file.** Only into the ArbiCore X Secrets form.

### 6.2 Store it

Add-secret form:
- **Scope**: `evm_sign`
- **Algorithm**: `eth_privkey`
- **Label**: `burner-base-01`
- **Private key**: paste (64 hex chars)

Click **STORE SECRET**. The response shows:
```
{ handle_id: "sec-…", mask: "abcd…wxyz", provider: "fernet_local" }
```
**Copy the `handle_id`.**

### 6.3 Test the secret

Row appears in the Registered Secrets table. Click **TEST** on the row. Result appears inline:
```
✓ decrypt:true algorithm:eth_privkey hex_length_64:true hex_only:true
```

### 6.4 Rotate (dry-run, optional)

Click **ROTATE** → paste a different 64-hex string → confirm. A new row appears, old row is removed. **For the real run, do NOT rotate yet** — you would have to re-link the wallet.

### 6.5 Link the secret to the wallet

- Return to Flash Loan Operator page → Wallets list → edit `burner-base-01` → paste the `handle_id` from §6.2 into **secret_handle_id** → save.
- Or: register a fresh row from scratch with the handle already populated (delete the old one first).

### 6.6 Verify the link

Open `/v2/wizard`. Step 03 "Secret registration (Fernet)" should be **READY**.

---

## 7 · Deploy FlashLoanReceiver.sol

The contract source, ABI, and full deploy runbook are in `canonical_repo/contracts/`.

### 7.1 Constructor parameters

Both are hard-coded per Base mainnet:
- `_vault  = 0xBA12222222228d8Ba445958a75a0704d566BF2C8` (Balancer V2 Vault)
- `_router = 0x2626664c2603336E57B271c5C0b26F421741e481` (Uniswap V3 SwapRouter02)

### 7.2 Option A · Foundry

```bash
export BASE_RPC_URL=https://mainnet.base.org
export BURNER_KEY=0xYourPrivateKey
forge create \
    --rpc-url $BASE_RPC_URL \
    --private-key $BURNER_KEY \
    canonical_repo/contracts/FlashLoanReceiver.sol:FlashLoanReceiver \
    --constructor-args \
       0xBA12222222228d8Ba445958a75a0704d566BF2C8 \
       0x2626664c2603336E57B271c5C0b26F421741e481
```

### 7.3 Option B · Remix

1. Open <https://remix.ethereum.org>.
2. Paste `canonical_repo/contracts/FlashLoanReceiver.sol` into a new file.
3. Compile with Solidity `0.8.20`.
4. Deploy tab → **Environment: Injected Provider – MetaMask** → confirm Base chain.
5. Constructor args: paste the Vault + Router addresses above.
6. **Transact** → confirm in MetaMask.

### 7.4 Gas estimate

- ~350 000–450 000 gas → **~$0.05–0.15 USD** on Base at typical gwei.

### 7.5 Verify deployment

- BaseScan → paste the deployed address → contract page loads with "Contract Creator" showing your burner.
- Note the deployed address; you paste it in §8.

---

## 8 · Configure and Verify Executor

### 8.1 Configure address

- **Settings › Network** → **Executor address** field on the base card → paste the deployed address → **VALIDATE** → **APPLY** (reason: "wire deployed executor").

### 8.2 Verify

- Left-nav or direct URL: `/v2/executor-verify`.
- Optionally paste address (defaults to the one in Settings › Network).
- Optionally paste your burner as **Expected owner**.
- Click **VERIFY**.

### 8.3 The 6 checks explained

| # | Check | Meaning |
|---|---|---|
| 1 | address_configured | You supplied an address (or the env has one) |
| 2 | rpc_available | Backend can reach Base RPC |
| 3 | contract_deployed | `eth_getCode` returns non-empty bytecode at the address |
| 4 | vault_matches | `VAULT()` on-chain returns the Balancer V2 Vault address |
| 5 | router_matches | `ROUTER()` on-chain returns Uniswap V3 SwapRouter02 |
| 6 | owner_matches | `owner()` returns your burner (INFO-level; only checked if you supplied one) |

### 8.4 Status vocabulary

- **READY** — check passed.
- **WAIT** — infrastructure not answering yet (RPC blip, retry).
- **BLOCKED** — configuration wrong; do not proceed until this is READY.
- **INFO** — advisory only; will never block.

**Do not proceed to first broadcast unless the overall pill shows READY.**

---

## 9 · Wizard Walkthrough

Open `/v2/wizard`. Ten steps:

| # | Step | READY when… | FIX → sends you to |
|---|---|---|---|
| 01 | RPC configuration | `chain_id=8453` reached | Settings › Network |
| 02 | Wallet registration | ≥1 gas wallet on base | Flash Loan Operator (registration form) |
| 03 | Secret registration | Wallet has bound `secret_handle_id` | Settings › Secrets |
| 04 | Gas wallet balance | Burner ≥ 0.005 ETH | Flash Loan Operator (send funds) |
| 05 | FlashLoanReceiver deployment | Address configured + `overall_status=READY` from verifier | Executor Verify page |
| 06 | Executor identity verification | Same as 05 | Executor Verify page |
| 07 | Kill Switch | DISENGAGED (banner on Operator page) | Flash Loan Operator |
| 08 | Certification pass | Advisory INFO — run 11 stages from Operator page manually | Flash Loan Operator |
| 09 | Execution mode | Strategy = LIMITED_LIVE | Flash Loan Operator |
| 10 | Final execution checklist | All above resolved | Flash Loan Operator |

Below the ten steps: the **Flash Loan family prerequisites** card runs 8 tighter family-scoped checks. Every failing row has its own FIX → button. All 8 should read READY before the first broadcast.

Every row has a **DETAIL** button — click for the `why:` reason + `fix_path:` link + raw evidence JSON.

---

## 10 · Waiting for Opportunities

**Reality check:** the automatic Flash Loan scanner engine is **not yet activated** in Preview (planned Phase 10.9). What that means for you today:

- **Automatic discovery**: only produces generic opportunities in `/v2/opportunities` and (for other families) the operator picks one and clicks convert-to-plan.
- **Flash Loan first-tx path**: **manually compose** the plan on the Flash Loan Operator page.

### 10.1 Manual composition (recommended for first tx)

On Flash Loan Operator page → New Plan:

```json
{
  "strategy": "flash_loan_arbitrage",
  "chain": "base",
  "flash_loan_provider": "balancer_v2",
  "borrow_token": "0x4200000000000000000000000000000000000006",   // WETH
  "borrow_amount_wei": 100000000000000000,                        // 0.1 WETH
  "hops": [
    {"token_in": "WETH", "token_out": "USDC",
     "fee_tier_bps": 5, "amount_in_wei": 100000000000000000,
     "amount_out_min_wei": 249500000},
    {"token_in": "USDC", "token_out": "WETH",
     "fee_tier_bps": 30, "amount_in_wei": 0,
     "amount_out_min_wei": 100500000000000000}
  ],
  "profit_recipient": "0xYourBurner"
}
```

`recipient` is left BLANK — the encoder auto-fills it from `network_config.executor_addresses.base`.

### 10.2 Interpreting the plan's readiness

| Field | Meaning | Green when… |
|---|---|---|
| Confidence | ML calibration on the plan features | ≥ 0.55 |
| Expected profit | Gross − gas | ≥ $5 net |
| Gas | Estimated wei × gas price | < 40 % of gross |
| Certification | 11-stage verdict | GO |
| Evidence | Ed25519 pre-broadcast bundle hash | populated |

If any is red, do not click Confirm.

---

## 11 · Execute the First LIMITED_LIVE Flash Loan

### 11.1 Recommended sequence

**Tx #1 · Intentional revert test (cost ~$0.05):**
- Plan with `recipient = your_burner_address` (NOT the executor).
- Very small: `borrow_amount_wei = 10**15` (0.001 WETH).
- The Vault will call `receiveFlashLoan` on the burner (an EOA), which reverts.
- **Point:** exercise the full off-chain gate ladder + sign + broadcast + tx-hash + evidence pipeline **without** relying on the executor.

**Tx #2 · First value-producing (cost = gas only):**
- Plan per §10.1 above, `recipient` blank (auto-fills executor).
- Small amount: 0.1 WETH.
- Verify hop-2 `amount_out_min_wei` gives you at least +0.001 WETH profit after slippage.

### 11.2 Pre-Execute safety checklist

- [ ] Wizard all-READY, FL prereqs card all-READY.
- [ ] Kill switch banner: **DISENGAGED**.
- [ ] Strategy mode: **LIMITED_LIVE**.
- [ ] Certifier last run: **GO** (11/11 stages PASS).
- [ ] Preflight in the plan: `preflight_ok=true`.
- [ ] Gas price: sane (< 1 gwei on Base).
- [ ] Nonce: matches burner's current on-chain nonce.
- [ ] `profit_recipient`: your burner (never the executor — the executor sweeps to `profit_recipient`).

### 11.3 Expected flow

1. Click **Prepare broadcast** → response shows `preflight_ok, gas_price_wei, gas_limit, nonce`.
2. Toggle **operator confirm** → true.
3. Click **Broadcast** → 6 gates fire in order: kill_switch → mode → capital → secret → preflight → operator_confirm.
4. Response returns `tx_hash`. Note it.
5. Watch BaseScan for the tx to land (usually < 5 s on Base).

---

## 12 · Post-Trade Review

### 12.1 Post-Trade Dashboard

- `/v2/post-trade` — the latest broadcast attempts.
- Fields shown: `tx_hash` (linked to BaseScan), `chain`, `borrow_token`, `borrow_amount`, `recipient`, `profit_recipient`, `gas_used`, `gas_price_wei`, `nonce`, `evidence_ref`, `attempted_at`.

### 12.2 Evidence bundles

- Right-hand tile on Post-Trade → last 5 bundle hashes.
- Full verify: `POST /api/arbicore/intelligence/evidence/verify` with `bundle_hash`.

### 12.3 Calibration

- Middle tile → last 5 calibration ticks (worker runs every 3600 s).

### 12.4 Adaptive Weights

- Right tile → last 5 recommendations.

### 12.5 Learning updates

- Aggregated on the Intelligence page (`/v2/intelligence`) — verdict distribution, roll-up over recent broadcasts.

### 12.6 Telegram notifications

- Settings › Telegram → add bot token + chat_id → **SAVE** → **SEND TEST**.
- The alert log at the bottom of the same page shows every send attempt.
- Rules matrix has 18 events including `first_broadcast`, `broadcast_sent`, `capital_denied`, `kill_switch_engaged`.

---

## 13 · Troubleshooting

### Wizard step: RPC · BLOCKED
Cause: RPC unreachable or wrong chain. Fix: Settings › Network → change RPC URL → APPLY.

### Wizard step: Wallet · BLOCKED
Cause: no wallet registered for `chain=base, role=gas`. Fix: Flash Loan Operator → register form.

### Wizard step: Secret · BLOCKED
Cause: wallet doc has no `secret_handle_id`. Fix: Settings › Secrets (create) → re-register wallet with the handle.

### Wizard step: Gas balance · WAIT
Burner has < 0.005 ETH. Fund it with more ETH on Base.

### Executor verification: vault_matches BLOCKED
Cause: wrong address or wrong chain. Verify BaseScan shows the contract on Base (chain id 8453) and the constructor args match §7.1 exactly.

### Executor verification: contract_deployed BLOCKED
Cause: address you configured has no bytecode. Either wrong address or deploy failed. Redeploy per §7.

### Broadcast: `preflight_failed`
On-chain `eth_call` reverts. Common: hop's `amount_out_min_wei` is too tight (increase slippage tolerance), or the route has no liquidity (change fee_tier_bps).

### Broadcast: `capital_denied`
Plan exceeds Settings › Execution `max_position_usd`. Either reduce `borrow_amount_wei` or raise the cap (with reason).

### Broadcast: `kill_switch_denied`
Kill switch is engaged. Fix from the banner on Flash Loan Operator page.

### Broadcast: `secret_denied`
Wallet's `secret_handle_id` can't be resolved. Verify Settings › Secrets shows the handle; if not, re-add.

### Transaction reverts on-chain (`RepayFailed`)
Executor received the loan but hop output was insufficient to repay Vault + fee. This is a routing / slippage problem. Rerun the plan with a larger `amount_out_min_wei` margin, or a different route (change fee_tier_bps).

### Low gas / stuck tx
Bump gas via Settings › Network `gas_price_gwei`, APPLY, resubmit with a higher nonce.

### Scanner not finding opportunities
Expected in Preview today — auto-discovery of Flash Loan opportunities is not yet activated. Use manual plan composition (§10.1).

---

## 14 · Best Practices

1. **Keep the burner ≤ 0.05 ETH.** If compromised, exposure is capped.
2. **Never reuse a burner across chains.**
3. **Rotate the secret every ~30 days.** Settings › Secrets → ROTATE (remember to re-link the wallet).
4. **Kill switch drill weekly.** Engage from the banner, watch a broadcast get denied at gate 1, disengage. Costs nothing.
5. **Save-Draft before Apply on every Settings change.** Draft is your undo before the audit row is written.
6. **Always fill "reason" on Apply.** The Audit tab is your future best friend.
7. **Preview is for validation; VPS is for scale.** Move to a VPS after:
   - 5+ successful LIMITED_LIVE tx recorded in Post-Trade
   - Calibration + adaptive weights have at least one full 24 h cycle of samples
   - Telegram alerting confirmed working end-to-end
8. **Test → Rotate → Value.** First tx should be an intentional revert (§11.1 Tx#1), second the smallest value-producing (0.1 WETH), third onwards scale gradually.
9. **Never hand-edit `.env` while the backend is running** — Settings › Network is the correct path for anything RPC/executor/gas.
10. **Watch the Audit tab after every Apply.** If you don't see a fresh row, the change didn't persist.

---

## Appendix · Files and links used above

- Solidity contract: `canonical_repo/contracts/FlashLoanReceiver.sol`
- Deploy runbook: `canonical_repo/contracts/DEPLOY.md`
- ABI: `canonical_repo/contracts/FlashLoanReceiver.abi.json`
- Full checklist: `docs/ui_v2/33_PHASE10_5_6_SECRETS_AND_READINESS_REPORT.md` §E
- Production audit: `docs/ui_v2/29_FLASH_LOAN_PRODUCTION_READINESS_AUDIT.md`

Base mainnet constants:
- Balancer V2 Vault: `0xBA12222222228d8Ba445958a75a0704d566BF2C8`
- Uniswap V3 SwapRouter02: `0x2626664c2603336E57B271c5C0b26F421741e481`
- WETH: `0x4200000000000000000000000000000000000006`
- USDC: `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`

You are ready to configure and execute. Good luck with the first transaction.
