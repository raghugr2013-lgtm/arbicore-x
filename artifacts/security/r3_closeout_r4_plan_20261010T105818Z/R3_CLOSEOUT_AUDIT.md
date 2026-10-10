# R3 closeout audit (read-only)

**Closeout verdict: PASS WITH LIMITATIONS — close R3**  
**Audit UTC:** `2026-10-10T10:59:10Z`  
**Mode:** Read-only · no mutations · rollback script **not** used · CRUD/index probes **not** re-run (mutating)  
**Live probe:** [`r3_live_closeout_probe.json`](r3_live_closeout_probe.json)

**Inputs:**  
- [`../r3_mongo_leastpriv_apply_20261010T105128Z/R3_APPLY_EXECUTION_REPORT.md`](../r3_mongo_leastpriv_apply_20261010T105128Z/R3_APPLY_EXECUTION_REPORT.md)  
- [`../r3_mongo_leastpriv_apply_20261010T105128Z/post_apply_verification.json`](../r3_mongo_leastpriv_apply_20261010T105128Z/post_apply_verification.json)  
- [`../r3_mongo_leastpriv_apply_20261010T102900Z/`](../r3_mongo_leastpriv_apply_20261010T102900Z/) (createUser + apply dump)  
- [`../r3_decision_package_20261010T095919Z/`](../r3_decision_package_20261010T095919Z/) (corrected backup procedure + validation)  
- [`../SECURITY_REMEDIATION_MATRIX.md`](../SECURITY_REMEDIATION_MATRIX.md) · [`../SECURITY_GATE_RECONCILIATION.md`](../SECURITY_GATE_RECONCILIATION.md)

---

## 1. Claim ↔ evidence reconciliation

| Claim (execution report) | Recorded evidence | Live re-check this audit | Status |
|---|---|---|---|
| Digest `69fe2459…` unchanged | `post_apply_verification.json` · `post_recreate_identity.json` | `sha256:69fe2459…e7315313` · healthy | **Confirmed** |
| `MONGO_URL` user `arbicore_app` | `env_switch_attestation.json` · post-verify | live username `arbicore_app` | **Confirmed** |
| Roles exactly `readWrite@arbicore_x` | `prior_102900Z_create_user_result.json` · post-verify `root_usersInfo` | `usersInfo` match | **Confirmed** |
| API `/api/` 200 | post-verify | local **200** | **Confirmed** |
| Admin login + `/api/auth/me` 200 | post-verify (`auth_me_path`, cookie) | not re-logged (avoid session churn); recorded **PASS** | **Attested (recorded)** |
| App ping / Factory denied / listDB only `arbicore_x` | `app_live` + `resume_auth_verify` | ping **1** · factory_denied · dbs=`[arbicore_x]` | **Confirmed** |
| CRUD + createIndex/dropIndex | `app_live.write_ok` / `index_create_ok` | **not re-executed** (would mutate) | **Attested (recorded only)** |
| Discovery 3 921 188 persisted · TTL 17 | post-verify `root_usersInfo` | discovery **3921188** · ttl **17** | **Confirmed** |
| Factory still root + healthy | post-verify `factory` | backend/runner user `root` | **Confirmed** |
| R1 docs 404 · R2 setup 503 | post-verify | R1 **404**×3 · R2 **503** | **Confirmed** |
| SHADOW · AUTOEXEC=false · RUNTIME=false · no BOOTSTRAP | post-verify | same | **Confirmed** |
| Alchemy fps `ca6545ba` (5 chains + primary); BASE public | `five_vs_six_alchemy_resolution.json` | same | **Confirmed** |
| Legacy exited · g5.79 / Foreman untouched | post-verify | same pattern | **Confirmed** |
| No private-key / mnemonic in backend ENV | post-verify / report | `PRIVATE_KEY_ENV_PRESENT=false` | **Confirmed** |
| Validation + apply backups present | backup paths in report | validation `validation_passed` · apply archive exists `0600` | **Confirmed** |

---

## 2. Missing evidence / unverified / hygiene gaps

| Gap | Severity | Disposition |
|---|---|---|
| Closeout did **not** re-run mutating CRUD/index probes | Low | Accept recorded `app_live` from apply window |
| `post_apply_verification.json` has `all_pass: false` while `failed: []` | Cosmetic | Stale flag after `/api/auth/me` fix; `checks` + `r3_verdict` authoritative |
| Stale `FAILURE.json` in final evid dir (`env_switch` / bad URI shape @ `10:51:31Z`) before successful resume in same dir | Hygiene | Superseded by `APPLY_STAGES_COMPLETE.json` + healthy live state; do not treat as current failure |
| Empty `r3_apply_probe` collection still present | Residual | Documented; out of cleanup scope |
| Historical ransom-note / pre-2026-09-07 log gap | Residual | Decision-package limitation; not an R3 functional fail |
| Factory still on Mongo `root` | Residual | Explicitly out of R3 scope |
| BASE RPC = public `mainnet.base.org` | Residual | Pre-existing; six URL keys present; five Alchemy fps `ca6545ba` |

No claim in the verification table was found **false** against recorded evidence or live non-mutating probes.

---

## 3. Closeout decision

**R3 may be closed as PASS WITH LIMITATIONS.**  
No R3 follow-up mutation is required for closure. Residuals are accepted limitations or separate workstreams (Factory least-privilege, BASE RPC policy, incident log gap, probe collection scrub).

**Overall security gate / P2:** remains **BLOCKED** (R4–R6 open).

**Preserved controls (this audit):** R1/R2 · digest `69fe2459…` · SHADOW · AUTOEXEC/RUNTIME false · signing/broadcast not enabled · legacy stopped · g5.79/Foreman isolation · R3 least-privilege cutover held.
