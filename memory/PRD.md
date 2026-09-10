# ArbiCore X v2 — Engineering PRD / Handoff Memory

## Project
Multi-network arbitrage backend (FastAPI/Python). SHADOW / detection-only /
fail-closed. GitHub is source of truth; VPS is the runtime-proof environment.
Working branch: `fix/p0-3-runtime-v3-liquidity-filter`.

## P0 status
- P0-1 Dynamic Capital: COMPLETE
- P0-2 Base RPC wiring: COMPLETE
- P0-3 Base Flash-Loan Discovery: IN PROGRESS — engineering/tests substantially
  complete; **NOT certified** (requires real VPS/Base runtime proof).

## Core, static invariants
- Canonical pool registry (`base_pool_registry`) is pure/deterministic — never
  mutated/deleted by runtime filtering (30 Base pools: 19 UniV3 + 11 Aerodrome).
- Runtime UniV3 `liquidity()` eligibility may EXCLUDE currently-unusable pools;
  zero/missing/malformed/unreadable/timed-out liquidity FAILS CLOSED.
- Aerodrome/Slipstream never subjected to the UniV3 `liquidity()` rule.
- Mode ladder OBSERVE→PAPER→SHADOW→LIMITED_LIVE→FULL_LIVE; broadcast only in
  LIMITED_LIVE/FULL_LIVE. No signing/broadcast/withdrawal enabled.
- Disposable validator = `scripts/run_vps_validator_audit.sh` (curated modules)
  against ephemeral Mongo; never production Mongo; no `--remove-orphans`.

## Implemented this workspace (dates)
- 2026-06: Section 6 — regression coverage for the Base UniV3 runtime liquidity
  eligibility filter. New `tests/test_z9_base_v3_liquidity_eligibility.py`; wired
  into validator module list. Commit `3a7b918`.
- 2026-06: Phase 4 — startup-budget remediation of
  `composition._refresh_base_v3_eligibility`: bounded concurrency
  (`asyncio.Semaphore`, default 8) + fail-closed pre-seed baseline + per-call
  timeout (default 2.0s ⇒ stalled read EXCLUDED) + caller fail-closed fallback
  (`_failclosed_exclude_all_base_univ3`). Independent adversarial module
  `tests/t1_verify/test_t1_z9_independent_verification.py`. Certification doc
  `docs/P0-3_CERTIFICATION_AND_CAPABILITY_MATRIX.md`. Commit `3bfaa5b`.
  Validator: 158 passed / 0 failed (PASS).
- 2026-06: Gas-model seam (item 3) — BaseGasModel.from_env() fails closed unless
  PROVIDER_RPC_URL(S)_BASE is explicitly set (public default no longer opens the
  M3 all-in-cost gate). Rewired stale test_base_all_in_cost.py to the registry
  seam (11/11). New test_gas_model_seam_failclosed.py. Commit `142084e`.
- 2026-06: Multichain readiness gate (item 4) — arbicore/runtime/multichain_
  readiness.py + GET /api/arbicore/multichain/readiness. Honest per-network
  status; NEVER limited-live eligible from code/config alone; economic dimension
  requires PROVIDER_* (ARBICORE_RPC_URL_BASE alone => economic_gate_rpc_not_
  configured). Endpoint error path keeps full SHADOW safety envelope. New
  test_multichain_readiness_gate.py. Commit `bd969ee`. Validator: 182 passed / 0.
- 2026-06: Certification harness path fix (commit `98da57f`). `scripts/
  arbicore_certify.py` now resolves APP_ROOT dynamically from its own location
  (=`<repo>/app/backend` in a checkout; =`/app` in the prod image where the
  Dockerfile does `COPY app/backend/ /app/`). KEY_MODULES + protected paths are
  APP_ROOT-relative so py_compile + integrity checks work in both layouts
  (missing file ⇒ explicit compile/integrity FAIL, never skipped). Git identity:
  live git when a `.git` checkout exists (authoritative), else BUILD_INFO.json /
  `ARBICORE_GIT_*` (real SHA/tag/image ref+digest inside the `.git`-stripped
  image); `git_source` reported. Protected git-dirty guard kept at full strength
  when git available (reported unavailable — never false-clean — in an image);
  deployment-only compose file honestly reported `not_in_image`. Matrix import
  guarded so a broken/removed key module yields a clean FALSE report + real
  error (never a fabricated matrix). Verified in both layouts + negative tests.
  NOTE: code/config certification (`repo_capability_pass`) is NOT P0-3; the real
  Base runtime proof requires the VPS (Base RPC). In the Emergent pod all chains
  correctly report `no_operator_configured_rpc` (no RPC ⇒ fail-closed).
- 2026-06: m3_0_real_candidate_scan fail-closed fix (commit `d00e894`).
  build_controlled_live_safety returns (None,None) when a Base controlled-live
  dep is missing (RPC provider / on-chain USD price feed); the scan called
  validator.validate() unguarded → AttributeError. Fixed via validate_candidate()
  (runs the REAL PreBroadcastValidator when present, else fail-closed DENY with
  the exact missing-dep reason — no fake validator/stub/bypass) +
  _controlled_live_unavailable_reason() read-only diagnosis. Regression
  tests/test_m3_0_real_candidate_scan_failclosed.py (4) wired into validator
  (235 passed/0). On the VPS the None-crash is now an explicit fail-closed reason
  (typically: set ARBICORE_USD_NUMERAIRE=USDC). Chains/venues preserved; signing/
  broadcast/auto-exec/full-live OFF.
- 2026-06: RouteSearch → chain/venue-aware quote wiring (commit `1f1d68f`).
  RouteSearchDiscoverySource now emits `route_hops` + a deterministic probe
  `borrow_amount_wei` for NON-Base cycles so the generic EVM path in
  `live_quote_provider` runs end-to-end (Base regression-frozen: `_plan_base`
  untouched, no route_hops emitted). New `chains/registries.probe_amount_wei`
  (<=6dec→200u, 18dec→0.05u, else fail-closed None — a PROBE only, never
  liquidity/capacity/trade-size/eligibility). New
  `searcher/runtime.make_eth_call_for_chain_from_env` (generic per-chain
  eth_call seam; real only when operator RPC configured; never Base fallback)
  wired into the canonical SHADOW quote provider in composition (additive,
  fail-closed; signer/broadcast untouched). Honest `quote_path_connected` flag
  + `quote_path_connected_count` (=40) added to the opportunity matrix/certify
  — STRUCTURAL connectivity only; quote/liquidity/economic stay
  `requires_runtime`, no cell limited-live eligible. New
  `tests/test_flash_route_to_quote_pipeline.py` (20 offline cases, all 14
  acceptance items) wired into the validator. Validator: 231 passed / 0 failed.
  Flash-loan SOURCE scope stays locked to {ethereum,arbitrum,base,optimism,
  polygon} (test_chain_scope_locked); bnb proven quote-capable at the provider
  layer only.

## Known blockers / backlog
- P0-3 VPS/Base runtime proof (live discovery→quote→liquidity→economics→evidence
  persist+readback) — mandatory, cannot be produced in Emergent.
- Non-Base networks (ethereum/arbitrum/optimism/polygon/bnb): IMPLEMENTED, need
  per-chain RPC config + health before limited-live eligibility.
- Pre-existing, out-of-scope failure (fails identically at 01a8989):
  `test_t1_multichain_foundation_adversarial.py::TestGasModelSeam::test_from_env_no_rpc_is_fail_closed`
  (env-driven). Not fixed.
- `composition.py` ~1.9k lines (> guideline) — future dedicated refactor only.

## Do-not-touch (VPS-local)
`scanners/dex_arbitrage/scanner.py`, `deployment/compose/docker-compose.yml`,
stash@{0} "VPS-local changes before P0-3 sync", branch
`backup/vps-before-p0-3-sync`. Preserve compose mapping `127.0.0.1:18001:8001`.
No merge to main, no force-push, no auto-deploy.

---

## TAKEOVER SESSION — 2026-09-05 (branch takeover/limited-live-seam-cc8db95, from HEAD cc8db95)

### Scope executed (user-approved): 1b + 2a + 3b + 4a
Trace architecture; wire missing GENUINE venue/quote/runtime seams (code only,
no live execution); run certification read-only against available RPC config;
do NOT attempt live execution / request keys; report LIMITED_LIVE_PROVEN=false
with exact blocker. Signing/broadcast/auto-exec/full-live/withdrawals OFF.

### Changes (commit 0bd9130)
- arbicore/chains/registries.py: explicit per-DEX ABI family classification
  (univ3/univ2/algebra/solidly/curve) + factory_for()/dex_abi()/annotated dexes_for().
- arbicore/discovery/univ3_pool_resolver.py: univ3_family_factory_for(); resolve_univ3_pool
  gains dex= to cover DIRECT UniV3 forks (Sushi V3, Pancake V3); new fail-closed
  resolve_univ2_pool() (getPair + getReserves) for Sushi V2.
- arbicore/discovery/opportunity_engine.py: venue-aware discoverability + honest
  per-family blockers; dex-aware discover_pools_parallel; abi surfaced per cell.
- arbicore/discovery/multichain_venues.py: probe universe now univ3-family +
  univ2-family; excludes algebra/solidly/curve (no resolver) — never fabricated.
- scripts/arbicore_certify.py: added provider-readiness + venue-family sections.
- tests/test_multichain_venue_seam.py: new offline suite (fork resolve, V2
  resolver fail-closed, matrix honesty). 

### Result
Certify PASS. Opportunity matrix: 75 rows, discoverable 40->55 (activated Sushi V3
/ Pancake V3 / Sushi V2), quote_path_connected=40 (unchanged — NO fabricated fork
quoter adapters), limited_live_eligible=0. Offline seam+regression tests 85 pass,
0 new regressions vs clean baseline. Protected files untouched.

### Runtime blocker (this container)
No web3-less RPC config present: no PROVIDER_RPC_URL[S]_*/ARBICORE_RPC_URL_* set;
provider_readiness blocked_by = {no_operator_configured_rpc: 6}. Live discovery→
quote→liquidity→economics→simulation→evidence and the controlled execution proof
are VPS-only (require operator RPC + funded signer). LIMITED_LIVE_PROVEN=false.

### Next (controlled execution-proof phase — needs operator)
Provide PROVIDER_RPC_URL_<CHAIN> for the allowed chain, dedicated low-value funded
signer, allowed venue/strategy; add fork QuoterV2 adapters (real verified addresses)
to close quote_path_connected for Sushi V3 / Pancake V3; run m3_0_vps_validate
read-only, then evidence-gated controlled proof with maximum-one execution + caps.

---

## TAKEOVER SESSION — PHASE 2 (commit dfe3d3b): fork quoters + Algebra resolver

### Delivered (still detection-only; signing/broadcast/auto/full-live/withdrawals OFF)
- quoter.py: SushiV3QuoterV2 (arb, 0x0524e833cCd057e4d7A296e3aaAb9f7675964Ce1),
  PancakeV3QuoterV2 (bnb, 0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997),
  UniV2RouterQuoter (Sushi V2 eth router 0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F,
  getAmountsOut). ABI-identical forks subclass UniV3QuoterV2; addresses from
  official docs; fail-closed off-map. Registered in QuoterRegistry.
- discovery/algebra_pool_resolver.py (NEW): fail-closed poolByPair resolver for
  Camelot V3 / QuickSwap V3 (dynamic fee). Discovery-only (no quote yet).
- opportunity_engine: Algebra now DISCOVERABLE; dex-aware parallel race covers
  univ3/univ2/algebra. Honest per-family blockers preserved.
- vps_multichain_preflight: venue-aware live probe now exercises univ3 forks +
  univ2 + algebra (read-only).
- docs/VPS_MULTICHAIN_RUNTIME_CERTIFICATION.md: VPS runbook.

### Result
Matrix: discoverable 55->65, quote_path_connected 40->55, limited_live_eligible=0.
Certify PASS. 110 tests pass in the venue/quote suite; 0 new regressions vs clean
baseline (1 pre-existing failure test_unsupported_chain, present in baseline).
Evidence: reports/TAKEOVER_CERTIFICATION_phase2.json. Protected files untouched.

### Remaining venue seams (honest)
- Algebra QUOTE adapter (dynamic-fee QuoterV2) — Camelot/QuickSwap discoverable
  but not quote-connected.
- Solidly/Velodrome + Curve resolvers — not implemented (explicit blockers).
- Fork quoter addresses must be re-verified live on first VPS run (fail-closed).

### Runtime blocker unchanged / LIMITED_LIVE_PROVEN
No RPC in this container (no web3 runtime, no operator RPC, no funded signer) ->
all live dims requires_vps_runtime. LIMITED_LIVE_PROVEN=false. Controlled proof
needs operator RPC + dedicated funded signer + allowed chain/venue/strategy +
explicit approval (see VPS runbook §7).

---

## TAKEOVER SESSION — PHASE 3 (commits 9e379d0, fc301b5): live read-only runtime certification

### What ran (read-only, against LIVE mainnet RPC via public endpoints — proxy for VPS)
- scripts/vps_runtime_certify.py (NEW): per chain×venue×pair discover→quote→liquidity
  + cross-venue pre-cost spread + head/latency. No signing/broadcast/keys.
- scripts/vps_multichain_preflight.py: venue-aware live probe (phase-2 extension).
- Evidence: reports/VPS_RUNTIME_CERT_public.json + VPS_RUNTIME_CERTIFICATION_REPORT.md.

### Live runtime results (public RPC)
- probe_rows 62 · discoverable 56 · liquidity_verified 56 · quotable 49.
- univ3 (Uniswap V3 + Sushi V3 + Pancake V3): 46/46/46 → QUOTABLE proven live.
- univ2 (Sushi V2): 3/3/3 → QUOTABLE proven live.
- algebra (Camelot V3 + QuickSwap V3): 7 discoverable+liquid, 0 quotable (no quoter adapter).
- Cross-venue big spreads (1036%/341%/30%) = illiquid-pool artifacts (gate rejects).
  Plausible ones (0.05–1.1%) below net cost. NET economics 0, fork sim 0 (no anvil here).
- Execution-ready candidate: NONE. LIMITED_LIVE_PROVEN=false.

### Recommendation
Next highest-value seam by EVIDENCE = Algebra QuoterV2 adapter (7 liquid pools blocked
only by missing quoter). Then wire net economic gate into multichain cross-venue path.
Re-run on VPS operator RPC (archive nodes) for authoritative numbers. No execution proof
until a genuine net-positive, gate-passing, simulated candidate exists.

---

## TAKEOVER SESSION — PHASE 4 (commit c6cbf7c): Algebra quoter + net-economics candidate gate

### Item 1 (authoritative operator/archive VPS run): BLOCKED here — no operator RPC in
container, not on VPS, no credentials (per standing instruction). Public-RPC numbers are
labeled as such and NOT substituted for operator results. Operator run remains a VPS prereq.

### Delivered (safety unchanged: all OFF, kill switch engaged; production untouched)
- quoter.py: CamelotV3Quoter + QuickSwapV3Quoter (Algebra dynamic-fee ABI
  quoteExactInputSingle(address,address,uint256,uint160)->(amountOut,uint16 fee)).
  Addresses: Camelot 0x0Fc73040b26E9bC8514fA028D998E73A254Fa76E (arb),
  QuickSwap 0xa15F0D7377B2A0C0c10db057f641beD21028FC89 (polygon). LIVE-VERIFIED
  (0.05 WETH -> 123.63 / 123.52 USDC). Fail-closed off-map. Registered.
- scripts/vps_runtime_certify.py: real cross-venue NET-ECONOMICS candidate gate wiring
  existing fail-closed compute_true_net_profit (on-chain gross edge, chain gas model,
  quoter route-gas, provider optimizer). Conservative DENY on missing input; no synthetic
  fallbacks. Candidate matrix DISCOVERED->LIQUIDITY->QUOTABLE->ECON->VERIFIABLE->
  SIMULATABLE->LIMITED_LIVE.

### Live race result (public RPC, 5 EVM chains + base-skipped)
probe_rows 62 · discoverable 56 · liquidity_verified 56 · quotable 56 (ALL families incl
Algebra) · candidates 15 · economically_valid 0 · execution_ready 0.
All 15 cross-venue candidates eliminated at NET_ECONOMICS: negative_gross_edge (no real
arb at probed block). LIMITED_LIVE_PROVEN=false. Item 7 harness NOT staged (precondition
unmet). Evidence: reports/VPS_RUNTIME_CERT_public.json + VPS_RUNTIME_CERTIFICATION_REPORT.md.

### Matrix (offline): discoverable 65, quote_path_connected 65 (Algebra now connected),
limited_live_eligible 0.

---

## TAKEOVER SESSION — PHASE 5 (commit pending): multi-hop + dynamic sizing + fork-sim gate
- quoter.py: quote_route_strict (all-hops-ok, no passthrough; Algebra multi-hop verified live).
- vps_runtime_certify: dynamic size sweep + full evidence bundle (block/pools/token_path/hops/
  liquidity/fees/gas/provenance/timestamp/evidence_id) + 7-state candidate matrix + SIMULATION_UNAVAILABLE.
- Race (public RPC): 15 candidates, ALL negative_gross_edge_all_sizes; economically_valid 0; execution_ready 0.
- Item1 VPS operator run BLOCKED (no operator RPC/VPS). Item5 fork sim SIMULATION_UNAVAILABLE (no anvil).
  Item7 harness NOT staged. LIMITED_LIVE_PROVEN=false. Certify PASS (65/65/0). No new regressions.


## TAKEOVER SESSION — PHASE 5b (2026-06): certification-harness fix (import path + provenance)
Fix ONLY the VPS certification/runtime harness + provenance handling. Source
otherwise unchanged; 3 protected files + main/production untouched; all execution OFF.

- BUG A (Step-6 `ModuleNotFoundError: No module named 'arbicore'`): the authoritative
  cert invokes harnesses by DIRECT PATH (`python /app/scripts/<name>.py`), putting
  `scripts/` on sys.path[0] not the app root. Fix: `vps_multichain_preflight.py`,
  `vps_runtime_certify.py`, `arbicore_certify.py` each prepend their own APP_ROOT
  (`Path(__file__).parent.parent`) to sys.path — works under BOTH `-m` and direct-path.
- BUG B (provenance contamination): `arbicore_certify` reported inherited production
  `ARBICORE_GIT_SHA=bd969ee…`/tag `p0-3-bd969ee` instead of the isolated image's real
  `ad64a50…`. Fix: `_build_identity` refactored to pure `_resolve_identity`; in
  `.git`-stripped IMAGE mode the baked `BUILD_INFO.json` is authoritative and a
  disagreeing runtime env is reported as `provenance_contamination` + IGNORED (never
  emitted). Checkout mode still certifies live working tree. Surfaced in repo section
  + human output.
- Regression: `tests/test_cert_harness_invocation_and_provenance.py` (7 tests pass):
  direct-path invocation of preflight + certify; image-mode BUILD_INFO-wins-over-stale-env;
  env-unverified fallback; checkout live-git wins; full `_build_identity` end-to-end.
- Docs: runbook `docs/VPS_MULTICHAIN_RUNTIME_CERTIFICATION.md` §0a (both invocation
  styles) + §0b (isolated-image build + provenance; do not pass a production env_file).
- Public-RPC PROXY re-run with FIXED harness (direct-path; NOT operator/VPS):
  preflight resolved eth 9/9, op 6/6, poly 12/12, arb 14/15, bnb 15/20 (base canonical);
  race probe_rows 45 · discoverable/liq/quotable 40 · candidates 7 ·
  ALL negative_gross_edge_all_sizes · economically_valid 0 · execution_ready 0 ·
  anvil unavailable · LIMITED_LIVE_PROVEN=false. Evidence:
  reports/PREFLIGHT_PUBLIC_PROXY_phase5_harnessfix.json,
  reports/VPS_RUNTIME_CERT_public_phase5_harnessfix.json.
- VPS-only blockers (honest, not converted to pass): no Docker (cannot rebuild/run
  isolated image), no operator/archive RPC, no anvil, no funded signer.
- Certify offline: git_sha=ad64a50, provenance clean, repo_capability_pass=True.
  Commit pending → push via "Save to Github".


## TAKEOVER SESSION — PHASE 5c (2026-06): cert blockers 1-4 + honest activation matrix
Branch takeover/limited-live-seam-cc8db95. All execution OFF; main/production +
3 protected files untouched; no fabrication; no SUPPORTED_DEXES change.

- BLOCKER 1 (Docker provenance): scripts/gen_build_info.py hardened — pure
  resolve_git_identity + is_valid_full_sha (40-hex). STRICT mode (ARBICORE_GIT_STRICT)
  FAILS the build if SHA would be unknown/malformed; a malformed explicit SHA always
  raises. Dockerfile (deployment/docker/backend/Dockerfile — NOT protected) adds
  ARG GIT_STRICT + ENV ARBICORE_GIT_STRICT and drops `|| true` so cert builds cannot
  silently embed a placeholder. Cert build cmd: `--build-arg GITSHA=$(git rev-parse HEAD)
  --build-arg GIT_STRICT=1`. arbicore.gitsha LABEL already embeds GITSHA.
- BLOCKER 2 (multichain operator RPC): verified all 6 chains
  (base,eth,arb,op,poly,bnb) consume PROVIDER_RPC_URLS_<CHAIN> (economic gate) and
  ARBICORE_RPC_URL_<CHAIN> (discovery only), fail-closed when unset. Public-RPC PROXY
  race resolved pools on all 6 (eth 9/9, op 6/6, poly 12/12, arb 14/15, bnb 15/20).
- BLOCKER 3 (executor capability audit): scripts/executor_capability_audit.py (read-only)
  classifies 15 venue cells across DISCOVER/QUOTE/ROUTE-CONSTRUCT/EXECUTION. Findings:
  on-chain FlashLoanReceiver executes uniswap_v3 swaps + balancer_v2 borrow ONLY.
  execution_capable=6 (uniswap_v3 × 6 chains). Aerodrome swap adapter EXISTS
  (route_constructable) but NOT execution-capable (receiver=UniV3 only). sushi_v3/
  pancake_v3/camelot_v3/quickswap_v3/sushi_v2 quotable but no DEX calldata adapter.
  curve/velodrome not discoverable (resolver not implemented). aave_v3/uniswap_v3 flash
  adapters exist but receiver borrows balancer_v2 only; morpho_blue no adapter. NO
  SUPPORTED_DEXES change (adding venues would fabricate execution capability).
- BLOCKER 4 (Mongo/broadcast-ladder): m3_0_real_candidate_scan.py — the ONLY Mongo
  dependency was the optional confirm=False broadcast-ladder proof (kill-switch/mode/
  capital Motor repos → hung on factory-mongo:27017). Now isolated via _mongo_reachable()
  ping + _broadcast_ladder_proof() that DEFERS with explicit `deferred_mongo_unavailable`
  when Mongo unreachable. Core candidate scan is Mongo-free/read-only. Dependency made
  explicit, not hidden.
- Tests: tests/test_phase5b_activation_audit.py (16) + existing harness/provenance (8);
  venue/cert/provenance suites 71 passed. Compile OK. Certify PASS, provenance clean.
- Evidence: reports/EXECUTOR_CAPABILITY_AUDIT.json, reports/PHASE5B_ACTIVATION_MATRIX.md.
- Activation truth: economically-valid cells 0 (real negative edge), Limited-Live-eligible 0,
  LIMITED_LIVE_PROVEN=false. Runtime SIMULATION/EXECUTION + operator-authoritative numbers
  remain VPS-only (no Docker/anvil/operator RPC/funded signer here). Commit pending → push
  via "Save to Github".

## TAKEOVER SESSION — PHASE 5d (2026-06): DEX/flash adapter route-construction expansion
Branch takeover/limited-live-seam-cc8db95. All execution OFF; main/production +
3 protected files untouched; no fabrication; SUPPORTED_DEXES UNCHANGED.

- Implemented REAL calldata adapters in arbicore/execution/adapters.py, wired into
  the ExecutionPlanner path (planner.py consumes AdapterRegistry.dex()/flash() —
  NOT registry-only): UniswapV2SwapAdapter (sushiswap_v2), UniV3ForkSwapAdapter
  (sushiswap_v3, pancakeswap_v3), AlgebraSwapAdapter (camelot_v3, quickswap_v3),
  SlipstreamSwapAdapter (aerodrome_slipstream), MorphoBlueFlashLoanAdapter.
  Router/singleton addresses are ENV-first (f"{CHAIN}_{DEX}_ROUTER") with fail-closed
  None default — NO guessed/hard-coded on-chain addresses (verify live on VPS).
- Effect (executor_capability_audit): route_constructable 7→13; execution_capable
  UNCHANGED at 6 (uniswap_v3 × 6 chains) because the deployed on-chain FlashLoanReceiver
  executes UniV3 swaps + Balancer V2 borrow only. Adding venues to SUPPORTED_DEXES would
  fabricate execution capability → NOT done. flash adapters now: aave_v3, balancer_v2,
  uniswap_v3, morpho_blue (exec-capable still balancer_v2 only).
- Added explicit 11-state CERTIFICATION_STATES model to the audit (per-cell states;
  runtime states = requires_runtime, never asserted offline).
- Tests: tests/test_phase5c_dex_adapter_expansion.py (9) incl. real ExecutionPlanner
  integration + fail-closed router + honesty (execution_capable⊆SUPPORTED_DEXES).
  32 passed across phase5b+5c+harness suites. Existing offline adapter/planner unit
  tests pass (44); server/auth-dependent wave6 tests fail 401 (pre-existing infra only).
- Evidence: reports/EXECUTOR_CAPABILITY_AUDIT.json (regenerated),
  reports/PHASE5C_ACTIVATION_MATRIX.md (full item-11 matrix).
- Activation truth: economically-valid 0 (real negative edge), Limited-Live-eligible 0,
  LIMITED_LIVE_PROVEN=false. Runtime SIM/EXEC + operator numbers remain VPS-only.
  Curve/Solidly resolvers still not implemented (exact remediation documented).
  Commit pending → push via "Save to Github".


## TAKEOVER SESSION — PHASE 5e (2026-06): six-chain operator-RPC configuration seam
Branch takeover/limited-live-seam-cc8db95. Config-infra only; NO production change;
signing/broadcast/auto-execution/Full-Live/Limited-Live/withdrawals OFF; 3 protected
files + main untouched; no secrets/RPC URLs committed.

- Canonical mechanism: per-chain env vars consumed by
  arbicore/runtime/multichain_readiness (rpc_explicitly_configured →
  PROVIDER_RPC_URLS_<CHAIN>/PROVIDER_RPC_URL_<CHAIN>/ARBICORE_RPC_URL_<CHAIN>/<CHAIN>_RPC_URL;
  provider_registry_rpc_configured → PROVIDER_RPC_URLS/PROVIDER_RPC_URL only) — already
  per-chain-strict, fail-closed, no URL values in reports.
- FIX (cross-chain leakage): arbicore/config/persistent.py resolve_rpc_url_from_env +
  async resolve_rpc_url — the non-chain-specific ARBICORE_RPC_URL global is now a
  BASE-ONLY alias; it no longer leaks Base's endpoint to eth/arb/op/poly/bnb (which
  previously made them falsely "configured" and routed their RPC calls to Base).
  Base precedence unchanged: ARBICORE_RPC_URL_BASE > ARBICORE_RPC_URL > BASE_RPC_URL.
- Config template (names only, no values): deployment/cert/.env.example lists all 12
  keys (6 PROVIDER_RPC_URLS_<CHAIN> + 6 ARBICORE_RPC_URL_<CHAIN>) + base-only aliases;
  real values file deployment/cert/.env is git-ignored (verified). VPS injects via
  `docker run --env-file` or `set -a; . .env; set +a`.
- Tests: tests/test_six_chain_rpc_seam.py (10) — six chains keyed independently;
  missing=fail-closed; correct-chain consumption; no cross-chain leakage from base
  alias; Base precedence preserved; five non-Base chains independently authoritative;
  readiness report emits NO RPC values; template lists all names/no values. Offline
  regression: seam+t0+phase5b 43 passed; config/env-sync suites 92 passed.
- Required env var names (values supplied ONLY on VPS, never in Git):
  PROVIDER_RPC_URLS_{BASE,ETHEREUM,ARBITRUM,OPTIMISM,POLYGON,BNB},
  ARBICORE_RPC_URL_{BASE,ETHEREUM,ARBITRUM,OPTIMISM,POLYGON,BNB}.
- Opportunity Race NOT run (per instruction). Six chains NOT declared configured until
  real operator RPCs supplied on VPS. Commit pending → push via "Save to Github".

---

## INDEPENDENT READ-ONLY AUDIT — 2026-09-08

### Current user assignment (supersedes earlier implementation next steps)
Perform a TWO-PHASE independent, READ-ONLY audit of ArbiCore X v2: Phase A
current-state whole-app assessment at commit
`2e6f253dd354248e0ad861b2011bdfbcef63eb97` on
`astra-audit-limited-live-5f8475a`; Phase B prioritized forward engineering.
Preserve Base, Ethereum, Arbitrum, Optimism, Polygon and BNB scope. No source,
config or secret changes; no tests/app execution/RPC/signing/broadcast; no
commits/merges/PRs. STOP after the report; no fixes authorized. Latest user
instruction: prioritize depth/evidence, control credits, avoid unnecessary
delegation; core whole-app audit before materially relevant targeted checks.

### Delivered
- `/app/audit_report.md`: both phases, executive summary, subsystem/strategy
  inventory, six-chain and 15-cell venue matrices, flash-provider matrix,
  10 High findings, 6 Medium observation groups, P0/P1/P2/P3 roadmap and
  per-chain acceptance evidence. No confirmed Critical finding.
- Target remote ref verified. Checkout remained on
  `takeover/limited-live-seam-cc8db95` at `5f8475a`; pre-existing edits were not
  the audit basis. All authoritative source read from target Git objects.
- Static reference validation: 101 cited ranges across 43 files resolve.
  Targeted AST inspection confirmed missing throttle arguments and missing
  endpoint auth dependencies. No application tests or runtime probes run.
  JavaScript static lint unavailable (engine error); no passing JS claim.
- No source/config fixes implemented. Only report and this memory entry written.

### Findings that correct stale historical readiness claims
- High: unauthenticated network, strategy-mode and operational mutations.
- High: `_throttle(scope)` called without scope in atomic simulator and wallet
  token reads; exact simulation not usable through these calls at audit commit.
- High: probe-size quote percentage reused at different USD trade notional;
  quoter global-RPC precedence leaks Base endpoints into non-Base quote paths.
- High: non-Base canonical flash forks rejected, TVL remains Base-composed,
  BNB excluded; runtime certification lacks provider liquidity and actual
  candidate simulation; executor identity can report READY on missing getters.
- Receiver source supports Balancer AND Aave, not Balancer only; swaps remain
  one immutable UniV3 router. Final Base M3 still only admits Balancer. Target
  registry records Base mainnet and Sepolia, not five other requested mainnets.
- No requested mainnet is demonstrated profitable/runtime-certified by this
  static audit. Historical public-RPC reports are not fresh target-commit proof.

### Recommendations only — NOT approved implementation tasks
- P0: authorization, throttle consumers, exact-size economics, chain isolation,
  strict executor identity and truthful candidate evidence.
- P1: full canonical six-chain/provider/venue composition; versioned receiver
  and verified per-chain deployments; real liquidity/net/simulation harness.
- P2: nonce/idempotency/finality/P&L reconciliation, operational recovery,
  private submission, coherent modes/UI and broader strategy execution.
- P3: measured ranking/calibration/performance and evidence-backed expansion.
- Enhancement: evidence-linked chain/venue/strategy dashboard with first blocker
  and evidence age. No further work until a new user-authorized task.


---

## PHASE P0 REMEDIATION — 2026-09-09 (branch takeover/limited-live-seam-cc8db95)

Authority: Astra audit at commit 2e6f253. Scope executed: P0 ONLY (H01,H02,H03,
H04,H05,H06,H10). STOPPED before P1/M01-M07/H07-H09 per directive. Full report:
`/app/P0_EXIT_REPORT.md`. Safety envelopes (signing/broadcast/auto-exec/Full-Live)
stayed OFF; protected files (dex_arbitrage/scanner.py, deployment/compose/
docker-compose.yml, deployment/cert/.env.example) untouched; no commit/merge/deploy.

### Environment fix (fork had lost .env)
- Restored `/app/backend/.env` (from /app/memory backup) + `/app/frontend/.env`
  (REACT_APP_BACKEND_URL). Backend was crashing on missing MONGO_URL.
- Seeded test accounts (pod-local, git-ignored, NOT committed):
  admin/ArbiCore2026! , operator/ShadowOperator!2026 (see test_credentials.md).
- Fixed recurring pre-completion "linter engine error": root `eslint.config.js`
  was ESM in a no-package.json dir → converted to CommonJS (tooling-only).

### P0 fixes (all verified; testing_agent 19/20, 1 env-only admin-seed drift, resolved)
- H01/H02/H03 (server.py): request-scoped `_CURRENT_ACTOR` ContextVar +
  `_audit_actor()`; `_require_operator_dep` stamps server-derived actor; added
  `dependencies=[Depends(_require_operator_dep)]` to 42 /arbicore/* mutation
  routes (deny-by-default; /status template stays public); replaced 21
  client-supplied `actor` reads with `_audit_actor()` (spoof-proof, confirmed
  via /arbicore/execution/mode/audit/history).
- H04: quoter._throttle(scope) consumers fixed in atomic_executor_sim.py +
  capital/wallet_intelligence.py (pass `_throttle_scope(rpc_url)`).
- H05: live_quote_provider emits size_basis/exact_size/quote_notional_usd;
  verifier + composition M3 fail closed (DENIED_SIZE_NOT_QUOTED) on probe-sized
  quotes and bind economics notional to the exact quoted size. New
  `VerifiedOutcome.DENIED_SIZE_NOT_QUOTED`. Regression: test_h05_exact_size_binding.py (5/5).
- H06: quoter _rpc_url/_rpc_url_candidates chain-scoped; global ARBICORE_RPC_URL/
  PROVIDER_RPC_URLS are Base-only aliases → non-Base fails closed (no leakage).
- H10: probe_executor_identity fail-closed (positive selector + known expected
  identity + all getter reads present + exact match, else UNKNOWN/BLOCKED);
  resolve_executor_address chain-scoped (Base env not returned for other chains).

### Regression status
- Offline unit sweep (215 files): with-changes vs baseline (changes stashed) =
  IDENTICAL failure set → 0 regressions. 59 pre-existing offline failures are
  environmental (no operator RPC / empty Mongo / no anvil / no seeded CONFIRMED
  evidence bundle) and fail identically without the P0 changes.
- Live E2E suites (72 files) intentionally not chased: many use drifted hardcoded
  creds and unauth calls that now (correctly) 401 under H03.

### VPS-only follow-ups (P0 evidence that needs operator)
- H05 exact-size CONFIRM needs an operator price feed / borrow_sizer (pod fails
  closed = honest). H06 optional eth_chainId challenge is defense-in-depth. H10
  positive READY needs a real deployment + archive RPC.

### Next (NOT started — awaiting user go-ahead for P1)
- P1: M01 evidence tiers, M02 real capability matrix, M03 actual economic inputs,
  M04 true net-optimal size, M05 deadline/freshness/blockhash, M06 one readiness
  model, M07 remove false financial readiness; H07/H08/H09.

---

## PHASE P1 — BATCH 1 — 2026-09-09 (branch p1-batch1-m01-m06-m07-h06, off P0 baseline)

Approved scope 1a/2a/3a. Full report: `/app/P1_BATCH1_EXIT_REPORT.md`. Safety OFF;
protected files untouched; no merge/deploy/real-tx. STOPPED after Batch 1.

- M01 (evidence tiers): new `arbicore/certification/evidence_tiers.py` — one ordered
  EvidenceTier ladder + non-certifying vs certifying sim-method sets. noop/symbolic/
  paper/heuristic/infra (even ok=True) never reach SIMULATION_CERTIFIED+.
- M06 (single authoritative readiness): kept ShadowCertificationEngine/ExecutionCertifier
  as the sole surface (no parallel framework). Certifier simulation stage rebound: exact
  candidate-bound method required for PASS; heuristic sim → INFO + WARNING ⇒ verdict capped
  at WAIT. Component READY ≠ candidate ≠ sim PASS ≠ runtime ≠ limited-live.
- M07 (financial truthfulness): server.py vaults/exchanges GET+reconcile+test now return
  MOCKED/NOT_CONFIGURED, mocked:true, contributes_to_readiness:false, null secrets/timestamps.
- H06 (chain-id guard): quoter verifies eth_chainId per endpoint before use AND failover
  (six chains), per-host cache, fail-closed on wrong/ambiguous/unreadable; ON for default
  backends, off for injected-backend unit stubs.
- H07 (safe in-pod): live_quote_provider TVL is `tvl_provider_chain`-scoped (default base) —
  no cross-chain TVL leakage; non-base fails closed. Full six-chain runtime deferred to VPS.
- H08/H09: deferred (VPS/operator) — receiver deployment + genuine candidate-bound exact
  simulator not provable in-pod. H05 exact-size sizer still needs operator price feed.

Tests: test_m01_evidence_tiers.py (6/6), test_h06_h07_chain_isolation.py (6/6),
test_m07_truthfulness.py (10/12; 2 = read-side authz on 2 settings GETs, out of scope),
P0 suites still green. No new regressions (delta vs P1-stashed baseline identical;
2 fixtures updated to new chain-scoped contract; test_unsupported_chain pre-existing).
testing_agent: /app/test_reports/iteration_2.json.

Known non-defects: two settings GETs (vaults/exchanges) return 200 unauth — consistent with
app's existing public-GET posture, truthful bodies, no secrets; read-side authz is a
separate app-wide decision, NOT Batch 1 scope.

Next (awaiting approval): P1 Batch 2 — deeper H07 six-chain composition wiring + H08/H09
(VPS-dependent), and remaining M-items.

---

## PHASE P1 — BATCH 2 — 2026-09-09 (branch p1-batch2-h07-h08-h09, off Batch 1)

Additive-only (no production source modified). Full report: `/app/P1_BATCH2_EXIT_REPORT.md`.
Safety OFF; protected files untouched; no merge/deploy/real-tx. STOPPED after Batch 2.

- H07 (six-chain isolation): proven in-pod across base/eth/arb/opt/poly/bnb — RPC alias
  no-leak + eth_chainId 6x6 no-cross-accept + chain-scoped TVL + Base-only certified
  composition. Real per-chain runtime deferred to VPS.
- H08 (receiver fabric): new `arbicore/execution/receiver_capability.py` — fail-closed,
  versioned capability over executor_registry. receiver_supports(chain,provider)=False
  unless a deployed receiver EXPLICITLY declares the provider (no inference). Owner/
  repayment/unsupported-venue/deployment checks preserved. No deploy; production receiver
  untouched.
- H09 (candidate-bound sim): new `arbicore/certification/candidate_simulation.py` —
  CandidateSimulationBinding (chain/block/token/decimals/exact_input/route/calldata/
  liquidity/economics/executor/receiver_version) + fail-closed evaluator. Certifies ONLY
  when binding complete + exact candidate-bound method + ok + chain match. Infra/noop/
  symbolic/paper/heuristic never certify. Exact fork simulator deferred to VPS.
- H05 preserved (probe economics still fail-closed). M01/M06/M07 invariants preserved.

Tests: test_p1b2_h07_h08_h09.py (13/13); combined P0+P1 regression 62 passed. Batch 2
added no live endpoints ⇒ testing_agent N/A this batch; Batch 1 live verification
(iteration_2.json) still valid (no production code changed).

Known non-defect (carried): two settings GETs public (truthful bodies) — read-side authz
is a separate app-wide decision. test_m07_truthfulness GET tests re-aligned to that contract.

Next (awaiting approval): VPS-gated runtime proofs (operator RPC, deployed versioned
receiver, exact candidate simulator, funded signer) — NOT startable in-pod.

---

## VPS CERTIFICATION HARNESS — 2026-09-09 (branch vps-cert-p1b2, off Batch 2)

In-pod engineering of a READ-ONLY, fail-closed certification harness + isolated
NON-PRODUCTION compose + operator runbook. No VPS access from pod → tooling only;
real six-RPC/on-chain evidence is produced by the operator on the VPS. Report:
`/app/VPS_CERT_HARNESS_COMPLETION_REPORT.md`. Safety OFF; protected files (incl.
production docker-compose.yml) untouched; no secrets committed; no merge/deploy.

- arbicore/certification/vps_harness.py — checks → PASS/FAIL/BLOCKED/UNKNOWN/
  NOT_CONFIGURED, reusing quoter(H06)/receiver_capability(H08)/candidate_simulation
  (H09)/probe_executor_identity(H10)/executor_registry. VPS-unavailable never PASS.
- scripts/vps_certify.py — 12-section report + JSON, commit/timestamp/safety-state,
  writes /app/vps_cert (VPS: ./vps_cert_out). In-pod dry-run = 0 PASS (all
  NOT_CONFIGURED/BLOCKED) — honest fail-closed.
- deployment/compose/docker-compose.certification.yml — isolated project
  `arbicore-cert` (own containers/net/volume, one-shot runner, safety OFF), does
  NOT touch production stack. deployment/cert/{cert.env.example, RUNBOOK}. cert.env
  + vps_cert_out git-ignored.
- H08 for 84532 stays BLOCKED (no supported_providers declared) — registry edits
  alone won't flip it; on-chain verify + explicit provider declaration required.
  No new receiver deployed (needs separate approval).

Tests: test_vps_harness.py 14/14 (incl. VPS-unavailable-never-PASS); combined
P0+P1+cert regression 76 passed. testing_agent N/A (CLI harness, no live endpoints).

Next: operator runs the runbook on the VPS staging container and returns the real
12-section report; then await approval before Opportunity Race / Limited Live.

---

## VPS CERT RUNNER FIX — 2026-09-09 (branch vps-cert-p1b2-fix, HEAD b2b4977)

BUG: `python -m scripts.vps_certify` → ModuleNotFoundError: No module named
'scripts' in arbicore-cert-runner. ROOT CAUSE: backend Dockerfile does
`COPY app/backend/ /app/` (code root=/app, WORKDIR /app), but the cert compose
set `working_dir: /app/backend` (absent in image) ⇒ parent of `scripts` not on
sys.path for `-m`. FIX (one line): certify service working_dir /app/backend→/app
in deployment/compose/docker-compose.certification.yml. Added regression test
app/backend/tests/test_vps_cert_container_entrypoint.py (ties compose working_dir
to the Dockerfile COPY dest; asserts scripts package + module resolvability + safe
isolation). Verified by testing_agent (/app/test_reports/iteration_3.json): exit 0,
no ModuleNotFoundError, report written, status_counts zero PASS (fail-closed), 18/18
tests pass. No production/protected/gate/receiver changes. Docker unavailable in pod
⇒ verified via code-root bash reproduction; real image rebuild runs on the VPS.

---

## TRACK 4/8/2 — Aave V3 runtime liquidity probe + evidence-driven flash readiness — 2026-06 (branch vps-cert-p1b3-buildinfo-gitsha-fix, HEAD f3f8aa3)

GOAL (Msg 168): expand genuine runtime opportunity surface beyond Base/UniV3/Balancer
without fabricating activations. Safety locks intact (signing/broadcast/auto-exec OFF,
LIMITED_LIVE RED, protected files untouched, no deploy).

IMPLEMENTED + VERIFIED (pytest, deterministic offline):
- provider_liquidity.runtime_flashloan_available — NEW chain-generic, fail-closed
  tri-state flash-loan liquidity probe over a bare async eth_call(to,data):
  True (liq>=borrow) / False (definitive: unsupported provider|chain, reserve unlisted,
  insufficient) / None (read failure|unpriceable => DENY). Real Aave V3 read
  (getReserveData -> aToken -> balanceOf) + Balancer V2 vault. RUNTIME_PROBE_PROVIDERS =
  {balancer_v2, aave_v3}; every other catalog provider (morpho_blue, ...) => False
  (registry presence != runtime capability). BALANCER_V2_CHAINS excludes BNB.
- composition._flashloan_available (Base broadcaster fresh_fn): was hardcoded
  balancer_v2-only; now delegates to the single source of truth => Aave V3 genuinely
  gated at runtime. Semantics unchanged (fail-closed).
- readiness._flash: dropped static "Aave V3 executable / Balancer V2 executable" claim.
  Evidence-driven: reports the real runtime probe; execution capability UNPROVEN until a
  deployed receiver EXPLICITLY supports a flash head (receiver_capability fail-closed).
  LIMITED_LIVE stays RED / non-activatable.

TESTS: test_track4_aave_runtime_probe.py (12) + test_track8_readiness_flash_evidence.py (4).
Touched-module suites all green in isolation (control_readiness 10, flashloan_live_probes 28,
h05 21, provenance 8, flash_provider_optimizer 8, v2117_aave_calldata 15, phase2_liquidity 13).
NOTE: full `pytest tests/` shows mass env failures (no MONGO_URL/RPC, HTTP-endpoint tests,
xdist event-loop pollution) — pre-existing/environmental, NOT from this batch (reproduced
without the new files). Container needed `pip install pytest-asyncio` to run async tests.

CAPABILITY DELTA (this batch): Base x UniV3 x flash-arb x **Aave V3** moved from
runtime-REFUSED -> runtime-WIRED liquidity gate (fail-closed). Aave V3 probe now
chain-generic for eth/arb/op/polygon/base/bnb given operator RPC (no Base-RPC leakage).
EXECUTION-CAPABLE and LIMITED-LIVE-ELIGIBLE cells remain 0 (no deployed receiver evidence,
no operator RPC in this env, LIMITED_LIVE hard-gated). Morpho: catalog-only, deliberately
NOT runtime-wired (no genuine reader) — fails closed.

BLOCKERS unchanged: GitHub push blocked from shell (local commits only, by user decision);
non-Base execution needs deployed+verified receiver (separate approval) + operator RPC.

---

## TRACK 2 — reusable chain-scoped execution-readiness evaluator — 2026-06 (branch vps-cert-p1b3-buildinfo-gitsha-fix, HEAD 49bba06)

GOAL: expand genuine NON-Base opportunity surface by generalising the Base-only
pre-broadcast execution gate into a reusable, chain-scoped ladder for all six
networks. Selected Arbitrum first (strongest genuine support: 8 tokens, UniV3 +
SushiV3, 112-route universe, Aave V3 + Balancer V2). Safety intact.

NEW: arbicore/control/chain_execution_readiness.py
- Ladder: RPC -> CHAIN_VERIFICATION -> MARKET_COMPOSITION -> LIQUIDITY_PROVIDER
  -> QUOTE -> ECONOMICS -> ROUTE -> SIMULATION -> EXECUTION_CAPABILITY.
- Status PASS/BLOCKED/UNKNOWN; each stage fails closed on its own missing
  evidence; execution_capable True only when ALL stages PASS.
- Chain-scoped seams (never Base fallback): make_eth_call_for_chain_from_env,
  base=canonical graph / others=multichain_venues, get_chain_gas_model(chain),
  receiver_capability(chain), resolve_executor_address(chain), runtime flash
  heads per chain. CHAIN_VERIFICATION reads eth_chainId and BLOCKS on mismatch
  (guard against RPC bound to wrong/Base chain).
- signed/broadcast always False; limited_live_eligible always False. Placed under
  control (not runtime) to dodge Mongo-coupled runtime import; economic-RPC check
  inlined; all arbicore imports lazy + read-only. Receiver capability generalized
  per-chain (no fabricated deployment).
- Helpers: make_registry_chain_id_reader (VPS live chain-id read),
  build_chain_execution_readiness_report (offline six-chain report).

TESTS: test_track2_chain_execution_readiness.py (13) — chain-scoped selection,
no Base leakage, wrong-chain RPC BLOCKED, missing rpc/receiver/executor/sim fail
closed, no signing/broadcast, Limited-Live RED, six-chain offline report all
fail-closed. All 29 track (2+4+8) tests green together; each touched file green
in isolation (control_readiness cross-file event-loop pollution is a pre-existing
xdist/pytest-asyncio quirk, not this batch).

COVERAGE DELTA: execution-readiness now assessable per chain for all six networks
(previously only Base had any execution path). Arbitrum/BNB/ETH/OP/Polygon reach
MARKET_COMPOSITION + ROUTE = PASS with genuine UniV3 universes; blocked at RPC/
economics/execution only by absent operator RPC + no deployed receiver. No cell is
execution-capable or Limited-Live eligible (fail-closed). Infrastructure + genuine
chain-scoped wiring; RUNTIME-PROVEN still needs operator RPC; execution needs a
deployed+declared receiver (separate approval).
