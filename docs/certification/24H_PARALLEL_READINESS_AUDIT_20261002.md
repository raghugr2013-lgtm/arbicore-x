# ArbiCore X — Parallel 24h Readiness Audit (READ-ONLY)

- **Status:** AUDIT ONLY — **no** source/config/runtime changes; **no** SHADOW campaign interrupt/reset/shorten/promote; **no** Recommendation / AUTOEXEC / RUNTIME / signing / broadcast / live enable
- **Date:** 2026-10-02
- **Workspace:** `/home/raghu/projects/arbicore-x-cert`
- **Binding tip (reused audits):** `9b196cde0c975d0efe94e94f49de05b4244bdbc6`
- **Gate posture (frozen):** Gate7 = **$25**; Gate8 / H05 **fail-closed unchanged**
- **SHADOW campaign:** **UNTOUCHED** by this audit (inspect/docs only)

---

## FINAL VERDICT

| Question | Answer |
|---|---|
| Code change required **before** continuing Gate 9 SHADOW? | **No** |
| Rebuild evidence / econ / broker systems? | **No** — reuse existing |
| Capability matrix supersede needed? | **No** — thin taxonomy addendum only (`ARBITRAGE_CAPABILITY_MATRIX_AUDIT_20261002_ADDENDUM.md`) |
| Recommendation / LIMITED_LIVE activation? | **Forbidden / not ready** — stay SHADOW |
| Official Gate9/Gate10 SHADOW campaign | **Continue as-is**; this workstream is parallel readiness only |

**Reuse (valid, not rebuilt):**

- `docs/certification/ARBITRAGE_CAPABILITY_MATRIX_AUDIT_20261002.md` → **READY** (SHADOW)
- `docs/certification/PAPER_BROKER_READINESS_AUDIT_20261002.md` → **READY-WITH-MINOR-DELTA**
- `docs/certification/PAPER_VALIDATION_MINIMAL_DELTA_PLAN_20261002.md` → **READY — no code**
- `docs/certification/PAPER_GATE9_10_VALIDATION_20261002.md` → **CONDITIONAL** (≈1.04h, evidence=0)
- `docs/certification/M6_POST_ALCHEMY_RESET_SHADOW_20261002.md` → **PASS (evidence-complete)**; Alchemy fp `5e5d5bb1`
- `docs/certification/SHADOW_VALIDATION_ARCHITECTURE_RECONCILIATION_20261001.md` (pre-M5; DiscoverySource wiring superseded by M5)

---

## 1. Evidence completeness (Priority 1)

### 1.1 Pipelines (existing — do not replace)

| Surface | Role | Persist |
|---|---|---|
| Canonical scanner → verifier → Gate7/8/9 → `EmissionBus` (`scanner._tick` only) | Live SHADOW discovery emit | Canonical opportunities + verifier audit sink |
| Verifier `_build_evidence_bundle` (schema `m2.3`) | Per-candidate CONFIRMED/DENIED audit | `evidence_sink` / learning `evidence_bundles` |
| `OpportunityPipeline` + `arbicore/paper/*` | Paper Validation Framework | Insert-only `arbicore_paper_evidence` |
| M6 / live SHADOW harness JSON | Campaign economic buckets A–F | `reports/shadow_validation/*` |

Architecture rule (recon + M5): **one** FLASH_LOAN EmissionBus site; GENERIC_DEX / triangular / Balancer feed DiscoverySources into the same verifier — no parallel emit engine.

### 1.2 Reconstruction checklist (can every opportunity be rebuilt?)

Legend: **Y** = present on primary audit surface; **D** = derivable from stored fields without new engine; **J** = requires join to canonical opportunity / journal; **N** = genuinely absent as first-class evidence; **—** = intentionally out of SHADOW (must stay false).

| Field | Verifier `m2.3` bundle | Paper `EvidenceBundle` | M6 GENERIC_DEX harness row | Verdict |
|---|---|---|---|---|
| Chain | Y | Y (`inputs.chain`) | Y | **OK** |
| Route family | Partial (`discovery_source`, hop/route shape; StrategyType tagging upstream) | Partial (`scanner_family` / `strategy`; no dedicated `route_family`) | Partial (`route` string, not enum) | Soft gap — **J**/tag, not missing pipeline |
| Flash provider | Y | Y | Y | **OK** |
| Quote | Y (`hop_legs`, `gross_profit_pct`, size/block provenance) | **J** (inputs truncated; stages may hold sim only) | Partial (leg status + USD econ) | Soft: paper bundle alone insufficient |
| Liquidity / TVL | Y (`min_pool_tvl`, provenance) | Stage if annotated; else permissive skip | D-bucket / N/A | Gate8 provider gaps remain (known) |
| Gross profit | Y (`economics` / quotes) | Profit stage payload when pipeline runs | Y `gross_profit_usd` | **OK** when path exercised |
| Flash repayment | **D** (`borrow` + `flash_loan_fee_*`); no explicit `repay_amount_wei` | **N** on bundle; operator_journey has `would_repay_usd` elsewhere | **D** (`borrow` + `flash_fee_usd`) | Soft gap — fee stored; repay not first-class |
| Gas | Y | Stage / nominal % if no `gas_estimate` | Y | **OK** (calibration quality varies) |
| Net profit | Y `atomic_profit_usd` / `expected_net_after_costs_usd` | Profit stage `net_profit_usd` | Y `net_profit_usd` | **OK** |
| Risk gates | Y explicit `gates` | Stage denials + `outcome_reason` | `gate7_pass` + reasons | **OK** |
| Rejection reason | Y `outcome_tag` / gate reasons | Y `outcome_reason` | Y `reasons[]` | **OK** |
| EXECUTABLE | Settlement/PaperOutcome vocabulary | Y `PaperOutcome.EXECUTABLE` | `eligible` / Gate7 | **OK** (A=0 honest to date) |
| Signing | Unsigned `execution_plan` only; never signs in verify | — | — | **By design** in SHADOW |
| Broadcast | `broadcast: false` invariant | Non-broadcast terminal | `broadcast: 0` | **By design** in SHADOW |

### 1.3 Genuinely missing fields / integration deltas only

**Do not build a new evidence system.** Gaps that are real (vs already deferred capability work):

| ID | Gap | Severity | Notes |
|---|---|---|---|
| E1 | Paper `EvidenceBundle.inputs` omits route hops / quote legs / net economics | P2 quality | Reconstruct via `opportunity_id` → canonical opp + verifier bundle; optional later widen inputs **only if** offline Gate9 packages require standalone bundles |
| E2 | No first-class `flash_repayment_amount_{wei,usd}` on verifier/paper evidence | P3 | Derivable: `borrow + flash_fee`; optional telemetry field later |
| E3 | Live paper path produced **0** `arbicore_paper_evidence` in Gate9 stamp | P0 **ops/feed** | Schema OK; feeder/inventory/market yield empty — **time + feed**, not new repo |
| E4 | Dual sinks (verifier audit vs paper evidence) without mandatory join index in Gate9 package | P2 ops | Document join keys: `opportunity_id` / `candidate_id` / `validation_id` |
| E5 | Route-family enum not always persisted on paper inputs | P3 | Strategy tagging exists; M5 sources distinguish discovery |

**Not gaps (already covered / intentional):** signing & broadcast absence in SHADOW; Gate7/8/H05 policy; A=0 profitability; empty DiscoverySource inventory (ops/data).

---

## 2. Capability matrix (Priority 2)

**Disposition:** Existing matrix audit remains binding. Classifications unchanged. Taxonomy remapped in addendum only — **no cell upgrades** without new live/shadow proof.

| Strongest SHADOW-proven | Weakest / deferred |
|---|---|
| GENERIC_DEX × Aave V3 × six chains (quote→econ→Gate7; A=0) | STABLECOIN / LST_LRT (**DETECTION-ONLY** tagging); CROSS_CHAIN executable (**NOT-IMPLEMENTED**); UniV3 flash / Morpho on V1 (**NOT** settle); Balancer long P1b (**INFRA-BLOCKED** Free getLogs) |

See: `docs/certification/ARBITRAGE_CAPABILITY_MATRIX_AUDIT_20261002_ADDENDUM.md`.

---

## 3. Economic replay (Priority 3)

### 3.1 Question

Can existing evidence deterministically replay  
`quote → repayment → fees → gas → buffers → net → Gate7 → Gate8/H05 → EXECUTABLE/REJECTED`  
using **existing** assessor/filter/verifier (no parallel econ engine)?

### 3.2 Answer: **Yes for the certified math path; gaps are evidence packaging / env gates only**

| Step | Existing component | Deterministic? | Gap |
|---|---|---|---|
| Quote | `live_quote_provider` / `QuoterRegistry` facts (`hop_legs`, `gross_profit_pct`, block) | Yes if quotes + block retained | Paper inputs truncated (E1) |
| Repayment / flash fee | `FlashLoanEconomicsAssessor` + `provider_fee_bps` | Yes | Explicit repay field optional (E2) |
| Fees / slippage | `aggregate_economics` (+ quote-inclusive double-count fix) | Yes | — |
| Gas | Assessor override / per-chain estimate / tx_gas_units scale; pipeline may use nominal % | Mostly | Nominal gas on paper path without `gas_estimate` |
| Buffers / worst-case | `build_profit_vector` (`worst_case_net_profit_usd`) | Yes as library | Gate7 still binds **atomic** net, not worst-case |
| Net | `atomic_profit_usd` ≡ `expected_profit_usd` | Yes | — |
| Gate7 $25 | `FlashLoanGate7AtomicProfit` / GENERIC_DEX `MIN_ATOMIC_PROFIT_USD=25` | Yes | Frozen |
| Gate8 TVL fail-closed | Filter + verifier gates | Yes when TVL facts present | Unverifiable TVL → deny (honest); provider gaps |
| H05 exact-size | Env-gated path | Off in campaign | Must stay **OFF**; replay of H05-sized quotes N/A |
| EXECUTABLE / REJECTED | Verifier outcome + Paper classifier + settlement `Verdict` | Yes | V1 settle heads limit EXECUTABLE shape |

**Replay method (ops, no new engine):** re-invoke `FlashLoanEconomicsAssessor.aggregate_economics` / `GenericDexRouteEngine` evaluation from stored quote facts + fee/gas inputs; re-apply Gate7/8 filters; compare to recorded `gate7_pass` / `outcome_tag` / PaperOutcome.

**Not required for Gate9 SHADOW:** new replay microservice, wallet PnL engine, or second economics implementation.

---

## 4. Recommendation Mode readiness (Priority 4) — NO ACTIVATION

### 4.1 What exists

| Claimed “Recommendation Mode” | Code reality |
|---|---|
| Distinct ladder mode `RECOMMENDATION` | **Does not exist** (`FLASH_LOAN_ARCHITECTURE_AUDIT.md`: doc drift). Ladder = `OBSERVE → PAPER → SHADOW → LIMITED_LIVE → FULL_LIVE` |
| Human approval | `safety/approval.py` (`require_operator`, paper_validation gate); journal `operator_approved`; kill switch |
| Limited-live eligibility (advisory) | `execution/limited_live_eligibility.py` — fail-closed controls; **never enables** live |
| Operator readiness UI/API | `execution/operator_wizard.py`, live readiness probes, readiness control plane |
| Broadcast path | Only `LIMITED_LIVE` / `FULL_LIVE` + broadcaster; SHADOW/PAPER terminate at shadow record |

Intended safe story (conceptual, **not activated**):

```
SHADOW (detect + evidence)
  → advisory “would recommend” (eligibility + economics + unsigned plan)
  → human approval
  → LIMITED_LIVE (separate operator authority; executor deploy + caps + signer)
```

### 4.2 Minimal delta if any (propose only)

| Item | Needed for Gate9 SHADOW? | Needed for future Recommendation→limited-live? |
|---|---|---|
| New mode enum `RECOMMENDATION` | **No** | Optional docs/ops overlay only — prefer **not** adding a mode; use SHADOW + eligibility API |
| Wire ApprovalGate into auto-broadcast | **No / forbidden now** | Later, when LIMITED_LIVE deliberately enabled |
| Executor deploy + `ARBICORE_EXECUTOR_ADDRESS_*` | **No** for SHADOW | **Hard blocker** for value-producing limited-live |
| Paper validation ≥24h/72h continuity | Campaign itself | Soft prerequisite for approval policy (`require_paper_validation`) |

**Activation status:** **NONE.** Do not promote mode, do not enable AUTOEXEC/RUNTIME, do not unlock signer/broadcast.

---

## 5. Provider readiness (Priority 5)

| Provider / surface | Classification | Evidence |
|---|---|---|
| Alchemy credential fp `5e5d5bb1` | **SHADOW-PROVEN** (infra fix complete) | Monthly 429 **CLEARED**; eth Balancer P0 `ok`; six-chain RPC PASS (M6 post-alchemy) |
| Alchemy Free `eth_getLogs` ≤10-blk | **INFRA-BLOCKED** (long-window P1b) | Ethereum/Arb/Op/Poly long P1b `discovery_unavailable` (HTTP 400 range), not capacity 429 |
| Balancer P0 quote (ethereum) | **SHADOW-PROVEN** | M6 P0 known pool `ok` |
| Balancer P1 subgraph | **Incomplete** (ops config) | `ARBICORE_BALANCER_SUBGRAPH_URL_*` unset → expected unavailable |
| Balancer P1b short window (base) | **TESTED / partial SHADOW** | Base P1b `ok` (1 candidate) in M6 |
| Six-chain RPC wiring (H06/M6) | **WIRED + SHADOW-PROVEN** (seam) | All six PASS chainId/blockNumber |
| GENERIC_DEX × Aave × six chains | **TESTED + SHADOW-PROVEN** (econ path); **not ECONOMICALLY-PROVEN** (A=0) | M6 buckets |
| Aave adapter `supports_chains` vs BNB catalog | **Incomplete** mismatch | Matrix: BNB class C |
| UniV3 flash / Morpho Blue | **IMPLEMENTED** adapters; **not V1 EXEC**; Morpho weak defaults | Settlement rejects UniV3 flash; Morpho V2 profile |
| Empty pool inventory → 0 DiscoverySource candidates | **Ops/data incomplete** | Not Gate9 code blocker |

---

## 6. Exact gap list (P0 / P1 / P2 / P3)

### P0 — Gate9/10 campaign continuity (ops; **no code**)

| ID | Gap | Action |
|---|---|---|
| P0-1 | Prior Gate9 stamp **CONDITIONAL** (≈1.04h < 24h; paper evidence **0**) | Sustain unbroken SHADOW + paper-validation runner ≥24h then ≥72h; **do not** interrupt campaign |
| P0-2 | Zero paper evidence / opportunities_processed | Keep single feeder (`PaperValidationRunner`); inventory/market may stay empty — honest; do **not** fake EXECUTABLE |
| P0-3 | Safety posture drift risk | Keep SHADOW; AUTOEXEC/RUNTIME **false**; Gate7=$25; Gate8/H05 fail-closed; no Recommendation/live |

### P1 — Provider / discovery quality (non-blocking for Gate9 continuity)

| ID | Gap | Notes |
|---|---|---|
| P1-1 | Alchemy Free getLogs block-range | Blocks long Balancer P1b on Alchemy chains — **INFRA**; do not change campaign for this |
| P1-2 | Balancer subgraph URLs unset | Ops-only optional config later |
| P1-3 | Polygon getLogs / gas unknown failures in M6 | Quality; fail-closed correct |
| P1-4 | Empty DiscoverySource inventory | Ops/data; harness still validated GENERIC_DEX |

### P2 — Evidence packaging / join (optional later; not Gate9 blocker)

| ID | Gap | Proposed change? |
|---|---|---|
| P2-1 | Paper inputs too thin for standalone reconstruct (E1) | Optional widen `pipeline._persist_evidence` inputs — **propose only** |
| P2-2 | Dual evidence sink join documentation | Docs/ops package only |
| P2-3 | Six-chain paper `eth_call` map Base-only | Quality-only (`simulator.py`) — prior plan **NO-GO** for Gate9–10 |

### P3 — Capability expansion (explicitly deferred; not Gate9)

| ID | Gap |
|---|---|
| P3-1 | Dedicated STABLECOIN / LST_LRT engines |
| P3-2 | MULTI_HOP first-class shadow campaign |
| P3-3 | Morpho / UniV3 flash on V1 receiver |
| P3-4 | CROSS_CHAIN executable / inventory / solver |
| P3-5 | Explicit `flash_repayment_amount` telemetry (E2) |
| P3-6 | True PaperBroker wallet (rejected by minimal delta plan) |
| P3-7 | Distinct `RECOMMENDATION` mode enum |

---

## 7. Proposed code changes (propose only — **DO NOT IMPLEMENT**)

| # | Files | Reason | Tests | Safe without SHADOW campaign change? |
|---|---|---|---|---|
| C0 | — | **None required** for Gate9 continuity | — | **N/A — preferred** |
| C1 (optional P2) | `app/backend/arbicore/execution/pipeline.py` (`_persist_evidence` inputs) | Persist route_family / hop summary / net / flash_fee for standalone paper reconstruct | `tests/test_v2118_paper_validation_slice_a.py` (+ pipeline glue) | **Yes** if deployed offline / next image **without** restarting campaign mid-window; prefer wait until after ≥24h stamp |
| C2 (optional quality) | `app/backend/arbicore/paper/simulator.py` `SimulationRouter.from_env` | Six-chain eth_call via existing `ARBICORE_RPC_URL_*` | `tests/test_v2118_paper_validation_slice_b.py` | **Yes** same caveat; **not** Gate9 criteria |
| C3 (deferred) | `…/flash_loan_arbitrage/verifier.py` `_build_evidence_bundle` | Add `flash_repayment_amount_usd/wei` telemetry | verifier / M2 evidence tests | **Yes** additive; low priority |
| C4 (deferred capability) | Aave adapter `supports_chains` include `bnb` if desired | Catalog/adapter mismatch | adapter unit + M6-style row | **Yes** but deferred |
| C5 (forbidden now) | mode / AUTOEXEC / RUNTIME / ApprovalGate live wire / signer | Recommendation or limited-live activation | — | **No — do not** |

**Explicit non-proposals:** new evidence DB; parallel econ engine; PaperBroker wallet; Gate7/8/H05 weaken; SHADOW interrupt.

---

## 8. Campaign & safety confirmation

| Check | Status |
|---|---|
| This audit modified app source? | **No** |
| This audit changed runtime flags / restarted / shortened SHADOW? | **No** |
| Recommendation / AUTOEXEC / RUNTIME / signing / broadcast / live? | **Not enabled; not proposed for now** |
| Gate7 $25 / Gate8 / H05? | **Unchanged** |
| Continue Gate9 SHADOW in parallel with this readiness workstream? | **Yes** |

---

## 9. FINAL STATUS

# **READY (parallel) — no code before Gate9**

Continue the official Gate 9/10 **SHADOW** campaign uninterrupted. Parallel readiness work is **documentation + deferred proposals only**. Capability incompleteness and provider Free-tier limits are **non-blocking** for Gate9 continuity. Prior paper Gate9 stamp remains **CONDITIONAL** until duration + evidence continuity accrue.

---

## Appendix — Artifact index

| Artifact | Path |
|---|---|
| This audit | `docs/certification/24H_PARALLEL_READINESS_AUDIT_20261002.md` |
| Matrix addendum | `docs/certification/ARBITRAGE_CAPABILITY_MATRIX_AUDIT_20261002_ADDENDUM.md` |
| Matrix (binding) | `docs/certification/ARBITRAGE_CAPABILITY_MATRIX_AUDIT_20261002.md` |
| M6 post-alchemy | `docs/certification/M6_POST_ALCHEMY_RESET_SHADOW_20261002.md` + `reports/shadow_validation/m6_post_alchemy_reset_latest.json` |
| Paper Gate9 stamp | `docs/certification/PAPER_GATE9_10_VALIDATION_20261002.md` |
