# P0 #3 — VPS Read-Only Activation & Evidence Runbook (SAFE)

Reproduces the exact read-only Base flash-loan discovery activation on your VPS using the
VPS's own existing Base RPC. No secret is requested or exposed. Nothing here signs, broadcasts,
withdraws, enables a live mode, or disengages the kill switch.

Prereqs on the VPS:
- Backend running and reachable (adjust BASE_URL below).
- A working Base RPC already configured in the VPS Network settings OR its `.env`
  (`ARBICORE_RPC_URL_BASE`). A dedicated RPC (Alchemy/Infura/QuickNode) is strongly recommended;
  the public `mainnet.base.org` is rate-limited and will not sustain a full discovery sweep.

## 0. Set variables + authenticate (cookie jar)
```bash
BASE_URL="https://<your-vps-host>"          # e.g. https://arbicore.example.com
JAR=/tmp/ac_cookies.txt

# Log in (admin). Do NOT paste the password into shared logs.
read -rsp "admin password: " ADMIN_PW; echo
curl -s -c "$JAR" -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PW\"}" ; echo
unset ADMIN_PW
```

## 1. Baseline (safety + RPC)
```bash
curl -s -b "$JAR" "$BASE_URL/api/arbicore/rpc/check" | python3 -m json.tool
curl -s -b "$JAR" "$BASE_URL/api/arbicore/wizard/flash-loan-prereqs?chain=base" | python3 -m json.tool
```
Expect: `rpc/check.status=READY`, `is_base_mainnet=true`; kill switch ENGAGED.

## 2. Enable Base network in Network config (approved mechanism)
Only run if `base_network_enabled` is BLOCKED. Replace the RPC URL with the VPS's real Base RPC.
```bash
curl -s -b "$JAR" -X POST "$BASE_URL/api/arbicore/settings/network/apply" \
  -H "Content-Type: application/json" \
  -d '{"patch":{"rpc_urls":{"base":["<YOUR_BASE_RPC_URL>"]},"chains_enabled":{"base":true}},"actor":"operator","reason":"P0#3 read-only Base flash-loan discovery"}' \
  | python3 -m json.tool
```

## 3. Enable ONLY the flash-loan Base + Aave V3 + Uniswap V3 discovery envelope
```bash
curl -s -b "$JAR" -X POST "$BASE_URL/api/arbicore/scanners/flash_loan_arb/providers/aave_v3/enable"    | python3 -m json.tool
curl -s -b "$JAR" -X POST "$BASE_URL/api/arbicore/scanners/flash_loan_arb/providers/uniswap_v3/enable" | python3 -m json.tool
curl -s -b "$JAR" -X POST "$BASE_URL/api/arbicore/scanners/flash_loan_arb/chains/base/enable"          | python3 -m json.tool
curl -s -b "$JAR" -X POST "$BASE_URL/api/arbicore/scanners/flash_loan_arb/resume"                      | python3 -m json.tool
```
Do NOT enable balancer_v2, dex_arb, cex/funding, or other chains in this pass.

## 4. Confirm the live quote provider is wired (critical)
```bash
curl -s -b "$JAR" "$BASE_URL/api/arbicore/engine/flash-loan/readiness" | python3 -m json.tool
```
- `readiness.quote_provider` MUST be `"live"` and `active=true`.
- If it is `"noop"`, the boot-time live-quote wiring did not complete (usually a slow/rate-limited
  RPC during on-chain Aerodrome pool resolution). Fix by pointing at a dedicated RPC, then restart
  the backend so boot activation re-runs:
  `sudo supervisorctl restart backend` (or your process manager), and re-check step 4.

## 5. Prove the live UniV3 quote leg (bounded, read-only)
```bash
curl -s -b "$JAR" -X POST "$BASE_URL/api/arbicore/wizard/opportunity-probe" \
  -H "Content-Type: application/json" \
  -d '{"chain":"base","token_in":"0x4200000000000000000000000000000000000006","token_out":"0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913","amount_in_wei":100000000000000000,"fees":[500,3000]}' \
  | python3 -m json.tool
```
Expect `any_live_pool=true` with real `amount_out_wei` + `block_number`.

## 6. Collect genuine discovery evidence (after ticks have run, quote_provider=live)
```bash
curl -s -b "$JAR" "$BASE_URL/api/arbicore/scanners/flash_loan_arb/status"        | python3 -m json.tool
curl -s -b "$JAR" "$BASE_URL/api/arbicore/scanners/flash_loan_arb/source-health" | python3 -m json.tool
curl -s -b "$JAR" "$BASE_URL/api/arbicore/scanners/flash_loan_arb/gate-analysis?window_minutes=60" | python3 -m json.tool
curl -s -b "$JAR" "$BASE_URL/api/arbicore/opportunities?family=FLASH_LOAN_ARBITRAGE&limit=50"       | python3 -m json.tool
```

## 7. Re-verify safety (must remain fail-closed)
```bash
curl -s -b "$JAR" "$BASE_URL/api/arbicore/wizard/flash-loan-prereqs?chain=base" | python3 -m json.tool
curl -s -b "$JAR" "$BASE_URL/api/arbicore/post-trade/latest?limit=5"            | python3 -m json.tool
curl -s -b "$JAR" "$BASE_URL/api/arbicore/auto-executor/status"                 | python3 -m json.tool
```
Expect: kill switch ENGAGED; executor/wallet/secret BLOCKED; post-trade receipts count=0;
auto-executor not running.

## STOP
Do NOT start Paper or Shadow, do NOT enable signer/broadcast/live mode, do NOT enable
dex_arb / Balancer / other chains until the flash-loan discovery pipeline is proven with a
dedicated RPC (quote_provider=live and verified candidates > 0) and you explicitly approve.
