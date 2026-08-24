# ARBICORE X — REPOSITORY AUDIT & FEATURE INVENTORY
Audit-first pass per the credit-efficiency directive. READ-ONLY (no functional code
changed in this pass). Purpose: prove reuse over rebuild, map roadmap→existing assets,
and classify duplication. Cross-branch + history verified.

## 0. Method / scope
- Branches inspected: `flashloan-live-shadow` (current, HEAD), `origin/main`, `origin/archive-v1`,
  `origin/feature/ui-v2-slices-0-2`, `origin/hotfix/auth-routing`, `origin/scanner-bootstrap-validator-fix`.
- History: 149 commits; symbol/concept search across all branches (git grep) for every
  capability below.
- Existing docs REUSED (not regenerated): `docs/ARBICORE_X_PRODUCTION_ACTIVATION_RUNBOOK.md`,
  `docs/LIMITED_LIVE_FLASH_LOAN_READINESS_AUDIT.md`, `docs/SHADOW_CERT_v2.11.9_LIVE_REPORT.md`,
  `docs/FLASH_LOAN_ARCHITECTURE_AUDIT.md`, `docs/RUNTIME_INTEGRITY_AUDIT.md`,
  `docs/V2_FLASH_LOAN_CAPABILITY_AUDIT.md`, `docs/PHASE_B_VPS_DEPLOYMENT_RUNBOOK.md`.
- Scale: ~60k LOC in `arbicore/`, 234 test files.

## 1. Headline finding (credit-relevant)
**Almost the entire roadmap already exists as built + tested code.** The only GENUINELY
ABSENT capability across ALL six branches is **V3 on-chain state ingestion** (V3 WSS
Swap/Mint/Burn decode + `slot0()`/`liquidity()` bootstrap + `sqrtPriceX96→sqrt_p` conversion) —
git-grep for `slot0(`, `Swap(address,address,int256`, `sqrtx96_to`, `decode_swap` = **0 matches on every branch**.
Everything else (registry consumers, TVL, price, gates, broadcaster, mode ladder, kill switch,
certification, auto-executor) is present; the work is **composition/wiring + operator provisioning**,
not new modules. This matches `LIMITED_LIVE_FLASH_LOAN_READINESS_AUDIT.md` ("off-chain software
~100%; remaining = deploy + operator + live-data proof").

## 2. THE single incomplete composition point
`server.py:6986` → `arbicore/searcher/runtime.py::maybe_build_base_searcher()` returns
`BaseSearcherRuntime(cache=PoolStateCache(), graph=RouteGraph())` — **empty graph** (no
`add_pool` → `enumerate_cycles` yields nothing) and **`tvl_provider=None`** (`_route_min_tvl`
returns None → Gate 8 fails closed). The WSS manager wrapping it (`wss_ingest.T2WssManager`
→ `live_base.BaseWssSubscriber`) decodes only V2 `Sync`. This ONE factory + the WSS decoder are
where M1/M2/M3 land. Note: the *FlashLoanArbitrageScanner* path (`composition.py` via
`build_pool_graph`) is a SEPARATE, working path already producing real quotes — the two must be
consolidated onto the canonical registry (brief A4).

## 3. Feature inventory (roadmap capability → existing asset → verdict)
| Capability | Current impl | Location | Branch | Status | Verdict | Tests | Prod relevance |
|---|---|---|---|---|---|---|---|
| Canonical Base pool registry (real addrs) | `base_pool_registry.py` (M1, this work) | `arbicore/discovery/` | current | DONE | NEW (no registry existed in any branch — verified) | `test_m1_base_pool_registry.py` (20) | HIGH |
| Synthetic pool graph (existing consumers) | `build_pool_graph()` | `discovery/base_venues.py` | all | working | CONSOLIDATE onto registry (canonical_id-aligned) | via scanner tests | HIGH |
| Live UniV3/Aero quoter (canonical) | `QuoterRegistry` | `execution/quoter.py` | all | complete | REUSE (Base QuoterV2 `0x3d4e44Eb…`) | scanner/econ tests | HIGH |
| Provider-seam V3 quoter (health/probe) | `UniswapV3Quoter` (`get_pool` = placeholder) | `providers/dex.py` | all | complete | KEEP (diff purpose); M1 registry supplies its missing real address | provider tests | MED |
| V3 AMM math (sqrt_p) | `amm_math.py` | `searcher/` | all | complete | REUSE | `test_t2_*` | HIGH |
| Pool state cache (V2/V3/stable + staleness) | `PoolStateCache` | `searcher/pool_cache.py` | all | complete | REUSE | `test_t2_*` | HIGH |
| **V3 WSS decode (Swap/Mint/Burn/Initialize)** | — | — | none | **ABSENT** | **NEW (M2)** — extend `BaseWssSubscriber` | to add | HIGH |
| **V3 initial state (`slot0`/`liquidity`)** | — | — | none | **ABSENT** | **NEW (M2)** — reuse `providers/dex` eth_call pattern | to add | HIGH |
| **`sqrtPriceX96→sqrt_p` conversion** | — | — | none | **ABSENT** | **NEW (M2)** — small util + tests | to add | HIGH |
| WSS lifecycle (reconnect/telemetry) | `T2WssManager` | `searcher/wss_ingest.py` | current | complete | REUSE (no change) | `test_t2_wss_ingest` | HIGH |
| TVL provider (on-chain reserves, fail-closed) | `OnChainReserveTVLProvider` + `make_base_reserves/price_fn` | `scanners/flash_loan_arbitrage/tvl_provider.py`, `searcher/live_base.py` | all | complete (V2 reserves) | REFINE (V3-aware reserves) + INTEGRATE (M3) | gate tests | HIGH |
| Price source (fail-closed) | `CoinGeckoTickerSource` + native price | `providers/`, config | all | complete | REUSE + wire into TVL (M3) | provider tests | HIGH |
| Gate 7 ($25 atomic) / Gate 8 (TVL) / Gate 9 (MEV) | `filter.py` (fail-closed) | `scanners/flash_loan_arbitrage/` | all | complete | REUSE (immutable) | `test_d5_1_gates`, `test_d6_1_*` | HIGH |
| Readiness + mode ladder (hard-gated) | `readiness.py`, `execution/mode.py` | `control/`, `execution/` | all | complete | REUSE | `test_control_readiness` | HIGH |
| 6-gate broadcaster (sole `eth_sendRawTransaction`) | `LimitedLiveBroadcaster` | `execution/broadcast.py` | all | complete | REUSE (M5) | broadcast tests | HIGH |
| Kill switch / capital policy / wallet+secret vault | multiple | `execution/`, `safety/`, `secrets/` | all | complete | REUSE (M5) | safety tests | HIGH |
| Calldata encoders (Balancer/Aave/executor userData) | `calldata.py` | `execution/` | all | complete | REUSE | `test_v2117_aave_v3_calldata` | HIGH |
| Fork simulation (Anvil REVM, v1.7.1) | `revm_backend.py`, `simulation.py` | `searcher/` | all | complete | REUSE (M4, VPS) | sim tests | HIGH |
| Shadow certification framework | `certification/*` | `arbicore/certification/` | all | complete (PASS 54% on seed) | REUSE (M4; needs live feed) | cert tests | HIGH |
| Auto-executor (FULL_AUTOMATION loop) | `auto_executor.py` | `execution/` | all | complete | REUSE (M6) | exec tests | HIGH |
| On-chain executor `FlashLoanReceiver.sol` | built, Foundry-tested | `contracts/` | all | BUILT, NOT DEPLOYED | DEPLOY (operator, VPS) | 8/8 forge | HIGH |
| Auth (canonical users/admin, JWT) | working | `auth/`, server | all | complete | REUSE (do not touch) | auth tests | HIGH |

## 4. Duplication / competing-truth classification
| Item | Instances | Canonical | Classification | Action |
|---|---|---|---|---|
| Quote engine | `execution/quoter.py` (canonical), `providers/dex.py::UniswapV3Quoter` (provider seam), `scanners/dex_arbitrage/quoter.py` | `execution/quoter.py` | quoter.py=KEEP; dex.py=KEEP (different role, same Base addr — consistent); dex_arbitrage/quoter.py=**REMOVE AFTER VERIFICATION** (0 importers found; confirm no dynamic load) | verify then prune |
| Pool identity | `base_venues.build_pool_graph` (synthetic) + `base_pool_registry` (real) | `base_pool_registry` | **CONSOLIDATE** — registry is source of truth; base_venues remains the authored input; migrate scanner + T2 to `resolved_addresses()` | migrate in M2/M3 |
| Base searcher composition | FlashLoan path (composition.py) + T2 `BaseSearcherRuntime` (server.py:6986) | one truth via registry | **CONSOLIDATE** onto shared pool truth (brief A4) | wire in M3 |
| Pool cache | 1 (`pool_cache.py`) | — | KEEP (no duplicate) | none |
| WSS | `T2WssManager` (lifecycle) + `BaseWssSubscriber` (decode) | — | KEEP (complementary) | extend decode in M2 |
| TVL provider | `tvl_provider.py` classes + `live_base` reserve/price fns | `tvl_provider.py` | KEEP | refine V3 + wire M3 |
| `scanner/` vs `scanners/` | contracts vs concrete impls | both | KEEP (abstract seam vs implementations — NOT duplicate) | none |
| `intel/` vs `intelligence/` | entity-resolution vs confidence/scoring/validators | both | KEEP (different domains; confusing name) | optional future rename |

No code deleted in this pass — items flagged REMOVE/CONSOLIDATE are classified only, pending verification.

## 5. Decision-tree verdict per milestone (why not rebuilt)
- **M1** registry — Q1–Q4 all NO (no registry in any branch, verified) → Q5 NEW, but DERIVED from
  existing `base_venues` (no duplicated metadata). DONE.
- **M2** V3 state sync — Q1–Q3 NO (absent in all branches, verified) → Q5 NEW, minimized by REUSING
  `PoolState(kind=v3)`, `amm_math` V3, `BaseWssSubscriber` (extend decode), `T2WssManager` (unchanged),
  `providers/dex` eth_call pattern for `slot0`. New code ≈ V3 topic decoder + sqrtX96 util + slot0 bootstrap.
- **M3** TVL wiring — Q4 YES (integration problem) → INTEGRATE existing `OnChainReserveTVLProvider` +
  price fn into `maybe_build_base_searcher` and populate `RouteGraph` from registry. Minimal.
- **M4** Shadow cert — Q1 YES → REUSE `certification/*` (already PASS on seed; run on live feed, VPS).
- **M5** Limited Live — Q1 YES → REUSE `LimitedLiveBroadcaster` + mode ladder + kill switch + caps;
  remaining = executor deploy + operator provisioning (not code).
- **M6** Controlled Auto — Q1 YES → REUSE `auto_executor` + FULL_AUTOMATION ladder.

## 6. Safety invariants confirmed still enforced (unchanged)
SHADOW broadcast=false; Gate7 $25; Gate8 fail-closed; REAL-only provenance write-gate;
LIMITED_LIVE/FULL_AUTOMATION `can_activate=false`; single broadcast call-site; kill switch default-engaged.

## 7. Recommended next step (smallest correct change)
Proceed to **M2** as pure EXTENSION of existing modules (V3 decode + sqrtX96 util + slot0 bootstrap),
with offline unit tests, then M3 wiring at the single `maybe_build_base_searcher` composition point.
No new engines. Live validation (M4+) on the VPS. **Await operator go — do not auto-enable next risk level.**
