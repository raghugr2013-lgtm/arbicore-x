# WP-A/WP-B Safe Git Delivery Plan (Pre-Commit)

**Date:** 2026-10-10  
**Status:** PROPOSAL ONLY — **no branch created, no commit, no push**  
**Purpose:** Give Emergent Git access to reviewed WP-A/WP-B work after Handoff-2 archive access failed.

---

## 1. Current repository state (verified)

| Field | Value |
|---|---|
| Workspace | `/home/raghu/projects/arbicore-x-cert` |
| Current branch | `handoff/emergent-arbicore-canonical-1-20261010` |
| HEAD / baseline | `8ac3c67d5b28c348782ee1e218e45040d46a311f` |
| Tracking | `origin/handoff/emergent-arbicore-canonical-1-20261010` (in sync; WP-A/B **not** committed) |
| Proposed review branch | `review/wp-ab-auth-20261010` (**does not exist yet**) |
| Working tree | Dirty — WP-A/B changes preserved; **not** reset/rebased |

### Code diff vs HEAD (exact)

```
 app/backend/arbicore/auth/__init__.py         |  28 +++--
 app/backend/arbicore/execution/kill_switch.py |  14 ++-
 app/backend/server.py                         | 157 +++++++++++++++-----------
 app/backend/services/auth.py                  |  44 +++++++-
 4 files changed, 161 insertions(+), 82 deletions(-)
```

Numstat: `+18/−10`, `+11/−3`, `+93/−64`, `+39/−5`.

---

## 2. Proposed branch contents

**Branch name:** `review/wp-ab-auth-20261010`  
**Base:** `8ac3c67d5b28c348782ee1e218e45040d46a311f`  
**Scope:** Only reviewed WP-A/WP-B implementation, associated tests, and required security reports.

### INCLUDE (proposed commit set)

#### Application code (modified)

1. `app/backend/arbicore/auth/__init__.py`  
2. `app/backend/services/auth.py`  
3. `app/backend/server.py`  
4. `app/backend/arbicore/execution/kill_switch.py`

#### Tests (new)

5. `app/backend/tests/test_wp_a_auth_unification.py`  
6. `app/backend/tests/test_wp_a_real_handlers.py`  
7. `app/backend/tests/test_wp_a_emergency_auth_finalization.py`  
8. `app/backend/tests/test_wp_b_kill_switch_auth.py`

#### Reports / delivery docs (new)

9. `artifacts/security_reconciliation/WP_A_AUTH_UNIFICATION_REPORT_20261010.md`  
10. `artifacts/security_reconciliation/WP_A_INDEPENDENT_REVIEW_20261010.md`  
11. `artifacts/security_reconciliation/WP_A_REAL_HANDLER_VERIFICATION_20261010.md`  
12. `artifacts/security_reconciliation/WP_B_KILL_SWITCH_AUTH_REPORT_20261010.md`  
13. `artifacts/security_reconciliation/WP_A_EMERGENCY_AUTH_RECONCILIATION_20261010.md`  
14. `artifacts/security_reconciliation/WP_C_BOUNDED_IMPLEMENTATION_PLAN_20261010.md` *(plan only; not WP-C code)*  
15. `artifacts/security_reconciliation/WP_AB_GIT_DELIVERY_PLAN_20261010.md` *(this file)*  
16. `artifacts/security_reconciliation/WP_AB_SNAPSHOT_20261010.tar.gz`  
17. `artifacts/security_reconciliation/WP_AB_SNAPSHOT_20261010.tar.gz.sha256`

**Optional INCLUDE (recommend YES for Emergent parity):**  
18. `artifacts/security_reconciliation/WP_AB_SNAPSHOT_20261010/` *(unpacked snapshot: README_TRANSFER, CODE.diff, tests/, reports/, MANIFEST)*  

**Optional INCLUDE (context only; not required for auth review):**  
- `artifacts/security_reconciliation/M2_FINDING_RECONCILIATION_CURRENT_CANONICAL_20261010.md`  
- `artifacts/security_reconciliation/M2_REMEDIATION_PLAN_REVIEW_ONLY_20261010.md`  

**Default recommendation:** Include items 1–17 + unpacked snapshot dir (18). Include M2 docs only if Emergent wants prior reconciliation context.

### EXCLUDE (must not stage)

| Path / class | Reason |
|---|---|
| `app/backend/.env`, any `.env*` | Secrets / env |
| `/home/raghu/arbicore_backups/**`, escrow, keystores | Key material / out of repo |
| `artifacts/dex_replay_archaeology_20261010/` | Unrelated |
| `artifacts/g15/**` large jsonl/csv.gz | Unrelated research dumps |
| `artifacts/workstream-a-quoter-429-*.bundle` | Unrelated |
| `phase-a-h05-*.bundle`, `phase-b-h06-*.bundle` | Unrelated |
| Production credentials, wallet keys, RPC URLs with real keys | Forbidden |
| Disposable worktrees under `/tmp/arbicore-wp-ab-review*` | Not source of truth for commit |
| Any path under Foundry keystores / deployer escrow | Forbidden |

---

## 3. Sensitive-file concerns

| Finding | Assessment |
|---|---|
| Private keys / `BEGIN * PRIVATE KEY` in proposed files | **None found** |
| Credentialed Mongo URLs in proposed files | **None found** |
| Backend `.env` in workspace candidates | **Absent** |
| Test JWT strings (`wp-a-*-jwt-secret…`) | **Synthetic offline fixtures only** — safe to commit; not production secrets |
| Synthetic Alchemy-shaped URL `.../v2/SYNTHETIC_TEST_KEY_NOT_REAL_0001` | **Synthetic** — used to prove redaction; safe |
| Snapshot tarball | Contains code/tests/reports only (same reviewed set); SHA-256 `e43f08b49cf821f524b8c8ef43276f8a6742f18d8cacbc3a4f4d031537641172` |
| Known residual (code behavior, not a secret in git) | Authenticated POST validate/draft/apply/rollback may still echo RPC URLs at runtime — documented in Handoff-2; not a reason to exclude files |

---

## 4. Test evidence (already recorded; not re-run in this planning step)

| Suite | Result | Where |
|---|---|---|
| WP-A unification + real handlers + emergency + WP-B | **54 passed** | Producer repro + Handoff-2 disposable worktree |
| Command | `pytest tests/test_wp_a_emergency_auth_finalization.py tests/test_wp_a_real_handlers.py tests/test_wp_a_auth_unification.py tests/test_wp_b_kill_switch_auth.py -q -o addopts=` | with synthetic `JWT_SECRET` / inert `MONGO_URL` |

Handoff-2 independent review: **CONDITIONAL PASS** (POST network response redaction still FAIL).

---

## 5. Recommended creation procedure (after approval only)

**Goal:** Create/push `review/wp-ab-auth-20261010` **without** resetting or overwriting the dirty producer tree.

```bash
# 1) Disposable worktree from exact baseline (leaves cert workspace untouched)
git -C /home/raghu/projects/arbicore-x-cert worktree add -b review/wp-ab-auth-20261010 \
  /tmp/arbicore-review-wp-ab-auth-20261010 \
  8ac3c67d5b28c348782ee1e218e45040d46a311f

# 2) Copy ONLY the INCLUDE paths from the producer tree into the worktree
#    (rsync/cp listed files — never copy .env, bundles, g15 dumps)

# 3) In the worktree: git add <include list>; git status; review
# 4) Commit with approved message (only after human OK)
# 5) git push -u origin review/wp-ab-auth-20261010  (only after human OK)
```

**Do not** on the producer tree before approval: `git reset`, `git rebase`, `git checkout --`, force-clean, or commit mixed unrelated untracked artifacts.

---

## 6. Proposed commit message (draft; not applied)

```
security(auth): WP-A/WP-B fail-closed JWT, admin network/KS gates

Unify canonical JWT auth (no MONGO_URL fallback, no legacy bearer),
admin-only network apply/rollback and kill-switch disengage, operator-gated
network GET with RPC URL redaction, plus offline regression tests and reports.
```

---

## 7. What this plan does **not** authorize

- Creating the branch, commit, or push  
- Deploy, production access, signing, broadcast, strategy activation  
- Implementing WP-C  
- Including unrelated archaeology/G1.5/bundle artifacts  

---

## 8. Next required human action

1. Approve or amend the INCLUDE/EXCLUDE lists (especially: include unpacked `WP_AB_SNAPSHOT_20261010/`? include M2 docs?).  
2. Explicitly authorize: **create branch + commit** and separately **push to origin**.  
3. After push, give Emergent the branch URL for `review/wp-ab-auth-20261010`.

**Awaiting approval. No commit or push performed.**
