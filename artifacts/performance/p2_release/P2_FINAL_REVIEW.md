# P2 Final Review — Patch Review & Deployment Decision Preparation

**Date:** 2026-10-09  
**Reviewer role:** Read-only package verification (no deploy)  
**Recommendation:** **APPROVE FOR SEPARATE DEPLOYMENT AUTHORISATION**

---

## 1. Checksum verification

| Item | SHA-256 |
|---|---|
| Recomputed `P2_ONLY_COMBINED.patch` | `56739a3d65470f61abfe3becfdf5a929576c41ce4ddc0a8bdd80615395690669` |
| Manifest `P2_RELEASE_CHECKSUMS.txt` entry | `56739a3d65470f61abfe3becfdf5a929576c41ce4ddc0a8bdd80615395690669` |

**Result:** **MATCH**

---

## 2. Exact file-scope verification

Paths present in `P2_ONLY_COMBINED.patch` (`+++ b/...`):

1. `app/backend/arbicore/data/discovery_queue.py`
2. `app/backend/arbicore/models/discovery.py`
3. `app/backend/arbicore/scanners/flash_loan_arbitrage/verifier.py`
4. `app/backend/arbicore/data/mongo/evidence_bundles_repo.py`
5. `app/backend/tests/test_flashloan_diagnostic_provenance.py`
6. `app/backend/tests/test_p2_flashloan_timing_instrumentation.py`
7. `app/backend/tests/test_p2_evidence_persisted_mongo.py`

**Count:** 7 / 7 approved. **No extra paths.**

### Forbidden queue-status tokens

Search of combined patch for `fresh_eligible`, `per_chain_backlog`, `per_strategy_backlog`: **ABSENT**.

---

## 3. Base commit and patch applicability

| Item | Value |
|---|---|
| Intended canonical base (this repo `HEAD`) | `9244ebdee6a95188d925084e7e10d4a972cda7ad` |
| Commit subject / date | `fix(quoter): host-scoped 429 cooldown with bounded retry and A→F failover` (2026-10-08) |
| Branch tip when reviewed | `cert/gate7-dynamic-profitability-20261007` |
| Production image tag correlation | `arbicore-x-backend:hybrid-e-rpc-9244ebd` (prefix aligns with base `9244ebd…`) |

**Applicability check (isolated, non-production):**

1. `git archive 9244ebdee6a95188d925084e7e10d4a972cda7ad` → temp tree `/tmp/p2_patch_apply_*`
2. `git apply --check P2_ONLY_COMBINED.patch` → **exit 0**
3. `git apply P2_ONLY_COMBINED.patch` in that temp tree → **APPLY_OK**
4. Spot-checks after apply: durable `claimed_at` comment present; `"claimed_at": None` absent from `mark_processed`; Option D stamp present; new tests present; no `fresh_eligible` / `per_chain_backlog` in applied `discovery_queue.py`

**Conflicts:** none against base `9244ebde…`.

**Packaging quirk (non-blocking):** the discovery_queue portion’s `---` header shows `/dev/fd/63` (process-substitution artifact from package generation). Despite that, `git apply` against the archived base succeeded. Prefer applying via `git apply` (as verified) rather than assuming all `patch(1)` variants tolerate the header.

**Ambiguity:** none for *this* repository tip. If a deployer targets a different commit than `9244ebde…`, re-run apply-check on that exact base before authorising deploy.

---

## 4. Safety / non-interference findings

| Area | Finding |
|---|---|
| Verdict / Gate-7/8/9 logic | No threshold or evaluate-path rewrites; timing wraps existing stages fail-safe |
| Risk / trading / AUTOEXEC / signing / broadcast | No hits in added patch lines for autoexec/signing/broadcast/private_key/RPC clients |
| Queue eligibility | Still `verified_outcome` + `expires_at` + `claimed_until`; durable `claimed_at` not used for eligibility |
| Worker / claim TTL / admission | Unchanged in patch |
| RPC behaviour | No new RPC client usage in P2 files |
| `update_one` in patch | **Tests only** (`AsyncMock` for `mark_processed` assertions); repo remains insert-only |
| `evidence_persisted` meaning | Option D stamps `True` immediately before `insert_one` = “this audit row is being / was inserted,” not profitability/capture |
| Failed insert | If `insert_one` raises, no Mongo row; verifier sink failure path remains non-fatal (`false` in-memory, verdict unchanged) |
| Historical backfill | None; no `update_many` / backfill logic |
| Unrelated working-tree edits | Preserved in production checkout (`fresh_eligible` / `per_chain_backlog` / `per_strategy_backlog` still present in WT `discovery_queue.py`) |

---

## 5. Known validation gaps

1. Focused suite (35) was previously run against isolated validator Mongo `172.26.0.2`; this final review re-verified package integrity and temp-tree apply, and did **not** re-execute the full 35 (not required for checksum/apply decision). Last recorded result remains in `P2_TEST_RESULTS.md`: **35 passed**.
2. Combined patch was not applied to the live dirty working tree (correctly avoided to protect unrelated edits).
3. End-to-end production image build / container restart was **not** performed (deployment prohibited).
4. Discovery_queue `---` `/dev/fd/63` header is cosmetic for `git apply` but should be noted in the deploy runbook.

---

## 6. Recommendation

**APPROVE FOR SEPARATE DEPLOYMENT AUTHORISATION**

Conditions for that later authorisation (not performed here):

- Apply `P2_ONLY_COMBINED.patch` to clean base `9244ebdee6a95188d925084e7e10d4a972cda7ad` (or re-verify apply-check if base differs).
- Do **not** ship dirty working-tree `discovery_queue.py` wholesale.
- Re-run focused tests in a non-production environment after apply/build.
- Require a **separate explicit** deploy/restart authorisation.

---

## 7. Production state (this review)

| Check | Status |
|---|---|
| Patch applied to production checkout | **No** |
| Commit / push / rebuild / restart / deploy | **No** |
| Env / scanner / SHADOW / RPC / trading changes | **No** |
| Unrelated WT edits discarded | **No** |
| `arbicore-x-backend-new` | `running`, image `arbicore-x-backend:hybrid-e-rpc-9244ebd`, started `2026-10-08T08:33:43Z` |

**Production remains unchanged.**
