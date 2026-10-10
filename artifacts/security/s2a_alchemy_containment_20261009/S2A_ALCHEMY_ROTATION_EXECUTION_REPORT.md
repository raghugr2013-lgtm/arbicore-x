# S2-A Alchemy primary cutover — execution report

**Verdict: PASS**  
**Revocation: NOT EXECUTED** (requires separate authorisation)  
**Report UTC:** `2026-10-10T08:23:57Z`

Authority: explicit primary-endpoint cutover auth following `S2A_ALCHEMY_CUTOVER_REVIEW.md`.  
Policy: `FALLBACK_POLICY=retain_existing` · g5.79 out of scope · no P2 · no live trading.

---

## 1. Cutover completion

| Field | Value |
|---|---|
| Backup dir | `/home/raghu/arbicore_backups/s2a_alchemy_cutover_20261010T065530Z` (verified) |
| Mongo + `.env` apply | `2026-10-10T06:58:04Z` · revision `rev-b968dd529509dea58183fe3de204fbcc` |
| Backend recreate started | `2026-10-10T06:58:13Z` |
| Backend recreate finished / healthy | `2026-10-10T06:58:48Z` |
| Image digest | `sha256:69fe2459e0021bbd3a90b7e4cda617cbeb45a8b41861f9ed0f6b8df8e7315313` (unchanged S2-A) |
| API | `/api/` → 200 |
| Health (at report) | **healthy** |

---

## 2. Six-chain health and primary fingerprints

Staged replacements resolve to a **single new** primary key identity across all six hosts.

| Chain | Primary health | Fallback[1] health | Primary fp8 | Old primary |
|---|---|---|---|---|
| ethereum | **PASS** (200) | PASS (200) | `ca6545ba` | was `24dab5d1` |
| arbitrum | **PASS** | PASS | `ca6545ba` | was `24dab5d1` |
| base | **PASS** | PASS | `ca6545ba` | was `24dab5d1` |
| optimism | **PASS** | PASS | `ca6545ba` | was `24dab5d1` |
| polygon | **PASS** | PASS | `ca6545ba` | was `24dab5d1` |
| bnb | **PASS** | PASS | `ca6545ba` | was `24dab5d1` |

Effective primaries match staged replacements (**NEW**, not reused old/g5.79 set).

---

## 3. Mongo fallback slots [1]–[5]

**Unchanged** on all six chains:

`e315c86f`, `dc432a6b`, `6e67e161`, `cd505118`, `124bc59c`

---

## 4. Controls and scope

| Control | Status |
|---|---|
| SHADOW | **preserved** |
| AUTOEXEC=false | **preserved** |
| RUNTIME=false | **preserved** |
| Signing / broadcast | **disabled** (unchanged) |
| Legacy b7/h05/w1 | **exited** |
| g5.79 | **running, unaffected** · still fp `a7961b2b` |
| P2 / vault / revoke | **not done** |

`env_sync` after recreate: exported 19 vars for all six chains; provider registry shows 6 Alchemy endpoints/chain (Base also showed early public bootstrap reg before sync — expected).

`.env`: bootstrap/archive/per-chain Alchemy vars → fp `ca6545ba`; `ARBICORE_RPC_URL_BASE` remains `mainnet.base.org`.

---

## 5. 60-minute acceptance window

| Field | Value |
|---|---|
| Start | `2026-10-10T06:59:52Z` |
| End (report) | `2026-10-10T08:23:57Z` |
| Elapsed | **5019 s (~83.6 min)** |
| Remaining at report | **0** |
| Window complete | **YES** |

### Log / error gates (scan ≈90m covering recreate→now)

| Metric | Result |
|---:|---|
| Unredacted Alchemy `/v2/<token>` | **0** |
| `/v2/[REDACTED]` markers | 3265 |
| httpx lines | 3299 |
| HTTP 401/403 | **0** |
| HTTP 5xx | **0** |
| HTTP 429 | **11** (preflight baseline 2 — elevated, not a cutover failure / not auth storm) |
| Failover keyword lines | **1** — quoter hop: `mainnet.base.org` → Base Alchemy after public `-32016` / host cooldown (expected path; not primary-key failure) |

**Acceptance verdict: PASS**

---

## 6. Old/new fingerprint map (revoke candidates — NOT revoked)

| Role | Old fp8 | New / disposition |
|---|---|---|
| Mongo primary all chains `[0]` | `24dab5d1` | **`ca6545ba`** (live) |
| Mongo fallbacks `[1..5]` | `e315c86f`…`124bc59c` | **retained** |
| ENV bootstrap/archive | `5e5d5bb1` | **`ca6545ba`** |
| Legacy stopped | `ce00e63d` | unchanged (containers exited) |
| g5.79 | `a7961b2b` | **do not revoke** under this change |

---

## 7. Residual risks

- Fallback keys still live until a separate fallback-rotation + revoke auth.  
- Old primary `24dab5d1` and ENV `5e5d5bb1` remain valid in Alchemy until separately revoked.  
- Pre-cutover Docker logs / backups under `/home/raghu/arbicore_backups/s2a_alchemy_cutover_*` are secret-bearing — keep access restricted.  
- Modest 429 elevation vs baseline — monitor; not treated as gate failure.

---

## Verdict

**PASS** — primary cutover successful; six-chain health OK; fallbacks retained; controls preserved; 60-minute clean-log/401 gates passed.

**REVOKE-READY for old primary `24dab5d1` and ENV `5e5d5bb1` only after separate explicit revoke authorisation.**  
Do **not** revoke fallback fps or g5.79 `a7961b2b` under this report.
