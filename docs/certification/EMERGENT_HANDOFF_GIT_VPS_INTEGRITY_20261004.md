# Emergent Handoff / Git–VPS Integrity Check

**Date (UTC):** 2026-10-04  
**Scope:** READ-ONLY integrity verification for Emergent handoff  
**Actions taken:** none (no code change, no deploy, no restart, no configuration change)

---

## Verdict

| Question | Result |
|---|---|
| Deployed image source commit identifiable? | **YES** — `9ed2718b3550066934bd11e99a96503ce75a499f` |
| Deployed product code matches that commit? | **YES** |
| Git HEAD identical to deployed commit? | **NO** — HEAD is one docs-only commit ahead |
| All five remediation commits ancestors of deployed? | **YES** |
| Workspace clean? | **NO** — dirty product files + many untracked cert docs |
| Runtime-only code modifications in the running container? | **NO** |
| Latest flash-loan diagnostic/cert docs committed? | **NO** — several critical docs remain untracked |

**Handoff status:** **CONDITIONAL** — runtime is on a known remediation tip (`9ed2718`), but the certification workspace is dirty/untracked and local HEAD is not identical to the deployed SHA.

---

## 1. Current VPS Git branch

| Checkout | Path | Branch |
|---|---|---|
| **Certification (canonical for remediation)** | `/home/raghu/projects/arbicore-x-cert` | `phase-b/h06-six-chain-runtime` |
| Production compose/source tree | `/home/raghu/projects/arbicore-x-v2` | `emergent/arbitrage-engineering-handoff-20260930` |

Remote tracking (cert): `origin/phase-b/h06-six-chain-runtime` — **ahead 25**, behind 0.

---

## 2. Current Git HEAD

| Checkout | HEAD |
|---|---|
| `arbicore-x-cert` | `ab2d6d5b8fc92b6deb47469152497a98d0245fcb` |
| `arbicore-x-v2` | `5bd952568aeda55bc90702289a9bfbfa9d6ba82c` |

Cert tip subject:

```text
ab2d6d5 docs(cert): record post-remediation pre-SHADOW coverage audit
```

---

## 3. `git status` (cert workspace)

Branch: `phase-b/h06-six-chain-runtime...origin/phase-b/h06-six-chain-runtime [ahead 25]`

**Modified (tracked):**
- `app/backend/arbicore/execution/quoter.py`
- `app/backend/tests/test_quoter_scoped_throttle.py`
- `docs/certification/M6_POST_ALCHEMY_RESET_SHADOW_20261002.md`
- `reports/shadow_validation/m6_post_alchemy_reset_latest.json`
- `reports/shadow_validation/post_alchemy_reset_probe.json`

**Untracked (high-signal, non-exhaustive):**
- `docs/certification/FLASH_LOAN_SIX_CHAIN_BLOCKER_DIAGNOSTIC_20261004.md`
- `docs/certification/FLASH_LOAN_DISCOVERY_SIX_CHAIN_PIPELINE_CERT_20261004.md`
- `docs/certification/FLASH_LOAN_DISCOVERY_RUNTIME_READINESS_20261004.md`
- `docs/certification/SHADOW_DISCOVERY_REMEDIATION_PLAN_20261003.md`
- `docs/certification/SIX_NETWORK_AB_ONLY_APPLY_20261003.md`
- `docs/certification/SIX_NETWORK_AB_ONLY_POST_APPLY_RUNTIME_20261004.md` (and related six-network cert pack)
- many other Oct 2–3 cert/report artifacts under `docs/certification/` and `reports/`
- staging bundles under `artifacts/`

`docs/certification/` porcelain count at check time: **50** lines (**49** untracked).

Production checkout `arbicore-x-v2` has a large set of untracked `*.pre-*` backup files and is **not** the remediation tip.

---

## 4. Deployed image source commit vs Git HEAD

### Running container

| Field | Value |
|---|---|
| Container | `arbicore-x-backend-new` |
| Image tag | `arbicore-x-backend:flash-discovery-readiness-9ed2718` |
| Image Id | `sha256:92a51023b75675f5be2d584345c6b3b7d2de44f66c659d4c291051879d842cfb` |
| Status | `running` |
| StartedAt | `2026-10-03T19:19:43.88295939Z` |
| RestartCount | **not exposed** by this Docker/engine inspect (`State.RestartCount` key absent) |

### `/app/BUILD_INFO.json` (inside container)

```json
{
  "git_sha": "9ed2718b3550066934bd11e99a96503ce75a499f",
  "git_tag": "flash-discovery-readiness-9ed2718",
  "app_version": "flash-discovery-readiness-9ed2718",
  "image_digest": "unset",
  "image_ref": "unset",
  "build_time": "2026-10-03T19:09:14Z",
  "runtime_env": "production"
}
```

`ARBICORE_GIT_SHA` / env also reports `9ed2718b3550066934bd11e99a96503ce75a499f`.

### Equality check

| Pair | Match? |
|---|---|
| Deployed `BUILD_INFO.git_sha` == Git HEAD | **NO** (`9ed2718` vs `ab2d6d5`) |
| Deployed product tree vs Git HEAD `app/backend` | **YES** — `git diff --stat 9ed2718 HEAD -- app/backend` empty |
| Only commit `9ed2718..HEAD` | `ab2d6d5` docs-only cert audit |

**Conclusion:** the running image is exactly remediation tip **`9ed2718`**. Local HEAD is that tip **plus one committed docs-only commit**. They are not the same SHA, but product code is identical.

---

## 5. Uncommitted modifications

**Yes.**

| Kind | Path | In running container? |
|---|---|---|
| Dirty product | `app/backend/arbicore/execution/quoter.py` (+79/−4 vs HEAD) | **No** — not bind-mounted |
| Dirty product | `app/backend/tests/test_quoter_scoped_throttle.py` (+65) | **No** |
| Dirty docs/reports | M6 alchemy reset docs/JSON | N/A |
| Untracked cert pack | ~49 certification docs + reports/artifacts | N/A |

### File hash proof (`quoter.py`)

| Source | SHA256 |
|---|---|
| Host working tree | `ccee938880af1fa42e8befc45d3a5e7c9e560e036d12bdf6d72af9e04950ed65` |
| Git HEAD | `1b3b683f216f79a10d9d9f17e3dec509bd16438a7062b78d111149d25c76202c` |
| Git `9ed2718` (deployed) | `1b3b683f216f79a10d9d9f17e3dec509bd16438a7062b78d111149d25c76202c` |
| Container `/app/arbicore/execution/quoter.py` | `1b3b683f216f79a10d9d9f17e3dec509bd16438a7062b78d111149d25c76202c` |

Host dirty `quoter.py` is **workspace-only** and does **not** affect the running image.

---

## 6. Remediation commits vs deployed commit

Required checkpoints:

| Commit | Subject | Ancestor of deployed `9ed2718`? | Ancestor of HEAD `ab2d6d5`? |
|---|---|---|---|
| `cb79ef17…` | scanner enabled-state cache | **YES** | **YES** |
| `df12c3df…` | TVL propagation before $100k floor | **YES** | **YES** |
| `4b25cc3b…` | quoter-reachable hop planning | **YES** | **YES** |
| `1241e6ca…` | triangular quotable-pool selection | **YES** | **YES** |
| `9ed2718b…` | BNB chain key + provider scope | **YES** (= deployed) | **YES** |

Ancestry: `DEPLOYED` is an ancestor of `HEAD`; `HEAD` is not an ancestor of `DEPLOYED`.  
`rev-list --count 9ed2718..HEAD` = **1** (docs-only).

---

## 7. Diagnostic / certification documents committed?

| Document | Git state |
|---|---|
| `PRE_SHADOW_STRATEGY_COVERAGE_AUDIT_POST_REMEDIATION_20261003.md` | **COMMITTED** (`ab2d6d5`) |
| `FLASH_LOAN_SIX_CHAIN_BLOCKER_DIAGNOSTIC_20261004.md` | **UNTRACKED** |
| `FLASH_LOAN_DISCOVERY_SIX_CHAIN_PIPELINE_CERT_20261004.md` | **UNTRACKED** |
| `FLASH_LOAN_DISCOVERY_RUNTIME_READINESS_20261004.md` | **UNTRACKED** |
| `SHADOW_DISCOVERY_REMEDIATION_PLAN_20261003.md` | **UNTRACKED** |
| `SIX_NETWORK_AB_ONLY_APPLY_20261003.md` | **UNTRACKED** |
| `SIX_NETWORK_AB_ONLY_POST_APPLY_RUNTIME_20261003.md` | **UNTRACKED** |
| `WORKSTREAM_A_QUOTER_429_BEFB14E_INDEPENDENT_CERT_20261002.md` | **UNTRACKED** |
| This integrity report | **UNTRACKED** (written by this check) |

**Answer:** not all. The post-remediation coverage audit is committed; the latest flash-loan readiness / pipeline / blocker diagnostics and most six-network APPLY evidence pack remain untracked.

---

## 8. Runtime-only code modifications?

**No evidence of runtime-only code mods in the running backend.**

Container mounts (only):
1. `/home/raghu/projects/arbicore-x-v2/app/backend/arbicore/intel/launch/labels.json` → `/app/arbicore/intel/launch/labels.json` (**ro**)
2. `/home/raghu/projects/arbicore-x-v2/deployment/upgrade/logs` → `/var/log/arbicore-x` (**rw**)

No bind-mount of `app/backend` source tree onto `/app`. Product Python in the container matches git `9ed2718` / HEAD product tree, not the dirty host working copy.

---

## 9. Current VPS image ↔ Git commit relationship

```text
Git tip (cert):     ab2d6d5  (docs after remediation)
                         │
                         │ docs-only
                         ▼
Deployed image SHA: 9ed2718  ←── BUILD_INFO.git_sha
Image tag:          arbicore-x-backend:flash-discovery-readiness-9ed2718
Image Id:           sha256:92a51023b75675f5be2d584345c6b3b7d2de44f66c659d4c291051879d842cfb
```

Production checkout `arbicore-x-v2` HEAD `5bd9525` is a **different branch/tip**. Object `9ed2718` exists in that object database but is **not** an ancestor of `v2` HEAD. Compose/runtime uses the Docker image built from the **cert** remediation tip, not `v2` HEAD.

---

## 10. Clean handoff summary for Emergent

### What Emergent can treat as authoritative runtime

- Image: `arbicore-x-backend:flash-discovery-readiness-9ed2718`
- Source commit: **`9ed2718b3550066934bd11e99a96503ce75a499f`**
- Contains all five remediation commits listed above
- Network Config (separate from Git): applied revision `rev-d069f13244ba44da81f97e72f7cfce5b` (Alchemy A `cd505118` → B `124bc59c`) — not re-verified in this Git check; prior cert docs cover it

### What is **not** clean for handoff yet

1. Cert workspace dirty `quoter.py` / scoped-throttle test (local only; not deployed).
2. Large untracked certification corpus, including the Oct 4 flash-loan pipeline cert and blocker diagnostic.
3. Local HEAD ≠ deployed SHA (docs-only delta).
4. `arbicore-x-v2` production git tip is not the remediation tip.
5. Branch is **25 commits ahead** of `origin` (not pushed as part of this check; push was not requested).

### Recommended Emergent intake (no action executed here)

1. Treat deployed product as **`9ed2718`**, not dirty workspace / not `v2` HEAD.
2. Commit or separately transfer the untracked Oct 3–4 certification pack before relying on docs as Git truth.
3. Do not assume host `quoter.py` dirty tree is live.
4. For surgical fixes (multichain H05 sizer; chain-fair `claim_batch`), branch from **`9ed2718`** (or `ab2d6d5` if docs tip is desired) in the cert repo — not from `arbicore-x-v2` HEAD `5bd9525`.

---

## Integrity checklist answers

| # | Check | Result |
|---|---|---|
| 1 | Current VPS Git branch | Cert: `phase-b/h06-six-chain-runtime`; V2: `emergent/arbitrage-engineering-handoff-20260930` |
| 2 | Current Git HEAD | Cert: `ab2d6d5…`; V2: `5bd9525…` |
| 3 | `git status` | Dirty + many untracked (cert); many `*.pre-*` untracked (v2) |
| 4 | Deployed image source == Git HEAD? | **No** (docs-only ahead); product == `9ed2718` |
| 5 | Uncommitted modifications? | **Yes** (workspace); **not** in container product code |
| 6 | Remediation commits ancestors of deployed? | **Yes** (all five) |
| 7 | Diagnostic/cert docs committed? | **Partial** — post-remediation coverage committed; flash-loan Oct 4 pack mostly untracked |
| 8 | Runtime-only code mods? | **No** |
| 9 | Image ↔ Git relationship | Image = `9ed2718`; cert HEAD = `ab2d6d5` (docs); v2 HEAD unrelated tip |
| 10 | Handoff report | This document |

**STOP.** No code changes, deployment, restart, or configuration changes were performed.
