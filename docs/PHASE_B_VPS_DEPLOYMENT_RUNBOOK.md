# Phase B — VPS Operational Deployment Runbook

**Mode:** Operations, not features. Flash-Loan feature set is FROZEN.
**Goal:** ship the Phase-A-validated build to the VPS, run SHADOW until
healthy, then enable LIMITED_LIVE at the smallest practical notional and
monitor the first profitable executions.

`$API` below = the VPS backend base URL (e.g. `https://<vps-host>/api`).

---

## Pre-flight (before touching the VPS)

- [ ] **Fresh mainnet burner** — generate a NEW wallet on the VPS for
      LIMITED_LIVE. Do **NOT** reuse the Base Sepolia testnet key
      `ARBICORE_VALIDATION_SIGNER_KEY` (it was exposed in a readiness scan
      and is testnet-only — consider it burned). Never put a mainnet key
      in a plaintext `.env`; register it through the wallet/secret registry
      so it is Fernet-wrapped at rest.
- [ ] Decide the target for first live: **Base mainnet** executor must be
      deployed first (the Sepolia executor `0x99c0…1052` is testnet-only).
      Use the same one-command deploy (`--rpc-url base`), then set
      `ARBICORE_EXECUTOR_ADDRESS_BASE` to the mainnet address.

---

## 1. Deploy the latest code to the VPS

Use your existing VPS deploy flow (shared-infra `factory-mongo` compose
profile). Typical sequence:

```bash
ssh <vps>
cd /opt/arbicore-x            # repo path on the VPS
git fetch --all && git checkout main && git pull --ff-only
git log -1 --oneline          # confirm the Phase-A commit is present
docker compose build backend frontend
docker compose up -d
docker compose ps             # backend + frontend + mongo healthy
```

## 2. Configure the production environment

Backend env (VPS `.env`, secrets stay out of git):

```
MONGO_URL=<vps mongo uri>
DB_NAME=arbicore_x
JWT_SECRET=<long random secret>                 # REQUIRED — auth 500s without it
CORS_ORIGINS=https://<your-frontend-domain>     # set explicitly (was '*')
ARBICORE_RPC_URL=https://sepolia.base.org        # Base Sepolia for Phase B
ARBICORE_CHAIN=base-sepolia
ARBICORE_EXECUTOR_ADDRESS_BASE=0x99c0b64e8F24fc1aADb07dAbA938d9f11dCD1052
# ARBICORE_VALIDATION_SIGNER_KEY only needed if you run the engine self-test
# (POST /wizard/technical-validation execute=true) from the VPS.
```

Frontend `.env`: `REACT_APP_BACKEND_URL=https://<vps-host>` (no trailing /api).

Restart after env edits: `docker compose up -d --force-recreate backend`.

Verify base health:
```bash
curl -s $API/arbicore/rpc/check          # READY, chain_id 8453 (mainnet)
curl -s $API/arbicore/executor/verify     # overall READY (all 6 green)
```

## 3. Enable the continuous scanner

```bash
# inspect families + state
curl -s $API/arbicore/operations/scanners
# enable the flash-loan family
curl -s -X POST $API/arbicore/operations/scanners/flash_loan_arbitrage/action \
     -H 'Content-Type: application/json' -d '{"action":"enable"}'
```
Confirm the AutoExecutor is ticking and journalling candidates:
```bash
curl -s $API/arbicore/auto-executor/status
curl -s $API/arbicore/journal/summary
```

## ⚠️ Base Sepolia reality (critical for Phase B expectations)

Validated live in the workspace (same Sepolia config + executor):
- Scanner enable works; FLASH_LOAN_ARBITRAGE goes RUNNING.
- **Continuous discovery works** — the WETH/USDC route is discovered and
  refreshed (`base-weth-usdc-univ3-aero`, age ~30s).
- **SHADOW pipeline correctly DECLINES it**: verdict `SOFT_NO`, spread
  `0 bps`, return `-0.01` → AutoExecutor skips (no execution). Correct.

Consequence: **Base Sepolia has no *profitable* flash-loan opportunities**
(spreads ≈ 0). Under LIMITED_LIVE the economics gate will (correctly)
never broadcast — so a *scanner-driven profitable* execution will NOT
occur on Sepolia. That is a **mainnet** phenomenon.

On Sepolia the engine's on-chain execution is proven via the Phase A
Technical Validation endpoint (forces a tiny real trade), NOT the scanner.
Therefore the honest Phase-B-on-Sepolia completion criteria are:
  1. env configured (incl. JWT_SECRET, CORS_ORIGINS) ✓
  2. flash-loan scanner RUNNING ✓
  3. continuous discovery observed ✓
  4. SHADOW pipeline evaluates + correctly declines unprofitable ✓
  5. LIMITED_LIVE plumbing armed (wallet + capital + gates) — will sit
     idle with no profitable opp (expected)
  6. engine execution proof on-chain = Technical Validation (done)
Real scanner-driven profitable executions are validated on **mainnet**.

## Proven VPS commands (verified in workspace)

```bash
# login (cookie jar)
curl -s -c cj.txt -X POST $API/auth/login -H 'Content-Type: application/json' \
     -d '{"username":"<admin>","password":"<pw>"}'
# scanner status
curl -s -b cj.txt $API/arbicore/operations/scanners
# ENABLE flash-loan family (verb = start, query param)
curl -s -b cj.txt -X POST "$API/arbicore/operations/scanners/FLASH_LOAN_ARBITRAGE/action?action=start"
# discovery feed (candidates)
curl -s -b cj.txt "$API/arbicore/opportunities?limit=5"
# SHADOW pipeline health
curl -s $API/arbicore/auto-executor/status
curl -s $API/arbicore/journal/summary
```



Governance default keeps `flash_loan_arbitrage = SHADOW` — leave it there.
Health gates to watch (all should be green/among expected) for a sustained
window (e.g. 24–48h):
```bash
curl -s $API/arbicore/execution/mode          # flash_loan_arbitrage=SHADOW
curl -s $API/arbicore/wizard/state            # kill_switch READY; rpc READY(8453)
curl -s $API/arbicore/wizard/flash-loan-prereqs
```
Healthy = scanner producing opportunities, pipeline evaluating them,
SHADOW decisions journalling without errors, no repeated preflight reverts,
executor verify stays READY. Optionally re-run Shadow Certification on the
live mainnet feed and confirm PASS before promoting.

## 5. Enable LIMITED_LIVE (smallest practical notional)

Only after SHADOW is healthy AND you explicitly approve:
1. Register + fund the mainnet burner; confirm wallet/secret/gas steps READY.
2. Set the smallest capital cap in the capital policy (tiny per-trade
   notional + a hard daily loss cap). Confirm kill-switch is armed.
3. Promote one step (SHADOW → LIMITED_LIVE):
```bash
curl -s -X POST $API/arbicore/execution/mode/flash_loan_arbitrage \
     -H 'Content-Type: application/json' -d '{"mode":"LIMITED_LIVE"}'
```
The 6-gate broadcaster still enforces kill_switch → mode → capital →
secret → preflight(eth_call) → operator_confirm on every trade.

## 6. Monitor first profitable executions + troubleshoot

```bash
curl -s $API/arbicore/execution/broadcasts        # recent broadcast receipts
curl -s $API/arbicore/journal/summary             # decision outcomes
curl -s "$API/arbicore/wizard/technical-validation/history"  # engine self-tests
docker compose logs -f backend | grep -iE "broadcast|revert|error|kill"
```
Troubleshooting quick-refs:
- **Preflight reverts** → decode the 4-byte selector (see Errors.sol map;
  `0x199bb70b`=EmptyHops, `0xdb42144d`=InsufficientBalance,
  `0xea8e4eb5`=NotAuthorized, `0xe9211597`=CallerNotPool).
- **RPC 403 / flakiness** → move `ARBICORE_RPC_URL` to a dedicated provider.
- **Any anomaly** → engage the kill-switch immediately; it hard-blocks the
  only `eth_sendRawTransaction` call-site.
- **Regression after any change** → rerun `POST /arbicore/wizard/technical-validation`
  (dry first, then execute) as the single-click engine proof.

---

## What stays OFF in Phase B (feature freeze)
No new modules. Other scanner families remain in learning mode. Adaptive
weights stay OBSERVE. Only work that unblocks successful live flash-loan
trading is in scope.
