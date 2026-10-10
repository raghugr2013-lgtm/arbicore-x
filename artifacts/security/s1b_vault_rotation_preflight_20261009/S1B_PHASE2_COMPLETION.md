# S1-B — Phase 2 completion: vault-key rotation

**Status:** **COMPLETE** — all mandatory verification and recovery-drill checks passed  
**Authorisation:** operator explicit approval (controlled rotation per `S1B_PHASE2_READINESS.md`)  
**Completed (UTC):** `2026-10-09T10:44:42Z`  
**P2 deployment:** still **BLOCKED** — not authorised; not performed  

Secrets are referenced only as `sha256[:12]` fingerprints / lengths / public addresses. **No key or ciphertext values are reproduced.**

---

## Executive result

| Check | Result |
|---|---|
| Pre-mutation backup checksums | **PASS** |
| Old-key escrow round-trip | **PASS** (sha12 `a46000441419`) |
| Off-host recovery copy | **NOT FEASIBLE** (no rclone / no remote mounts) — local verified backup + escrow retained |
| Image digest unchanged | **PASS** `sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52` |
| New independent Fernet `VAULT_KEY` | **PASS** sha12 `fb5ca619211e` (≠ old) |
| `arbicore_secrets` re-encrypt (cipher only) | **PASS** |
| Decrypt + plaintext integrity + address | **PASS** |
| Backend recreate on same digest | **PASS** (healthy) |
| Recovery drill (pre-rotation archive + old escrow) | **PASS** |
| SHADOW / AUTOEXEC false / runtime false / legacy stopped / no sendRaw | **PASS** |
| Old recovery material retained | **YES** (escrow + pre-rotation env copies + readiness dumps) |

---

## Prerequisites (before mutation)

| Gate | Evidence |
|---|---|
| Backup `SHA256SUMS` | secrets `ffbdd322…b1e5` (783 B); full `d229bf5e…015b` (~441 MB); `sha256sum -c` OK |
| Escrow | `/home/raghu/arbicore_backups/s1b_vault_key_escrow_20261009T053628Z/` mode `700`; unwrap sha12 = live sha12 `a46000441419` |
| Off-host | Documented in `offhost_status.json` — not feasible on this host |
| Image / config | `arbicore-x-backend:hybrid-e-rpc-9244ebd` @ `sha256:40b2116b…`; compose `docker-compose.prod.yml` + `/tmp/arbicore-hybrid-e-rpc-9244ebd-override.yml` |
| Posture | Legacy b7/h05/w1 exited; `SHADOW`; AUTOEXEC/runtime `false`; `sendRawTransaction` 60m = 0 |

---

## Rotation outcomes (fingerprints only)

| Item | Before | After |
|---|---|---|
| `VAULT_KEY` sha12 | `a46000441419` | `fb5ca619211e` |
| `cipher` sha12 | `660386c2e939` | `45e7f15ca337` |
| plaintext sha12 | `b4ce2e6143a2` | `b4ce2e6143a2` (unchanged) |
| `derived_address` | `0x0a43F432681cA5eE053D53B79Ae1648FDAaBFa89` | **unchanged** |
| `handle_id` | `sec-3cec159e23d7495ab89140e5452a3d67` | unchanged |
| Non-cipher fields | preserved | **all preserved** (`algorithm`, `created_at`, `derived_address`, `execution_role`, `handle_id`, `label`, `provider`, `scope`) |
| Old key decrypts new cipher | — | **false** (expected) |

Active env updated (mode `600`):

- `/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env` (compose `env_file`)
- `/home/raghu/projects/arbicore-x-v2/.env` (aligned active copy)

Backend recreate: `docker compose … up -d --no-deps --force-recreate backend` — container healthy; ImageID **identical** to pre-rotation digest; **not** a P2 deploy.

---

## Container / execution posture (post)

| Control | Value |
|---|---|
| Container | `arbicore-x-backend-new` — running, **healthy** |
| Image | `arbicore-x-backend:hybrid-e-rpc-9244ebd` |
| Image digest | `sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52` |
| Live `VAULT_KEY` sha12 | `fb5ca619211e` |
| `ARBICORE_EXECUTION_MODE` | `SHADOW` |
| `ARBICORE_AUTOEXEC_AUTOSTART` | `false` |
| `ARBICORE_RUNTIME_AUTOSTART` | `false` |
| `sendRawTransaction` (10m post-recreate) | **0** |
| Legacy b7 / h05 / w1 | **exited** (still contain old key in `Config.Env`) |

---

## Recovery drill

1. Restored pre-rotation `arbicore_secrets_20261009T053628Z.archive.gz` into scratch DB `arbicore_s1b_recovery_drill_20261009T102445Z` (not production).  
2. Decrypted restored cipher (`660386c2e939`) with **old escrow** key sha12 `a46000441419`.  
3. Plaintext sha12 `b4ce2e6143a2`; address `0x0a43F432…Fa89` matched.  
4. Production cipher remained `45e7f15ca337` throughout; scratch dropped.

**Recovery anchors retained (do not delete yet without separate approval):**

- `/home/raghu/arbicore_backups/s1b_vault_key_escrow_20261009T053628Z/` (encrypted old key)  
- `/home/raghu/arbicore_backups/s1b_phase2_readiness_20261009T053628Z/` (pre-rotation dumps)  
- `/home/raghu/arbicore_backups/s1b_phase2_rotation_20261009T102445Z/` (pre-rotation env copies + encrypted new-key backup)

---

## Old-key residual locations

**Scrubbed (30):** historical v2 `.env*` backups and `/tmp/*env*` dumps — `VAULT_KEY=` replaced with `REDACTED_AFTER_S1B_PHASE2` (`old_key_scrub.json`). Active/tmp residual plaintext old assignments after scrub: **none**.

**Intentionally retained recovery material:**

- Escrow directory (encrypted old key + wrap pass)  
- Rotation workdir `backend.env.pre-rotation` / `root.env.pre-rotation`  
- Pre-rotation mongodumps (old ciphertext)

**Still containing old key until legacy removal (separate change control):**

- `docker:arbicore-x-b7-candidate:Config.Env`  
- `docker:arbicore-x-backend-h05:Config.Env`  
- `docker:arbicore-x-backend-w1:Config.Env`  

These containers remain **stopped**. Do not start them.

---

## Explicit non-actions

- P2 not deployed  
- No Alchemy / admin / JWT / Mongo / wallet rotations  
- No LIVE / signing / AUTOEXEC / runtime enablement  
- No legacy start  
- No unrelated collection modifications  
- Old escrow **not** deleted  

---

## Evidence index

Artifact dir: `artifacts/security/s1b_vault_rotation_preflight_20261009/`

- `S1B_PHASE2_READINESS.md` — prerequisites  
- `S1B_PHASE2_COMPLETION.md` — this report  
- `reencrypt_result.json`, `post_swap_verify.json`, `recovery_drill_result.json`  
- `remaining_key_locations.json`, `old_key_scrub.json`, `offhost_status.json`  
- `crypto_dryrun.json`, `posture_recheck.json` (pre-mutation baseline)

Restricted host work: `/home/raghu/arbicore_backups/s1b_phase2_rotation_20261009T102445Z/`

---

## Follow-ups (not part of this completion)

1. Remove or recreate stopped legacy containers to clear embedded old `VAULT_KEY` from `Config.Env`.  
2. Optional off-host copy of readiness dumps + escrow when remote storage is available.  
3. Separate authorisation required before any P2 deployment.  
4. Other open items in `SECURITY_REMEDIATION_STATUS.md` (Alchemy, Mongo least-privilege, etc.) remain outstanding.
