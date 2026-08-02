# ArbiCore X · Flash Loan Operator Manual (v1.0.0)

**Audience:** the operator who will execute the first controlled
LIMITED_LIVE Flash Loan transaction on Base mainnet.
**Baseline:** v1.1.0 candidate · 418/418 backend tests green.
**Companion docs:**
- `docs/ui_v2/28_PHASE0_RECOVERY_AND_FLASHLOAN_COMPLETION.md`
- `docs/ui_v2/29_FLASH_LOAN_PRODUCTION_READINESS_AUDIT.md`
- `canonical_repo/contracts/DEPLOY.md`

---

## 0. Quickstart (five links you will use most)

| Screen | Path | Purpose |
|---|---|---|
| **Guided Wizard** | `/v2/wizard` | Ten-step readiness dashboard; poll every 5 s |
| **Flash Loan Operator** | `/v2/flash-loan-operator` | The single page that runs every mutating operation |
| **Executor Verify** | `/v2/executor-verify` | Verify a deployed FlashLoanReceiver contract |
| **Post-Trade Dashboard** | `/v2/post-trade` | Broadcast receipts + evidence + learning updates |
| **Kill Switch** | (banner in Operator page + `POST /api/arbicore/execution/kill-switch/engage`) | Global stop |

---

## 1. Wallet setup

You need **one Externally-Owned Account** (EOA) on Base to serve as the
**gas wallet** — it pays the tiny gas for the flash-loan transaction and
receives residual profit (unless you split the profit recipient).

1. Create a fresh EOA (MetaMask, `cast wallet new`, whatever you prefer).
2. **Do not reuse a wallet that holds significant funds.** Treat this as
   a burner — you can rotate it later.
3. Send **~0.02 ETH on Base** to it (bridge or CEX withdraw). Enough for
   20+ validation transactions.
4. Note the address; you'll register it in step 3.

## 2. RPC setup

The backend needs an RPC to preflight, estimate gas, and broadcast.

1. Edit `/app/backend/.env` and add:
   ```
   ARBICORE_RPC_URL=https://mainnet.base.org
   ```
   Alternatives that work: Alchemy Base, Infura Base, Ankr, Coinbase Cloud,
   your own node. **Base mainnet chain id must be 8453.**
2. Restart the backend:
   ```
   sudo supervisorctl restart backend
   ```
3. Verify: open `/v2/wizard` — Step 01 (RPC configuration) should turn
   **READY** with `chain_id=8453`.

## 3. Secret setup (Fernet)

The burner's private key is wrapped by the Fernet backend before it
touches Mongo. `VAULT_KEY` (backend env var) is the Fernet key that
protects every secret.

1. Generate a Fernet key locally:
   ```
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
2. Add it to `backend/.env`:
   ```
   VAULT_KEY=<the 44-char Fernet key>
   SIGNING_ACTIVE_KEY_VERSION=v1
   SIGNING_ED25519_PRIVATE_V1=<32-byte hex or base64 seed>
   ```
3. Restart the backend.
4. Register the wallet's private key as a secret:
   ```
   curl -X POST "$API/arbicore/execution/secrets" \
       -H "Content-Type: application/json" \
       -d '{"scope":"broadcast","algorithm":"eth_privkey",
            "plaintext_hex":"<64-char private key hex, no 0x>"}'
   ```
   The response includes `handle_id` — save it for step 4.
5. Register the wallet in the Wallet Registry using that `handle_id`:
   ```
   curl -X POST "$API/arbicore/execution/wallets" \
       -H "Content-Type: application/json" \
       -d '{"wallet_id":"burner-base-01",
            "address":"0xYourBurner",
            "chain":"base","execution_role":"gas",
            "secret_handle_id":"<from step 4>"}'
   ```
6. Verify in `/v2/wizard`: Steps 02 (Wallet) and 03 (Secret) turn READY.

## 4. Deploying FlashLoanReceiver

Full details in `canonical_repo/contracts/DEPLOY.md`. Summary:

**Foundry (recommended):**
```
forge create \
   --rpc-url https://mainnet.base.org \
   --private-key $BURNER_KEY \
   canonical_repo/contracts/FlashLoanReceiver.sol:FlashLoanReceiver \
   --constructor-args \
      0xBA12222222228d8Ba445958a75a0704d566BF2C8 \
      0x2626664c2603336E57B271c5C0b26F421741e481
```

Or use **Remix** with the same constructor args. Note the deployed
address — call it `EXECUTOR_ADDR`.

Cost: **~$0.10 in gas, one-time.**

## 5. Configuring the executor

1. Add to `backend/.env`:
   ```
   ARBICORE_EXECUTOR_ADDRESS_BASE=<EXECUTOR_ADDR>
   ```
2. Restart backend.
3. Open `/v2/executor-verify`. It runs six checks:
   - Address configured
   - RPC available
   - Contract deployed (bytecode present)
   - `VAULT()` == `0xBA12...` (Balancer V2 Vault)
   - `ROUTER()` == `0x2626664...` (Uniswap V3 SwapRouter02)
   - `owner()` == burner (optional — fill in "Expected owner")
4. Overall pill must read **READY**. If any check is BLOCKED, do **not**
   proceed — resolve first.
5. Wizard Step 05/06 will now flip to READY.

## 6. Running Continuous Discovery

Discovery starts automatically (see `ARBICORE_DISCOVERY_AUTOSTART`
default = true). You can pause/resume from the Operations page or via:
```
POST /api/arbicore/execution/discovery/start
POST /api/arbicore/execution/discovery/stop
GET  /api/arbicore/execution/discovery/status
```
Each tick writes a `CanonicalOpportunity` row to `arbicore_opportunities`
and (when the strategy is in SHADOW) may build a plan into
`execution_plans`.

## 7. Reviewing opportunities

- `/v2/opportunities` — cockpit list, filter by family (`FLASH_LOAN_ARBITRAGE`),
  verdict, chain.
- `/v2/opportunities/{id}` — detail view with verification data.
- `GET /api/arbicore/opportunities/{id}/timeline` — full institutional
  audit trail.

## 8. Running SHADOW

By default every strategy is in **SHADOW** (or **OBSERVE**). Broadcasts
are refused by the mode gate. This is where you validate:

- Certifier verdict distribution (`/v2/intelligence` → Certification card).
- Plan cadence + evidence stream (`/api/arbicore/intelligence/evidence/*`).
- Calibration ticks + adaptive-weight recommendations (background workers
  publish every 3600 s).

Do **not** flip to LIMITED_LIVE until you have at least one green
certification pass and the wizard says all steps are READY.

## 9. Running LIMITED_LIVE

Flip the strategy from SHADOW → LIMITED_LIVE:
```
curl -X POST "$API/arbicore/execution/mode/flash_loan_arbitrage" \
    -H "Content-Type: application/json" \
    -d '{"mode":"LIMITED_LIVE","reason":"first controlled validation"}'
```
The wizard Step 09 must go READY.

## 10. First intentional test (pipeline-exercise)

**Optional but recommended.** Do a broadcast with
`recipient = burner_address` (not the executor). The Vault will call
`receiveFlashLoan` on your EOA, which reverts on-chain — but you exercise
every off-chain gate + signature + tx hash. Cost: ~$0.05.

- In the Operator page, submit a small plan with
  `flash_loan_provider = balancer_v2`, `borrow_token = WETH`,
  `borrow_amount_wei = 10^15` (0.001 WETH), `recipient = burner`.
- "Prepare broadcast" → verify `preflight_ok=false` (revert expected)
  OR `preflight_ok=true` if the RPC's `eth_call` is permissive.
- Toggle "confirm" → submit → observe `tx_hash` in Post-Trade.
- The tx will fail on chain — that's the point.

## 11. First successful transaction (value-producing)

1. Wizard fully green.
2. Compose a Flash Loan plan with **executor as recipient**:
   ```json
   {
     "strategy": "flash_loan_arbitrage",
     "flash_loan_provider": "balancer_v2",
     "chain": "base",
     "borrow_token": "0x4200000000000000000000000000000000000006",
     "borrow_amount_wei": 100000000000000000,
     "hops": [
       {"token_in":"WETH","token_out":"USDC","fee_tier_bps":5,
        "amount_in_wei":100000000000000000,"amount_out_min_wei":249500000},
       {"token_in":"USDC","token_out":"WETH","fee_tier_bps":30,
        "amount_in_wei":0,"amount_out_min_wei":100500000000000000}
     ],
     "profit_recipient": "0xYourBurner"
   }
   ```
   `recipient` is auto-filled from `ARBICORE_EXECUTOR_ADDRESS_BASE`.
3. Prepare broadcast → confirm → wait for `tx_hash`.
4. Post-Trade dashboard shows the receipt within seconds.

## 12. Reading evidence

- **Evidence bundles** (`evidence_bundles` collection): signed Ed25519
  receipts of every LIMITED_LIVE broadcast attempt. Verify with:
  ```
  POST /api/arbicore/intelligence/evidence/verify
  { "bundle_hash": "<hash>" }
  ```
- **Timeline** (`arbicore_opportunities.timeline`):
  `GET /api/arbicore/opportunities/{id}/timeline`.
- **Post-Trade UI** (`/v2/post-trade`) surfaces the last 10 broadcasts.

## 13. Recovery procedures

| Symptom | Recovery |
|---|---|
| Backend service down | `sudo supervisorctl restart backend`; check `/var/log/supervisor/backend.err.log` |
| RPC 429/500 | Rotate `ARBICORE_RPC_URL`; restart backend |
| Executor address wrong | Update `ARBICORE_EXECUTOR_ADDRESS_BASE`; restart |
| VAULT_KEY lost | **Every wrapped secret becomes unreadable.** Register new secrets after generating a new Fernet key; re-register wallets |
| Signing key lost | Delete matching row from `evidence_signing_keys`; rotate `SIGNING_ACTIVE_KEY_VERSION` |
| Broadcast stuck in preflight fail | Check `broadcast_last_result.denied_reason`; usually gas / slippage / kill_switch |

## 14. Kill Switch usage

The kill switch is a global stop. When ENGAGED, every broadcast attempt
DENIES at the first gate.

Engage:
```
POST /api/arbicore/execution/kill-switch/engage
{ "reason": "operator drill", "actor": "operator" }
```
Disengage:
```
POST /api/arbicore/execution/kill-switch/disengage
{ "reason": "drill complete", "actor": "operator" }
```
Audit history: `GET /api/arbicore/execution/kill-switch/audit?limit=50`.

The Operator page renders a persistent banner — always visible, one-click.

## 15. Common troubleshooting

| Wizard blocker | What it means | Fix |
|---|---|---|
| **rpc** BLOCKED | `ARBICORE_RPC_URL` unset or unreachable | Set in `backend/.env`, restart |
| **wallet** BLOCKED | No gas wallet registered on chain | `POST /api/arbicore/execution/wallets` |
| **secret** BLOCKED | Wallet has no `secret_handle_id` | Wrap key first, re-register wallet with handle |
| **gas_balance** BLOCKED | 0 ETH on burner | Send ~0.02 ETH to burner on Base |
| **executor** BLOCKED | Env var unset or contract not deployed | Deploy `FlashLoanReceiver.sol`, set env, restart |
| **executor** WAIT | RPC not responding | Check RPC provider status |
| **kill_switch** BLOCKED | Global stop engaged | Disengage from Operator page banner |
| **mode** WAIT | Strategy still in SHADOW | Flip to LIMITED_LIVE (only after cert pass) |
| Broadcast rejected: `capital_denied` | Plan exceeds capital policy | Reduce `borrow_amount_wei` OR raise limits |
| Broadcast rejected: `preflight_failed` | On-chain revert simulated | Fix hops, slippage, or route |
| `RepayFailed` at executor | Insufficient output to repay Vault | Verify swap route economics; tighten `amount_out_min_wei` |
| No tx hash but `broadcast_sent=true` | Response landed at wrong path | Refresh Post-Trade; check `execution_plans.broadcast_last_result` |

---

## Appendix A · Backend .env template

```
# Mongo
MONGO_URL="mongodb://localhost:27017"
DB_NAME="test_database"
CORS_ORIGINS="*"

# Base mainnet RPC (required for LIMITED_LIVE)
ARBICORE_RPC_URL=https://mainnet.base.org

# FlashLoanReceiver executor address (after deploy)
ARBICORE_EXECUTOR_ADDRESS_BASE=

# Fernet secret backend (required for wrapping private keys)
VAULT_KEY=

# Evidence signing (Ed25519)
SIGNING_ACTIVE_KEY_VERSION=v1
SIGNING_ED25519_PRIVATE_V1=

# Optional
ARBICORE_DISCOVERY_AUTOSTART=true
```

## Appendix B · Six operator questions (quick answers)

| Q | A |
|---|---|
| Can I connect my wallet today? | **Yes** — Wallet Registry + Fernet backend live |
| Fund only the gas wallet? | **Yes** — 0.02 ETH on Base covers 20+ tx |
| Flash loan supplies all trading capital? | **Yes** — Balancer V2 (0 bps premium) |
| System can execute a full atomic flash loan? | **Yes** — after deploying `FlashLoanReceiver.sol` |
| Operator steps remain? | **Six** — RPC, wallet fund, wallet register + secret, deploy contract, wire env var, mode flip |
| Software work remains? | **Zero** — Phase 9 closed the last item (`user_data_hex` refinement) |
