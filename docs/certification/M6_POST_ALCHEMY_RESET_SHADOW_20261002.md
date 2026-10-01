# POST-ALCHEMY-RESET SHADOW Evidence Pass

- Status: **CONDITIONAL (evidence-complete)** — operator-claimed Alchemy Free reset did **not** clear monthly capacity on the live operator key
- Date: 2026-10-02 (UTC labeling; run finished 2026-10-01T19:52:07Z)
- Branch: `phase-b/h06-six-chain-runtime`
- Machine evidence: `reports/shadow_validation/m6_post_alchemy_reset_latest.json`
- RPC probe: `reports/shadow_validation/post_alchemy_reset_probe.json`
- Harness reuse: `scripts/m6_shadow_validation.py` + `scripts/live_shadow_validation.py` (no certified-module edits)

---

## 1. Starting SHA

`a9c6968db907258c90bc128a89cbab20a3be327f`

Post-M6 FINAL tip (also POST-M6 START for this retest). Prior POST-M6 series START: `aab47f2400b3b80f89a46d957208145bcfc81ad7`.

## 2. Final SHA

Authoritative tip = `git rev-parse HEAD` after the POST-ALCHEMY-RESET evidence/docs commit (avoid self-updating this field). STATUS block FINAL SHA is binding.

## 3. Branch

`phase-b/h06-six-chain-runtime`

## 4. Prior evidence references

| Item | Value |
|---|---|
| Post-M6 report | `docs/certification/M6_POST_INFRA_SHADOW_20261002.md` |
| Post-M6 JSON | `reports/shadow_validation/m6_post_infra_shadow_latest.json` |
| Post-M6 START | `aab47f2400b3b80f89a46d957208145bcfc81ad7` |
| Post-M6 FINAL | `a9c6968db907258c90bc128a89cbab20a3be327f` |
| Post-M6 buckets | A=0 B=2 C=28 D=0 E=2 F=0 |
| M6 report | `docs/certification/M6_SHADOW_VALIDATION_20261002.md` |
| Operator claim | Alchemy Free plan reset; CU shown as `0 / 30,000,000 remaining` |

## 5. Exact infrastructure / code changes

**None applied.**

| Attempt | Outcome |
|---|---|
| Alchemy plan upgrade | **Not done** (forbidden) |
| Invented / public RPC endpoints | **Not added** |
| Balancer subgraph URLs | **Still unset** — not invented |
| Failover architecture / Gate 7 / Gate 8 | **Unchanged** |
| PAPER / AUTOEXEC / RUNTIME | **Not enabled** |
| App / certified modules | **No source changes** |

Operator RPC URLs mirrored 1:1 into `PROVIDER_RPC_URLS_<CHAIN>` (count=1) for canonical registry path only.

## 6. TASK 1 — Six-chain RPC / failover health

Hosts redacted only:

| Chain | RPC host | Health | HTTP (eth_blockNumber) | eth_call | eth_getLogs (Balancer vault, 200 blk) | Failure type |
|---|---|---|---|---|---|---|
| ethereum | `eth-mainnet.g.alchemy.com` | unhealthy | **429** | fail | skipped (no block) | `alchemy_monthly_capacity_429` |
| arbitrum | `arb-mainnet.g.alchemy.com` | unhealthy | **429** | fail | skipped | `alchemy_monthly_capacity_429` |
| base | `mainnet.base.org` (non-Alchemy) | **healthy** | 200 | ok | ok | none |
| optimism | `opt-mainnet.g.alchemy.com` | unhealthy | **429** | fail | skipped | `alchemy_monthly_capacity_429` |
| polygon | `polygon-mainnet.g.alchemy.com` | unhealthy | **429** | fail | skipped | `alchemy_monthly_capacity_429` |
| bnb | `bnb-mainnet.g.alchemy.com` | unhealthy | **429** | fail | skipped (no vault) | `alchemy_monthly_capacity_429` |

Ethereum direct JSON-RPC error (verbatim class):

> `Monthly capacity limit exceeded. Visit https://dashboard.alchemy.com/settings/billing to upgrade your scaling policy for continued service.`

Canonical failover (`RegistryRpcProvider` / `PROVIDER_RPC_URLS_<CHAIN>`): present; single endpoint → exhausts immediately on 429. **No secondary operator RPC configured.** Failover architecture OK; capacity is the blocker.

**Verdict:** Operator-claimed reset is **not observed** on the live key wired into `arbicore-x-backend-new`. Capacity **not cleared**.

## 7. TASK 2 — Balancer P1 / P1b / P0

| Chain | P1 subgraph | P1b on-chain | P0 known-pool |
|---|---|---|---|
| ethereum | `discovery_unavailable` (URL unset) | `discovery_unavailable` (429 capacity) | `rpc_error` (80BAL-20WETH) |
| arbitrum | `discovery_unavailable` (URL unset) | `discovery_unavailable` (429) | n/a |
| base | `discovery_unavailable` (URL unset) | **`ok`** (0 candidates; honest empty window) | n/a |
| optimism | `discovery_unavailable` (URL unset) | `discovery_unavailable` (429) | n/a |
| polygon | `discovery_unavailable` (URL unset) | `discovery_unavailable` (429) | n/a |
| bnb | Balancer V2 unsupported on vault map | — | — |

Subgraph vars still **UNSET** in production container. No invented pools / subgraph URLs.

## 8. TASK 3 — Canonical SHADOW harness

Reused `scripts/m6_shadow_validation.py` (GenericDex + Triangular + Balancer + QuoterRegistry + H05/H06 + Gate7/8). Real data only.

| Bucket | This pass | Prior POST-M6 |
|---|---|---|
| **A** Real profitable (Gate 7) | **0** | 0 |
| **B** Real economically rejected | **2** | 2 |
| **C** Quote failures | **28** | 28 |
| **D** Liquidity failures | **0** | 0 |
| **E** Gas failures | **2** | 2 |
| **F** RPC/data failures | **0** | 0 |

**C failures from Alchemy capacity did not disappear.** Counts identical to POST-M6. A=0 remains valid.

GenericDex by chain: ethereum C=2; arbitrum C=8; base B=2,C=4,E=2; optimism C=2; polygon C=6; bnb C=6.

Triangular: DiscoverySource registered; Gate 7 library default 25.0; 0 discovery candidates (empty pool inventory — not fabricated).

## 9. Gate 7 / Gate 8 / H05

| Check | Result |
|---|---|
| Gate 7 floor | **$25.00** — rejects $24.99, accepts $25.00 — **PASS — not lowered** |
| Gate 8 floor | $100,000 min pool TVL; unverifiable TVL fail-closed — **not weakened** |
| H05 | price feed / borrow sizer env-gated **OFF** |

## 10. Safety posture

| Variable / check | Value |
|---|---|
| `ARBICORE_EXECUTION_MODE` | `SHADOW` |
| `ARBICORE_SHADOW_CERT_ENABLED` | `true` |
| `ARBICORE_SCANNER_AUTOSTART` | `true` |
| `ARBICORE_AUTOEXEC_AUTOSTART` | `false` |
| `ARBICORE_RUNTIME_AUTOSTART` | `false` |
| Signing / broadcast / funds moved | **NOT REACHED / 0** |
| Production deploy | **NO** |

## 11. Offline tests (unchanged suite)

| Suite | Result |
|---|---|
| M5 + H05/H06 + GenericDex + Balancer P0/P1/P1b + SP1–SP5 + shadow route | **295 passed** (13 warnings; network=none) |
| Tests weakened / deleted | **None** |

## 12. Whether source code changed

**NO.** Evidence/docs + JSON reports only.

## 13. Final disposition

**CONDITIONAL (evidence-complete).**

POST-ALCHEMY-RESET retest shows the **same** Alchemy monthly-capacity HTTP 429 class on ethereum/arbitrum/optimism/polygon/bnb as POST-M6. Base (non-Alchemy `mainnet.base.org`) remains healthy for P1b. Economic buckets unchanged (A=0 B=2 C=28 D=0 E=2 F=0). Gate 7 stays $25; Gate 8 fail-closed; H05 off; signing/broadcast/AUTOEXEC/RUNTIME untouched.

### Operator follow-up (evidence only)

1. Confirm the Alchemy **app / API key** that was reset is the **same** key embedded in `ARBICORE_RPC_URL_{ETHEREUM,ARBITRUM,OPTIMISM,POLYGON,BNB}` on `arbicore-x-backend-new` (dashboard “CU remaining” may refer to a different app).
2. Or provision a legitimate secondary operator RPC via existing `PROVIDER_RPC_URLS_<CHAIN>` (do not invent public endpoints).
3. Optional: supply `ARBICORE_BALANCER_SUBGRAPH_URL_<CHAIN>` for P1.
4. Re-run this POST-ALCHEMY-RESET pass after the live key actually serves non-429 responses.

Do **not** start Stablecoin/LST/Morpho/cross-chain capability work; do **not** promote modes; do **not** upgrade Alchemy plan from this agent.

## STOP

No paper execution. No live trading. No production deploy. No AUTOEXEC/RUNTIME enable. No Gate 7/8 weaken. No invented endpoints. No source patches for capacity.
