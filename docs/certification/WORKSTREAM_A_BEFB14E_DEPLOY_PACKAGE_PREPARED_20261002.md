# Workstream A `befb14e` — Deploy Package PREPARED (2026-10-02)

- **Status:** **PACKAGE PREPARED — NOT DEPLOYED**
- **Prepared (UTC):** `2026-10-02T14:44:46Z`
- **Workspace:** `/home/raghu/projects/arbicore-x-cert`
- **Staging root:** `artifacts/deploy_staging/workstream-a-befb14e/`
- **PRE-FIX baseline freeze:** `docs/certification/PRE_FIX_8H_BASELINE_FREEZE_20261002.md`
- **Cross-link:** `docs/certification/POST_8H_12H_SHADOW_VALIDATION_PACKAGE_20261002.md` (§9 deploy checklist, §10 rollback)
- **Cert:** `docs/certification/WORKSTREAM_A_QUOTER_429_BEFB14E_INDEPENDENT_CERT_20261002.md` §12–§13
- **Gate9:** **UNTOUCHED** (no deploy/restart/rebuild/recreate/env change)

---

## Intended next phase (DOCUMENT ONLY — DO NOT EXECUTE)

```text
8h PRE-FIX (frozen) → certified WA quoter fix deploy → fresh 12h SHADOW → compare → official 24h Gate9
```

No step after the freeze is authorized by this document.

---

## Checklist verification (items 1–10)

| # | Required package element | Verified | Evidence |
|---|---|---|---|
| **1** | Commit SHA (product tip) | **PASS** | `befb14e6aa77515daa038e142ff978822a4fab91` — tip tree `fdd6f7996a4364885fca31d394eeae75d04b379a` — `meta/tip_identity.txt` |
| **2** | Parent / history | **PASS** | Parent `8e63f252b599ea97b9f563162ba8c1836a1c9e28`; ancestry includes `2b86cda` + base `93a20c9` (present in self-contained bundle); `ancestor_*=YES` in `meta/ancestry_checks.txt` |
| **3** | Changed files | **PASS** | Exactly **2**: `M app/backend/arbicore/execution/quoter.py`; `A app/backend/tests/test_quoter_eth_call_429_amplification.py` (`meta/name_status.txt`) |
| **4** | Product-code diff | **PASS** | Extracted to `product_diff/quoter.py.diff` (+52/−11 region; 63-line net edit in `_eth_call` 429 bound + per-host cooldown). Tip file SHA256 `589ef14ee1c33f5d79907ccd02211962a79264ea3c1555cd24ea5f642da3c37f`. **No additional product-code changes** beyond certified tip. |
| **5** | Fixture-followup status | **PASS (documented separate)** | `57f53651d8c7638d0a5f3d2cd8eb2c083fd97f44` = **test hygiene only** (clear `_RPC_HOST_COOLDOWN_UNTIL` in autouse); **not** in self-contained product bundle; **not** required for product deploy of `_eth_call` fix; land for CI co-run gate (`meta/fixture_followup_status.txt`; cert §13) |
| **6** | Cert evidence pointers | **PASS** | Cert §12 self-contained re-run + §13 residual fixture-only; deploy rec **READY WITH CONDITIONS**; amp RED→GREEN ≤2 POSTs; tip+fixture 33/33; Gate9 frozen during cert |
| **7** | Rollback SHA / package | **PASS** | Live image `arbicore-x-backend:g5.79-green-20260927` Id `sha256:aaadc3a9cc78d695a9e7e2d16681babc71c576033ad3764061a918946d8e993a`; override `/tmp/arbicore-g579-prod-override.yml` sets `ARBICORE_GIT_SHA=4fec11f92fecb7f7ef1f56e39cddf18277845470` / tag `G5.79-green-20260927`; procedure `POST_8H_12H…` §10 |
| **8** | Image / build requirements | **PASS (documented)** | Import self-contained bundle → throwaway checkout tip → build from `app/backend` with same Dockerfile as prod compose → tag **new** e.g. `arbicore-x-backend:ws-a-befb14e-20261002`; **never** retag over `g5.79-green-20260927`; thin bundle **forbidden** as deploy source |
| **9** | Required env vars (document expected; **do not change live**) | **PASS (documented)** | Keep live safety block. Tip reads optional: `ARBICORE_RPC_MAX_RETRIES_429` default **1**; `ARBICORE_RPC_RATE_LIMIT_COOLDOWN_S` default **60**. Required posture (unchanged): `ARBICORE_EXECUTION_MODE=SHADOW`, `ARBICORE_AUTOEXEC_AUTOSTART=false`, `ARBICORE_RUNTIME_AUTOSTART=false`, `ARBICORE_SHADOW_CERT_ENABLED=true`, `ARBICORE_SCANNER_AUTOSTART=true`. **Do not flip live env in this prepare.** |
| **10** | Expected post-deploy safety posture | **PASS (documented)** | SHADOW **ON**; AUTOEXEC **OFF**; RUNTIME **OFF**; signing/broadcast/funds **0**; kill engaged; live_execution false; new StartedAt / RestartCount=0 for **new** campaign window; **voids** current Gate9 continuity (explicit tradeoff) |

**Checklist aggregate:** **10/10 verified for prepare package.** Deploy execution: **NO-GO until explicit authorization.**

---

## Product commit package (exact)

| Role | Full SHA |
|---|---|
| **Product tip (deploy)** | `befb14e6aa77515daa038e142ff978822a4fab91` |
| Tip tree | `fdd6f7996a4364885fca31d394eeae75d04b379a` |
| Parent | `8e63f252b599ea97b9f563162ba8c1836a1c9e28` |
| Provider hardening ancestor (intact) | `2b86cdab115223d69a48aeefd4d434dd094eee1e` (`providers/rpc.py` blob equal tip↔ancestor) |
| Fixture follow-up (separate; test only) | `57f53651d8c7638d0a5f3d2cd8eb2c083fd97f44` |

**Subject:** `fix(quoter): bound HTTP-429 retries + per-host cooldown in execution/quoter.py::_eth_call`

**Proven path (not rpc.py-only substitute):**  
`live_quote_provider` → `QuoterRegistry.quote_route` → DEX backend → `execution/quoter.py::_eth_call` (direct httpx).

**Authoritative artifact:**  
`artifacts/workstream-a-quoter-429-befb14e-selfcontained.bundle`  
SHA256 `b7f3952e29a5664bb6c7a144e7a76c9df7ba207b3f2ee6a430bb84a3a4dff964` / **8199151** bytes  
`git bundle verify` (empty bare): **PASS** — complete history; tip ref `xfer/workstream-a-befb14e`.

Thin bundle `artifacts/workstream-a-quoter-429-befb14e.bundle` left on disk for history only — **NOT** for deploy.

---

## Certification status (authoritative)

| Scope | Verdict | Deploy recommendation |
|---|---|---|
| Product tip `befb14e` | Product behaviour **PASS** (amp RED→GREEN; cooldown; failover; fail-closed) | **READY WITH CONDITIONS** (land fixture hygiene for CI co-run gate) |
| Tip + fixture `57f5365` | **PASS** (33/33 relevant suites) | **READY** for combined tree |
| Gate9 campaign | Frozen / continuous PRE-FIX | **NOT READY to modify** until campaign owner GO |

Residual from §12 CONDITIONAL **resolved as fixture-only** (§13). No architecture rebuild; reuse exact certified implementation; **no additional product-code changes** in this prepare.

---

## PRE-FIX 8h baseline (frozen)

| Field | Value |
|---|---|
| Verdict | **HEALTHY WITH OBSERVATIONS** |
| Elapsed | ≈ **8.01 h** (JSON 8.0095) |
| Cycles / Exceptions / Restarts | **5740 / 0 / 0** |
| Opportunities / Paper evidence | **0 / 0** |
| Image | `g5.79-green-20260927` |
| MD SHA256 | `42305fa1e4e0bf60d29243917ea2b5a800bf0af85e39400bf88f63958879dab7` |
| JSON SHA256 | `021c5ece36115284e9f8a62d6af8018869febe34b9ce292eb5b61b8e0dd6f54b` |
| Gate9 StartedAt | `2026-10-02T06:19:33.513948555Z` (RestartCount **0**) |

---

## Rollback package (current certified runtime)

| Item | Value |
|---|---|
| Image | `arbicore-x-backend:g5.79-green-20260927` |
| Digest/Id | `sha256:aaadc3a9cc78d695a9e7e2d16681babc71c576033ad3764061a918946d8e993a` |
| Compose override | `/tmp/arbicore-g579-prod-override.yml` |
| Recorded runtime commit (override) | `4fec11f92fecb7f7ef1f56e39cddf18277845470` |
| Safety in override | SHADOW; AUTOEXEC=false; RUNTIME=false; SCANNER=true; SHADOW_CERT=true |
| Full procedure | `POST_8H_12H_SHADOW_VALIDATION_PACKAGE_20261002.md` §10 |

---

## Image / build requirements (later — outline only)

1. Throwaway import of self-contained bundle (already demonstrated under `/tmp/ws-a-deploy-prep-freeze-20261002`).
2. Verify tip `befb14e…` + tree `fdd6f799…`.
3. Build backend image tagged e.g. `arbicore-x-backend:ws-a-befb14e-20261002` from tip `app/backend` context (same Dockerfile path as prod).
4. **Do not** overwrite/retag `g5.79-green-20260927`.
5. Compose working dir (when authorized): `/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose` with override mirroring safety block.

---

## Required env vars (expected — do NOT change live now)

**Must remain (safety):**

```text
ARBICORE_EXECUTION_MODE=SHADOW
ARBICORE_AUTOEXEC_AUTOSTART=false
ARBICORE_RUNTIME_AUTOSTART=false
ARBICORE_SHADOW_CERT_ENABLED=true
ARBICORE_SCANNER_AUTOSTART=true
```

**Optional tip knobs (defaults already correct in code):**

```text
ARBICORE_RPC_MAX_RETRIES_429=1          # ≤2 POSTs on 429
ARBICORE_RPC_RATE_LIMIT_COOLDOWN_S=60   # per-host cooldown
```

---

## Expected post-deploy safety posture (when authorized later)

| Control | Required |
|---|---|
| SHADOW | **ON** |
| AUTOEXEC | **OFF** |
| RUNTIME | **OFF** |
| Signing / broadcast / funds | **0 / 0 / 0** |
| live_execution | false |
| Kill | engaged |
| Continuity note | New `StartedAt`; original Gate9 24h continuity **ends** at cutover |

---

## Forbidden by this prepare (confirmed not executed)

- Deploy / restart / rebuild / recreate Gate9 or production
- Modify `/home/raghu/projects/arbicore-x-v2`
- Dirty-reset cert workspace
- Start PAPER / 12h / AUTOEXEC / RUNTIME / live / LIMITED_LIVE
- Hot-mount dirty cert `quoter.py` into Gate9
- Deploy thin bundle

---

## Exact next action after explicit authorization (NOT executed here)

**Build-only first step (still no Gate9 cutover unless operator expands GO):**

```bash
# AFTER explicit authorization only — illustrative
# 1) Throwaway checkout tip from self-contained bundle (already verified)
# 2) Build NEW image tag (preserve g5.79-green-20260927 immutably):
# docker build -t arbicore-x-backend:ws-a-befb14e-20261002 \
#   -f <prod Dockerfile> <tip app/backend context>
# 3) Only with separate activate GO: compose up backend with new image + SHADOW safety override
#    (ends current Gate9 continuity — record new StartedAt as post-patch T0)
```

Until that authorization: **hold** — campaign continues on `g5.79-green-20260927`.
