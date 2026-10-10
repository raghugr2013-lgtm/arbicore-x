# S1-B — Phase 2 readiness: backup and recovery gate

**Status:** Backup/recovery prerequisites **READY** — Phase 2 **executed** under separate authorisation; see `S1B_PHASE2_COMPLETION.md`  
**P2:** still **BLOCKED** — not built or deployed by this task  
**G1.6:** closed with documented limitations — **not reopened**  
**Window (UTC):** backup `2026-10-09T05:36:28Z` → restore re-verify / posture / crypto dry-run `2026-10-09T09:54:31Z`  
**Mode (this readiness document):** pre-mutation gate only. Mutation results are recorded in `S1B_PHASE2_COMPLETION.md`.

Secrets are referenced only as `sha256[:12]` fingerprints / lengths / public addresses. **No key or ciphertext values are reproduced.**

---

## Executive verdict

| Gate | Result |
|---|---|
| Fresh consistent backup of `arbicore_secrets` | **PASS** |
| Full `arbicore_x` backup (operational) | **PASS** |
| Isolated restore verification (scratch DB only) | **PASS** (re-verified) |
| Old `VAULT_KEY` escrow (encrypted, restricted) | **PASS** (round-trip hash only) |
| Encrypt / decrypt / re-encrypt procedure confirmed | **PASS** (throwaway key; production unchanged) |
| Signing-wallet address integrity | **PASS** (`0x0a43F432…Fa89`) |
| Legacy stopped; SHADOW; AUTOEXEC/runtime false; no sendRaw | **PASS** |
| Phase 2 mutation (new key / rewrite / recreate) | **NOT STARTED** — needs written approval below |
| P2 deploy | **NOT STARTED** |

**Overall:** Recovery prerequisites for a separately authorised vault rotation are in place. **Do not begin Phase 2 until the approvals in §8 are granted in writing.**

---

## 1. MongoDB deployment verification (no credentials exposed)

| Fact | Value |
|---|---|
| Authoritative Mongo container | `factory-mongo` (`mongo:7` / 7.0.39), healthy, started `2026-09-07T05:21:43Z` |
| Networks | `strategy-factory-canonical_default`, `vqb-network` |
| Host port | **not** published on host `27017` (container-network only) |
| Production database | `arbicore_x` (`DB_NAME` from `arbicore-x-backend-new`) |
| App URI shape (redacted) | `mongodb://***@factory-mongo:27017/?authSource=admin` |
| Auth model | Root user on `admin`; app still uses root (known residual risk; not rotated here) |
| Collections at backup time | **62** |
| `arbicore_secrets` live count | **1** |
| `api_keys` encrypted rows | **0** |
| Free disk (`/`) | **45G** available (82% used) — sufficient for ~441 MB full archive + scratch restore |
| Backup destination | `/home/raghu/arbicore_backups/s1b_phase2_readiness_20261009T053628Z/` (mode `700`) |
| Access controls | Owner `raghu`; archives/evidence mode `600`; not under `/tmp`; outside git trees |
| Dump procedure | Authenticated `mongodump --archive --gzip` via URI piped into `factory-mongo` (URI never printed); matches upgrade-toolkit `mongo_dump` pattern |
| Existing upgrade archives | **Untouched** — Sep‑14 pointer `preupgrade_arbicore_x_20260914T091112Z.archive.gz` still `64840467` bytes, mtime `2026-09-14`, mode `664`; `.last_backup` not modified |

Non-authoritative Mongo (`arbicore-x-mongo` Created / validators) was **not** used.

---

## 2. Fresh backups produced

Directory: `/home/raghu/arbicore_backups/s1b_phase2_readiness_20261009T053628Z/` (`drwx------`)

| Artifact | Size | Mode | SHA-256 |
|---|---|---|---|
| `arbicore_secrets_20261009T053628Z.archive.gz` | 783 B | `600` | `ffbdd32297d5a7fa317c982f77bba3a6b18a0b3af7b0ae05ddc337ff0f13b1e5` |
| `arbicore_x_full_20261009T053628Z.archive.gz` | 462 049 198 B (~441 MB) | `600` | `d229bf5e7a2b491e398a6d9f2ea4c6fe7c5e4765c92b841abeff518974e5015b` |
| `SHA256SUMS` | — | `600` | (lists both archives) |
| `live_baseline.json` | — | `600` | live metadata at dump time |

Dump log highlights:

- Secrets dump: **1 document** (`arbicore_x.arbicore_secrets`)
- Full dump: includes all 62 collections (e.g. `arbicore_discovery_candidates` 3 921 188 docs; `evidence_bundles` 583 481; `decision_history` 726 708)

Baseline secret metadata (hash-only):

| Field | Value |
|---|---|
| `handle_id` | `sec-3cec159e23d7495ab89140e5452a3d67` |
| `scope` / `algorithm` / `provider` | `evm_sign` / `eth_privkey` / `fernet_local` |
| `label` / `execution_role` | `arbicore-executor-owner` / `signer` |
| `derived_address` | `0x0a43F432681cA5eE053D53B79Ae1648FDAaBFa89` |
| `cipher_len` / `cipher_sha12` / prefix | 184 / `660386c2e939` / `gAAA` |
| Fields preserved | `algorithm`, `cipher`, `created_at`, `derived_address`, `execution_role`, `handle_id`, `label`, `provider`, `scope` |
| Live `VAULT_KEY` sha12 | `a46000441419` (len 44) |

---

## 3. Restore verification (scratch only — production never overwritten)

### Method (corrected archive / credential handling)

1. `docker cp` archive into `factory-mongo:/tmp/…`
2. Pipe **only** `MONGO_URL` on stdin into `mongorestore --uri=… --archive=/tmp/…` (do **not** mix archive bytes with the URI on the same stdin — that failure mode was observed once and corrected)
3. Remap namespace to a disposable DB: `--nsFrom='arbicore_x.arbicore_secrets' --nsTo='<scratch>.arbicore_secrets'`
4. Compare non-sensitive integrity fields + `cipher_sha12` vs live
5. `drop_database(scratch)`; remove temp archive inside mongo
6. Confirm production `arbicore_secrets` still count=1 and `cipher_sha12=660386c2e939`

### Results

| Test | Scratch DB | Result |
|---|---|---|
| Secrets archive → scratch | `arbicore_s1b_restore_verify_20261009T053628Z` | **1/1 restored**; live↔restored **match** |
| Full archive secrets slice → scratch | `arbicore_s1b_fullslice_verify_20261009T053628Z` | **1/1**; `fullslice_match=true` |
| Re-verify secrets archive (this continuation) | `arbicore_s1b_restore_reverify_20261009T053628Z` | **match=true**, readable, prod untouched |
| `gzip -t` + `sha256sum -c SHA256SUMS` | — | **OK** |

Evidence files: `restore_compare.json`, `restore_secrets_verify.log`, `restore_fullslice_verify.log`, `restore_reverify.log` (under backup dir + selected copies in this artifact directory).

**Verdict:** Backup integrity **VERIFIED**. Gate is **not BLOCKED**.

### How restoration would work (operator procedure — do not run against prod without separate approval)

**A. Vault-only recovery (preferred for rotation rollback)**

```bash
TS=20261009T053628Z
BK=/home/raghu/arbicore_backups/s1b_phase2_readiness_${TS}
# Copy archive in, then restore with explicit ns remap OR replace collection only after approval:
docker cp "$BK/arbicore_secrets_${TS}.archive.gz" factory-mongo:/tmp/restore_secrets.archive.gz
docker exec arbicore-x-backend-new printenv MONGO_URL | docker exec -i factory-mongo sh -c '
  IFS= read -r mongo_url
  # EXAMPLE scratch (safe):
  mongorestore --uri="$mongo_url" --gzip --archive=/tmp/restore_secrets.archive.gz \
    --nsFrom="arbicore_x.arbicore_secrets" --nsTo="arbicore_restore_scratch.arbicore_secrets" --drop
  # PRODUCTION replace requires explicit written approval — not authorised by this document.
'
```

After a failed Phase‑2 ciphertext rewrite: restore prior `cipher` from this archive (or from full dump slice) **and** keep/load escrowed old `VAULT_KEY` until decrypt + address checks pass.

**B. Full DB disaster recovery**

Use `arbicore_x_full_${TS}.archive.gz` with `mongorestore --gzip --archive=…` into a **scratch** DB first (`--nsFrom='arbicore_x.*' --nsTo='arbicore_dr_scratch.*'`), verify counts, then only under separate change control restore into `arbicore_x` (destructive). This readiness gate does **not** authorise production overwrite.

---

## 4. Old vault-key escrow

| Item | Value |
|---|---|
| Directory | `/home/raghu/arbicore_backups/s1b_vault_key_escrow_20261009T053628Z/` |
| Dir mode | `700` |
| `VAULT_KEY.old.enc` | AES-256-CBC + PBKDF2 (200 000 iter), mode `600` |
| `wrap.pass` | wrapping passphrase, mode `600` |
| `README_ACCESS.txt` | unwrap instructions; mode `600` |
| Escrowed key sha12 | `a46000441419` |
| Enc file sha256 | `53dbf3a94bcba0a4f697cdcfee6b456c5c0994b5c615c53fe2a2b74de07da03d` |
| Round-trip check | decrypt → sha12 equals live container `VAULT_KEY` sha12 — **OK** |
| Plaintext in reports/logs | **None** |

Recoverability without exposure: operator unwraps locally per `README_ACCESS.txt`; compare `sha256[:12]` only before use. Do not paste key into chat, tickets, git, or `/tmp`.

---

## 5. Encryption / decryption / re-encryption procedure (confirmed; not executed on prod)

**Format:** Fernet (`cryptography.fernet`) via `VAULT_KEY`; provider `fernet_local`; collection `arbicore_secrets`.  
**Code paths:** `FernetSecretBackend` (`app/backend/arbicore/secrets/backends.py`); signer ingest/resolve (`signer_vault.py`).  
**No built-in master-key rotate API** — Phase 2 remains a controlled offline/operator procedure.

**Confirmed dry-run (throwaway key, not stored):**

| Check | Result |
|---|---|
| Decrypt with current key | OK; plaintext_len=64; plaintext_sha12 `b4ce2e6143a2`; looks_64hex |
| Address derive (`Account.from_key`, no sign/broadcast) | `0x0a43F432681cA5eE053D53B79Ae1648FDAaBFa89` |
| Matches `derived_address` on doc | **true** |
| Re-encrypt under throwaway Fernet key → decrypt | roundtrip OK; plaintext sha unchanged |
| Production `cipher_sha12` after dry-run | still `660386c2e939` |
| All secret fields listed for preservation | see §2 field list — none may be dropped on rewrite |

**Authorised Phase‑2 mutation sequence (NOT run):**

1. Freeze posture (legacy stopped; SHADOW; AUTOEXEC/runtime false).  
2. Confirm this backup + escrow still present.  
3. Generate **new** Fernet key (`Fernet.generate_key()`); never reuse `a46000441419`.  
4. For each `arbicore_secrets` doc: decrypt with old → encrypt with new → verify plaintext_sha12 + derived address → write new `cipher` (preserve every non-cipher field).  
5. Update compose-backed backend `.env` `VAULT_KEY` only after ciphertext verify.  
6. Backend-only recreate on **current** image digest to load env (not P2).  
7. Post-swap: count=1; decrypt OK; address unchanged; no sendRaw; legacy still stopped.  
8. Recovery drill from this backup + escrow on scratch; only then scrub old key copies.

`api_keys` has **0** rows — no second collection to migrate.

---

## 6. Rollback / recovery drill (no signing, no broadcast)

**Drill already performed (safe):**

1. Restore secrets archive → scratch → metadata/`cipher_sha12` match → drop scratch.  
2. Restore secrets slice from full archive → match → drop scratch.  
3. Escrow unwrap → sha12 match live (no plaintext echoed).  
4. Decrypt + address derive dry-run in process memory only; no `sendRawTransaction`; mode remains SHADOW.

**Drill to run immediately before / during Phase 2 (still no LIVE):**

| Step | Action | Pass criteria |
|---|---|---|
| R1 | Confirm backup `SHA256SUMS` and escrow dir modes | checksums OK; `700`/`600` |
| R2 | Scratch-restore secrets archive again | count=1; sha12/`derived_address` match live pre-change snapshot |
| R3 | After any failed rewrite: restore old cipher from backup into **scratch**, decrypt with escrowed old key, address match | OK without touching prod first |
| R4 | Only if prod rewrite failed: restore cipher into `arbicore_x` under change control + keep old key loaded | handle/address/sha checks; still SHADOW; sendRaw=0 |
| R5 | Never enable AUTOEXEC, RUNTIME autostart, or LIVE during drill | env gates remain false / SHADOW |

---

## 7. Runtime posture (re-checked)

| Control | Value |
|---|---|
| `arbicore-x-backend-new` | running, healthy; image `arbicore-x-backend:hybrid-e-rpc-9244ebd`; ImageID `sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52` |
| `ARBICORE_EXECUTION_MODE` | `SHADOW` |
| `ARBICORE_AUTOEXEC_AUTOSTART` | `false` |
| `ARBICORE_RUNTIME_AUTOSTART` | `false` |
| `ARBICORE_SCANNER_AUTOSTART` | `true` (unchanged; not disabled by this task) |
| `sendRawTransaction` (60m logs) | **0** |
| `arbicore-x-b7-candidate` / `h05` / `w1` | **exited** (must remain stopped) |
| `arbicore-g5-79-app` | running on isolated `arbicore_g579_test` (no prod vault key) |
| Production ciphertext / active ENV | **unchanged** by this task |
| P2 / collectors / Base tracker / frozen exports / live ledger | **not modified** |

---

## 8. Approvals required before Phase 2 mutations

Phase 2 remains **blocked** until you approve **in writing**, as a separate message from this readiness note, **all** of:

1. **Generate** a new Fernet `VAULT_KEY` (not reuse of `a46000441419` / historic hashes).  
2. **Rewrite** production `arbicore_x.arbicore_secrets.cipher` under the procedure in §5 (preserving all fields; verify address `0x0a43F432…Fa89`).  
3. **Update** active backend env files that feed `arbicore-x-backend-new` with the new `VAULT_KEY`.  
4. **Backend-only recreate** of `arbicore-x-backend-new` on the **current** image digest `sha256:40b2116b…` solely to load the new key (**not** a P2 deploy, not a new image build).  
5. Acknowledgement that recovery anchors are this readiness backup + escrow dirs above; scrub of old key from env/backups/`/tmp` only **after** post-swap verify + recovery drill pass.

**Not requested / not approved by this document:**

- P2 build or deploy  
- Alchemy / admin / JWT / Mongo / wallet credential rotation  
- Legacy container start or removal  
- LIVE / signing / AUTOEXEC / runtime autostart enablement  
- Overwriting the Sep‑14 upgrade archive or production DB wholesale outside the vault rewrite scope  

---

## 9. Unresolved risks (outside this gate’s fixes)

1. Old `VAULT_KEY` sha12 `a46000441419` still present in live env, stopped legacy `Config.Env`, many `.env*` backups, and `/tmp` dumps — escrow does not remove exposure; Phase 2 + scrub still required.  
2. Live `evm_sign` material remains decryptable under that shared key until rotation completes.  
3. Mongo app still uses `root` on shared `factory-mongo`.  
4. Alchemy log redaction / key rotation and other `SECURITY_REMEDIATION_STATUS.md` FAILs remain open (separate workstreams).  
5. Escrow + backups live on the same host disk (45G free) — off-host copy is recommended before Phase 2 but was not performed here.  
6. Full-archive restore of all 62 collections was **not** loaded end-to-end into scratch (size/time); secrets path was fully verified from both archives; full DR should be rehearse-restored to scratch under a maintenance window if required before destructive DB recovery.

---

## 10. Evidence index

**This directory (`artifacts/security/s1b_vault_rotation_preflight_20261009/`):**

- `S1B_PHASE1_PREFLIGHT.md` (prior; unchanged intent)  
- `S1B_PHASE2_READINESS.md` (this file)  
- `live_baseline_pre_backup.json`, `restore_compare.json`, `restore_reverify.log`  
- `vault_key_escrow_meta.json`, `crypto_dryrun.json`, `posture_recheck.json`  
- Prior Phase‑1 JSON inventories (`containers_posture.json`, `vault_*`, `backup_inventory.json`)

**Restricted host paths (not in git):**

- `/home/raghu/arbicore_backups/s1b_phase2_readiness_20261009T053628Z/`  
- `/home/raghu/arbicore_backups/s1b_vault_key_escrow_20261009T053628Z/`

---

## 11. Safety confirmation

- Legacy b7 / h05 / w1: **stopped**  
- Execution: **SHADOW**; AUTOEXEC / runtime autostart: **false**  
- Signing/broadcast (60m): **none**  
- New vault key: **not generated**  
- Production ciphertext / ENV / backend: **unchanged**  
- P2: **not deployed**  
- Waiting for **explicit approval** before any Phase 2 mutation
