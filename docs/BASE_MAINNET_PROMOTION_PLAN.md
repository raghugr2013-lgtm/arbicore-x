# Base Mainnet Promotion Plan — LIMITED_LIVE Production Runbook

**Status:** PLAN ONLY. Nothing in this document has been executed. No mainnet
executor deployed, no burner wallet generated, no key requested, no broadcast.
**Scope:** Promote the Phase-A-validated flash-loan engine from Base Sepolia
(engineering proof) to Base **mainnet** (chain id `8453`) LIMITED_LIVE at the
smallest practical notional, on the operator-owned VPS (`git pull + docker
compose`).
**Feature freeze:** Flash-loan feature set is FROZEN. This runbook contains
operational commands and gates only — no new functionality.

> `$API` below = the VPS backend base URL, e.g. `https://<vps-host>/api`.
> `$BACKEND` = the same host **without** the `/api` suffix.
> Every command that mutates state runs against an authenticated cookie jar
> (`-b cj.txt`) — see step 0.

---

## ⛔ STOP GATES — read first

This runbook has **four hard STOP gates**. At each one, work halts until the
operator explicitly approves the *next* gate. No step past a STOP gate may be
run "to be safe".

- **STOP-1 — Burner:** generate + fund the fresh mainnet burner. Requires
  operator go-ahead (real ETH at risk).
- **STOP-2 — Deploy:** broadcast the executor deployment to mainnet. Requires
  operator go-ahead (mainnet key used for the first time).
- **STOP-3 — Arm:** register wallet/secret, set capital caps, confirm
  kill-switch. Still SHADOW. Requires operator go-ahead.
- **STOP-4 — Go live:** flip `flash_loan_arbitrage` SHADOW → LIMITED_LIVE.
  Requires the **final** operator sign-off and a fully green Production
  Readiness Checklist below.

**Default posture until STOP-4 is explicitly cleared: `flash_loan_arbitrage =
SHADOW`.** The 6-gate broadcaster (kill_switch → mode → capital → secret →
preflight `eth_call` → operator_confirm) still guards every trade even after
STOP-4.

---

## ✅ Production Readiness Checklist

Do not clear STOP-4 (go live) until **every** box is ticked and the operator
has signed off. Verification command for each item is in the referenced step.

```
☐ VPS healthy                 — docker compose ps all Up            (§1)
☐ Mongo healthy               — backend connects, no boot timeout   (§1, §2)
☐ Backend healthy             — GET $API/  → {"message":"Hello World"} (§2)
☐ Scanner healthy             — flash_loan_arbitrage RUNNING + discovery (§5)
☐ Executor deployed           — mainnet address printed by forge     (§3)
☐ Executor verified           — GET $API/arbicore/executor/verify READ Y (§4)
☐ Burner wallet funded        — GET .../wallets/{id}/balance > gas floor (§6)
☐ Kill switch tested          — engage → broadcast blocked → disengage (§7)
☐ Evidence pipeline working   — journal + technical-validation history write (§8)
☐ Rollback tested             — kill-switch + SHADOW demotion rehearsed (§10)
☐ Operator approval obtained  — explicit sign-off recorded for STOP-4  (§9)
```

---

## Pre-flight facts (carried from Sepolia phases)

| Item | Value |
|---|---|
| Sepolia executor (testnet-only, DO NOT reuse) | `0x99c0b64e8F24fc1aADb07dAbA938d9f11dCD1052` |
| Sepolia deployer + validation signer | **burned / testnet-only — never touch mainnet** |
| Contract | `contracts/contracts/core/FlashLoanReceiver.sol` (8/8 Foundry tests, ~4987-byte runtime) |
| Deploy script | `contracts/script/Deploy.s.sol` (chain-aware via `block.chainid`) |
| Mainnet chain id | `8453` |

**Base mainnet venue addresses** (baked as defaults in `Deploy.s.sol`, and in
`contracts/.env.example`):

| Venue | Base Mainnet (8453) |
|---|---|
| Balancer V2 Vault | `0xBA12222222228d8Ba445958a75a0704d566BF2C8` |
| Aave V3 Pool | `0xA238Dd80C259a72e81d7e4664a9801593F98d1c5` |
| Uniswap V3 SwapRouter02 | `0x2626664c2603336E57B271c5C0b26F421741e481` |

**Flash-loan head:** let the engine/economics gate choose the head per
opportunity. On mainnet the Balancer V2 head (0-fee) is generally preferred
over Aave V3 (5 bps premium); the executor supports both and the pipeline
selects the cheaper viable head. No hardcoded head for first-live.

---

## 0. Authenticate (cookie jar)

```bash
curl -s -c cj.txt -X POST $API/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"username":"<admin>","password":"<pw>"}'
# all mutating calls below reuse: -b cj.txt
```
Credentials are the VPS operator admin (see your own secrets store — never the
Sepolia workspace admin).

---

## 1. Deploy the latest code to the VPS

```bash
ssh <vps>
cd /opt/arbicore-x                       # repo path on the VPS
git fetch --all && git checkout main && git pull --ff-only
git log -1 --oneline                     # confirm the Phase-A commit is present
docker compose build backend frontend
docker compose up -d
docker compose ps                        # backend + frontend + mongo all "Up"
```

**Checklist → VPS healthy / Mongo healthy.** If backend boot hangs, tail
`docker compose logs backend` for the `BOOT:` lines — the last
`BOOT: <handler> done` identifies the last successful startup stage; a
`BOOT: ... TIMED OUT` points at an unreachable Mongo.

---

## 2. Configure the production environment (Base mainnet)

Backend `.env` on the VPS (secrets stay OUT of git):

```
MONGO_URL=<vps mongo uri>
DB_NAME=arbicore_x
JWT_SECRET=<long random secret>                 # REQUIRED — auth 500s without it
CORS_ORIGINS=https://<your-frontend-domain>     # set explicitly (never '*' in prod)
ARBICORE_RPC_URL=<PRIMARY mainnet RPC>          # see RPC note below
ARBICORE_CHAIN=base
ARBICORE_EXECUTOR_ADDRESS_BASE=                 # filled after §3 deploy
# NO signer key here. The mainnet burner key is registered via the secret
# registry (§6), Fernet-wrapped at rest — never a plaintext .env value.
```

**RPC note (documented: dedicated primary + public fallback).**
- **Primary (recommended for live):** a dedicated provider endpoint
  (Alchemy / QuickNode / Coinbase CDP). Live broadcasting on the public
  endpoint risks rate-limits / 403s during the trade window.
- **Fallback:** `https://mainnet.base.org` (public, no key). Acceptable for
  read/verify, not ideal under load.
Set `ARBICORE_RPC_URL` to the dedicated endpoint; keep the public one noted as
a manual fallback.

Frontend `.env`: `REACT_APP_BACKEND_URL=https://<vps-host>` (no trailing `/api`).

Apply env changes:
```bash
docker compose up -d --force-recreate backend
```

Verify backend + chain:
```bash
curl -s $API/                       # {"message":"Hello World"}  → Backend healthy
curl -s -b cj.txt $API/arbicore/rpc/check   # READY, chain_id 8453
```
**Checklist → Backend healthy.** `rpc/check` must report chain id `8453`.

---

## ⛔ STOP-1 — mainnet burner (operator approval required)

## 3. Deploy the mainnet executor  *(after STOP-1 + STOP-2)*

> This is the first time a **mainnet** key is used. It stays in
> `contracts/.env` (gitignored, `chmod 600`), is used ONLY by `forge`, and is a
> **fresh dedicated deployer** — never the Sepolia key.

```bash
cd /opt/arbicore-x/contracts
cp .env.example .env                 # mainnet venue addresses already pre-filled
# edit .env:
#   BASE_RPC_URL=<dedicated mainnet RPC>
#   DEPLOYER_PRIVATE_KEY=0x...       <-- fresh mainnet deployer, funded with a little ETH
#   BASESCAN_API_KEY=...             <-- optional (only if verifying source, §3a)

source .env

# Dry-run first (NO broadcast) — confirm it targets chain 8453 + mainnet venues:
forge script script/Deploy.s.sol:Deploy --rpc-url base -vvvv

# ⛔ STOP-2 — operator go-ahead before the real broadcast:
forge script script/Deploy.s.sol:Deploy --rpc-url base --broadcast -vvvv
```

On success the script prints:
```
Target: Base mainnet (chainid 8453)
Executor deployed at: 0x....
Update backend/.env with:
  ARBICORE_EXECUTOR_ADDRESS_BASE=0x....
```
**Checklist → Executor deployed.** Record the mainnet address.

### 3a. (Optional) verify source on Basescan
Skippable. To publish source, add `--verify --etherscan-api-key
$BASESCAN_API_KEY` to the broadcast command (Etherscan v2 multichain key works
for chain 8453). Not required for LIMITED_LIVE.

### 3b. Wire the address into the backend
```
# backend/.env
ARBICORE_EXECUTOR_ADDRESS_BASE=0x....   # the deployed mainnet address
```
```bash
docker compose up -d --force-recreate backend
```

---

## 4. Verify the deployed executor (on-chain identity)

```bash
curl -s -b cj.txt "$API/arbicore/executor/verify?chain=base"
```
Expect **overall READY** with all checks green:
- `address_configured` READY
- `contract_deployed` READY (bytecode present)
- `vault_matches`  → `0xBA12…2C8`  (Balancer V2)
- `aave_matches`   → `0xA238…d1c5` (Aave V3 Pool)
- `router_matches` → `0x2626…e481` (Uniswap V3)
- `owner_matches`  → the mainnet deployer

**Checklist → Executor verified.** If any getter mismatches, STOP — do not
proceed; re-check the deployed address and the mainnet venue map.

---

## 5. Enable the continuous scanner (still SHADOW)

```bash
# inspect families + state
curl -s -b cj.txt $API/arbicore/operations/scanners

# ENABLE the flash-loan family (verb = start, QUERY param — not a JSON body)
curl -s -b cj.txt -X POST \
  "$API/arbicore/operations/scanners/FLASH_LOAN_ARBITRAGE/action?action=start"
```
Confirm discovery + SHADOW pipeline are alive:
```bash
curl -s -b cj.txt $API/arbicore/auto-executor/status      # running
curl -s -b cj.txt "$API/arbicore/opportunities?limit=5"   # live candidates
curl -s -b cj.txt $API/arbicore/journal/summary           # decisions journalling
```
**Checklist → Scanner healthy.** Family shows `RUNNING`, AutoExecutor
`running`, candidates appear, journal is writing. Because the mode is SHADOW,
nothing broadcasts — the pipeline evaluates and (mostly) declines. On mainnet,
unlike Sepolia, genuinely profitable candidates can appear; SHADOW still refuses
to broadcast them until STOP-4.

---

## ⛔ STOP-3 — arm LIMITED_LIVE plumbing (operator approval required)

## 6. Register + fund the mainnet burner  *(after STOP-3)*

**Never** put the burner private key in `.env`. Register it through the secret
registry so it is Fernet-wrapped at rest, then attach it to a wallet row.

```bash
# 6a. Wrap the burner key (scope=evm_sign, algorithm=eth_privkey; 64 hex, no 0x).
#     The response returns a handle_id + masked preview — never the plaintext.
curl -s -b cj.txt -X POST $API/arbicore/execution/secrets \
  -H 'Content-Type: application/json' \
  -d '{"plaintext":"<64-hex-burner-privkey>","scope":"evm_sign","algorithm":"eth_privkey","label":"base-mainnet-burner-01"}'
# → note the returned handle.handle_id

# 6b. Register the wallet, linking the secret handle (NO key material here).
curl -s -b cj.txt -X POST $API/arbicore/execution/wallets \
  -H 'Content-Type: application/json' \
  -d '{"wallet_id":"mainnet-burner-01","address":"0x<burner-address>","chain":"base","execution_role":"broadcaster","secret_handle_id":"<handle_id>","label":"base-mainnet-burner-01","actor":"operator","reason":"limited-live burner"}'

# 6c. Fund the burner address with a small amount of ETH (gas) on Base mainnet,
#     then confirm balance + health:
curl -s -b cj.txt "$API/arbicore/execution/wallets/mainnet-burner-01/balance"
curl -s -b cj.txt "$API/arbicore/execution/wallets/mainnet-burner-01/health?strategy=flash_loan_arbitrage"
```
**Checklist → Burner wallet funded.** Health card should report gas above the
floor and the secret handle resolvable. Fund only what a few small trades'
gas requires.

## 6d. Set the smallest capital caps

```bash
# Tiny per-trade notional + a hard daily loss cap. Exact numbers are the
# operator's to set (placeholders shown). Field names follow the capital
# policy defaults returned by GET .../capital-policy.
curl -s -b cj.txt -X PATCH $API/arbicore/execution/capital-policy/flash_loan_arbitrage \
  -H 'Content-Type: application/json' \
  -d '{"max_notional_usd":<PER_TRADE_CAP>,"daily_loss_cap_usd":<DAILY_LOSS_CAP>,"actor":"operator","reason":"first-live smallest notional"}'

# confirm:
curl -s -b cj.txt $API/arbicore/execution/capital-policy/flash_loan_arbitrage
```
> Start as small as the venue minimums allow. Confirm the exact field names
> against `GET .../capital-policy` (`defaults` block) before patching.

## 7. Kill-switch verification (arm + prove it blocks)

```bash
# state
curl -s -b cj.txt $API/arbicore/execution/kill-switch

# engage (reason REQUIRED) — this HARD-blocks the only eth_sendRawTransaction site
curl -s -b cj.txt -X POST $API/arbicore/execution/kill-switch/engage \
  -H 'Content-Type: application/json' -d '{"reason":"pre-live kill test","actor":"operator"}'

# with the switch engaged, the broadcaster refuses at gate-1. Verify via a
# SHADOW pipeline tick / auto-executor status that no broadcast occurs.
curl -s -b cj.txt $API/arbicore/auto-executor/status

# disengage to arm normal operation
curl -s -b cj.txt -X POST $API/arbicore/execution/kill-switch/disengage \
  -H 'Content-Type: application/json' -d '{"reason":"kill test complete","actor":"operator"}'

# audit trail
curl -s -b cj.txt $API/arbicore/execution/kill-switch/audit
```
**Checklist → Kill switch tested.**

## 8. Evidence pipeline check

```bash
curl -s -b cj.txt $API/arbicore/journal/summary
curl -s -b cj.txt "$API/arbicore/wizard/technical-validation/history"
```
**Checklist → Evidence pipeline working.** Journal records decisions and (if
run) technical-validation history persists receipts/events.

---

## 9. Go / No-Go review  → then ⛔ STOP-4

Run the readiness aggregators and confirm every checklist box:
```bash
curl -s -b cj.txt "$API/arbicore/wizard/state?strategy=flash_loan_arbitrage&chain=base"
curl -s -b cj.txt "$API/arbicore/wizard/flash-loan-prereqs?chain=base"
curl -s -b cj.txt $API/arbicore/execution/mode      # flash_loan_arbitrage = SHADOW
```
**Go/No-Go — all must be true:**
- [ ] `rpc/check` chain id `8453`, executor verify overall READY
- [ ] Scanner RUNNING, discovery live, journal writing, no repeated preflight reverts
- [ ] Burner funded; wallet health READY; secret handle resolvable
- [ ] Capital caps set to smallest notional + hard daily loss cap
- [ ] Kill-switch proven to block, then disengaged
- [ ] Evidence pipeline writing
- [ ] Rollback rehearsed (§10)
- [ ] **Operator sign-off recorded** for STOP-4

If any box is unchecked → **NO-GO**. Stay in SHADOW.

**Checklist → Operator approval obtained.**

---

## ⛔ STOP-4 — enable LIMITED_LIVE (final operator sign-off)

Promote exactly one step on the ladder (SHADOW → LIMITED_LIVE). The mode
transition body uses **`to_mode`** (NOT `mode`):

```bash
curl -s -b cj.txt -X POST $API/arbicore/execution/mode/flash_loan_arbitrage \
  -H 'Content-Type: application/json' \
  -d '{"to_mode":"LIMITED_LIVE","reason":"first live — smallest notional, approved","actor":"operator"}'

# confirm
curl -s -b cj.txt $API/arbicore/execution/mode/flash_loan_arbitrage
```
The response echoes `broadcast_allowed: true` once LIMITED_LIVE. Every trade
still passes the full 6-gate ladder:
`kill_switch → mode → capital → secret → preflight(eth_call) → operator_confirm`.

---

## 10. Monitor first executions + rollback

Monitor:
```bash
curl -s -b cj.txt $API/arbicore/post-trade/latest        # recent broadcast receipts
curl -s -b cj.txt $API/arbicore/journal/summary          # decision outcomes
curl -s -b cj.txt "$API/arbicore/wizard/technical-validation/history"
docker compose logs -f backend | grep -iE "broadcast|revert|error|kill"
```

**Rollback / stop (rehearse this BEFORE STOP-4 → Checklist "Rollback tested"):**
```bash
# 1. Immediate hard stop — engage kill-switch (blocks the only send site):
curl -s -b cj.txt -X POST $API/arbicore/execution/kill-switch/engage \
  -H 'Content-Type: application/json' -d '{"reason":"rollback","actor":"operator"}'

# 2. Demote the strategy back to SHADOW (ladder allows any backward jump):
curl -s -b cj.txt -X POST $API/arbicore/execution/mode/flash_loan_arbitrage \
  -H 'Content-Type: application/json' -d '{"to_mode":"SHADOW","reason":"rollback","actor":"operator"}'

# 3. (Optional) pause the scanner:
curl -s -b cj.txt -X POST \
  "$API/arbicore/operations/scanners/FLASH_LOAN_ARBITRAGE/action?action=stop"
```

Troubleshooting quick-refs:
- **Preflight reverts** → decode the 4-byte selector: `0x199bb70b`=EmptyHops,
  `0xdb42144d`=InsufficientBalance, `0xea8e4eb5`=NotAuthorized,
  `0xe9211597`=CallerNotPool.
- **RPC 403 / rate-limit during a trade** → switch `ARBICORE_RPC_URL` to the
  dedicated provider and `docker compose up -d --force-recreate backend`.
- **Any anomaly** → engage the kill-switch first, ask questions second.

---

## What stays OFF (feature freeze)
No new modules. Other scanner families stay in learning mode. Adaptive weights
stay OBSERVE. Only work that unblocks a successful, safe live flash-loan trade
is in scope. LIMITED_LIVE is never enabled without the operator clearing STOP-4.
