# S1-B — VAULT_KEY rotation Phase 1 preflight (READ-ONLY)

**Status:** Phase 1 complete — **STOP for human approval before Phase 2**  
**Verification window (UTC):** `2026-10-09T05:16:50Z` – `2026-10-09T05:19:30Z`  
**Mode:** Read-only. No key generation, no Mongo writes, no env edits, no container recreate, no P2 deploy.  
**Source of truth baseline:** `SECURITY_REMEDIATION_STATUS.md` (prior checks `2026-10-09T05:07–05:10Z`)

Secrets below are referenced only as `sha256[:12]` fingerprints / lengths. **No secret values are reproduced.**

---

## 1. Files and services inspected

| Area | Path / service | Finding |
|---|---|---|
| Production backend | `arbicore-x-backend-new` | Running, healthy; `VAULT_KEY` sha12 `a46000441419` (len 44) |
| Legacy backends | `arbicore-x-b7-candidate`, `arbicore-x-backend-h05`, `arbicore-x-backend-w1` | **Exited**; identical `VAULT_KEY` sha12 in `Config.Env` |
| Isolated test app | `arbicore-g5-79-app` | Running; **no** `VAULT_KEY` in env; `DB_NAME=arbicore_g579_test` |
| Vault MVP (CEX) | `app/backend/services/vault.py` | Fernet via `os.environ["VAULT_KEY"]`; collection `api_keys` |
| Vault EVM | `app/backend/arbicore/secrets/backends.py` `FernetSecretBackend` | Fernet via `VAULT_KEY`; collection `arbicore_secrets` |
| Registry | `app/backend/arbicore/secrets/registry.py` | `put` / `resolve` / `delete`; **no master-key re-encrypt** |
| Signer ingest | `app/backend/arbicore/execution/signer_vault.py` | Scope `evm_sign`; `resolve_signer_account` decrypts for signing |
| REST rotate | `POST .../execution/secrets/{id}/rotate` | Rotates **plaintext secret** supplied by operator — **not** `VAULT_KEY` |
| Live Mongo | `arbicore_x.arbicore_secrets` / `api_keys` / `wallet_registry` | See §3 |
| Env / backups | v2 tree, `/tmp`, legacy `.env*` | See §2 |
| Mongo archives | `deployment/upgrade/.state/backups/*.archive.gz` | Oldest usable pointer `20260914T091112Z` (~65 MB) |
| Compose | `docker-compose.prod.yml` `env_file` + override `/tmp/arbicore-hybrid-e-rpc-9244ebd-override.yml` | Override does **not** set `VAULT_KEY` (comes from compose env_file / backend `.env`) |

Evidence JSON in this directory:

- `containers_posture.json`
- `vault_key_locations.json` / `vault_key_location_summary.json`
- `vault_mongo_metadata.json`
- `backup_inventory.json`

---

## 2. Old `VAULT_KEY` locations (fingerprint inventory)

**Production fingerprint:** sha12 `a46000441419` (Fernet url-safe, len 44)

| Class | Count / notes |
|---|---|
| Live container env | `arbicore-x-backend-new` + three stopped legacy containers — **same sha12** |
| Active env files | `/home/raghu/projects/arbicore-x-v2/.env`, `.../deployment/upgrade/backend/.env` (mode `600`) |
| On-disk `.env*` backups with prod sha | **21** under v2 tree |
| `/tmp` env dumps with prod sha | **9** |
| Alternate historic sha `73c3f6b84882` | 3 paths (including `/home/raghu/projects/arbicore-x/.env`) — **not** current prod |
| Docs / examples | Placeholders or unrelated example hashes — not live material |

**Containment today:** legacy containers remain stopped; active exposure is production env + many readable backups/`/tmp` copies.

---

## 3. Encryption format and atomic re-encrypt feasibility

| Check | Result |
|---|---|
| Format | Fernet token (`gAAA…`), provider `fernet_local` |
| `arbicore_secrets` count | **1** |
| Live secret | `handle_id=sec-3cec159e23d7495ab89140e5452a3d67`, `scope=evm_sign`, `algorithm=eth_privkey`, `label=arbicore-executor-owner`, `derived_address=0x0a43F432…Fa89`, `execution_role=signer`, cipher_len=184, cipher_sha12 `660386c2e939` |
| Decrypt with current key | **OK** (plaintext_len=64, looks_64hex=true, plaintext_sha12 `b4ce2e6143a2` — hash only) |
| Re-encrypt dry-run (throwaway Fernet key, not stored) | **roundtrip_ok=true**, plaintext sha unchanged |
| `api_keys` encrypted rows | **0** — CEX vault empty; no second collection to migrate |
| Built-in `VAULT_KEY` rotate/re-encrypt utility | **ABSENT** — must be a controlled offline/operator procedure |

**Conclusion:** Decrypt → re-encrypt under a new independent Fernet key **without changing secret bytes** is cryptographically feasible for the single `evm_sign` row. There is **no** in-product atomic master-key rotation; Phase 2 must use a documented, recoverable procedure (backup ciphertext + old key, write new ciphertext, swap env, verify, only then scrub).

---

## 4. Restorable backup / recovery understanding

| Asset | Status |
|---|---|
| Latest mongodump pointer | `.last_backup` → `preupgrade_arbicore_x_20260914T091112Z.archive.gz` |
| Fresh pre-rotation dump of `arbicore_secrets` | **NOT present** (gap) |
| Recovery if new key lost after re-encrypt | Impossible without old key + old ciphertext (operator manual §13) |
| Recovery if re-encrypt fails mid-flight | Restore prior `cipher` from pre-change export + keep old `VAULT_KEY` |
| Legacy Config.Env copies of old key | Persist until containers are removed/recreated under separate approval — **do not start them** |

**Prerequisite gap (Phase 1 STOP item):** take a **fresh, access-restricted** backup of at least `arbicore_secrets` (and preferably full `arbicore_x`) **immediately before** Phase 2, plus an encrypted offline copy of the **old** `VAULT_KEY` retained until recovery is proven.

---

## 5. Live `evm_sign` consumers (no secret values)

Code paths that can obtain plaintext after decrypt:

1. `FernetSecretBackend.get` ← `SecretRegistry.resolve`
2. `signer_vault.resolve_signer_account` / `ensure_signer_address` (address backfill)
3. Broadcast / live execution path that resolves the isolated executor signer from `evm_sign` (gated by mode / kill switch / AUTOEXEC)
4. Readiness / wizard surfaces that check **presence** / `derived_address` without needing plaintext
5. REST `secrets/.../test` style resolve paths (operator-authenticated) — must remain unused during rotation

Gas wallet `0x998d…aad25` has `secret_handle_id=null` (not the vault signer).

**Runtime gates verified now:**

| Control | Value |
|---|---|
| `ARBICORE_EXECUTION_MODE` | `SHADOW` |
| `ARBICORE_AUTOEXEC_AUTOSTART` | `false` |
| `ARBICORE_RUNTIME_AUTOSTART` | `false` |
| `sendRawTransaction` (60m logs) | **0** |
| Legacy b7/h05/w1 | **exited** |

---

## 6. Precise Phase 2 rotation plan (NOT EXECUTED)

Proceed **only** after explicit human approval of this plan and recovery procedure.

1. **Freeze posture:** confirm legacy still stopped; SHADOW; AUTOEXEC/runtime false; no signing/broadcast.
2. **Fresh backup:** mongodump `arbicore_secrets` (+ recommended full DB); store archive mode `600`; record sha256 of archive; export current secret metadata (handle_id, cipher_sha12, derived_address) to evidence.
3. **Offline old-key escrow:** copy current `VAULT_KEY` to an encrypted, access-restricted recovery file (not `/tmp`, not git); record sha12 only in evidence.
4. **Generate new key:** `Fernet.generate_key()` (or equivalent CSPRNG); never reuse `a46000441419` / legacy hashes.
5. **Re-encrypt offline/in-process:** decrypt each `arbicore_secrets.cipher` with old key → encrypt with new key → write **new** field or staging doc first; validate decrypt with new key (compare plaintext_sha12 + derived_address via `Account.from_key` address-only); then atomically replace `cipher`.
6. **Update active config:** set new `VAULT_KEY` in the compose-backed backend `.env` files that feed `arbicore-x-backend-new` (**same image**, no P2). Requires an authorised backend recreate to reload env — **separate from P2**.
7. **Post-swap verify:** list handles count=1; decrypt OK; derived_address unchanged; no sendRaw; legacy still stopped.
8. **Recovery drill:** from the fresh pre-change backup + old-key escrow, prove restore of old ciphertext decrypts under old key (on a non-production scratch DB or dry-run), **then** scrub old key from active env and accessible backups/`/tmp`. Document immutable archives that still contain old key/ciphertext.
9. **Do not** destroy old vault material until step 8 passes.

### Explicit approval required before Phase 2

Please approve **in writing**, as a separate message from this preflight, all of:

1. Execution of Phase 2 steps 1–9 above (including generating a new `VAULT_KEY` and rewriting `arbicore_secrets.cipher`).
2. A **backend-only recreate** of `arbicore-x-backend-new` on the **current** image digest `sha256:40b2116b…` solely to load the new `VAULT_KEY` (not a P2 deploy).
3. Creation of a fresh mongodump / secret ciphertext backup immediately before rewrite.
4. Post-success scrub of old `VAULT_KEY` from listed active env files, backups, and `/tmp` copies (with documented exceptions).

**Not approved by this document:** P2 deployment, legacy start, LIVE/signing/AUTOEXEC enablement, wallet private-key rotation, Alchemy/Mongo/bootstrap rotations, fund movement.

---

## 7. Rotation status

| Item | Status |
|---|---|
| Phase 1 preflight | **COMPLETE** |
| New-key decrypt/re-encrypt verification (production) | **NOT DONE** (dry-run with throwaway key only) |
| Old-key scrub | **NOT DONE** |
| Recovery test | **NOT DONE** |
| Phase 2 | **BLOCKED pending explicit approval** |

### Blockers / uncertainties

1. No first-class master-key re-encrypt API — custom procedure required.  
2. Fresh restorable backup of current `arbicore_secrets` not yet taken.  
3. Loading a new `VAULT_KEY` into the running container requires env update + recreate (must not be conflated with P2).  
4. Legacy stopped containers still embed old key in `Config.Env` until removed under later change control.  
5. Many backup/`/tmp` copies — scrub plan must be explicit; some archives may be immutable.

---

## 8. Safety confirmation (end of Phase 1)

- Legacy b7 / h05 / w1: **stopped**  
- Execution mode: **SHADOW**; AUTOEXEC / runtime autostart: **false**  
- Signing/broadcast observed (60m): **none**  
- P2: **not deployed** as part of this task  
- Production vault ciphertext: **unchanged**
