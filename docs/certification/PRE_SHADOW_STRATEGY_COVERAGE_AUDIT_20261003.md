# Pre-SHADOW Strategy Coverage Audit — 2026-10-03

- **Classification:** **SHADOW_COVERAGE_PARTIAL**
- **Checked (UTC):** `2026-10-03T16:03:05Z`
- **Container:** `arbicore-x-backend-new` · image `arbicore-x-backend:27dfab4-20261003` · `ARBICORE_GIT_SHA` `27dfab42ae6981b39628c04fd9d1b869c3f6c57b` · StartedAt `2026-10-03T12:42:03.446652725Z` · Pid `2830498` · RestartCount `0`
- **Network runtime (unchanged):** `docs/certification/SIX_NETWORK_AB_ONLY_POST_APPLY_RUNTIME_20261003.md` · revision `rev-d069f13244ba44da81f97e72f7cfce5b` · **RUNTIME_CONFIG_VERIFIED**
- **Code authority:** running image. Hashes of the scanner, route search, quote planner, composition, registries, and venue graph match git `27dfab4`. The cert workspace copy of `app/backend/arbicore/execution/quoter.py` differs from that commit and was not used.
- **SHADOW campaign:** not started. `arbicore_shadow_certifications` has **0** documents with `status=RUNNING`. The latest historical row is `PASS_INFRASTRUCTURE_ONLY` from `2026-09-16`.

Read-only. No SHADOW start, no PAPER start, no APPLY, no rollback, no config edit, no restart, no signing, no broadcast.

---

## Verdict

**SHADOW_COVERAGE_PARTIAL.** Safety controls that keep SHADOW from real execution are held, and the discovery pipeline can be audited. The strategy set that this product actually puts in SHADOW is not fully reachable on the six chains.

The only execution-mode row in `SHADOW` is `flash_loan_arbitrage` (unchanged since `2026-09-07T05:24:07Z`). Every other stored strategy is `PAPER`. The SHADOW discovery/simulation path is therefore `FlashLoanArbitrageScanner`: route search, generic-DEX 2-hop, triangular 3-leg, and Balancer V2 paired with a second venue, then a live quote, then the verifier. That scanner is instantiated with a live quote provider and its loop has started, but `enabled=false`, so each tick returns before discovery. Even if that flag were on, persisted providers are all disabled, so every discovery source returns no candidates. Route search would still return no cycles: every pool in the graph has `tvl_usd=0` and `min_pool_tvl_usd` is `100000`.

No network × family cell below is **COVERED**. Code, unit tests, and quoter adapters are not treated as coverage.

---

## What “the SHADOW pipeline” is

| Piece | Runtime fact |
|---|---|
| Strategy in `SHADOW` | `flash_loan_arbitrage` only |
| Scanner | `FlashLoanArbitrageScanner`, worker started `12:42:48Z`, `quote_provider=live`, `enabled=false`, `detection_only=true` |
| Sources registered in that scanner | `flash_loan_route_search`, `flash_loan_provider_health` (no candidates), `flash_loan_generic_dex`, `flash_loan_triangular`, `flash_loan_balancer_v2` |
| Active chains after boot config is deep-merged with Mongo `arbicore_scanner_config.flash_loan_arb` | ethereum, arbitrum, base, optimism, polygon **enabled**. **bnb is absent** from the persisted document and stays **enabled false** from the boot default |
| Providers | `aave_v3`, `balancer_v2`, `uniswap_v3` all **enabled false** |
| Discovery-source toggles | key absent in Mongo; code default is enabled. Irrelevant while providers are off: sources return `[]` |
| Route search | `max_hops=4`, `candidate_cap=64`, `wall_clock_cap_s=5`, `min_pool_tvl_usd=100000` |
| Gate 7 / Gate 8 floors | atomic profit `$25`, route TVL `$100000` |
| Exact-size borrow sizer | `ARBICORE_BORROW_SIZER_ENABLED` absent. Quotes that do run are probe-sized and the verifier denies `DENIED_SIZE_NOT_QUOTED` **before** profit, gas, and Gates 7–9 |
| Pipeline simulation sink | `shadow_route=false` (`ARBICORE_FLASH_LOAN_SHADOW_ROUTE` absent). Confirmed opportunities are not handed to `OpportunityPipeline` |
| Base universe at activation | `pool_universe_size=30`, UniV3 liquidity eligibility `checked=19 eligible=3 excluded=16`, Aerodrome resolved `11`, TVL provider `onchain_reserves` **scoped to Base** |
| Not this pipeline | `dex_arb`, `cex_arb`, `cross_chain_arb`, `funding_arb`, `launch_arb` scanner state **enabled false**. `ARBICORE_RUNTIME_AUTOSTART=false`, so those scanners were not started. Wave 1B shadow adapters do not run live discovery and were not started |

`ShadowCertificationRunner` and `PaperValidationRunner` were already looping at container start (`ARBICORE_SHADOW_CERT_ENABLED=true`, `ARBICORE_PAPER_VALIDATION_ENABLED=true`). Neither is a SHADOW campaign. `ARBICORE_SHADOW_CERT_AUTOSTART_RUN` is absent. This audit did not start either runner.

---

## Shared gates (every route family)

| Question | Result on this runtime |
|---|---|
| Implemented in the flash-loan scanner? | See the family sections. Presence of a class is not coverage |
| Registered? | The five sources above are built by `build_all_flash_loan_sources` inside the canonical scanner |
| Enabled? | Scanner state `enabled=false`. All three flash providers `enabled=false`. Five chains enabled, BNB not |
| Reachable by a SHADOW tick today? | **No.** `_tick` returns immediately when `is_enabled()` is false |
| Would discovery emit if only the scanner flag were flipped? | **No.** Empty provider list returns no candidates |
| Would route search emit if providers were also enabled? | **No** at the configured TVL floor. Offline enumeration on the image, same `min_pool_tvl_usd=100000`, returned **0 cycles on all six chains** |
| Opportunity discovery wired? | Sources are wired. Current config and the TVL filter produce an empty candidate set |
| Route/path generation wired? | `RouteSearchEngine` DFS, hop cap 4, 64 cycles per borrow token, 5s cap. Triangular uses `enumerate_cycles` and picks the alphabetically first pool per leg. Generation does not survive the TVL filter |
| Profitability calculation wired? | `FlashLoanEconomicsAssessor` exists and is called only after an exact-size quote. Probe quotes are denied first. Sizer is off, and it is Base-scoped when on |
| Gas costs considered? | Static USD table (ETH `$8`, BNB `$0.40`, Arbitrum `$0.30`, Base `$0.15`, Optimism `$0.15`, Polygon `$0.05`), scaled by quoted gas units / `250000` when economics runs. Not a live `eth_gasPrice` feed. Not reached while quotes are probe-sized |
| Slippage considered? | A successful quoter result already includes price impact. The economics leg `slippage_pct` defaults to `0`. A 30 bps minimum-output is applied only inside the SHADOW sink, which is unwired. Persisted execution settings `slippage_bps=8` is a different surface and is not this scanner’s hop model |
| Liquidity / depth considered? | Discovery drops any pool under `$100000` TVL, and the graph stores `tvl_usd=0`, so the drop is total. Gate 8 fails closed when measured route TVL is `<= 0`. The on-chain TVL provider is Base-only; any other chain skips it on purpose |
| Opportunity simulated? | The quoter is an `eth_call` quote, and it is not being asked for candidates. `OpportunityPipeline` simulation runs only from the unwired SHADOW sink, and only after a confirmed exact-size quote |
| Blocked from real execution during SHADOW? | **Yes.** See safety |
| Test / evidence that this runtime path works? | **No live evidence on this process.** Unit tests construct fixtures with providers enabled and pools that pass TVL. They do not show this config emitting a simulated opportunity |

---

## NETWORK × STRATEGY-FAMILY

Cell values are only `COVERED`, `PARTIAL`, `NOT_WIRED`, or `UNKNOWN`.

`PARTIAL` means the SHADOW scanner has a real source or venue for that shape on that chain, and a measured gate stops a complete discover → quote → economics → simulate path.

`NOT_WIRED` means that shape is not emitted into this SHADOW scanner for that chain.

`COVERED` would require the path to be reachable on that chain through this pipeline under the current runtime. None are.

| Family | ETH | ARB | BASE | OP | POLYGON | BNB |
|---|---|---|---|---|---|---|
| DEX→DEX | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL |
| Multi-hop | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL |
| Triangular | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL |
| Multi-DEX | PARTIAL | PARTIAL | PARTIAL | NOT_WIRED | PARTIAL | PARTIAL |
| Cross-pool | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL |
| Cross-protocol | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL |
| Balancer V2 discovery | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | NOT_WIRED |
| Aerodrome | NOT_WIRED | NOT_WIRED | PARTIAL | NOT_WIRED | NOT_WIRED | NOT_WIRED |
| Sushi / Camelot / QuickSwap / Pancake | PARTIAL | PARTIAL | NOT_WIRED | NOT_WIRED | PARTIAL | PARTIAL |
| Curve | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED |
| Velodrome | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED |
| Morpho Blue flash | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED |
| Stablecoin (dedicated) | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED |
| LST/LRT (dedicated) | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED |
| Cross-chain scanner | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED |
| Capital DEX scanner | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED | NOT_WIRED |

The intended SHADOW subset is the first six rows plus Balancer V2, inside `flash_loan_arbitrage`. That subset is not fully `COVERED` on all six chains, so the classification stays **PARTIAL**.

---

## Family notes

### DEX→DEX

`GenericDexDiscoverySource` keeps 2-hop cycles that use two DEX names or two pool ids. It is registered. It calls `RouteSearchEngine.search`, which currently returns nothing because of the TVL floor.

If that floor were 0, the 64-cycle cap still returns only a handful of 2-hop cycles, and the quote planner (`_plan_generic_evm`) accepts only `uniswap_v3` and `balancer_v2`. Counted on the image with the floor forced to 0: ethereum 5 two-hop (1 cross-DEX, 4 planner-ok), arbitrum 7 (3 cross-DEX, 4 planner-ok), base 14 (0 cross-DEX, 14 same-DEX UniV3 planner-ok), optimism 4 (0 cross-DEX, 4 planner-ok), polygon 5 (1 cross-DEX, 4 planner-ok), bnb 6 (2 cross-DEX, **0 planner-ok**). Those counts are not what this runtime emits.

Base cross-DEX against Aerodrome is not quoted on this source: generic DEX always attaches `route_hops`, and the planner rejects Aerodrome. The Base-only `_plan_base` path, which can quote Aerodrome, is used when `route_hops` is absent (route-search on Base). That path is also empty under the TVL floor.

Optimism has no second DEX in the probe graph, so its 2-hop surface is UniV3 fee tiers (cross-pool), not two protocols.

### Multi-hop

There is no separate multi-hop source. `RouteSearchEngine` can close cycles of 2, 3, or 4 hops (`max_hops=4`). `strategy_tagging.classify_strategy` would call `>3` legs `MULTI_HOP`, but the verifier never calls that classifier. The hint is only the hop count on the candidate.

With the configured floor, multi-hop emission is zero on every chain. With the floor at 0, the cap fills mostly with 4-hop cycles (ethereum 230, arbitrum 237, base 71, optimism 230, polygon 236, bnb 294, summed across borrow tokens, each borrow capped at 64). Any hop whose DEX is not UniV3 or Balancer fails the planner, so a 4-hop that touches Sushi, Camelot, QuickSwap, or Pancake does not quote. Optimism and a UniV3-only Base graph could quote; the live Base graph also contains resolved Aerodrome, and route-search on Base does not attach `route_hops`, so Aerodrome would be quoted only on that Base path, which the TVL floor currently blocks.

### Triangular

`TriangularDiscoverySource` does **not** use the TVL filter and does **not** call `discover_triangular`. It enumerates `A→B→C→A` over a fixed borrow set (`USDC`, `USDT`, `WETH`, `DAI`) and intermediate set, and keeps the alphabetically first pool per leg. Economics stay in the verifier, which does not run them for probe quotes.

Offline cycle counts and the DEX that the picker actually chose:

| Chain | Cycles | Planner would accept | First-pool DEX |
|---|---:|---:|---|
| ethereum | 48 | 0 | `sushiswap_v2` on every leg |
| arbitrum | 80 | 0 | `camelot_v3` on every leg |
| base, UniV3-only graph | 12 | 12 | `uniswap_v3` |
| base, Aerodrome included (live activation resolved 11) | 12 | 0 | every cycle touches Aerodrome |
| optimism | 80 | 80 | `uniswap_v3` |
| polygon | 48 | 0 | `quickswap_v3` |
| bnb | 24 | 0 | `pancakeswap_v3` |

Optimism is the only chain whose triangular cycles are structurally planner-ok against the current graph. They are still not covered: BNB aside, the chain is enabled, but providers are off, the scanner is off, a quote would be probe-sized and denied before profit, and Gate 8 has no Optimism TVL provider. Base’s live universe is the Aerodrome-inclusive one, so its triangular cycles are not planner-ok. This audit did not re-read which 3 of 19 Base UniV3 pools passed `liquidity()`.

`triangular.py`’s own quote-and-profit function is a library. The scanner does not call it.

### Multi-DEX / multi-route

Multi-route exists as many cycles in one search, capped at 64 per borrow token, not as a best-route selector.

Multi-DEX (two protocols in one cycle) is in the graph on ethereum (UniV3 + Sushi V2), arbitrum (UniV3 + Sushi V3 + Camelot), base (UniV3 + Aerodrome, once resolved), polygon (UniV3 + QuickSwap), and bnb (UniV3 + Pancake). The activation planner drops the non-UniV3 hop. Optimism’s probe graph is UniV3 only, so multi-DEX is **NOT_WIRED** there.

### Cross-pool

Same-pair, different pool or fee tier is a 2-hop the generic-DEX filter accepts. UniV3 fee tiers in the graph are 500 and 3000 ppm (Base curated venues also include other tiers). All of those pools have `tvl_usd=0`, so none pass the configured floor. Same-DEX 2-hops seen only when the floor is forced to 0: ethereum 4, arbitrum 4, base 14, optimism 4, polygon 4, bnb 5. BNB’s were not planner-ok (Pancake sorts first).

### Cross-protocol

Two mechanisms:

1. `BalancerV2DiscoverySource` pairs a Balancer pool with one non-Balancer pool from the graph. Vaults exist for ethereum, base, arbitrum, optimism, and polygon. **BNB has no vault; the source skips it (NOT_WIRED).** Subgraph URLs were not in the process environment at start. On-chain `PoolRegistered` logs are fail-closed when `eth_getLogs` is missing or errors. No complementary pool is fabricated. This runtime has not been shown to emit a Balancer candidate.
2. UniV3 versus Sushi, Camelot, QuickSwap, Pancake, or Aerodrome. Those pairs can appear in the graph. The planner rejects every hop that is not `uniswap_v3` or `balancer_v2`, so the quote does not run.

### Other families that exist in this repository

| Family | Where it lives | SHADOW scanner |
|---|---|---|
| Balancer V2 discovery | `flash_loan_balancer_v2` | Registered. See row. Not emitting |
| Aerodrome / Slipstream | Base venue list and Base quoters. Live activation resolved 11 pools | Not a discovery source. Generic-DEX planner rejects the hop. Route-search Base path could quote it only after the TVL floor stops discarding `tvl_usd=0` |
| Sushi V3 | Arbitrum graph + quoter address | In the graph. Planner rejects it |
| Sushi V2 | Ethereum graph + router quoter | In the graph. Planner rejects it. Alphabetical first, so it captures every ethereum triangular leg |
| Camelot V3 | Arbitrum graph + Algebra quoter | In the graph. Planner rejects it. Alphabetical first, so it captures every arbitrum triangular leg |
| QuickSwap V3 | Polygon graph + Algebra quoter | Same pattern as Camelot |
| Pancake V3 | BNB graph + quoter address | Same pattern. BNB chain flag is also false |
| Curve | Ethereum registry factory only. ABI family `curve` is excluded from `multichain_venues` | **NOT_WIRED** |
| Velodrome V2 | Optimism registry factory only. ABI family `solidly` is excluded from the probe graph. No Velodrome quoter in `QuoterRegistry` | **NOT_WIRED** |
| Morpho Blue | Fee catalog for ethereum and base only. Not a key under `scanner_config.flash_loan_arb.providers` | **NOT_WIRED** |
| UniV3 flash and Aave V3 / Balancer V2 flash heads | Provider catalog. Aave lists all six chains. Balancer V2 and UniV3 flash list five and omit BNB | Config keys exist for Aave, Balancer, and UniV3 and are **disabled**. They are funding heads, not route families. No head is active |
| Stablecoin, LST/LRT | `classify_strategy` only | Verifier does not call it. No discovery source. **NOT_WIRED** |
| Cross-chain arbitrage | Own scanner | Mode `PAPER`, state `enabled=false`, runtime autostart off. **NOT_WIRED** into SHADOW |
| Capital / DEX arbitrage scanner | Own scanner, DexScreener hint | Mode `PAPER` (`dex_capital_arbitrage`), state `enabled=false`. **NOT_WIRED** into SHADOW |
| CEX, funding, launch | Own scanners | Not `SHADOW`. State disabled. Not started |

Quoter adapters that exist and are still not reached by the SHADOW planner: Sushi V3 (arbitrum), Pancake V3 (bnb), Sushi V2 (ethereum), Camelot (arbitrum), QuickSwap (polygon), Aerodrome classic and Slipstream (base), Balancer V2 (when an explicit pool id is present). UniV3 QuoterV2 addresses exist for all six chains. A chain with no adapter fails closed inside the quoter; the planner fails closed earlier for non-UniV3 hops.

---

## Network-specific limits

| Chain | In active scanner config | DEX identities in the SHADOW graph | Not in the graph | Quote limit on the SHADOW planner | Other |
|---|---|---|---|---|---|
| Ethereum | enabled | UniV3, Sushi V2. 45 venues, all TVL 0 | Curve factory is registered only | Sushi V2 rejected. UniV3 can be planned | Balancer vault present. Subgraph/getLogs not shown live. Gate 8 TVL is not this chain’s provider |
| Arbitrum | enabled | UniV3, Sushi V3, Camelot. 140 venues, TVL 0 | — | Sushi V3 and Camelot rejected | Same Balancer and Gate 8 limits. Camelot wins every triangular leg |
| Base | enabled | Canonical registry: 19 UniV3 with addresses. Live process also resolved 11 Aerodrome/Slipstream. All TVL 0. 16 of 19 UniV3 excluded by `liquidity()` | Curated list has no Sushi/Camelot/Pancake | Activation `route_hops` reject Aerodrome. `_plan_base` can quote Aerodrome only when `route_hops` is absent | Only chain with an on-chain TVL provider and a USD price feed in this wiring. Exact-size sizer is off, so Gate 8 is still not reached. 3 UniV3 pools had positive liquidity at startup; the other 16 stay out of the route universe |
| Optimism | enabled | UniV3 only. 56 venues, TVL 0 | Velodrome factory registered, `solidly` ABI not built into the graph, no quoter | UniV3 only, and that part can be planned | Structurally the cleanest triangular graph. Still probe-denied and Gate 8 fail-closed |
| Polygon | enabled | UniV3, QuickSwap V3. 63 venues, TVL 0 | — | QuickSwap rejected | QuickSwap wins every triangular leg |
| BNB | **not enabled** (missing from persisted chains) | Pancake V3, UniV3. 60 venues, TVL 0, built by code when an RPC exists | No Balancer vault | Pancake rejected. The 2-hop sample was 0-for-6 planner-ok. Pancake wins every triangular leg | Aave catalog includes BNB. Balancer flash and UniV3 flash catalogs do not. Chain is outside the merged enable set, so sources do not iterate it |

Route generation limits on every chain: hop cap 4, 64 cycles per borrow token, 5 second wall clock, borrow tokens `USDC`/`USDT`/`WETH`/`DAI` (BNB’s `WBNB` is not in that borrow set). Triangular intermediates add `WBTC`, `ARB`, `OP` only when the symbol is actually in that chain’s pool graph.

Simulation limit: non-Base routes need `eth_call` from that chain’s registry RPC. The live process has Alchemy A/B for all six (`RUNTIME_CONFIG_VERIFIED`). A missing RPC fails the plan closed. This audit did not send quotes.

---

## Safety (current runtime, read-only)

| Control | Observed |
|---|---|
| No transaction signing | Discovery and the quote path are `eth_call` / `eth_getLogs` only. The unsigned-calldata helper in the verifier is not on the path that is running. No `eth_sendRawTransaction` in logs since `12:42Z` |
| No broadcast | `OpportunityPipeline` broadcasts only in `LIMITED_LIVE` or `FULL_LIVE`, and only with a broadcaster. The SHADOW sink builds the pipeline with **no** broadcaster and **no** mode repo, so mode resolves to `SHADOW` and the pipeline returns at `SHADOW_RECORDED`. That sink is **not wired** (`shadow_route=false`) |
| No wallet execution | No broadcast, no signer on this path. Scanner activation log: `detection_only=true` |
| No live execution | `flash_loan_arbitrage` mode is `SHADOW`. No mode row is `LIMITED_LIVE` or `FULL_LIVE`. `updated_at` still `2026-09-07` |
| No LIMITED_LIVE activation | Distinct modes in `execution_mode_state`: `PAPER`, `SHADOW` only |
| No autoexec | `ARBICORE_AUTOEXEC_AUTOSTART=false`. Persisted `execution_settings.auto_execute_enabled=false`, revision `rev-35aaafa0454f4a2d8c9aa7b750a2c803`, `updated_by=system:boot` at `2026-09-07T05:24:08Z` |
| No runtime autostart | `ARBICORE_RUNTIME_AUTOSTART=false`. Boot log: `arbicore_runtime autostart disabled`. Per-scanner `ARBICORE_SCANNER_FLASH_LOAN_ARB` is absent (default off). `ARBICORE_SCANNER_DEX_ARB=false`, `CEX=false`, `FUNDING=false`, `LAUNCH=false` |
| Kill switch | Same process as the runtime verification. That check recorded in-memory kill `engaged=true`, reason `boot_default`, `effective_kill_engaged=true`. This audit did not disengage it and did not restart the process |
| SHADOW campaign | Not started. Certification runner ticks every 60s with no RUNNING run. `ARBICORE_SHADOW_CERT_AUTOSTART_RUN` absent |

`PaperValidationRunner started` at `12:42:21Z` because the container already had `ARBICORE_PAPER_VALIDATION_ENABLED=true`. This audit did not start PAPER and did not change execution mode.

---

## Evidence this audit actually ran

Offline, inside the image, no RPC quote and no scanner start:

- Mongo `flash_loan_arb` chains, providers, route-search floor, and scanner state
- `execution_mode_state` and `execution_settings.auto_execute_enabled`
- `arbicore_shadow_certifications` running count
- Pool-graph sizes, DEX mix, and `RouteSearchEngine.search` at `min_pool_tvl_usd` `100000` and `0`
- Triangular first-pool DEX selection, including Base with Aerodrome venues present
- File hashes of the image against git `27dfab4`

Live process, read-only:

- Pid `2830498` unchanged, RestartCount `0`
- Boot log line at `12:42:48Z` for scanner readiness (`enabled=false`, `shadow_route=false`, Base eligibility and Aerodrome counts)
- Logs since `12:42Z` contain no `shadow/start`, no `eth_sendRawTransaction`, no `LIMITED_LIVE`

Tests that prove fixture behavior, not this runtime:

- `app/backend/tests/test_m5_canonical_activation.py` — sources register and can emit when the test enables chains and providers and supplies pools
- `app/backend/tests/test_d6_1_route_search.py` — search respects a `$100000` TVL floor when fixtures have TVL
- `app/backend/tests/test_flash_route_to_quote_pipeline.py` — `tvl_usd=0` pools are searchable only if the floor is `0`
- `app/backend/tests/test_m2_4_shadow_route.py` — when the sink is invoked, the pipeline records SHADOW and does not broadcast

None of those tests is a six-chain SHADOW run on pid `2830498`.

---

## Final classification

**SHADOW_COVERAGE_PARTIAL**

Safety is held, and the pipeline was auditable, so this is not **SHADOW_COVERAGE_BLOCKED**. The intended SHADOW discovery set is not actually reachable on all six chains, so this is not **SHADOW_COVERAGE_READY**.

**STOP.** Do not start SHADOW.
