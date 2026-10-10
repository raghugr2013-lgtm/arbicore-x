# Phase 1A shadow scanner activation diagnostic — 2026-10-04

**Classification: PHASE_1A_EXPECTED_DORMANCY**

The Phase 1 control opened an infrastructure-only Shadow Certification window. That control does not start or enable the canonical flash-loan scanner. Zero certified flash-loan iterations during the window are the expected result.

**NO RUNTIME OR CONFIGURATION CHANGES WERE MADE BY THIS DIAGNOSTIC.**

This diagnostic did not reopen the window. It used the established Phase 1 record, one read of the shadow certification start path and the Phase 1 controller, and one read-only identity snapshot taken `2026-10-05T04:49:57Z`.

---

## 1. Classification

| | |
|---|---|
| Classification | **PHASE_1A_EXPECTED_DORMANCY** |
| Prior window classification | `SHADOW_30MIN_PARTIAL` (unchanged; window not reopened) |
| Decision rule | `PHASE_1A_EXPECTED_DORMANCY` because the certification control is infrastructure-only and does not start the flash-loan scanner. `PHASE_1A_ACTIVATION_GAP` would apply only if that control was supposed to activate the scanner and did not. |

`POST /api/arbicore/certification/shadow/start` refuses a non-live-ready emission chain unless the body sets `infrastructure_only=true`. With that flag it records the marker and starts a certification run. It does not call flash-loan resume, canonical activation, or the in-memory cache refresh.

The Phase 1 controller sent `infrastructure_only: true` and the note `Scanner enablement not changed.` `START_RESULT` was HTTP 200, `window_opened=true`, status `RUNNING`, `infrastructure_only=true`, readiness issues `no_scanners_running` and `paper_runner_zero_processed`.

---

## 2. Non-actions

| Action | Result |
|---|---|
| Files modified | This report only |
| Commits | None |
| Deploy | None |
| Docker restart or recreate | None |
| Mongo writes | None |
| Network Config change | None |
| RPC change | None |
| Scanner resume or enablement change | None |
| New SHADOW window | None |
| Execution-mode change | None |

---

## 3. Window (established; not reopened)

| | |
|---|---|
| Start | `2026-10-04T17:08:32.861018Z` |
| End | `2026-10-04T17:38:32.861018Z` |
| Duration | 1800 seconds |
| Prior classification | `SHADOW_30MIN_PARTIAL` |
| Controller | `/tmp/phase1_shadow_controller.py` |
| Run id | `shadowcert-0a95cbe2-5956-47d2-9ede-e282540bd7f3` |
| `START_RESULT` | `window_opened=true`, HTTP 200, status `RUNNING`, `infrastructure_only=true`, readiness issues `["no_scanners_running", "paper_runner_zero_processed"]` |
| Heartbeats | PID stayed `2823992`, restarts `0`, Network Config `rev-1068cb9715194f118c99e5f04f9e1bdb`, cycles reached `89` |
| Stop | `WINDOW_STOPPED` `2026-10-04T17:38:34Z`, status `ABORTED`, fail reasons `["aborted: phase1_shadow_30min_complete"]`, `current_after_is_null=true` |
| Window left running | No |
| Certified flash-loan scanner iterations in the window | `0` |

---

## 4. Certification control

Read once: `v2_shadow_cert_start` in `app/backend/server.py` and `/tmp/phase1_shadow_controller.py`.

The start handler loads readiness, then:

- If `is_live_ready` is false and `infrastructure_only` is false, it returns HTTP 412 `not_live_ready`.
- If `infrastructure_only` is true, it calls `engine.start_run`, stores `start_markers.infrastructure_only` and `readiness_at_start`, and returns the run.

`is_live_ready` is true only when at least one probed scanner has `is_enabled()` and a live task, the paper runner has `opportunities_processed > 0`, and the probe did not fail. An empty `scanners_running` list appends `no_scanners_running`. Zero paper opportunities append `paper_runner_zero_processed`. Both issues were present at start, which is why the controller set `infrastructure_only`.

The controller start body was:

- `infrastructure_only: true`
- `target_cycles: 1000`
- notes: Phase 1 controlled SHADOW window, wall-clock 1800s, infrastructure-only because readiness is not live-ready, scanner enablement not changed

The controller's API calls in the window were login, readiness, `shadow/start`, `shadow/current`, a network-revision read, and `shadow/stop` with reason `phase1_shadow_30min_complete`. It contains no flash-loan resume, no scanner action, and no call to `activate_canonical_flash_loan_scanner`.

---

## 5. Why certified iterations are zero

On `62ec784` / `823a79b`, already verified and consistent with the start path:

1. `FlashLoanArbitrageScanner.is_enabled()` reads the in-memory cache (`scanner.py`). It does not read Mongo on the tick.
2. `FlashLoanArbitrageScanner._tick` returns immediately when `is_enabled()` is false, before `iterations` is incremented.
3. The factory boot cache is `state.enabled=false` until a refresh copies the persisted row.
4. `activate_canonical_flash_loan_scanner` wires the live quote provider and calls `scanner.start()`. That starts the asyncio loop even when the cache is disabled. Startup schedules that activation from `_canonical_flash_loan_scanner_startup`. The loop can be alive while every tick returns before counting an iteration.
5. The 15-second `_flash_loan_cache_refresh_loop` that copies Mongo `enabled=true` into that cache lives in `initialise_arbicore_runtime` (`composition.py`). The server comment gates that initialiser on `ARBICORE_RUNTIME_AUTOSTART`. The live handler `_arbicore_runtime_autostart` returns immediately when that variable is not on, so its one-shot cache prime does not run either.
6. The running container has `ARBICORE_RUNTIME_AUTOSTART=false`.
7. Phase 1 did not call flash-loan resume. Resume is the operator path that can mirror persisted enabled state into a scanner that is already built (`refresh_live_flash_loan_state_cache`). The infrastructure-only start path does not call it.

Zero iterations are the expected result of an infrastructure-only window that does not activate the canonical flash-loan scanner.

`ARBICORE_SCANNER_AUTOSTART=true` starts the separate continuous opportunity scanner. That autostart is not the certified flash-loan iteration counter.

---

## 6. Controller log bound

Checks that would otherwise re-query the window were limited to the controller source already cited in section 4 and the identity snapshot in sections 7–10. The window log contents used here are the established `START_RESULT`, heartbeats, and `WINDOW_STOPPED` record. They were not re-collected.

---

## 7. Identity snapshot — docker inspect

Inspected `arbicore-x-backend-new` once at `2026-10-05T04:49:57Z`. The Phase 0 / Phase 1 identity is still true.

| Field | Established | This snapshot |
|---|---|---|
| Container | `arbicore-x-backend-new` | `arbicore-x-backend-new` |
| Container id | `096bcb87b121e9c56758c51c340b684d299ba9505442be60901540e9d279ea33` | same |
| Image | `arbicore-x-backend:phase0-823a79b` | same |
| Image id | `sha256:768b4410a07843a11ddeda6fde31491cd4108eb00fd559099098627a9adb32a4` | same |
| Commit | `823a79b617ddb1f19397cf5073b9c516aae4e9fd` | same (`ARBICORE_GIT_SHA` and `BUILD_INFO.git_sha`) |
| PID | `2823992` | `2823992` |
| Started | `2026-10-04T15:14:34Z` | `2026-10-04T15:14:34.569825639Z` |
| Restart count | `0` | `0` |
| Status | running | `running` |
| Health | healthy | `healthy` |
| OOMKilled | — | `false` |

The image, commit, image digest, PID, and start time did not change.

---

## 8. BUILD_INFO and version endpoint

`/app/BUILD_INFO.json` inside the container:

| Field | Value |
|---|---|
| `git_sha` | `823a79b617ddb1f19397cf5073b9c516aae4e9fd` |
| `git_tag` | `phase0-823a79b` |
| `app_version` | `phase0-823a79b` |
| `build_time` | `2026-10-04T14:58:40Z` |
| `runtime_env` | `production` |

Unauthenticated `GET /api/arbicore/version` returned HTTP 200 at `generated_at=2026-10-05T04:49:57.326571+00:00`:

| Field | Value |
|---|---|
| `git_sha` | `823a79b617ddb1f19397cf5073b9c516aae4e9fd` |
| `git_tag` | `phase0-823a79b` |
| `app_version` | `arbicore-x-cert-baseline-99059c0-20260914-dirty` |
| `build_time` | `2026-09-14T09:11:11Z` |
| `dirty` | `false` |

`git_sha` and `git_tag` match the image. `app_version` and `build_time` on the version endpoint differ from `BUILD_INFO.json`. The resolver prefers process environment over the stamp file. This snapshot did not dump those extra environment names. The image id, tag, git sha, PID, and start time remain the Phase 0 container. That field difference is not a new image and is not a restart.

---

## 9. Environment names (read-only; unchanged)

Filtered from the same inspect. Values match the Phase 0 deploy record.

| Variable | Value |
|---|---|
| `ARBICORE_EXECUTION_MODE` | `SHADOW` |
| `ARBICORE_SCANNER_AUTOSTART` | `true` |
| `ARBICORE_SHADOW_CERT_ENABLED` | `true` |
| `ARBICORE_FLASH_LOAN_SHADOW_ROUTE` | `true` |
| `ARBICORE_BORROW_SIZER_ENABLED` | `true` |
| `ARBICORE_PRICE_FEED_ENABLED` | `true` |
| `ARBICORE_AUTOEXEC_AUTOSTART` | `false` |
| `ARBICORE_RUNTIME_AUTOSTART` | `false` |
| `ARBICORE_SCANNER_CEX_ARB` | `false` |
| `ARBICORE_SCANNER_DEX_ARB` | `false` |
| `ARBICORE_SCANNER_FUNDING_ARB` | `false` |
| `ARBICORE_SCANNER_LAUNCH_ARB` | `false` |
| `ARBICORE_GIT_SHA` | `823a79b617ddb1f19397cf5073b9c516aae4e9fd` |
| `ARBICORE_GIT_TAG` | `phase0-823a79b` |

`ARBICORE_SCANNER_FLASH_LOAN_ARB`, `ARBICORE_SCANNER_CROSS_CHAIN_ARB`, and `ARBICORE_SHADOW_CERT_AUTOSTART_RUN` were absent from the container environment (unset), the same posture recorded at Phase 0.

---

## 10. Scanner status (unauthenticated only)

`GET /api/arbicore/scanners/flash_loan_arb/status` requires authentication. This diagnostic did not log in and did not call it.

Unauthenticated `GET /api/arbicore/scanners/status` returned HTTP 200 at `generated_at=2026-10-05T04:49:57.333897+00:00`.

Wave 1B-β harness: `running=[]`. The `flash_loan_arbitrage` harness entry is `running=false`, `enabled=false`, `iterations=0`.

Canonical block `canonical_flash_loan_arbitrage`:

| Field | Value |
|---|---|
| `instantiated` | `true` |
| `initialization_state` | `READY` |
| `scanner_id` | `flash_loan_arb` |
| `enabled` | `false` |
| `mode` | `SHADOW` |
| `quote_provider` | `live` |
| `detection_only` | `true` |
| `shadow_route` | `true` |
| `stats.iterations` | `0` |
| `stats.rows_emitted` | `0` |
| `stats.candidates_claimed` | `0` |
| `stats.verifier_confirmed` | `0` |
| `stats.verifier_denied` | `0` |
| `stats.last_run_at` | `null` |

`readiness.ready=true` and `readiness.active=true` on that block mean the live quote provider is wired (`flash_loan_quote_readiness` sets `active` when the provider is not the noop). They do not mean `is_enabled()` is true. `enabled` is false and `iterations` is 0.

This is a current snapshot. It was not used to reopen or regrade the 1800-second window. It matches the established window result of zero certified iterations.

---

## 11. Attribution

Zero iterations on PID `2823992` follow from the disabled in-memory cache during an infrastructure-only window.

HTTP logging from the older `h05`, `w1`, and `b7` containers stays with those containers. Older Base 429 responses and b7 discovery rows are not the cause of zero iterations on PID `2823992`.

The in-window certification cycles (`89`) are Shadow Certification runner cycles. They are not certified flash-loan scanner iterations.

---

## 12. Checkpoint answers

1. **Classification:** `PHASE_1A_EXPECTED_DORMANCY`.
2. **Evidence:** Established window `2026-10-04T17:08:32.861018Z`–`2026-10-04T17:38:32.861018Z`, run `shadowcert-0a95cbe2-5956-47d2-9ede-e282540bd7f3`, `START_RESULT` infrastructure-only with `no_scanners_running`, heartbeats on PID `2823992` through 89 cycles, stop `ABORTED` with `current` null, certified iterations `0`. Control path `v2_shadow_cert_start` plus `/tmp/phase1_shadow_controller.py` does not resume the scanner. `_tick` returns while the cache is disabled, and the cache refresh loop is not running because `ARBICORE_RUNTIME_AUTOSTART=false`. Identity snapshot still matches image `arbicore-x-backend:phase0-823a79b`, sha256 `768b4410a07843a11ddeda6fde31491cd4108eb00fd559099098627a9adb32a4`, commit `823a79b617ddb1f19397cf5073b9c516aae4e9fd`, PID `2823992`, started `2026-10-04T15:14:34.569825639Z`.
3. **Checks:** 1–8 complete. 9–10 not performed. See section 13.
4. **Files modified:** `docs/certification/PHASE_1A_SHADOW_SCANNER_ACTIVATION_DIAGNOSTIC_20261004.md` only.
5. **Commits:** none.
6. **Deploy:** none.
7. **Docker restart:** none.
8. **Mongo, Network Config, RPC, scanner, SHADOW, and execution:** unchanged by this diagnostic. No Mongo write, no network or RPC edit, no scanner resume, no new SHADOW window, `ARBICORE_EXECUTION_MODE` still `SHADOW`. Network revision was not re-read; the last established heartbeat value remains `rev-1068cb9715194f118c99e5f04f9e1bdb`.
9. **Current PID / image / commit:** PID `2823992`; image `arbicore-x-backend:phase0-823a79b`; image id `sha256:768b4410a07843a11ddeda6fde31491cd4108eb00fd559099098627a9adb32a4`; commit `823a79b617ddb1f19397cf5073b9c516aae4e9fd`.
10. **Runtime and configuration:** NO RUNTIME OR CONFIGURATION CHANGES WERE MADE BY THIS DIAGNOSTIC.

---

## 13. Checks completed and pending

| Check | Scope | Status |
|---|---|---|
| 1 | Window bounds, 1800s, `SHADOW_30MIN_PARTIAL` | Complete from established evidence. Not reopened. |
| 2 | `START_RESULT`: infrastructure-only, HTTP 200, `RUNNING`, `no_scanners_running`, `paper_runner_zero_processed` | Complete from established evidence. |
| 3 | Heartbeats: PID `2823992`, restarts `0`, Network Config revision, 89 cycles | Complete from established evidence. |
| 4 | `WINDOW_STOPPED` `ABORTED`, fail reason `phase1_shadow_30min_complete`, `current` null, window not left running | Complete from established evidence. |
| 5 | Certified flash-loan iterations during the window = 0 | Complete from established evidence. |
| 6 | Control path: infrastructure-only start and no flash-loan resume | Complete. Limited to `/tmp/phase1_shadow_controller.py` and `v2_shadow_cert_start`. |
| 7 | Current process identity | Complete. One `docker inspect`. Unchanged. |
| 8 | `BUILD_INFO` and unauthenticated scanner status | Complete in the same snapshot. Authenticated flash-loan status was not called. |
| 9 | Further window forensics (authenticated status replay, Mongo re-read, log re-scan, new SHADOW window) | Not performed. |
| 10 | Any resume, deploy, restart, RPC change, or Network Config change | Not performed. |

No further evidence is required for `PHASE_1A_EXPECTED_DORMANCY`. Checks 9 and 10 stay pending because this diagnostic stopped.

---

NO RUNTIME OR CONFIGURATION CHANGES WERE MADE BY THIS DIAGNOSTIC.
