# Flash-Loan Discovery — Six-Chain Pipeline Verification — 2026-10-04

- **Classification:** **SIX_CHAIN_PIPELINE_PARTIAL**
- **Wall-clock start (UTC):** `2026-10-04T03:00:23Z`
- **Wall-clock end (UTC):** `2026-10-04T03:47:08Z`
- **Budget:** 45 minutes from poll start
- **Stopped early because all six completed:** **no** (budget exhausted; five chains still missing exact-size borrow sizing and/or profitability evaluation)
- **Prior readiness:** [FLASH_LOAN_DISCOVERY_RUNTIME_READINESS_20261004.md](./FLASH_LOAN_DISCOVERY_RUNTIME_READINESS_20261004.md) (`PIPELINE_WORKING_VERIFICATION_PARTIAL`)

Verification only. No redeploy, no Network Config / RPC / Alchemy A→B change, no TVL or $25 profit-gate change, no PAPER/LIVE enablement, no signing, no broadcast, no long SHADOW campaign. Coordinated with the already-running container by read-only log/metrics/Mongo evidence collection.

---

## 1. Runtime identity (unchanged)

| Field | Observed |
|---|---|
| Container | `arbicore-x-backend-new` |
| Image | `arbicore-x-backend:flash-discovery-readiness-9ed2718` |
| Started | `2026-10-03T19:19:43Z` (RestartCount 0; healthy throughout) |
| Network Config revision | `rev-d069f13244ba44da81f97e72f7cfce5b` |
| Scanner state `flash_loan_arb.enabled` | true (`operator_resume`) |
| `route_search.min_pool_tvl_usd` | 100000 |
| `gate_thresholds.default.min_atomic_profit_usd` | 25.0 |
| `flash_loan_arbitrage` mode | SHADOW (unchanged since 2026-09-07) |
| Long SHADOW `status=RUNNING` | 0 |
| `broadcast=true` on verifier bundles (since resume) | 0 |
| Confirmed verifier bundles (since resume) | 0 |

No concurrent container recreate was observed during the poll window.

---

## 2. Pipeline stage definition

A chain is counted **complete** only when evidence shows all of:

1. discovery candidates  
2. routes  
3. TVL measurement  
4. exact-size quote (`quotes.size_basis=exact` / `exact_size=true`)  
5. borrow sizing accepted (exact-size path, not probe)  
6. profitability evaluation (Gate 7 `PASS` or `FAIL`)

Base was accepted from prior readiness plus reconfirmed in this window. Focus chains: Ethereum, Arbitrum, Optimism, Polygon, BNB.

---

## 3. Verification-window discovery (candidates / routes / TVL)

New `FLASH_LOAN_ARBITRAGE` candidates with ObjectId ≥ `2026-10-04T03:00:23Z` (poll window). Every counted row had non-empty `candidate_venues` (route present).

| Chain | Candidates | Routes | TVL > 0 | TVL ≥ $100k | Max `min_tvl_usd` | Sources | Flash providers on new rows |
|---|---:|---:|---:|---:|---:|---|---|
| Ethereum | 12,225 | 12,225 | yes | yes | ~$47.0M | route_search, generic_dex, triangular | aave_v3, balancer_v2, uniswap_v3 |
| Arbitrum | 11,583 | 11,583 | yes | yes | ~$8.0M | route_search, generic_dex, triangular | aave_v3, balancer_v2, uniswap_v3 |
| Base | 8,153 | 8,153 | yes | yes | ~$8.8M | route_search, generic_dex | aave_v3, balancer_v2, uniswap_v3 |
| Optimism | 3,744 | 3,744 | yes | yes (subset) | ~$277k | route_search, generic_dex, triangular | aave_v3, balancer_v2, uniswap_v3 |
| Polygon | 9,036 | 9,036 | yes | yes | ~$427k | route_search, generic_dex, triangular | aave_v3, balancer_v2, uniswap_v3 |
| BNB | 2,688 | 2,688 | yes | yes | ~$5.2M | route_search, generic_dex, triangular | **aave_v3 only** |

BNB remains Aave-only on new candidates (Balancer/Uniswap flash providers absent), matching catalog scope from the readiness report.

Prior coverage audit (discovery + routes + TVL on all six) is not re-litigated; the table above shows the same stages continuing during this poll.

---

## 4. Verifier evidence — poll window (`created_at` ≥ `2026-10-04T03:00:23Z`)

| Chain | Bundles | Quote `ok` | Exact-size | Profit eval (Gate 7) | Dominant denials | Confirmed |
|---|---:|---:|---:|---:|---|---:|
| Base | 123 | 80 | **80** | **80 FAIL** | 43 `venue_unreadable`; 80 Gate 7 `$25` floor fails | 0 |
| Ethereum | 1,018 | 218 | **0** | **0** | 800 `venue_unreadable`; 218 `size_not_quoted` (`size_basis=probe`) | 0 |
| Arbitrum | 0 | 0 | 0 | 0 | verifier never claimed | 0 |
| Optimism | 0 | 0 | 0 | 0 | verifier never claimed | 0 |
| Polygon | 0 | 0 | 0 | 0 | verifier never claimed in this window | 0 |
| BNB | 0 | 0 | 0 | 0 | verifier never claimed | 0 |

### Stage samples (poll window)

**Base (complete path):** bundle `2026-10-04T03:32:55Z` — `route_quote_status=ok`, `size_basis=exact`, `exact_size=true`, Gate 7 `FAIL` `atomic_profit $-176.04 < floor $25.00`, provider `balancer_v2`, `broadcast=false`.

**Ethereum (blocked before profitability):** bundle `2026-10-04T03:44:24Z` — `route_quote_status=ok` with hop depths, but `size_basis=probe`, `exact_size=false`, outcome `denied:size_not_quoted`, Gate 7 `NOT_EVALUATED`.

---

## 5. Cumulative verifier context since scanner resume (`≥ 2026-10-03T19:24:00Z`)

Used only to show whether any non-Base chain ever cleared exact-size / Gate 7 before or during this poll (they did not).

| Chain | Bundles | Quote `ok` | Exact-size | Profit eval | Notes |
|---|---:|---:|---:|---:|---|
| Base | 1,598 | 1,069 | **1,069** | **1,069 FAIL** | Full pipeline; all quoted exact-size rows failed $25 floor |
| Ethereum | 8,910 | 2,059 | **0** | **0** | Quotes exist; all sized as probe → `size_not_quoted` |
| Polygon | 32 | 0 | 0 | 0 | All `venue_unreadable` (last at `2026-10-03T23:48:53Z`) |
| Arbitrum | 0 | 0 | 0 | 0 | Discovery only |
| Optimism | 0 | 0 | 0 | 0 | Discovery only |
| BNB | 0 | 0 | 0 | 0 | Discovery only |

Prior readiness already documented Base’s first 42 exact-size Gate 7 fails; this window adds continuous Base Gate 7 evaluation (80 more exact-size fails in-window; 1,069 cumulative since resume).

---

## 6. Per-chain pipeline verdict

| Chain | Discovery | Route | TVL | Exact-size quote | Borrow sizing | Profitability eval | Verdict |
|---|---|---|---|---|---|---|---|
| Base | yes | yes | yes | yes | yes (`exact`) | yes (Gate 7 FAIL) | **COMPLETE** |
| Ethereum | yes | yes | yes | quotes ok, **not exact** | **blocked** (`probe` → `size_not_quoted`) | **not reached** | **INCOMPLETE** |
| Arbitrum | yes | yes | yes | no verifier bundle | no | no | **INCOMPLETE** |
| Optimism | yes | yes | yes | no verifier bundle | no | no | **INCOMPLETE** |
| Polygon | yes | yes | yes | no successful quote (`venue_unreadable` only historically) | no | no | **INCOMPLETE** |
| BNB | yes | yes | yes (Aave-only) | no verifier bundle | no | no | **INCOMPLETE** |

---

## 7. Why unfinished chains did not reach quote / sizing / profitability

1. **Ethereum — quoting works; exact-size borrow sizing does not.**  
   218 in-window (2,059 cumulative) routes returned `route_quote_status=ok`, then were denied as `size_not_quoted` because `size_basis=probe` / `exact_size=false`. Gate 7 is never evaluated on those rows. This matches the readiness finding that the wired USD sizer is Base-scoped; non-Base exact-size was not demonstrated and was not extended in this verification-only gate.

2. **Arbitrum / Optimism / BNB — verifier never claimed them in ~45 minutes.**  
   Discovery, routes, and TVL continued (thousands of new candidates each). Zero `flash_loan_arb_verifier` bundles. Claim traffic stayed on Base and Ethereum (large historical queue + Base/ETH claim affinity). Without a verifier bundle there is no exact-size quote, sizing, or Gate 7 record.

3. **Polygon — verifier historically fail-closed; none in this window.**  
   32 cumulative bundles since resume, all `denied:venue_unreadable`, last at `2026-10-03T23:48:53Z`. Poll window: 0 new Polygon bundles. No quote_ok, no exact-size, no Gate 7.

4. **Not a market-profit blocker for the unfinished five.**  
   Base alone proves Gate 7 is live ($25 floor). The unfinished chains did not reach that evaluation step.

5. **Safety boundaries held.**  
   No confirmed candidates, no broadcast, no long SHADOW, flash strategy remains SHADOW, scanner left enabled as found.

---

## 8. Classification rationale

**SIX_CHAIN_PIPELINE_VERIFIED** requires all six chains through exact-size quote → borrow sizing → profitability evaluation. Only **Base** clears that bar.

**SIX_CHAIN_PIPELINE_BLOCKED** would require runtime inability to proceed on the pipeline as a whole (e.g. scanner down, wrong image/config, deploy fight). Container stayed healthy on the expected image/revision; discovery kept emitting on all six; Base continued full Gate 7 evaluation. Incomplete coverage is stage/coverage limitation, not a hard stop of the runtime.

Therefore: **SIX_CHAIN_PIPELINE_PARTIAL**.

---

## 9. Boundaries held

- Did not modify discovery code.  
- Did not deploy.  
- Did not change Network Config, RPCs, Alchemy A→B, $100k TVL, $25 profit gate, risk gates, or provider architecture.  
- Did not enable PAPER/LIVE, sign, broadcast, or start long SHADOW.  
- BNB flash providers remained Aave-only on observed candidates.

---

## 10. Stop

Procedure stops after this report. Scanner left as found (`enabled=true`). No follow-on deploy or config mutation performed.
