# WP-B Kill-Switch Authorization Hardening Report

**Date:** 2026-10-10  
**Work package:** WP-B (task charter: **F-AUTH-03** only)  
**Mode:** Isolated code changes + offline regression tests  
**Base HEAD:** `8ac3c67d5b28c348782ee1e218e45040d46a311f` (unchanged — no commit)  
**Prerequisite:** WP-A changes preserved  

---

## Verdict

**COMPLETE — awaiting human review**

Execution kill-switch **disengage** is now admin-only via the WP-A `_require_admin_dep` / canonical resolver path. Audit actor is server-derived. Unauthorized requests do not mutate state. Engage remains operator-accessible. Dual-store unification and send-path gates were **not** implemented (out of WP-B charter / belong with broader F-AUTH-04 / WP-C).

---

## 1. Base HEAD and working-tree status

| Field | Value |
|---|---|
| Workspace | `/home/raghu/projects/arbicore-x-cert` |
| Branch | `handoff/emergent-arbicore-canonical-1-20261010` |
| HEAD | `8ac3c67d5b28c348782ee1e218e45040d46a311f` |
| Commit / push / deploy | **None** |

### Working tree (auth / WP-A + WP-B)

| State | Path |
|---|---|
| Modified (WP-A) | `app/backend/arbicore/auth/__init__.py` |
| Modified (WP-A) | `app/backend/services/auth.py` |
| Modified (WP-A + WP-B) | `app/backend/server.py` |
| Modified (WP-B) | `app/backend/arbicore/execution/kill_switch.py` |
| Untracked | `app/backend/tests/test_wp_a_auth_unification.py` |
| Untracked | `app/backend/tests/test_wp_a_real_handlers.py` |
| Untracked | `app/backend/tests/test_wp_b_kill_switch_auth.py` |
| Untracked | `artifacts/security_reconciliation/*` |

---

## 2. Inspection (pre-change defect confirmation)

| Route | Pre-WP-B auth | Store | Defect? |
|---|---|---|---|
| `POST /api/arbicore/execution/kill-switch/disengage` | `_require_operator_dep` | Persistent `_KILL_SWITCH_REPO` | **YES** — any authenticated operator could disengage |
| `POST /api/arbicore/execution/kill-switch/engage` | `_require_operator_dep` | Persistent | OK (emergency stop; left unchanged) |
| `POST /api/arbicore/safety/kill/disengage` | Manual `_resolve_current_user`, `role == admin` | In-memory `_KILL` | Already admin-only; not duplicated, verified |
| `POST /api/arbicore/safety/kill/engage` | admin or operator | In-memory | Left unchanged |

**Actor spoofing (execution path):** Already used `_audit_actor()` (session ContextVar). Body `actor` was not passed into the repo. WP-B tests prove forged body `actor` is ignored and session username is recorded.

**Canonical admin dependency:** WP-A `_require_admin_dep` → `_require_operator_dep` → `_resolve_current_user` → `services.auth.get_current_user`.

---

## 3. Exact files changed (WP-B)

| Path | Change |
|---|---|
| `app/backend/server.py` | Execution disengage → `Depends(_require_admin_dep)`; fail-closed HTTP 503 on disengage persistence errors; safety disengage audit-first + session-only actor |
| `app/backend/arbicore/execution/kill_switch.py` | `disengage()` writes audit **before** clearing engaged state (fail-closed) |
| `app/backend/tests/test_wp_b_kill_switch_auth.py` | New real-handler regression suite |

WP-A files untouched beyond prior uncommitted work.

---

## 4. Finding disposition — F-AUTH-03

| Requirement | Disposition | Evidence |
|---|---|---|
| Disengage requires authenticated admin | **FIXED** | Execution route uses `_require_admin_dep` |
| Authorization before mutation | **FIXED** | FastAPI Depends runs before handler; 401/403 leave counters at 0 |
| Audit actor from authenticated identity | **FIXED / VERIFIED** | `_audit_actor()` / safety `ctx.username`; body `actor` ignored |
| Unauthorized / malformed → no state change | **FIXED + TESTED** | Unauth/operator/forged → no disengage call |
| Audit-write failures fail closed | **FIXED + TESTED** | Repo audit-first; handler/safety return 503; state stays engaged |
| Engage / emergency-stop not weakened | **PRESERVED** | Engage still `_require_operator_dep`; operator engage test passes |
| Compatible with WP-A canonical-only auth | **YES** | Uses `_require_admin_dep` / `_resolve_current_user` |

**ID note:** Remediation-plan WP-B also targets **F-AUTH-04** (dual-store unification + send-gate races). This task charter scoped **F-AUTH-03 only**; dual stores remain (documented limitation).

---

## 5. Tests and results

### Commands

```bash
cd /home/raghu/projects/arbicore-x-cert/app/backend

# Charter suites (WP-B + WP-A)
JWT_SECRET='wp-b-kill-switch-jwt-secret-32chars!!' \
ARBICORE_JWT_SECRET='wp-b-kill-switch-jwt-secret-32chars!!' \
MONGO_URL='mongodb://127.0.0.1:27017' \
DB_NAME='wp_b_kill_switch_auth_test' \
/tmp/wp_a_auth_venv/bin/python -m pytest \
  tests/test_wp_b_kill_switch_auth.py \
  tests/test_wp_a_real_handlers.py \
  tests/test_wp_a_auth_unification.py \
  -v --tb=short -o addopts=

# Additional targeted kill-switch unit regressions
/tmp/wp_a_auth_venv/bin/python -m pytest \
  tests/test_wave6d_unit.py -k 'kill or Kill' -v --tb=short -o addopts=
```

### Results (targeted only — not a full backend suite)

| Suite | Result |
|---|---|
| `test_wp_b_kill_switch_auth.py` | **12 passed** |
| `test_wp_a_real_handlers.py` | **15 passed** |
| `test_wp_a_auth_unification.py` | **16 passed** |
| **Combined charter command** | **43 passed** |
| `test_wave6d_unit.py` (kill filter) | **5 passed** (17 deselected) |

### WP-B cases covered

- Unauthenticated / operator / forged-token disengage → reject, no mutation  
- Admin disengage → success; body `actor=attacker-spoof` **not** used  
- Audit failure → 503; no successful disengage  
- Operator engage still works  
- Real `KillSwitchRepo.disengage` audit-first leaves state engaged on audit error  
- Alternate safety disengage: admin-only; operator 403; audit fail-closed  

Authorization dependencies were **not** mocked to force success.

---

## 6. Remaining limitations

1. **Dual kill-switch stores** (`_KILL` in-memory vs `_KILL_SWITCH_REPO` persistent) still exist; status uses OR semantics. Unification is F-AUTH-04 / broader plan WP-B — **not** done here.  
2. **No send-path / race hardening** (re-check under lock before `eth_sendRawTransaction`) — WP-C.  
3. Full `server.app` lifespan not started in HTTP tests; real handler functions + real Depends are remounted on an isolated FastAPI app (same pattern as WP-A real-handler verification).  
4. `get_user_by_payload` stubbed after JWT verification for offline isolation.  
5. No commit, push, deploy, production access, signing, or broadcast.

---

## 7. Boundaries

| Boundary | Confirmed |
|---|---|
| WP-A preserved | Yes |
| WP-C not implemented | Yes |
| No production / RPC / wallet / credential access | Yes |
| No deploy / commit / push | Yes |
| Signing / broadcast / execution remain disabled | Yes |

---

## 8. Stop

WP-B (F-AUTH-03 charter) complete. **Do not proceed to WP-C** until separately authorized.
