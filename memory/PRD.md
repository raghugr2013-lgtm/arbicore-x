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
