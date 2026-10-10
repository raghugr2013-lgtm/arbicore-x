# G1.5 Offline Base Winner ↔ ArbiCore Route Universe Coverage Audit

**Status:** READ-ONLY / OFFLINE  
**Generated:** 2026-10-09  
**Verdict (next research step only):** **GO — coverage research**  
**Hot-path / latency remediation:** **NO-GO** (not justified by this evidence)  
**Live trading / code changes / deploy:** **NOT AUTHORIZED**

---

## 1. Evidence and revisions inspected

### Frozen G1.5 export
| Item | Value |
|---|---|
| Path | `artifacts/g15/core-20261008T2216Z/G1_5_EXPORT_20261008T2216Z/` |
| Winners JSONL | `MEV_SCOUT_BASE_BSC_WINNERS_G1_5.jsonl` (27,307 rows; Base 6,287; BNB 21,020) |
| Base window | 2026-10-08 00:00 → 17:59 UTC, blocks 52314127–52346526 |
| Supporting | contract ledger, `out/identity_base.json`, `out/survival_base.json`, `out/segments.json`, `REPORT.md`, `MANIFEST.json` |
| Manifest note | Essential files previously size/SHA-256 validated (per task input) |

### ArbiCore runtime (comparison target, read-only)
| Item | Value |
|---|---|
| Container | `arbicore-x-backend-new` |
| Image / tag | `hybrid-e-rpc-9244ebd` |
| `BUILD_INFO.json` | `git_sha=fff0d0eced5ce3783cff18fb976e55a2a6504504`, `build_time=2026-10-08T07:58:15Z` |
| Base venue source | `/app/arbicore/discovery/base_venues.py` (30 curated venues, 12 tokens) |
| Pool identity | `/app/arbicore/discovery/base_pool_registry.py` |
| Registry at snapshot | 19 UniV3 `deterministic_verified` addresses; 11 Aerodrome `runtime_getpool`; **0** `runtime_resolved` |

### Runtime telemetry inspected (read-only Mongo)
| Collection | Window use |
|---|---|
| `decision_history` | 8,136 Base decisions in 2026-10-08 00:00–18:00 UTC |
| `arbicore_discovery_candidates` | **0** docs with `hint_observed_at` in window |
| `route_recurrence` | 134 routes; Base UniV3/Aerodrome cycles from curated graph |
| `arbicore_opportunities` | empty |

Frozen universe snapshot written to:  
`artifacts/g15/audit_offline_base_replay_20261009/arbicore_base_universe_snapshot.json`

---

## 2. Matching methodology

### Identifiers used (defensible)
1. **Pool address** (lowercase) vs ArbiCore resolved pool address set (19 UniV3 CREATE2 addresses only).
2. **Leg venue label** mapped to ArbiCore dex family:
   - `UniswapV3` → `uniswap_v3`
   - `Aerodrome-Slipstream{,2,3}` → `aerodrome_slipstream`
   - `Aerodrome-V2` → `aerodrome`
   - `UniswapV4` / `UniV4*` / `PancakeV3` / `Curve` / `AlgebraIntegral*` / `UniswapV2` / other → **unsupported**
3. **Token addresses** vs ArbiCore `TOKENS` (12 Base majors).
4. **Route-family (sensitivity only):** every hop’s `(mapped_dex, token_in_symbol, token_out_symbol)` exists as an undirected pair in `base_venues.VENUES`.

### Explicitly rejected as a match
- Token-symbol overlap alone.
- “Supported venue atom present” without pool or full hop-pair coverage.
- Inferring Aerodrome pool identity (registry `runtime_resolved=0`; no RPC allowed).

### Match tiers
| Tier | Meaning | Confidence |
|---|---|---|
| `EXACT_POOL_AND_VENUE` | All listed pools ∈ resolved address set **and** all leg venues supported | High |
| `PARTIAL_POOL_UNSUPPORTED_VENUE` | All listed pools resolved, but ≥1 unsupported venue on route | Medium (pool hit only) |
| `PARTIAL_POOL_SET` | Some but not all pools resolved | Medium-low |
| `ROUTE_FAMILY` | Venue+token-pair covered; **no** pool-address proof | Low (labelled sensitivity) |
| `UNMATCHED` | Identifiers present; outside universe | — |
| `UNMATCHABLE` | Missing pool addresses / legs | — |

### Reproducible commands
```bash
# 1) Snapshot universe from running container (read-only dump already saved)
# 2) Run matcher (audit dir only; no product edits)
cd ~/projects/arbicore-x-cert/artifacts/g15/audit_offline_base_replay_20261009
python3 offline_base_winner_route_coverage.py
# Outputs:
#   BASE_G15_ROUTE_COVERAGE.csv
#   coverage_summary.json
```

Script: `offline_base_winner_route_coverage.py` (audit-artifact only).

---

## 3. Base winner population (G1.5 A/B/C/D)

Denominator for all coverage %: **6,287 Base rows** in the winners JSONL.

| Class | Meaning (from G1.5 REPORT) | Count | Share |
|---|---|---:|---:|
| **A** | Trace-verified kept-NET; confirmed searcher flows | 1,418 | 22.55% |
| **B** | Reconstructable kept-NET (Base, untraced, constrained) | 4,252 | 67.63% |
| **C** | Gross-only / kept-NET not established | 57 | 0.91% |
| **D** | Unknown / unpriced / unresolved legs | 560 | 8.91% |

**Interpretation constraint (per task):** Class A is trace-verified *external* flow evidence, **not** proof ArbiCore could have executed the opportunity.

Owner payout basis on Base JSONL rows: VERIFIED 374 · INFERRED 1,330 · MISSING 4,583.

---

## 4. Coverage table (explicit denominators)

### 4.1 Primary match tiers (n = 6,287)

| Tier | Count | % of Base |
|---|---:|---:|
| **EXACT_POOL_AND_VENUE** | **7** | **0.11%** |
| PARTIAL (any of below) | 682 | 10.85% |
| — partial pools + unsupported venue | 57 | 0.91% |
| — partial pool set | 624 | 9.93% |
| — route-family only (no address proof) | 1 | 0.02% |
| **UNMATCHED** | **5,260** | **83.66%** |
| **UNMATCHABLE** | **338** | **5.38%** |

**Conservative addressable by existing resolved universe:** 7 / 6,287 (0.11%).  
**Sensitivity (exact ∪ route-family):** 8 / 6,287 (0.13%).

### 4.2 Tiers by G1.5 classification

| Class | Exact | Partial any | Unmatched | Unmatchable | Class n |
|---|---:|---:|---:|---:|---:|
| A | 1 | 497 | 903 | 17 | 1,418 |
| B | 1 | 161 | 3,867 | 223 | 4,252 |
| C | 0 | 7 | 45 | 5 | 57 |
| D | 5 | 17 | 445 | 93 | 560 |

### 4.3 Unmatched / unmatchable reasons

| Reason | Count |
|---|---:|
| Unsupported venue on route | 3,788 |
| Token outside ArbiCore 12-token universe | 1,260 |
| No pool / route-family match (venues supported-ish but pairs/pools miss) | 212 |
| No valid pool addresses | 330 |
| Missing pools and legs | 8 |

### 4.4 Venue / family context

**ArbiCore Base universe (current):** UniV3 (19) + Aerodrome Slipstream (4) + Aerodrome classic (7); tokens WETH, USDC, cbETH, DAI, USDbC, cbBTC, AERO, USDT, rETH, wstETH, weETH, DEGEN.

**Winner leg venue atoms (external):** dominated by UniV4, PancakeV3, Aerodrome-Slipstream*, UniV3, Algebra, Curve — many **not** in ArbiCore.

Among Base winners:
- Only supported venue atoms (UniV3 / Aerodrome*): **1,670** (26.6%) — still mostly unmatched because pools/tokens/pairs are outside the curated 30.
- Any supported venue atom present: 5,471 (not a coverage claim).
- All tokens ⊆ ArbiCore TOKENS: 1,557 (24.8%).

Top unsupported venue hits among non-exact rows include: PancakeV3 (~1,987), AlgebraIntegral@0x36077d39 (~332), UniV4 USDC/USDT fee variants, UniswapV2, Curve.

### 4.5 Exact matches (all 7)

All seven are pure `UniswapV3` routes using canonical WETH/USDC fee-tier pools already in the CREATE2 registry (`0xd0b53d92…`, `0x6c561b44…`, `0x0b1c2dcb…`).

| tx (prefix) | Class | Owner basis | kept NET USD | Notes |
|---|---|---|---:|---|
| `0x411e54f1…` | A | INFERRED | 36.36 | Only exact class-A with kept NET |
| `0xc470f69a…` | B | MISSING | 0.22 | |
| `0x5373155d…` | D | MISSING | (null kept) | Class D — not decision-grade economics |
| `0x13c6d5f3…` | D | MISSING | (null kept) | |
| `0x31e128a6…` | D | MISSING | (null kept) | large gross listed; kept null |
| `0x8225a464…` | D | MISSING | (null kept) | |
| `0x70a6e373…` | D | MISSING | (null kept) | |

**VERIFIED owner-payee exact matches:** **0**.  
Decision-grade conclusion: under VERIFIED-only attribution, existing exact pool+venue coverage of the G1.5 Base winner set is **empty**.

### 4.6 Kept-NET on exact tier (sensitivity; includes INFERRED)

From JSONL `searcher_kept_net_usd` where present on exact rows: n=2, sum≈$36.58, median≈$18.29, ≥$1: 1, ≥$25: 1, ≥$100: 0.  
This is **not** a capture forecast — only the economic size of the tiny exact-overlap set.

---

## 5. Historical “was it in the universe at the time?”

| Claim | Evidence | Result |
|---|---|---|
| UniV3 curated venues existed as code-defined pairs | `base_venues.py` in image built `2026-10-08T07:58:15Z` (mid-window); 19 CREATE2 addresses deterministic | **Supported for UniV3 address identity** if those venue tuples were loaded (they are static in the image) |
| Aerodrome pools were address-resolved in registry | `runtime_resolved=0` at audit time; no historical resolved-address ledger found in Mongo | **Cannot claim Aerodrome pool-address coverage historically** |
| Exact winner pools were on ArbiCore routes during window | `decision_history` shows UniV3 WETH/USDC cycles were being evaluated | **Consistent** that the 7 exact UniV3 pools were inside the scanned graph — **not** evidence those winner txs were seen |
| Full historical universe reconstruction point-in-time | No time-stamped pool-universe snapshots / migrations for the window | **Limitation stated — stop short of claiming broader historical coverage** |

---

## 6. Latency and capture findings (evidence-bounded)

### 6.1 What is **not** available
- No join from G1.5 `tx_hash` → ArbiCore candidate / opportunity / decision row.
- `arbicore_discovery_candidates` in-window count = **0**.
- Therefore: **no defensible discovery→decision latency for these winners**, and **no capture curve** tying ArbiCore reaction time to external winner value.

### 6.2 Winner-side timing (G1.5 observables only — not ArbiCore causality)
| Observable | Value |
|---|---|
| Rows with `timing.route_state_age_s` | 6,287 |
| Median / p90 `route_state_age_s` | 0.0 / 0.0 |
| Same-block trigger relation | 5,753 / 6,287 (91.5%) |
| `route_age_censored` | 21 |

These describe external competition geometry. **They do not prove ArbiCore missed due to latency** (per task: do not treat age below a median as causal).

### 6.3 ArbiCore self-scan telemetry (separate; not winner-joined)
Window 2026-10-08 00:00–18:00 UTC, `decision_history` chain=base:
- Decisions: 8,136  
- `would_execute`: **0**  
- `net_profit_usd > 0`: **0**  
- Quote age: median ≈ 0.090 s, mean ≈ 0.148 s, p90 ≈ 0.308 s  
- Dexes observed: `uniswap_v3`, `aerodrome`, `aerodrome_slipstream` only  

**Direct observation:** ArbiCore was actively scanning its curated Base graph during the window and recording decisions, but produced **zero** executable positives on that graph. That is economics/simulation rejection inside the small universe — not evidence it raced the external winner set.

### 6.4 Survival (G1.5 Base ledger — external searchers)
From `out/survival_base.json` overall: `s_central=0.7009`, `s_high=0.8732`, `s_low=0.0445`.  
This characterizes external searcher survival under G1.5 cost variants — **not** ArbiCore capture probability.

---

## 7. Limitations (over/under-statement)

**May overstate coverage**
- Treating CREATE2 UniV3 address presence as “route covered” ignores fee-tier / hop-order / flash-loan / Gate7 constraints.
- `PARTIAL_*` counts include routes that still require unsupported venues (e.g. UniV4 co-legs).
- INFERRED owner kept-NET on the single class-A exact hit is not VERIFIED attribution.

**May understate coverage**
- Aerodrome venues are configured but addresses unresolved → true Aerodrome overlap cannot be proven offline without RPC (forbidden).
- 330 unmatchable rows lack pool addresses; some might be in-universe if pools were recovered (not done here).
- Image mid-window build: if an older image had a different venue list before 07:58Z, early-window coverage could differ (no snapshot → not claimed).

**Hard exclusions honored**
- No BNB economic conclusions.
- No fabricated timestamps / capture tiers.
- No product code, config, DB, RPC, deploy, or LIVE changes.

---

## 8. Answers to the coverage questions

1. **Dominant failure = venue coverage?** **Yes.** 3,788 / 6,287 unmatched primarily for unsupported venues (UniV4, PancakeV3, Algebra, Curve, etc.), on top of a 30-venue curated graph.
2. **Route coverage?** **Yes, secondary but severe.** Even among the 1,670 winners whose venue atoms are only UniV3/Aerodrome*, almost none have full pool-address or hop-pair coverage inside the 30 curated pairs; exact = 7.
3. **Scheduler starvation?** **INSUFFICIENT EVIDENCE** to blame scheduler for these winners — they were mostly never in the universe. Self-scan still emitted 8,136 decisions (so the loop was alive on the tiny graph).
4. **Discovery latency?** **INSUFFICIENT EVIDENCE** as causal for misses — no winner↔candidate join; external same-block dominance is not ArbiCore latency proof.
5. **Economic verification?** **Inside the existing universe, yes as a separate fact:** 8,136 decisions → 0 `would_execute` / 0 positive net in-window. That kills capture *even for covered routes*, but is not the reason most external winners were absent.
6. **Execution/competition?** External winners are 91.5% same-block; competition is real in the wild. Without universe coverage + join evidence, this does not justify a hot path.
7. **Hot path justified by capture curve?** **No.** No supported capture curve tying latency tiers to addressable winner value for ArbiCore.

---

## 9. Verdict (next research step only)

| Decision | Result |
|---|---|
| **Next research step** | **GO** — venue/token/route **coverage gap analysis & prioritization** (UniV4, PancakeV3, Algebra, broader Aerodrome pool identity, token expansion). Evidence is sufficient and reproducible. |
| Hot-path engineering | **NO-GO** |
| Latency remediation as primary bet | **NO-GO** / insufficient join evidence |
| Claiming historical Aerodrome address coverage | **INSUFFICIENT EVIDENCE** |
| Live trading / deploy / code change | **NO-GO** (out of scope; not authorized) |

**Finite recommendation for research sequencing:** coverage repair research first (**B** in prior letter scheme). Latency/hot-path (**C/D**) not justified by this offline replay. Economics/competition (**E**) still zero inside the current scanned graph and would remain binding even after selective coverage adds — treat as a follow-on measurement after coverage candidates are defined, not as a reason to skip coverage work.

---

## 10. Deliverable index

| File | Role |
|---|---|
| `BASE_G15_OFFLINE_ROUTE_COVERAGE_AUDIT.md` | This report |
| `BASE_G15_ROUTE_COVERAGE.csv` | Per-winner match tier + fields |
| `coverage_summary.json` | Machine-readable aggregates |
| `arbicore_base_universe_snapshot.json` | Frozen universe used for matching |
| `arbicore_decision_history_window.json` | Read-only decision telemetry summary |
| `offline_base_winner_route_coverage.py` | Repro matcher (audit-only) |
| `README.md` | How to re-run |
