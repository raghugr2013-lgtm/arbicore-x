# Pre-SHADOW Strategy Coverage Audit — Post Remediation — 2026-10-03

- **Classification:** **SHADOW_COVERAGE_PARTIAL**
- **Checked (UTC):** `2026-10-03T18:25:32Z`
- **Remediated code:** branch `phase-b/h06-six-chain-runtime` tip `9ed2718b3550066934bd11e99a96503ce75a499f`
- **Running process (unchanged):** container `arbicore-x-backend-new` · image `arbicore-x-backend:27dfab4-20261003` · `ARBICORE_GIT_SHA` `27dfab42ae6981b39628c04fd9d1b869c3f6c57b` · StartedAt `2026-10-03T12:42:03.446652725Z` · Pid `2830498` · RestartCount `0`
- **Network runtime (unchanged):** revision `rev-d069f13244ba44da81f97e72f7cfce5b` · `updated_at` `2026-10-03T15:27:57.368745+00:00` · `updated_by` `admin` · six chains enabled · Alchemy A `cd505118` then B `124bc59c` on ethereum, arbitrum, base, optimism, polygon, and bnb
- **Prior audit:** `docs/certification/PRE_SHADOW_STRATEGY_COVERAGE_AUDIT_20261003.md` (`SHADOW_COVERAGE_PARTIAL` at `2026-10-03T16:03:05Z`)
- **SHADOW campaign:** not started. `arbicore_shadow_certifications` with `status=RUNNING` is **0**

This pass did not deploy the remediated checkout, did not restart the container, did not resume the scanner, did not write scanner config, did not change Network Config or RPCs, and did not send quotes.

Two reachability layers are kept apart below. **Code-path** is the remediated checkout. **Live-data** is the process and Mongo that are actually running.

---

## Verdict

**SHADOW_COVERAGE_PARTIAL.** Safety controls that keep this scanner off real execution are still held, and the remediated discovery code can now plan the quoters that were previously dropped. That is not a live six-chain SHADOW path.

The running image is still `27dfab4`. It does not contain these fixes. Live Mongo still has `flash_loan_arb.enabled=false`, all three flash providers disabled, no `chains.bnb` key, and `min_pool_tvl_usd=100000`. Every pool the remediated graph builders emit still stores `tvl_usd=0` until an enabled tick measures it, so route search at the real floor returns **0 cycles on all six chains**. Exact-size sizing and the SHADOW simulation sink are still off, so a quote that did run would be probe-sized and denied before profit, and would not enter `OpportunityPipeline`.

No live network × family cell is **COVERED**.

---

## What changed in code, and what live data still is

| Gate | Remediated checkout | Live Mongo / running process |
|---|---|---|
| Scanner enabled cache | `cb79ef17` copies persisted `enabled` into the runtime cache. Boot stays false | `arbicore_scanner_state.flash_loan_arb.enabled` is **false**. Other scanners are false. This process is the pre-fix image, so the cache fix is not in pid `2830498` |
| TVL before the floor | Measured USD is written onto `PoolNode` before `tvl_usd >= min_pool_tvl_usd`. Unknown stays `0`. Floor remains **$100,000** | Graph builders still store `0`. The running process never executes the new refresh. Route search at `$100,000` is empty on every chain |
| Quote planner | Sushi V2/V3, Camelot, QuickSwap, Pancake, and Base Aerodrome plan when that chain's existing quoter and resolver both succeed | Not in the running image. This audit did not send `eth_call` quotes |
| Triangular / route-search pick | Incapable DEXes are removed, then the lowest pool id wins. Cap stays 64 | Not in the running image. Live ticks do not discover |
| BNB scanner key | Enable/disable `$set`s only `chains.bnb` from the code default when the key is missing. Default `enabled` stays **false** | Persisted chains are ethereum, arbitrum, base, optimism, polygon, all **enabled true**. **No `bnb` key.** The enable route was not called |
| Provider pairing | A candidate is labeled only with a provider whose catalog `supports_chains` includes that chain. BNB pairs **Aave only** | `aave_v3`, `balancer_v2`, and `uniswap_v3` are all **enabled false**. Defaults in source are still false |
| Exact-size sizer | Unchanged. Still off unless `ARBICORE_BORROW_SIZER_ENABLED` and `ARBICORE_PRICE_FEED_ENABLED` | Both absent. `ARBICORE_USD_NUMERAIRE=USDC` |
| SHADOW sink | Unchanged. Still off unless `ARBICORE_FLASH_LOAN_SHADOW_ROUTE` | Absent |
| Network / RPC | Not edited | Revision and A/B fingerprints match the certified apply |

`execution_mode_state.flash_loan_arbitrage` is still `SHADOW` (`updated_at` `2026-09-07T05:24:07Z`). Every other stored strategy is `PAPER`. `execution_settings.auto_execute_enabled` is **false**, revision `rev-35aaafa0454f4a2d8c9aa7b750a2c803`. Persisted `kill_switch_state` key `global` has `engaged=false` (updated `2026-09-13`). This audit did not read the process's in-memory kill flag and did not change it.

Logs on this container since `12:42Z` contain **0** lines matching `shadow/start`, `eth_sendRawTransaction`, or `LIMITED_LIVE`.

---

## Code-path graph (remediated checkout, no RPC)

`RouteSearchEngine.min_pool_tvl_usd` is `100000.0`. At that floor, with the graph's stored `tvl_usd=0`, search returns **0** cycles for USDC, USDT, WETH, and DAI on every chain. That is the floor working, not an empty market.

The same graphs with a diagnostic floor of `0` (not a product setting, not deployed) and `hop_quote_capable` produce cycles, and every venue in those graphs is on a quoter that serves that chain:

| Chain | Venues | All `tvl_usd=0` | Quoter-capable venues | DEX mix | Diagnostic cycles at floor 0 | 2-hop |
|---|---:|---:|---:|---|---:|---:|
| ethereum | 45 | 45 | 45 | UniV3 30, Sushi V2 15 | 259 | 5 |
| arbitrum | 140 | 140 | 140 | UniV3 56, Sushi V3 56, Camelot 28 | 260 | 7 |
| base, resolved addresses only | 19 | 19 | 19 | UniV3 19 | 160 | 14 |
| optimism | 56 | 56 | 56 | UniV3 56 | 258 | 4 |
| polygon | 63 | 63 | 63 | UniV3 42, QuickSwap 21 | 261 | 5 |
| bnb | 60 | 60 | 60 | Pancake 30, UniV3 30 | 262 | 6 |

The prior audit's BNB 2-hop sample was 0-for-6 planner-ok because Pancake was dropped. In this checkout every BNB venue is on a registered quoter. A hop still fail-closes if the existing resolver returns no pool. This audit did not resolve pools on-chain.

Triangular selection on that same offline graph, using the real capability map (not an injected "incapable" predicate):

| Chain | Cycles | DEX actually chosen |
|---|---:|---|
| ethereum | 48 | `sushiswap_v2` on every leg (quotable, and it sorts first) |
| arbitrum | 80 | `camelot_v3` on every leg (quotable, sorts before UniV3) |
| base, static resolved graph | 12 | `uniswap_v3` |
| optimism | 80 | `uniswap_v3` |
| polygon | 48 | `quickswap_v3` |
| bnb | 24 | `pancakeswap_v3` |

Base canonical registry has 30 pools: 19 UniV3 with addresses, 7 Aerodrome and 4 Slipstream with **no** address in this checkout (`aero_with_address=0`). Aerodrome is quotable on Base once a resolved address exists. The live process's earlier activation log resolved 11 Aerodrome pools; that was the old image, and this audit did not re-resolve them.

Quoter map (`quoter_serves`, local, no RPC):

| DEX | ETH | ARB | BASE | OP | POLYGON | BNB |
|---|---|---|---|---|---|---|
| uniswap_v3 | yes | yes | yes | yes | yes | yes |
| sushiswap_v2 | yes | | | | | |
| sushiswap_v3 | | yes | | | | |
| camelot_v3 | | yes | | | | |
| quickswap_v3 | | | | | yes | |
| pancakeswap_v3 | | | | | | yes |
| aerodrome / slipstream | | | yes | | | |
| balancer_v2 | yes | yes | yes | yes | yes | |
| curve_stable, velodrome_v2 | | | | | | |

---

## NETWORK × STRATEGY-FAMILY

Cell values are `COVERED`, `PARTIAL`, `NOT_WIRED`.

`COVERED` would mean this running process can discover, quote, price, and simulate that shape on that chain. None are.

`PARTIAL` on the **code-path** row means the remediated scanner has a real source and a quotable venue for that shape, and a gate that is still in force stops a complete live path (undeployed code, scanner off, providers off, unmeasured TVL, probe-size denial, or the unwired sink).

### Live runtime (image `27dfab4`, Mongo as read at `18:25Z`)

Unchanged in substance from the 16:03Z audit. The intended rows stay **PARTIAL** or **NOT_WIRED**. None are **COVERED**. BNB is still absent from the persisted chain set. Providers are still disabled. Stored graph TVL is still not measured.

### Remediated checkout (not deployed)

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

Base multi-DEX and Aerodrome are **PARTIAL** in code because the planner accepts Aerodrome when the canonical address is present. This checkout's static registry has no Aerodrome address. Optimism multi-DEX stays **NOT_WIRED**: the probe graph is UniV3 only. BNB Balancer stays **NOT_WIRED**: there is no vault. BNB flash heads other than Aave stay off that chain by catalog.

---

## Family notes

### DEX→DEX, multi-hop, cross-pool

`GenericDexDiscoverySource` and `RouteSearchEngine` still apply the `$100,000` floor. With stored TVL at 0 they emit nothing. The new refresh fills `PoolNode.tvl_usd` only from `OnChainReserveTVLProvider` (Base provider, or the existing non-Base reserves reader plus `MultichainUsdPriceFeed`). A miss stays 0 and is excluded. The comparison was not changed.

Once a pool is measured at or above the floor, route search can emit it, and the predicate drops a DEX that has no quoter on that chain before the candidate cap. Every DEX currently in these six graphs has a quoter on its chain, so the cap is no longer spent on a family the planner rejects.

Optimism 2-hops are UniV3 fee tiers (cross-pool), not two protocols.

### Triangular

`enumerate_cycles` still orders token symbols. The pool picked for a leg is the lowest `pool_address` among quotable pools. A leg with no quotable pool drops the cycle. Sushi V2, Camelot, QuickSwap, and Pancake win their chains because they are quotable and sort first, not because the planner rejects them.

### Cross-protocol and Balancer

UniV3 versus Sushi, Camelot, QuickSwap, Pancake, or Aerodrome can be planned when the resolver returns a pool. Balancer still needs an explicit 32-byte pool id or 20-byte address. BNB has no vault, so `BalancerV2DiscoverySource` does not iterate it. Subgraph and `eth_getLogs` behavior was not re-run live.

### Providers

Catalog support is unchanged: Aave lists all six chains; Balancer V2 and UniV3 flash list five and omit BNB. Discovery now uses that list. Enabling the flags in Mongo was not done. Source defaults remain `enabled: false`.

### Families left unwired on purpose

Curve, Velodrome, Morpho Blue as a scanner provider, dedicated stablecoin and LST/LRT sources, and the PAPER scanners (`dex_arb`, `cex_arb`, `cross_chain_arb`, `funding_arb`, `launch_arb`) were not added to this SHADOW scanner.

---

## Tests

Focused integration run at `18:25Z` against the remediated checkout, `253 passed`.

`tests/test_phase2_multichain_discovery.py` still fails two cases (`arbitrum`, `polygon`) because Algebra venues are stored with `fee_bps=0`. That placeholder is in `multichain_venues.py`, which these commits did not change. Inventing a fee tier was out of scope. Those two failures are not regressions from this remediation.

| Check | Result |
|---|---|
| Scanner state cache | `tests/test_flash_loan_scanner_state_cache.py` included in the 253 |
| TVL propagation and the `$100,000` floor | `tests/test_pool_tvl_propagation.py`, `tests/test_d6_1_route_search.py`, `tests/test_t0_correctness.py` |
| DEX / quoter compatibility | `tests/test_quoter_dex_compatibility.py`, `tests/test_flash_route_to_quote_pipeline.py` |
| Triangular selection | `tests/test_triangular_route_selection.py` |
| BNB chain key and provider scope | `tests/test_bnb_scanner_config_path.py` |
| Six-chain discovery / quote seams | `tests/test_h06_canonical_sixchain.py`, `tests/test_h06_h07_chain_isolation.py`, `tests/test_live_quote_provider_multichain.py`, `tests/test_sp2_multichain_pool_registry.py`, `tests/test_sp4_multichain_tvl_provider.py`, `tests/test_sp5_multichain_pool_resolver.py`, `tests/test_m5_canonical_activation.py` |

Checkpoint commits on `phase-b/h06-six-chain-runtime`:

| Item | SHA |
|---|---|
| Scanner enabled-state cache (already done) | `cb79ef17ad52b8458babeb074adf38c6f0873da3` |
| TVL propagation | `df12c3dfb21630d98f7c8a70334a2d22787e0f86` |
| Quoter reachability | `4b25cc3b829b67b2590bc0d7169c7a3ea1e772bb` |
| Triangular / quotable selection | `1241e6ca23a9dc875aa19e1e5c4f36cdb12bc5e9` |
| BNB chain key and provider scope | `9ed2718b3550066934bd11e99a96503ce75a499f` |

---

## Remaining blockers

1. The running container is still image `27dfab4`. None of the remediation commits are in pid `2830498`.
2. Live scanner state is `enabled=false`. Discovery ticks do not run. This pass did not resume it.
3. Live providers `aave_v3`, `balancer_v2`, and `uniswap_v3` are `enabled=false`. With that document, every discovery source returns no candidates even after the code is deployed.
4. Live `chains.bnb` is absent. Boot merge keeps BNB disabled. The new enable path was not invoked.
5. Stored pool TVL is `$0`. The `$100,000` floor therefore excludes every pool until a measured snapshot exists. Measurement runs only from an enabled tick of the new code, and only when reserves and a real USD price both exist. Unpriced pools stay excluded.
6. Exact-size borrow sizing is off. Probe quotes are denied with `DENIED_SIZE_NOT_QUOTED` before profit and Gates 7–9.
7. `ARBICORE_FLASH_LOAN_SHADOW_ROUTE` is absent, so a confirmed opportunity is not handed to `OpportunityPipeline`.
8. Optimism has no second DEX in the probe graph. BNB has no Balancer vault. Curve, Velodrome, and Morpho Blue are not on this scanner.
9. Base Aerodrome addresses are not in the static registry. They appear only after the existing runtime resolver runs.

---

## Safety

| Control | This pass |
|---|---|
| Network Config / RPCs | Not modified. Revision `rev-d069f13244ba44da81f97e72f7cfce5b`. A `cd505118`, B `124bc59c`, six chains, read back from `arbicore_config` `_id=network` |
| Deploy / restart | Not done. Pid `2830498`, RestartCount `0` |
| SHADOW / PAPER / LIVE | Not started. Running certification count is 0. Flash-loan mode is still `SHADOW`. No mode row is `LIMITED_LIVE` or `FULL_LIVE` |
| Scanner resume | Not done. `enabled` remains false. Provider flags were not written |
| TVL floor | Still `$100,000` in code defaults, in `RouteSearchEngine`, and in live `route_search.min_pool_tvl_usd` |
| Signing / broadcast | Not done |

**STOP.** Do not start SHADOW on the current process. The discovery fixes are in the checkout, not in the running image, and the live scanner document is still disabled with unmeasured TVL.
