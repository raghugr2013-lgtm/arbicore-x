# ArbiCore X — Post-G5.130 Engineering Audit

Read-only audit. Tags: **IMPLEMENTED · PARTIAL · SCAFFOLD · UNVERIFIED · BLOCKED · CERTIFIED**.
Checkout: `/app` = `main`@`621faea` (v2.9.2) + isolated dev work SP-1/2/3/4.
Access caveat: the G5.79/G5.130 worktree (`3ddde0d`) and production/VPS are NOT in this
environment — G5.130 statements are contract/mechanism-level, verified against the code here.

---

## 1. Executive Summary
The flash-loan architecture is genuinely fail-closed and, in its **pure/offline layers**,
chain-generic across all six chains (route search, economics math, gas models, provider
selection, strategy classification, gates, evidence). **Only Base** is runtime-wired
end-to-end (DISCOVER→QUOTE→LIQUIDITY→ECONOMICS→…→EVIDENCE). SP-1/2/3/4 advanced the five
non-Base chains from "discover-only" to "address-aware + feedable quote path (SP-1/3) +
read-only registry (SP-2) + chain-aware fail-closed TVL read path (SP-4)". **The single
first broken seam for a real non-Base opportunity is on-chain POOL-ADDRESS RESOLUTION**
(produces real pool addresses for quotes and `pool_meta` for TVL). Execution/sign/broadcast
remain intentionally OFF (SHADOW). No production readiness is claimed anywhere.

## 2. Current Architecture
DI graph in `runtime/composition.py` wires the canonical `FlashLoanArbitrageScanner`
(SHADOW/DORMANT) with a Base live quote provider + Base TVL provider + per-chain gas models.
Pipeline stages are discrete modules under `scanners/flash_loan_arbitrage/*`,
`searcher/*`, `execution/*`, `chains/*`, `discovery/*`, `certification/*`, `learning/*`.

## 3. G5.130 Assessment  — **PARTIAL (in worktree) / ABSENT (here)**
- Seam intent: canonical `ARBICORE_RPC_URL_<CHAIN>` → `PROVIDER_RPC_URL_<CHAIN>` via the
  existing bridge `sync_provider_registry_rpc_from_env()`, invoked from
  `env_sync.sync_env_from_network_config()`.
- **In `/app`:** bridge absent (grep = 0), `env_sync` is the pre-G5.130 shim → seam **NOT**
  closed here (cannot demo the fix).
- **In the worktree (per handoff):** design is correct — writes only single keys, no
  fabricated plural `PROVIDER_RPC_URLS_<CHAIN>`, preserves explicit precedence + Base
  isolation; this is what clears `no_operator_configured_rpc`.
- Chain: canonical RPC → env sync → provider registry (`providers/bootstrap._rpc_urls`)
  → runtime (`RpcFailover`) → quote consumers (`execution/quoter` reads
  `PROVIDER_RPC_URL[S]_<CHAIN>`) → liquidity/economics consumers. The bridge closes the
  **env→registry** link; **no additional lifecycle seam is required** for the env path.
  Runtime confirmation is a Codex/VPS step.
- **No further G5.130 code change needed** from what is described.

## 4. Six-Chain Coverage Matrix (runtime capability)
| Chain | Discover | Quote | Liquidity | Economics(math) | End-to-end |
|---|---|---|---|---|---|
| Base | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | **IMPLEMENTED** (to EVIDENCE; not economically evidenced at runtime) |
| Ethereum | IMPLEMENTED | PARTIAL (SP-1 addr + SP-3 feed) | PARTIAL (SP-4 read path, needs pool_meta) | IMPLEMENTED | **BLOCKED** on pool resolution |
| Arbitrum | IMPLEMENTED | PARTIAL | PARTIAL | IMPLEMENTED | BLOCKED |
| Optimism | IMPLEMENTED | PARTIAL | PARTIAL | IMPLEMENTED | BLOCKED |
| Polygon | IMPLEMENTED | PARTIAL | PARTIAL | IMPLEMENTED | BLOCKED |
| BNB | IMPLEMENTED | PARTIAL | PARTIAL | IMPLEMENTED | BLOCKED |
All non-Base = **UNVERIFIED at runtime** (no live eth_call proof; Codex/VPS required).

## 5. Flash-Loan Provider Matrix (vs intended coverage)
| Provider | Intended chains | Repo status |
|---|---|---|
| Aave V3 | ETH/ARB/BASE/OP/POL/BNB | **PARTIAL/config-only** — fee+selection logic implemented & unit-tested; no runtime provider call/executor any chain |
| Balancer V2 | ETH/ARB/BASE/OP/POL | **PARTIAL/config-only** — 0-bps fee handled; no runtime verification |
| Uniswap V3 flash | ETH/ARB/BASE/OP/POL | **PARTIAL** — only provider whose QUOTE adapter exists (SP-1); flash-execution path not runtime-verified |
| Morpho Blue | ETH/BASE | **SCAFFOLD/config-only** — singleton/selector/0-fee constants present; no runtime executor |
No provider is **execution-capable** or **CERTIFIED** on any chain. Catalog ≠ runtime.

## 6. Strategy / Route Matrix
| Family | Impl | Discoverable | Quotable | Liq-checkable | Econ-valid | Sim | Exec |
|---|---|---|---|---|---|---|---|
| GENERIC_DEX | IMPLEMENTED | 6 | Base(+non-Base pending pools) | Base(+SP-4 pending pool_meta) | Base | Base(gated) | OFF |
| TRIANGULAR | IMPLEMENTED (dedicated discovery) | 6 | as above | as above | Base | gated | OFF |
| STABLECOIN | IMPLEMENTED (classification) | 6 | as above | as above | Base | gated | OFF |
| MULTI_HOP | IMPLEMENTED (classification) | 6 | as above | as above | Base | gated | OFF |
| LST_LRT | IMPLEMENTED (classification) | 6 | as above | as above | Base | gated | OFF |
Families are runtime-proven only on Base. Non-Base = BLOCKED on pool resolution.

## 7. Core Pipeline Audit
| Stage | Module | Impl | Tests | Runtime dep | Blocker | Cert |
|---|---|---|---|---|---|---|
| DISCOVER | discovery/multichain_venues, route_search | IMPLEMENTED | phase2 discovery/liquidity | none | none | n/a |
| QUOTE | execution/quoter, flash…/live_quote_provider | Base IMPL / non-Base PARTIAL | sp1,sp3,m2_1,phase10_10_8 | per-chain RPC + real pools | non-Base pools | Base only |
| LIQUIDITY | searcher/runtime(build_*_tvl), flash…/tvl_provider | Base IMPL / non-Base PARTIAL | sp4,d6_1 | RPC + pool_meta + price | pool_meta (resolution) | Base only |
| ECONOMICS | flash…/economics, multichain_economics, chains/gas_model | IMPLEMENTED (all 6, math) | phase2_multichain, d6_1 | quotes+TVL inputs | inputs off-Base | n/a |
| PROFIT GATE | flash…/filter | IMPLEMENTED ($25/etc) | gate tests | none | none | n/a |
| ROUTE | flash…/route_search | IMPLEMENTED (caps==thresholds) | route tests | none | exec-proof Base | n/a |
| SIMULATION | execution/atomic_executor_sim, settlement_simulator | Base IMPL, BLOCKED(no signer) | sim tests | signer auth | safety gate (F) | n/a |
| EXECUTION | execution/auto_executor | SCAFFOLD/gated | — | signer+mode | intentional OFF | — |
| SIGN | execution/live_signer, signer_vault | present, OFF | — | operator auth | intentional OFF | — |
| BROADCAST | execution/broadcast | present, OFF | — | signer | intentional OFF | — |
| RECEIPT/REPAY | execution/* | SCAFFOLD | — | broadcast | downstream of exec | — |
| RECONCILIATION | paper/outcomes | IMPLEMENTED (paper) | paper tests | evidence | no accumulated evidence | — |
| EVIDENCE | flash…/verifier, evidence/bundle, data/provenance | IMPLEMENTED | audit/provenance tests | quotes | non-Base source-ids unregistered | n/a |

## 8. Real Opportunity Path Audit (single hypothetical, traced)
Base: DISCOVER→real pool (base_pool_registry)→real liquidity (build_base_tvl_provider)→
real quote (QuoterV2 eth_call)→gas (BaseGasModel)→flash fee→DEX fees→slippage→MEV→net→
profit gate→route→simulation(gated)→evidence — **runs end-to-end today (SHADOW)**, but no
runtime economic evidence is accumulated in this environment (UNVERIFIED economically).
Non-Base (e.g. Arbitrum WETH/USDC): DISCOVER ✓ → **FIRST BROKEN SEAM = pool-address
resolution**: `live_quote_provider` needs a real pool per hop and SP-4 needs `pool_meta`;
SP-2 exposes candidate venues with `pool_contract_address=None`. Without resolution, QUOTE
falls back and TVL fails closed → no economics. **This is the highest-priority blocker.**

## 9. Economic Gate Audit — **IMPLEMENTED, unchanged**
$25 atomic / $35 cert / $100k TVL / conf 60 / MEV MEDIUM / 4 hops / 5s / cap 64
(`filter.py`, `route_search.py`, `certification/thresholds.py`). No SP-1..4 change touched
them (verified). Do not weaken.

## 10. Paper Validation Readiness — **BLOCKED**
Engine/runner/evidence present (IMPLEMENTED); zero accumulated bundles. Requires ≥1
runtime-verified chain producing real economics → needs pool resolution + Codex live proof.

## 11. Tier-5 24h Readiness — **BLOCKED** (depends on §10 + sustained SHADOW run evidence).
## 12. Tier-5 72h Readiness — **BLOCKED** (depends on §11).
## 13. Limited Live Readiness — **BLOCKED / hard-RED** (readiness gate + no signer; §10–12 + explicit human authorization).

## 14. Test / Coverage Audit
- SP-1 (7), SP-2 (11), SP-3 (7), SP-4 (31): **passing**.
- Base/multichain/quoter/economics/Gate-8 regression (this session): **202 passed, 0 failed**.
- `test_phase10_10_env_sync.py`: **4 passed here** (no bridge). `test_g5_79_multirpc_provider_sync.py`
  and `test_cert_rpc_env_contract.py`: **absent here** (worktree-only).
- Pre-existing repo-wide: ~31 collection errors — env-specific (read `/app/frontend/.env`,
  `MONGO_URL`/`REACT_APP_BACKEND_URL` at import) → classify **ENVIRONMENT-SPECIFIC**, not defects.
- No stale/duplicate SP tests; no unrelated test modified except a 1-line intent-preserving
  retarget in `test_phase10_10_8_live_quoter.py` (polygon was used as "unsupported"; SP-1 made
  it supported → retargeted to `solana`).

## 15. Known Failures (`test_empty_persistent_leaves_env_alone`, `test_idempotent`)
**Genuinely pre-existing test-isolation expectations (classification: stale isolation
assumption + cross-suite PROVIDER_* leakage), NOT a regression.** Pass here (no bridge);
fail in the worktree only once the bridge joins the lifecycle, because they assert global
`exported == {}` / raw returned-dict equality instead of the ARBICORE-namespace / os.environ
end-state. Bridge writes only single keys; plural behavior unchanged. **Do not modify to
green the count — reframe in the worktree** (autouse fixture clearing
`PROVIDER_RPC_URL[S]_<CHAIN>`/`ARBICORE_RPC_URL_<CHAIN>` + narrowed assertions).

## 16. Exact Blockers (ordered by technical dependency)
1. **On-chain pool-address resolution** (SP-5) — produces real pool addresses (quotes) +
   `pool_meta` (SP-4 TVL). First broken seam for every non-Base chain. Dev-implementable with
   mocked tests; live proof = Codex.
2. **Non-Base source-id provenance registration** (`data/provenance.py`) — else non-Base
   CONFIRMED fails closed at `derive_provenance`.
3. **Non-Base price feed** beyond native (multi-token USD) — economics inputs.
4. **Runtime verification (Codex/VPS)** of SP-1 quoter addresses + resolved pools + provider
   callability per chain.
5. **Paper-evidence accumulation** on ≥1 verified chain (still SHADOW).
6. **Provider runtime verification / executor** (Aave/Balancer/Morpho) — later, exec-gated.

## 17. Recommended Implementation Sequence (dependency-ordered, not preference)
SP-5 pool resolver → provenance source-ids (§16.2) → non-Base price feed (§16.3) → Codex
live verification of one chain (Arbitrum) → paper-evidence accumulation → provider/executor
verification. Each fail-closed, no threshold/execution change.

## 18. Files / Modules Requiring Work
- SP-5: new `discovery/multichain_pool_resolver.py` (factory `getPool` + `decimals()` reads,
  fail-closed) + thin wiring in `multichain_pool_registry` / `composition` to feed `pool_meta`
  and real quote pools. Tests with mocked eth_call.
- `data/provenance.py` (register non-Base quoter source-ids).
- `searcher/` price source generalization (multi-token, genuine feed).
- (Codex) VPS runtime verification harness.

---
**No production/VPS action. SHADOW preserved. Thresholds unchanged. No execution/sign/broadcast.**
