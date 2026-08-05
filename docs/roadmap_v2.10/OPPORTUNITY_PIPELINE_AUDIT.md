# Opportunity Pipeline — Architectural Audit
## Read-only wiring map, pre-Slice-1

**Date:** 2026-08-05
**Baseline:** post-v2.9.3 (auth hotfix) on branch `hotfix/auth-routing` @ `57b0e72`
**Method:** static enumeration of engine instantiations, endpoint decorators,
and frontend API consumers. Zero code changed.

**Bottom line up front:** the discovery → detection → route generation →
profitability → execution planning → flash-loan execution → learning
pipeline is **already largely instantiated and wired** in `server.py`.
The gaps are narrower than the earlier framing suggested. Slice 1 should
be a **preview-fallback deletion + shape polish**, not a rebuild.

---

## §1. Engine inventory

Every engine and repository *actually instantiated* in `server.py` (with line
numbers of the `_NAME = ...(...)` binding), and its wiring state.

| # | Engine (variable) | Class · module | Instantiated? | Currently mounted (endpoint) | Returns live data? | Notes |
| - | :----------------- | :------------- | :-----------: | :--------------------------- | :----------------: | :---- |
| 1  | `_CONTINUOUS_DISCOVERY`     | `ContinuousDiscovery` · `arbicore/execution/discovery.py` (346 LOC) | ✅ L234    | ✅ `/arbicore/execution/discovery/{status,tick,start,stop}` (L2794-2818) | ✅ writes to `_CANONICAL_OPP_REPO` on promotion (L261 wires them) | **Not autostarted at boot.** Operator must call `/start`. Runs in-process. |
| 2  | `_CANONICAL_OPP_REPO`       | `MongoOpportunityRepository` · `arbicore/data/mongo/opportunity_repo_mongo.py` (134 LOC) | ✅ L258 | ✅ `/arbicore/opportunities` (L537), `/{id}` (L638), `/approve` (L713), `/reject` (L740), `/{id}/timeline` (L768) | ✅ real Mongo collection `arbicore_opportunities` | Endpoint L537 is **canonical-first + preview-fallback** — returns real rows plus `_V2_OPPS` merge when canonical thin. |
| 3  | `_OPPORTUNITY_JOURNAL`      | `OpportunityJournal` · `arbicore/data/journal.py` | ✅ L269 | ✅ `/arbicore/journal` (L3390), `/summary` (L3407), `/{id}` (L3413) | ✅ writes `opportunity_journal` collection | Real. Fully wired. |
| 4  | `_OPPORTUNITY_PIPELINE`     | `OpportunityPipeline` · `arbicore/execution/pipeline.py` (516 LOC) | ✅ L288 | ✅ `/arbicore/pipeline/evaluate` (L3475) | ✅ orchestrates journal + learning ledger | Executes stages: verdict → confidence → policy → certify → journal. Real. |
| 5  | `_LEARNING_LEDGER`          | `LearningLedger` · `arbicore/data/journal.py` | ✅ L277 | ✅ `/arbicore/learning/status` (L3430), `/emit` (L3446) | ✅ | Emits from journal in batches. |
| 6  | `_LIVE_SCANNER`             | `LiveMarketScanner` · `arbicore/scanners/live/scanner.py` (Wave 1) | ✅ L4347 (bound in startup event, not module load) | ✅ `/arbicore/live/{status,start,stop,prices,opportunities}` | ✅ **autostarts** in OBSERVE mode via `LIVE_MARKET_AUTOSTART=1` (default) | Writes ticks to `_PAPER_ENGINE` + `_MID_WRITER`. |
| 7  | `_SCANNER_ACTIVATION`       | `ScannerActivation` · `arbicore/scanners/wave1b/activation.py` | ✅ L3917 | via bridge into `_LIVE_SCANNER` | ✅ | Bridges shadow scanners into evidence signer. |
| 8  | `_PROVIDER_REGISTRY`        | `ProviderRegistry` · `arbicore/providers/` | ✅ (Phase 5) | ✅ `/arbicore/providers/status` | ✅ 47 providers registered | Live provider polling. |
| 9  | `_MID_WRITER` / `_MID_READER` | `MarketIntelligenceWriter/Reader` · `arbicore/data/mid/` | ✅ (Phase M) | ✅ `/arbicore/memory/summary` + 7 more | ✅ | Ticks persisted to Mongo MID collections. |
| 10 | `_KILL_SWITCH_REPO` + kill helpers | `KillSwitchRepo` · `arbicore/execution/kill_switch.py` | ✅ L191 | ✅ `/arbicore/execution/kill-switch{,/engage,/disengage}`, `/safety/kill/{engage,disengage}` | ✅ | Real switch, real DB. |
| 11 | `_EXECUTION_PLANNER`        | `ExecutionPlanner` · `arbicore/execution/planner.py` (540 LOC) | ✅ L173 | ✅ `/arbicore/execution/plans/build` (L2355), `/plans/{id}` (L2428), `/plans` (L2437), `/simulate` (L2497), `/sign` (L2684), `/calldata` (L3313), `/broadcast` (L3331) | ✅ writes to `_EXECUTION_PLANS_REPO` | **Full plan lifecycle wired.** |
| 12 | `_DRY_RUN_ENGINE`           | `DryRunEngine` · `arbicore/execution/` | ✅ L174 | via `/plans/simulate` | ✅ | Uses adapters to simulate. |
| 13 | `_CAPITAL_ALLOCATOR`        | `CapitalAllocator` · `arbicore/execution/` | ✅ L190 | via plan/build | ✅ | Real repo `_CAPITAL_POLICY_REPO`. |
| 14 | `_EXECUTION_PLANS_REPO`     | `ExecutionPlansRepo` · `arbicore/execution/` | ✅ L182 | via all plan endpoints | ✅ | Real Mongo `execution_plans`. |
| 15 | `_WALLET_REGISTRY`          | `WalletRegistryRepo` · `arbicore/wallets/` | ✅ L154 | ✅ `/arbicore/execution/wallets{,/…}` | ✅ | Real repo. |
| 16 | `_MEV_REGISTRY`             | `MevRouterRegistry` · `arbicore/execution/mev.py` | ✅ L170 | via `/plans/broadcast` | ✅ | MEV router selection. |
| 17 | `_FL_JOURNEY` (Flash Loan Operator Journey) | `FlashLoanOperatorJourney` · `arbicore/flashloan/operator_journey.py` (300 LOC) | ✅ (bound in startup) | ✅ `/arbicore/flashloan/journey/run`, `/status` | ✅ | Guided flash-loan pre-flight sequence. |
| 18 | `_PAPER_ENGINE`             | `PaperEngine` · `arbicore/paper/paper_engine.py` | ✅ | ✅ `/arbicore/paper/*` | ✅ | Paper simulator. |
| 19 | `_CALIBRATION_REPO` / `_ADAPTIVE_WEIGHTS_REPO` / `_EVIDENCE_REPO` | learning-loop repos | ✅ L101/L120/L139 | ✅ `/arbicore/intelligence/{calibration,adaptive-weights,evidence}/*` | ✅ | Real Mongo. |
| 20 | `_DISCOVERY_REPO`           | `DiscoveryRepo` · `arbicore/execution/discovery.py` L103 | ✅ L233 | (used by `_CONTINUOUS_DISCOVERY`) | ✅ | Real Mongo `discovery_candidates`. |
| 21 | `_AUTO_EXECUTOR`            | `AutoExecutor` · `arbicore/execution/auto_executor.py` | ✅ | ✅ `/arbicore/auto-executor/{status,start,stop,tick}` (L3490-3507) | ✅ | The end-to-end runtime binder — glues discovery → pipeline → planner → journal. |

### §1a. Per-strategy scanners — implementation status

Every one of these has a real `Scanner` class on disk. Only the LiveMarketScanner
(spatial CEX/DEX) is bound into a live process at boot; the others are **wired
via `ScannerRegistry`** and can be activated per-family.

| Scanner | File | Class | Wired via `_SCANNER_ACTIVATION`? | Mounted endpoint? |
| :------ | :--- | :---- | :------------------------------: | :----------------: |
| **CEX arbitrage**           | `arbicore/scanners/cex_arbitrage/scanner.py`           | `CEXArbitrageScanner`           | ✅  | `/arbicore/scanners/{family}/status/kill/resume` (L2860+) — from `_SCANNER_ACTIVATION` |
| **DEX arbitrage**           | `arbicore/scanners/dex_arbitrage/scanner.py`           | `DEXArbitrageScanner`           | ✅  | same |
| **Cross-chain arbitrage**   | `arbicore/scanners/cross_chain_arbitrage/scanner.py`   | `CrossChainArbitrageScanner`    | ✅  | same |
| **Funding arbitrage**       | `arbicore/scanners/funding_arbitrage/scanner.py`       | `FundingArbitrageScanner`       | ✅  | same |
| **Launch arbitrage**        | `arbicore/scanners/launch_arbitrage/scanner.py`        | `LaunchArbitrageScanner`        | ✅  | same |
| **Flash loan arbitrage**    | `arbicore/scanners/flash_loan_arbitrage/scanner.py`    | `FlashLoanArbitrageScanner`     | ✅  | same (bridged via `arbicore/scanners/wave1b/bridge.py`) |
| **Cross scanner (Cex↔Dex, Dex↔Dex)** | `arbicore/scanners/live/cross.py`             | `CexDexScanner`, `DexDexScanner` | ✅  | `/arbicore/scanners/cross/status` |

### §1b. Route generation

`arbicore/scanners/flash_loan_arbitrage/route_search.py::RouteSearchEngine`
(192 LOC) — the actual multi-hop route generator (DFS over pool adjacency,
cycle detection, PoolNode/RouteCycle dataclasses). Used **inside**
`FlashLoanArbitrageScanner.scan()`. Not exposed as its own HTTP endpoint.

### §1c. Profitability engine

`arbicore/economics/net_profit.py::compute_net_profit()` — the actual net-profit
computer. Returns `NetProfitResult` with gas cost, fees, gross vs net USD.
Used internally by the scanners' economics modules
(`arbicore/scanners/*/economics.py`) — one per strategy — before an
opportunity is emitted. Not exposed as its own HTTP endpoint.

### §1d. `engines/` top-level layer (verdict / confidence / spread / …)

`app/backend/engines/pipeline.py`, `engines/verdict.py`, `engines/confidence.py`,
`engines/economics.py`, `engines/quality.py`, `engines/safety.py`,
`engines/spread.py`, `engines/capacity.py`, `engines/deployable.py`
(803 LOC total). **Grep for `from engines.` in `server.py` and `arbicore/`:
zero hits.** This entire folder is **DORMANT** — imported only by
`services/observation.py`, `services/execution/ledger.py`, and
`services/execution/arbitrage_intel.py`, all of which are themselves
downstream services. The actual pipeline logic used at runtime is
`arbicore/execution/pipeline.py::OpportunityPipeline`, not this
`engines/pipeline.py`. Historical duplicate.

---

## §2. Engine status matrix — the seven engines you asked about

| # | Engine (yours) | Where it lives | Implemented % | Production-ready? | Live data? | Mounted? | Dormant? | Placeholder? |
| - | :------------- | :------------- | :-----------: | :---------------: | :--------: | :------: | :------: | :----------: |
| 1 | **Scanner**            | Per-family classes in `arbicore/scanners/*/scanner.py` + `LiveMarketScanner`  | **95%**  | ✅ yes for LiveMarketScanner (spatial CEX/DEX); each strategy scanner instantiable via `ScannerActivation` | ✅ | ✅ (LiveMarketScanner autostarts; per-family via `_SCANNER_ACTIVATION`) | ❌  | ❌  |
| 2 | **Discovery**          | `arbicore/execution/discovery.py::ContinuousDiscovery` (+ `arbicore/scanners/discovery/*` for CoinGecko/DexScreener sources) | **90%**  | ✅ | ✅ (writes to `_DISCOVERY_REPO` + promotes to `_CANONICAL_OPP_REPO`) | ✅ endpoints `/execution/discovery/{status,tick,start,stop}` | ❌ code-wise, but **NOT autostarted at boot** — operator must POST `/start` | ❌ |
| 3 | **Opportunity detector** | `arbicore/execution/pipeline.py::OpportunityPipeline` + per-strategy verifiers (`arbicore/scanners/*/verifier.py`, 6 files) | **95%**  | ✅ | ✅ | ✅ `/arbicore/pipeline/evaluate` + implicit via `_AUTO_EXECUTOR` | ❌ | ❌ |
| 4 | **Route generator**    | `arbicore/scanners/flash_loan_arbitrage/route_search.py::RouteSearchEngine` (+ per-strategy variants inside each scanner's `sources.py`/`filter.py`) | **80%** — DFS multi-hop cycle detector present; not exposed via HTTP | ⚠️ ready but internal-only | ✅ | ❌ HTTP-wise (only reachable through the flash-loan scanner) | ⚠️ partially — no `/routes/generate` endpoint | ❌ |
| 5 | **Profitability engine** | `arbicore/economics/net_profit.py::compute_net_profit` + per-strategy `arbicore/scanners/*/economics.py` (6 files) | **90%**  | ✅ | ✅ (called inline by every scanner) | ❌ HTTP-wise | ⚠️ HTTP surface — no `/profitability/compute` endpoint | ❌ |
| 6 | **Execution planner**  | `arbicore/execution/planner.py::ExecutionPlanner` (540 LOC) + `_DRY_RUN_ENGINE` + `_CAPITAL_ALLOCATOR` + `_EXECUTION_PLANS_REPO` | **95%**  | ✅ | ✅ full plan lifecycle in Mongo | ✅ **10 endpoints** `/arbicore/execution/plans/{build,{id},list,simulate,sign,calldata,broadcast,…}` | ❌ | ❌ |
| 7 | **Flash-loan planner** | `arbicore/flashloan/operator_journey.py::FlashLoanOperatorJourney` (300 LOC) + `FlashLoanArbitrageScanner` + `route_search.py` | **90%**  | ✅ | ✅ | ✅ `/arbicore/flashloan/journey/run`, `/status` | ❌ | ❌ |

**Nothing in the primary pipeline is a placeholder.** Every engine has real
code with real Mongo repositories behind it. What IS a placeholder:

- The **`_V2_OPPS` list** merged into `GET /arbicore/opportunities` responses (server.py L485-526, 8 hardcoded opportunities that appear when canonical is thin).
- The **`_V2_DISCOVERY` list** in `GET /arbicore/discovery/candidates` (server.py L863).
- The **`_V2_SCANNERS` list** in `GET /arbicore/operations/scanners` (server.py L1263).

---

## §3. Canonical Opportunity endpoints — all mounted right now

The following are **live in `server.py`** as of `57b0e72`. Response schemas
inferred from the handler bodies and `_canonical_opp_to_contract` translator.

| # | HTTP | Path | Handler line | Backing engine | Response shape (top-level) | Consumed by frontend? | Notes |
| - | :--- | :--- | :----------: | :------------- | :------------------------- | :-------------------: | :---- |
| 1 | GET  | `/api/arbicore/opportunities`               | L537  | `_CANONICAL_OPP_REPO.find()` + `_V2_OPPS` merge | `{items:[…], total:int, source:"canonical"\|"preview"\|"canonical+preview", generated_at:iso}` | ✅ `OpportunitiesPage.jsx` via `v2Api.opportunitiesList()` | **Hybrid — preview merge to remove in Slice 1** |
| 2 | GET  | `/api/arbicore/opportunities/{opp_id}`      | L638  | `_CANONICAL_OPP_REPO.get()` + `_V2_OPPS` fallback | `{item:{…}, source, generated_at}` | ✅ `OpportunityDrawer.jsx` | **Hybrid — preview fallback to remove** |
| 3 | POST | `/api/arbicore/opportunities/{opp_id}/approve` | L713 | `_CANONICAL_OPP_REPO.upsert()` (canonical write); `_V2_OPPS` mutate on fallback | `{ok:true, item:{…}, source, generated_at}` | ✅ `OpportunitiesPage.jsx` action + `[A]` keyboard shortcut | **Hybrid mutation — preview branch to remove** |
| 4 | POST | `/api/arbicore/opportunities/{opp_id}/reject`  | L740 | same | same | ✅ `[R]` keyboard shortcut | **Hybrid — same as approve** |
| 5 | GET  | `/api/arbicore/opportunities/{opp_id}/timeline` | L810 | `_CANONICAL_OPP_REPO.get()` + `_OPPORTUNITY_JOURNAL.timeline()` fallback | `{items:[{ts,action,actor,reason,payload}, …], source, generated_at}` | ✅ `OpportunityDrawer.jsx` timeline panel | Uses real journal when canonical exists |
| 6 | GET  | `/api/arbicore/opportunities/summary` | L447 | **hardcoded literal** | `{total:14, by_family:{…}, by_chain:{…}, by_status:{…}, generated_at}` | ✅ `HomePage.jsx` + `AppShell.jsx` badge | **Pure placeholder — replace with `_CANONICAL_OPP_REPO.aggregate()`** |
| 7 | GET  | `/api/arbicore/dashboard/deck` | L422 | **hardcoded** 5 opps | `{deck:[…], pending_approvals:[], requires_attention:[], generated_at}` | ✅ `HomePage.jsx` + `OpsCenter.jsx` (old one under `pages/`) | **Pure placeholder — replace with `_CANONICAL_OPP_REPO.find(status=CANDIDATE)`** |
| 8 | GET  | `/api/arbicore/journal` | L3390 | `_OPPORTUNITY_JOURNAL.list()` | `{items:[…], total, generated_at}` | ✅ transitively via drawer timeline; direct call in `PostTradeDashboardPage` | Real |
| 9 | GET  | `/api/arbicore/journal/summary` | L3407 | `_OPPORTUNITY_JOURNAL.summary()` | aggregate stats | not yet | Real |
| 10 | GET  | `/api/arbicore/journal/{opportunity_id}` | L3413 | `_OPPORTUNITY_JOURNAL.get()` | `{item:{…}}` | via drawer timeline | Real |
| 11 | GET  | `/api/arbicore/execution/discovery/status` | L2794 | `_CONTINUOUS_DISCOVERY.status()` | discovery loop state | ✅ `FlashLoanOperatorPage.jsx` | Real |
| 12 | POST | `/api/arbicore/execution/discovery/tick` | L2802 | `_CONTINUOUS_DISCOVERY.tick_once()` | tick result | ✅ `FlashLoanOperatorPage.jsx` (operator-triggered) | Real |
| 13 | POST | `/api/arbicore/execution/discovery/start` | L2811 | `_CONTINUOUS_DISCOVERY.start()` | ok+status | not currently called from UI | Real; **can be autostarted via env var if we choose to add one** |
| 14 | POST | `/api/arbicore/execution/discovery/stop` | L2818 | `_CONTINUOUS_DISCOVERY.stop()` | ok+status | not currently called from UI | Real |
| 15 | POST | `/api/arbicore/pipeline/evaluate` | L3475 | `_OPPORTUNITY_PIPELINE.evaluate()` | `{result:{stages,decision,confidence,verdict,…}, generated_at}` | not yet from UI | Real — the actual "detector" endpoint |
| 16 | GET  | `/api/arbicore/execution/opportunities` | L2340 | reads `_CANONICAL_OPP_REPO` (execution-view) | `{items:[…]}` (executor filter) | ✅ `FlashLoanOperatorPage.jsx` | Real |
| 17 | GET  | `/api/arbicore/auto-executor/status` | L3490 | `_AUTO_EXECUTOR.status()` | end-to-end status | not yet | Real |
| 18 | GET  | `/api/arbicore/learning/status` | L3430 | `_LEARNING_LEDGER.status()` | learning loop state | not yet | Real |
| 19 | GET/POST | `/api/arbicore/roi-probability` | L458 | **hardcoded** returns `{sample_size:42, win_rate:0.643, …}` regardless of `route_id` | ROI stats | ✅ `OpsCenter.jsx` (old) | **Pure placeholder — should delegate to `arbicore/routes/arbicore.py::/outcomes?route_id=` or add a new one on `_LEARNING_LEDGER`** |

---

## §4. Frontend components displaying placeholder opportunities

| # | File | Widget | What it displays | Source when placeholder | API it consumes | Action for Slice 1 |
| - | :--- | :----- | :--------------- | :---------------------- | :-------------- | :------------------ |
| 1 | `app/frontend/src/v2/pages/OpportunitiesPage.jsx` | Table of opportunities | id, family, subject, chain, verdict, confidence, spread_bps, depth_usd, return_low/high, age | Backend `_V2_OPPS` merge branch triggers when Mongo thin → 8 fake rows show | `v2Api.opportunitiesList()` → `GET /api/arbicore/opportunities` | **Delete backend merge branch** — frontend already handles empty state. |
| 2 | `app/frontend/src/v2/components/OpportunityDrawer.jsx` | Detail panel + confidence breakdown + timeline | `data.confidence`, `data.reasoning.confidence_breakdown`, timeline events | Backend `_V2_OPPS.find(id)` fallback → drawer shows fake detail for the 8 fake ids | `v2Api.opportunityDetail(id)` + `v2Api.opportunityTimeline(id)` → `/opportunities/{id}` + `/timeline` | **Delete backend fallback** — return 404 when not in canonical repo. |
| 3 | `app/frontend/src/v2/pages/HomePage.jsx` | Deck of fresh opps + regime tile + summary badge | `opps.map(...)`, `opps[].confidence`, `summary.total`, `summary.by_family`, `regime.confidence` | Backend hardcoded literals in `/dashboard/deck`, `/dashboard/pulse`, `/opportunities/summary` | `v2Api.deck()`, `v2Api.pulse()`, `v2Api.opportunitiesSummary()` | **Rewrite three handlers** to read `_CANONICAL_OPP_REPO` + `_MID_READER.regime()`. |
| 4 | `app/frontend/src/v2/pages/FlashLoanOperatorPage.jsx` | Opportunity list (executor scoped) | `opportunities.map(...)`, `o.confidence`, `o.route`, `o.chain`, `o.expected_profit_usd`, `o.capital_required_usd` | Reads `/arbicore/execution/opportunities` which reads `_CANONICAL_OPP_REPO` — **already real**, no placeholder here | `/arbicore/execution/opportunities` | **No change needed for opp list.** (Card labels like "conf {o.confidence}" already render real data.) |
| 5 | `app/frontend/src/v2/pages/OpsCenter.jsx` (v2) | Left rail live opportunities count | reads `/arbicore/live/opportunities` | **Real** — `_LIVE_SCANNER.opportunities()` | `/arbicore/live/opportunities` | **No change.** |
| 6 | `app/frontend/src/pages/OpsCenter.jsx` (legacy, `/dashboard/deck` consumer) | Deck | Reads `/dashboard/deck` | Backend hardcoded | `/dashboard/deck` | Fixed transitively by fixing backend handler (item #3). |
| 7 | `app/frontend/src/pages/ApprovalConsole.jsx`, `OperatorConsole.jsx` | Legacy dashboards (pre-v2) | Not in current App.js routing | Not routed | — | Orphaned; out of scope for Slice 1. |

---

## §5. Exact replacement map (Slice 1 scope only)

Slice 1 = Opportunity Detection. Everything below can be delivered as one
release. The frontend already handles all the empty-state cases (per the
Empty-State Widget Sweep audit).

### 5a. Backend edits — exactly 6 endpoint bodies

| # | Placeholder | Canonical replacement | Engine | Frontend | Effort |
| - | :---------- | :-------------------- | :----- | :------- | :----- |
| 1 | `_V2_OPPS` array + `_hydrate_opps()` at `server.py:485-534` | **DELETE entirely** | — | (no consumer once removed) | 0.1 d |
| 2 | Merge branch at `server.py:568-580` in `GET /arbicore/opportunities` | Return only canonical items; add `source: "canonical"` unconditionally | `_CANONICAL_OPP_REPO` (already wired) | `OpportunitiesPage.jsx` (empty-state OK) | 0.2 d |
| 3 | Preview fallback at `server.py:648-680` in `GET /opportunities/{id}` | Return 404 when `_CANONICAL_OPP_REPO.get(id)` returns None | `_CANONICAL_OPP_REPO` | `OpportunityDrawer.jsx` | 0.2 d |
| 4 | `_V2_OPPS` mutation at `server.py:730-737` in `/approve` | Delete branch. Enforce `_CANONICAL_OPP_REPO.upsert()` write; 404 when missing. | `_CANONICAL_OPP_REPO` + `_OPPORTUNITY_JOURNAL.record_action(APPROVE)` | `[A]` shortcut | 0.2 d |
| 5 | `_V2_OPPS` mutation at `server.py:755-765` in `/reject` | Same as approve | Same | `[R]` shortcut | 0.2 d |
| 6 | `_V2_OPPS.find(id).timeline` fallback at `server.py:820-855` in `/timeline` | Return `_OPPORTUNITY_JOURNAL.timeline(opp_id)` directly. 404 when opp not in canonical. | `_OPPORTUNITY_JOURNAL` | `OpportunityDrawer.jsx` timeline | 0.3 d |
| 7 | `GET /arbicore/opportunities/summary` at `server.py:447-455` (hardcoded) | Aggregate `_CANONICAL_OPP_REPO.find({})` grouped by `.opportunity_type`, `.chain`, `.status` (small in-memory rollup) | `_CANONICAL_OPP_REPO` | `HomePage.jsx` badge, `AppShell.jsx` | 0.4 d |

**Total Slice-1 backend effort: ~1.6 dev-days.** (Below the 2.25 d I estimated
previously — because half the work is *deletions*, not additions.)

### 5b. Frontend edits — zero required

Every consumer already handles `items: []`, `data: null`, and 404. Confirmed
in `docs/roadmap_v2.10/EMPTY_STATE_WIDGET_SWEEP.md`. No JSX changes for Slice 1.

### 5c. Autostart consideration (out of Slice 1, recommend for Slice 2)

`_CONTINUOUS_DISCOVERY` is instantiated but never auto-`.start()`'d.
Without it running, the canonical repo stays empty and everything below the
detection layer has nothing to feed on. **Slice 2 should add an env-gated
autostart** (`ARBICORE_DISCOVERY_AUTOSTART=1`) mirroring the pattern already
used by `LIVE_MARKET_AUTOSTART=1`.

---

## §6. What this audit changes for the roadmap

Previous framing (docs/roadmap_v2.10/EXECUTION_PIPELINE_ROADMAP.md) treated
the pipeline as "canonical dormant". This audit corrects that:

- ✅ Canonical `_CANONICAL_OPP_REPO`, `_OPPORTUNITY_JOURNAL`,
  `_OPPORTUNITY_PIPELINE`, `_CONTINUOUS_DISCOVERY`, `_EXECUTION_PLANNER`,
  and `_AUTO_EXECUTOR` are **already instantiated and wired**.
- ✅ 19 real endpoints already serve real data through them.
- 🟡 The **only** production-blocking placeholders in the Opportunity
  Detection surface are the 6 preview-fallback branches listed in §5a and
  the 2 pure-hardcoded aggregate endpoints (`/summary`, `/dashboard/deck`).
- ❌ There is **no rebuild required.** Slice 1 is a scoped delete-plus-shape-polish.

Consequence for the critical path (Stages 1–4):

| Stage | Old estimate | New estimate |
| :---- | :----------: | :----------: |
| 1 Opportunity Detection | 2.25 d | **1.6 d** |
| 2 Discovery (+ autostart, mount `arbicore/routes/scanners.py`) | 3.25 d | 2 d |
| 3 Market Intelligence | 3.5 d | 2 d |
| 4 Execution Planning | 3 d | 1 d (mostly regression testing — the planner is already fully live) |
| **Critical-path to paper validation** | **12 d** | **~7 d** |

---

## §7. Deliverable — the wiring map you asked for

```
Placeholder                                              →  Canonical endpoint                             →  Engine                          →  Frontend component
------------------------------------------------------------  ------------------------------------------------  --------------------------------  ------------------------------------
_V2_OPPS[8 rows] merged into                             →  GET /api/arbicore/opportunities                 →  _CANONICAL_OPP_REPO             →  OpportunitiesPage.jsx (table)
     GET /arbicore/opportunities (server.py:568)            (already wired; delete merge)

_V2_OPPS[id] fallback in                                 →  GET /api/arbicore/opportunities/{id}            →  _CANONICAL_OPP_REPO             →  OpportunityDrawer.jsx (detail panel)
     GET /arbicore/opportunities/{id} (server.py:648)        (already wired; delete fallback → 404)

_V2_OPPS[id] mutation in                                 →  POST /api/arbicore/opportunities/{id}/approve   →  _CANONICAL_OPP_REPO             →  OpportunitiesPage.jsx [A] shortcut
     POST /arbicore/opportunities/{id}/approve               + _OPPORTUNITY_JOURNAL.record_action
        (server.py:730)                                      (delete preview branch)

_V2_OPPS[id] mutation in                                 →  POST /api/arbicore/opportunities/{id}/reject    →  _CANONICAL_OPP_REPO             →  OpportunitiesPage.jsx [R] shortcut
     POST /arbicore/opportunities/{id}/reject                + _OPPORTUNITY_JOURNAL.record_action
        (server.py:755)

_V2_OPPS[id].timeline fake steps in                      →  GET /api/arbicore/opportunities/{id}/timeline   →  _OPPORTUNITY_JOURNAL.timeline   →  OpportunityDrawer.jsx timeline panel
     GET /arbicore/opportunities/{id}/timeline               (delete fake steps; return journal directly)
        (server.py:820)

Hardcoded {total:14, by_family:{...}} in                 →  GET /api/arbicore/opportunities/summary         →  _CANONICAL_OPP_REPO.aggregate  →  HomePage.jsx summary badge · AppShell header
     GET /arbicore/opportunities/summary (server.py:447)     (rewrite handler; delete hardcoded)

Hardcoded 5-row deck in                                  →  GET /api/arbicore/dashboard/deck                →  _CANONICAL_OPP_REPO.find        →  HomePage.jsx deck (Stage 3, not Slice 1)
     GET /arbicore/dashboard/deck (server.py:422)            (Stage 3 — not in Slice 1 scope)
```

---

## §8. Recommendation

Proceed to **Slice 1 (Opportunity Detection)** with the reduced scope
above. Delete branches 1–7 in §5a. Expected total: **~1.6 dev-days**.

No dormant canonical routers need mounting for Slice 1 — the endpoints are
already served by `api_router` and already read from real engines. Slice 2
is where the router-mount work starts (for the per-family scanner status
detail from `arbicore/routes/scanners.py`).

Awaiting your explicit go before opening `hotfix/canonical-slice-1`.
