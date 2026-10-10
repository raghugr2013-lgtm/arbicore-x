# Emergency Auth Reconciliation — WP-A Finalization

**Date:** 2026-10-10  
**Mode:** Offline verification + minimal residual remediation  
**Canonical baseline (Emergent-reviewed):** `8ac3c67d5b28c348782ee1e218e45040d46a311f`  
**Working HEAD (unchanged):** `8ac3c67d5b28c348782ee1e218e45040d46a311f`  
**Emergent source named:** `EMERGENT_HANDOFF_1_INDEPENDENT_REVIEW_20261010.md`  
**Emergent source status:** **NOT FOUND on disk** in this workspace, agent stores, Downloads, or sibling trees. Reconciliation below uses (a) the task’s stated Emergent invariants, (b) prior M2 reconciliation of the same baseline, and (c) live source + real-handler tests on the preserved WP-A/WP-B working tree.

---

## Overall verdict

**`CONDITIONAL PASS` for WP-A auth finalization invariants** (JWT fail-closed, legacy bearer removed, network apply/rollback + GET disclosure hardened, kill-switch disengage admin-only, control-mode readiness gate enforced).

**Not a deploy / LIVE authorization.** Dual kill-switch stores, send-path races, chain/budget/nonce gates remain **WP-C / F-AUTH-04** follow-ons.

---

## 1. Working-tree preservation

| Item | Status |
|---|---|
| WP-A/WP-B uncommitted work preserved | **Yes** — no reset/rebase/discard |
| Commit / push | **None** |
| Production / VPS / secrets / RPC / deploy / sign / broadcast | **None** |

### Diffstat vs baseline HEAD

```
 app/backend/arbicore/auth/__init__.py         |  28 +++--
 app/backend/arbicore/execution/kill_switch.py |  14 ++-
 app/backend/server.py                         | 157 +++++++++++++++-----------
 app/backend/services/auth.py                  |  44 +++++++-
 4 files changed, 161 insertions(+), 82 deletions(-)
```

### New tests / reports (untracked)

- `app/backend/tests/test_wp_a_auth_unification.py`
- `app/backend/tests/test_wp_a_real_handlers.py`
- `app/backend/tests/test_wp_b_kill_switch_auth.py`
- `app/backend/tests/test_wp_a_emergency_auth_finalization.py` ← this finalization
- `artifacts/security_reconciliation/WP_*.md` (prior + this report)

### Finalization-only code delta (this step)

| File | Change |
|---|---|
| `server.py` | Auth on `GET .../settings/network` + `.../history`; `_redact_network_payload()` using `redact_credential_url` |
| `tests/test_wp_a_emergency_auth_finalization.py` | Inventory / redaction / mode-gate tests |

WP-A JWT/legacy and WP-B kill-switch changes remain as previously implemented.

---

## 2. Authentication path verification

### Authoritative resolver

`server._resolve_current_user` → **only** `services.auth.get_current_user` (cookie or `Authorization: Bearer` access token, `JWT_SECRET`, DB role + session_version).

### Legacy bearer acceptance routes

| Check | Result |
|---|---|
| Runtime `_auth_decode_token(` / `_auth_issue_token(` call sites in `server.py` | **None** |
| Resolver body still contains legacy decode | **No** |
| Dead import aliases of `arbicore.auth.decode_token` | Present but **unused** (residual clutter) |
| Routes that accept Tree-B legacy tokens | **None found** on HTTP path |

### Secret fail-closed

| Secret | Behavior |
|---|---|
| `JWT_SECRET` missing / blank / &lt;32 chars | `AuthSecretError` / auth 503 / resolver → deny |
| `ARBICORE_JWT_SECRET` missing / short | `AuthSecretError` (no MONGO_URL hash) |
| Predictable `sha256("arbicore-x-dev-"+MONGO_URL)` | **Removed** |

---

## 3. Invariant scorecard (PASS / FAIL)

| ID | Invariant | Verdict | Evidence |
|---|---|---|---|
| **I-1** | No deterministic JWT secret from `MONGO_URL` / predictable seed | **PASS** | `arbicore/auth/_jwt_secret`; tests |
| **I-2** | Missing/blank/short JWT secrets fail closed | **PASS** | `services.auth._secret`; real resolver tests |
| **I-3** | Legacy bearer not accepted on unified resolver / HTTP path | **PASS** | Resolver source + real-handler legacy reject |
| **I-4** | Network apply/rollback: unauth/forged/operator rejected; admin OK; no unauthorized env sync | **PASS** | `test_wp_a_real_handlers` |
| **I-5** | Kill-switch disengage admin-only; actor not spoofable from body | **PASS** | `test_wp_b_kill_switch_auth` |
| **I-6** | Network GET/history authenticated | **PASS** | Finalization: `_require_operator_dep` |
| **I-7** | Network GET/history redact credential-bearing RPC URLs | **PASS** | `_redact_network_payload` + finalization tests |
| **I-8** | Control-center mode transition consults readiness; LIMITED_LIVE not applied | **PASS** | `v2_control_set_mode` + finalization tests |
| **I-9** | Single kill-switch store / send-path race closed | **FAIL** (out of WP-A) | Dual stores remain → WP-C / F-AUTH-04 |
| **I-10** | Full unauthenticated write-route census of entire `server.py` | **PARTIAL** | Priority surfaces covered; full POST audit incomplete |

---

## 4. Unauthenticated-route inventory (priority)

| Route | Pre-finalization | After finalization |
|---|---|---|
| `GET /api/arbicore/settings/network` | **NO_AUTH** (RPC disclosure) | **Operator** + redaction |
| `GET /api/arbicore/settings/network/history` | **NO_AUTH** | **Operator** + redaction |
| `POST .../network/apply\|rollback` | Admin (WP-A) | Unchanged |
| `POST .../execution/kill-switch/disengage` | Admin (WP-B) | Unchanged |
| `POST .../safety/kill/disengage` | Admin (manual resolve) | Unchanged |
| `GET .../execution/mode*` / mode audit | Still unauthenticated reads | Residual (non-RPC); WP-C backlog |
| Many other read GETs | Mixed | Broader census → WP-C |

Redaction uses synthetic fixture keys only in tests; production secrets were not read or printed.

---

## 5. Mode-transition readiness gate

| Path | Enforcement |
|---|---|
| `POST /api/arbicore/control/mode` | Calls `_READINESS_ENGINE.can_transition(target)`; if `allowed` is false → `applied: false`, **no** `set_mode`. LIMITED_LIVE / FULL_AUTOMATION hard-gated in engine. |
| Frontend readiness display | Advisory only if it ignores backend; **cannot** bypass this handler. |
| `POST /api/arbicore/execution/mode/{strategy}` | Separate ladder (`ExecutionModeRepo.transition`); operator-gated; **not** the Control Center readiness matrix. Document as residual scope difference. |

---

## 6. Tests executed (exact)

```bash
cd /home/raghu/projects/arbicore-x-cert/app/backend
JWT_SECRET='wp-a-final-jwt-secret-32chars-minimum!!' \
ARBICORE_JWT_SECRET='wp-a-final-jwt-secret-32chars-minimum!!' \
MONGO_URL='mongodb://127.0.0.1:27017' \
DB_NAME='wp_a_emergency_auth_finalization' \
/tmp/wp_a_auth_venv/bin/python -m pytest \
  tests/test_wp_a_emergency_auth_finalization.py \
  tests/test_wp_a_real_handlers.py \
  tests/test_wp_a_auth_unification.py \
  tests/test_wp_b_kill_switch_auth.py \
  -q -o addopts=
```

**Result:** `54 passed` (≈5.7s) — disposable venv; no production services.

| Suite | Count |
|---|---|
| `test_wp_a_emergency_auth_finalization.py` | 11 |
| `test_wp_a_real_handlers.py` | 15 |
| `test_wp_a_auth_unification.py` | 16 |
| `test_wp_b_kill_switch_auth.py` | 12 |

**Not claimed:** full backend suite.  
`tests/test_control_readiness.py` co-run after `server` import failed in this venv with `RuntimeError: There is no current event loop` (pre-existing asyncio helper in that file); mode-gate coverage is provided by the finalization suite instead.

---

## 7. Comparison with Emergent Handoff-1 findings

Because the Emergent markdown file is **missing locally**, mapping uses the task’s Emergent-derived requirements and overlap with M2 reconciliation at the same baseline.

| Emergent / task theme | Status vs working tree | Notes |
|---|---|---|
| Deterministic JWT fallback | **Confirmed fixed** | Verified in source + tests |
| Legacy bearer bypass | **Confirmed fixed** | No HTTP acceptance path |
| Network apply/rollback authz | **Confirmed fixed** (WP-A) | Real-handler tests |
| Kill-switch disengage admin | **Confirmed fixed** (WP-B) | Real-handler tests |
| Unauth network GET / RPC disclosure | **Confirmed fixed** (this step) | Auth + redaction |
| Mode readiness advisory-only | **Confirmed enforced** on Control Center path | Engine + handler |
| Dual KS / send races | **Still open** | Separate WP-C |
| Full route census / GW findings | **Unverified / separate** | Need Emergent file for 1:1 ID mapping |
| Emergent report claims we cannot open | **UNVERIFIED** | Attach/copy `EMERGENT_HANDOFF_1_INDEPENDENT_REVIEW_20261010.md` for line-accurate closeout |

**Regressions observed:** none in targeted suites.

---

## 8. Residual limitations

1. Emergent review file not available for verbatim finding-ID closeout.  
2. Dual kill-switch stores (`_KILL` vs `_KILL_SWITCH_REPO`) remain.  
3. Dead `_auth_*` imports in `server.py` (unused).  
4. Legacy seed password defaults if `ARBICORE_LEGACY_AUTH_SEED=1`.  
5. Apply/rollback response bodies still return config to **admins** (redaction applied to GET/history; admin apply UX left intact).  
6. Broader unauthenticated GET surfaces (execution mode reads, etc.) not all gated.  
7. No production attestation of env secret length / deployed image digest.

---

## 9. Proposed WP-C test list (next)

1. **Single KS facade:** engage via execution API reflected in safety status and `LiveSigner.guard` / broadcast deny.  
2. **Disengage race:** concurrent engage vs send — send denied if engaged wins.  
3. **Pre-send fail-closed:** `broadcast.py` / `live_signer` denies without LIVE flags + KS disengaged + signer + policy.  
4. **Chain allowlist:** reject non-allowlisted `chain_id` at broadcast.  
5. **Tx-byte immutability:** mutate plan bytes between validate and send → deny.  
6. **Budget matrix:** daily loss / gas / top-up counters block send when exceeded.  
7. **Nonce lock:** two concurrent sends do not share nonce without coordination.  
8. **RPC leakage in HTTP errors:** exception paths never echo raw credential URLs.  
9. **Full unauth POST census:** every `@api_router.post` / `@app.post` has auth or is explicitly public-safe.  
10. **Restart persistence:** KS engaged survives process restart (persistent store only).

---

## 10. Stop

Emergency Auth Reconciliation complete for human review. **No commit/push.** Attach the missing Emergent review file for ID-level closeout if required before merge.
