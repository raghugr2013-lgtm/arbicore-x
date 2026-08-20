# ArbiCore — Limited Live Setup Manual

Golden rules
- Public values (RPC URL, wallet ADDRESS, executor ADDRESS) → backend env / config.
- Secret values (signer PRIVATE KEY) → encrypted vault ONLY (never .env, source, chat, files).
- After any `.env` change: restart backend (`sudo supervisorctl restart backend`).
- Edit ONE key at a time in `/app/app/backend/.env`; never retype `REACT_APP_BACKEND_URL` or `MONGO_URL`.

Verify base (run after each step). Get preview URL from `/app/app/frontend/.env` (REACT_APP_BACKEND_URL), log in as operator:
```
API=<REACT_APP_BACKEND_URL>
# login → cookie; then:
curl $API/api/arbicore/engine/readiness-matrix   # GREEN/YELLOW/RED per item
curl $API/api/arbicore/engine/rpc-capabilities    # state_override/archive/trace
curl $API/api/arbicore/engine/onboarding          # presence checklist
```

---

## 1. Alchemy Base RPC   (value = SECRET: URL embeds API key)
- Where: backend env → `/app/app/backend/.env` (or Emergent → Project → Environment/Secrets).
- Variable: `ARBICORE_RPC_URL_BASE=https://base-mainnet.g.alchemy.com/v2/<YOUR_KEY>`
  - (Leave the existing `ARBICORE_RPC_URL` line as-is; `_BASE` takes precedence for Base.)
- Save: add the line, then `sudo supervisorctl restart backend`.
- Verify saved: `grep -c ARBICORE_RPC_URL_BASE /app/app/backend/.env` → `1`.
- Verify GREEN: `readiness-matrix` → `CONFIGURATION_RPC` GREEN; then run a scan and check `rpc-capabilities` + coverage: rate-limit failures should drop sharply.

## 2. Archive RPC (only if separate from #1)   (SECRET)
- Variable: `ARBICORE_ARCHIVE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/<YOUR_KEY>`
  - If your Alchemy tier is archive-capable, reuse the same URL as #1.
- Verify: `rpc-capabilities` → `archive_state: true`. For fork/trace, see #7.

## 3. Base gas wallet ADDRESS   (PUBLIC — address only, NEVER the key)
- Where: backend env.
- Variable: `ARBICORE_GAS_WALLET_ADDRESS=0x...`  (the burner wallet's public address)
- Save + restart.
- Verify GREEN: `readiness-matrix` → `WALLET_GAS` GREEN; `onboarding` → `gas_wallet` DONE.
- Note: fund it with a small ETH reserve on Base for gas.

## 4. Executor contract ADDRESS   (PUBLIC)
- Where: backend env (or ArbiCore UI → Settings → Network Config).
- Variable: `ARBICORE_EXECUTOR_ADDRESS_BASE=0x...`
- Save + restart.
- Verify saved: `readiness-matrix` → `EXECUTOR_CONTRACT` GREEN.
- Verify on-chain (ArbiCore will do this automatically once set): the address must have bytecode + pass allowlist config (see #5 allowlist below).

## 4b. Executor allowlist / configuration   (PUBLIC config)
- Where: ArbiCore UI → Settings → Network Config (or `NetworkConfigRepo`).
- Ensure approved routers (Uniswap V3 `0x2626664c…e481`, Aerodrome `0xcF77a3Ba…4E43`) and tokens are allowlisted, and the executor references them.
- Verify: `readiness-matrix` → `DEX_ADAPTERS_SETTLE` GREEN (already) and executor allowlist check passes once #4 is set.

## 5. Execution signer PRIVATE KEY   (SECRET → encrypted vault ONLY)
- Do NOT put this in `.env`, source, chat, or a file.
- `VAULT_KEY` is already configured (FernetSecretBackend is ready).
- Where/how (two supported paths):
  - (a) Emergent secret manager / KMS: store the key there and give ArbiCore the handle name.
  - (b) One-time secure ingestion endpoint: on resume I will add `POST /api/arbicore/settings/signer` (operator-auth) that accepts the key over HTTPS once, encrypts it via `VAULT_KEY` into the `arbicore_secrets` collection, and returns only a handle — the raw key is never logged, echoed, or stored in plaintext. You call it privately (curl/Postman), not in chat.
- Verify GREEN: `readiness-matrix` → `SIGNER` GREEN (the app confirms a stored handle exists + the derived address matches the gas/execution wallet). The private key itself is never displayed.

## 6. VAULT_KEY / secret-manager config
- Status: `VAULT_KEY` is PRESENT in backend env (vault operational) — no action needed unless rotating.
- If rotating: set a new `VAULT_KEY` and re-ingest the signer secret (old handles become unreadable).
- Verify: signer store/list works (no "VAULT_KEY missing" error in backend logs).

## 7. Anvil fork configuration   (for real FORK_VALIDATION)
- Requires an archive/trace-capable RPC (#2) + the `anvil` binary.
- Variable: `ARBICORE_FORK_RPC_URL=<archive RPC url>` (can equal #2 if archive+trace).
- On resume I will: install/point to `anvil`, spawn `anvil --fork-url $ARBICORE_FORK_RPC_URL`, and run a real fork test.
- Verify GREEN: `readiness-matrix` → `FORK_VALIDATION` GREEN — but ONLY after an actual fork test executes successfully (no config-presence GREEN).

---

## FINAL MANUAL CHECKLIST (complete before we resume)
- [ ] `ARBICORE_RPC_URL_BASE` set to your Alchemy Base URL (secret)
- [ ] `ARBICORE_ARCHIVE_RPC_URL` set (same as above if archive-tier) (secret)
- [ ] `ARBICORE_GAS_WALLET_ADDRESS` set to burner PUBLIC address; wallet funded with gas ETH
- [ ] `ARBICORE_EXECUTOR_ADDRESS_BASE` set to deployed executor PUBLIC address
- [ ] Executor allowlist/config confirmed (routers + tokens) in Network Config
- [ ] Execution signer key stored in the vault/KMS (via secret manager handle, or the secure ingestion endpoint I'll add) — NOT in .env
- [ ] `VAULT_KEY` present (already ✅) — rotate only if you choose to
- [ ] `ARBICORE_FORK_RPC_URL` set for fork validation (if archive/trace available)
- [ ] Backend restarted after env changes
- [ ] Tell me your Alchemy tier: archive+trace / archive-only / unsure

When these are done, I will (on real evidence only): connect Alchemy → measure rate-limit/coverage/latency before-vs-after → verify executor bytecode + allowlist on-chain → enable atomic executor state-override simulation → run the full settlement sim through the executor path → run Anvil fork validation → update the readiness matrix. SHADOW keeps running; LIMITED_LIVE stays operator-activated (never automatic).
