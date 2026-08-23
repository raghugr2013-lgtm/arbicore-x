# ArbiCore X — Flash-Loan-First Profit Engine · Phase-0 Architecture & Git Reconciliation Audit

**Mode:** READ-ONLY. No production code modified. No merge / cherry-pick / rebase / reset / clean / delete performed.
**Environment caveat:** This audit was performed against the Git working tree in the Emergent workspace only. The audit environment has **no access** to the live VPS `arbicore-x-backend` container or the `factory-mongo` database. Every claim about the *deployed* system is tagged **[UNVERIFIABLE-HERE]** and must be confirmed on the VPS.
**Evidence tags:** `[FACT]` = read directly from source; `[INFERENCE]` = reasoned from source + prior audit notes; `[UNVERIFIABLE-HERE]` = requires VPS/DB access; `[RECOMMENDATION]` = proposed, not applied.

---

## 0. Git state snapshot

- `main` HEAD = `43230f6` ("Clarify limited live readiness authorization"). `[FACT]`
- Remote branches: `main`, `archive-v1`, `feature/ui-v2-slices-0-2`, `hotfix/auth-routing`, `scanner-bootstrap-validator-fix`. `[FACT]`
- `origin` remote URL **embeds a GitHub PAT** (`ghu_…`) in cleartext. `[FACT]` → `[RECOMMENDATION]` **Rotate that token immediately**; store credentials in a credential helper, not the remote URL. (Value intentionally NOT reproduced here.)
- Working tree: 44 uncommitted modifications, each a single-line change swapping the preview host `https://defi-exec-audit.preview.emergentagent.com` → `https://flash-execution.preview.emergentagent.com` in test files, 2 Tampermonkey userscripts and 2 docs. **No logic changes.** `[FACT]` Treated as intentional in-progress work; preserved untouched.

---

## A. Current architecture map

Backend root: `/app/app/backend` (symlinked as `/app/backend`). `server.py` = **8154 lines** monolith; `api.py` = 550 lines. Core package: `arbicore/`. `[FACT]`

Principal subsystems (`arbicore/…`):

| Area | Path | Role |
|------|------|------|
| Scanners (canonical) | `scanners/flash_loan_arbitrage/` | Real FL scanner: scanner, route_search, sources, live_quote_provider, verifier, economics, filter (gates 7/8/9) |
| Other scanner families | `scanners/{cex,dex,cross_chain,funding,launch,live}_arbitrage/`, `scanners/discovery/`, `scanners/wave1b/` | Additional opportunity families |
| Thin discovery (legacy) | `execution/discovery.py` | `ContinuousDiscovery` = `thin_activator@1` |
| Runtime composition | `runtime/composition.py` (1273 ln) | Scanner/provider factories, canonical FL activation |
| Economics kernel | `economics/` | `opportunity_engine.py`, `net_profit.py`, `expected_value.py`, `size_optimizer.py`, `quote_provider.py` + `scanners/economics.py` (`aggregate_economics`) |
| Execution/pipeline | `execution/` | `pipeline.py`, `mode.py`, `gas.py`, `mev.py`, `slippage.py`, `simulation.py`, `atomic_executor_sim.py`, `auto_executor.py`, `live_signer.py`, `broadcast.py`, `capital_policy.py`, `kill_switch.py` |
| Paper | `paper/` | `runner.py` (PaperValidationRunner), `paper_engine.py`, `evidence.py`, `repo.py` |
| Shadow | `shadow/` | `observer.py`, `mapper.py` |
| Certification | `certification/` | `engine.py`, `runner.py`, `models.py`, `repo.py`, `thresholds.py` |
| Evidence | `evidence/` | `bundle.py`, `signer.py` (Ed25519) |
| Providers | `providers/` | Protocols (`base.py`), `registry.py`, `rpc.py`, `dex.py`, `cex.py`, `bootstrap.py` |
| Config | `config/` | `persistent.py`, `env_sync.py`, `scanner_config.py`, `signing_config.py`, `runtime.py` |
| Data/Mongo | `data/`, `data/mongo/`, `data/mid/` | Repos incl. `opportunity_repo_mongo.py`, `evidence_bundles_repo.py`, provenance layer |
| Safety/control | `safety/`, `control/` | approval, capital, kill_switch, readiness |

Runtime engines are **three distinct loops** (critical): `[FACT]`
1. `_CONTINUOUS_SCANNER` (`server.py:332`) — autostarted via `ARBICORE_SCANNER_AUTOSTART` (default on) at `server.py:6274`.
2. `_CONTINUOUS_DISCOVERY` (`server.py:235`) — the **thin_activator**; constructed at import, **only started via API** (`/discovery/start`, `server.py:4130`), not at boot.
3. `FlashLoanArbitrageScanner` (canonical) — activated via `activate_canonical_flash_loan_scanner()` at `server.py:6852` and the gated `_arbicore_runtime_autostart` (`ARBICORE_RUNTIME_AUTOSTART`, `server.py:6926`).

---

## B. Existing Flash-Loan components

`[FACT]` All present under `scanners/flash_loan_arbitrage/`:
- **`scanner.py`** — orchestrator (discover → queue → claim → verify → emit). Sole EmissionBus emit site for `FLASH_LOAN_ARBITRAGE`. Boot posture DORMANT; composition cache flips detection on.
- **`route_search.py`** — `RouteSearchEngine`: depth-bounded DFS closed-cycle enumeration over a token→pool graph. Caps: max_hops, wall_clock, candidate_cap, min_pool_tvl. Pure computation.
- **`live_quote_provider.py`** — `make_live_quote_provider(quoter_registry)`: quotes every hop live via `QuoterRegistry.quote_route`; returns `None` (→ `denied:venue_unreadable`) when a route can't be priced. Computes `gross_profit_pct` from real wei ratio. **Honest by design.**
- **`verifier.py`** — `FlashLoanOpportunityVerifier`: quote → economics → Gate 7/8/9 → LegEvidence (BORROW+hops+REPAY) → provenance derivation → CanonicalOpportunity.
- **`economics.py`** — `FlashLoanEconomicsAssessor` + inline `FLASH_LOAN_PROVIDERS` catalog (aave_v3 5bps, balancer_v2 0bps, uniswap_v3 tiered). Wraps `aggregate_economics`.
- **`filter.py`** — Gate 7 atomic-profit (floor **$25** default), Gate 8 liquidity depth, Gate 9 MEV.
- **`sources.py`** — `build_all_flash_loan_sources` (aave/balancer/uniswap real sources).
- Pool universe: `discovery/base_venues.py` — 33 Base venues across Uniswap V3 (fee tiers), Aerodrome SlipStream, Aerodrome classic. **TVL hardcoded to `5_000_000.0` sentinel** (route-search TVL gate effectively a no-op; real depth handled downstream by slippage/size-optimizer). `[FACT]`

---

## C. Opportunity families — implementation status

| Family | Dir present | Status | Notes |
|--------|-------------|--------|-------|
| A. Cross-DEX arbitrage | `scanners/dex_arbitrage/` | **IMPLEMENTED** | economics/quoter/verifier/quote_cache present |
| B. Triangular / multi-hop | `scanners/flash_loan_arbitrage/route_search.py` | **IMPLEMENTED** | DFS closed cycles (multi-hop) |
| C. Multi-DEX multi-hop | route_search over multi-DEX Base graph | **IMPLEMENTED** | graph mixes Uni V3 + Aerodrome |
| D. Stablecoin dislocation | base_venues stable surfaces (USDC/DAI/USDT/USDbC) | **PARTIALLY IMPLEMENTED** | pairs exist; no dedicated dislocation scorer |
| E. Wrapped/native arb | WETH/cbETH/wstETH/rETH/weETH pairs | **PARTIALLY IMPLEMENTED** | present as routes, no dedicated family module |
| F. Protocol-specific FL | `scanners/flash_loan_arbitrage/` (aave/balancer/uni) | **IMPLEMENTED** (detection) | execution gated |
| G. Liquidation | — | **MISSING** | no liquidation scanner |
| H. Liquidity imbalance / dislocation | — | **SCAFFOLD** | implicit via route search only |
| I. Cross-chain | `scanners/cross_chain_arbitrage/` | **PARTIALLY IMPLEMENTED** | bridge_intelligence, chain_liveness, economics, transfer_provider present; atomicity correctly NOT modeled as single-tx FL |
| (extra) CEX arb | `scanners/cex_arbitrage/` | IMPLEMENTED | out of FL scope |
| (extra) Funding arb | `scanners/funding_arbitrage/` | IMPLEMENTED | out of FL scope |
| (extra) Launch arb | `scanners/launch_arbitrage/` | IMPLEMENTED | Solana-centric, out of FL scope |

`[INFERENCE]` for D/E/H (module exists but no family-specific economics scorer).

---

## D. Chains & actual readiness

`[FACT]` from `economics.py` provider catalog + `provenance.py` chain sources + `env_sync.py`:
- **Base** — proving ground. Canonical pool universe (`base_venues.py`), live quoter path, executor address configured (persistent). **The only chain with real end-to-end wiring.**
- **Ethereum / Arbitrum / Optimism / Polygon** — declared in provider `supports_chains` and provenance registry (`*_rpc_real`), but **no pool universe, no executor address, no per-chain adapter**. NOT ready. `[FACT]`
- There is **no `ChainAdapter` class** yet. `providers/base.py` defines per-category Protocols (RPCProvider, DEXProvider, FlashLoanProvider, GasProvider, etc.) but **no unified `ChainAdapter` aggregating chainId/native/RPC/registries/health/capability**. Adding chains today = code, not config. `[FACT]`

---

## E. DEX integrations

`[FACT]` Base: Uniswap V3 (SwapRouter02 allowlisted, QuoterV2 real), Aerodrome + Aerodrome SlipStream (router allowlisted; MixedRouteQuoter real). Provenance registry also classifies PancakeSwap V3 (BNB/Arb/Base), Raydium (Solana) as REAL quoters for other families. Heritage sources `balancer`, `oneinch` are explicitly classified **CONTAMINATED**; `sushiswap/quickswap/curve/pancakeswap` (hosted subgraphs) classified **DEAD**. No `DEXAdapter` unification class — only the `DEXProvider` Protocol + per-scanner quoters.

---

## F. Flash-loan providers

`[FACT]` `FLASH_LOAN_PROVIDERS` (economics.py): `aave_v3` (5 bps), `balancer_v2` (0 bps), `uniswap_v3` (pool-tier). All list Ethereum/Arbitrum/Base/Optimism/Polygon. `providers/base.py:FlashLoanProvider` Protocol exists (get_available_liquidity/get_fee_bps/simulate_flashloan/health_probe) but is **read-only shape / Phase-7 stub** — provider "enabled" is a config toggle, **not a real health probe**. `[FACT]` Matches §21 concern.

---

## G. Discovery paths (COMPETING AUTHORITIES — §5)

**Two writers into the canonical opportunity repo:** `[FACT]`

1. **Canonical:** `FlashLoanArbitrageScanner` → verifier → `EmissionBus.emit` (only on `CONFIRMED_*`). Emits genuinely-priced, gate-passed opportunities only.
2. **Thin:** `ContinuousDiscovery._evaluate_candidate` (`execution/discovery.py:265-311`) builds a `CanonicalOpportunity` with `source_data_quality=DataProvenance.SIMULATED`, `metadata={"engine":"thin_activator", ...}`, `status=VALIDATED|CANDIDATE`, and **upserts it into `_CANONICAL_OPP_REPO`** (looked up lazily via `import server; server._CANONICAL_OPP_REPO`).

**→ CONFIRMED CONTAMINATION VECTOR.** The thin activator injects `SIMULATED`-provenance rows into the same canonical repo the operator UI, PaperValidationRunner, and Shadow Certification read from. Its universe (`DEFAULT_UNIVERSE_BASE`) is a single hardcoded WETH→USDC→WETH template with a fixed `min_amount_out_wei` — i.e. a synthetic candidate. `[FACT]`

Mitigating facts: it is **not auto-started at boot** (manual API trigger only) and its rows are honestly tagged `SIMULATED`. But nothing structurally prevents contamination once started, and downstream counters do not all filter on provenance (see K/§14). `[FACT]`

---

## H. Quote paths

`[FACT]` Canonical live quoting = `QuoterRegistry.quote_route` (real `eth_call` per hop) surfaced through `make_live_quote_provider`. `noop_quote_provider` is the cold-start default → everything denied `venue_unreadable` until a live provider is wired. Canonical FL scanner ships with `quote_provider=None`; live provider installed only by `activate_canonical_flash_loan_scanner(quoter_registry)`. The thin activator instead calls `dry_run.evaluate_live(plan)` with a deterministic fallback. Two different quoting entrypoints exist but both ultimately target the same registry — acceptable, but not unified behind one interface.

---

## I. Profitability paths

`[FACT]` Canonical kernel = `scanners/economics.py::aggregate_economics` (+ `per_chain_gas_estimate_usd`), consumed by `FlashLoanEconomicsAssessor`. Separately, `economics/opportunity_engine.py`, `economics/net_profit.py`, `economics/expected_value.py` exist and are used by the OpportunityEngine/thin path. **There are at least two economics surfaces** (`scanners/economics.aggregate_economics` vs `economics/net_profit`+`opportunity_engine`). This is the "different profitability calculations in different scanners" risk called out in §19. `[INFERENCE]` A single canonical economic kernel is **not yet enforced**.

Modeled today (canonical FL): borrow amount, flash-loan fee (bps→USD), per-hop swap fees, gas (per-chain + tx_gas_units scaling), slippage (per leg), MEV penalty, atomic_profit_usd, ROI confidence band. **Not explicitly surfaced as first-class outputs:** worst_case_net_profit_usd, execution_probability, priority-fee vs base-fee split, bridge/settlement cost, capital efficiency. `[FACT]`

---

## J. Simulation paths

`[FACT]` `execution/atomic_executor_sim.py`, `execution/settlement_simulator.py`, `execution/simulation.py`, plus the `run-atomic-sim` endpoint (with optional Anvil fork / archive-RPC block-pinned replay per commit `313e0c2`). Prior audit note (commit `313e0c2`): **the atomic sim has never PASSed in Emergent** because the fixture round-trip (WETH→USDC→WETH through the same 0.05% pool) loses fees and cannot repay a 0-fee Balancer loan — deterministic economics, not a parity bug. `[INFERENCE from commit message + code]`

---

## K. Paper / Shadow / Certification paths

`[FACT]`
- **PaperValidationRunner** (`paper/runner.py`): drains canonical opp repo → `pipeline.evaluate(opp_as_dict)` → evidence. Idempotent via `_processed_ids` + `get_by_opportunity_id`. Stale-reprocess controlled by `ARBICORE_PAPER_RUNNER_REPROCESS_STALE_MIN` (minutes→seconds; `0` = strict one-evidence-per-opp). Started at boot only when `ARBICORE_PAPER_VALIDATION_ENABLED=true`.
- **Shadow** (`shadow/observer.py`, `mapper.py`) + **Certification** (`certification/engine.py`): engine computes **delta cycles** from runner counters + evidence deltas; trusts evidence delta as the immutable source for `executable`; clamps `processed_delta ≥ evidence_delta`. Grades `exec_rate = executable/processed` against pass/warn thresholds.
- **Gap:** `certification/engine.py` contains **no provenance/synthetic filtering** (grep: no `synthetic`/`SIMULATED`/`provenance`). So paper-evaluated `SIMULATED` thin rows that produce evidence can be counted toward certification deltas. `[FACT]` → matches §14 requirement to exclude synthetic from executable counts.
- **OBSERVE-as-hidden-failure:** `pipeline._resolve_mode` returns `"OBSERVE"` as its **fallback** when no `execution_mode_state` row matches (lines 572-573) and on read exception (572). Case-normalization (raw/lower/upper) was added (v2.11.10) to stop `FLASH_LOAN_ARBITRAGE` missing `flash_loan_arbitrage`. In OBSERVE, pipeline records `"mode is OBSERVE — no analysis"` and stops (lines 251-261). This exactly reproduces the `arbicore_paper_evidence` records `mode=OBSERVE / outcome=REJECTED / "mode is OBSERVE — no analysis"`. `[FACT]`

---

## L. Execution / governance path

`[FACT]` Mode ladder (`execution/mode.py`): **OBSERVE → PAPER → SHADOW → LIMITED_LIVE → FULL_LIVE** (note: no `RECOMMENDATION` mode — §11/§24's "RECOMMENDATION" is not a distinct code mode; treat as doc drift). Forward one step only; rollback any steps; broadcast allowed only in LIMITED_LIVE/FULL_LIVE (`is_broadcast_allowed`). `default_mode_map()` = flash_loan_arbitrage **SHADOW**, all other trading strategies **PAPER**. `ensure_defaults()` is **idempotent** and **is wired** into a startup handler `_seed_execution_substrate` (`server.py:8068-8082`). Governance components present: `safety/approval.py`, `safety/capital.py`, `safety/kill_switch.py`, `execution/capital_policy.py`, `execution/auto_executor.py`. Live execution requires `ARBICORE_RUNTIME_AUTOSTART` + explicit mode promotion + AutoExecutor — never auto-enabled by code path. `[FACT]`

---

## M. Duplicate / legacy paths

`[FACT]`
1. **Discovery:** canonical `FlashLoanArbitrageScanner` **vs** thin `ContinuousDiscovery` (both write canonical repo). ← primary defect (§5).
2. **Scanner dirs:** `arbicore/scanner/` (singular, `base.py` only) vs `arbicore/scanners/` (plural, all real families). Singular is near-empty legacy.
3. **Economics:** `scanners/economics.aggregate_economics` vs `economics/net_profit`+`opportunity_engine` — two profitability surfaces (§19).
4. **RPC config namespaces:** legacy `ETH_RPC_URL / BASE_RPC_URL / ARBITRUM_RPC_URL / OPTIMISM_RPC_URL / POLYGON_RPC_URL` (referenced by `provenance.py` chain-liveness sources) **vs** new `ARBICORE_RPC_URL / ARBICORE_RPC_URL_BASE / ARBICORE_EXECUTOR_ADDRESS_BASE` written by `config/env_sync.py` from the persistent `NetworkConfigRepo`. Two namespaces, **precedence not centrally defined** (§17). `env_sync` writes both `ARBICORE_RPC_URL` and `ARBICORE_RPC_URL_BASE` but not the legacy `BASE_RPC_URL`, so a component still reading `BASE_RPC_URL` would diverge from the UI. `[FACT]`
5. **Quote entrypoints:** `make_live_quote_provider` vs `dry_run.evaluate_live` (both hit QuoterRegistry). Minor.

---

## N. Root causes already identified (from prior audit / DB findings) — CONFIRMED against code

| Prior finding | Code confirmation | Verdict |
|---|---|---|
| `rows_emitted=0` while `candidates_claimed>800`, `verifier_denied>800`, buckets `gate_7_atomic_profit` + `denied_venue_unreadable` | scanner.py stats + verifier.py flow + filter.py Gate7 floor $25 | **Honest refusal, not a gate bug** (see O) |
| `arbicore_paper_evidence` `mode=OBSERVE / "no analysis"` | pipeline.py 251-261 + `_resolve_mode` fallback OBSERVE 572-573 | **CONFIRMED** — OBSERVE is a hidden failure fallback |
| `evidence_bundles` `verification_status=unsigned`, reason `SIGNING_ACTIVE_KEY_VERSION unset` | `signing_config.py:unsigned_reason()` + `signer.py` | **CONFIRMED — BY DESIGN** (Option-b bootstrap: run unsigned, never auto-gen keys). Not a bug; a config gap. |
| execution_mode_state empty until manual `ensure_defaults()` | `ensure_defaults` exists + wired at `server.py:8075` | **CONFIRMED wired in Git**; if empty in prod → deployed image predated it OR ran against wrong DB `[UNVERIFIABLE-HERE]` |
| Backend uses `factory-mongo`, not `arbicore-x-mongo` | not determinable from tree (env-driven `MONGO_URL`) | `[UNVERIFIABLE-HERE]` |

---

## O. Additional root causes discovered

1. **`denied_venue_unreadable` has two causes**: (a) canonical scanner still on `noop_quote_provider` because `activate_canonical_flash_loan_scanner()` was never invoked (gated by `ARBICORE_RUNTIME_AUTOSTART`), OR (b) live quoter cannot reach Base RPC / cannot price the route. Both are honest, but (a) is a **wiring/bootstrap** issue, not a market issue. `[INFERENCE]`
2. **`gate_7_atomic_profit` mass rejection is structurally correct**: the Base pool universe is dominated by **same-token round-trips through similar fee tiers**; after flash fee + 2× swap fees + gas + slippage, atomic profit is negative → correctly denied at the $25 floor. The engine is refusing to fabricate profit. The apparent "0 executable" is the honest truth of the current universe + quote availability, **not** a gate that needs lowering. `[INFERENCE, corroborated by commit 313e0c2]`
3. **The system "looks productive" only because the thin activator writes SIMULATED rows** while the honest scanner emits 0. This is the core deception risk: operators may mistake `SIMULATED` thin rows for executable opportunities. `[INFERENCE]`
4. **TVL is a hardcoded sentinel** (`5_000_000.0`) in `base_venues.py`, so Gate 8 (liquidity depth) and route-search TVL prune are effectively no-ops on Base; real depth risk is deferred to slippage/size-optimizer. Liquidity health is therefore **not real** at the route-search layer. `[FACT]`
5. **No `ChainAdapter`** → multi-chain is not yet config-driven (§3 target unmet). `[FACT]`
6. **Certification lacks provenance attribution** → can count synthetic-derived evidence (§14). `[FACT]`
7. **RPC namespace split** can produce "UI says configured, scanner reads a different var" (§17). `[FACT]`

---

## P. Proposed target architecture `[RECOMMENDATION]`

1. **Single canonical discovery authority.** Production canonical opportunity stream = `FlashLoanArbitrageScanner` only. Quarantine the thin activator: (a) forbid it writing to `_CANONICAL_OPP_REPO`; route its output to a clearly separate `arbicore_discovery_candidates` collection tagged `SYNTHETIC/TEST`; (b) keep it importable for tests behind an explicit flag. Preserve rollback.
2. **Provenance everywhere, enforced at boundaries.** Extend the existing 5-tier provenance (`VERIFIED_REAL/REAL/SIMULATED/CONTAMINATED/DEAD`) to a hard write-gate on the canonical repo: only verifier-emitted `REAL` opportunities may enter the production stream; PaperRunner and Certification filter on provenance.
3. **One economic kernel.** Converge `scanners/economics.aggregate_economics` and `economics/net_profit`/`opportunity_engine` into a single kernel emitting the full §19 vector (gross, total_cost, expected_net, worst_case_net, margin_bps, confidence, execution_probability). All scanners consume it.
4. **`ChainAdapter` abstraction** (§3) aggregating chainId/native/RPC/finality/gas/token registry/DEX registry/FL-provider registry/quoter/simulation/executor/health/capability. Chains activate only after a real health/capability gate (§10).
5. **Real health probes** for DEX + FL providers (replace config-toggle "enabled" with `health_probe()` results feeding `ProviderHealth.score()` already defined in `providers/base.py`).
6. **One canonical RPC config source** = persistent `NetworkConfigRepo` via `env_sync`, with `env_sync` also writing the legacy `<CHAIN>_RPC_URL` aliases (or all readers migrated to `ARBICORE_RPC_URL_*`), and explicit documented precedence.
7. **Bootstrap correctness**: keep `ensure_defaults()` at startup (already wired); add a startup assertion/health row proving the seed ran against the canonical DB. Never rely on manual seeding.
8. **Certification integrity**: count entered / analyzed / per-gate / executable / real vs synthetic separately; exclude synthetic from executable metrics.
9. **Signing**: production posture = configure `SIGNING_ACTIVE_KEY_VERSION` + key material (never disable signing, never auto-gen in prod). Document key-management runbook.
10. **Observability**: one operator dashboard keyed on *genuinely executable opportunities + expected/realized net profit*, not raw candidate counts.

---

## Q. Exact implementation sequence (maps to §29) `[RECOMMENDATION]`

- **Phase 0** — this document. ✅
- **Phase 1** — Canonical FL architecture: guarantee canonical scanner is authoritative + live-quoter wired deterministically at boot (not only behind autostart env).
- **Phase 2** — Isolate thin activator from canonical repo (quarantine collection + provenance write-gate); keep test path.
- **Phase 3** — Canonical economics kernel (single source, full §19 vector).
- **Phase 4** — Base end-to-end real opportunity validation (real quotes, real TVL, honest atomic sim).
- **Phase 5** — Paper + Shadow certification integrity (provenance-filtered counts; OBSERVE-fallback → explicit error state, not silent).
- **Phase 6** — `ChainAdapter` framework + health/capability gating.
- **Phases 7–10** — Arbitrum → Ethereum → Optimism → Polygon (config + adapter only).
- **Phase 11** — Additional DEX/provider expansion (real health).
- **Phase 12** — Additional families (liquidation G, dislocation D/H).
- **Phase 13** — Controlled live execution (operator-gated).

---

## R. Risks

- **Deployed ≠ Git** `[UNVERIFIABLE-HERE]`: prod may run an image predating `ensure_defaults` wiring or against a different Mongo (`factory-mongo` vs `arbicore-x-mongo`). Must reconcile on VPS before any Phase-1 change.
- **Quarantining thin activator** could reduce visible opportunity counts to ~0 on Base until real dislocations appear — this is *correct* but may look like a regression; communicate clearly.
- **TVL sentinel removal** will start denying thin-liquidity routes (Gate 8 becomes active) — expected, but changes emission counts.
- **Economics convergence** risks behavioral drift if the two surfaces disagree; needs golden-fixture regression.
- **Secret hygiene**: PAT in remote URL is a live exposure risk.
- **Big monolith** (`server.py` 8154 ln) raises merge-conflict risk for any cross-cutting change.

---

## S. Tests required (§28) `[RECOMMENDATION]`

Deterministic fixtures for: stale quote, missing RPC, RPC failure, DEX unavailable, FL provider unavailable, insufficient liquidity, gas spike, negative profit, repayment failure, slippage failure, MEV risk, simulation failure, duplicate opportunity, **synthetic-contamination (thin row must NOT reach canonical stream)**, wrong strategy case (`FLASH_LOAN_ARBITRAGE` resolves), missing execution mode (must NOT silently OBSERVE), stale reprocessing idempotency, unsigned evidence, DB failure. Plus unit/integration/provider/chain-adapter/quote/route/economic/paper/shadow/certification suites. Existing suites live in `app/backend/tests/` (+ `_pending_scanner_activation/`).

---

## T. Definition of Done

Adopt §32 verbatim as the acceptance gate. Additionally, this Phase-0 is "done" when the operator has: (a) confirmed deployed-vs-Git on the VPS, (b) approved the canonical baseline (below), (c) approved the Phase-1 plan.

---

# GIT / BRANCH RECONCILIATION

## Reconciliation table

| Change area | Branch | Tip / range | In main? | In deployed container? | Keep? | Conflict? |
|---|---|---|---|---|---|---|
| v1.0.0/v1.0.1 canonical (old v1) | `archive-v1` | `23cbfe8`,`20bad02`,`f372911` (3 commits ahead; ~131k del vs main) | No (diverged) | `[UNVERIFIABLE-HERE]` | Preserve as archive | N/A (do not merge) |
| UI v2 slices 0–2 (auto-commits) | `feature/ui-v2-slices-0-2` | 28 commits ahead (mostly `auto-commit …`); ~230k del vs main | No (old fork base) | `[UNVERIFIABLE-HERE]` | Preserve; inspect for any unique asset | Would massively conflict |
| Auth routing hotfix + doc trims | `hotfix/auth-routing` | 0 commits ahead of main | **Yes** (contained) | `[UNVERIFIABLE-HERE]` | Already in main | None |
| Scanner bootstrap + validator contract | `scanner-bootstrap-validator-fix` | tip `515b49f` (0 ahead; main +`66b4430`,`43230f6`) | **Yes** (superseded by follow-ups) | `[UNVERIFIABLE-HERE]` | Already in main | None |
| Preview-URL swap (test/userscripts/docs) | working tree (uncommitted) | 44 one-line edits | No (uncommitted) | n/a | **Keep** (intentional) | None |

## B — Commits/files by topic (where the FL work lives)
`[FACT]` All flash-loan / route-search / quote / Aave-Balancer-Uni / Base-activation / execution-mode / pipeline-mode / paper / shadow-cert / evidence / provenance / thin_activator / discovery / RPC-config / simulation / atomic-gate work is **on `main`** (the `Stage 1/2` + `scanner bootstrap` + `atomic-sim diagnostics` commit chain `313e0c2 … 43230f6`). The two "flash-loan" feature branches (`scanner-bootstrap-validator-fix`, and auth in `hotfix/auth-routing`) are **already contained in main**. The UI FL surface lives in `app/frontend/src/v2/` on main.

## C — Recent VPS-diagnosis fixes: in Git? 
- `_resolve_mode` case-normalization, `ensure_defaults` wiring, `env_sync`, canonical FL activation, atomic-sim replay: **present in Git main** `[FACT]`.
- Whether the *running container* actually contains them, and whether the seed ran against `factory-mongo/arbicore_x`: **[UNVERIFIABLE-HERE]** — requires VPS file hashes + DB read.

## D — Duplicate/competing paths → see §M.
## E — Likely merge conflicts: only if `archive-v1` or `feature/ui-v2-slices-0-2` were ever merged (they must NOT be — they are older/divergent, huge deletions). `main` needs no merge from any branch. Primary future conflict surface = `server.py`, `execution/pipeline.py`, `execution/mode.py`, `paper/runner.py`, `certification/engine.py`, `config/env_sync.py`, `config/persistent.py`, `runtime/composition.py`, `scanners/flash_loan_arbitrage/*`.

## F — Recommended canonical baseline
**`main` @ `43230f6` + the 44 uncommitted preview-URL edits (commit them).** No branch merge required — every feature branch is either already-in-main or superseded/archive. `[RECOMMENDATION]` Do NOT assume the deployed container equals this baseline until VPS reconciliation is done.

## G — Branch classification
- **SAFE TO KEEP (canonical):** `main`.
- **SAFE TO CHERRY-PICK:** none needed (nothing unique & valuable outside main identified).
- **NEEDS MANUAL RECONCILIATION:** deployed-container ↔ `main` file/DB parity (VPS-side) `[UNVERIFIABLE-HERE]`.
- **ALREADY IN MAIN:** `hotfix/auth-routing`, `scanner-bootstrap-validator-fix`.
- **SUPERSEDED / EXPERIMENTAL (preserve, DO NOT MERGE):** `feature/ui-v2-slices-0-2`.
- **ARCHIVE / DO NOT MERGE:** `archive-v1`.

---

# TOP-PRIORITY FINDINGS (executive)

1. **Thin activator (`thin_activator@1`) writes `SIMULATED` rows into the canonical opportunity repo** → competing authority + contamination. Isolate (Phase 2). `[FACT]`
2. **`rows_emitted=0` is honest**, driven by (a) live-quoter not wired unless `ARBICORE_RUNTIME_AUTOSTART` set (→ `venue_unreadable`) and (b) structurally-unprofitable same-pool round-trips (→ `gate_7`). **Do not lower gates.** Fix bootstrap wiring + real universe. `[INFERENCE]`
3. **OBSERVE is a silent failure fallback** in `_resolve_mode`; must become an explicit error/health signal. `[FACT]`
4. **Unsigned evidence is by-design** (no key configured), not a bug — configure signing for prod; never disable. `[FACT]`
5. **No `ChainAdapter`; only Base is real** — multi-chain is code-work today. `[FACT]`
6. **Two economics surfaces + two RPC namespaces + hardcoded TVL** — converge/canonicalize. `[FACT]`
7. **Certification does not filter provenance** — can count synthetic-derived evidence. `[FACT]`
8. **Canonical baseline = `main@43230f6` + uncommitted URL edits; no merges needed.** VPS parity unverified from here. `[FACT]/[UNVERIFIABLE-HERE]`

**STOP — awaiting operator approval before any implementation (Phase 1+).**
