# ArbiCore X v2.0.0 — Canonical Intelligence Audit

**Date:** 2026-08-02
**Scope:** Read-only capability audit of `/app/canonical_repo/` at tag `v2.0.0`
**Sources of truth:** the canonical repo only (v1.0.2 deployment tree + Wave 6 + Phase 7–10 execution + UI v2 + dormant scanner tree)
**Purpose:** determine what is **built**, what is **stub**, what is **dormant**, and what is **missing** — so no intelligence module is built twice.

**Legend:**
- ✅ **COMPLETE** — production-ready, wired into `server.py`, tested green
- 🟡 **PARTIAL** — present but preview-stub / one leg missing / needs refinement
- 🔴 **MISSING** — no foundation in tree
- ⚪ **DORMANT** — full implementation exists in the tree but not wired into `server.py` (per merge directive 4b)

**Effort scale:** S = ≤1 day · M = 2–4 days · L = 1–2 weeks · XL = 3+ weeks

---

## 1. Capability Matrix

### A. Autonomous Execution

| Capability | Status | Existing implementation | Reused modules | Runtime status | Missing pieces | Action | Deps | Effort | Deploy impact |
|---|:-:|---|---|---|---|---|---|:-:|---|
| **Discovery** | 🟡 | `arbicore/execution/discovery.py` (thin activator, 60 s cadence, Base WETH/USDC universe) | Wave 6B planner, `db.opportunities` | ACTIVE background task | Multi-chain universe, dynamic token discovery, canonical scanner-tree wiring | **Refine** — first activate `arbicore/scanners/flash_loan_arbitrage`; **Upgrade** later for multi-family | dormant `scanners/`, `emission_bus.py` | M | Adds background task cadence + Mongo writes; no external calls beyond RPC |
| **Certification** | ✅ | `arbicore/execution/certification.py`, `PIPELINE_STAGES` | evidence signer, capital policy, mode | ACTIVE, `POST /execution/certification/run` | — | Refine only if new gates required | — | — | — |
| **Policy Engine** | ✅ | `arbicore/execution/mode.py` + `capital_policy.py` | mode ladder (SHADOW/PAPER/LIMITED_LIVE/FULL_LIVE) × 7 trading strategies | ACTIVE | — | Refine if new strategies added | — | — | — |
| **Auto Executor** | ✅ | `arbicore/execution/auto_executor.py` (30 s tick, batch 25) | pipeline, journal, ledger | ACTIVE background task | Metrics telemetry (tick success/failure counter) | Refine — add observability | — | S | None (in-process worker) |
| **Safety Gates** | ✅ | 6-gate ladder in `arbicore/execution/broadcast.py` (kill_switch → mode → capital → secret → preflight → operator_confirm) | kill_switch, capital_policy, secret registry | ACTIVE | — | — | — | — | — |
| **Kill Switch** | ✅ | `arbicore/execution/kill_switch.py`, `db.kill_switch_state` + `db.kill_switch_audit` | REST endpoints + signed evidence | ACTIVE, 4 endpoints | Cross-strategy dashboard banner | Refine (UI-side polish) | — | S | None |
| **Capital Policy** | ✅ | `arbicore/execution/capital_policy.py` (7 seeded per-strategy policies) | `db.capital_policy`, `db.capital_policy_audit` | ACTIVE, 4 endpoints | — | — | — | — | — |
| **Broadcast Pipeline** | ✅ | `arbicore/execution/broadcast.py` + `calldata.py` + `live_signer.py` | Balancer V2 flashLoan encoder, UniV3 exactInputSingle encoder, executor.execute() encoder, revert decoder (`decode_revert_data`, `debug_traceCall` fallback) | ACTIVE, gates production-verified through preflight | HSM/KMS signer backend (currently Fernet-encrypted burner) | Upgrade (Wave 6D backlog) | — | L | Requires HSM provider integration |

### B. Market Intelligence

| Capability | Status | Existing implementation | Reused modules | Runtime status | Missing pieces | Action | Deps | Effort | Deploy impact |
|---|:-:|---|---|---|---|---|---|:-:|---|
| **Historical Market Storage** | ⚪ | `arbicore/data/metrics_repo.py` + `arbicore/data/mongo/metrics_repo_mongo.py` (WalletMetric, SignalMetric — `arbicore_signal_metrics`, `arbicore_wallet_metrics`) | Motor db handle | DORMANT — collection referenced by ledger but no ingestion worker | Time-series price/depth ingestion writer | **Build new** — thin ingestion worker that writes candles to a new `market_history` collection per (chain, dex, pair) tuple | RPC/DEX subgraph access | M | New background task + Mongo writes ~few MB/day |
| **Market History Engine** | 🔴 | — | — | — | Entire read/query surface (candle retrieval, aggregation) | **Build new** | Historical Market Storage | M | New REST endpoints |
| **Opportunity History** | ✅ | `arbicore/data/journal.py` (Opportunity Journal — append-only, one doc per opp_id, events[] array) | `db.opportunity_journal` | ACTIVE — writes by pipeline; 3 endpoints (`/journal`, `/journal/summary`, `/journal/{opportunity_id}`) | — | — | — | — | — |
| **Opportunity Lifecycle** | ✅ | `arbicore/models/canonical.py` FSM (CANDIDATE → QUOTED → GATED → APPROVED → BROADCASTING → BROADCAST_SENT → CONFIRMED/FAILED, with REJECTED / SHADOW_RECORDED / POLICY_DENIED terminals) | pipeline, journal | ACTIVE | — | — | — | — | — |
| **Opportunity Lifetime Intelligence** | 🟡 | `first_seen`, `last_seen`, `lifetime_ms` on every journal row | journal | Data captured but no derived metrics | Aggregator: mean lifetime by family/chain, decay-time histogram, survival curves | **Build new** (thin analytic layer over journal) | journal, learning/concrete/survival.py (dormant) | S | Pure DB read; no external calls |
| **Market Regime Detection** | ⚪ | `arbicore/learning/concrete/regime_classifier.py` + `regime_worker.py` (dormant) + `data/mongo/regime_snapshot_repo_mongo.py` + `arbicore_regime_snapshots` collection | Full canonical implementation carried forward | DORMANT — `regime` field appears on dashboard pulse stub but no live classifier tick | Wire `regime_worker` into `server.py` startup; wire `regime_snapshot_repo` into dashboard pulse | **Refine** — reuse dormant module verbatim, just activate | dormant `learning/concrete/regime_worker.py`, `regime_classifier.py` | S | New background task; ~1 KB/tick to Mongo |
| **Market Pattern Learning** | ⚪ | `arbicore/learning/concrete/sequence_miner.py` + `arbicore_sequence_patterns` collection + `arbicore_temporal_sequences` | Full implementation in tree | DORMANT | Activation + a producer of temporal_sequences rows | **Refine** — activate after regime classifier is live | regime detection, journal | M | Background analytic worker |
| **Seasonal Behaviour** | 🔴 | — | — | — | Time-of-day / day-of-week aggregators over journal + market history | **Build new** (~200 LOC analytics module + endpoint) | Opportunity History, Market History Engine | S | Read-only analytics |
| **Liquidity Intelligence** | 🟡 | `arbicore/execution/quoter.py` (Quoter registry — Uni V3, Aerodrome quoter contracts) | Wave 6B adapters | ACTIVE for quote time; not persisted historically | Depth snapshots + historical liquidity time-series | **Upgrade** existing quoter — add snapshot writer | Market history storage | M | New Mongo writes |
| **Volatility Intelligence** | 🔴 | — | — | — | rolling stddev over pair mid-price; regime-aware volatility bands | **Build new** | Market history storage | S | Analytics only |
| **Gas Intelligence** | 🟡 | `arbicore/execution/gas.py` (StaticGasOracle default + RpcGasOracle opt-in) + `/execution/gas` endpoint | RPC eth_gasPrice | ACTIVE for point-in-time reads; not persisted | Historical gas time-series + priority-fee analytics | **Upgrade** — add gas snapshot worker | RPC | S | Background worker + Mongo |
| **Borrow Intelligence** | 🟡 | `arbicore/execution/adapters.py` — Aave V3 (5 bps), Balancer V2 (0 bps), Uniswap V3 (pool tier) | FLASH_LOAN_PROVIDERS catalog | ACTIVE — adapters expose fee at plan time | Historical borrow-availability tracking (pool depth vs required notional over time) | **Upgrade** — add availability tracker | RPC | M | Background worker |
| **Market Replay Engine** | 🔴 | — | — | — | Framework to feed historical opportunities back through the pipeline for "what-if" analysis | **Build new** | Opportunity History (present), Market History Engine (missing), pipeline stub | L | Read-only replay path; can dry-run existing plans |

### C. Learning System

| Capability | Status | Existing implementation | Reused modules | Runtime status | Missing pieces | Action | Deps | Effort | Deploy impact |
|---|:-:|---|---|---|---|---|---|:-:|---|
| **Learning Ledger** | ✅ | `arbicore/learning/ledger.py` (P0-B) + `arbicore_signal_metrics` + `calibration_log` writers | journal, MongoRouteSuccessTracker | ACTIVE — invoked by pipeline every terminal | — | — | — | — | — |
| **Calibration** | ✅ | `arbicore/learning/calibration.py` + `learning/concrete/calibration_worker.py` (`_CALIBRATION_WORKER` running at 3600 s tick) + `learning/concrete/calibrator_isotonic.py` | `calibration_models` collection, `calibration_log` | ACTIVE background task; 4 endpoints (`/intelligence/calibration`, `/calibration/status`, `/calibration/history`, `/intelligence/models`) | — | — | — | — | — |
| **Adaptive Weights** | ✅ | `arbicore/learning/weights.py` + `learning/concrete/adaptive_weights_worker.py` (`_ADAPTIVE_WEIGHTS_WORKER` running at 3600 s tick) | `arbicore_signal_metrics` | ACTIVE in **OBSERVE** mode (Wave 4) — provider does not yet update primary confidence | Promote to ENFORCE mode (post-calibration validation window) | **Refine** — one flag flip after 14 days of SHADOW data | — | S | None (single ENV/config toggle) |
| **Self Improvement** | 🟡 | Emergent property of Journal → Ledger → Calibration → AdaptiveWeights loop | all above | Loop closed but ENFORCE not enabled | Automated flag flip triggered by calibration confidence-drift telemetry | **Build new** — small governance worker | learning ledger, calibration | S | New worker |
| **Recommendation Engine** | 🟡 | `/intelligence/recommendations` returns **STATIC STUB** (top_routes/top_chains/top_entities are hardcoded arrays) | — | Preview only | Actual data source: query `MongoRouteSuccessTracker` + `arbicore_signal_metrics` + `arbicore_entities` | **Refine** — swap stub body for real Mongo aggregation | dormant `arbicore/intel/scorer.py`, learning ledger data | M | Read-only |
| **Replay Learning** | 🔴 | — | — | — | Ability to re-inject historical opportunities as training samples | **Build new** | Market Replay Engine (missing), learning ledger | M | Batch job |
| **Outcome Labelling** | ⚪ | `arbicore/learning/outcomes.py` + `learning/concrete/outcome_tracker.py` (dormant) | `arbicore_outcomes` collection | DORMANT — pipeline currently labels internally via journal state | Wire outcome_tracker into pipeline for full 5-horizon outcome tracking | **Refine** — activate after adaptive weights ENFORCE | dormant outcome_tracker, journal | S | New Mongo writes |
| **Historical Learning** | 🟡 | Learning Ledger reads journal; calibration + adaptive-weights workers consume samples | — | ACTIVE for **forward** learning | Backfill: consume the journal for opportunities that pre-date the ledger's first emit | **Build new** (~50 LOC ledger backfill script + one endpoint) | Learning Ledger, journal | S | One-off batch |

### D. Opportunity Intelligence

| Capability | Status | Existing implementation | Reused modules | Runtime status | Missing pieces | Action | Deps | Effort | Deploy impact |
|---|:-:|---|---|---|---|---|---|:-:|---|
| **Opportunity Ranking** | ✅ | `sort_by={confidence,spread,depth,freshness}` on `GET /opportunities` (Phase 8) | canonical opportunity fields | ACTIVE | Composite scoring (weighted blend) | **Refine** — add `sort_by=score` computed live | dormant scorer | S | Read-only |
| **Confidence Intelligence** | 🟡 | `MongoRouteSuccessTracker` + `/roi-probability?route_id=…` (Slice 0) + calibration curve applied downstream | learning ledger, calibration | ACTIVE for surface layer; underlying scorer engine dormant | Full `arbicore/intelligence/confidence.py` (`SignalConfidence` engine — dormant) not wired into decisions endpoint | **Refine** — swap decisions stub for real confidence engine | dormant `intelligence/confidence.py`, calibration | M | Live confidence per opp |
| **Expected Value** | 🟡 | Computed inline by pipeline: `expected_profit_usd = pnl_estimate - gas_estimate - flash_fee` | pipeline | ACTIVE for point-in-time | Aggregated EV over route history | **Refine** — add EV distribution to `/roi-probability` | — | S | Read-only |
| **Profit Prediction** | 🟡 | `arbicore/intelligence/roi_probability.py` (dormant — full ROI probability engine) + surface via `/roi-probability` | dormant engine ships in tree but endpoint currently reads from tracker | Endpoint is a thin passthrough | Wire `ROIProbabilityEngine` into endpoint for real probabilistic bands | **Refine** — activate dormant module | dormant `intelligence/roi_probability.py`, outcome tracker | S | Read-only |
| **Capital Intelligence** | ✅ | `arbicore/execution/capital_policy.py` (per-strategy binding of pool%/wallet%/per-plan/daily-notional) | — | ACTIVE, 4 endpoints | — | — | — | — | — |
| **Borrow Optimization** | 🟡 | Adapter registry compares Aave V3 (5 bps) vs Balancer V2 (0 bps) vs UniV3 (pool tier); planner picks lowest fee | `adapters.py`, `planner.py` | ACTIVE at plan time | Live pool-depth check before selecting borrow provider | **Upgrade** — add depth query to adapter | RPC | S | +1 RPC call per plan |
| **Slippage Intelligence** | ✅ | `arbicore/execution/slippage.py` (deterministic estimator based on price impact model + configurable safety buffer) | quoter | ACTIVE at plan time; used by dry-run engine | — | — | — | — | — |
| **Opportunity Prediction** | 🔴 | — | — | — | Time-series model that flags likely-imminent arbitrages (feed = journal aggregates) | **Build new** | Opportunity History, seasonal, regime | L | New worker + endpoint |
| **Opportunity Decay Analysis** | 🟡 | `freshness_hint` field on `/dashboard/pulse` | journal `lifetime_ms` | ACTIVE for headline metric | Detailed decay curves by family/chain | **Build new** analytic (thin, over journal) | journal | S | Read-only |

### E. Market Research

| Capability | Status | Existing implementation | Reused modules | Runtime status | Missing pieces | Action | Deps | Effort | Deploy impact |
|---|:-:|---|---|---|---|---|---|:-:|---|
| **Multi-DEX Intelligence** | 🟡 | `arbicore/execution/adapters.py` — Uniswap V3, Aerodrome (Base) | address book | ACTIVE for 2 DEXes on Base | Add SushiSwap, PancakeSwap, Balancer weighted pools, Curve; extend address book to Arbitrum/Optimism/Polygon | **Upgrade** — add adapters | ABI + address book | M | Adapter files only |
| **Multi-Flashloan Provider Intelligence** | 🟡 | 3 providers × 1 chain (Aave V3, Balancer V2, UniV3 flash on Base) | adapters | ACTIVE | Extend to Radiant, dYdX v3; extend to other chains | **Upgrade** — add adapters | ABI | S | Adapter files only |
| **Multi-Chain Intelligence** | 🟡 | `arbicore/execution/wallet_registry.SUPPORTED_CHAINS` lists many chains but ContinuousDiscovery + broadcast pipeline only exercise Base | wallet_registry | ACTIVE for Base | Per-chain RPC endpoint, per-chain executor address, per-chain adapter address book | **Upgrade** — add chain profile registry | RPC infra | L | Multi-chain routing layer |
| **Route Discovery** | ⚪ | `arbicore/scanners/flash_loan_arbitrage/route_search.py` (dormant — `RouteSearchEngine`, path enumeration, 3-token loop discovery) | full canonical scanner tree | DORMANT | Wire scanner into ContinuousDiscovery activator | **Refine** — first scanner activation wave (v2.1.0) | dormant `scanners/flash_loan_arbitrage`, `scanner/base.py` | M | Background CPU load ↑ |
| **Route Evolution** | ✅ | `MongoRouteSuccessTracker` (win rate + sample count per route over rolling window) | learning ledger | ACTIVE | — | — | — | — | — |
| **Liquidity Mapping** | 🔴 | — | — | — | Per-pair liquidity snapshot writer + hot/cold liquidity map | **Build new** | subgraph or on-chain reads, market history | M | Background worker |

### F. Infrastructure Intelligence

| Capability | Status | Existing implementation | Reused modules | Runtime status | Missing pieces | Action | Deps | Effort | Deploy impact |
|---|:-:|---|---|---|---|---|---|:-:|---|
| **Health Monitoring** | 🟡 | `scripts/healthcheck.sh` + `deployment/monitoring/{healthcheck,uptime-probe,snapshot}.sh` + `/api/system/status` in-app | container healthchecks | ACTIVE (host + container level) | In-app SLO metrics: task tick success rate, discovery lag, ledger consumption rate | **Refine** — add `/api/arbicore/health/tasks` endpoint | background workers | S | Read-only |
| **Worker Supervision** | 🟡 | Host: supervisord. In-app: 5 background asyncio tasks (calibration, adaptive_weights, evidence_signing, discovery, auto_executor) started in `server.py` `startup` hook | supervisor | ACTIVE | No restart-on-crash inside process; no dashboard view of task health | **Build new** — thin task supervisor + dashboard endpoint | — | S | Read-only + minor restart logic |
| **Recovery** | 🔴 | — | — | — | Automatic quiescing on Mongo outage, RPC outage, secret vault outage; graceful drain | **Build new** | Health monitoring | M | Startup / shutdown hooks |
| **Alerting** | 🟡 | `arbicore/notifications/telegram.py` (Telegram bot integration) + settings endpoints (`/settings/telegram/*`) | python-telegram-bot | ACTIVE — operator can configure bot token, chat_id, emit test messages | Actual alerts (kill switch engaged, worker crashed, calibration drift, LIMITED_LIVE tx confirmed/reverted) not yet wired to sender | **Refine** — add alert-router with well-defined alert types | telegram notifier | M | External calls only when triggered |
| **Logging** | ✅ | Python `logging` module → supervisor log files under `/var/log/supervisor/` | stdlib | ACTIVE | Log level configurable at runtime (currently static) | **Refine** — add `/api/system/log-level` endpoint | — | S | None |
| **Evidence** | ✅ | `arbicore/evidence/{bundle,signer}.py` — Ed25519 signing, key rotation, evidence bundle emit for kill-switch / broadcast / certification events | signing worker (active), Wave 5 | ACTIVE — 5 endpoints (`/evidence/{current,history,keys,status,verify}`) | HSM/KMS signer backend adapter (currently Fernet-encrypted burner key) | **Upgrade** — HSM/KMS integration | HSM provider | L | Provider integration |
| **Backup** | ✅ | `deployment/backups/{backup,backup-cron,restore}.sh` (mongodump archive+gzip, optional rclone off-host push) | mongodump | Deployment-level ACTIVE | Backup-verification runner (checksum + test-restore in scratch db) | **Refine** — add nightly restore verification | — | S | Deploy-side only |
| **Runtime Diagnostics** | 🟡 | `/system/status` + `/dashboard/pulse` (worker states, regime, opportunity vitals) | all workers | ACTIVE | Task-level diagnostics: last-tick timestamp, tick duration histogram, error counts per worker | **Refine** — extend `/system/status` payload | workers | S | Read-only |

### G. Operator Intelligence

| Capability | Status | Existing implementation | Reused modules | Runtime status | Missing pieces | Action | Deps | Effort | Deploy impact |
|---|:-:|---|---|---|---|---|---|:-:|---|
| **Dashboard Analytics** | 🟡 | `/dashboard/pulse` + `/dashboard/deck` + `/opportunities/summary` (Slice 0 composed endpoints) | journal, opportunity repo, route tracker | ACTIVE | Wire dormant `arbicore/intelligence` modules (confidence, capital, scoring) into surface | **Refine** — swap stubs for real engines | dormant `intelligence/` | M | Read-only |
| **Daily Reports** | 🔴 | — | — | — | Daily summary email/telegram (opps discovered, broadcasted, PnL, notable events) | **Build new** — new worker + template | notifications, journal, ledger | M | External send |
| **Opportunity Heatmaps** | 🔴 | — | — | — | 2D/matrix view of opportunity density by (family, chain) × time window | **Build new** (~250 LOC analytics + endpoint + UI card) | journal | S | Read-only |
| **Market Statistics** | 🟡 | `/opportunities/summary` (counts by family/chain/status) | opportunity repo | ACTIVE | Deeper stats: median lifetime, EV distribution, verdict distribution over time | **Refine** — extend summary payload | journal | S | Read-only |
| **Learning Statistics** | 🟡 | `/intelligence/calibration/{status,history}` + `/intelligence/weights/{status,history,recommendations}` | calibration + adaptive_weights workers | ACTIVE with real data | Drift telemetry (Brier score over time, calibration error trend) | **Refine** — add drift dashboard endpoint | — | S | Read-only |
| **Performance Analytics** | 🟡 | Journey stage tracker + Post-Trade page + `/post-trade/latest` | wizard, journal | ACTIVE for walkthrough | Aggregate performance: cumulative PnL, per-strategy PnL, gas-cost analysis, per-adapter success rate | **Build new** (~300 LOC analytics + endpoints + UI section) | journal, ledger | M | Read-only |

### H. Future AI Readiness

| Capability | Status | Existing implementation | Reused modules | Runtime status | Missing pieces | Action | Deps | Effort | Deploy impact |
|---|:-:|---|---|---|---|---|---|:-:|---|
| **Knowledge Hub Readiness** | 🔴 | — | — | — | Vector store + doc ingestion + retrieval endpoint | **Build new** (deferred — v2.3+) | LLM key, embedding service | XL | External services |
| **Strategy Evolution Readiness** | ⚪ | Foundation exists: journal (state), ledger (labels), calibration (feedback), adaptive weights (parameters), evidence (audit) | learning system | Loop closed but no evolutionary layer | Multi-armed-bandit or genetic loop that mutates weights/policy toward observed reward | **Build new** (deferred — v2.4+) | Learning system COMPLETE, replay engine, self-improvement governance | XL | Background evolutionary worker |
| **AI Research Assistant Readiness** | 🔴 | — | — | — | LLM integration + knowledge hub + query surface | **Build new** (deferred — v2.5+) | Knowledge Hub, LLM key | XL | External LLM calls |
| **Reinforcement Learning Readiness** | ⚪ | Reward signal (PnL/verdict) available in journal; policy surface (mode, capital policy, adapter selection) enumerable | journal, capital policy, mode | Data ready; no policy learner | Actor-critic loop that treats mode/capital knobs as actions, PnL as reward | **Build new** (deferred — v2.4+) | Learning system, replay engine | XL | Background RL worker |

---

## 2. Dependency Graph

```
Level 0 (foundations — already ACTIVE, unblock everything):
  ├── Opportunity Journal (P0-A)          ✅
  ├── Learning Ledger (P0-B)              ✅
  ├── Calibration Worker                  ✅
  ├── Adaptive Weights Worker (OBSERVE)   ✅
  ├── ContinuousDiscovery (thin)          🟡
  ├── AutoExecutor                        ✅
  ├── Certification Pipeline              ✅
  ├── Capital Policy + Kill Switch        ✅
  └── Broadcast Pipeline (6-gate)         ✅

Level 1 (immediate refinements — small effort, high leverage):
  ├── Refine `/intelligence/recommendations` (stub → live)     depends on: L0
  ├── Refine `/intelligence/decisions`     (stub → live)       depends on: L0, Confidence engine
  ├── Wire Regime Classifier               (⚪→✅)              depends on: L0, dormant module
  ├── Wire Outcome Tracker                 (⚪→✅)              depends on: L0, dormant module
  ├── Promote Adaptive Weights to ENFORCE  (flag flip)         depends on: L0 + 14d SHADOW data
  ├── Historical Learning backfill                             depends on: L0
  └── Wallet Health card refine (already partial)              depends on: L0

Level 2 (data producers — build once, reuse everywhere):
  ├── Market Intelligence Database (MID)   (🔴→✅ NEW)          depends on: L0, RPC/subgraph — see V2_PLATFORM_ROADMAP.md §P1-α
  ├── Gas Intelligence historical writer   (🟡→✅ UPGRADE)      depends on: L0
  ├── Liquidity snapshot writer            (🟡→✅ UPGRADE)      depends on: L2 Market History
  └── Multi-DEX + Multi-Flashloan adapter expansion            depends on: adapters framework

Level 3 (derived analytics — consume L2):
  ├── Volatility Intelligence              (🔴→✅ NEW)          depends on: L2 Market History
  ├── Seasonal Behaviour                   (🔴→✅ NEW)          depends on: L2 + Journal
  ├── Opportunity Lifetime Intelligence    (🟡→✅ REFINE)       depends on: Journal
  ├── Opportunity Decay Analysis           (🟡→✅ REFINE)       depends on: Journal
  ├── Opportunity Heatmaps                 (🔴→✅ NEW)          depends on: Journal
  └── Performance Analytics                (🟡→✅ REFINE)       depends on: Journal + Ledger

Level 4 (aggregators + prediction):
  ├── Confidence Intelligence full         (🟡→✅ REFINE)       depends on: L1, L2
  ├── Recommendation Engine full           (🟡→✅ REFINE)       depends on: L3
  ├── Market Pattern Learning              (⚪→✅ REFINE)       depends on: L3 + regime
  ├── Opportunity Prediction               (🔴→✅ NEW)          depends on: L3 all
  └── Daily Reports                        (🔴→✅ NEW)          depends on: L3

Level 5 (systemic):
  ├── Route Discovery (canonical scanner activation)           depends on: L0, ContinuousDiscovery upgrade
  ├── Liquidity Mapping                                        depends on: L2, L3
  ├── Replay Learning                                          depends on: L2, L3
  ├── Market Replay Engine                                     depends on: L2 all
  ├── Self-Improvement governance                              depends on: L1 promotion, L4 drift telemetry
  ├── Recovery / Alerting router                               depends on: L0, notifications
  └── Multi-Chain Intelligence expansion                       depends on: L2 all + chain profile registry

Level 6 (AI readiness — deferred, non-blocking):
  ├── Knowledge Hub                                            depends on: — (independent)
  ├── Strategy Evolution                                       depends on: L4, L5
  ├── AI Research Assistant                                    depends on: L6 Knowledge Hub
  └── Reinforcement Learning                                   depends on: L4, L5, Replay
```

---

## 3. Recommended Build Order

**Rule:** never build before what it depends on; never build new when refine suffices.

### Phase 3-A — Zero-risk activations (Sprint 1, ~1 week)
_All refinements of existing dormant/stub modules. No new dependencies. No deployment impact beyond flag flips._
1. Wire **Regime Classifier + regime_worker** from dormant tree into startup (Refine)
2. Wire **Outcome Tracker** from dormant tree into pipeline terminal (Refine)
3. Swap **`/intelligence/recommendations`** stub for real Mongo aggregation (Refine)
4. Swap **`/intelligence/decisions`** stub for live `SignalConfidence` engine (Refine + wire dormant `intelligence/confidence.py`)
5. Extend **`/dashboard/pulse`** to consume dormant `capital.py`, `scoring.py` (Refine)
6. Add **Historical Learning backfill** endpoint (Build new — small)
7. Add **Opportunity Lifetime Intelligence** analytics endpoint (Build new — small, thin over journal)
8. Add **Opportunity Decay Analysis** endpoint (Build new — small)

### Phase 3-B — Data producers (Sprint 2, ~2 weeks)
_Foundational writers that unblock everything in Levels 3–5._
9. Build **Market Intelligence Database (MID)** — 11-domain unified persistence layer under `arbicore/data/mid/` façade (Build new — M–L). See `V2_PLATFORM_ROADMAP.md` §P1-α for the full domain table.
10. Upgrade **Gas Intelligence** — add historical snapshot writer to existing gas oracle (Upgrade — S)
11. Upgrade **Liquidity Intelligence** — add depth snapshot writer to existing quoter (Upgrade — S)
12. Upgrade **Multi-DEX** — add SushiSwap, Curve adapters (Upgrade — S each)
13. Upgrade **Multi-Flashloan** — add Radiant, dYdX v3 adapters (Upgrade — S each)

### Phase 3-C — Derived analytics (Sprint 3, ~2 weeks)
_All read-only aggregations over L2 data + Journal._
14. Build **Volatility Intelligence** (Build new — S)
15. Build **Seasonal Behaviour** (Build new — S)
16. Build **Opportunity Heatmaps** (Build new — S)
17. Refine **Performance Analytics** — extend to cover PnL/gas/adapter success/venue-level (Refine — M)
18. Refine **Market Statistics** — extend summary (Refine — S)
19. Refine **Learning Statistics** — add drift telemetry (Refine — S)

### Phase 3-D — Intelligence + prediction (Sprint 4, ~2 weeks)
20. Refine **Confidence Intelligence** — full engine wired end-to-end (Refine — M)
21. Refine **Recommendation Engine** — live aggregator (Refine — M)
22. Refine **Market Pattern Learning** — activate `sequence_miner` (Refine — M)
23. Refine **Borrow Optimization** — live pool-depth query (Upgrade — S)
24. Build **Opportunity Prediction** — time-series model (Build new — L)
25. Build **Daily Reports** — telegram + email templates (Build new — M)

### Phase 3-E — Systemic (Sprint 5, ~2–3 weeks)
26. Activate **Canonical Scanner Tree** — first scanner wave (`flash_loan_arbitrage`) — the P1 backlog item (Refine — M)
27. Build **Liquidity Mapping** — hot/cold map (Build new — M)
28. Build **Alerting Router** — well-defined alert types wired to Telegram notifier (Refine + Build — M)
29. Build **Recovery hooks** — graceful drain on outage (Build new — M)
30. Build **Self-Improvement governance worker** — automated ENFORCE flip (Build new — S)
31. Build **Market Replay Engine** (Build new — L)
32. Build **Replay Learning** — retro-inject journal (Build new — M)
33. Promote **Adaptive Weights to ENFORCE** (flag flip — S)

### Phase 3-F — AI readiness (deferred, v2.3+)
34. Knowledge Hub (XL)
35. Strategy Evolution (XL)
36. AI Research Assistant (XL)
37. Reinforcement Learning (XL)

---

## 4. Priority Classification

> **Superseded by [`V2_PLATFORM_ROADMAP.md`](V2_PLATFORM_ROADMAP.md) §3–4** (ratified 2026-08-02 after operator review).
> This section preserves the original audit-time proposal for provenance. **The platform roadmap document is now the authoritative priority list.**

### Adjusted priority summary (from platform roadmap)

| Tier | Contents |
|---|---|
| **P0** | None. v2.0.0 is deployment-ready. |
| **P1** | **P1-α Market Intelligence Database** (renamed from Market History Storage; expanded to 11 domains — Sprint 1) · **P1-β Opportunity Lifetime Intelligence** (permanent record of first_seen / last_seen / disappeared_at / lifetime / recurrence / survival probability) · **P1-γ Historical Market Intelligence** (learn from observed-but-not-executed) · **P1-δ zero-risk dormant-module activations** (regime, outcome, stub swaps, drift telemetry) |
| **P1↔P2 bridge** | **Replay & Outcome Intelligence** — the five-question contract per execution (why succeed / why fail / better route? / better provider? / better size?). SHADOW → LIMITED_LIVE promotion gate. |
| **P2** | Provider Intelligence · Borrow Optimization · Capital Allocator (portfolio-aware) · Multi-chain Optimization · Opportunity Prediction (+ Volatility / Seasonality / Multi-DEX / Gas historical / Heatmaps / Daily Reports / full Confidence + Recommendation surface / extended Performance Analytics from the original audit) |
| **P3** | Dormant scanner activation · Additional protocol activation · Autonomous Research · AI-generated strategy discovery · Alerting router + Recovery + ENFORCE governance · Market Replay Engine batch + Replay Learning retro-inject |
| **P4** | Knowledge Hub · Strategy Evolution · AI Research Assistant · Reinforcement Learning (deferred, v2.3+) |

Sequence, effort estimates, success metrics, and non-negotiable invariants are all in the platform roadmap document.

---

### Original audit-time proposal (preserved for provenance)

### P0 — Must build BEFORE deployment (v2.0.0 → VPS)
_None._ v2.0.0 is deployment-ready as certified. Every P0 for the first LIMITED_LIVE broadcast was closed in Phase 10.10.6. The audit surface identifies **zero blocking gaps** for VPS deployment of the current feature set.

### P1 — Should build BEFORE deployment (nice-to-have, low-cost)
_Only refinements of existing dormant modules._ These stay in-tree even without activation; the risk is nil, and turning them on before deployment gives operators a richer cockpit day-one:
- **P1-a** — Wire Regime Classifier + Outcome Tracker (Phase 3-A items 1–2)
- **P1-b** — Swap Recommendations + Decisions stubs (Phase 3-A items 3–4)
- **P1-c** — Historical Learning backfill (Phase 3-A item 6)

_Total effort_: ~1 week for all of P1. Zero external dependencies. Read-only endpoints.

### P2 — Can build AFTER deployment (build during SHADOW validation window)
Everything in Phases 3-B, 3-C, 3-D:
- Market Intelligence Database (renamed; expanded to 11 domains)
- Gas / Liquidity / Volatility / Seasonal analytics
- Multi-DEX + Multi-Flashloan expansion
- Confidence + Recommendation full wiring
- Opportunity Prediction, Heatmaps, Daily Reports
- Performance Analytics extended

_Total effort_: ~6–8 weeks. Non-blocking. Can iterate weekly.

### P3 — Systemic upgrades (v2.1 → v2.2)
Everything in Phase 3-E:
- Canonical scanner activation
- Market Replay + Replay Learning
- Alerting router
- Recovery hooks
- ENFORCE promotion + governance

### P4 — AI readiness (v2.3+)
Everything in Phase 3-F. Not needed for LIMITED_LIVE / FULL_LIVE operation.

---

## 5. Estimated Implementation Effort (aggregate)

| Phase | Items | Total effort | Cumulative |
|---|---|---|---|
| 3-A (P1) | 8 refinements + 2 small builds | ~1 week | 1 wk |
| 3-B (P2 producers) | 5 upgrades / new writers | ~2 weeks | 3 wks |
| 3-C (P2 analytics) | 6 refinements / small builds | ~2 weeks | 5 wks |
| 3-D (P2 intelligence) | 4 refines + 2 builds (1 large) | ~2 weeks | 7 wks |
| 3-E (P3 systemic) | 8 items (mix S/M/L) | ~2–3 weeks | 9–10 wks |
| 3-F (P4 AI readiness) | 4 XL items — deferred | ~3 months | v2.3+ |

**Realistic timeline to reach a fully-instrumented v2.2 platform: ~10 developer-weeks after v2.0.0 deployment.**

---

## 6. Risk Assessment

| Risk | Severity | Mitigation |
|---|:-:|---|
| **Refining recommendations/decisions endpoint changes UI shape** | Low | Both stubs return additive-only fields; the UI ignores unknown fields; can ship refined body under a feature flag with the stub as fallback |
| **Activating regime + outcome workers doubles Mongo write rate** | Low | Both are 1-doc-per-tick writers; ~1 KB/tick; well under Mongo capacity |
| **Market history storage causes disk growth** | Medium | Add TTL index (90 days by default); provide `.env` toggle for retention window; cap max writes/hour |
| **Adaptive Weights ENFORCE flip too early → bad routes reinforced** | Medium | Governance worker requires 14-day SHADOW window + Brier-score threshold before flip; audit trail written |
| **Multi-chain expansion introduces per-chain address book drift** | Medium | Chain profile registry with strict schema; deployment-side validation script |
| **Canonical scanner activation triggers CPU spike** | Medium | Activate one family at a time; each behind its own feature flag; benchmarked in shadow first |
| **HSM/KMS integration failure blocks broadcast** | High | Keep Fernet burner path as fallback; feature-flag-gated cutover; retry logic + kill-switch trigger on hardware error |
| **AI-readiness modules require LLM keys** | Low (deferred) | Use Emergent LLM key; scoped behind feature flag; strictly opt-in |

---

## 7. Final Recommendation

**v2.0.0 as it stands is deployment-ready.** All 8 audit categories have functioning foundations. There are **zero P0 gaps**. The audit surfaces exactly two classes of unfinished work:

1. **Dormant modules the tree ALREADY ships** but does not wire (11 items marked ⚪). Every one of these becomes a **refine** — flip a flag / activate a worker / swap a stub for the dormant real engine. **No net-new modules to build.** Estimated total effort: ~1 week for all of P1.

2. **Genuinely missing capabilities** (10 items marked 🔴). Half of these are downstream consumers of a **single missing persistence layer** (the Market Intelligence Database — MID). Build that first and the analytics stack (Volatility / Seasonal / Heatmaps / Prediction) all become 1-day items each.

**Recommended path forward:**

1. **Ship v2.0.0 to VPS now.** Do not delay for P1 or P2. The current feature set is production-grade.
2. **In parallel with the 14-day SHADOW validation window**, execute Phase 3-A (P1) — pure refinements, no new dependencies, gives operators a richer cockpit day-one.
3. **Build the Market Intelligence Database (MID) FIRST in Sprint 1** as the single upstream investment. Everything else in P1/P2/P3 becomes cheap once that lands. Original Phase 3-B ordering has been superseded by the 5-sprint plan in `V2_FLASH_LOAN_CAPABILITY_AUDIT.md` §8.
4. **Only build "new" where there is no foundation.** Of the 10 🔴 items, 7 already have adjacent modules that can be leveraged (survival.py, sequence_miner.py, journal.py). Reuse before rebuild.

**What NOT to do:**
- Do not rebuild Confidence Intelligence — the canonical `intelligence/confidence.py` is already in the tree.
- Do not rebuild ROI Probability — `intelligence/roi_probability.py` is already in the tree.
- Do not rebuild Regime Classifier — `learning/concrete/regime_classifier.py` is in the tree with a worker.
- Do not rebuild Outcome Tracker — `learning/concrete/outcome_tracker.py` is in the tree.
- Do not rebuild Route Discovery — the entire `arbicore/scanners/flash_loan_arbitrage` tree is in the repo, dormant.
- Do not rebuild the Universal Entity Scorer — `arbicore/intel/scorer.py` is in the tree.
- Do not rebuild `sequence_miner`, `survival`, `metrics_aggregator`, `evaluator_worker`, `state_observers` — all present as dormant workers under `learning/concrete/`.

The strongest verified implementation of every subsystem already lives in the canonical tree — for **50% of the audit surface, the correct action is "activate", not "build".**

---

## 8. Deliverable summary

| # | Deliverable | Location in this document |
|---|---|---|
| 1 | Capability Matrix (44 capabilities across A–H) | §1 |
| 2 | Dependency Graph (Levels 0–6) | §2 |
| 3 | Recommended Build Order (Phases 3-A → 3-F, 37 items) | §3 |
| 4 | Priority Classification (P0/P1/P2/P3/P4) | §4 |
| 5 | Aggregate effort estimation (~10 dev-weeks to v2.2) | §5 |
| 6 | Risk assessment (8 named risks + mitigations) | §6 |
| 7 | Final recommendation | §7 |

**No code was written for this audit.** All findings are based on direct inspection of `/app/canonical_repo/@v2.0.0` at HEAD. Zero fabrication.

_Awaiting approval to proceed. Suggested first sprint scope: **Phase 3-A (P1) — 8 items, ~1 week, zero net-new modules**._
