# S2-A — Final cutover review (READ-ONLY)

**Verdict: GO — AWAITING EXPLICIT CUTOVER AUTHORISATION**  
**Review UTC:** `2026-10-10` (session)  
**Mutations this review:** **NONE** · Revocation: **NOT AUTHORISED**

Staging validation: **PASS** (`rotation_staging_validation.json`).  
Staged file still present: `/tmp/s2a_alchemy_replacements.env` · `raghu` · `0600` · `FALLBACK_POLICY=retain_existing` · credentials **NEW** vs known old/g5.79 set.

---

## 1. Current production posture (confirmed)

| Control | Value |
|---|---|
| Container | `arbicore-x-backend-new` healthy |
| Image | `arbicore-x-backend:s2a-rpc-redact-5bd952568aed` |
| Digest | `sha256:69fe2459e0021bbd3a90b7e4cda617cbeb45a8b41861f9ed0f6b8df8e7315313` |
| Execution | **SHADOW** |
| AUTOEXEC | **false** |
| RUNTIME | **false** |
| Signing / broadcast | remain disabled (unchanged by this change set) |
| Legacy b7 / h05 / w1 | **exited** |
| g5.79 | **OUT OF SCOPE** (fp `a7961b2b` untouched) |
| S2-A / Hybrid-E overrides | present under `/tmp/` |

---

## 2. Exact MongoDB change set

**Document:** `arbicore_x.arbicore_config` · `_id=network`  
**Current revision:** `rev-37e7b2123cda4d658fc7f5daf7ceaa81` · `updated_at=2026-10-08T05:09:17Z` · `updated_by=admin`

### `rpc_urls[0]` only (six chains) — REPLACE

| Chain | Current `[0]` host | Current `[0]` fp | Becomes |
|---|---|---|---|
| ethereum | `eth-mainnet.g.alchemy.com` | `24dab5d1` | staged `PRIMARY_ETHEREUM` (same host, **new** key identity) |
| arbitrum | `arb-mainnet.g.alchemy.com` | `24dab5d1` | `PRIMARY_ARBITRUM` |
| base | `base-mainnet.g.alchemy.com` | `24dab5d1` | `PRIMARY_BASE` |
| optimism | `opt-mainnet.g.alchemy.com` | `24dab5d1` | `PRIMARY_OPTIMISM` |
| polygon | `polygon-mainnet.g.alchemy.com` | `24dab5d1` | `PRIMARY_POLYGON` |
| bnb | `bnb-mainnet.g.alchemy.com` | `24dab5d1` | `PRIMARY_BNB` |

### `rpc_urls[1]`–`[5]` — UNCHANGED (explicit)

| Index | fp (all six chains) | Action |
|---:|---|---|
| 1 | `e315c86f` | **retain** |
| 2 | `dc432a6b` | **retain** |
| 3 | `6e67e161` | **retain** |
| 4 | `cd505118` | **retain** |
| 5 | `124bc59c` | **retain** |

`FALLBACK_POLICY=retain_existing` **forbids** mutating or revoking these fallback slots/keys in this cutover.

Non-RPC network fields (`executor_addresses`, `gas_settings`, `chains_enabled`, etc.): **untouched**.

---

## 3. `.env` / bootstrap handling

File: `deployment/upgrade/backend/.env`

| Variable | Current | Cutover action |
|---|---|---|
| `ARBICORE_RPC_URL` | Alchemy Base host · fp `5e5d5bb1` | → `PRIMARY_BASE` (no `BOOTSTRAP_BASE` staged) |
| `ARBICORE_ARCHIVE_RPC_URL` | Alchemy Base · fp `5e5d5bb1` | → `PRIMARY_BASE` (no `ARCHIVE_BASE` staged) |
| `ARBICORE_RPC_URL_ETHEREUM` | fp `5e5d5bb1` | → `PRIMARY_ETHEREUM` |
| `ARBICORE_RPC_URL_ARBITRUM` | fp `5e5d5bb1` | → `PRIMARY_ARBITRUM` |
| `ARBICORE_RPC_URL_OPTIMISM` | fp `5e5d5bb1` | → `PRIMARY_OPTIMISM` |
| `ARBICORE_RPC_URL_POLYGON` | fp `5e5d5bb1` | → `PRIMARY_POLYGON` |
| `ARBICORE_RPC_URL_BNB` | fp `5e5d5bb1` | → `PRIMARY_BNB` |
| `ARBICORE_RPC_URL_BASE` | `mainnet.base.org` (public) | **leave unchanged** |
| `ALCHEMY_API_KEY` | empty | unchanged |

Compose image/tag: **unchanged** (stay on S2-A override).

---

## 4. Backup and restore (to run only after cutover auth)

### Backup (before writes)

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
BK=/home/raghu/arbicore_backups/s2a_alchemy_cutover_${TS}
mkdir -p "$BK" && chmod 700 "$BK"
cp -a /home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env "$BK/backend.env.pre-cutover"
chmod 600 "$BK/backend.env.pre-cutover"
# Mongo network doc via backend (fps-only summary also saved to artifacts)
docker exec -w /app -e PYTHONPATH=/app arbicore-x-backend-new python - <<'PY'
# export network doc to stdout as JSON for operator-held backup path — run under cutover auth only
PY
```

Practical backup under cutover auth (secret-bearing, mode 0600 under `$BK` only — never commit):

1. Copy `.env` → `$BK/backend.env.pre-cutover` (`0600`).  
2. Dump Mongo `arbicore_config` `_id=network` to `$BK/network.pre-cutover.json` (`0600`) via authenticated `mongodump`/`mongoexport` or backend one-shot writer into `$BK`.  
3. Record current digest + controls in `$BK/posture.txt`.

### Restore (if cutover fails — before any revoke)

```bash
# 1) Restore .env
cp -a "$BK/backend.env.pre-cutover" /home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env
chmod 600 /home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env
# 2) Restore Mongo network document from $BK/network.pre-cutover.json
# 3) Recreate on SAME S2-A image (do NOT use Hybrid-E for key rollback)
cd /home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose
docker compose -f docker-compose.prod.yml -f /tmp/arbicore-s2a-rpc-redact-override.yml \
  up -d --no-deps --force-recreate backend
# 4) Verify health + SHADOW flags + Mongo [0] fps restored to 24dab5d1; [1..5] unchanged
```

**Do not** recreate onto Hybrid-E `40b2116b…` solely to undo keys (re-exposes URLs in logs).

---

## 5. Runtime refresh and expected downtime

| Step | Detail |
|---|---|
| Refresh method | Backend-only recreate with `/tmp/arbicore-s2a-rpc-redact-override.yml` (reloads `.env` + startup `env_sync`) |
| Expected downtime | **~30–90 seconds** (health flap only) |
| Affected | `arbicore-x-backend-new` only |
| After `env_sync` | Expect log: exported vars for all six chains; provider registry re-registers **6** Alchemy endpoints per chain (`[0]`=new primary identity, `[1..5]`=retained fallback fps) |

---

## 6. Post-cutover verification (secret-free)

### Per-chain health

For each of `ethereum`, `arbitrum`, `base`, `optimism`, `polygon`, `bnb`:

1. Fingerprint probe: Mongo `[0]` ≠ `24dab5d1` and is the new identity; `[1..5]` fps **identical** to pre-cutover.  
2. RPC: `eth_blockNumber` (or existing health/check path) succeeds — not HTTP 401/403.  
3. Controls still SHADOW / AUTOEXEC=false / RUNTIME=false; digest still `69fe2459…`.

### Provider registration

Startup/recreate logs must show six `rpc_<chain>_*_*.g.alchemy.com` (or truncated host) registrations per chain after `env_sync`.

### 60-minute acceptance gates

Compare to `rotation_preflight_log_baseline_60m.json`:

| Gate | Pass |
|---|---|
| Unredacted `alchemy.com/v2/<token>` | **0** |
| `/v2/[REDACTED]` under traffic | present |
| Unexplained httpx 401/403 | none / no storm |
| 429 / 5xx / failover keywords | inspect vs baseline; no unexplained sustained regression |
| Chain health at T+60m | still OK |

Any fail → **stop** → restore procedure → report **BLOCKED** (still no revoke).

---

## 7. Explicit non-goals this cutover

- Mongo fallback slots `[1]`–`[5]`: **unchanged**  
- Fallback key revocation: **forbidden**  
- g5.79 / fp `a7961b2b`: **out of scope**  
- Old primary `24dab5d1` / ENV `5e5d5bb1` revoke: **only after** separate post-evidence authorisation  
- P2, vault, live trading, legacy starts: **forbidden**  
- Inventing credentials / printing URLs: **forbidden**

---

## 8. GO / BLOCKED checklist

| Prerequisite | Status |
|---|---|
| Staging validation PASS | **YES** |
| Staged file still 0600 / policy retain_existing / NEW credentials | **YES** |
| Mongo layout confirmed (6×6; `[0]=24dab5d1`; `[1..5]` known fallbacks) | **YES** |
| `.env` bootstrap targets identified | **YES** |
| S2-A image + override ready | **YES** |
| Safety controls green | **YES** |
| Backup/restore procedure documented | **YES** |
| Cutover executed | **NO** |
| Keys revoked | **NO** |

---

## Verdict

**GO — READY FOR EXPLICIT CUTOVER AUTHORISATION**

Production is unchanged. Fallbacks `[1]`–`[5]` will remain unchanged under `FALLBACK_POLICY=retain_existing`. g5.79 remains out of scope. SHADOW / AUTOEXEC=false / RUNTIME=false / signing-broadcast disabled / legacy stopped will be preserved.

**Stop.** No cutover until you explicitly authorise it.
