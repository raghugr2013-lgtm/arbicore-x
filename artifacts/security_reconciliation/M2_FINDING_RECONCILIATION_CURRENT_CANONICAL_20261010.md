# M2 Finding Reconciliation — Current Canonical State

**Date:** 2026-10-10  
**Mode:** READ-ONLY REPOSITORY AUDIT  
**Authorization:** Audit only — no remediation, deployment, signing, broadcast, or DEX replay.

---

## 0. Critical limitation — source report unavailable

**Expected file:** `M2_ADVERSARIAL_REVIEW_20261010-201500.md`  
**Search result:** **NOT FOUND** under the canonical worktree, sibling project trees (shallow), `/tmp`, or Cursor project attachments reachable from this session.

Therefore:

- Original M2 finding **wording**, **severity**, and **disposition** cannot be preserved verbatim.
- Every finding ID listed in the task is retained.
- Classifications below are based on **current source inspection** at HEAD plus Git ancestry relative to baseline `621faea9175277206210886539c30781e22a0f28`.
- Where the original M2 claim cannot be reconstructed, the classification is `UNVERIFIED` (or a current-path provisional class with that limitation noted).

**Clarification needed from human:** provide the absolute path to `M2_ADVERSARIAL_REVIEW_20261010-201500.md` (or re-upload it) for a second-pass reconciliation that can preserve original severity/disposition text.

---

## 1. Repository identity and inspected commit

| Field | Value |
|---|---|
| Canonical local path | `/home/raghu/projects/arbicore-x-cert` (git worktree of `/home/raghu/projects/arbicore-x-v2`) |
| Canonical remote | `git@github.com:raghugr2013-lgtm/arbicore-x.git` (`origin`) |
| Current branch | `handoff/emergent-arbicore-canonical-1-20261010` |
| Inspected HEAD | `8ac3c67d5b28c348782ee1e218e45040d46a311f` |
| Tracks | `origin/handoff/emergent-arbicore-canonical-1-20261010` (clean vs remote tip at inspect time) |
| Working tree | Dirty with **untracked** archaeology/g15/bundle artifacts only; no staged source edits inspected for this audit |
| Handoff identity doc | `HANDOFF_EMERGENT_ARBICORE_CANONICAL_1_20261010.md` (manifest tip fields may lag HEAD by docs-only commits) |

**Git posture used:** read-only (`rev-parse`, `log`, `merge-base`, `diff`, `status`). No checkout, reset, merge, stash, commit, or push.

---

## 2. M1 baseline ancestry and source drift

| Check | Result |
|---|---|
| M2-reviewed baseline | `621faea9175277206210886539c30781e22a0f28` (2026-09-03, “Phase 2 complete…”) |
| Is baseline ancestor of HEAD? | **Yes** (`git merge-base --is-ancestor` exit 0) |
| Commits `621faea..HEAD` | **159** |
| Material drift on security-relevant paths | **Yes** — auth, execution, broadcast, calldata_v2, capital_policy, log_redaction, FlashLoanReceiverV2, network settings, quoter, etc. differ substantially from baseline tip |

Baseline commit itself only touched `memory/PRD.md` in its own diffstat; the M2 review treated that SHA as the **code tip** under review, not as a security-only commit. Current HEAD is a descendant with extensive later changes — findings must be re-evaluated against HEAD, not assumed open or closed from M2 alone.

---

## 3. Classification summary (current-path)

| Classification | Count |
|---|---:|
| `FIXED_VERIFIED` | **0** |
| `PARTIALLY_FIXED` | **4** |
| `OPEN_CONFIRMED` | **3** |
| `OPEN_PLAUSIBLE` | **12** |
| `NOT_APPLICABLE_TO_CURRENT_PATH` | **1** |
| `UNVERIFIED` | **8** |
| **Total finding IDs** | **28** |

**Final verdict:** `FAIL`

Rationale: (a) M2 source register unavailable → incomplete documentary reconciliation; (b) current-path inspection confirms open JWT/legacy-auth and dual kill-switch risks; (c) Slither reentrancy IDs lack OpenZeppelin `ReentrancyGuard` remediation evidence; (d) no production signing gateway service is wired, but that is **not** a fix for the listed auth/gateway findings.

A `PASS` is **not** granted. This verdict is **not** permission to deploy or enable live execution.

---

## 4. Finding-by-finding reconciliation

> **Legend for “Original finding”:** `UNAVAILABLE — M2 report file not on disk`. Severity from M2 not restorable; task ID list used as the register.

### 4.1 Authentication — F-AUTH-01 … F-AUTH-04

#### F-AUTH-01 — JWT secret fallback

| Item | Content |
|---|---|
| Original (M2) | UNAVAILABLE |
| Suspected theme (task §4) | JWT secret fallback |
| Current refs | `app/backend/arbicore/auth/__init__.py` `_jwt_secret()` ~L44–53; docstring L12–13 |
| Current behavior | If `ARBICORE_JWT_SECRET` missing or `<32` chars, derives `sha256("arbicore-x-dev-"+MONGO_URL)` — deterministic install-scoped fallback. Seed passwords still have hardcoded defaults `admin-shadow-2026` / `operator-shadow-2026` when env unset (L105–112). |
| Later commits/tests | Auth module present since before baseline; no evidence of removal of fallback. Canonical `services/auth.py` `_secret()` requires `os.environ["JWT_SECRET"]` (KeyError if unset) — **dual auth stacks**. |
| Classification | **`OPEN_CONFIRMED`** |
| Justification | Fallback still present in code on the legacy JWT path used by `_resolve_current_user`. |
| Remaining conditions | Exploit requires ability to forge JWTs under the derived secret (knowledge/guess of `MONGO_URL` seed) **or** use of default seed passwords if never overridden. |
| Next action | Remove deterministic JWT fallback in production paths; refuse boot without strong secrets; confirm which stack is authoritative for all routes. |

#### F-AUTH-02 — Legacy bearer-token acceptance

| Item | Content |
|---|---|
| Original (M2) | UNAVAILABLE |
| Suspected theme | Legacy bearer acceptance |
| Current refs | `app/backend/server.py` `_resolve_current_user` L6989–7048; comments L7061–7063 |
| Current behavior | Preferred: `services.auth.get_current_user` (cookie/bearer). **Fallback:** decode bearer via `arbicore.auth` for pre-v2.9.3 tokens. Explicitly retained. |
| Classification | **`OPEN_CONFIRMED`** |
| Justification | Legacy path still active in unified resolver used by `_require_operator_dep` and safety kill routes. |
| Remaining conditions | Valid legacy token still accepted if not revoked (`jti` check). |
| Next action | Time-box/remove legacy bearer; force re-login under `JWT_SECRET` stack only. |

#### F-AUTH-03 — Auth on execution-control routes

| Item | Content |
|---|---|
| Original (M2) | UNAVAILABLE |
| Suspected theme | Auth on execution-control routes |
| Current refs | `server.py` kill-switch API L4092–4127 (`Depends(_require_operator_dep)`); safety kill L8509–8544 (manual `_resolve_current_user`, admin-only disengage) |
| Current behavior | Primary `/api/arbicore/execution/kill-switch/*` routes are dependency-gated. Alternate `/api/arbicore/safety/kill/*` also checks auth/role. |
| Classification | **`PARTIALLY_FIXED`** |
| Justification | Execution kill-switch mutations are authenticated now; residual risk is dual-store semantics (see F-AUTH-04 / dual KS) and legacy bearer acceptance feeding the same resolver. |
| Next action | Unify kill-switch stores; drop legacy bearer; audit any remaining execution POSTs without Depends. |

#### F-AUTH-04 — Kill-switch disengage permissions / race

| Item | Content |
|---|---|
| Original (M2) | UNAVAILABLE |
| Suspected theme | Disengage permissions and pre-send races |
| Current refs | Safety disengage admin-only L8537–8538; execution disengage any authenticated operator L4114–4122; dual stores documented L8479–8483; `live_signer.py` gate ladder |
| Current behavior | **Two** kill-switch stores: in-memory `_KILL` vs persistent `_KILL_SWITCH_REPO`. Effective engage = OR of both for status. Disengage paths update different stores depending on API used. Race between check and send not formally proven closed under concurrency. |
| Classification | **`OPEN_CONFIRMED`** |
| Justification | Dual-store design is explicit in source; operator vs admin permission models differ by endpoint; TOCTOU not demonstrated fixed. |
| Next action | Single authoritative kill-switch; admin-only disengage everywhere; re-check immediately before `eth_sendRawTransaction` under a lock. |

---

### 4.2 Gateway / execution path — F-GW-01 … F-GW-08

> No separate production “signing gateway” process/module was found. Signing/broadcast logic lives in-process (`execution/broadcast.py`, `live_signer.py`, `signer_vault.py`). M2’s “absence of production gateway” is treated as historical context only.

#### F-GW-01 — Validated tx bytes immutable through sign/submit

| Item | Content |
|---|---|
| Original (M2) | UNAVAILABLE |
| Current refs | `execution/broadcast.py` (sole `eth_sendRawTransaction` path per file header); `live_signer.py` |
| Current behavior | Broadcast builds/submits raw hex; immutability of a prior validation digest through sign is **not** fully proven by this audit (no end-to-end hash binding verified offline). |
| Classification | **`UNVERIFIED`** |
| Next action | Trace validate→sign→send for a single digest equality check; add/lock regression test on real path. |

#### F-GW-02 — Base mainnet chain-ID allowlisting

| Item | Content |
|---|---|
| Original (M2) | UNAVAILABLE |
| Current refs | `executor_interface.py` `BASE_MAINNET_ID = 8453`; `executor_interface_v2.py` chain tables; `quoter.py` chain maps; operator wizard Base checks |
| Current behavior | Base `8453` heavily encoded; multichain also present (84532, others). Allowlisting for **broadcast** is configuration/mode gated; not re-proven as exclusive Base-only under all modes. |
| Classification | **`PARTIALLY_FIXED`** |
| Next action | Prove broadcast refuse for non-allowlisted chain_id in current wiring. |

#### F-GW-03 — Cumulative gas / top-up / loss budgets

| Item | Content |
|---|---|
| Original (M2) | UNAVAILABLE |
| Current refs | `execution/capital_policy.py` daily loss limit / cumulative realized loss (~L277+) |
| Current behavior | Daily loss / capital binding constraints exist. Full coverage of gas+top-up+loss as M2 described — **not** fully mapped without report. |
| Classification | **`PARTIALLY_FIXED`** |
| Next action | Diff against M2 expected budget matrix once report available. |

#### F-GW-04 — Failed technical-validation allowance cleanup

| Item | Content |
|---|---|
| Original (M2) | UNAVAILABLE |
| Current refs | `execution/technical_validation.py` exists; no strong allowance-cleanup hits in quick scan |
| Current behavior | Cleanup semantics not confirmed. |
| Classification | **`UNVERIFIED`** |
| Next action | Inspect TV failure paths for ERC-20 approve residual cleanup. |

#### F-GW-05 — Nonce coordination across concurrent instances

| Item | Content |
|---|---|
| Original (M2) | UNAVAILABLE |
| Current refs | `broadcast.py` reads nonce via RPC (~L661+) |
| Current behavior | Appears RPC `eth_getTransactionCount`-style; no distributed nonce lock observed in this pass. |
| Classification | **`OPEN_PLAUSIBLE`** |
| Next action | Document single-writer assumption or add durable nonce allocator before multi-instance LIVE. |

#### F-GW-06 — Canonical outer calldata validation (Python)

| Item | Content |
|---|---|
| Original (M2) | UNAVAILABLE |
| Current refs | `execution/calldata.py`, `calldata_v2.py` |
| Current behavior | Selector/ABI construction present; “canonical outer calldata validator” as a single enforced gate — not fully verified. |
| Classification | **`UNVERIFIED`** |
| Next action | Map Python validator ↔ Solidity decoder invariants with tests. |

#### F-GW-07 — Sensitive RPC URL/API-key leakage in errors

| Item | Content |
|---|---|
| Original (M2) | UNAVAILABLE |
| Current refs | `arbicore/log_redaction.py` (added after baseline; 175-line module); cert harness `_redact` |
| Current behavior | Log redaction filter exists for credential URLs. Error **HTTP response** bodies not exhaustively proven free of RPC secrets in this pass. |
| Classification | **`PARTIALLY_FIXED`** |
| Next action | Grep/handlers for exception `str(exc)` returning URLs to clients; extend redaction to API error paths. |

#### F-GW-08 — Signing gateway fail-closed in current wiring

| Item | Content |
|---|---|
| Original (M2) | UNAVAILABLE |
| Current refs | `broadcast.py` sole send path; kill-switch + mode gates in `live_signer.py`; handoff claims signing disabled in live posture |
| Current behavior | In-process fail-closed patterns exist (mode/kill/policy). **No** separate gateway binary. Operational disablement is environment/config (not re-verified live). |
| Classification | **`OPEN_PLAUSIBLE`** (fail-closed intended; production posture not empirically verified here) |
| Next action | Confirm AUTOEXEC/RUNTIME/signing env fail-closed on the running image without enabling them. |

---

### 4.3 F-MAIN-01

| Item | Content |
|---|---|
| Original (M2) | UNAVAILABLE |
| Current refs | Unknown without report (likely main/server composition) |
| Classification | **`UNVERIFIED`** |
| Next action | Reconcile when M2 text available. |

---

### 4.4 Technical validation — F-TV-01, F-TV-02

| ID | Original | Current path note | Classification | Next action |
|---|---|---|---|---|
| **F-TV-01** | UNAVAILABLE | `technical_validation.py` present; semantics vs M2 unknown | **`UNVERIFIED`** | Re-read with M2 text |
| **F-TV-02** | UNAVAILABLE | Same | **`UNVERIFIED`** | Re-read with M2 text |

---

### 4.5 Flash loan receiver — F-FLR-01, F-FLR-02

| ID | Original | Current path note | Classification | Next action |
|---|---|---|---|---|
| **F-FLR-01** | UNAVAILABLE | `FlashLoanReceiverV2.sol` uses `_authorized` flash-window flags; Morpho `MorphoReentrancyGuard` for zero-token; **no** OZ `ReentrancyGuard` | **`OPEN_PLAUSIBLE`** | Map to Slither IDs; confirm callback auth |
| **F-FLR-02** | UNAVAILABLE | Same contract family | **`OPEN_PLAUSIBLE`** | Same |

---

### 4.6 Codec — F-CODEC-01

| Item | Content |
|---|---|
| Original (M2) | UNAVAILABLE |
| Suspected theme | Python/Solidity outer calldata codec mismatch |
| Current refs | `calldata.py` / `calldata_v2.py` + Solidity `userData` schema in FlashLoanReceiverV2 header |
| Classification | **`UNVERIFIED`** |
| Next action | Cross-check abi.encode schema and selectors with M2 codec claim. |

---

### 4.7 Slither reentrancy — S-H1…S-H7, S-M1…S-M4 (11 IDs)

| IDs | Original | Current evidence | Classification |
|---|---|---|---|
| **S-H1 … S-H7** | UNAVAILABLE | `FlashLoanReceiverV2.sol` / V1 receivers: callback authorization flags; **no** `nonReentrant` / OZ `ReentrancyGuard` inheritance found on V2 core contract | **`OPEN_PLAUSIBLE`** each (shared underlying pattern) |
| **S-M1 … S-M4** | UNAVAILABLE | Same | **`OPEN_PLAUSIBLE`** each |

**Shared remediation cross-ref:** All 11 share the absence of a standard reentrancy guard on flash callback entrypoints. Morpho-specific `MorphoReentrancyGuard` is narrow (zero-address token) and does **not** close generic Slither CEI findings.

**Next action:** Re-run Slither on current `FlashLoanReceiverV2.sol` offline; triage true positives vs trusted-callback model; do not mark fixed until guards or formal arguments close each detector site.

---

## 5. Prioritized unresolved risks (current HEAD)

1. **P0 — Dual auth stacks + JWT fallback + legacy bearer** (`F-AUTH-01`, `F-AUTH-02`).  
2. **P0 — Dual kill-switch stores / inconsistent disengage authority** (`F-AUTH-04`).  
3. **P0 — Slither reentrancy cluster unverified closed** (`S-H*`, `S-M*`, `F-FLR-*`).  
4. **P1 — RPC/credential leakage in client-visible errors** (`F-GW-07` partial).  
5. **P1 — Multi-instance nonce coordination** (`F-GW-05`).  
6. **P1 — Missing M2 report blocks exact residual closure** (all `UNVERIFIED` IDs).

---

## 6. Pre-existing unauthenticated write-route scope question

**Scope question:** Are there mutation routes reachable without authentication on the current HEAD?

**Observation (this pass):**

| Route class | Auth posture |
|---|---|
| `/api/arbicore/execution/kill-switch/*` mutations | `Depends(_require_operator_dep)` |
| `/api/arbicore/settings/network/{validate,draft,apply,rollback}` | `Depends(_require_operator_dep)` |
| Many `/api/arbicore/engine/*` POSTs sampled | `Depends(_require_operator_dep)` |
| `/api/arbicore/safety/kill/{engage,disengage}` | Manual `_resolve_current_user` (role-gated); **not** anonymous |
| `/api/arbicore/safety/status` | **No auth** (read) |
| `/api/arbicore/mid/status` | **No auth** (read) |
| Some `/api/arbicore/execution/{mode,wallets,…}` **GET**s | Appear without Depends in decorator lines (read surface) |

**Conclusion:** No **confirmed anonymous write** on the kill-switch/network-apply paths inspected. Residual scope risk remains: (1) legacy bearer counting as “authenticated”; (2) incomplete enumeration of all `@app.post` / `@api_router.post` handlers in the 8k+ line `server.py`; (3) read endpoints leaking operational state without auth.

**Classification of the scope question itself:** **`PARTIALLY_FIXED` historically if M2 claimed fully open writes; currently `OPEN_PLAUSIBLE` for incomplete enumeration + legacy-auth bypass class.**

---

## 7. Limitations and tests not performed

- M2 report file not available — original severities/dispositions not restorable.  
- No pytest executed in this pass.  
- No Slither re-run.  
- No RPC, fork, deploy, broadcast, or live integration.  
- No `.env` / secret / key material read.  
- No production DB access.  
- Operational fail-closed env on the live VPS image not re-probed.  
- Not every POST in `server.py` manually audited.

---

## 8. Verdict

**`FAIL`**

| Question | Answer |
|---|---|
| Ready for human approval review of **this reconciliation document**? | Yes — as an incomplete but evidence-based status |
| Ready to treat M2 findings as cleared? | **No** |
| Permission to deploy / enable live execution? | **No** |

**RECONCILIATION_STATUS: COMPLETE_WITH_SOURCE_GAP — FAIL — AWAITING M2 REPORT PATH + HUMAN REVIEW**
