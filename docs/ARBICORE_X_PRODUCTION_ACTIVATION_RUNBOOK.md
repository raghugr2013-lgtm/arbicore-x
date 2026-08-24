# ArbiCore X — Production Activation Runbook (canonical, generated from code)

Generated from the current canonical branch `flashloan-live-shadow` (do NOT push to `main`).
Everything below is inspected from the actual code — no roadmap assumptions.
**All operation is SHADOW-only until an operator explicitly and manually promotes.
No signing, no broadcast, `broadcast=false` everywhere in the current build.**

---

## 1. CURRENT SOFTWARE STATE

| Item | Value |
|---|---|
| Version (`/app/VERSION`) | **2.9.2** |
| Canonical Git HEAD (short) | `cc9874a` (`git describe` = `v2.9.2-123-gcc9874a`) |
| Docker image tag (derived) | `arbicore-x-backend:2.9.2-<shortsha>` (e.g. `2.9.2-cc9874a`) |
| Base image | `python:3.11-slim` + pinned **Foundry/Anvil v1.7.1** (SHA256-verified) |
| API health | `GET /api/` → 200; `GET /api/arbicore/version` → identity JSON |

**T2 runtime components (all implemented + tested):**
- `arbicore/searcher/route.py` — RouteGraph + closed-cycle enumeration + spot fast-filter
- `arbicore/searcher/amm_math.py` — V2 / V3 / StableSwap math kernels
- `arbicore/searcher/pool_cache.py` — log-synced cache + block-staleness refusal
- `arbicore/searcher/simulation.py` — LocalMath backend + honest REVM stub + two-stage pipeline
- `arbicore/searcher/revm_backend.py` — `AnvilRevmForkBackend` + `make_calldata_tx_builder` (canonical `execute()` calldata)
- `arbicore/searcher/runtime.py` — `BaseSearcherRuntime` (Gate7/Gate8, REAL provenance)
- `arbicore/searcher/live_base.py` — readiness, dry-run audit, 5-cat audit, `BaseWssSubscriber`
- `arbicore/searcher/wss_ingest.py` — **NEW** `BaseWssClient` + `T2WssManager` (lifecycle + reconnect + telemetry)

**WSS subscriber/manager:** `T2WssManager` starts at app boot when `ARBICORE_T2_SEARCHER_ENABLED` + a WSS url are set; feeds `newHeads`→`scan_block` and Sync `logs`→`ingest_log`; telemetry via `GET /api/arbicore/engine/base-live-shadow/wss-status`.

**Existing scanners (flag-gated):** CEX arb, DEX arb, Flash-Loan arb (canonical), Funding arb, Cross-chain arb, Launch arb + always-on read-only `ContinuousScanner` (OpportunityEngine).

**Opportunity/MEV families IMPLEMENTED (Base):** `same_dex_fee_tier`, `cross_dex`, `triangular`, `stablecoin_triangular`, `multi_hop`, `flash_loan_arbitrage` (atomic). Backrun/liquidation/cross-chain execution families are **NOT implemented** (cross-chain/CEX/funding exist as discovery scanners only).

**Supported chains:** **Base** (`BaseChainAdapter`, chainId 8453) — the only implemented execution chain. `ChainAdapter` is a generic seam; **no `ArbitrumChainAdapter` exists yet**.

**Supported DEXs/venues:** Uniswap V3 (SwapRouter02 — the ONLY executor-runnable venue: `EXECUTABLE_UNIV3`), Aerodrome SlipStream + classic (quoting + settlement encoder; **not** executor-runnable). Curve/Balancer-swap/Jupiter quoting exists off-path.

**Flash-loan providers:** `balancer_v2` (0 bps), `morpho_blue` (0 bps), `aave_v3` (5 bps). Selection = cheapest feasible with KNOWN borrow liquidity.

**Operating modes:** `SHADOW`, `PAPER`, `PROFIT_ENGINE` (all NON-broadcast), `LIMITED_LIVE`, `FULL_AUTOMATION` (both hard-locked / operator-gated). Default persisted mode = **SHADOW**.

---

## 2. CONFIGURATION INVENTORY

Secrets identified by NAME only (never printed). Files: `deployment/upgrade/backend/.env` (runtime, baked from live container + T2 wiring), `deployment/upgrade/compose/.env` (build), `deploy.env`.

| VARIABLE | PURPOSE | REQUIRED? | SOURCE | EXAMPLE FORMAT | SAFE TO CHANGE ON VPS? | RESTART? |
|---|---|---|---|---|---|---|
| `MONGO_URL` (secret) | Mongo connection (factory-mongo) | YES | live container | `mongodb://user:***@factory-mongo:27017/...` | NO (authoritative) | YES |
| `DB_NAME` | App database | YES | live container | `arbicore_x` | NO | YES |
| `JWT_SECRET` (secret) | Operator auth signing | YES | env | `<random>` | change rotates sessions | YES |
| `VAULT_KEY` (secret) | Fernet key for signer vault | for signer | env | Fernet key | NO (rotating orphans ciphertext) | YES |
| `ARBICORE_RPC_URL_BASE` | Base read-only eth_call RPC | YES (T2) | live container | `https://base-mainnet.<provider>/v2/<key>` | YES | YES |
| `ARBICORE_RPC_URL` | Generic/legacy RPC fallback | optional | env | `https://mainnet.base.org` | YES | YES |
| `ARBICORE_ARCHIVE_RPC_URL` | Archive/fork RPC for anvil | for fork sim | env | `https://base-archive.<provider>/<key>` | YES | YES |
| `ARBICORE_WSS_URL_BASE` (secret if keyed) | **PRIMARY** Base WSS for T2 ingestion | YES (T2) | detect override / live | `wss://base-mainnet.<provider>/v2/<key>` | YES | YES |
| `ARBICORE_RPC_WSS_BASE` (secret if keyed) | Fallback Base WSS | optional | env | `wss://.../ws` | YES | YES |
| `ARBICORE_T2_SEARCHER_ENABLED` | Activate T2 SHADOW runtime + WSS | YES | 00_detect_env (default true) | `true` | YES | YES |
| `ARBICORE_EXECUTOR_ADDRESS_BASE` | Deployed FlashLoanReceiver | for sim/live | env | `0x91c0…3DE3` | YES | YES |
| `ARBICORE_EXECUTOR_ENTRYPOINT_SIG` | Executor entrypoint sig | optional | env | `execute(address[],uint256[],bytes)` | YES | YES |
| `ARBICORE_GAS_WALLET_ADDRESS` | Gas/profit-recipient (PUBLIC) | for sim/live | env | `0x998d…ad25` | YES | YES |
| Signer key (secret, in vault) | Execution signer | LIMITED_LIVE only | vault `arbicore_secrets` | (never in env) | operator-only | YES |
| `ARBICORE_ANVIL_PATH` | anvil binary path | optional | env | `anvil` | YES | YES |
| `ARBICORE_ANVIL_PORT` / `ARBICORE_FORK_RPC_URL` | fork sim | optional | env | `8546` / url | YES | YES |
| `ARBICORE_NATIVE_PRICE_USD` | Native price seed (fallback) | optional | env | `3000` | YES | YES |
| `ARBICORE_ETHERSCAN_API_KEY` (secret) | Capital statement source | optional | env | `<key>` | YES | YES |
| `ARBICORE_RPC_MIN_INTERVAL_MS` / `ARBICORE_RPC_MAX_RETRIES` | RPC throttle/backoff | optional | env | `140` / `4` | YES | YES |
| `ARBICORE_GAS_PRICE_GWEI` / `ARBICORE_MAX_FEE_GWEI` / `ARBICORE_PRIO_FEE_GWEI` | gas modeling | optional | env | `0.02` | YES | YES |
| `ARBICORE_SAFETY_KILL_DEFAULT` | Kill switch default | SAFETY | env | `true` (engaged) | with care | YES |
| `ARBICORE_SAFETY_LIVE_EXECUTION_ENABLED` | Master live-exec lock | SAFETY | env | `false` | operator-gated | YES |
| `ARBICORE_SAFETY_MAX_PER_TRADE_USD` | Capital cap / trade | SAFETY | env | `500` | operator-gated | YES |
| `ARBICORE_SAFETY_MAX_DAILY_NOTIONAL_USD` | Daily notional cap | SAFETY | env | `5000` | operator-gated | YES |
| `ARBICORE_SAFETY_MAX_PER_CHAIN_USD` / `..._PER_TYPE_CAPS_USD` | Per-chain / per-family caps | SAFETY | env | `2000` / json | operator-gated | YES |
| `ARBICORE_SAFETY_REQUIRE_APPROVAL` / `..._REQUIRE_PAPER_VALIDATION` | Promotion gates | SAFETY | env | `true` | operator-gated | YES |
| `ARBICORE_SCANNER_*` (`FLASH_LOAN_ARB`, `DEX_ARB`, `CEX_ARB`, `FUNDING_ARB`, `CROSS_CHAIN_ARB`, `LAUNCH_ARB`, `AUTOSTART`) | Scanner enables | optional | env | `on` | YES | YES |
| `ARBICORE_AUTOEXEC_*` (`AUTOSTART`, `INTERVAL_S`, `MIN_CONF`, `BATCH`, `LEARN_EVERY`) | Auto-executor (mode-gated; no broadcast < LIMITED_LIVE) | optional | env | `false` / nums | operator-gated | YES |
| `ARBICORE_SHADOW_CERT_*` | Shadow certification runner | optional | env | `true` / secs | YES | YES |
| `ARBICORE_PAPER_VALIDATION_ENABLED` | Paper validation runner | for PAPER | env | `true` | YES | YES |
| `ARBICORE_MEV_RELAY_URL` | MEV relay (unused < LIMITED_LIVE) | optional | env | url | YES | YES |
| `ARBICORE_CANONICAL_STRICT_PROVENANCE` | REAL-only write gate | SAFETY | env | `true` | keep true | YES |
| `ARBICORE_GIT_SHA/GIT_TAG/BUILD_TIME/VERSION/IMAGE_DIGEST` | Build identity | auto | Dockerfile ARG | — | build-time | — |

---

## 3. CHAIN ACTIVATION MATRIX (only what exists)

| CHAIN | RPC | ARCHIVE | WSS | DEXES | FLASH PROVIDERS | EXECUTOR | TOKEN UNIVERSE | SEARCHERS | MEV FAMILIES | SIMULATION | STATUS | BLOCKER |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Base (8453)** | `ARBICORE_RPC_URL_BASE` ✅ | `ARBICORE_ARCHIVE_RPC_URL` (opt) | `ARBICORE_WSS_URL_BASE` ✅ (T2) | UniV3 (executable), Aerodrome SlipStream+classic (quote/settle) | balancer_v2 (0), morpho_blue (0), aave_v3 (5bps) | FlashLoanReceiver `0x91c0…3DE3` (`execute` 0x64ba4bc1) | 12 verified ERC-20s (WETH,USDC,cbETH,DAI,USDbC,cbBTC,AERO,USDT,rETH,wstETH,weETH,DEGEN); borrow WETH/USDC/cbETH/USDbC | T2 BaseSearcherRuntime + ContinuousScanner + flash_loan_arb | cross_dex, triangular, stablecoin_triangular, multi_hop, fee-tier, flash-loan atomic | LocalMath + Anvil REVM fork (v1.7.1) | **SHADOW ACTIVE** | VALIDATION: real fork-sim PASS + a profitable UniV3 route (MARKET) |
| Arbitrum | — | — | — | — | — | — | — | — | — | — | **NOT IMPLEMENTED** | `ArbitrumChainAdapter` not written (only the generic `ChainAdapter` seam exists) |
| Other (ETH/OP/Polygon) | calldata addrs only | — | — | — | balancer/aave pool addrs exist in encoder maps | — | — | — | — | — | **NOT IMPLEMENTED** | no adapter/searcher wired |

---

## 4. CAPABILITY ACTIVATION MATRIX

| CAPABILITY | IMPLEMENTED | CONFIGURED | SHADOW | PAPER | LIMITED-LIVE | FULL-AUTO | BLOCKER |
|---|---|---|---|---|---|---|---|
| Arbitrage (generic) | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | operator promotion + safety unlock |
| Flash-loan arbitrage (atomic) | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | fork-sim PASS + profitable route + signer |
| Cross-DEX | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | market spread ≥ costs |
| Triangular | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | market |
| Stablecoin (triangular) | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | market |
| CL / concentrated liquidity (UniV3) | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | executor UniV3-only alignment ✔; market |
| Multi-hop | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | market |
| MEV / backrun | ❌ | — | — | — | — | — | not implemented |
| Liquidation | ❌ | — | — | — | — | — | not implemented |
| Cross-chain opportunities | discovery-only | partial | scan-only | ❌ | ❌ | ❌ | no execution path |
| CEX/DEX, funding, launch | discovery-only | flag | scan-only | ❌ | ❌ | ❌ | detection scanners only |

---

## 5. READINESS GATES (from `arbicore/control/readiness.py` + `live_base.base_live_shadow_audit`)

| GATE | CATEGORY | CONDITION | EVIDENCE | CURRENT STATE | HOW TO SATISFY |
|---|---|---|---|---|---|
| route/amm/cache/localsim/encoder/tx_builder/revm/bridge/wss | SOFTWARE | code present + self-test | selectors/tests | **COMPLETE (9/9)** | done |
| CONFIGURATION_RPC | CONFIG | Base RPC set | env | PRESENT on VPS | keep set |
| T2 flag + WSS | CONFIG | flag=true + WSS url | preflight gate | wire on VPS | `ARBICORE_WSS_URL_BASE=wss://…` |
| executor + gas wallet | CONFIG | env addrs | on-chain code check | PRESENT on VPS | keep set |
| SIGNER / WALLET_SIGNER | CONFIG | vault signer + addr match | vault handle | operator-only | store signer in vault (LIMITED_LIVE) |
| SETTLEMENT/STATE-OVERRIDE/HISTORICAL | VALIDATION | real eth_call/replay | live run | GREEN when RPC set | provide archive RPC |
| FORK_VALIDATION | VALIDATION | anvil fork run passes | ran=true/passed=true | READY (anvil in image) | run on VPS |
| SIMULATION_ONCHAIN / fork_simulation_run | VALIDATION | atomic sim repays > $25 | passing sim | **BLOCKED** (needs run + profit) | profitable route + fork run |
| profitable_route_exists | MARKET | REAL route clears costs+$25 | alert record | **PENDING_EVIDENCE** | wait for real spread |
| Gate 7 ($25 floor) | SAFETY | atomic net ≥ $25 | — | ENFORCED | immutable |
| Gate 8 (liquidity) | SAFETY | verifiable TVL | — | ENFORCED (fail-closed) | immutable |
| shadow_only / no_broadcast | SAFETY | broadcast=false | — | ENFORCED | immutable until promotion |
| real_provenance_only | SAFETY | REAL/VERIFIED only | write-gate | ENFORCED | keep strict |
| no_auto_promotion | SAFETY | LIMITED_LIVE/FULL locked | can_activate=false | ENFORCED | operator manual |

---

## 6. OPERATING MODES & TRANSITIONS

Backend-authoritative (`ControlStateRepo`, default **SHADOW**). Frontend can only REQUEST; backend decides.

- **SHADOW** — discovery + quote + economics + Gate7/Gate8 + fork sim; **no broadcast, no signing**. Prohibited: any tx send. Set `mode=SHADOW` (default).
- **PAPER** — same + records paper evidence for calibration (`ARBICORE_PAPER_VALIDATION_ENABLED=true`). Still non-broadcast.
- **PROFIT_ENGINE** — continuous ranking within the current exec mode. Still non-broadcast (in `NON_BROADCAST_MODES`).
- **LIMITED_LIVE** — HARD-LOCKED in this build (`can_activate=false`). Requires: signer in vault, funded gas wallet, executor allowlisted, `ARBICORE_SAFETY_LIVE_EXECUTION_ENABLED=true`, kill switch DISENGAGED, capital caps set, **a fork-sim PASS + a profitable route**, and an explicit operator mode POST. Broadcast becomes possible only here.
- **FULL_AUTOMATION** — HARD-LOCKED; adds autonomous auto-exec loop under capital/mode policy. No per-opp approval; still bounded by safety caps.

Control API (operator-auth): `GET /api/arbicore/control/readiness`, `GET/POST /api/arbicore/control/mode`, `GET /api/arbicore/control/profit-preview`, `POST /api/arbicore/control/decide-opportunity`. **No code-mandated 24h/72h waits** — promotion is gated by evidence + safety, not time.

---

## 7. LIVE MONITORING (commands)

Auth once: `TOKEN cookie` via `POST /api/auth/login`. `API=<backend-url>`.

| Signal | Command |
|---|---|
| WSS connection / reconnects / last_block / blocks_scanned / logs_ingested | `curl -s -b cj $API/api/arbicore/engine/base-live-shadow/wss-status` |
| T2 software/config/validation/market/safety audit | `curl -s -b cj $API/api/arbicore/engine/base-live-shadow/audit` |
| Readiness (both surfaces) | `curl -s -b cj $API/api/arbicore/control/readiness` ; `.../engine/readiness-matrix` |
| Scanner + funnel (candidates/quotes/positive/executable) | `curl -s -b cj $API/api/arbicore/engine/scanner/status` ; `.../engine/checkpoint` |
| Opportunities / recurring / alerts | `.../engine/opportunities` ; `.../engine/recurring` ; `.../engine/alerts` |
| Dry-run decoded canonical tx (SHADOW) | `.../engine/base-live-shadow/dry-run` |
| Gate 7 / Gate 8 rejections | scanner funnel `gate7_rejected`/`gate8_rejected` + decision history |
| Simulations (fork/atomic) | `POST .../engine/run-fork-validation` ; `POST .../engine/run-atomic-sim` (signed=false) |
| P&L / balances / money-trail | `.../capital/overview` ; `.../capital/balances` ; `.../capital/money-trail?tx_hash=` |
| Safety state / kill switch | `.../control/readiness` (kill), `.../control/mode` |
| Container / anvil | `docker logs <backend> --tail=200` ; `docker exec <backend> anvil --version` |
| Mongo evidence | `docker exec <mongo> mongosh arbicore_x --quiet --eval 'db.arbicore_paper_evidence.countDocuments()'` |
| Errors / latency / stale | backend logs grep `WSS|reconnect|scan_block|stale`; funnel `stale_hops`, `scan_latency_ms` |

---

## 8. ACTIVATION PROCEDURE (forward from current deployed state)

```
# 1. Git — land the canonical branch (use Emergent "Save to GitHub" → flashloan-live-shadow), then on VPS:
git fetch && git checkout flashloan-live-shadow && git pull
# 2. Configure Base WSS (operator secret) + confirm RPC/executor/gas present:
export ARBICORE_WSS_URL_BASE="wss://base-mainnet.<provider>/v2/<key>"
# 3. Detect env (wires T2 flag + WSS; VERSION from repo root; Mongo preserved):
bash deployment/upgrade/steps/00_detect_env.sh
# 4. Preflight (T2 gate fails closed if WSS missing):
bash deployment/upgrade/steps/01_preflight.sh
# 5. Backup + build:
bash deployment/upgrade/steps/02_backup.sh && bash deployment/upgrade/steps/05_build.sh
# 6. Cutover (additive, no down -v):
bash deployment/upgrade/steps/06_cutover.sh
# 7. Health:
curl -s http://127.0.0.1:8001/api/arbicore/version   # expect image 2.9.2-<sha>, anvil present
# 8. WSS SHADOW evidence:
curl -s -b cj $API/api/arbicore/engine/base-live-shadow/wss-status   # running=true, connected=true, blocks_scanned rising
# 9. Validation: run fork sim; watch Gate7/Gate8; accumulate REAL quotes.
# 10. Readiness → PAPER: set ARBICORE_PAPER_VALIDATION_ENABLED=true; POST control/mode {mode:PAPER}.
# 11. LIMITED_LIVE (manual, only when readiness allows): store signer, set safety caps + LIVE_EXECUTION_ENABLED=true, disengage kill switch, POST control/mode {mode:LIMITED_LIVE}.
# 12. FULL_AUTOMATION (manual): POST control/mode {mode:FULL_AUTOMATION} once LIMITED_LIVE proven.
```

---

## 9. TROUBLESHOOTING MATRIX

| SYMPTOM | CLASS | DIAGNOSIS | COMMAND | ACTION |
|---|---|---|---|---|
| `IMAGE_TAG=0.0.0-…` | CONFIG | VERSION path | `bash 00_detect_env.sh` | fixed: REPO_ROOT resolves `/VERSION` |
| Preflight dies "no Base WSS configured" | CONFIG | T2 on, WSS unset | check `backend/.env` | set `ARBICORE_WSS_URL_BASE` |
| wss-status `running=false` | CONFIG/SOFTWARE | flag off / import err | `docker logs` grep `T2` | set flag + WSS, restart |
| `connected=false`, reconnect_count climbing | CONFIG | bad/rate-limited WSS | logs `reconnect` | use dedicated provider WSS |
| blocks_scanned=0 but connected | MARKET/CONFIG | no newHeads / empty graph | wss-status | verify WSS subscription; seed pool graph |
| Gate7 rejects all | MARKET | net < $25 | funnel `gate7_rejected` | none — honest (no arb) |
| Gate8 rejects all | CONFIG/MARKET | TVL unverifiable | funnel `gate8_rejected` | wire TVL/price feed |
| atomic sim reverts | VALIDATION/MARKET | route unprofitable | `run-atomic-sim` | needs profitable route |
| anvil missing in container | SOFTWARE→fixed | image lacked anvil | `docker exec … anvil --version` | rebuild (v1.7.1 pinned) |
| `/api` 500 on boot | SOFTWARE/CONFIG | missing env | `docker logs` | set MONGO_URL/DB_NAME/JWT_SECRET |
| login 401 | CONFIG | seed creds | check `ARBICORE_ADMIN_*` | reseed on boot |
| broadcast attempted | SAFETY | must never happen | kill switch | engage kill; stay SHADOW |

---

## 10. ROLLBACK / EMERGENCY SHUTDOWN

- **Kill switch (immediate):** `POST /api/arbicore/control/*` engage kill → all broadcast Gate-1 denies. `ARBICORE_SAFETY_KILL_DEFAULT=true`.
- **Return to SHADOW:** `POST /api/arbicore/control/mode {mode:"SHADOW"}`.
- **Disable a chain:** unset that chain's RPC/WSS (Base: `ARBICORE_T2_SEARCHER_ENABLED=false`) + restart.
- **Disable an opportunity family / scanner:** `ARBICORE_SCANNER_<FAMILY>=off`.
- **Disable signing / live exec:** `ARBICORE_SAFETY_LIVE_EXECUTION_ENABLED=false`; remove signer via `DELETE /api/arbicore/engine/settings/signer`.
- **Rollback Docker image:** `docker compose … up -d` with the previous `IMAGE_TAG` (images are immutable tags `2.9.2-<sha>`).
- **Git rollback:** use Emergent **Rollback** to any prior checkpoint (free; non-destructive) — do NOT `git reset`.
- **DB/evidence preservation:** additive deploy only — never `down -v` / volume delete; `factory-mongo` + `arbicore_x` preserved; `02_backup.sh` before cutover.

---

## 11. AUTONOMOUS OPERATION

**Operator configures ONCE:** dedicated Base RPC + WSS, executor address + gas wallet, signer in vault, safety caps (`MAX_PER_TRADE/DAILY/CHAIN`, `PER_TYPE_CAPS`), promotion flags (`REQUIRE_APPROVAL`, `REQUIRE_PAPER_VALIDATION`), then promote mode.

**ArbiCore then runs autonomously (per block):**
`DISCOVER` (RouteGraph over verified venues) → `QUOTE` (live eth_call / WSS state) → `SCORE` (confidence v2) → `EV` (P(success)·net − P(fail)·max_loss) → `RISK` (size optimizer, depth-aware) → `POLICY` (capital/mode caps) → `SIMULATE` (LocalMath → Anvil fork atomic) → `EXECUTE` (only ≥ LIMITED_LIVE, mode+kill gated) → `RECORD` (decision history + evidence) → `LEARN` (calibration + adaptive weights).

**Remaining manual intervention:** (a) supplying the signer + funding gas; (b) the one-time explicit promotion to LIMITED_LIVE/FULL_AUTOMATION; (c) any capital-limit change. Everything else is autonomous.

---

## 12. FINAL ACTIVATION CHECKLIST

```
[x] SOFTWARE            — T2 runtime + WSS manager + calldata + fork backend complete & tested (0 regressions)
[~] CONFIGURATION       — Base RPC/executor/gas present on VPS; SET ARBICORE_WSS_URL_BASE + confirm T2 flag
[ ] VALIDATION          — run genuine anvil fork sim (fork_simulation_run BLOCKED→PASSED) on VPS
[x] SAFETY              — Gate7 $25, Gate8 fail-closed, SHADOW-only, no-broadcast, no-auto-promotion ENFORCED
[~] BASE                — SHADOW ACTIVE; awaiting WSS config + fork evidence + profitable route (MARKET)
[ ] ARBITRUM            — NOT implemented (no ArbitrumChainAdapter)
[ ] OTHER CHAINS        — NOT implemented
[ ] MEV                 — backrun/liquidation NOT implemented
[x] FLASH LOANS         — balancer_v2 / morpho_blue / aave_v3 wired (SHADOW)
[ ] SIGNING             — signer NOT provisioned (operator vault; LIMITED_LIVE only)
[~] MONITORING          — endpoints live; wire external alerting as desired
[ ] LIMITED LIVE        — locked (needs signer + safety unlock + fork PASS + profitable route)
[ ] FULL AUTONOMOUS     — locked (needs LIMITED_LIVE proven)
```

---

## STATUS SUMMARY

- **CURRENT STAGE:** Base **SHADOW** — software-complete, T2 WSS ingestion wired; awaiting VPS config + validation evidence.
- **CURRENT SOFTWARE BLOCKER:** **NONE.** T2 integration complete; 103/103 relevant tests + testing_agent iter4 (100%) pass.
- **CURRENT CONFIGURATION BLOCKERS:** set `ARBICORE_WSS_URL_BASE` (+ confirm `ARBICORE_T2_SEARCHER_ENABLED=true`) on the VPS; optionally dedicated RPC + archive RPC.
- **CURRENT VALIDATION BLOCKERS:** genuine anvil fork-sim PASS (`fork_simulation_run` BLOCKED→PASSED); requires anvil (now in image) + archive RPC.
- **CURRENT SAFETY LOCKS:** kill switch default-engaged; LIMITED_LIVE + FULL_AUTOMATION `can_activate=false`; live-exec + signing disabled; Gate7/Gate8/provenance enforced.
- **NEXT VPS ACTION:** Save-to-GitHub → pull on VPS → set `ARBICORE_WSS_URL_BASE` → `00_detect_env.sh` → `01_preflight.sh` → build → cutover → confirm `wss-status running=true, blocks_scanned rising`.
- **REMAINING EMERGENT (software) WORK:** NONE for T2 Base live-SHADOW. Further engineering is only for NEW scope (Aave executor variant, Arbitrum adapter, MEV/liquidation families) — none required to run Base SHADOW autonomously.
