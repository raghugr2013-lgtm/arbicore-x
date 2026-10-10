# S2-A Alchemy rotation — PREPARE ONLY (no cutover)

**Status:** `WAITING_FOR_STAGING`  
**Authority:** Operator approved preparation only; cutover blocked until explicit confirmation that `/tmp/s2a_alchemy_replacements.env` is securely staged.  
**Mutations this stage:** **NONE** (Mongo, `.env`, Compose, keys, containers unchanged).

---

## Safety controls (must hold through cutover)

| Control | Required |
|---|---|
| Execution mode | SHADOW |
| AUTOEXEC | false |
| RUNTIME autostart | false |
| Signing / broadcast | disabled |
| Legacy b7 / h05 / w1 | stopped |
| Image | S2-A `arbicore-x-backend:s2a-rpc-redact-5bd952568aed` @ `sha256:69fe2459…` |
| g5.79 (`a7961b2b`) | **OUT OF SCOPE** — do not change or revoke |
| P2 / vault / live trading | not in scope |
| Revocation | **forbidden** until separate post-evidence authorisation |

---

## Staging contract (operator) — REVISED

Six ArbiCore-x-2 endpoints = **chain primaries**, not `PRIMARY`+`FALLBACK_1..5`.  
Full secret-free template: `S2A_ALCHEMY_STAGING_TEMPLATE.md`.

| Item | Value |
|---|---|
| Path | `/tmp/s2a_alchemy_replacements.env` |
| Mode | `0600` |
| Confirm in chat | `"staged"` only — **never** paste keys |
| Required keys | `PRIMARY_ETHEREUM`, `PRIMARY_ARBITRUM`, `PRIMARY_BASE`, `PRIMARY_OPTIMISM`, `PRIMARY_POLYGON`, `PRIMARY_BNB` |
| Fallback policy | `FALLBACK_POLICY=retain_existing` (Mongo `[1..5]` unchanged this cutover) |
| Optional | `BOOTSTRAP_BASE`, `ARCHIVE_BASE` (default to `PRIMARY_BASE`) |

---

## Exact change set (AFTER staging confirmation + fp validation — NOT NOW)

| Target | Action |
|---|---|
| Mongo `arbicore_x.arbicore_config` `_id=network` | Replace `rpc_urls` `[0..5]` for `base,ethereum,arbitrum,optimism,polygon,bnb` with new role keys; hosts unchanged |
| `deployment/upgrade/backend/.env` | Replace Alchemy URLs currently fp `5e5d5bb1` (global RPC, archive, eth/arb/op/poly/bnb); keep Base public host unless file says otherwise |
| Compose / image | No change — stay on S2-A override |
| Runtime | Backend-only recreate to reload `.env` + `env_sync` → `PROVIDER_RPC_URLS_*` |
| g5.79 | Unchanged |

**Affected service:** `arbicore-x-backend-new` only.  
**Expected downtime:** ~30–90s recreate.

### Old fps to replace (prod)

| Role | fp8 |
|---|---|
| Primary (all chains `[0]`) | `24dab5d1` |
| Fallbacks `[1..5]` | `e315c86f`, `dc432a6b`, `6e67e161`, `cd505118`, `124bc59c` |
| ENV bootstrap / archive | `5e5d5bb1` |

Reject staged file if it reuses any of the above, or `ce00e63d`, or `a7961b2b`.

---

## Recovery (if cutover fails — before any revoke)

1. Restore Mongo network doc from pre-cutover backup.  
2. Restore `.env` from pre-cutover `0600` backup under `/home/raghu/arbicore_backups/`.  
3. Recreate backend on **same** S2-A image + `/tmp/arbicore-s2a-rpc-redact-override.yml`.  
4. Fingerprint-verify old fps restored; health green.  
5. **Do not** roll back to Hybrid-E `40b2116b…` for key failures (log re-exposure risk).

---

## Evidence required after future cutover (before revoke)

1. fps-only old→new map artifact  
2. Six-chain RPC health + Mongo fingerprint proof  
3. Fallback registration (six providers/chain after `env_sync`)  
4. Full **60-minute** clean-log window: 0 unredacted URLs; no unexplained 401/403; 429/5xx/failover vs `rotation_preflight_log_baseline_60m.json`  
5. `S2A_ALCHEMY_ROTATION_EXECUTION_REPORT.md` with **REVOKE-READY** or **BLOCKED**

---

## Current stop line

**No cutover. No key rotation. No revocation.**  
Waiting for operator confirmation that `/tmp/s2a_alchemy_replacements.env` is staged.
