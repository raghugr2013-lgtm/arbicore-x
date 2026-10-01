# POST-M6 Targeted Infra SHADOW Evidence Pass

- Status: **CONDITIONAL (evidence-complete)** — infra limits confirmed; not cleared
- Date: 2026-10-02 (UTC labeling; run finished 2026-10-01T19:34:55Z)
- Branch: `phase-b/h06-six-chain-runtime`
- Machine evidence: `reports/shadow_validation/m6_post_infra_shadow_latest.json`
- Harness reuse: `scripts/m6_shadow_validation.py` + `scripts/live_shadow_validation.py` (no certified-module edits)

---

## 1. Starting SHA

`aab47f2400b3b80f89a46d957208145bcfc81ad7`  


M6 validation START SHA (reference): `7ec144009b38fd94f7a0a977b41f4a92abdef750`

## 2. Final SHA

Authoritative tip = `git rev-parse HEAD` after the POST-M6 infra evidence/docs commits (avoid self-updating this field). Evidence series starts at `aab47f2400b3b80f89a46d957208145bcfc81ad7`. STATUS block FINAL SHA is binding.


## 3. Branch

`phase-b/h06-six-chain-runtime`

## 4. M6 reference

| Item | Value |
|---|---|
| Report | `docs/certification/M6_SHADOW_VALIDATION_20261002.md` |
| JSON | `reports/shadow_validation/m6_shadow_latest.json` |
| Start SHA | `7ec144009b38fd94f7a0a977b41f4a92abdef750` |
| Final evidence SHA | `aab47f2400b3b80f89a46d957208145bcfc81ad7` |
| M6 buckets | A=0 B=2 C=29 D=0 E=1 F=0 |
| M5 tip | `05dacdb3eb3cc2f6555aee77b8a9811206891bc5` |
| M5 tag | `arbicore-m5-canonical-activation-pass-20261001` |

## 5. Exact infrastructure changes

**None applied.**

| Attempt | Outcome |
|---|---|
| Balancer subgraph env | **Not configured** — no operator `ARBICORE_BALANCER_SUBGRAPH_URL_<CHAIN>` / API key in production container; URLs not invented |
| Ethereum secondary RPC | **Not provisioned** — only single Alchemy `ARBICORE_RPC_URL_ETHEREUM`; no `PROVIDER_RPC_URLS_ETHEREUM` multi-URL already present |
| Validation env | Operator URLs mirrored 1:1 into `PROVIDER_RPC_URLS_<CHAIN>` (count=1). **Did not** invent publicnode (unlike M6 Polygon validation append) |
| App / certified modules | **No source changes** |

## 6. Balancer subgraph status

**Unavailable due to missing operator configuration.**

Existing mechanism (documented; unchanged):

- Per-chain URL: `ARBICORE_BALANCER_SUBGRAPH_URL_<CHAIN>`
- Optional bearer: `ARBICORE_BALANCER_SUBGRAPH_API_KEY`
- Implementation: `SubgraphBalancerV2PoolSource` in `balancer_v2_pool_enumeration.py`
- Fail-closed: missing URL → `discovery_unavailable` (never fabricates pools)

Production container (`arbicore-x-backend-new`): all five Balancer-chain subgraph vars **UNSET**; API key **UNSET**. `GRAPH_GATEWAY_API_KEY` empty. No legitimate operator subgraph URL available to configure.

## 7. Ethereum RPC / P1b status

**Precise failure mode: operator Alchemy monthly capacity exhaustion (HTTP 429).**

| Probe | Result |
|---|---|
| Direct `eth_blockNumber` | HTTP **429**, JSON-RPC error `Monthly capacity limit exceeded...` |
| Direct `eth_chainId` | HTTP **429** (same capacity message) |
| `eth_getLogs` (200-block) | Skipped — block number unresolved |
| Registry P1b (`make_eth_get_logs_for_chain_from_env`) | `discovery_unavailable` — `latest block unresolved: ProviderError` (underlying 429; single endpoint exhausted; failover has nowhere to go) |
| Harness P1b (window=50000) | `discovery_unavailable` — `latest block unresolved: HTTPStatusError` |
| Known-pool P0 (80BAL-20WETH) | `rpc_error` (fail-closed) |
| Secondary operator RPC | **Not configured** (`provider_urls_count=1`) |
| App defect? | **No** — fail-closed correct; do not patch certified RPC seams for capacity |

Same Alchemy 429 class observed on arbitrum / optimism / polygon / bnb. **Base** uses `mainnet.base.org` (non-Alchemy) and remains healthy for P1b.

## 8. Six-chain Balancer results

| Chain | P1 subgraph | P1b on-chain | P0 |
|---|---|---|---|
| ethereum | `discovery_unavailable` (URL unset) | `discovery_unavailable` (429 capacity) | `rpc_error` |
| arbitrum | `discovery_unavailable` (URL unset) | `discovery_unavailable` (429) | n/a |
| base | `discovery_unavailable` (URL unset) | **`ok`** (0 candidates; honest empty window) | n/a |
| optimism | `discovery_unavailable` (URL unset) | `discovery_unavailable` (429) | n/a |
| polygon | `discovery_unavailable` (URL unset) | `discovery_unavailable` (429) | n/a |
| bnb | Balancer V2 unsupported on vault map | — | — |

No synthetic pools. Existing `BalancerV2Quoter` / QuoterRegistry / Gate 7 untouched.

## 9. GenericDex results

Six chains exercised via live `QuoterRegistry` (real quotes only). Alchemy chains largely quote-fail / endpoint reject under 429 (`eth_chainId mismatch/unreadable` fail-closed skip). Base still produced real B/E outcomes.

| Chain | Summary (this pass) |
|---|---|
| ethereum | C=2 |
| arbitrum | C=8 |
| base | B=2, C=4, E=2 |
| optimism | C=2 |
| polygon | C=6 |
| bnb | C=6 |

## 10. Triangular results

- `TriangularDiscoverySource` registered (`flash_loan_triangular`)
- Gate 7 authoritative; library default `min_net_profit_usd=25.0` — **no $35 drift**
- Discovery smoke candidates: 0 (empty pool inventory in harness — not fabricated)

## 11. Counts A/B/C/D/E/F

From GENERIC_DEX live evaluations (`m6_post_infra_shadow_latest.json`):

| Bucket | Count |
|---|---|
| **A** Real profitable (Gate 7) | **0** |
| **B** Real economically rejected | **2** |
| **C** Quote failures | **28** |
| **D** Liquidity failures | **0** |
| **E** Gas failures | **2** |
| **F** RPC/data failures | **0** |

A=0 remains valid. Compared with M6 (C=29 E=1): small C/E shift under depleted Alchemy capacity; **not** profitability manufacturing.

## 12. Gate 7 result

| Check | Result |
|---|---|
| Floor | **$25.00** |
| Rejects $24.99 | Yes |
| Accepts $25.00 | Yes |
| Triangular library default | 25.0 |
| Verdict | **PASS — not lowered** |

## 13. Gate 8 result

| Check | Result |
|---|---|
| Floor | $100,000 min pool TVL |
| Unverifiable TVL | fail-closed deny |
| Weakened? | **No** |
| Verdict | **FAIL-CLOSED (as designed)** |

## 14. H05 result

| Item | Status |
|---|---|
| `ARBICORE_PRICE_FEED_ENABLED` | false |
| `ARBICORE_BORROW_SIZER_ENABLED` | false |
| Exact-size path | **disabled_by_environment** |
| Live exact-size | not exercised |
| Verdict | **FAIL-CLOSED / env-gated OFF** |

## 15. RPC / failover result

| Check | Result |
|---|---|
| Canonical failover | Present (`RegistryRpcProvider` / `PROVIDER_RPC_URLS_<CHAIN>`) |
| Ethereum multi-URL | **No** — single Alchemy; failover exhausts immediately on 429 |
| Polygon this pass | Configured (1 endpoint); `multi_url_provisioned=false`; getLogs probe transport-error under capacity / registry bootstrap in harness window |
| vs M6 | M6 temporarily appended publicnode for Polygon in validation env only; **this pass did not invent secondaries** |
| Verdict | Failover architecture OK; **operator capacity/config is the blocker** |

## 16. Test results

| Suite | Result |
|---|---|
| M5 activation + H05/H06 + RPC + Balancer P0/P1/P1b + GenericDex + Gate7 economics | **252 passed** |
| Shadow cert / shadow route (`test_v2119_*`, `test_m2_4_shadow_route`) | **14 passed** |
| `test_wave6b_shadow_invariant.py` collection without `REACT_APP_BACKEND_URL` | ERROR (AttributeError) — **pre-existing env requirement**; collects 9 tests when URL set |
| Tests weakened / deleted | **None** |

## 17. Safety posture

| Variable / check | Value |
|---|---|
| `ARBICORE_EXECUTION_MODE` | `SHADOW` |
| `ARBICORE_SHADOW_CERT_ENABLED` | `true` |
| `ARBICORE_SCANNER_AUTOSTART` | `true` |
| `ARBICORE_AUTOEXEC_AUTOSTART` | `false` |
| `ARBICORE_RUNTIME_AUTOSTART` | `false` |
| PAPER / LIMITED_LIVE | OFF |
| Signing | **NOT REACHED** |
| Broadcast | **0** |
| Funds moved | **0** |
| Production deploy | **NO** |

## 18. Whether source code changed

**NO.** Evidence/docs + JSON reports only.

## 19. Exact Git diff if source code changed

N/A — no source diff. Evidence scope:

- `docs/certification/M6_POST_INFRA_SHADOW_20261002.md`
- `reports/shadow_validation/m6_post_infra_shadow_*.json` / `m6_post_infra_shadow_latest.json`

## 20. Final disposition

**CONDITIONAL (evidence-complete).**

POST-M6 targeted infra pass establishes that **A=0 is partly explained by observation/infrastructure limits**, specifically:

1. Alchemy **HTTP 429 monthly capacity** on ethereum (and other Alchemy chains) — blocks Balancer P1b getLogs/P0 and dominates GenericDex quote failures
2. Balancer P1 subgraph **unset** — correct fail-closed; needs operator URLs
3. No secondary operator RPC already configured — existing failover cannot remediate single-endpoint capacity exhaustion without inventing endpoints (forbidden)

Base Balancer P1b remains healthy. Gate 7 stays $25; Gate 8 fail-closed; H05 off; signing/broadcast/AUTOEXEC/RUNTIME untouched. **Remain SHADOW.**

### Next action (operator / evidence only)

Restore Alchemy capacity **and/or** provision legitimate secondary operator RPCs via existing `PROVIDER_RPC_URLS_<CHAIN>` (and optional `ARBICORE_BALANCER_SUBGRAPH_URL_<CHAIN>`). Then re-run this POST-M6 SHADOW evidence pass. Do **not** start Stablecoin/LST/Morpho/cross-chain capability work; do **not** promote modes.

## STOP

No paper execution. No live trading. No production deploy. No AUTOEXEC/RUNTIME enable. No Gate 7/8 weaken. No invented endpoints.
