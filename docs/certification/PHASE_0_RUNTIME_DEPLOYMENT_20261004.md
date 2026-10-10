# Phase 0 runtime deployment — 2026-10-04

- **Classification:** `PHASE_0_RUNTIME_DEPLOYED`
- **Deployed commit:** `823a79b617ddb1f19397cf5073b9c516aae4e9fd`
- **Parent:** `62ec7844cdec9517b10a5d40378bd1c5aacc9551`
- **Branch:** `phase-0/strategy-intelligence-observability-20261004`
- **Verified (UTC):** `2026-10-04T15:17Z`
- **Scope:** Backend image rebuild and recreate of `arbicore-x-backend-new` only. No Phase 1 SHADOW window. No PAPER, recommendation, or LIVE activation. No Network Config write. No RPC, strategy, economics, gate, wallet, signing, or broadcast change.
- **Secrets policy:** RPC credentials not printed. Alchemy fingerprints are `sha256(<key>)[:8]` of the path segment after `/v2/`.

The live Network Config revision was `rev-1068cb9715194f118c99e5f04f9e1bdb` before the build and again immediately before recreate. The deploy proceeded.

A later override gate compared the Phase 0 compose merge with the previous `b1b2-62ec784` merge before any further recreate. The gate passed. No second recreate was performed.

---

## Override gate

Compared `docker compose config` for the same production file plus each override:

- `/tmp/arbicore-b1b2-62ec784-override.yml`
- `/tmp/arbicore-phase0-823a79b-override.yml`

No compose apply or container recreate was run for this comparison. Rendered config files were deleted after the diff.

| Surface | Difference |
|---|---|
| **Image** | `arbicore-x-backend:b1b2-62ec784` → `arbicore-x-backend:phase0-823a79b` |
| **Environment** | Only `ARBICORE_GIT_SHA` (`62ec7844cdec9517b10a5d40378bd1c5aacc9551` → `823a79b617ddb1f19397cf5073b9c516aae4e9fd`) and `ARBICORE_GIT_TAG` (`b1b2-62ec784` → `phase0-823a79b`). Every other merged env key is identical, including `ARBICORE_VERSION`, `ARBICORE_BUILD_TIME`, `ARBICORE_ENV=production`, and `ARBICORE_RUNTIME_ENV=production`. |
| **Secrets** | Same env file source. `MONGO_URL` and `MONGO_IMAGE` values are unchanged. No Redis variable is present in either merge. Secret values were not printed. |
| **Volumes** | Same two binds: `labels.json` read-only, and `deployment/upgrade/logs`. |
| **Networks** | Same `existing_mongo_net` and `vqb-network`. The running container attaches to `strategy-factory-canonical_default` and `vqb-network`. |
| **Ports** | Same `127.0.0.1:8001:8001`. |
| **Mongo / Redis** | Mongo env values unchanged. Redis absent. |
| **Network Config** | Not referenced by either override. Live revision remains `rev-1068cb9715194f118c99e5f04f9e1bdb`. |
| **RPC** | The eight `ARBICORE_*RPC*` env values are unchanged. Live topology remains NEW A → NEW B → OLD A → OLD B (`dc432a6b`, `6e67e161`, `cd505118`, `124bc59c`) on all six chains. |
| **Execution mode** | `ARBICORE_EXECUTION_MODE=SHADOW`, `ARBICORE_AUTOEXEC_AUTOSTART=false`, `ARBICORE_RUNTIME_AUTOSTART=false` on both merges. |
| **Scanner** | `ARBICORE_SCANNER_AUTOSTART=true`, CEX/DEX/funding/launch `false`, `ARBICORE_SHADOW_CERT_ENABLED=true`, `ARBICORE_BORROW_SIZER_ENABLED=true`, `ARBICORE_PRICE_FEED_ENABLED=true`, `ARBICORE_FLASH_LOAN_SHADOW_ROUTE=true` on both merges. |

Extra non-identity env diffs: **0**. Gate result: **PASS**. The container was not recreated again.

---

## Result

| Field | Value |
|---|---|
| **Classification** | `PHASE_0_RUNTIME_DEPLOYED` |
| **Deployed commit** | `823a79b617ddb1f19397cf5073b9c516aae4e9fd` |
| **Image** | `arbicore-x-backend:phase0-823a79b` |
| **Image id** | `sha256:768b4410a07843a11ddeda6fde31491cd4108eb00fd559099098627a9adb32a4` |
| **Container** | `arbicore-x-backend-new` `096bcb87b121e9c56758c51c340b684d299ba9505442be60901540e9d279ea33` |
| **New PID** | `2823992` |
| **Old PID** | `1698122` |
| **Restart count** | `0` on the new container (recreate, not an in-process restart) |
| **Started** | `2026-10-04T15:14:34.569825639Z` |
| **Health** | `healthy` |
| **BUILD_INFO git_sha** | `823a79b617ddb1f19397cf5073b9c516aae4e9fd` |
| **GET /api/arbicore/version git_sha** | `823a79b617ddb1f19397cf5073b9c516aae4e9fd` |
| **git_tag** | `phase0-823a79b` |
| **Smoke** | `PASS` 20/20 inside the new container |
| **Network Config revision** | `rev-1068cb9715194f118c99e5f04f9e1bdb` (unchanged, `updated_at=2026-10-04T14:24:36.649620+00:00`, `updated_by=admin`) |
| **Fingerprints** | A `dc432a6b`, B `6e67e161`, C `cd505118`, D `124bc59c` |
| **Topology** | NEW A → NEW B → OLD A → OLD B on all six chains |
| **Chain IDs** | Ethereum `1`, Optimism `10`, BNB `56`, Polygon `137`, Base `8453`, Arbitrum `42161` |
| **Execution** | `ARBICORE_EXECUTION_MODE=SHADOW`. Signing unset. Broadcast unset. Every strategy `broadcast_allowed=false`. |
| **Phase 1** | Not started |

---

## Pre-deploy record

Captured `2026-10-04T14:58Z` from the still-running previous container, before the image build finished and again immediately before recreate.

| Field | Value |
|---|---|
| **Image** | `arbicore-x-backend:b1b2-62ec784` |
| **Image id** | `sha256:25dd0905b70e728f333aca170706299f420fc94dc7204dd7ae183df792a687fb` |
| **Container id** | `27b930baa7c2b8ff07f952036185d7c66e433a463cc9a7849a19fa4312fb5c95` |
| **PID** | `1698122` |
| **Started** | `2026-10-04T08:28:21.865915247Z` |
| **Restart count** | `0` |
| **Health** | `healthy` |
| **git_sha** | `62ec7844cdec9517b10a5d40378bd1c5aacc9551` |
| **git_tag** | `b1b2-62ec784` |
| **Network Config revision** | `rev-1068cb9715194f118c99e5f04f9e1bdb` |
| **updated_at** | `2026-10-04T14:24:36.649620+00:00` |
| **Execution mode** | `ARBICORE_EXECUTION_MODE=SHADOW` |
| **AUTOEXEC / RUNTIME** | `ARBICORE_AUTOEXEC_AUTOSTART=false`, `ARBICORE_RUNTIME_AUTOSTART=false` |
| **Scanner** | Continuous scanner `running=true`, interval `90s`. `ARBICORE_SCANNER_AUTOSTART=true`. Per-scanner flags `CEX/DEX/FUNDING/LAUNCH=false`. Cross-chain and flash-loan scanner env flags unset. |
| **Signing** | `ARBICORE_ENABLE_SIGNING` and `ENABLE_SIGNING` unset |
| **Broadcasting** | `ARBICORE_ENABLE_BROADCAST` and `ENABLE_BROADCAST` unset. Strategy modes: `flash_loan_arbitrage=SHADOW`, all others `PAPER`. `broadcast_allowed=false` for every strategy. `auto_execute_enabled=false` (`rev-35aaafa0454f4a2d8c9aa7b750a2c803`) |
| **Shadow window** | `ARBICORE_SHADOW_CERT_AUTOSTART_RUN` unset. No new run was issued. |

Fingerprints and chain enablement at this snapshot matched the post-deploy table below.

---

## Build

The image was built from the clean worktree `/tmp/arbicore-b1b2-reconcile-9ed2718`, which was at exactly `823a79b617ddb1f19397cf5073b9c516aae4e9fd` with a clean status. Parent is `62ec7844cdec9517b10a5d40378bd1c5aacc9551`. The commit diff against that parent is the Phase 0 observability package only:

- `app/backend/arbicore/observability/__init__.py`
- `app/backend/arbicore/observability/economics_observation.py`
- `app/backend/arbicore/observability/fields.py`
- `app/backend/arbicore/observability/record.py`
- `app/backend/arbicore/observability/taxonomy.py`
- `app/backend/tests/test_phase0_strategy_intelligence.py`
- `docs/certification/PHASE_0_STRATEGY_INTELLIGENCE_ECONOMICS_IMPLEMENTATION_20261004.md`

The dirty primary worktree `/home/raghu/projects/arbicore-x-cert` was not the build context. No other branch was merged.

```text
docker build --network=host \
  -f /tmp/arbicore-b1b2-reconcile-9ed2718/deployment/upgrade/backend/Dockerfile \
  --build-arg GITSHA=823a79b617ddb1f19397cf5073b9c516aae4e9fd \
  --build-arg GITTAG=phase0-823a79b \
  --build-arg BUILD_TIME=2026-10-04T14:58:40Z \
  --build-arg APP_VERSION=phase0-823a79b \
  --build-arg ARBICORE_GIT_SHA=823a79b617ddb1f19397cf5073b9c516aae4e9fd \
  --build-arg ARBICORE_GIT_TAG=phase0-823a79b \
  -t arbicore-x-backend:phase0-823a79b \
  /tmp/arbicore-b1b2-reconcile-9ed2718/app/backend
```

`scripts.gen_build_info` wrote `/app/BUILD_INFO.json` with `git_sha=823a79b617ddb1f19397cf5073b9c516aae4e9fd` and `git_tag=phase0-823a79b`. Build exit code `0`.

The backend `.dockerignore` excludes `tests/`, so the Phase 0 test module is not in the image. The five observability modules are.

---

## Recreate

Same mechanism as the `b1b2-62ec784` deploy. Working directory `/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose`. Compose files: `docker-compose.prod.yml` plus `/tmp/arbicore-phase0-823a79b-override.yml`.

The override changes only the image tag, `ARBICORE_GIT_SHA`, and `ARBICORE_GIT_TAG`. It keeps the previous override's safety flags:

- `ARBICORE_EXECUTION_MODE=SHADOW`
- `ARBICORE_AUTOEXEC_AUTOSTART=false`
- `ARBICORE_RUNTIME_AUTOSTART=false`
- `ARBICORE_SCANNER_AUTOSTART=true`
- `ARBICORE_SHADOW_CERT_ENABLED=true`
- `ARBICORE_BORROW_SIZER_ENABLED=true`
- `ARBICORE_PRICE_FEED_ENABLED=true`
- `ARBICORE_FLASH_LOAN_SHADOW_ROUTE=true`

`env_file` `deployment/upgrade/backend/.env` was not edited. Network Config in Mongo was not written.

```text
docker compose --env-file .env \
  -f docker-compose.prod.yml \
  -f /tmp/arbicore-phase0-823a79b-override.yml \
  up -d --no-deps --force-recreate --no-build backend
```

Only `arbicore-x-backend-new` was recreated (`2026-10-04T15:14:19+02:00` local). Unrelated containers kept their previous start times and PIDs, including `arbicore-x-frontend` (`51a592aaa98f`, PID `3076179`, started `2026-10-03T14:24:18Z`), `caddy` (PID `2866`), and `arbicore-x-nginx` (PID `2631`).

| | Before | After |
|---|---|---|
| Container | `27b930baa7c2…` | `096bcb87b121…` |
| PID | `1698122` | `2823992` |
| Restart count | `0` | `0` |
| Image | `arbicore-x-backend:b1b2-62ec784` | `arbicore-x-backend:phase0-823a79b` |

---

## Post-deploy identity

Running container files:

| Path | Present | Bytes |
|---|---|---|
| `/app/arbicore/observability/__init__.py` | yes | 508 |
| `/app/arbicore/observability/fields.py` | yes | 2794 |
| `/app/arbicore/observability/taxonomy.py` | yes | 32206 |
| `/app/arbicore/observability/economics_observation.py` | yes | 20057 |
| `/app/arbicore/observability/record.py` | yes | 3048 |

`/app/BUILD_INFO.json` and `GET /api/arbicore/version` both report `git_sha=823a79b617ddb1f19397cf5073b9c516aae4e9fd` and `git_tag=phase0-823a79b`.

`ARBICORE_VERSION` and `ARBICORE_BUILD_TIME` in the process environment are still the pre-existing env_file values `arbicore-x-cert-baseline-99059c0-20260914-dirty` and `2026-09-14T09:11:11Z`. Those keys were not part of this override and the env file was not edited. The version endpoint surfaces those two fields from the environment. The commit identity is the git SHA above.

---

## Smoke

Ran inside `arbicore-x-backend-new` with `python -`. It imported `observe_strategy_intelligence` from `arbicore.observability` and called it on in-memory bundles shaped like the m2.3 verifier schema (`schema_version=m2.3`, `source_component=flash_loan_arb_verifier`, route, hop legs, economics, fees, gas, gates). No SHADOW window was started. No scanner resume or enable call was made.

| Check | Result |
|---|---|
| Two-leg explicit protocols classify `DEX_TO_DEX` | `COMPLETE` / `FULLY_CLASSIFIED` |
| Secondary tags include `CROSS_PROTOCOL` only with explicit per-leg protocols | `CROSS_POOL`, `CROSS_PROTOCOL` |
| Per-leg evidence | leg 0 `uniswap_v3`, leg 1 `sushiswap_v3`; evidence text records distinct per-leg protocols |
| Economics observation | completeness `PARTIAL`; `true_net_usd=-83.691492` |
| Missing slippage, gas units, and gross profit USD | `value=null`, status `unavailable` (not zero) |
| Stored numeric zero | slippage `0.0` and flash-loan fee USD `0.0` stay zero |
| Flash-loan fee percent absent from the bundle | stays `null` (`AVAILABLE_NOT_PERSISTED`) |
| Venue ids and pool ids without `dex_protocol` / `route_dex_protocols` | `UNCLASSIFIED` / `INCOMPLETE`; `CROSS_PROTOCOL` absent |
| Explicit `uniswap_v3` / `aerodrome` / `uniswap_v3` | primary family `CROSS_PROTOCOL`; three leg protocols match |

**Smoke result: PASS 20/20. Exit code 0.**

---

## Network Config and chains

Unchanged after recreate. No draft is present.

| Chain | Chain ID | Enabled | Host | Order |
|---|---|---|---|---|
| Ethereum | 1 | true | `eth-mainnet.g.alchemy.com` | `dc432a6b`, `6e67e161`, `cd505118`, `124bc59c` |
| Arbitrum | 42161 | true | `arb-mainnet.g.alchemy.com` | same |
| Base | 8453 | true | `base-mainnet.g.alchemy.com` | same |
| Optimism | 10 | true | `opt-mainnet.g.alchemy.com` | same |
| Polygon | 137 | true | `polygon-mainnet.g.alchemy.com` | same |
| BNB | 56 | true | `bnb-mainnet.g.alchemy.com` | same |

Each list length is 4. All six sequences are identical. Chain IDs are the running image's `EXPECTED_CHAIN_IDS`. Supported chains remain `base`, `ethereum`, `arbitrum`, `optimism`, `polygon`, `bnb`.

Execution settings revision is still `rev-35aaafa0454f4a2d8c9aa7b750a2c803` (`updated_at=2026-09-07T05:24:08.858259+00:00`, `updated_by=system:boot`). `auto_execute_enabled=false`.

---

## Safety after boot

The recreate starts the process, so the existing boot path ran again. No start, resume, or campaign API was called.

| Control | After |
|---|---|
| `ARBICORE_EXECUTION_MODE` | `SHADOW` |
| `ARBICORE_AUTOEXEC_AUTOSTART` | `false` |
| `ARBICORE_RUNTIME_AUTOSTART` | `false` (log: runtime autostart disabled) |
| `ARBICORE_SCANNER_AUTOSTART` | `true` (unchanged; continuous scanner was already running and started again on boot, interval 90s) |
| Wave 1B scanners | `running=[]`, boot dormant. CEX/DEX/funding/launch flags remain `false`. |
| Canonical flash-loan scanner | `enabled=false`, `mode=SHADOW`, `detection_only=true`. Not resumed. |
| `ARBICORE_SHADOW_CERT_ENABLED` | `true` (runner process started, same flag as before) |
| `ARBICORE_SHADOW_CERT_AUTOSTART_RUN` | unset. No log of an auto-started certification run. |
| Signing | unset |
| Broadcasting | unset. No strategy is `LIMITED_LIVE` or `FULL_LIVE`. |
| T2 searcher | constructed `SHADOW, no-broadcast` from the pre-existing `ARBICORE_T2_SEARCHER_ENABLED` flag |

`PaperValidationRunner` and `ShadowCertificationRunner` log lines appear because those enablement flags were already set on the previous container and were preserved. This pass did not open a SHADOW window and did not activate PAPER, recommendation, or LIVE.

---

## Stop

Phase 0 runtime is deployed. Phase 1 SHADOW was not started.
