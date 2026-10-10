# ArbiCore X — Pre–Gate 9/10 Capability Matrix Audit

- **Status:** AUDIT ONLY (no source/config changes, no rebuild/deploy, no Gate changes, no PAPER/AUTOEXEC/RUNTIME enable, no execution)
- **Date:** 2026-10-02
- **Workspace:** `/home/raghu/projects/arbicore-x-cert`
- **Branch tip (binding for this audit):** `9b196cde0c975d0efe94e94f49de05b4244bdbc6`
- **Method rule:** Completeness is proven only via implementation + integration + tests/evidence — **not** docs/enums alone.

---

## FINAL STATUS: **READY**

**Continue the 24h/72h Gate 9–10 SHADOW campaign now.** Do **not** block the campaign on completing STABLECOIN / LST_LRT / MULTI_HOP / Morpho / UniV3-flash / CROSS_CHAIN-executable first. Those are deferred capability gaps, not SHADOW-campaign blockers.

Optional **ops-only** continuity delta (no implementation): keep `ARBICORE_PAPER_VALIDATION_ENABLED=true`, SHADOW on, AUTOEXEC/RUNTIME off, and sustain an unbroken ≥24h / ≥72h evidence window (prior paper Gate 9–10 run was CONDITIONAL at ≈1.04h with 0 evidence rows).

---

## 1. Executive summary

| Question | Answer |
|---|---|
| Can we safely continue 24h/72h Gate 9–10 **SHADOW** now? | **Yes.** M6 POST-ALCHEMY-RESET SHADOW is **PASS (evidence-complete)**; Gate 7=$25 / Gate 8 fail-closed / H05 off / AUTOEXEC+RUNTIME off held. |
| Must we complete/validate a capability first? | **No** for SHADOW Gate 9–10 continuity. Capability expansion (stables/LST/Morpho/cross-chain executable) is explicitly out of campaign scope. |
| Strongest proven surface | **GENERIC_DEX** quote→econ→Gate7 on six chains via live harness (Aave flash fee model); M5 DiscoverySources wired; Balancer **quote** P0 on Ethereum operational after Alchemy key reset. |
| Weakest / deferred | Dedicated STABLECOIN / LST_LRT engines; MULTI_HOP as first-class family; UniV3 single-sided flash & Morpho on **deployed V1** receiver; CROSS_CHAIN **executable** path; Balancer P1 subgraph + Alchemy Free `eth_getLogs` range; empty live pool inventory → DiscoverySource smoke = 0 candidates. |
| FINAL STATUS | **READY** (SHADOW Gate 9–10 campaign). Capability matrix is **incomplete** but **non-blocking** for this campaign. |

Classification discipline used below (exactly one per meaningful combo):

| Code | Meaning |
|---|---|
| **A** | IMPLEMENTED + INTEGRATED + TESTED/VALIDATED (live/shadow evidence on that combo) |
| **B** | IMPLEMENTED + INTEGRATED, **not** sufficiently validated (tests and/or partial shadow only) |
| **C** | PARTIAL / LIMITED (adapter/tagging/library without full pipeline or with material gaps) |
| **D** | DETECTION ONLY (emit/classify/hint; no executable settlement path claimed) |
| **E** | NOT IMPLEMENTED |
| **F** | BLOCKED / UNAVAILABLE INFRASTRUCTURE |
| **N/A** | Genuinely not applicable (protocol absent on chain) |

Per-combo columns: IMPLEMENTED? | INTEGRATED INTO OPPORTUNITY PIPELINE? | QUOTE/SIM SUPPORT? | ECONOMIC GATE SUPPORT? | EXECUTION PATH? | SHADOW TESTED? | PAPER/evidence tested? | CERTIFIED? | BLOCKER? | EVIDENCE REFERENCE?

---

## 2. Scope, method, and non-goals

### In scope

- Six chains: `ethereum`, `arbitrum`, `base`, `optimism`, `polygon`, `bnb`
- Route families: `GENERIC_DEX` (DEX→DEX), `TRIANGULAR`, `STABLECOIN`, `MULTI_HOP`, `LST_LRT`, `CROSS_CHAIN`
- Flash providers: Aave V3, Balancer V2, Uniswap V3 single-sided flash, Morpho Blue
- Evidence from source, routers/adapters, tests, config defaults, M5/M6/H06/extract-port/Balancer P0–P1b, paper Gate 9–10, shadow + paper reports

### Out of scope (hard stop)

- Source/config edits, rebuild, deploy
- Gate 7/8 threshold changes
- PAPER mode promotion, AUTOEXEC, RUNTIME, LIMITED_LIVE, signing, broadcast
- Implementing any capability delta listed in §11

### Proof standard

- **Enums / docs alone ≠ implemented.** Example: `StrategyType.STABLECOIN` / `LST_LRT` exist and classify routes, but there is no dedicated discovery+eval engine → not A/B.
- **Library + unit tests ≠ integrated.** Pre-M5 GENERIC_DEX/triangular were library-only; M5 wires DiscoverySources (`05dacdb`).
- **Registration ≠ live inventory.** M6 smoke: `flash_loan_generic_dex` / `triangular` / `balancer_v2` registered; **0** discovery candidates from empty inventory.
- **SHADOW harness ≠ paper fills.** M6 exercised `GenericDexRouteEngine` live; paper Mongo `arbicore_paper_evidence` count = **0** on Gate 9–10 stamp.

---

## 3. Evidence anchors (SHAs / tags / reports)

| Anchor | Value |
|---|---|
| Audit HEAD | `9b196cde0c975d0efe94e94f49de05b4244bdbc6` |
| M5 activation | `05dacdb3eb3cc2f6555aee77b8a9811206891bc5` · tag `arbicore-m5-canonical-activation-pass-20261001` · **ancestor of HEAD** |
| Extract-port tip | `861af4d60e841ac8abac5891d663e23986c356ad` · tag `arbicore-extract-port-pass-20261001` |
| GENERIC_DEX extract | `f57e853` · tag `arbicore-generic-dex-on-h06-20261001` |
| Balancer P0/P1/P1b | `520b0cc` / `76eb003` / `d7e2418` · tags `arbicore-p0/p1/p1b-*-on-h06-20261001` |
| H06 six-chain | `7c2b1bce4ca97cb3aa753ed9dff6d67a9be168b4` · tag `arbicore-h06-sixchain-pass-20261001` |
| M6 POST-ALCHEMY SHADOW | `docs/certification/M6_POST_ALCHEMY_RESET_SHADOW_20261002.md` · `reports/shadow_validation/m6_post_alchemy_reset_20261002T063623Z.json` / `…_latest.json` |
| Paper Gate 9–10 | `docs/certification/PAPER_GATE9_10_VALIDATION_20261002.md` · `reports/paper_validation/gate9_10_final_20261002T072116Z.json` |
| Paper readiness | `docs/certification/PAPER_BROKER_READINESS_AUDIT_20261002.md` · `PAPER_VALIDATION_MINIMAL_DELTA_PLAN_20261002.md` |
| Architecture recon | `docs/certification/SHADOW_VALIDATION_ARCHITECTURE_RECONCILIATION_20261001.md` (pre-M5; superseded for DiscoverySource wiring by M5) |
| Image / mode (observed) | `arbicore-x-backend:g5.79-green-20260927` · `ARBICORE_EXECUTION_MODE=SHADOW` · AUTOEXEC/RUNTIME **false** |

Primary implementation roots:

- `app/backend/arbicore/scanners/flash_loan_arbitrage/` (scanner, verifier, economics, route_search, activation_sources, strategy_tagging, provider_liquidity, executor_capability)
- `app/backend/arbicore/scanners/generic_dex_route_engine.py`
- `app/backend/arbicore/scanners/cross_chain_arbitrage/`
- `app/backend/arbicore/execution/{quoter.py,adapters.py,settlement_dispatcher.py,pipeline.py,calldata*.py}`
- `app/backend/arbicore/discovery/balancer_v2_*.py`
- `app/backend/arbicore/chains/{registries.py,evm_gas.py}`
- `app/backend/arbicore/data/scanner_config_defaults.py`
- `app/backend/arbicore/runtime/composition.py`

---

## 4. Six-chain infrastructure matrix

| Chain | RPC identity (M6/Paper) | Gas model | Token registry | Quoter backends relevant | Flash catalog presence | Notes |
|---|---|---|---|---|---|---|
| ethereum | PASS (Alchemy) | L1 `none` | Yes | UniV3, Sushi, Balancer, … | Aave, Balancer, UniV3 flash, Morpho | Balancer P0 **ok** post-reset; P1b long window **F** (Free `eth_getLogs` ≤10 blk) |
| arbitrum | PASS | L1 `arbitrum` | Yes | UniV3, Sushi, Camelot, Balancer | Aave, Balancer, UniV3 flash | GENERIC_DEX B=6 + E=2 (unknown_gas) |
| base | PASS (`mainnet.base.org`) | OP-stack L1 | Yes | UniV3, Aerodrome(+SS), Balancer | Aave, Balancer, UniV3 flash, Morpho | aero_ss quote gaps; P1b on-chain **ok** (short window) |
| optimism | PASS | OP-stack L1 | Yes | UniV3, Balancer | Aave, Balancer, UniV3 flash | GENERIC_DEX B=2 |
| polygon | PASS | L1 `none` | Yes | UniV3, QuickSwap, Balancer | Aave, Balancer, UniV3 flash | GENERIC_DEX E=6 unknown_gas; getLogs probe error |
| bnb | PASS | L1 `none` | Yes | PancakeV3 (UniV3-class) | **Aave only** in catalog | Balancer **N/A**; UniV3 flash **N/A**; Morpho **N/A**; pancake `no_adapter` gaps in prior blockers |

H06 certifies the **six-chain runtime seam** (operator-RPC gate), not live trading or full venue coverage (`docs/certification/H06_SIXCHAIN_PASS_20261001.md`).

---

## 5. Route-family × chain matrix

Legend applies to the **family capability on that chain** (flash provider orthogonal — see §6–7).

### 5.1 GENERIC_DEX / DEX→DEX

| Chain | Class | IMP | INT | QUOTE | ECON | EXEC | SHADOW | PAPER | CERT | BLOCKER | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ethereum | **B** | Y | Y | Y | Y | Y* | Y | N | Partial† | M5 `GenericDexDiscoverySource`; M6 eth B=2 (aave); `generic_dex_route_engine.py`; tests `test_generic_dex_*` |
| arbitrum | **B** | Y | Y | Y | Y | Y* | Y | N | Partial† | M6 arb B=6 E=2 |
| base | **C** | Y | Y | Partial | Y | Y* | Y | N | Partial† | M6 base C=4 E=4 (aero/quote+gas) |
| optimism | **B** | Y | Y | Y | Y | Y* | Y | N | Partial† | M6 op B=2 |
| polygon | **C** | Y | Y | Y | Y | Y* | Y | N | Partial† | M6 poly E=6 unknown_gas |
| bnb | **C** | Y | Y | Partial | Y | Limited* | Y | N | Partial† | M6 bnb C=4 E=2; pancake adapter gaps |

\*EXECUTION PATH: deployed **V1** receiver = flash heads `{balancer_v2, aave_v3}` + swap venue `{uniswap_v3}` only (`executor_capability.py`, `settlement_dispatcher.py`). Planning adapters exist for more DEXes; live settle is UniV3-only until Executor V2 on-chain. Mode remains SHADOW — path exists, not live-exercised.  
†CERTIFIED: M5 activation + M6 SHADOW evidence-complete for detection/quote/econ; **not** live-executable / profitable certified (A_real_profitable=0).

**Integration note:** M5 registers `flash_loan_generic_dex` into canonical scanner → verifier → Gate7 → EmissionBus. M6 smoke still saw **0** inventory candidates; live GENERIC_DEX rows come from harness driving `GenericDexRouteEngine` + `QuoterRegistry`.

### 5.2 TRIANGULAR

| Chain | Class | IMP | INT | QUOTE | ECON | EXEC | SHADOW | PAPER | CERT | BLOCKER | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all six | **C** | Y | Y | Y‡ | Y | Y* | Partial | N | Partial (M5 wire) | `triangular.py`; `TriangularDiscoverySource`; M5 tests; M6 triangular **0 candidates**; Gate7 library default 25 |

‡Quotes only if hops carry quoter-supported venues. No M6 live triangular route evaluations comparable to GENERIC_DEX table.

### 5.3 STABLECOIN

| Chain | Class | IMP | INT | QUOTE | ECON | EXEC | SHADOW | PAPER | CERT | BLOCKER | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all six | **D** | Tag only | Via generic route path if tokens match | Indirect | Indirect | Indirect* | N | N | N | No dedicated family discovery/eval | `strategy_tagging.py` `STABLE_SYMBOLS` + `classify_strategy`; unit tests `test_phase2_strategy_economics.py`. No `StablecoinDiscoverySource`. |

### 5.4 MULTI_HOP (>3 legs)

| Chain | Class | IMP | INT | QUOTE | ECON | EXEC | SHADOW | PAPER | CERT | BLOCKER | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all six | **C** | Partial | Partial | Partial | Y | Limited* | N | N | N | No dedicated MULTI_HOP source; hop budget only | `RouteSearchEngine` `max_hops` default **4**; `RouteSearchDiscoverySource` emits cycles; tagging `legs > 3` → `MULTI_HOP`. No M6 MULTI_HOP campaign. V1 executor still UniV3-hop limited. |

### 5.5 LST_LRT

| Chain | Class | IMP | INT | QUOTE | ECON | EXEC | SHADOW | PAPER | CERT | BLOCKER | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| eth/arb/base/op/poly | **D** | Tag only | Indirect | Indirect | Indirect | Indirect* | N | N | N | No LST inventory/oracle family engine | `LST_LRT_SYMBOLS` in `strategy_tagging.py`. No dedicated discovery. |
| bnb | **D** / weak | Tag only | Indirect | Weak | Indirect | Limited | N | N | N | LST set is ETH-centric | Same tagging; little BNB LST coverage in registries. |

### 5.6 CROSS_CHAIN

| Combo | Class | Notes |
|---|---|---|
| Detection (all listed EVM corridors in config) | **D** | `CrossChainArbitrageScanner` + sources + verifier + Gates 7/8/9 **bridge/chain/MEV**; boot **dormant**; docstring: “No execution. Detection-only.” |
| Executable cross-chain arb | **E** | No atomic cross-chain flash, no solver/intent settlement, no inventory bridge capital path in execution ladder |

Full CROSS_CHAIN breakdown → §8.

---

## 6. Flash-provider × chain matrix

### 6.1 Aave V3

| Chain | Class | IMP | INT | QUOTE§ | ECON | EXEC | SHADOW | PAPER | CERT | BLOCKER | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ethereum | **B** | Y | Y | Fee model | Y | Y (V1 head) | Y | N | Partial | `FLASH_LOAN_PROVIDERS`; `AaveV3FlashLoanAdapter`; `encode_aave_v3_*`; `AAVE_V3_POOL`; M6 all GENERIC_DEX used `flash_provider=aave_v3` |
| arbitrum | **B** | Y | Y | Fee model | Y | Y | Y | N | Partial | Same + M6 arb |
| base | **B** | Y | Y | Fee model | Y | Y | Y | N | Partial | Same + M6 base |
| optimism | **B** | Y | Y | Fee model | Y | Y | Y | N | Partial | Same + M6 op |
| polygon | **B** | Y | Y | Fee model | Y | Y | Y | N | Partial | Same + M6 poly (gas fails dominate) |
| bnb | **C** | Partial | Partial | Fee model | Y | Gap | Y | N | N | Catalog + `AAVE_V3_POOL["bnb"]` exist; **`AaveV3FlashLoanAdapter.supports_chains` omits `bnb`**; M6 still evaluated aave fee on BNB GENERIC_DEX |

§Flash providers are not DEX quoters; “QUOTE” = fee/liquidity modeling + downstream hop quotes.

### 6.2 Balancer V2 (flash + quote)

| Chain | Class | IMP | INT | QUOTE | ECON | EXEC | SHADOW | PAPER | CERT | BLOCKER | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ethereum | **B** | Y | Y | Y (P0) | Y | Y (V1 head) | Partial | N | P0 extract-port | P0 `ok` post-alchemy; P1 subgraph **unset→F**; P1b long window **F** (getLogs); flash adapter + calldata; M5 `BalancerV2DiscoverySource` |
| arbitrum | **C** | Y | Y | Limited | Y | Y | Partial | N | P0 port | P1 unset; P1b F; flash supported |
| base | **C** | Y | Y | Limited | Y | Y | Partial | N | P0 port | P1 unset; P1b short-window **ok** |
| optimism | **C** | Y | Y | Limited | Y | Y | Partial | N | P0 port | P1/P1b unavailable |
| polygon | **C** | Y | Y | Limited | Y | Y | Partial | N | P0 port | P1/P1b unavailable; RPC getLogs errors |
| bnb | **N/A** | — | — | — | — | — | — | — | — | Vault not deployed (`BALANCER_V2_CHAINS`; catalog `supports_chains` excludes bnb) |

### 6.3 Uniswap V3 single-sided flash

| Chain | Class | IMP | INT | QUOTE | ECON | EXEC | SHADOW | PAPER | CERT | BLOCKER | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| eth/arb/base/op/poly | **C** | Y (adapter+catalog) | Partial (config provider) | Tier fee resolve | Y | **N on V1** | N | N | N | `UniswapV3FlashLoanAdapter`; `FLASH_LOAN_PROVIDERS["uniswap_v3"]`; **not** in `SUPPORTED_FLASH_PROVIDERS` / `CALLDATA_ENCODABLE_FLASH`; settlement rejects univ3 flash (`test_executor_v2_settlement_dispatcher.py::test_uniswap_v3_flash_rejected`) |
| bnb | **N/A** | — | — | — | — | — | — | — | — | Catalog excludes bnb; Pancake ≠ UniV3 pool.flash head |

### 6.4 Morpho Blue

| Chain | Class | IMP | INT | QUOTE | ECON | EXEC | SHADOW | PAPER | CERT | BLOCKER | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ethereum | **C** | Y | Weak | Fee 0 | Y | **N on V1** (V2 profile only) | N | N | N | `MorphoBlueFlashLoanAdapter`; runtime probe tests `test_trackA2_morpho_runtime_probe.py`; in `FLASH_LOAN_PROVIDERS` + optimizer; **absent** from `DEFAULT_FLASH_LOAN_ARB_CONFIG.providers`; V1 `SUPPORTED_FLASH_PROVIDERS` excludes morpho; V2 profile lists it |
| base | **C** | Y | Weak | Fee 0 | Y | **N on V1** | N | N | N | Same |
| arb/op/poly/bnb | **N/A** | — | — | — | — | — | — | — | — | `supports_chains = ("ethereum","base")` |

---

## 7. Meaningful route × provider × chain combos

Only combos that are not universal N/A. Class is the **strictest** proven status for that intersection.

### 7.1 GENERIC_DEX × Aave V3

| Chain | Class | Shadow evidence (M6) | Notes |
|---|---|---|---|
| ethereum | **B** | B=2 non_positive_net | Quotes ok; Gate7 deny; paper 0 |
| arbitrum | **B** | B=6 E=2 | Integrated+shadow; gas seam issues |
| base | **C** | C=4 E=4 | Quote/gas limited |
| optimism | **B** | B=2 | Same as eth pattern |
| polygon | **C** | E=6 | unknown_gas fail-closed |
| bnb | **C** | C=4 E=2 | Adapter chain-support gap + pancake quotes |

### 7.2 GENERIC_DEX × Balancer V2 flash

| Chain | Class | Notes |
|---|---|---|
| eth/arb/base/op/poly | **C** | Flash head executable on V1 **in principle**; M6 GENERIC_DEX harness did **not** exercise balancer as flash_provider (all `aave_v3`). Discovery/Balancer quote path separate (P0/P1). |
| bnb | **N/A** | No Balancer |

### 7.3 GENERIC_DEX × UniV3 flash / Morpho

| Combo | Class | Notes |
|---|---|---|
| GENERIC_DEX × UniV3 flash × {eth,arb,base,op,poly} | **C** | Economics/optimizer aware; **no V1 execution** |
| GENERIC_DEX × Morpho × {eth,base} | **C** | Probe+adapter; not scanner-default provider; no V1 execution |
| Others | **N/A** or **E** | Per §6 |

### 7.4 TRIANGULAR × providers

| Combo | Class | Notes |
|---|---|---|
| TRIANGULAR × Aave × six chains | **C** | Source wired; 0 live candidates; unit liquidity/oracle tests |
| TRIANGULAR × Balancer flash | **C** | Same; Balancer N/A on bnb |
| TRIANGULAR × UniV3 flash / Morpho | **C** / **N/A** | Same V1 gaps as §6 |

### 7.5 STABLECOIN / LST_LRT / MULTI_HOP × providers

| Family | × any flash × any chain | Class | Notes |
|---|---|---|---|
| STABLECOIN | all | **D** | Tagging only |
| LST_LRT | all | **D** | Tagging only |
| MULTI_HOP | all | **C** | RouteSearch hop budget + tag; no shadow family proof |

### 7.2 Field checklist (canonical GENERIC_DEX×Aave×ethereum as template)

| Field | Value |
|---|---|
| IMPLEMENTED? | Yes — `GenericDexRouteEngine` + `GenericDexDiscoverySource` |
| INTEGRATED INTO OPPORTUNITY PIPELINE? | Yes — M5 → verifier → Gate7 → `_tick` EmissionBus |
| QUOTE/SIM SUPPORT? | Yes — `QuoterRegistry` / live_quote_provider |
| ECONOMIC GATE SUPPORT? | Yes — Gate7 $25, Gate8 TVL fail-closed, Gate9 MEV class |
| EXECUTION PATH? | Yes for Aave+UniV3 V1 shape; SHADOW-only; not broadcast |
| SHADOW TESTED? | Yes — M6 live harness |
| PAPER/evidence tested? | No — 0 paper evidence rows |
| CERTIFIED? | SHADOW detection/econ evidence-complete; not live/profit certified |
| BLOCKER? | Empty inventory; A=0 market; not a Gate9–10 SHADOW blocker |
| EVIDENCE | `05dacdb`, M6 JSON, `M6_POST_ALCHEMY_RESET_SHADOW_20261002.md` |

---

## 8. CROSS_CHAIN special section (detection vs executable)

| Dimension | Detection | Executable / live-capable |
|---|---|---|
| Pricing comparison | **Partial D** — corridor hints + transfer quote providers (LI.FI / Stargate projectors) when injected | **E** — no executable arb planner binding both legs atomically |
| Settlement | N/A (detection) | **E** — no cross-chain settlement dispatcher; pipeline treats CROSS_CHAIN gas as **nominal 1%** only |
| Inventory | Config metadata (`bridge_inventory_pct` vocab in pending/substrate tests) | **E** — no capital inventory manager for bridges |
| Bridge / intent / solver | Bridge catalog + transfer_provider HTTP quotes (`lifi_quote_real`, `stargate_quote_real`) | **E** — no intent/solver execution path; Stargate marked deprecated/dormant in provider comments |
| Atomicity | Explicitly **non-atomic** family (multi-tx bridge) | **E** — no atomic cross-domain flash |
| Execution | Scanner emit only; mode dormant by default | **E** — not in V1 flash receiver; composition boots scanner dormant |
| Reconciliation | Outcome loader tests exist (D-5.2) | **E** — no live reconcilation/ops certified |
| Failure recovery | Fail-closed deny when transfer provider no-op | **E** |
| SHADOW evidence | **No** M6/M5 six-chain SHADOW campaign for CROSS_CHAIN | — |
| Live-capable | **No** | **No** |

**Classification:** CROSS_CHAIN overall = **D** (detection substrate present, dormant) / executable = **E**.  
**Do not conflate** with flash-loan GENERIC_DEX SHADOW evidence.

Evidence: `scanners/cross_chain_arbitrage/{scanner,sources,verifier,transfer_provider,economics,filter}.py`; `composition.get_cross_chain_arb_scanner`; tests `test_d5_*`; `DEFAULT_CROSS_CHAIN_ARB_CONFIG`.

---

## 9. Quote, economic gates, and execution path (system-wide)

| Layer | Status | Binding proof |
|---|---|---|
| QuoterRegistry | Implemented; multi-DEX backends | `execution/quoter.py` default_backends (UniV3, Aero, Sushi, Pancake, Camelot, QuickSwap, Balancer) |
| Live quote provider | Multichain; M5 venue-identity path | `live_quote_provider.py` |
| Gate 7 atomic profit | **$25** immutable floor in certified filter | M6 gate7 block; `filter.FlashLoanGate7AtomicProfit` |
| Gate 8 TVL | Fail-closed $100k / unverifiable deny | M6 gate8; TVL provider gaps remain |
| Gate 9 MEV (flash) | Class thresholds in config | `FlashLoanGate9FlashLoanMev` |
| H05 exact-size | Env-gated **OFF** | M6 `h05_exact_size.exercised_in_m6=false` |
| V1 execution heads | Flash: Aave + Balancer; Swaps: UniV3 only | `executor_capability.SUPPORTED_*`; `CALLDATA_ENCODABLE_FLASH` |
| V2 profile (not live) | Wider DEX set + Morpho flash | `RECEIVER_CAPABILITY_PROFILES["v2"]` — effective only when V2 receiver deployed+verified |
| OpportunityPipeline paper/shadow | Terminates at SHADOW_RECORDED; no broadcast in SHADOW/PAPER | `execution/pipeline.py`; paper audit |
| Mode ladder | flash_loan_arbitrage default SHADOW | `execution/mode.py` |

---

## 10. SHADOW and PAPER evidence summary

### 10.1 M6 POST-ALCHEMY-RESET SHADOW (2026-10-02T06:36:23Z)

| Bucket | Count |
|---|---|
| A real profitable (Gate7) | **0** |
| B economically rejected | **10** |
| C quote failures | **8** |
| D liquidity failures | **0** |
| E gas failures | **14** |
| F RPC/data failures | **0** |

- Activation sources registered: `route_search`, `provider_health`, `generic_dex`, `triangular`, `balancer_v2`
- Discovery smoke candidates: **0** (inventory empty; Balancer P1b polygon error)
- Alchemy monthly 429: **CLEARED** (key fp `5e5d5bb1`); Free-tier getLogs range still limits P1b
- Disposition: **PASS (evidence-complete)** — remain SHADOW

### 10.2 Paper Gate 9–10 (20261002T072116Z)

| Gate | Result |
|---|---|
| Gate 9 (24h + non-neg paper PnL) | **CONDITIONAL** — runner ≈1.04h; evidence total **0**; PnL $0 |
| Gate 10 (72h + drawdown) | **CONDITIONAL** — same short window |

Safety posture held (SHADOW, AUTOEXEC/RUNTIME off, six-chain RPC PASS).

### 10.3 What is *not* evidenced

- Continuous ≥24h / ≥72h unbroken paper-validation window
- Any `EXECUTABLE` paper fills / cumulative paper PnL series
- Live triangular / Balancer-flash GENERIC_DEX / Morpho / UniV3-flash routes
- CROSS_CHAIN SHADOW campaign
- Limited-live / signing / broadcast

---

## 11. Blockers and MINIMUM exact delta (DO NOT IMPLEMENT)

### 11.1 Campaign blockers for Gate 9–10 SHADOW?

| Item | Blocks 24h/72h SHADOW? |
|---|---|
| A=0 profitable | **No** (honest SHADOW outcome; continue measuring) |
| Empty DiscoverySource inventory | **No** (harness/library path still validates quotes; ops may later load pools) |
| Balancer subgraph unset | **No** |
| Alchemy Free getLogs range | **No** for Gate9–10 SHADOW continuity |
| STABLECOIN/LST/MULTI_HOP/Morpho/UniV3-flash/XCHAIN executable gaps | **No** — deferred capability work |
| Paper evidence = 0 / short window | **Yes for Gate9–10 PASS claim** — resolved by **time continuity**, not code |

### 11.2 MINIMUM exact delta (ops only — do not implement code)

1. Keep `ARBICORE_EXECUTION_MODE=SHADOW`, `ARBICORE_AUTOEXEC_AUTOSTART=false`, `ARBICORE_RUNTIME_AUTOSTART=false`.
2. Keep `ARBICORE_PAPER_VALIDATION_ENABLED=true` (already used for Gate9–10 stamp).
3. Do **not** weaken Gate7/8; do **not** enable H05 live exact-size for this campaign.
4. Sustain unbroken runner/process window ≥24h then ≥72h; collect `arbicore_paper_evidence` / validation metrics (see `PAPER_VALIDATION_MINIMAL_DELTA_PLAN_20261002.md`).
5. Optional non-code: operator may later set `ARBICORE_BALANCER_SUBGRAPH_URL_<CHAIN>` — **not required** to continue SHADOW campaign.

### 11.3 Deferred capability deltas (explicitly NOT required before SHADOW campaign)

| Delta | Why deferred |
|---|---|
| Dedicated STABLECOIN / LST_LRT discovery+eval | Currently tagging-only (**D**) |
| First-class MULTI_HOP family validation | Hop budget exists; no shadow campaign |
| Wire Morpho into scanner_config + V2 receiver deploy | V1 cannot settle Morpho |
| UniV3 flash on receiver + calldata | Settlement rejects today |
| Fix Aave adapter `supports_chains` to include bnb (if desired) | Catalog/probe vs adapter mismatch |
| CROSS_CHAIN executable / inventory / solver | Detection-only by design |
| Pool inventory for DiscoverySource smoke >0 | Ops/data; not Gate9–10 code gate |
| Executor V2 on-chain for multi-DEX settle | Expand EXEC beyond UniV3 |

---

## 12. Gate 9–10 SHADOW go/no-go and FINAL STATUS

### Go / no-go

| Decision | Verdict |
|---|---|
| Continue 24h/72h Gate 9–10 **SHADOW** campaign now? | **GO** |
| Complete/validate a missing route/flash capability first? | **NO** — not a prerequisite |
| Promote PAPER / LIMITED_LIVE / AUTOEXEC / RUNTIME? | **NO** |
| Claim Gate 9/10 **PASS** today? | **NO** — prior stamp CONDITIONAL; need continuity + evidence |

### FINAL STATUS

# **READY**

Ready to **continue** the Gate 9–10 SHADOW campaign under existing safety posture. Capability matrix remains incomplete (many **C/D/E** cells); incompleteness is **documented and deferred**, not a campaign blocker.

---

## Appendix A — Quick reference class heatmaps

### Route family × chain (summary)

| Family | eth | arb | base | op | poly | bnb |
|---|---|---|---|---|---|---|
| GENERIC_DEX | B | B | C | B | C | C |
| TRIANGULAR | C | C | C | C | C | C |
| STABLECOIN | D | D | D | D | D | D |
| MULTI_HOP | C | C | C | C | C | C |
| LST_LRT | D | D | D | D | D | D |
| CROSS_CHAIN | D* | D* | D* | D* | D* | D* |

\*Detection substrate; executable = E globally.

### Flash provider × chain (summary)

| Provider | eth | arb | base | op | poly | bnb |
|---|---|---|---|---|---|---|
| Aave V3 | B | B | B | B | B | C |
| Balancer V2 | B | C | C | C | C | N/A |
| UniV3 flash | C | C | C | C | C | N/A |
| Morpho Blue | C | N/A | C | N/A | N/A | N/A |

---

## Appendix B — STOP

No source changes. No config edits. No rebuild/deploy. No Gate changes. No PAPER/AUTOEXEC/RUNTIME enable. No execution. Audit ends here.
