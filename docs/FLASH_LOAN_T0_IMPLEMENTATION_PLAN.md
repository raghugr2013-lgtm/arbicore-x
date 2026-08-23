# ArbiCore X — TIER-0 Correctness Implementation Plan

**Mode:** PLAN ONLY. No code modified, no branches merged/cherry-picked/rebased/reset, no VPS change, no production change.
**Baseline:** `main @ 43230f6` + the 44 intentional uncommitted preview-URL edits (preserved untouched).
**Inputs:** `docs/FLASH_LOAN_ARCHITECTURE_AUDIT.md` (Phase 0), `docs/FLASH_LOAN_MARKET_COMPETITIVE_AUDIT.md`.
**Tags:** `[FACT]` verified in code · `[INF]` inference · `[REC]` recommendation · `[VPS?]` needs VPS verification.

**Guardrails honored throughout:** never lower gates (Gate 7 stays **$25**), never disable signing, never fabricate data, never auto-promote modes, never delete historical evidence.

---

## 0. T0 objective & non-goals

**Objective:** make the Base flash-loan pipeline *trustworthy and honest end-to-end* — one authoritative scanner, no synthetic contamination, no silent zeroing, one economics number, one RPC source, a real liquidity gate, provenance-clean certification, and clean seams for T1/T2 — **without** adding chains, searcher performance, or new strategies.

**Non-goals (explicitly deferred):** local pool-state cache, local AMM/CL math, per-block trigger, revm hot-loop sim, private RPC/WSS, optimal sizing engine, Morpho/UniV4/Pancake venues, Arbitrum, liquidation/backrun families. T0 only prepares interfaces for them (§T0-14).

---

## T0-1 · Canonical Flash-Loan Scanner authority + deterministic live-wiring

- **Exact files:** `arbicore/runtime/composition.py` (`get_flash_loan_arb_scanner` ~697, `activate_canonical_flash_loan_scanner` ~766), `server.py` (thin/canonical wiring ~235-263, canonical activation ~6852, `_arbicore_runtime_autostart` ~6926-6999), `arbicore/scanners/flash_loan_arbitrage/scanner.py` (`quote_provider_is_default`, `set_quote_provider`), `arbicore/scanners/flash_loan_arbitrage/verifier.py` (noop path).
- **Current behavior `[FACT]`:** canonical scanner ships `quote_provider=None` → falls back to `noop_quote_provider` (returns `None` → every candidate `denied:venue_unreadable`). Live provider is only installed by `activate_canonical_flash_loan_scanner(quoter_registry)`, which runs behind `ARBICORE_RUNTIME_AUTOSTART` (default off). So in a default deploy the authoritative scanner emits nothing while the thin activator can still populate the UI.
- **Proposed behavior `[REC]`:** (a) On startup, if the flash-loan strategy is in an analysis mode (PAPER/SHADOW/LIMITED_LIVE/FULL_LIVE), the canonical scanner MUST be activated with a **live** quote provider *or* the scanner MUST be held in an explicit `NOT_READY` state surfaced to the operator (never silently running on noop in production). (b) Add a hard guard: if `quote_provider_is_default` is True while the scanner is enabled in a non-OBSERVE mode, emit a `readiness_error` (health-visible) and refuse to mark the scanner "active". (c) Keep `noop_quote_provider` strictly for cold-start/tests; it can never be the *production* path silently.
- **Root cause addressed:** noop-as-silent-production quote path; canonical authority gated behind an off-by-default env.
- **Implementation approach:** introduce a small readiness resolver in composition that (1) resolves the live `QuoterRegistry`, (2) calls `set_quote_provider(make_live_quote_provider(...))`, (3) records `quote_provider="live|noop"` + `activation_source` into a health/status doc; a startup hook invokes it deterministically when FL mode ≠ OBSERVE. Preserve `ARBICORE_RUNTIME_AUTOSTART` as an *additional* control for *starting the loop*, but decouple "quote provider is live" from it.
- **Dependencies:** T0-5 (RPC canonicalization) so the QuoterRegistry has a real endpoint; T0-3 (mode resolution) to know FL mode.
- **DB impact:** none (in-memory scanner state + a status/health doc, additive).
- **API impact:** extend existing scanner-status endpoint to expose `quote_provider`, `activation_source`, `readiness_error`. No breaking change.
- **Frontend impact:** operator console should show "quote provider: live/noop" + readiness error (read-only display; optional in T0).
- **Test requirements:** unit — enabled+non-OBSERVE+noop ⇒ readiness_error, not "active"; activation installs live provider deterministically; noop still allowed in OBSERVE/tests.
- **Deployment risk:** LOW-MEDIUM — could surface a NOT_READY state that was previously hidden (this is desired). No data change.
- **Rollback:** revert composition/server wiring commit; scanner returns to prior gated behavior.
- **Complexity:** MEDIUM.
- **Blocking for T1/T2:** **YES** — T2 replaces the quote provider with the local-cache quoter; a clean, single activation seam is required.

---

## T0-2 · Quarantine thin_activator / synthetic contamination

- **Exact files:** `arbicore/execution/discovery.py` (`ContinuousDiscovery._evaluate_candidate` canonical upsert block ~265-311), `server.py` (`_CONTINUOUS_DISCOVERY` construction + `_canonical_repo` binding ~235-263; discovery API `/discovery/start|tick` ~4113-4138), `arbicore/data/mongo/opportunity_repo_mongo.py` (`upsert` ~131, `_apply_provenance_filter` ~43), `arbicore/paper/runner.py` (`_fetch_opps` ~255-266).
- **Current behavior `[FACT]`:** thin activator builds a `CanonicalOpportunity` with `source_data_quality=DataProvenance.SIMULATED`, `metadata.engine="thin_activator"`, and **upserts into `_CANONICAL_OPP_REPO`** (looked up lazily via `import server`). PaperRunner `_fetch_opps` calls `find({}, limit=...)` with **no provenance filter**, so it drains SIMULATED rows into `pipeline.evaluate`. `MongoOpportunityRepository` already supports `_apply_provenance_filter`/`find(provenance_filter=...)`, but `upsert` has **no gate**.
- **Proposed behavior `[REC]` (defense in depth):**
  1. **Source quarantine:** thin activator writes to a **separate research collection** (`arbicore_research_candidates`) tagged `provenance=SYNTHETIC` (add a `SYNTHETIC`/`TEST` provenance tier if not present; today thin uses `SIMULATED`). It MUST NOT write to `_CANONICAL_OPP_REPO`.
  2. **Boundary write-gate:** `MongoOpportunityRepository.upsert` asserts `opp.source_data_quality ∈ {REAL, VERIFIED_REAL}` for the production canonical collection; non-real writes are rejected (raise) or diverted with a logged provenance-audit row. Keep a config flag `ARBICORE_CANONICAL_STRICT_PROVENANCE=true` (default true; false only for legacy tests).
  3. **Read-side filter:** PaperRunner `_fetch_opps` passes `provenance_filter=frozenset({REAL, VERIFIED_REAL})`.
  - Preserve the thin activator as an **importable research tool** (tests + optional research endpoint), never in the production canonical path.
- **Root cause addressed:** competing authority + SIMULATED masquerading as executable.
- **Implementation approach:** (a) remove the `_CANONICAL_OPP_REPO` lazy-upsert in `discovery.py`; add a `research_repo` injection writing to `arbicore_research_candidates`; (b) add the provenance assertion in `opportunity_repo_mongo.upsert`; (c) add the provenance_filter to PaperRunner fetch. All additive/subtractive at boundaries; no schema rewrite.
- **Dependencies:** T0-7 (provenance tiers) — align enum; T0-1 (so canonical stream is the real source once thin is removed).
- **DB impact:** **new collection** `arbicore_research_candidates` (additive, indexes on opportunity_id/created_at). Existing `opportunities`/`arbicore_opportunities` untouched except future writes are provenance-gated. Historical SIMULATED rows preserved (see T0-9 for optional tagging/backfill).
- **API impact:** thin discovery endpoints keep working but report they write to the research collection; add `provenance` to opportunity read payloads if not already present.
- **Frontend impact:** any UI page reading canonical opportunities will now show **only REAL** rows (may look emptier — expected/correct). A separate "research/synthetic" view can display the research collection (optional, not T0).
- **Test requirements:** synthetic-contamination test — thin tick must NOT create a canonical row; canonical `upsert` of SIMULATED must be rejected; PaperRunner must skip SIMULATED; research collection receives the thin row.
- **Deployment risk:** MEDIUM — canonical opportunity counts drop to honest levels; communicate. No historical deletion.
- **Rollback:** re-enable thin canonical upsert + relax `upsert` gate via `ARBICORE_CANONICAL_STRICT_PROVENANCE=false`.
- **Complexity:** MEDIUM.
- **Blocking for T1/T2:** **YES** — a clean canonical stream is the substrate everything downstream trusts.

---

## T0-3 · OBSERVE silent fallback → explicit readiness failure

- **Exact files:** `arbicore/execution/pipeline.py` (`_resolve_mode` ~543-573, OBSERVE short-circuit ~251-261), `arbicore/execution/mode.py` (`ExecutionModeRepo.ensure_defaults` ~141-164, `default_mode_map` ~82), `server.py` (`_seed_execution_substrate` startup ~8068-8082).
- **Current behavior `[FACT]`:** `_resolve_mode` returns `"OBSERVE"` as the fallback when (a) no `execution_mode_state` row matches the strategy after raw/lower/upper normalization, or (b) a read exception occurs. The pipeline then records `"mode is OBSERVE — no analysis"` and stops. This silently zeroes the funnel and is indistinguishable from a legitimate OBSERVE posture. `ensure_defaults()` IS wired at startup and is idempotent.
- **Proposed behavior `[REC]`:** distinguish **three** cases:
  1. **Legitimate OBSERVE** — a seeded row explicitly says `mode=OBSERVE`. Behavior unchanged (record + stop). ✅ preserved.
  2. **Missing mode row** (strategy known but unseeded) — return a distinct sentinel `MODE_UNRESOLVED` → pipeline records an explicit `readiness_error` outcome (`config_missing: no execution_mode_state row for '<strategy>'`), increments a health counter, and does NOT silently label it "OBSERVE / no analysis".
  3. **Mode read exception** — return `MODE_ERROR` → explicit `infra_error` outcome + health flag (not OBSERVE).
  - Keep case-normalization. Keep `ensure_defaults()` at boot, and add a **startup readiness assertion** that logs/flags if `execution_mode_state` is empty after seeding (catches wrong-DB/`factory-mongo` mismatch `[VPS?]`).
- **Root cause addressed:** OBSERVE-as-hidden-failure; undetected seeding-against-wrong-DB.
- **Implementation approach:** add explicit return states in `_resolve_mode`; branch in `evaluate` to emit readiness/infra outcomes; add a startup health check that counts seeded rows and records a health doc.
- **Dependencies:** none (self-contained); complements T0-7 (certification treats readiness_error/infra_error as non-executable, non-synthetic).
- **DB impact:** none (health doc additive). Reads existing `execution_mode_state`.
- **API impact:** health/status endpoint exposes `mode_unresolved_count`, `seed_ok`. Pipeline outcome vocabulary gains `readiness_error`/`infra_error` (additive).
- **Frontend impact:** operator console can surface "N opportunities blocked: mode unresolved" (optional in T0).
- **Test requirements:** mode-resolution tests — seeded OBSERVE ⇒ observe (unchanged); unseeded strategy ⇒ readiness_error (NOT observe); wrong-case strategy resolves; read exception ⇒ infra_error; empty state after seed ⇒ startup flag.
- **Deployment risk:** LOW — surfaces previously hidden failures; no data change.
- **Rollback:** revert pipeline/mode changes; fallback returns to plain OBSERVE.
- **Complexity:** LOW-MEDIUM.
- **Blocking for T1/T2:** **YES** (soft) — trustworthy funnel accounting is required before optimizing throughput.

---

## T0-4 · Economics unification

- **Exact files:** canonical kernel `arbicore/scanners/economics.py` (`aggregate_economics` ~145, `EconomicAssessment` ~118, `per_chain_gas_estimate_usd` ~78, `mev_penalty_pct` ~105); second surface `arbicore/economics/net_profit.py` (`compute_net_profit` ~51, `NetProfitResult` ~32); consumers `arbicore/scanners/flash_loan_arbitrage/economics.py` (uses `aggregate_economics` ✅) and `arbicore/economics/opportunity_engine.py` (uses `compute_net_profit`, ~241-350).
- **Current behavior `[FACT]`:** two profitability computations. `aggregate_economics` (pct-based → `expected_profit_usd`, `profitable`) feeds the **authoritative verifier + Gate 7** (`atomic_profit_usd = EconomicAssessment.expected_profit_usd`). `compute_net_profit` (usd-based → `gross/total_cost/net_profit_usd`) feeds the `OpportunityEngine` (the research/thin `evaluate_live` path). Two different numbers → inconsistent ranking.
- **Proposed behavior `[REC]`:** designate **`aggregate_economics`/`EconomicAssessment` as THE canonical economic kernel** (it models fee+slippage+gas+MEV and drives the production gate). Refactor `compute_net_profit` into a **thin USD *view/adapter* over `EconomicAssessment`** (or mark it `research-only` and route `OpportunityEngine` through the canonical kernel) so there is exactly one source of truth for the profit numbers. **Do not change Gate 7 semantics or the $25 floor.** T0 does not add worst_case/execution_probability/margin_bps (those are T1/T2 extensions of the *same* kernel).
- **Root cause addressed:** dual economics surfaces → untrustworthy ranking.
- **Implementation approach:** minimal viable T0 = (a) document `aggregate_economics` as canonical; (b) make `OpportunityEngine` compute via `aggregate_economics` and derive USD via a small projection, OR (since `OpportunityEngine`/thin is quarantined from canonical in T0-2) explicitly namespace `compute_net_profit` as `research` and add a shared `to_net_profit_usd(EconomicAssessment)` helper used by both. Prefer the shared-helper route (lowest risk, no behavior change to the production verifier).
- **Dependencies:** T0-2 (quarantine reduces production exposure of the second surface).
- **DB impact:** none.
- **API impact:** none (numbers already surfaced via verifier metadata). Optionally expose a unified economics block.
- **Frontend impact:** none required.
- **Test requirements:** economics-consistency test — for a fixed route+quote, canonical kernel and any USD view agree to tolerance; Gate 7 boundary at exactly $25 unchanged (24.99 fail / 25.00 pass).
- **Deployment risk:** LOW (production verifier path unchanged if shared-helper route chosen).
- **Rollback:** revert helper; independent calcs restored.
- **Complexity:** LOW-MEDIUM.
- **Blocking for T1/T2:** **YES** (soft) — T1 sizing + T2 ranking must extend one kernel.

---

## T0-5 · RPC configuration unification

- **Exact files:** canonical namespace consumers `arbicore/execution/{gas,simulation,mev,broadcast,quoter,wallet_balance,technical_validation,atomic_executor_sim,operator_wizard}.py` (all read `ARBICORE_RPC_URL` / `ARBICORE_RPC_URL_{CHAIN}`), resolver `arbicore/config/persistent.py` (~230-231, ~259-260, ~395-396), shim `arbicore/config/env_sync.py`; **legacy consumers** `arbicore/paper/simulator.py` (~251-256 reads `BASE_RPC_URL`), `arbicore/data/scanner_config_repo.py` + `scanner_config_defaults.py` (store `rpc_env_var: BASE_RPC_URL/ETH_RPC_URL/...`); provenance chain-liveness sources reference `<CHAIN>_RPC_URL` in `arbicore/data/provenance.py`.
- **Current behavior `[FACT]`:** two namespaces. **Canonical:** `ARBICORE_RPC_URL` + `ARBICORE_RPC_URL_{CHAIN}`, populated by `env_sync` from persistent `NetworkConfigRepo` (UI-managed) with resolver precedence `ARBICORE_RPC_URL_{CHAIN}` → `ARBICORE_RPC_URL`. **Legacy:** `<CHAIN>_RPC_URL` (`BASE_RPC_URL`, `ETH_RPC_URL`, …) read by `paper/simulator.py` and referenced by scanner-config. `env_sync` writes the ARBICORE_* vars but **not** the legacy aliases → a component reading `BASE_RPC_URL` can diverge from what the UI shows.
- **Proposed behavior `[REC]`:** **one canonical model = persistent `NetworkConfigRepo` → `ARBICORE_RPC_URL_{CHAIN}` (chain-specific) → `ARBICORE_RPC_URL` (any)**, with explicit precedence: `ARBICORE_RPC_URL_{CHAIN}` > `ARBICORE_RPC_URL` > legacy `<CHAIN>_RPC_URL` (compat only). Two-part fix:
  1. **Writer:** extend `env_sync.sync_env_from_network_config` to ALSO export the legacy alias `<CHAIN>_RPC_URL` (so legacy readers stay consistent with the UI during migration).
  2. **Readers:** migrate `paper/simulator.py` (and scanner-config `rpc_env_var` resolution) to a single helper `resolve_rpc_url(chain)` in `persistent.py` implementing the precedence above. Keep legacy env read as the lowest-precedence fallback (backward compatible).
  - Add a deterministic `resolve_rpc_url(chain)` used everywhere a chain RPC is needed.
- **Root cause addressed:** "UI says configured but scanner reads a different var".
- **Implementation approach:** add `resolve_rpc_url(chain)` (precedence-ordered) in `persistent.py`; point legacy readers at it; extend `env_sync` to write legacy aliases. No secrets logged — health/presence only (§ no-secret rule).
- **Dependencies:** none; unblocks T0-1 (live quoter needs a deterministic endpoint).
- **DB impact:** none (reads persistent `network_config`).
- **API impact:** network settings apply/rollback endpoints already call `env_sync`; now also set legacy aliases. Health endpoint reports resolved-RPC **presence** (never value).
- **Frontend impact:** none (UI already manages persistent network config).
- **Test requirements:** RPC-precedence tests — chain-specific wins over generic wins over legacy; env_sync writes both namespaces; `resolve_rpc_url("base")` deterministic; missing config → explicit unset (fails fast, no silent default).
- **Deployment risk:** LOW-MEDIUM (env var writes only). `[VPS?]` verify which var the deployed container actually has set.
- **Rollback:** revert env_sync + resolver; legacy readers restored.
- **Complexity:** MEDIUM.
- **Blocking for T1/T2:** **YES** — T1 private RPC/WSS + T2 cache all depend on one deterministic RPC resolver.

---

## T0-6 · TVL sentinel replacement + real-TVL interface

- **Exact files:** `arbicore/discovery/base_venues.py` (`build_pool_graph` ~123-149, hardcoded `tvl_usd=5_000_000.0`), gate consumer `arbicore/scanners/flash_loan_arbitrage/filter.py` (Gate 8 liquidity depth), route TVL prune `arbicore/scanners/flash_loan_arbitrage/route_search.py` (~129 `min_pool_tvl_usd`), verifier min_tvl (`verifier.py` ~155-158).
- **Current behavior `[FACT]`:** every pool gets `tvl_usd=5_000_000` sentinel → Gate 8 (liquidity depth) and route-search TVL prune are effectively no-ops; liquidity is not real. Also live_quote_provider's `depth_usd` derives from this sentinel.
- **Proposed behavior `[REC]`:** introduce a **`TVLProvider` interface** (`get_pool_tvl_usd(chain, pool) -> Optional[float]`) with:
  - **T0 minimal real implementation:** derive per-pool TVL from the *same live quoter/pool reads* already available (e.g., token balances × token USD price for the pool address), cached briefly in Redis. If a lightweight on-chain read is too heavy for T0, use a **DexScreener/subgraph read** for Base pools as the T0 source (already in provenance registry as REAL hint) — clearly tagged and cached.
  - **Fallback behavior when TVL cannot be verified:** the pool is treated as **`tvl_unknown`** → Gate 8 **fails closed** (route denied `gate_8:liquidity_unverifiable`) rather than passing on a fabricated sentinel. This is honest and safe (no false executable).
  - Remove the `5_000_000` sentinel; `build_pool_graph` no longer fabricates TVL.
- **Root cause addressed:** fabricated liquidity → false positives / bad fills / no real depth gate.
- **Implementation approach:** define `TVLProvider` protocol + a Base implementation + Redis cache with TTL; wire it into `pool_loader`/verifier so `min_pool_tvl_usd_in_route` is real; Gate 8 fails-closed on unknown. Keep it lightweight (cached, not per-quote).
- **Dependencies:** T0-5 (RPC) if using on-chain reads; T0-1 (quoter available).
- **DB impact:** optional TVL cache (Redis) — no Mongo change. Optional `venue_capability`/tvl snapshot collection (additive) if persistence desired.
- **API impact:** health endpoint reports TVL source + freshness; scanner status shows `gate_8` denials with `liquidity_unverifiable` reason.
- **Frontend impact:** none required (metrics only).
- **Test requirements:** TVL/liquidity-gate tests — known-high-TVL passes Gate 8; below-floor fails `gate_8:depth`; unverifiable TVL fails-closed `gate_8:liquidity_unverifiable`; sentinel removed (no route passes on fabricated depth).
- **Deployment risk:** MEDIUM — with fails-closed, emission counts may drop until a real TVL source is wired; correct but visible.
- **Rollback:** feature-flag `ARBICORE_TVL_PROVIDER=sentinel|live`; sentinel path restores old behavior for emergency rollback (documented as non-production).
- **Complexity:** MEDIUM.
- **Blocking for T1/T2:** **YES** — T1 real-TVL + optimal sizing consume this interface directly.

---

## T0-7 · Certification / provenance filtering

- **Exact files:** `arbicore/certification/engine.py` (`_sample_evidence_delta` ~471, executable/outcome counting ~195-247, `_grade_cycle` ~288-345), `arbicore/paper/evidence.py` (evidence model ~79-131 — has `mode`, `outcome`; **no `source_data_quality`**), `arbicore/paper/repo.py` (evidence persistence + queries), `arbicore/models/enums.py` (`DataProvenance`).
- **Current behavior `[FACT]`:** certification counts evidence deltas by `outcome` and computes `executable_rate = executable/processed` with **no provenance filter**. Paper evidence carries `mode`+`outcome` but not the opportunity's `source_data_quality`, so certification cannot exclude synthetic-derived evidence → SIMULATED thin rows that were paper-evaluated could inflate executable metrics.
- **Proposed behavior `[REC]`:**
  1. **Stamp provenance on evidence:** add `source_data_quality` (from the opportunity) + `mode` to each `EvidenceBundle`/paper evidence row (additive field; historical rows read as `unknown`).
  2. **Partition certification counts** by provenance and mode: `_sample_evidence_delta` returns per-provenance counts; **`executable_count` and `executable_rate` are computed over REAL/VERIFIED_REAL evidence only**; SIMULATED/SYNTHETIC/TEST counted separately and reported but **never** in the pass/warn grading.
  3. Preserve evidence integrity + signing exactly (`evidence/signer.py`, `signing_config.py`) — no field removed from `HASHED_FIELDS`; new provenance field added to the bundle schema and (if it must be integrity-bound) added to `HASHED_FIELDS` in a **versioned** bundle (`bundle_version` bump) so historical signed bundles stay verifiable.
- **Root cause addressed:** synthetic evidence contaminating executable-rate/profitability certification.
- **Implementation approach:** thread `source_data_quality` from opportunity → pipeline → evidence bundle; extend `_sample_evidence_delta` query/counting to group by provenance; grade on the REAL subset. Bump `EVIDENCE_BUNDLE_VERSION` if hashing scope changes.
- **Dependencies:** T0-2 (provenance tiers), T0-3 (readiness/infra outcomes excluded from executable).
- **DB impact:** additive fields on `arbicore_paper_evidence`/`evidence_bundles`; **no rewrite, no delete**. Historical rows lack the field → treated as `unknown` and excluded from REAL executable-rate (documented). Optional backfill (T0-9).
- **API impact:** certification/metrics endpoints gain per-provenance breakdown (`real`, `simulated`, `synthetic`, `paper`, `shadow`). Additive.
- **Frontend impact:** certification dashboard should show REAL vs synthetic split (optional in T0; metrics available regardless).
- **Test requirements:** certification-filtering tests — a cycle with mixed REAL+SIMULATED evidence grades executable_rate on REAL only; synthetic never counts as executable; signed historical bundle still verifies after schema/version bump; unsigned-by-config remains unsigned (signing not disabled).
- **Deployment risk:** MEDIUM — certified executable_rate may drop to honest values.
- **Rollback:** revert counting change (metrics revert to unfiltered); evidence field is additive and harmless if unused.
- **Complexity:** MEDIUM-HIGH (touches signing scope — handle via version bump).
- **Blocking for T1/T2:** **YES** (soft) — trustworthy certification is the gate before any live promotion.

---

## T0-8 · Minimal ChainAdapter foundation (interface only; no new chains)

- **Exact files (new + isolate):** new `arbicore/chains/adapter.py` (protocol) + `arbicore/chains/base_adapter.py` (Base impl wrapping existing wiring); isolate Base assumptions currently hardcoded in `arbicore/discovery/base_venues.py` (`CHAIN="base"`, token map, venue list, router allowlist, PROBE_AMOUNT), `arbicore/scanners/flash_loan_arbitrage/economics.py` (`FLASH_LOAN_PROVIDERS.supports_chains`), `arbicore/execution/gas.py` (per-chain gas), `arbicore/config/persistent.py` (`resolve_rpc_url`).
- **Current behavior `[FACT]`:** no `ChainAdapter`; Base specifics are scattered constants/modules. Multi-chain would require touching many files.
- **Proposed behavior `[REC]`:** define a **minimal `ChainAdapter` protocol** exposing exactly what the FL pipeline needs today: `chain_id`, `native_token`, `resolve_rpc_url()`, `token_registry()`, `dex_registry()`, `flashloan_provider_registry()`, `quote_provider()`, `gas_estimator()`, `tvl_provider()`, `executor_address()`, `health()` / `capability_flags()`. Ship **only `BaseChainAdapter`** in T0 (wraps the existing Base wiring — a pure refactor of accessors, no behavior change). No Arbitrum/other adapters. Goal: make "add Arbitrum" later = write one adapter + config, not edit the pipeline.
- **Root cause addressed:** Base-specific assumptions block clean multi-chain (T4).
- **Implementation approach:** introduce the protocol + Base adapter that delegates to existing functions; **do not** rip out the current call sites in T0 beyond what's needed to route through the adapter cleanly. Keep it thin to respect the resource target.
- **Dependencies:** T0-5 (`resolve_rpc_url`), T0-6 (`TVLProvider`), T0-1 (quote provider seam).
- **DB impact:** none.
- **API impact:** optional `/chains` health endpoint returning Base capability flags (additive).
- **Frontend impact:** none required.
- **Test requirements:** chain-adapter tests — `BaseChainAdapter` returns correct chain_id/native/rpc/registries; capability flags reflect real health; FL pipeline runs unchanged through the adapter (regression parity).
- **Deployment risk:** LOW (refactor with parity tests).
- **Rollback:** revert adapter; direct wiring restored.
- **Complexity:** MEDIUM.
- **Blocking for T1/T2:** **NO for T1/T2 Base performance; YES for T4 (Arbitrum).** Recommended in T0 because doing it before T2 avoids re-plumbing the cache/quoter later.

---

## T0-9 · Database / migration safety

- **Affected collections `[FACT]`:** `arbicore_opportunities` / `opportunities` (canonical write-gate), `arbicore_paper_evidence` + `evidence_bundles` (add provenance/mode fields), `execution_mode_state` + `execution_mode_audit` (seed assertion), `arbicore_discovery_candidates` (existing) + **new** `arbicore_research_candidates` (thin quarantine), certification run docs, `network_config` (RPC).
- **Migration/backfill requirements `[REC]`:**
  - **Additive only.** New fields (`source_data_quality`, `mode` on evidence) default to `unknown` for historical rows; certification excludes `unknown` from REAL executable-rate.
  - **Optional backfill (idempotent, reversible):** tag historical `opportunities` rows with `metadata.engine=="thin_activator"` as `SYNTHETIC` for clean historical certification; join evidence→opportunity to backfill `source_data_quality`. Backfill is a **read-then-write script**, dry-run first, no deletes.
  - **Never delete historical evidence** (auditability). Unsigned historical bundles stay unsigned; do not retro-sign.
  - `[VPS?]` Confirm canonical DB is `factory-mongo/arbicore_x` (Phase-0 finding) before running any migration; do NOT touch `arbicore-x-mongo`.
- **Deployment risk:** LOW if additive; MEDIUM if backfill run (mitigate: dry-run + count-diff + backup).
- **Rollback:** additive fields are inert; backfill script must ship with an inverse (untag) and a pre-backfill snapshot.
- **Complexity:** LOW-MEDIUM.
- **Blocking for T1/T2:** **NO** (backfill optional).

---

## T0-10 · Testing — categories & acceptance criteria

All deterministic, fixture-based, offline (no live RPC in unit tests). Existing suites live in `app/backend/tests/` (+ `_pending_scanner_activation/`).

| Category | Key cases | Acceptance criteria |
|---|---|---|
| Real vs synthetic provenance | thin tick; canonical upsert of SIMULATED; research collection write | SIMULATED never in canonical repo; `upsert` gate rejects non-REAL; research row created |
| Mode resolution | seeded OBSERVE; unseeded strategy; wrong-case; read error; empty-after-seed | OBSERVE preserved; unseeded ⇒ `readiness_error` (not observe); case resolves; error ⇒ `infra_error`; empty ⇒ startup flag |
| Scanner authority | enabled+non-OBSERVE+noop; activation installs live | noop never "active" in production; activation deterministic; status shows `quote_provider=live` |
| Economics consistency | fixed route/quote across kernels; Gate 7 boundary | canonical kernel == USD view (tolerance); 24.99 fails / 25.00 passes (floor unchanged) |
| RPC precedence | chain-specific vs generic vs legacy; env_sync dual-write; missing | precedence deterministic; both namespaces written; missing ⇒ explicit unset (fail fast) |
| TVL / liquidity gate | high TVL; below floor; unverifiable | pass; `gate_8:depth`; fail-closed `gate_8:liquidity_unverifiable`; no sentinel pass |
| Certification filtering | mixed REAL+SIMULATED cycle; signed historical verify | executable_rate on REAL only; synthetic excluded; historical signature verifies post version-bump; signing not disabled |
| Paper runner | provenance-filtered fetch; idempotency; stale reprocess | drains REAL only; no duplicate evidence; stale threshold deterministic |
| Shadow certification | delta counting; provenance partition; grading | deltas exclude synthetic; grade uses REAL subset; no double-count inflation |
| Base flash-loan pipeline (integration) | discover→route→quote(mocked live)→economics→gates→emit→paper→cert | end-to-end produces REAL provenance opportunity, honest gate reasons, provenance-clean certification |

**Regression gate:** existing FL/scanner/mode/paper/cert suites must remain green (parity for T0-8 refactor).

---

## T0-11 · Deployment sequence (Docker / VPS)

`[REC]` (main agent will NOT execute; operator-run on VPS):
1. **Pre-deploy checks:** `git status` clean except the 44 known URL edits; confirm `main@43230f6`; confirm canonical DB = `factory-mongo/arbicore_x` `[VPS?]`; record baseline counts (`opportunities`, `arbicore_paper_evidence`, `evidence_bundles`, `execution_mode_state`) — **redacted, presence/counts only, no secrets**.
2. **Backup:** `mongodump` of `arbicore_x` (all affected collections) + store SHA256 of dump; snapshot `.env` presence (not values).
3. **Migration order:** (a) deploy code with `ARBICORE_CANONICAL_STRICT_PROVENANCE=true`, `ARBICORE_TVL_PROVIDER=live`; (b) run additive index creation; (c) OPTIONAL dry-run backfill → review count-diff → apply; (d) restart.
4. **Container restart:** rebuild backend + frontend images only if code changed; `docker compose up -d --no-deps backend frontend opportunity-center`. No DB container restart. `.env`/dependency changes ⇒ restart required (env-only change ⇒ backend restart).
5. **Health checks:** `/api/arbicore/health` shows seed_ok, quote_provider=live, RPC presence, TVL source fresh; scanner status shows `quote_provider=live`, honest gate reason histogram; certification metrics show REAL vs synthetic split; post-counts ≥ pre-counts (no data loss).
6. **Rollback:** `docker compose` back to previous image tag; set `ARBICORE_CANONICAL_STRICT_PROVENANCE=false` + `ARBICORE_TVL_PROVIDER=sentinel` to restore prior behavior without redeploy if needed; restore `mongodump` only if a backfill went wrong (additive fields need no restore).

**Deployment risk overall:** MEDIUM — the visible effect is *honest* (fewer canonical opportunities, honest executable_rate). No data destruction. All changes flag-guarded.

---

## T0-12 · Git / branch safety

- Baseline = **`main@43230f6`**. `[FACT]` all required FL/scanner/mode/paper/cert/RPC/evidence code is on main.
- **Do NOT merge** `feature/ui-v2-slices-0-2` (superseded), `archive-v1` (v1 archive). Phase-0 confirmed no unique required code outside main.
- **`scanner-bootstrap-validator-fix`:** already contained in main (0 commits ahead; main is +2). Audit finds **nothing genuinely missing from main** → do not merge.
- **Preserve the 44 uncommitted preview-URL edits** — do not reset/clean/stash/overwrite/discard. Recommend committing them as an isolated commit ("chore: point tests/userscripts at flash-execution preview host") before T0 work begins, on a **new T0 feature branch off `main@43230f6`** (e.g. `t0/flash-loan-correctness`).
- Rotate the PAT embedded in the `origin` remote URL (Phase-0 security note).

---

## T0-13 · Resource target

`[INF]` T0 is intentionally lightweight — no cache, no WSS, no sim hot-loop. Additions: a Redis TVL cache (small), additive Mongo fields/collection, per-boundary provenance counting. **Negligible CPU/RAM footprint**; the 12 vCPU / 48 GB box stays reserved for T1/T2 searcher work. TVL provider must be **cached/TTL'd** (not per-quote) to avoid RPC pressure.

---

## T0-14 · Future T1/T2 compatibility (seams T0 must leave clean)

| Future need | T0 seam provided |
|---|---|
| Real TVL | `TVLProvider` interface (T0-6) — swap DexScreener→on-chain later |
| Optimal sizing | canonical economics kernel (T0-4) accepts size input; `size_optimizer` wires to it |
| Private Base RPC/WSS | `resolve_rpc_url(chain)` (T0-5) — point at private endpoint via persistent config |
| Local pool-state cache | quote-provider activation seam (T0-1) — replace `make_live_quote_provider` with cache-backed quoter |
| Local AMM/CL math | quote provider is an interface; cache quoter drops in behind it |
| Per-block triggering | scanner loop currently timer-based; T0 keeps `_tick` as the single entry so a block-event trigger can replace the timer |
| Fast-filter → revm sim | verifier already has quote→economics→gate stages; sim slots as a pre-emit stage |
| More FL providers (Morpho) | `flashloan_provider_registry()` on ChainAdapter (T0-8) + `FLASH_LOAN_PROVIDERS` catalog |
| More Base DEXs (UniV4/Pancake) | `dex_registry()` on ChainAdapter (T0-8) + venue list isolation |
| Arbitrum ChainAdapter | `ChainAdapter` protocol (T0-8) — add one adapter + config |

---

## Dependency graph (safest implementation order)

```
                 ┌─────────────────────────────┐
                 │ T0-5 RPC unification         │  (deterministic resolve_rpc_url)
                 └───────────────┬─────────────┘
                                 │
        ┌────────────────────────┼───────────────────────────┐
        ▼                        ▼                             ▼
┌───────────────┐      ┌──────────────────┐          ┌──────────────────┐
│ T0-3 mode/    │      │ T0-1 canonical   │          │ T0-6 TVL provider │
│ OBSERVE fix   │      │ scanner + live   │◄─────────│ + fail-closed g8  │
└──────┬────────┘      │ quote wiring     │          └────────┬─────────┘
       │               └────────┬─────────┘                   │
       │                        │                             │
       │                        ▼                             │
       │             ┌──────────────────────┐                 │
       │             │ T0-2 quarantine thin │                 │
       │             │ + repo write-gate    │                 │
       │             │ + paper provenance   │                 │
       │             │   filter             │                 │
       │             └──────────┬───────────┘                 │
       │                        │                             │
       ▼                        ▼                             ▼
┌───────────────┐      ┌──────────────────┐          ┌──────────────────┐
│ T0-4 economics│      │ T0-7 certification│         │ T0-8 ChainAdapter │
│ unification   │      │ provenance filter │         │ (Base only)       │
└───────────────┘      └──────────────────┘          └──────────────────┘
                                 │
                                 ▼
                       ┌──────────────────┐
                       │ T0-9 DB migration │  (additive; optional backfill last)
                       │ + T0-10 tests     │
                       │ + T0-11 deploy    │
                       └──────────────────┘
```
**Order rationale:** RPC first (everything real needs a real endpoint) → mode + scanner authority + TVL in parallel (independent) → quarantine (needs real canonical stream) → economics + certification + adapter → migration/tests/deploy last.

---

## A. T0 MUST FIX (blocking; correctness/trust)
- **T0-1** deterministic canonical live-wiring + noop guard.
- **T0-2** thin quarantine + canonical write-gate + paper provenance filter.
- **T0-3** OBSERVE silent fallback → explicit readiness/infra error + seed assertion.
- **T0-5** one canonical RPC resolver + precedence + env_sync dual-write.
- **T0-6** remove TVL sentinel + `TVLProvider` + fail-closed Gate 8.
- **T0-7** certification provenance filtering (REAL-only executable-rate).

## B. T0 SHOULD FIX (high value; not strictly gating live-correctness)
- **T0-4** economics unification via shared canonical kernel/view.
- **T0-8** minimal `ChainAdapter` (Base) — do now to avoid re-plumbing before T2/T4.
- **T0-9** optional idempotent historical provenance backfill.

## C. T0 CAN WAIT (defer to T1+)
- Real on-chain TVL (T0 may start with cached DexScreener/subgraph).
- Frontend dashboards for provenance/readiness (metrics exist regardless).
- Bundle-hash version bump *only if* provenance must be integrity-bound (else store as non-hashed metadata in T0).
- Any performance/cache/WSS work (T2).

## D. Risks / unknowns requiring VPS verification `[VPS?]`
- Canonical DB identity (`factory-mongo/arbicore_x`) and that `execution_mode_state` seeded there.
- Which RPC env var the deployed container actually has set (ARBICORE_* vs legacy).
- Whether the running container == `main@43230f6` (file hashes).
- Live counts of SIMULATED rows already in canonical collections (scope of optional backfill).
- Presence (not value) of `SIGNING_ACTIVE_KEY_VERSION` for the production signing decision.

## E. Acceptance criteria — T0 complete when:
1. Canonical `FlashLoanArbitrageScanner` is the **sole** writer of production/executable opportunities; thin activator cannot write to the canonical repo (verified by test + live check). 
2. `noop_quote_provider` can never be the silent production quote path; a non-OBSERVE enabled scanner on noop surfaces a `readiness_error`.
3. Every canonical opportunity has provenance ∈ {REAL, VERIFIED_REAL}; SIMULATED/SYNTHETIC/TEST are isolated to the research collection and never counted as executable.
4. `_resolve_mode` never silently returns OBSERVE for a missing/unresolvable mode; missing/seed/DB failures are explicit, operator-visible outcomes; `ensure_defaults` verified to have seeded the canonical DB.
5. Exactly one economics kernel produces the numbers used by Gate 7; the **$25 floor is unchanged**; a USD view (if any) agrees with the canonical kernel.
6. One canonical RPC resolver with documented precedence; UI-configured RPC and scanner-read RPC provably agree; no fabricated defaults.
7. TVL sentinel removed; Gate 8 evaluates **real or fail-closed** liquidity; no route passes on fabricated depth.
8. Certification executable-rate/profitability metrics are computed over REAL evidence only; synthetic reported separately; signing NOT disabled; historical (signed and unsigned) evidence preserved and still verifiable.
9. Minimal `BaseChainAdapter` in place with parity to prior behavior; Base assumptions isolated behind it.
10. All T0-10 test categories pass; existing FL/scanner/mode/paper/cert suites remain green; no historical evidence deleted; deployment + rollback rehearsed on a backup.

**STOP — awaiting approval. No code changes made in this run.** Plan saved to `docs/FLASH_LOAN_T0_IMPLEMENTATION_PLAN.md`.
