# G1.5 Follow-up — Coverage Prioritisation (Research Only)

**Scope:** Rank next venue/token/route coverage gaps from the completed offline audit.  
**Not in scope:** hot-path, latency, RPC collection, code/config changes, SHADOW execution, LIVE.

**Sources (read-only):**
- `BASE_G15_OFFLINE_ROUTE_COVERAGE_AUDIT.md`
- `BASE_G15_ROUTE_COVERAGE.csv`
- `coverage_summary.json`
- `arbicore_base_universe_snapshot.json`
- `arbicore_decision_history_window.json`
- Frozen winners JSONL (Base rows only) for token/pair decomposition
- Machine stats: `coverage_prioritisation_stats.json`

---

## Assumptions and denominators

| Item | Value |
|---|---|
| Denominator for all shares | **6,287** Base rows in G1.5 winners JSONL |
| “Affected” | Winner is **not** `EXACT_POOL_AND_VENUE` **and** matches the gap predicate |
| Exact matches excluded from gaps | 7 already exact — not counted as coverage gaps |
| Partial matches | Reported only as context; **not** treated as executable / covered |
| Economics used | `searcher_kept_net_usd` on classes **A/B only**; C/D kept treated as non-decision-grade |
| Gross profit | Never used as net |
| BNB rows | Ignored entirely |
| VERIFIED vs INFERRED | Owner payout basis from JSONL; decision-grade callouts require VERIFIED |
| Capture / latency | **Not estimated** (no winner↔ArbiCore join) |
| ArbiCore universe | 30 curated venues; 19 UniV3 addresses resolved; **0** Aerodrome addresses resolved |

**Hard reading of attribution:** only **2** Base rows are class A ∩ VERIFIED owner in the entire JSONL. Under a strict VERIFIED-only bar, **no** coverage candidate currently clears a decision-grade economic gate. Ranking below therefore uses **A-count and A/B kept-NET as research signal**, with VERIFIED reported separately as a sensitivity — not as proof of ArbiCore-captureable profit.

---

## Ranked shortlist

| Rank | Candidate | Base winners affected | Share | A / B / C / D | VERIFIED owner (gap) | A/B kept-NET (signal) | Exact pool IDs offline? | Hist. route compatibility |
|---:|---|---:|---:|---|---:|---|---|---|
| **1** | **Uniswap V4 / UniV4 (any leg)** | **2,012** | **32.00%** | 556 / 1,229 / 27 / 200 | 73 (A∩VERIFIED = 1) | sum $1,636; ≥$1 179; ≥$25 9; ≥$100 2; ≥$1000 0 · VERIFIED A/B ≥$1: **0** | **No** — V4 pools not in ArbiCore CREATE2 registry; many G1.5 D rows cite unresolved V4 | **Unknown** — no V4 in current universe / decision_history dexes |
| **2** | PancakeV3 (any leg) | 1,987 | 31.60% | 313 / 1,531 / 16 / 127 | 168 (A∩VERIFIED = 1) | sum $2,764; ≥$1 220; ≥$25 18; ≥$100 3 · VERIFIED A/B ≥$1: **2** | **No** — not in registry | **Unknown** — not in scanned dex set |
| **3** | Already-mapped dex atoms only (UniV3 + Aerodrome*) but not exact | 1,663 | 26.45% | 450 / 991 / 11 / 211 | 93 (A∩VERIFIED = 1) | sum $11,668; ≥$1 311; ≥$25 40; ≥$100 17; ≥$1000 4 · VERIFIED A/B ≥$1: **5** | **Partial** — UniV3 subset addressable; Aerodrome `runtime_resolved=0` | **Partial** — dex families already in `decision_history`; pairs/tokens mostly missing |
| **4** | Token XDP outside universe | 1,537 | 24.45% | 458 / 1,077 / 1 / 1 | 19 (A∩VERIFIED = 0) | sum $496; ≥$1 92; ≥$25 **0** | N/A (token gap) | Depends on host venues (often UniV4) |
| **5** | AlgebraIntegral (any) | 482 | 7.67% | 79 / 392 / 1 / 10 | 19 | sum $252; ≥$1 25; ≥$25 3 | **No** | **Unknown** |
| **6** | Token cbXRP outside universe | 246 | 3.91% | 81 / 158 / 4 / 3 | 14 | sum $5,146; ≥$1 93; ≥$25 29; ≥$100 10; ≥$1000 1 | N/A | Needs venue+pool research; lumpy |
| **7** | **Curated-pair gap only** (mapped dexes + tokens already in ArbiCore TOKENS + missing `VENUES` pair) | **109** | **1.73%** | 25 / 53 / 0 / 31 | 5 (VERIFIED A/B ≥$1: **0**) | sum $628; ≥$1 24; ≥$25 4; ≥$100 2 | **Pool addresses present on winners** (41 distinct; 35 not in UniV3 resolved set → mostly Aerodrome) | **Highest** — dex+token already in product; missing pair list explicit |

Supporting slice (not a separate rank row): **UniV4 + all other legs already mapped** = 1,790 (28.47%), A=520. Of all UniV4 gaps, 1,142 also touch **XDP** (AB kept ≥$25: 0); **870 UniV4 without XDP** carry most of the ≥$25 mass (9).

---

## Candidate notes (evidence, uncertainty, SHADOW bar)

### 1) Uniswap V4 / UniV4 — **recommended next research target**

1. **Affected:** 2,012 / 6,287 (32.00%); A=556 largest class-A venue gap.  
2. **Gaps:** New venue family; co-legs often UniV3/Aerodrome (1,790 “V4 + mapped-only else”). Frequent extra token gaps (XDP 1,142, WHUF, …). Route families: triangular / multi-hop / DEX-DEX.  
3. **A/B/C/D & attribution:** A-heavy relative to Pancake; owner VERIFIED 73 but **VERIFIED A/B kept ≥$1 = 0**. Use A/B kept only as research signal; label INFERRED/MISSING.  
4. **Exact pools / historical compatibility:** **Cannot** establish ArbiCore-resolvable V4 pool identity from current universe snapshot. G1.5 already flags unresolved V4 in class D. No V4 in `decision_history` dexes for the window.  
5. **Research value / uncertainty / evidence to resolve:**  
   - **Value:** Largest single missing venue by A-count and share; compositional add (V4 beside existing UniV3/Aerodrome) is well-defined.  
   - **Uncertainty:** Quoter/hook surface, pool-id scheme, which V4 pools are real vs unresolved in G1.5, token long-tail.  
   - **Evidence needed (still research/read-only):** inventory distinct V4 pool identifiers + hooks + token sets from Base winner `legs`/`pools`; split resolved vs unresolved V4; quantify A/B kept on “V4 + majors-only tokens”; map whether any V4 pool addresses recur enough to be a finite allowlist. **No RPC in this step** — use frozen JSONL/ledger only.  
6. **Worth later SHADOW if:** offline inventory yields a **finite** V4 pool allowlist with (a) class A/B rows, (b) tokens limited to a declared set, (c) recurring pool IDs, and (d) a pre-declared kept-NET bar on that subset (suggested research gate: ≥20 A/B rows with kept-NET ≥$1 **or** ≥3 with kept-NET ≥$25 on the allowlist, with VERIFIED called out separately). Do **not** SHADOW on gross or on partial UniV3 pool overlap alone.

### 2) PancakeV3

- Scale similar to V4 (1,987) but fewer A (313), more B.  
- Slightly better VERIFIED A/B signal (2 with kept ≥$1) — still too thin for decision-grade profit claims.  
- Same blockers: new venue + often non-universe tokens (SOL, JitoSOL, msUSD, …).  
- **Defer** until V4 inventory completes or if V4 inventory fails finiteness.

### 3) Mapped dexes (UniV3/Aerodrome) but not exact — composite

- Large A (450) and large A/B kept sum, but **1,404 / 1,663** blocked by **tokens outside** the 12-token universe — not a single clean coverage fix.  
- True Aerodrome address-only blocker among token-in-universe rows is ~1; the clean sub-gap is curated pairs (#7).  
- Treat as a **bucket**, not one research ticket.

### 4) Token XDP

- High count, tightly coupled to UniV4; **no** A/B kept ≥$25.  
- Poor standalone SHADOW economics; fold into V4 inventory as a long-tail exclusion unless majors-only subset is empty.

### 5) AlgebraIntegral

- Smaller (7.67%); factory-specific; higher integration uncertainty than Pancake/V4 population leaders.

### 6) Token cbXRP

- High kept-NET tail (including ≥$1000) but small n and venue-heterogeneous; lumpy; needs venue context first. Not a clean first target.

### 7) Curated-pair expansion (existing TOKENS + mapped dexes)

- **Most implementation-tractable**, smallest population (109).  
- Top missing pairs (winner counts):  
  `aerodrome_slipstream:USDC/cbBTC` (38), `AERO/USDC` (21), `USDC/USDT` (20), `cbBTC/cbETH` (19), `USDC/USDbC` (8).  
- Winner JSONL already carries pool addresses for offline identity listing; Aerodrome still not CREATE2-proven in-repo (`runtime_getpool`).  
- Good **parallel** research after or beside V4 inventory; **not** the single largest evidence gap.

---

## Explicit non-claims

- Partial pool hits (682) are **not** executable coverage.  
- In-window ArbiCore `decision_history` (8,136 decisions, 0 `would_execute`) shows the current graph was dry — it does **not** score these gaps’ future SHADOW EV.  
- No latency/capture curve is offered.

---

## Recommendation — exactly one next research target

**Choose: Uniswap V4 / UniV4 Base coverage inventory (offline, from frozen G1.5 legs/pools only).**

**Why this one (not #7 or Pancake):**
- Largest class-A and share gap (556 A; 32% of Base winners).  
- Clean compositional story: 1,790 affected winners already use only V4 + venues ArbiCore already names.  
- Economic research signal survives excluding XDP (870 winners; 121 A/B ≥$1; 9 ≥$25).  
- Curated-pair expansion (#7) is better for *cheap engineering fit* but is too small (1.73%) to be the primary gap the audit pointed at. Pancake is similar in scale to V4 but weaker on class A and more token-entangled with non-majors.

**Immediate research output to produce next (still read-only, no RPC):**  
a V4 pool/hook/token inventory table from the 2,012 rows, with resolved vs unresolved, majors-only vs long-tail, A/B kept-NET histogram, and a go/no-go for defining a finite SHADOW allowlist under the bar in §1.6.

**If that inventory shows V4 pool identity is mostly unresolved/non-finite:** fall back to candidate **#7 (Aerodrome Slipstream curated pairs among existing TOKENS)** as the next research target — do not proceed to Pancake or hot-path by default.
