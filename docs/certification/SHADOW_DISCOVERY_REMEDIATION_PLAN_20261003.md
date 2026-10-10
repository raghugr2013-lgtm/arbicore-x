# SHADOW Discovery Remediation Plan — 2026-10-03

- **Classification:** **REMEDIATION_PLAN_READY**
- **Input:** `docs/certification/PRE_SHADOW_STRATEGY_COVERAGE_AUDIT_20261003.md` (`SHADOW_COVERAGE_PARTIAL`, checked `2026-10-03T16:03:05Z`)
- **Code authority:** running image `arbicore-x-backend:27dfab4-20261003`, `ARBICORE_GIT_SHA` `27dfab42ae6981b39628c04fd9d1b869c3f6c57b`, as recorded by that audit. This plan re-read the cert workspace against that commit. Scanner, route search, activation sources, quote planner, composition, registries, pool graph, and flash-loan adapters are identical to `27dfab4`. The only workspace delta in this set is an uncommitted HTTP-429 cooldown in `app/backend/arbicore/execution/quoter.py`. That delta does not add or remove quoter backends. The planner lives in `live_quote_provider.py`, which matches the image. This plan did not re-open the container.
- **Network runtime (not in scope):** revision `rev-d069f13244ba44da81f97e72f7cfce5b`, six chains, Alchemy A→B, A=`cd505118`, B=`124bc59c`, `RUNTIME_CONFIG_VERIFIED` in `docs/certification/SIX_NETWORK_AB_ONLY_POST_APPLY_RUNTIME_20261003.md`.
- **This document:** plan only. SHADOW was not started. No product code, scanner config, network config, APPLY, rollback, restart, scanner enable, or threshold change was made.

---

## Verdict

**REMEDIATION_PLAN_READY.** Every path in the coverage audit is present in the image’s code. None of the eight items requires touching the certified RPC revision, lowering `min_pool_tvl_usd`, or enabling live execution. The work is an ordered code-and-scanner-config sequence. It is not safe to flip the scanner on against the current process: the in-memory enable cache cannot observe `enabled=true`, stored pool TVL is a hard-coded placeholder, and the quote planner drops every hop that is not Uniswap V3 or Balancer V2.

---

## Non-goals

- Do not lower `route_search.min_pool_tvl_usd` or Gate 8 `min_pool_tvl_usd_in_route` (both `$100,000`). A floor of `0` is a test fixture, not a production workaround.
- Do not edit Network Config, revision `rev-d069f13244ba44da81f97e72f7cfce5b`, Alchemy A/B, public RPC, or `ce00e63d`.
- Do not APPLY, roll back, restart containers, or change executor / signer / broadcast settings.
- Do not set `execution_mode_state` to `LIMITED_LIVE` or `FULL_LIVE`. `flash_loan_arbitrage` stays `SHADOW`.
- Do not set `execution_settings.auto_execute_enabled`.
- Do not disengage the kill switch as part of discovery remediation. The scanner tick does not read it. The execution pipeline does.
- Do not start a SHADOW certification campaign (`arbicore_shadow_certifications`).
- Do not enable `dex_arb`, `cex_arb`, `cross_chain_arb`, `funding_arb`, or `launch_arb`.
- Do not wire Curve, Velodrome, Morpho Blue, or dedicated stablecoin / LST discovery into this SHADOW pass. They are not on this scanner.
- Do not widen `SUPPORTED_DEXES` / receiver profile `v1` (`uniswap_v3` only). That constant is the deployed settlement capability, not the SHADOW quote capability.

---

## Ordered plan

Do these in order. Later steps are useless until earlier gates stop returning empty.

| Step | What | Kind | Starts SHADOW ticks? |
|---|---|---|---|
| 1 | Make the flash-loan state cache copy `arbicore_scanner_state.flash_loan_arb.enabled` | Code | No, while the stored flag stays false |
| 2 | Measure real pool TVL and write it onto `PoolNode.tvl_usd` before the `$100,000` filter. Leave the floor unchanged. Unmeasured pools stay excluded | Code, read-only `eth_call` on the already-certified RPC | No |
| 3 | Teach the quote planner the DEX families that already have quoter backends, and select only those hops inside route search and triangular picking | Code | No |
| 4 | Add the missing `chains.bnb` object on the flash-loan scanner document and set it enabled. Do not replace the other chain objects. Do not touch network config | Scanner-config write, later | No, until step 6 |
| 5 | Set `providers.aave_v3`, `providers.balancer_v2`, and `providers.uniswap_v3` to `enabled: true`, and skip a provider on a chain its catalog does not list | Scanner-config write, later | No, until step 6 |
| 6 | After steps 1–5 are deployed, `POST /api/arbicore/scanners/flash_loan_arb/resume` so ticks pass `is_enabled()` | Scanner-state write, later | Yes. Detection only. This plan does not do it |
| 7 | Turn on an exact-size borrow sizer per chain, or accept that probe quotes still end at `DENIED_SIZE_NOT_QUOTED` before profit and Gates 7–9 | Code + env, later | Does not by itself start ticks |
| 8 | Optionally set `ARBICORE_FLASH_LOAN_SHADOW_ROUTE` so confirmed quotes reach `make_flash_loan_shadow_sink` (no broadcaster, mode resolves to `SHADOW`) | Env, later | Records simulation. Does not broadcast |

Steps 1–3 are the code remediation. Steps 4–8 are operator actions after that code is running. None of them is performed by this plan.

---

## 1. Flash-loan scanner `enabled=false`

### Source

| Symbol | Path |
|---|---|
| `FlashLoanArbitrageScanner.is_enabled` | `app/backend/arbicore/scanners/flash_loan_arbitrage/scanner.py` |
| `FlashLoanArbitrageScanner._tick` | same file. Returns immediately when `is_enabled()` is false |
| `FlashLoanArbitrageScanner._run` | same file. Loop is already started; interval is `config.interval_s` (boot `60`) |
| `get_flash_loan_arb_scanner` / `_refresh_caches_once` / `_BOOT_CFG` | `app/backend/arbicore/runtime/composition.py` |
| `activate_canonical_flash_loan_scanner` | same file. Calls `scanner.start()` after the live quote provider is wired |
| `_canonical_flash_loan_background_activation` | `app/backend/server.py`. Startup task calls that activator. This is why the worker is running with `enabled=false` |
| `flash_loan_resume` | `app/backend/arbicore/routes/scanners.py`. `POST /api/arbicore/scanners/flash_loan_arb/resume` |
| `ScannerStateRepository.set_enabled` / `seed_defaults` | `app/backend/arbicore/data/scanner_config_repo.py`. Collection `arbicore_scanner_state`, `_id` `flash_loan_arb` |
| `build_all_flash_loan_sources` | `app/backend/arbicore/scanners/flash_loan_arbitrage/sources.py` |

Other scanners (`get_cex_arb_scanner`, `get_dex_arb_scanner`, and the funding, launch, and cross-chain factories in the same composition module) assign `cache["state"] = await state_repo.get(...)`. The flash-loan factory does not.

### Current state

The loop is up. `activate_canonical_flash_loan_scanner` starts it even when the flag is false. Each `_tick` returns before discovery, rebuild, quote, or emit. Mongo `arbicore_scanner_state.flash_loan_arb.enabled` is false (unchanged since the coverage audit’s reading of the boot row). `execution_mode_state.flash_loan_arbitrage` is already `SHADOW`. `detection_only=true` on the activation log. `ARBICORE_RUNTIME_AUTOSTART` is false, so the env path `ARBICORE_SCANNER_FLASH_LOAN_ARB` is not what started this loop.

### Root cause

`is_enabled()` reads an in-memory cache, not Mongo on each tick. That cache is initialised to `{"enabled": False}`. `_refresh_caches_once` deep-merges **config** from Mongo, but for **state** it only writes the cache when `enabled is False` and `_operator_set` is set. `set_enabled` never writes `_operator_set`. Nothing in this factory assigns `enabled: true` into the cache. `POST .../resume` updates Mongo and calls `start()` (already running) and still leaves every tick as a no-op.

### Proposed change

In `get_flash_loan_arb_scanner._refresh_caches_once`, assign `cache["state"]` from `state_repo.get("flash_loan_arb")` the same way the other five scanners do. Keep the boot default false when the read fails. Do not auto-set the flag inside the code change.

After that code is deployed, the enable action for SHADOW is `POST /api/arbicore/scanners/flash_loan_arb/resume` (`flash_loan_resume` → `set_enabled(..., True, actor="operator_resume")`). That writes scanner state only. It does not change execution mode, network config, or provider flags. The 15-second refresh loop then makes `is_enabled()` true and `_tick` enters discovery. Do not do this until steps 2 and 3 are in, or the ticks still emit nothing.

Tick path once the flag is observed: `_maybe_rebuild_route_engine` → each source `discover()` → queue → `FlashLoanOpportunityVerifier.verify` → `EmissionBus.emit` only on a confirmed outcome. Sources are already built by `build_all_flash_loan_sources`: `flash_loan_route_search`, `flash_loan_provider_health` (always `[]`), `flash_loan_generic_dex`, `flash_loan_triangular`, `flash_loan_balancer_v2`.

### Tests required

- Unit: after `_refresh_caches_once`, a state document `enabled: true` makes `is_enabled()` true, and `enabled: false` makes it false. A failed state read leaves the boot default false.
- Unit: `_tick` with the cache false does not call `discover`. With the cache true it does.
- Do not add a test that starts the production loop or writes the live Mongo row.

Existing coverage that does **not** prove this runtime: `app/backend/tests/test_m5_canonical_activation.py` (sources register when the test enables chains and providers), `app/backend/tests/test_stage1_canonical_flash_loan_scanner.py` (`detection_only`).

### Infrastructure

Yes. The loop, live quote provider, five sources, and resume route already exist. The missing piece is the state-cache assignment.

### Mode scope

The cache fix is specific to `FlashLoanArbitrageScanner`. Other scanners already copy their own state. `flash_loan_arbitrage` is the only strategy row in `SHADOW`. Resume does not start the PAPER scanners. The same tick function runs if that mode row were later changed; this plan does not change it.

### RPC risk

None. No RPC client, URL, or network document is involved.

---

## 2. Flash-loan providers Aave / Balancer / UniV3 disabled

### Source

| Symbol | Path |
|---|---|
| `DEFAULT_FLASH_LOAN_ARB_CONFIG["providers"]` | `app/backend/arbicore/data/scanner_config_defaults.py`. All three `enabled: false` |
| `_enabled_chains_providers` | `app/backend/arbicore/scanners/flash_loan_arbitrage/activation_sources.py` |
| `RouteSearchDiscoverySource.discover` | `app/backend/arbicore/scanners/flash_loan_arbitrage/sources.py`. Empty provider list returns `[]` |
| `FlashLoanProviderHealthSource.discover` | same file. Always `[]` |
| `FLASH_LOAN_PROVIDERS` | `app/backend/arbicore/scanners/flash_loan_arbitrage/economics.py` |
| `AaveV3FlashLoanAdapter`, `BalancerV2FlashLoanAdapter`, `UniswapV3FlashLoanAdapter`, `ADDRESS_BOOK` | `app/backend/arbicore/execution/adapters.py` |
| `flash_loan_provider_enable` | `app/backend/arbicore/routes/scanners.py`. `POST /api/arbicore/scanners/flash_loan_arb/providers/{provider_id}/enable` |
| `SUPPORTED_FLASH_PROVIDERS` | `app/backend/arbicore/scanners/flash_loan_arbitrage/executor_capability.py`. `balancer_v2` and `aave_v3` only. UniV3 flash is not a v1 settlement head |

Catalog `supports_chains`:

| Provider | Catalog chains | Adapter `supports_chains` | `ADDRESS_BOOK` |
|---|---|---|---|
| `aave_v3` | ethereum, arbitrum, base, optimism, polygon, **bnb** | five chains, **bnb omitted** | Base pool address only |
| `balancer_v2` | five chains, **bnb omitted** | same five | Base vault only |
| `uniswap_v3` (flash head) | five chains, **bnb omitted** | same five | not a pool entry; UniV3 router is Base-only in this book |
| `morpho_blue` | ethereum, base | not in the scanner `providers` object | not a scanner toggle |

### Current state

Persisted providers are disabled. Every discovery source returns `[]` before it looks at pools. The health source never emits candidates. Adapters exist as calldata **planners** (`borrow_step` / `repay_step` return dicts). They are not called by `_tick`. Tests in `app/backend/tests/test_wave6b_unit.py` construct those objects and do not sign or broadcast.

### Root cause

Operator boot posture. `seed_defaults` inserts the dormant provider block once and does not turn flags on. Discovery treats “no enabled provider” as “no candidates”, even though the provider value is only a funding-head label on the `DiscoveryCandidate`.

### Proposed change

After steps 1–3, set the three existing provider objects to `enabled: true` through `flash_loan_provider_enable` (or an equivalent `$set` of `providers.<id>.enabled` only). Config refresh already deep-merges `providers`, so this flag **is** observed without the state-cache fix. It still produces no ticks until step 1 and no cycles until steps 2–3.

Also filter the provider paired onto a candidate by `FLASH_LOAN_PROVIDERS[provider]["supports_chains"]`. Today `discover()` pairs every enabled provider with every enabled chain, so a BNB cycle would be labeled `balancer_v2` or `uniswap_v3` flash even though those catalogs omit BNB. Aave is the only catalog head that lists BNB. Do not add Morpho to this scanner config in this plan.

Do not call `borrow_step` from the scanner. Enabling the flag is safe for SHADOW because the tick never builds flash calldata. It is not a license to broadcast. `ADDRESS_BOOK` has no non-Base pool address, so those adapters are not an execution path on five of the six chains.

### Tests required

- Existing: `app/backend/tests/test_wave6b_unit.py` (adapter registry, Base `borrow_step` / `repay_step` shape).
- New: with providers disabled, `RouteSearchDiscoverySource.discover` and the three activation sources return `[]`.
- New: with providers enabled and a fixture pool that passes TVL, a candidate is emitted and its `provider` is in that chain’s `supports_chains`.
- New: BNB plus enabled `balancer_v2` does not label the candidate `balancer_v2`.
- Assert the scanner module does not import `borrow_step` onto `_tick`.

### Infrastructure

Yes for the discovery gate. The flags, catalog, and enable route exist. No for treating the adapters as six-chain execution: addresses and `supports_chains` are Base-centred, and v1 settlement flash heads are Balancer V2 and Aave V3 only. That limitation does not block SHADOW detection.

### Mode scope

The provider flags are read only by this flash-loan scanner. They do not enable other scanners and do not change `execution_mode_state`. A later live mode would still have to pass the pipeline and the receiver profile; this plan does not open that path.

### RPC risk

The enable write is Mongo `arbicore_scanner_config`. It does not read or write RPC URLs. Provider-liquidity `eth_call` helpers in `provider_liquidity.py` are not on `FlashLoanProviderHealthSource.discover`.

---

## 3. Pool TVL is `$0` against a `$100,000` floor

### Source

| Symbol | Path |
|---|---|
| `RouteSearchEngine.search` | `app/backend/arbicore/scanners/flash_loan_arbitrage/route_search.py`. `pools = [p for p in pools if p.tvl_usd >= self.min_pool_tvl_usd]` |
| Default floor `100_000` | same file; `DEFAULT_FLASH_LOAN_ARB_CONFIG["route_search"]`; composition `_BOOT_CFG` |
| `build_pool_graph` | `app/backend/arbicore/discovery/multichain_venues.py`. Every `PoolNode` is constructed with `tvl_usd=0.0` |
| `build_canonical_pool_graph` | `app/backend/arbicore/discovery/base_pool_registry.py`. Same `tvl_usd=0.0` |
| `_multichain_pool_loader` | `app/backend/arbicore/runtime/composition.py`. Base uses the canonical graph minus the runtime UniV3 deny-list. Other chains use `build_pool_graph` when `resolve_rpc_url_from_env(chain)` is set |
| `OnChainReserveTVLProvider`, `UnknownTVLProvider` | `app/backend/arbicore/scanners/flash_loan_arbitrage/tvl_provider.py`. `None` means unknown, not zero |
| `build_base_tvl_provider` | `app/backend/arbicore/searcher/runtime.py`. Base reserves + Base USD price, used **after** a quote |
| `_resolve_pool_tvls` / `tvl_provider_chain` | `app/backend/arbicore/scanners/flash_loan_arbitrage/live_quote_provider.py`. Gate 8 depth is Base-scoped. Any other chain skips it on purpose |
| `FlashLoanGate8LiquidityDepth` | `app/backend/arbicore/scanners/flash_loan_arbitrage/filter.py` |

`TriangularDiscoverySource` does **not** apply this floor. It can emit cycles whose `min_tvl_usd` is `0`. Those still die later in the planner (section 6) and, if quoted, at Gate 8 when measured depth is missing.

### Current state

The graph is not empty. The coverage audit counted venues (ethereum 45, arbitrum 140, base canonical UniV3 plus 11 resolved Aerodrome, optimism 56, polygon 63, bnb 60) and every stored `tvl_usd` was `0`. `RouteSearchEngine.search` at the configured floor returned 0 cycles on all six chains. Forcing the floor to `0` produced cycles, which shows the graph has edges. That force is not the remediation.

### Root cause

Schema mismatch, not an empty market and not a failed ingestion job. Both graph builders document `tvl_usd=0.0` as “not fabricated; measure later”. `RouteSearchEngine` treats that field as a measured dollar TVL and drops anything under `$100,000`. Unknown is stored as zero, and zero fails a positive floor. The real measurer (`OnChainReserveTVLProvider` via `build_base_tvl_provider`) runs only for Base, only after a route has already been planned, and only for Gate 8. It never writes back onto `PoolNode`. Non-Base chains have no USD price wired in this composition (`MultichainPriceSource` is constructed with `{"base": price_feed}` only).

### Proposed change

Keep both floors at `$100,000`.

Before `search()` filters, fill `PoolNode.tvl_usd` from a measured snapshot:

- Reuse `OnChainReserveTVLProvider` (`get_pool_tvl_usd(chain, pool_address) -> Optional[float]`).
- Resolve the pool’s real address first (UniV3 `resolve_univ3_pool`, Algebra `algebra_pool_resolver`, Base canonical `address`). A synthetic venue id is not a TVL key.
- Call `eth_call` only through the existing per-chain registry provider (`make_eth_call_for_chain_from_env` / the Base provider already used at activation). No new endpoint.
- If reserves or a USD price is missing, leave `tvl_usd` at `0` so the existing filter excludes the pool. Do not substitute a sentinel.
- Extend the price side past Base only with the same fail-closed on-chain feed pattern (`exact_size_sizer.MultichainUsdPriceFeed` / `searcher/price_feed.py`). No invented prices.
- Cache with `CachedTVLProvider` so a tick does not re-read every pool on every hop.
- Gate 8 must use that same per-chain measurement. Today a non-Base quote skips the Base TVL provider and fails closed even if the graph TVL were fixed. One measurer should feed both the pre-search field and `min_pool_tvl_usd_in_route`.

`RouteSearchEngine` stays synchronous. The snapshot is computed before `search()` and passed in as already-measured `PoolNode`s. Do not change the comparison `tvl_usd >= min_pool_tvl_usd`.

### Tests required

- Existing floor behaviour stays: `app/backend/tests/test_d6_1_route_search.py`, `app/backend/tests/test_t0_correctness.py` (Gate 8 denies `min_pool_tvl_usd_in_route=0`), `app/backend/tests/test_z8_canonical_scanner_loader_integration.py` (graph does not invent `$5M`).
- New: a pool whose provider returns `150_000` is searchable at the default floor; a pool whose provider returns `None` stays at `0` and is excluded; a pool measured at `99_999` is excluded.
- New: a non-Base route does not receive Base TVL (`test_h06_h07_chain_isolation.py` already covers the leak direction).
- Do not add a production test that sets `min_pool_tvl_usd=0`.

### Infrastructure

Partial. The provider interface, Base reserves reader, Base price feed, and six-chain `eth_call` seam exist. The non-Base price feed and the write-back onto the route graph do not. Chains that cannot be priced stay fail-closed under the current floor, which is the correct outcome.

### Mode scope

The loader and the floor are used only by this flash-loan route engine. Gate 8 thresholds are this scanner’s `gate_thresholds`. No other execution mode reads `build_pool_graph`’s placeholder as a live trading size.

### RPC risk

The change issues more read-only `eth_call`s (reserves, decimals, prices) against the RPC the process already uses. It must not add a URL, change A/B order, or select a public endpoint. Operational CU volume goes up. The certified revision does not.

---

## 4. BNB absent from the persisted discovery chain set

### Source

| Symbol | Path |
|---|---|
| `DEFAULT_FLASH_LOAN_ARB_CONFIG["chains"]["bnb"]` | `app/backend/arbicore/data/scanner_config_defaults.py`. Present, `enabled: false`, `chain_id` 56, `rpc_env_var` `BNB_RPC_URL` |
| `_BOOT_CFG["chains"]["bnb"]` | `app/backend/arbicore/runtime/composition.py`. Present, `enabled: false` |
| `_deep_merge_cfg` | same file. Persisted keys override; missing persisted keys keep the boot value |
| `ScannerConfigRepository.seed_defaults` | `app/backend/arbicore/data/scanner_config_repo.py`. Inserts the default document only when `_id=flash_loan_arb` is **absent**. It does not backfill new chain keys |
| `ScannerConfigRepository.get` | same file. Returns the raw Mongo document, not the boot merge |
| `flash_loan_chain_enable` | `app/backend/arbicore/routes/scanners.py`. If `chains[chain_id]` is missing or empty, HTTP 404 `unknown chain` |
| `_enabled_chains_providers` / `RouteSearchDiscoverySource` | activation sources and `sources.py`. A chain with `enabled` false is not iterated |
| `build_pool_graph("bnb")` | `multichain_venues.py` plus `chains/registries.py` `CHAIN_REGISTRIES["bnb"]`. The graph can still be built when an RPC exists. Sources never ask for it |
| `BALANCER_V2_VAULT_BY_CHAIN` | `app/backend/arbicore/discovery/balancer_v2_pool_discovery.py`. BNB is intentionally absent |

The coverage audit’s Mongo read is the runtime fact: the persisted `flash_loan_arb.chains` object has ethereum, arbitrum, base, optimism, and polygon enabled, and **no `bnb` key**.

### Current state

Network config has BNB (certified six-chain RPC). The discovery merge does not. Boot contributes `bnb.enabled=false`. The persisted document does not override that key, so the merged config keeps BNB off. `POST .../chains/bnb/enable` cannot fix it: `get()` sees the raw document, the key is missing, and the handler returns 404. `seed_defaults` will not repair an existing document.

### Root cause

Scanner-config drift, not network-config drift. The chain key was added to code defaults after the Mongo document was seeded. Seed-once plus a 404 on an unknown key froze the omission. Deep merge then preserves boot `enabled: false`.

### Proposed change

Do not edit network config.

1. Code: `flash_loan_chain_enable` / `disable` should treat a chain as known when it is in `DEFAULT_FLASH_LOAN_ARB_CONFIG["chains"]` (or `_IN_SCOPE_CHAINS` and the default object), even if the persisted document omitted it. The write must `$set` only `chains.bnb` (and its sibling fields from the default object) and must not replace `chains` wholesale. A wholesale `$set` of `chains` would drop the five enabled chains.
2. Later operator write: set that `chains.bnb.enabled` to true. Gas token, chain id, and `rpc_env_var` stay the code defaults. The RPC URL itself stays the certified provider registry. Do not write a URL into this document.

BNB Balancer remains unwired after this. There is no vault. That is correct, not a defect to patch with a fake vault.

BNB borrow set stays `USDC`, `USDT`, `WETH`, `DAI`. `WBNB` is in the token registry and in the pool graph, and it is not in `_DEFAULT_BORROW`. Adding `WBNB` as a borrow token is optional and separate; it is not required to let the chain be iterated.

### Tests required

- New: persisted chains without `bnb`, boot config with `bnb.enabled=false`, merged result stays disabled.
- New: enable route creates `chains.bnb` from the default object without deleting `chains.ethereum`.
- New: after `enabled: true`, `discover()` iterates `bnb` and still skips it when the provider list is empty.
- Existing graph test can keep asserting `build_pool_graph("bnb")` returns Pancake and UniV3 venues with `tvl_usd=0` until step 3’s measurer is in.

### Infrastructure

Yes. Registry, quoter addresses, and certified RPC already exist. The scanner document and the enable route are what omit the chain.

### Mode scope

`chains` on `flash_loan_arb` is this scanner only. Cross-chain and other families have their own chain maps. Enabling this key does not change their mode rows.

### RPC risk

None if the write touches only `arbicore_scanner_config.chains.bnb.enabled` and the default metadata. Discovery will then call the existing BNB `eth_call` helper. That helper must keep using the certified resolver. No new host, no public RPC, no APPLY.

---

## 5. DEX / quote coverage

### Source

Planner, image-identical file `app/backend/arbicore/scanners/flash_loan_arbitrage/live_quote_provider.py`:

- `_plan_generic_evm` accepts `uniswap_v3` (via `resolve_univ3_pool`) and `balancer_v2` (via `_explicit_balancer_identity`). Any other `dex` returns `None`.
- The live provider uses `_plan_generic_evm` whenever `route_hops` is present, **including Base**.
- `_plan_base` runs only when `route_hops` is absent and the chain is Base. It can carry Aerodrome specs from `canonical_pool_specs`.
- `RouteSearchDiscoverySource._augment_multichain_route` attaches `route_hops` for every non-Base cycle and returns early for Base. Generic DEX and triangular always attach `route_hops`, including on Base.

Quoter backends registered in `QuoterRegistry.__init__` (`app/backend/arbicore/execution/quoter.py`). Chain maps:

| Backend | `dex` | Chains with a contract | In the SHADOW graph? | Intended for this SHADOW quote path? |
|---|---|---|---|---|
| `UniV3QuoterV2` | `uniswap_v3` | all six | yes | yes |
| `BalancerV2Quoter` | `balancer_v2` | vault on five; not BNB | only after Balancer discovery supplies a real pool id | yes on those five chains |
| `SushiV3QuoterV2` | `sushiswap_v3` | arbitrum | yes | yes |
| `UniV2RouterQuoter` | `sushiswap_v2` | ethereum | yes | yes for SHADOW quotes. Not in receiver profile `v2` |
| `CamelotV3Quoter` | `camelot_v3` | arbitrum | yes | yes |
| `QuickSwapV3Quoter` | `quickswap_v3` | polygon | yes | yes |
| `PancakeV3QuoterV2` | `pancakeswap_v3` | bnb | yes | yes, once BNB is in the enabled chain set |
| `AerodromeSlipStreamQuoter` | `aerodrome_slipstream` | base | yes, after runtime resolve | yes |
| `AerodromeClassicQuoter` | `aerodrome` | base | yes, after runtime resolve | yes |
| — | `curve_stable` | factory only, ABI family `curve` excluded from `build_pool_graph` | no | no |
| — | `velodrome_v2` | factory only, ABI family `solidly` excluded, no quoter | no | no |

Resolvers that already exist and are not called by `_plan_generic_evm`: `discovery/univ3_pool_resolver.py` (called for `uniswap_v3` only; Sushi V3 and Pancake V3 are the same ABI family), `discovery/algebra_pool_resolver.py` (Camelot / QuickSwap; the module says it does not quote, and the quoter classes do), `discovery/multichain_pool_resolver.py` (`_SUPPORTED_DEXES = ("uniswap_v3",)` only).

`executor_capability.SUPPORTED_DEXES` is `{"uniswap_v3"}`. `RECEIVER_CAPABILITY_PROFILES["v2"]` lists UniV3, Sushi V3, Pancake V3, both Aerodrome ids, Camelot, and QuickSwap. It omits Sushi V2. `evaluate_executor_capability` is not called from `_tick`. Settlement capability and SHADOW quote capability are different sets. This plan changes only the quote set.

### Current state

Adapters for the eight quote families above are implemented and registered. The SHADOW planner never calls six of them. Curve and Velodrome are not intended for this pass.

### Root cause

`_plan_generic_evm` was written as a UniV3-plus-explicit-Balancer planner. The graph and the quoter registry grew additional families. Selection still emits those families (sections 6 and 7) and the planner fail-closes the whole route.

### Proposed change

Intended SHADOW quote set is the table rows marked yes: every DEX that is already in the discovery graph and already has a chain-scoped quoter backend. Curve, Velodrome, and Morpho-as-a-route are out.

Extend `_plan_generic_evm` (and the Base `route_hops` path, which uses it) so a hop is planned only when `QuoterRegistry` has that `dex` and the backend’s chain map contains the chain:

- `univ3` ABI (`uniswap_v3`, `sushiswap_v3`, `pancakeswap_v3`): existing `resolve_univ3_pool` against that DEX’s factory, then the matching quoter.
- `algebra` (`camelot_v3`, `quickswap_v3`): `algebra_pool_resolver`, then `CamelotV3Quoter` / `QuickSwapV3Quoter`. Dynamic fee stays on the quoter; do not invent a fee tier.
- `univ2` (`sushiswap_v2`): router quoter; no UniV3 pool resolve.
- `aerodrome` / `aerodrome_slipstream` on Base: the same spec fields `_plan_base` already passes (`tick_spacing`, `stable`, resolved address).
- `balancer_v2`: unchanged; still requires an explicit `pool_id` or 20-byte address. A synthetic `balancer_v2:TOKEN:...` id stays rejected.
- Anything else: still `None` for that hop. Do not fabricate a quoter.

A chain with no contract in the backend map fails closed inside the quoter today (`fallback:no_adapter`). The planner should fail that hop before the quote, using the same map, so the route is not half-quoted.

### Tests required

- Existing planner rejection is encoded in `app/backend/tests/test_flash_route_to_quote_pipeline.py`. Update it so Sushi V3, Pancake V3, Sushi V2, Camelot, QuickSwap, and Base Aerodrome with `route_hops` plan when the resolver returns a pool, and still fail when the resolver returns `None`.
- A Curve or Velodrome hop still returns `None`.
- A Balancer hop without a 32-byte pool id or 20-byte address still returns `None`.
- No test may assert a live mainnet quote. Use injected `eth_call`.

### Infrastructure

Yes for the intended set. Factories are in `chains/registries.py`, quoters are registered, Algebra and UniV3 resolvers exist, Aerodrome resolution already runs at Base activation. No for Curve and Velodrome.

### Mode scope

`make_live_quote_provider` is the flash-loan scanner’s quote path. Widening it changes what that scanner can quote in whatever mode the strategy row has. Today that row is `SHADOW`. It does not change `SUPPORTED_DEXES`, so a future live settlement path that actually consults v1 capability still cannot encode these venues. This plan does not put `evaluate_executor_capability` on the broadcast path and does not widen v1. Sushi V2 is quote-only until a receiver profile that includes it is a separate, explicit decision.

### RPC risk

Quotes stay `eth_call` on the certified per-chain provider. No URL edits. More successful plans mean more `eth_call`s. That is volume, not a config change.

---

## 6. Unsupported DEXes are selected, then dropped

### Source

Selection:

- `RouteSearchEngine._build_adjacency` / `search` (`route_search.py`). Adjacency is graph insertion order. The DFS keeps the first cycles until `candidate_cap` (64) or `max_hops` (4) or the 5-second cap. It does not look at `dex_protocol`.
- `GenericDexDiscoverySource.discover` keeps 2-hop cycles and always sets `route_hops`.
- `build_pool_graph` inserts every `univ3`, `univ2`, and `algebra` DEX. Venue ids are `"{dex}:{token_lo}:{token_hi}:{param}"` (`_venue_id` sorts the two symbols). Pancake, Camelot, QuickSwap, and Sushi therefore sit in the same adjacency as UniV3.

Drop:

- `_plan_generic_evm` `else` branch (`live_quote_provider.py`). One unsupported hop returns `None` for the whole route.
- Because generic DEX and triangular set `route_hops`, Base Aerodrome is dropped on those sources even though `_plan_base` could quote it. Route-search on Base does not set `route_hops`, so that one source can reach `_plan_base`.

The 64-cap is consumed before the planner runs. A chain whose first cycles touch Sushi, Camelot, QuickSwap, or Pancake can fill the cap with routes the planner will reject. The coverage audit’s floor-at-0 counts are that behaviour (BNB 2-hop 0-for-6 planner-ok; ethereum triangular 0-for-48 because every leg was `sushiswap_v2`).

### Root cause

Discovery is venue-blind. Quoting is venue-narrow. The cap sits in the blind layer, so rejection does not free a slot for a quotable cycle.

### Proposed change

One capability predicate, shared by the planner and the search:

`hop_quote_capable(chain, pool) -> bool` is true only when step 5 can build a `_HopPlan` for that chain and `pool.dex_protocol`.

- `RouteSearchEngine.search` skips a pool that fails the predicate **before** the cycle is appended and before it counts toward `candidate_cap`. Default the predicate to “all pools” so existing unit tests keep their fixture behaviour unless they pass the predicate.
- `GenericDexDiscoverySource` only emits a 2-hop whose both pools pass.
- Do not delete unsupported venues from `build_pool_graph`. Readiness can still see them. They must not occupy a candidate slot.
- Do not lower the cap and do not raise it to compensate. The cap should count quotable cycles only.
- Balancer complement pools (section 7) use the same predicate.

This is selection, not a second planner. The planner remains the definition of “capable”.

### Tests required

- Fixture graph with Sushi sorted before UniV3, predicate that allows only `uniswap_v3`: the emitted cycles are UniV3, and the cap is not filled with Sushi.
- A mixed cycle is emitted only when every hop passes.
- With the predicate omitted, current DFS order is unchanged.
- Existing: `app/backend/tests/test_d6_1_route_search.py`, `app/backend/tests/test_flash_route_to_quote_pipeline.py`.

### Infrastructure

Yes, once step 5’s predicate exists. No new DEX integration is required for the filter itself.

### Mode scope

Route search is this scanner only. The predicate does not change PAPER scanners or the v1 receiver.

### RPC risk

None in the predicate. Capability is a local map of dex and chain to a quoter contract. It must not probe new RPCs to decide.

---

## 7. Triangular alphabetical pool ordering

### Source

| Symbol | Path | What it sorts |
|---|---|---|
| `TriangularDiscoverySource.discover` | `activation_sources.py` | `sorted(cands, key=lambda p: p.pool_address)[0]` per leg |
| `BalancerV2DiscoverySource._complement_venue` | same file | same key, first non-Balancer pool |
| `enumerate_cycles` | `app/backend/arbicore/scanners/flash_loan_arbitrage/triangular.py` | `permutations(sorted(set(inter)), 2)`. This orders **token symbols**, not pools |
| `_venue_id` | `multichain_venues.py` | `sorted([token_a, token_b])` inside the id string |

`pool_address` for non-Base venues is the synthetic id, so lexicographic order is DEX-name order. That is why the coverage audit saw `sushiswap_v2` on every ethereum leg, `camelot_v3` on every arbitrum leg, `quickswap_v3` on every polygon leg, `pancakeswap_v3` on every bnb leg, and Aerodrome on every live Base triangular cycle (`aerodrome` < `uniswap_v3`).

`TriangularDiscoverySource` does not call `discover_triangular`, does not call `RouteSearchEngine.search`, and does not apply the TVL floor. `triangular.py`’s `discover_triangular` / `UniV3QuoteClient` is a library. The scanner does not use it.

### Current state

Cycle **token** order is deterministic and should stay. Pool choice per leg is deterministic and wrong for quoting: the alphabetically first venue id wins even when that DEX is not in the planner.

### Root cause

The comment in `discover` says “Prefer first distinct pool; deterministic order” and implements that as `sorted(...)[0]` on the raw id. The id’s first component is the DEX name. Unsupported names sort first on five chains.

### Proposed change

Keep `enumerate_cycles` as the token-path enumerator.

Replace the per-leg pick:

1. Candidates for the unordered pair `{A, B}` are unchanged.
2. Keep only pools for which `hop_quote_capable(chain, pool)` is true (section 6).
3. If that set is empty, skip the cycle. Do not emit a leg the planner will drop.
4. Among the capable pools, choose the minimum `pool_address`. Deterministic, and stable if the capable set is unchanged.
5. Apply the same two-step pick in `_complement_venue`.

Do not sort by liquidity, fee, or expected profit in this change. Those need measured quotes and would be a second policy. TVL may later exclude a chosen pool at Gate 8; that is a gate, not a reason to pick an incapable pool.

`discover_triangular` stays unwired. Economics stay in `FlashLoanOpportunityVerifier`.

### Tests required

- Ethereum fixture with `sushiswap_v2:...` and `uniswap_v3:...` on the same leg: the chosen DEX is `uniswap_v3` while Sushi is incapable, and `sushiswap_v2` once step 5 marks it capable.
- Arbitrum: Camelot does not win while incapable; it can win once capable, because `camelot_v3` still sorts before `uniswap_v3`.
- Base with Aerodrome and UniV3: Aerodrome is eligible only when the planner accepts it; otherwise the leg is UniV3.
- A leg with only an incapable DEX produces no candidate.
- Token-path order from `enumerate_cycles` stays sorted-intermediate permutations.
- Existing: `app/backend/tests/test_phase2_strategy_economics.py` covers `classify_strategy`, not this picker.

### Infrastructure

Yes. The picker is local. It needs the section 6 predicate and nothing from network config.

### Mode scope

`TriangularDiscoverySource` is registered only on this scanner. The library `triangular.py` is unchanged.

### RPC risk

None. Ordering does not call RPC. A capable pool is still quoted later with the existing `eth_call` path.

---

## 8. Strategy families and where they are implemented

The SHADOW scanner emits only `OpportunityType.FLASH_LOAN_ARBITRAGE`. Family shape is a source plus hop pattern. `strategy_tagging.classify_strategy` would label `LST_LRT`, `STABLECOIN`, `TRIANGULAR`, `MULTI_HOP`, or `GENERIC_DEX`, and the verifier never calls it. The hint field is `strategy_hint` on the candidate (`GENERIC_DEX`, `TRIANGULAR`). Route-search candidates have no strategy hint; the hop count is the only shape signal.

| Family | Implementation path | Registered on this scanner? | What blocks a full path today |
|---|---|---|---|
| DEX→DEX | `GenericDexDiscoverySource` (`activation_sources.py`). 2-hop, two DEX names or two pool ids. Calls `RouteSearchEngine.search` | yes, `flash_loan_generic_dex` | scanner flag, providers, TVL floor, then planner |
| Multi-hop | no separate source. `RouteSearchEngine` cycles of 2–4 hops. `classify_strategy` would call `legs > 3` `MULTI_HOP`. Verifier does not | the cycles come out of `flash_loan_route_search` | same gates. A 4-hop that touches an incapable DEX is dropped as a whole |
| Triangular | `TriangularDiscoverySource` + `enumerate_cycles` | yes, `flash_loan_triangular` | scanner flag, providers, alphabetical incapable pool, planner. TVL floor does not apply at enumeration |
| Multi-DEX | the same 2-hop filter when `len(set(dexes)) >= 2`, and longer mixed cycles from route search | yes, inside generic DEX and route search | planner rejects the non-UniV3/Balancer hop. Optimism’s probe graph is UniV3 only, so multi-DEX stays absent there until a second DEX is registered |
| Cross-pool | same 2-hop filter when pool ids differ (UniV3 fee tiers 500 and 3000 in the probe graph) | yes, inside generic DEX | TVL floor. Planner can accept a UniV3/UniV3 pair |
| Cross-protocol | `BalancerV2DiscoverySource` (Balancer pool + one non-Balancer complement) and any mixed-DEX cycle | yes, `flash_loan_balancer_v2` | subgraph URL absent and `eth_getLogs` fail-closed produce no Balancer pool; complement picker is alphabetical; BNB has no vault |
| Aerodrome | Base canonical graph + `aero_resolver` at activation. Not its own source | quoted only by `_plan_base` when `route_hops` is absent | generic DEX / triangular attach `route_hops` and the generic planner rejects it |
| Sushi V3 / Sushi V2 / Camelot / QuickSwap / Pancake | `build_pool_graph` + quoter classes in section 5 | in the graph, not separate sources | planner `else` branch |
| Curve | `curve_stable` factory in `registries.py`. ABI `curve` excluded in `build_pool_graph` | no | no quoter. Leave unwired |
| Velodrome | `velodrome_v2` factory. ABI `solidly` excluded. No `QuoterRegistry` entry | no | leave unwired |
| Morpho Blue flash | `FLASH_LOAN_PROVIDERS["morpho_blue"]` only. Not a key under `scanner_config.providers` | no | leave unwired |
| Stablecoin, LST/LRT | `classify_strategy` only | no discovery source | leave unwired. Do not pretend a label is a scanner |
| Cross-chain | `CrossChainArbitrageScanner` | no. Mode `PAPER`, state disabled, runtime autostart off | out of this plan |
| Capital / DEX scanner | `DexArbitrageScanner` and DexScreener hint | no. Mode `PAPER`, state disabled | out of this plan |
| CEX, funding, launch | own scanners | no | out of this plan |

Additional implemented flash-loan behaviour that is not a route family:

- Funding-head catalog and calldata adapters (section 2).
- `FlashLoanEconomicsAssessor` in `economics.py`, called from the verifier only after an exact-size quote.
- `FlashLoanGate7AtomicProfit` (`$25`), `FlashLoanGate8LiquidityDepth` (`$100,000`), `FlashLoanGate9FlashLoanMev`.
- Exact-size denial: `FlashLoanOpportunityVerifier` returns `DENIED_SIZE_NOT_QUOTED` when `facts["size_basis"] == "probe"` (`verifier.py`). The sizer is off (`ARBICORE_BORROW_SIZER_ENABLED` absent) and Base-scoped when on (`_build_base_exact_size_borrow_sizer`).
- SHADOW simulation sink: `make_flash_loan_shadow_sink` builds `OpportunityPipeline` with no broadcaster and no mode repo, so mode resolves to `SHADOW` and the pipeline stops at `SHADOW_RECORDED` (`execution/pipeline.py`). The sink is unwired because `ARBICORE_FLASH_LOAN_SHADOW_ROUTE` is absent (`composition._wire_canonical_flash_loan_scanner`).

### Proposed change

Do not add sources for the unwired families. For the six families the coverage audit called the intended SHADOW subset (DEX→DEX, multi-hop, triangular, multi-DEX, cross-pool, cross-protocol) plus Balancer V2:

1. Steps 1–7 make the existing sources able to emit a quotable, TVL-qualified, exactly sized candidate.
2. Stamp `strategy_hint` from the hop pattern at candidate build time (`GENERIC_DEX` for 2-hop, `TRIANGULAR` for the triangular source, `MULTI_HOP` for hop count greater than 3). Do not call `classify_strategy` for LST/stable side effects unless a dedicated source exists. Optional and not required for quotes to run.
3. Step 8 wires the existing sink when a confirmed quote should be simulated. Leave it off until steps 1–7 are in. The sink must stay the no-broadcaster constructor.

### Tests required

- Existing registration: `app/backend/tests/test_m5_canonical_activation.py`.
- Existing SHADOW sink does not broadcast: `app/backend/tests/test_m2_4_shadow_route.py`.
- Existing probe denial: `app/backend/tests/test_h05_exact_size_binding.py`.
- New: one fixture candidate per intended family reaches `quote_route` when TVL, provider, and capability predicates pass, and does not reach it when any one of those fails.
- New: `shadow_sink is None` does not call `OpportunityPipeline`. When the sink is the test double from `test_m2_4_shadow_route.py`, action is not `broadcast`.

### Infrastructure

The intended families are already coded. Curve, Velodrome, Morpho, stablecoin, LST/LRT, and the other scanners are not infrastructure for this SHADOW path. The exact-size sizer and the shadow sink exist and are switched off. Non-Base exact size needs the same price-feed extension as TVL (section 3). Until that exists, non-Base quotes remain probe-sized and the verifier denies them before profit. That is fail-closed, and it is not fixed by lowering a threshold.

### Mode scope

Family code under `scanners/flash_loan_arbitrage/` serves this scanner. Other families have separate scanners and separate `scanner_state` rows. Turning flash-loan discovery on does not start them. Wiring the shadow sink records SHADOW pipeline evidence for this scanner only. `BROADCAST_MODES` still exclude `SHADOW`.

### RPC risk

Family wiring does not change RPC configuration. Quotes and TVL reads use the existing per-chain `eth_call`. The sink’s simulate stage, if later enabled, also uses that read-only router (`SimulationRouter` / `eth_call`). It must not gain a broadcaster in this plan.

---

## Certified RPC configuration

Every proposed change was checked against the network revision.

| Change | Touches `rev-d069f13244ba44da81f97e72f7cfce5b`? |
|---|---|
| State-cache copy | No |
| Scanner resume | No. Writes `arbicore_scanner_state` only |
| Provider `enabled` flags | No. Writes `arbicore_scanner_config.providers` |
| BNB scanner chain key | No, if the write is `chains.bnb` on the scanner document and does not set an RPC URL |
| TVL snapshot and wider quotes | No URL change. Additional `eth_call` volume on the already-selected A/B providers |
| Capability predicate and triangular sort | No |
| Exact-size sizer env and shadow-sink env | No, if they do not override `PROVIDER_RPC_URLS_*` or the network document |
| `SUPPORTED_DEXES` / kill switch / execution mode | Not in this plan |

`resolve_rpc_url_from_env` remains the only reason a non-Base chain contributes a graph. This plan does not change that function and does not add a public endpoint.

---

## What this plan did not do

- Did not start SHADOW, PAPER, or any scanner tick beyond what the already-running process is doing (`enabled=false` no-op).
- Did not edit product code, scanner documents, network config, env, or thresholds.
- Did not restart containers or enable live execution, signing, or broadcast.

**STOP.** Do not start SHADOW until steps 1–3 are implemented and reviewed. Steps 4–8 are separate operator actions after that.
