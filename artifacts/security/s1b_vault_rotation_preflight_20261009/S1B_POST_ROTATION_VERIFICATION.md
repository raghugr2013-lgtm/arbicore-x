# S1-B — Post-rotation independent verification (READ-ONLY)

**Mode:** Read-only. No edits, deletes, rotations, restarts, recreates, builds, or deploys.  
**Verification timestamp (UTC):** `2026-10-09T10:58:33Z` – `2026-10-09T11:05:03Z`  
**Source claim:** `S1B_PHASE2_COMPLETION.md` (completed `2026-10-09T10:44:42Z`)  
**P2:** remains **BLOCKED** — not authorised by this audit  

Secrets referenced only as fingerprints / lengths / public addresses. **No key or ciphertext values reproduced.**

---

## Final deployment-gate recommendation

**P2 deployment: BLOCKED.**

S1-B vault rotation is independently verified as successful on the active path (**PASS WITH LIMITATIONS** for residual old key in stopped legacy `Config.Env` + retained recovery escrow). That clears the vault-containment gate claimed by Phase 2, but **does not** clear the broader execution-security gate: Alchemy credential logging, Mongo root access, public `/docs` + bootstrap token, deployer private-key exposure, and plaintext admin/JWT in ENV remain **FAIL**.

Do not deploy P2 until those remaining risks are remediated or explicitly accepted under separate written authorisation.

---

## Section verdicts

| # | Section | Verdict |
|---|---|---|
| 1 | Vault rotation | **PASS** |
| 2 | Old-key containment | **PASS WITH LIMITATIONS** |
| 3 | Runtime safety | **PASS WITH LIMITATIONS** |
| 4 | Remaining security findings | **FAIL** (multiple open items) |
| — | **P2 deploy gate** | **BLOCKED** |

---

## 1. Vault rotation — **PASS**

### Reconciliation with `S1B_PHASE2_COMPLETION.md`

| Claim | Live result |
|---|---|
| Active `VAULT_KEY` sha12 `fb5ca619211e` | **Confirmed** in `arbicore-x-backend-new` env and both active `.env` files |
| Cipher sha12 `45e7f15ca337` | **Confirmed** |
| Plaintext sha12 `b4ce2e6143a2` | **Confirmed** after decrypt with live key |
| Address `0x0a43F432681cA5eE053D53B79Ae1648FDAaBFa89` | **Confirmed** (decrypt-derived == doc `derived_address`) |
| Non-cipher fields preserved | **Confirmed** exact set: `algorithm`, `cipher`, `created_at`, `derived_address`, `execution_role`, `handle_id`, `label`, `provider`, `scope` |
| Handle `sec-3cec159e23d7495ab89140e5452a3d67` / `evm_sign` / `fernet_local` | **Confirmed** |
| Image digest `sha256:40b2116b…` | **Confirmed** (not a P2 image) |
| Recovery drill evidence | Artifact `recovery_drill_result.json` present; drill recorded PASS |
| Backup / escrow references | Paths exist; checksums OK; escrow unwrap sha12 `a46000441419` |

### Live evidence (hash-only)

```
vault_key_sha12=fb5ca619211e  vault_key_matches_expected_new=true
cipher_sha12=45e7f15ca337     decrypt_ok=true
plaintext_sha12=b4ce2e6143a2  address=0x0a43F432681cA5eE053D53B79Ae1648FDAaBFa89
count=1  api_keys_count=0
```

Active env files (mode `600`):

- `/home/raghu/projects/arbicore-x-v2/.env` → sha12 `fb5ca619211e`
- `/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env` → sha12 `fb5ca619211e`

### Backup / escrow (current references)

| Path | Status |
|---|---|
| `/home/raghu/arbicore_backups/s1b_phase2_readiness_20261009T053628Z/` | Present (`700`); `sha256sum -c SHA256SUMS` **OK** |
| `/home/raghu/arbicore_backups/s1b_vault_key_escrow_20261009T053628Z/` | Present (`700`); encrypted old key round-trip sha12 `a46000441419` |
| `/home/raghu/arbicore_backups/s1b_phase2_rotation_20261009T102445Z/` | Present; designated pre-rotation env copies retained |
| `recovery_drill_result.json` | `decrypt_with_old_escrow_ok=true`, address match, old cipher sha12 `660386c2e939` |

Off-host copy remains **not present** (previously documented not feasible). Limitation only for DR geography, not for local rotation correctness.

---

## 2. Old-key containment — **PASS WITH LIMITATIONS**

### Inventory (plaintext `VAULT_KEY=` assignments; no values)

| Class | Count | Paths / notes |
|---|---|---|
| Active env (new key) | 2 | v2 `.env`, `deployment/upgrade/backend/.env` — sha12 `fb5ca619211e` |
| Unintended old key in active env | **0** | — |
| Unintended old key in `/tmp` | **0** | — |
| Historical / tmp redacted (`REDACTED_AFTER_S1B_PHASE2`) | 30 | Prior scrub still in place |
| Designated recovery plaintext (old) | 2 | `…/s1b_phase2_rotation_…/backend.env.pre-rotation`, `root.env.pre-rotation` (**approved retention**) |
| Encrypted escrow (old) | 1 dir | `…/s1b_vault_key_escrow_…` (`VAULT_KEY.old.enc` + `wrap.pass`) — **approved retention** |
| Legacy stopped `Config.Env` (old) | 3 | `arbicore-x-b7-candidate`, `arbicore-x-backend-h05`, `arbicore-x-backend-w1` — all **exited** |

Evidence: `post_rotation_oldkey_inventory.json`. Docker logs (60m): no `VAULT_KEY=` lines observed in this probe.

### Limitations (accepted residual, not a rotation failure)

1. Old key sha12 `a46000441419` remains in **stopped** legacy container config until remove/recreate under separate change control.  
2. Approved recovery escrow + pre-rotation env copies still hold old material by design (must not start legacy; protect recovery dirs).  
3. Pre-rotation mongodumps still contain **old ciphertext** (expected; decryptable only with old key).

**Not found:** unintended old-key copies in active runtime configuration, current `.env` files, or temporary env dumps.

---

## 3. Runtime safety — **PASS WITH LIMITATIONS**

| Control | Live value | Verdict |
|---|---|---|
| Backend health | `running` / `healthy`; RestartCount=0; started `2026-10-09T10:25:59Z` | PASS |
| Image | `arbicore-x-backend:hybrid-e-rpc-9244ebd` | PASS |
| Image digest | `sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52` | PASS (original; **not** P2) |
| Git tag / sha env | `hybrid-e-rpc-9244ebd` / `fff0d0ec…` | PASS |
| `ARBICORE_EXECUTION_MODE` | `SHADOW` | PASS |
| `ARBICORE_AUTOEXEC_AUTOSTART` | `false` | PASS |
| `ARBICORE_RUNTIME_AUTOSTART` | `false` | PASS |
| Legacy b7/h05/w1 | exited / not running | PASS |
| `sendRawTransaction` 10m | **0** | Useful check PASS |
| `sendRawTransaction` 60m | **0** | Useful check PASS |
| Sign/broadcast-ish log hits 10m | **0** | Useful check PASS |

**Limitation:** A quiet 10–60 minute log window is **not** proof that all signing code paths are unreachable—only that no sendRaw/broadcast activity was observed under current SHADOW + autostart-false controls. Scanner remains `true` (unchanged; not a signing enablement).

---

## 4. Remaining security findings — **FAIL** (reconciled live)

| Finding | Live status | Verdict |
|---|---|---|
| Alchemy key rotation + RPC/log redaction | `log_redaction.py` **absent** (0 files). 60m logs: **2059** `alchemy.com/v2/…` hits; redacted markers **0**. Dominant log fp8 `24dab5d1` (1614). ENV bootstrap RPC fp8 `5e5d5bb1`. Mongo `network` config still holds Alchemy URL fps `124bc59c`, `24dab5d1`, `6e67e161`, `cd505118`, `dc432a6b`, `e315c86f`. Keys not rotated/revoked in this environment. | **FAIL** |
| MongoDB root / least privilege | App `MONGO_URL` user **`root`** (`authSource=admin`). `admin` users: only `root`. `arbicore_x` DB-scoped users: **0**. | **FAIL** |
| Bootstrap token + public `/docs` | `ARBICORE_BOOTSTRAP_TOKEN` present (len 64, sha12 `d5a682fbe887`). Local `127.0.0.1:8001/docs` and `/openapi.json` → **200**. Public `https://144-91-78-175.sslip.io/docs` and `/openapi.json` → **200** (Caddy proxies `/api/*` only for API; docs still reachable on backend via host routing / direct). | **FAIL** |
| Deployer private key / wallet migration | `contracts/.env` still has `DEPLOYER_PRIVATE_KEY` (len 64, sha12 `7e792fd2e48f`) → derived address **`0x3b37a5E124b177fEE30365deb295A5CCF76841Cd`**. Address file `.deployer_address.txt` shows different address `0x65af…2003` (inconsistency). Foundry keystore `~/.foundry/keystores/arbicore-base-mainnet-deployer` present (mode `600`). On-chain balance/migration need: **UNKNOWN** (not queried this pass). Not in backend container ENV. | **FAIL** / balance **UNKNOWN** |
| Plaintext admin / JWT copies | Live ENV: `ARBICORE_ADMIN_USER=admin`; admin pass present len 36 sha12 `6757aa3396d8`; JWT sha12 `066b178751e1`. Still plaintext in container ENV + active `.env`. Legacy (stopped) still has **pre-rotation** admin/JWT sha12s `6780d7b21193` / `7013ef842946`. | **FAIL** (rotated once, still ENV-plaintext; legacy copies remain in stopped config) |

---

## Remaining old-key locations (authoritative list)

**Approved recovery (retain):**

1. `/home/raghu/arbicore_backups/s1b_vault_key_escrow_20261009T053628Z/` (encrypted)  
2. `/home/raghu/arbicore_backups/s1b_phase2_rotation_20261009T102445Z/backend.env.pre-rotation`  
3. `/home/raghu/arbicore_backups/s1b_phase2_rotation_20261009T102445Z/root.env.pre-rotation`  
4. Pre-rotation dumps under `/home/raghu/arbicore_backups/s1b_phase2_readiness_20261009T053628Z/` (old **ciphertext**, not old key)

**Residual exposure (legacy — keep stopped):**

5. `docker:arbicore-x-b7-candidate:Config.Env`  
6. `docker:arbicore-x-backend-h05:Config.Env`  
7. `docker:arbicore-x-backend-w1:Config.Env`  

**Active path:** new key only (`fb5ca619211e`).

---

## Unresolved risks (ordered)

1. **Alchemy keys in logs + Mongo config** — active credential leakage; no redaction in running image.  
2. **Mongo application uses `root`** — shared `factory-mongo`.  
3. **Public OpenAPI/docs + bootstrap token** — unauthenticated API surface documentation; bootstrap material still live.  
4. **Deployer private key on disk** — `0x3b37…41Cd`; migration/balance unresolved.  
5. **Admin/JWT plaintext in ENV** — usable if host/container env is read; legacy stopped configs still hold older hashes.  
6. **Legacy containers retain old vault key** — safe only while exited.  
7. **No off-host DR copy** of vault backups/escrow.

---

## Evidence index

- This file: `S1B_POST_ROTATION_VERIFICATION.md`  
- Claim under test: `S1B_PHASE2_COMPLETION.md`  
- `post_rotation_oldkey_inventory.json`  
- Prior: `recovery_drill_result.json`, `post_swap_verify.json`, `old_key_scrub.json`, `offhost_status.json`

---

## Safety confirmation (audit end state)

- No configuration changed; no containers started/stopped/recreated by this audit  
- Legacy remain **stopped**; execution **SHADOW**; AUTOEXEC/runtime **false**  
- P2 **not** deployed  
- Independent conclusion: vault rotation claim **holds**; overall P2 security gate **BLOCKED**
