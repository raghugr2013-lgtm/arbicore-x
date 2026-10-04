# Flash-Loan Six-Chain Pipeline — Blocker Diagnostic — 2026-10-04

- **Classification of prior gate:** `SIX_CHAIN_PIPELINE_PARTIAL` ([FLASH_LOAN_DISCOVERY_SIX_CHAIN_PIPELINE_CERT_20261004.md](./FLASH_LOAN_DISCOVERY_SIX_CHAIN_PIPELINE_CERT_20261004.md))
- **This document:** READ-ONLY root-cause diagnostic. No code change, deploy, config mutation, SHADOW start, or broadcast.
- **Runtime:** `arbicore-x-backend:flash-discovery-readiness-9ed2718` / container `arbicore-x-backend-new` / Network Config `rev-d069f13244ba44da81f97e72f7cfce5b`
- **Verification window:** `2026-10-04T03:00:23Z` → `03:47:08Z` (plus continuous discovery evidence through ~`04:30Z`)
- **Control path:** **Base** (complete through exact-size quote + Gate 7 evaluation)

---

## Executive verdict

Only **Base** reaches exact-size borrow sizing and Gate 7. The five non-Base chains diverge earlier:

| Failure mode | Chains | First divergence vs Base |
|---|---|---|
| Claim/queue starvation — qualifying candidates never reach the verifier | Arbitrum, Optimism, BNB (Polygon in-window) | Stage 4 — verifier handoff |
| Exact-size sizer Base-scoped — quotes stay `probe` → `denied:size_not_quoted` | Ethereum | Stage 6/7 — exact-size quote / borrow sizing |
| Historical quote fail-closed `denied:venue_unreadable` (RPC degraded window) | Polygon (pre-window only) | Stage 5 — quote request (when briefly claimed) |

**PRE-SHADOW GO: NO.** Pipeline is not six-chain complete. Safety gates held; blockers are scheduling/wiring, not market profit on the unfinished chains.

---

## Stage matrix (Base = control)

| Chain | Last successful stage | First failing/missing stage | Evidence | Root cause classification | Code fix required? | Confidence |
|---|---|---|---|---|---|---|
| **Base** | 8 — Gate 7 profitability eval (FAIL on $25 floor) | — (complete path) | 80 in-window exact-size Gate 7 FAILs; cumulative 1,117 exact since resume | — | No (market outcome) | High |
| **Ethereum** | 5 — quote request (`route_quote_status=ok`) | **6 — exact-size quote** (`size_basis=probe`) | 218 in-window ok+probe → `denied:size_not_quoted`; 0 exact; Gate 7 NOT_EVALUATED | **D** exact-size sizing unavailable | **Yes** (wire multichain H05 sizer) | High |
| **Arbitrum** | 3 — TVL eligibility (≥$100k routes exist) | **4 — verifier handoff** | 11,269 window candidates / 8,389 TVL≥$100k; **0 ever verified**; 0 bundles | **B** candidate not handed to verifier | **Yes** (fair claim / drain) | High |
| **Optimism** | 3 — TVL eligibility | **4 — verifier handoff** | 3,744 window / 1,008 TVL≥$100k; **0 ever verified**; 0 bundles | **B** | **Yes** (fair claim / drain) | High |
| **Polygon** | 3 — TVL eligibility (in-window); historically reached 5 then failed | **4 — verifier handoff** (in-window); historically **5 — quote** (`venue_unreadable`) | 0 in-window bundles; 32 cumulative all `denied:venue_unreadable` at `2026-10-03T23:48Z` during polygon RPC breaker recovery | **B** (current); **E** (historical quote) | **Yes** for handoff; quote re-test after handoff | High (B); Medium (E persistence) |
| **BNB** | 3 — TVL eligibility (Aave-only providers by catalog) | **4 — verifier handoff** | 2,688 window / 2,400 TVL≥$100k; **0 ever verified**; 0 bundles; providers Aave-only (**F** secondary) | **B** primary; **F** secondary | **Yes** for handoff; catalog scope intentional | High |

Classification key: **A** no qualifying candidate · **B** not handed to verifier · **C** quote unavailable · **D** exact-size unavailable · **E** venue/provider unreadable · **F** chain-specific configuration · **G** insufficient evidence · **H** other.

---

## Pipeline stage reference (Base control)

| # | Stage | Base evidence |
|---|---|---|
| 1 | Candidate discovery | 8,153 window `FLASH_LOAN_ARBITRAGE` rows |
| 2 | Route selection | Non-empty `candidate_venues` / route-search + generic DEX |
| 3 | TVL eligibility | `min_tvl_usd` ≥ $100k on route-search paths |
| 4 | Verifier handoff | Claim → `flash_loan_arb_verifier` bundles (123 in window) |
| 5 | Quote request | `route_quote_status=ok` on 80 rows |
| 6 | Exact-size quote | `size_basis=exact`, `exact_size=true`, `quote_notional_usd=10000` |
| 7 | Borrow sizing accepted | Verifier accepts non-probe; proceeds to economics |
| 8 | Gate 7 | Evaluated; FAIL vs $25 floor (e.g. `atomic_profit $-176.04 < floor $25.00`) |

---

## 1. Confirmed blockers

### B1 — Ethereum: Base-scoped H05 borrow sizer (classification **D**)

**First divergence:** stage 6 (exact-size quote), after successful stage-5 quotes.

**Component / function:**

- Wiring: `composition._wire_canonical_flash_loan_scanner` → `borrow_sizer=_build_base_exact_size_borrow_sizer(price_feed)`
- Sizer scope: `_build_base_exact_size_borrow_sizer` builds `MultichainPriceSource({"base": price_feed})` only
- Quote stamping: `live_quote_provider.make_live_quote_provider` — if `borrow_sizer(chain, token, usd)` returns `None`, keeps `size_basis="probe"`
- Deny: `FlashLoanOpportunityVerifier.verify` — `size_basis == "probe"` → `VerifiedOutcome.DENIED_SIZE_NOT_QUOTED` (`denied:size_not_quoted`) before Gate 7

**Exact reason:** `size_basis=probe` / `exact_size=false` / `quote_notional_usd=None` → outcome `denied:size_not_quoted`.

**Evidence:**

- In-window: 218 Ethereum bundles with `(probe, false, ok)`; 800 `venue_unreadable`; 0 exact; Gate 7 all `NOT_EVALUATED`
- Sample (continuous run): Ethereum USDC/`aave_v3`/`flash_loan_route_search` — `route_quote_status=ok`, `quoted_amount_in_wei=200000000` (probe), `size_basis=probe`, outcome `denied:size_not_quoted`
- Base control sample: `size_basis=exact`, `quoted_amount_in_wei=10000000000`, `quote_notional_usd=10000.0`, Gate 7 FAIL
- Running image confirms Base-only wiring (`MultichainPriceSource({"base": price_feed})`); env has `ARBICORE_BORROW_SIZER_ENABLED=true` and `ARBICORE_PRICE_FEED_ENABLED=true`
- Six-chain builder `build_h05_borrow_sizer` / `build_multichain_price_source` exists in the same module but is **not** used by canonical flash-loan scanner wiring

**Defect vs opportunity:** Genuine **wiring gap** (multichain sizer implemented, Base-only path activated). Not “no Ethereum opportunity” — quotes already return `ok`.

**Safe to fix without changing safety gates?** **Yes.** Wire existing `build_h05_borrow_sizer` (or equivalent per-chain feeds) into `_wire_canonical_flash_loan_scanner`. Keep fail-closed probe denial and $25 / $100k floors unchanged.

---

### B2 — Arbitrum / Optimism / BNB: verifier never claims (classification **B**)

**First divergence:** stage 4 (verifier handoff). Stages 1–3 succeed with TVL-qualified routes.

**Component / function:**

- `FlashLoanArbitrageScanner._tick` → `DiscoveryQueue.claim_batch(worker_id, batch_size=32)`
- `DiscoveryQueue.claim_batch` — `findOneAndUpdate` with filter `verified_outcome=None`, `expires_at > now`, claim lock free; **no `sort`, no chain fairness, no `opportunity_type` filter**
- Mongo plan: `expires_at_1` index scan ascending (soonest expiry first)

**Exact reason:** Qualifying candidates expire with `verified_outcome=None` (`expired_unproc` mass). Verifier never runs → zero `evidence_bundles` for these chains.

**Evidence (not “no qualifying candidate”):**

| Chain | Window candidates | Window TVL≥$100k unverified | Ever `verified_outcome` set | Verifier bundles since resume |
|---|---:|---:|---:|---:|
| Arbitrum | 11,269 | 8,389 | **0** | **0** |
| Optimism | 3,744 | 1,008 | **0** | **0** |
| BNB | 2,688 | 2,400 | **0** | **0** |

Live eligible samples (still unclaimed at diagnostic time) had routes + TVL well above floor, e.g. Arbitrum USDC cycle `min_tvl_usd≈$830k`, Optimism ≈$237k, BNB ≈$218k.

Claim-head simulation: first ~745 eligible docs by `expires_at` are **all Ethereum**; Arbitrum first appears ~rank 746. With `batch_size=32` and continuous Ethereum discovery refill, non-ETH chains are starved. Last 100 processed candidates observed during diagnostic: **100% Ethereum**.

**Absence of verifier bundles is:** **verifier handoff not occurring** (queue claim starvation), **not** “no candidate surviving filters,” and **not** primarily quote/provider incompatibility (those stages never reached).

**Defect vs opportunity:** Genuine **scheduling/queue defect** relative to multi-chain discovery volume. Candidates qualify under existing $100k filters.

**Safe to fix without changing safety gates?** **Yes.** Add chain-fair claim (round-robin / per-chain quotas / sort+filter), and/or raise effective drain rate, without touching TVL or profit floors. Optional ops: temporarily reduce Ethereum emit pressure only if done without weakening safety gates (prefer code fairness).

---

### B3 — Polygon: handoff starved in-window; historical `venue_unreadable` (classification **B** + **E**)

**In-window first divergence:** stage 4 (0 bundles), same claim starvation as B2 (7,308 TVL≥$100k window rows unverified).

**Historical (still relevant when claimed):** stage 5 — all 32 bundles since resume at `2026-10-03T23:48:45Z`–`23:48:53Z`, outcome `denied:venue_unreadable`, `route_quote_status=None`, providers `uniswap_v3` / `aave_v3` / `balancer_v2`, routes involving USDT/WMATIC and WETH/WMATIC.

**Component / function:**

- Handoff: same `DiscoveryQueue.claim_batch` as B2
- Quote deny: `FlashLoanOpportunityVerifier.verify` — `quote_provider` returns falsy / empty `hop_legs` → `denied:venue_unreadable`
- Contemporaneous logs: `rpc_polygon_* TRIPPED → DEGRADED` then recovery; Alchemy polygon POSTs returned 200 shortly after

**Does historical `venue_unreadable` still apply?** **Unknown on current runtime** — no Polygon verifier claim after `23:48Z` (starvation). WMATIC is present in the multichain token registry (`0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270`). Cannot classify current quote path as permanently broken (**G** for quote persistence) until fair claim delivers fresh Polygon rows.

**Defect vs opportunity:** Handoff starvation is a code/scheduling defect. Historical unreadable likely **transient RPC/provider unreadability** (and/or plan/quote failure under degraded RPC), not “no TVL-qualified candidate.”

**Safe to fix without changing safety gates?** Handoff fairness: **yes**. Quote-path diagnosis after handoff: observe-only first; fix only if reproducible unreadable with healthy RPC.

---

### B4 — BNB Aave-only catalog (classification **F**, secondary)

**Not the first divergence** (handoff fails first). Catalog `FLASH_LOAN_PROVIDERS`: Balancer V2 and Uniswap V3 flash **omit `bnb`**; only `aave_v3` pairs. Matches observed candidates. Intentional scope from readiness cert — do not treat as the stage-4 blocker.

---

## 2. Evidence-only gaps

1. **Polygon quote health on current image/RPC** after a successful claim — no post-`23:48Z` bundle.
2. **Whether Arbitrum/Optimism/BNB quotes would reach `ok`** once claimed — discovery/TVL say they should be attempted; no verifier evidence yet.
3. **Exact Base vs Arbitrum interleaving under `findOneAndUpdate`** — Base still receives bundles (~60–215/hour) while Arbitrum has zero lifetime verifies; claim head is Ethereum-dominated. Fairness defect is proven by zero verifies + large eligible backlogs; fine-grained Base interleave micro-order is secondary.
4. **Ethereum `venue_unreadable` majority** (800/1018 in window) — secondary to exact-size blocker for rows that already quote `ok`; per-route plan/quoter failure modes not fully decomposed here.

---

## 3. Genuine code defects (if any)

| ID | Defect | Severity for six-chain pipeline |
|---|---|---|
| D1 | Canonical flash scanner wires **Base-only** borrow sizer despite multichain H05 builders existing | Blocks Ethereum (and would block any non-Base chain that reaches quoting) at exact-size |
| D2 | `DiscoveryQueue.claim_batch` has **no chain-fair scheduling**; `expires_at` ASC + Ethereum emit volume starves other chains | Blocks Arbitrum, Optimism, BNB, Polygon handoff |
| D3 | (Secondary) BNB flash provider catalog excludes Balancer/UniV3 | Limits BNB surface after handoff; not first blocker |

**Not defects:** Gate 7 $25 failures on Base (market); triangular low-TVL rows that never pass $100k search floor; fail-closed `denied:size_not_quoted` when sizer returns `None` (correct safety behavior).

---

## 4. Recommended surgical fixes (DO NOT IMPLEMENT IN THIS GATE)

1. **Wire multichain exact-size sizing into canonical activation**  
   In `_wire_canonical_flash_loan_scanner`, replace `_build_base_exact_size_borrow_sizer(price_feed)` with `await build_h05_borrow_sizer(quoter_registry)` (or merge Base feed into `build_multichain_price_source`). Keep env gates and fail-closed probe denial.

2. **Chain-fair claim**  
   Change `DiscoveryQueue.claim_batch` (or scanner claim loop) to round-robin / quota by `hint_metric.chain` among six certified chains; optionally filter `opportunity_type=FLASH_LOAN_ARBITRAGE` and sort explicitly. Do not lower TTL below discover latency without measuring.

3. **Backlog drain (ops, non-safety)**  
   After fairness lands: allow short observation until each of Arb/Opt/Polygon/BNB produces ≥1 verifier bundle. Do not delete safety denials.

4. **Polygon re-probe**  
   Once claimed under healthy RPC, inspect whether `venue_unreadable` reproduces; only then chase quoter/WMATIC hop planning.

5. **Do not** change `$100k` TVL, `$25` Gate 7, Network Config, or enable PAPER/LIVE/broadcast for this remediation.

---

## 5. Exact next action per affected chain

| Chain | Next action |
|---|---|
| **Ethereum** | Implement/deploy multichain H05 sizer wiring; re-verify bundles show `size_basis=exact` then Gate 7 PASS/FAIL |
| **Arbitrum** | Implement chain-fair claim; confirm ≥1 verifier bundle; then inspect quote → exact-size (depends on D1) → Gate 7 |
| **Optimism** | Same as Arbitrum |
| **Polygon** | Same handoff fairness; then dedicated quote audit if `venue_unreadable` returns under healthy Alchemy |
| **BNB** | Same handoff fairness; accept Aave-only providers unless catalog expansion is separately approved; then exact-size (D1) → Gate 7 |
| **Base** | No blocker for pipeline completeness; continue as control (Gate 7 fails are market) |

---

## 6. PRE-SHADOW GO readiness

| Question | Answer |
|---|---|
| Six chains through exact-size + Gate 7? | **No** — only Base |
| Safe to start long SHADOW / PRE-SHADOW GO? | **NO** |
| Why | Ethereum blocked on exact-size wiring; Arb/Opt/BNB/Polygon blocked on verifier handoff; Polygon quote unresolved |
| What would flip to GO | Fair claim evidence on Arb/Opt/Polygon/BNB **and** Ethereum (and others) exact-size Gate 7 evaluation under unchanged $25/$100k gates |

---

## Appendix A — Per-chain divergence detail

### Base (control)

- Stages 1–8 exercised. In-window: 123 bundles; 80 exact-size; 80 Gate 7 FAIL; 43 `venue_unreadable`.
- Working path proves live quote + Base H05 sizer + Gate 7 evaluator are live.

### Ethereum

| Stage | Status |
|---|---|
| 1–3 Discovery / route / TVL | Pass (12,225 window; TVL up to tens of $M) |
| 4 Handoff | Pass (1,018 in-window bundles) |
| 5 Quote | Partial — 218 `ok`, 800 unreadable |
| 6 Exact-size | **FAIL** — all ok quotes are `probe` |
| 7–8 Sizing / Gate 7 | Not reached on probe path |

### Arbitrum / Optimism / BNB

| Stage | Status |
|---|---|
| 1–3 | Pass (large TVL-qualified sets) |
| 4 Handoff | **FAIL** — 0 bundles, 0 ever verified |
| 5–8 | Not reached |

BNB note: provider set Aave-only (**F**) after handoff would still allow a complete Aave-only pipeline if claim + exact-size work.

### Polygon

| Stage | Status |
|---|---|
| 1–3 | Pass in-window |
| 4 Handoff | **FAIL** in-window (0 bundles) |
| 5 Quote | Historical FAIL `venue_unreadable` (32) during RPC degradation; current unknown |
| 6–8 | Not reached |

---

## Appendix B — Key code pointers (read-only)

- Claim: `app/backend/arbicore/data/discovery_queue.py` → `DiscoveryQueue.claim_batch`
- Tick: `app/backend/arbicore/scanners/flash_loan_arbitrage/scanner.py` → `_tick`
- Base-only sizer wire: `app/backend/arbicore/runtime/composition.py` → `_build_base_exact_size_borrow_sizer`, `_wire_canonical_flash_loan_scanner`
- Unused six-chain sizer: `build_multichain_price_source`, `build_h05_borrow_sizer` (same file)
- Probe vs exact: `live_quote_provider.py` (H05 binding); deny in `verifier.py` (`DENIED_SIZE_NOT_QUOTED`)
- Provider catalog: `economics.py` → `FLASH_LOAN_PROVIDERS` / `providers_for_chain`

---

## Appendix C — Boundaries held

- No code modification, deploy, container restart, Network Config / RPC change, provider enablement beyond existing state, TVL/$25/safety gate changes, SHADOW campaign start, signing, or broadcast.
- Diagnostic only; scanner left as found.

---

## Stop

Procedure stops after this report. No remediation implemented.
