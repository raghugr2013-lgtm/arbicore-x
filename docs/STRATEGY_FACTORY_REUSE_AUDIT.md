# Strategy Factory → ArbiCore X Canonical-Reuse Audit (AUDIT & PLAN ONLY)

Branch `phase3/final-proof-completion` (HEAD `53482ae`); `main` untouched
(`621faea`). No code ported, no data changed, no safety gate touched, no
signer/broadcast/live enabled. **No secrets requested or exposed.**

> ⚠️ **Blocker — Strategy Factory source not available.** The repository
> `strategy-factory-canonical` is **not present anywhere in this environment**:
> no matching directory, none of its signature modules exist on disk
> (`strategy_ir.py`, `strategy_engine.py`, `mutation_engine.py`,
> `evolution_engine.py`, `auto_factory_engine.py`, `gem_factory_engine.py`,
> `optimization_engine.py`, `strategy_ingestion.py`, `knowledge/…`), and the only
> git repo here is ArbiCore (`origin` = arbicore-x). I therefore **cannot trace SF
> imports/callers/tests** and will **not fabricate** an audit of code I cannot see.
> The **ArbiCore side is fully audited** below from real modules; every
> Strategy-Factory-side classification is marked **`SF-UNVERIFIED`** and requires
> the repo to finalize. See §17 for exactly what is needed.

---

## 1. EXECUTIVE CONCLUSION

- The intended boundary is **sound and already latent in the codebase**: ArbiCore X
  already implements the entire *downstream* half (opportunity/economics/optimizer/
  simulation/evidence/provenance/learning-advisory/safety), and **lacks** the classic
  *upstream research* half (generic Strategy IR/DSL, generation/mutation/**evolution**,
  **backtest / walk-forward / Monte-Carlo / robustness** research validation, and an
  **external-knowledge connector framework** — GitHub/arXiv/etc.). Grep evidence:
  `evolution=0, backtest=0, walk_forward=0, monte=0, robustness=0, knowledge=1` files
  in ArbiCore, versus `economics/optimizer/evidence/provenance/learning/discovery`
  all richly present.
- **Recommendation:** keep ArbiCore as the sole authority for on-chain economics +
  safety + execution eligibility; adopt Strategy Factory as an **out-of-process
  upstream candidate producer** that hands ArbiCore a normalized **Strategy IR +
  provenance + fingerprint + version** and **never** touches ArbiCore's hard gates.
  Integrate via a **one-way ingestion contract**, not a merge.
- Because the SF repo is unavailable, the SF-component A–F verdicts here are
  **provisional (SF-UNVERIFIED)** and framed by capability; they must be confirmed
  against the actual SF code before any porting.

## 2. STRATEGY FACTORY → ARBICORE REUSE MATRIX

Classification uses the requested A–F. Where the SF implementation cannot be seen,
the verdict is the **role-based** recommendation and is tagged `SF-UNVERIFIED`.

| Capability | Strategy Factory location | ArbiCore equivalent (real) | Class | Recommendation |
|---|---|---|---|---|
| Strategy IR / schema / serialization | `strategy_ir*`, `ir_interpreter`, `ir_telemetry` (SF-UNVERIFIED) | Opportunity/route contracts: `arbicore/models/{opportunity_contract,canonical,discovery,enums}.py` (opportunity-level, **not** a generic strategy DSL) | **C** | Adapt SF IR → an ArbiCore-side **StrategyIR ingest schema** (EVM/DEX/flash fields). Keep ArbiCore contracts canonical downstream. |
| Strategy identity / fingerprint | SF fingerprints (SF-UNVERIFIED) | Fingerprints in `data/mid/schemas.py`, `intelligence/wave3/memory.py`, scanners; opportunity/route hashes | **A** (concept) / **C** (strategy-level) | Reuse ArbiCore's hashing; add a **strategy_fingerprint** at the IR boundary. |
| Strategy library / memory / versioning | `strategy_library`, `strategy_memory` (SF-UNVERIFIED) | Partial: `intelligence/wave3/memory.py`, `learning/ledger.py`; **no** general strategy registry | **C** | New ArbiCore **strategy_registry** collection keyed by fingerprint+version (see §8). |
| Lifecycle state machine | `strategy_lifecycle`, `strategy_profiler` (SF-UNVERIFIED) | `scanners/flash_loan_arbitrage/strategy_tagging.py`; execution-mode ladder in `execution/mode.py` | **C** | Adapt SF lifecycle states → candidate states (`DISCOVERED→IR→EVALUATED→SIM→PAPER→SHADOW→…`), gated by ArbiCore evidence. |
| Generation / mutation / **evolution** | `strategy_engine`, `mutation_engine`, `evolution_engine`, `auto_factory*`, `gem_factory_engine` (SF-UNVERIFIED) | **None** (evolution=0) | **B/D** | Keep **out-of-process in SF**. ArbiCore only *ingests + evaluates* candidates. Port as architecture (D), not FX-coupled code. |
| Optimization portfolio | `optimization_engine`, `ga_optimizer`, `random_search_optimizer`, `optimization_portfolio_bridge` (SF-UNVERIFIED) | `economics/size_optimizer.py` (notional/liquidity/gas/flash/EV — proven Phase-2/3) | **A** (sizing) / **C** (multi-candidate portfolio search) | Keep ArbiCore sizing canonical; SF GA/search may **rank/propose** candidates only. |
| Strategy ingestion | `strategy_ingestion` (SF-UNVERIFIED) | `arbicore/*ingestion*` (9 files, discovery-oriented) | **C** | New **one-way ingestion endpoint** normalizing SF output → StrategyIR + provenance. |
| Knowledge / external intelligence | `knowledge/`, trust scorer, GitHub/arXiv connectors (SF-UNVERIFIED) | Almost none (`knowledge=1`); `intel/` (entity resolve/cluster/score), `intelligence/confidence*` | **C** | New connector framework, **legitimate public sources only**; output = provenance-tagged candidates, never executable. |
| Validation research (backtest/WF/OOS/MC/regime/stress) | SF research suite (SF-UNVERIFIED) | `regime` (38 files), `postvalidation/`, `certification/`, `shadow/`, `paper/`; **no** backtest/WF/MC | **C** | Adapt SF research to EVM/DEX (historical fork replay, OOS on decision history). |
| Ranking / EV / confidence | SF ranking (SF-UNVERIFIED) | `intelligence/{confidence,roi_probability,scoring}.py`, `economics/expected_value.py` | **A** | Keep ArbiCore canonical; SF may feed *inputs* to ranking only. |
| Learning / meta-learning | SF learning loop (SF-UNVERIFIED) | `learning/{calibration,outcomes,route_success,weights,ledger}.py` (advisory, proven) | **A** (loop) / **D** (meta concepts) | Keep ArbiCore learning canonical + advisory-only; SF meta-learning informs research direction, never gates. |
| Provenance / evidence | SF provenance (SF-UNVERIFIED) | `evidence/{bundle,signer,audit_provenance}.py` (Ed25519 audit signer), provenance in 100 files | **A** | Keep ArbiCore evidence canonical; require SF candidates to carry source provenance. |
| Signer / broadcast / execution authority | (must not exist in SF) | `execution/*`, kill switch, allowlists, sim gate | **F** | **Never** exposed to or influenced by SF. Hard boundary. |

## 3. EXACT COMPONENTS WORTH REUSING (B/C — pending SF verification)
1. **Strategy IR schema + interpreter** (C) — the biggest genuine gap; adapt to EVM/DEX/flash.
2. **Evolution/mutation engine** (B/D) — run **in SF**, emit IR candidates; do not port FX code.
3. **External-knowledge connector framework + trust/confidence/provenance** (C) — public sources only.
4. **Backtest / walk-forward / Monte-Carlo / robustness** research (C) — adapt to fork/decision-history.
5. **GA/random-search portfolio optimizer** (C) — as a *candidate proposer*, not the on-chain sizer.

## 4. COMPONENTS THAT MUST REMAIN SEPARATE (D/E/F)
- All **generation/mutation/evolution/auto-factory** engines → stay in SF (out-of-process).
- Anything touching **execution/signer/broadcast/kill switch/allowlists** → **F** (never cross).
- FX-market-specific assumptions (sessions, pip/lot, FX regimes) → **E** unless generalized.

## 5. EXISTING ARBICORE COMPONENTS THAT ALREADY SOLVE THE REQUIREMENT (class A — do NOT duplicate)
- Economics/EV/optimizer: `economics/*` (proven Phase-2/3).
- Simulation gate + decision: `economics/opportunity_decision.py` (11 hard checks).
- Learning (advisory): `learning/*`. Evidence/provenance: `evidence/*`, 100 provenance files.
- Confidence/ROI/scoring/ranking: `intelligence/*`. Discovery/venues: `discovery/*`.
- Safety authority: `execution/*`, kill switch, allowlists, capital policy.
→ **Keep one canonical implementation each; SF must feed these, never replace them.**

## 6. MISSING INTEGRATION POINTS
1. **StrategyIR ingest contract** (schema + validation + fingerprint + version + provenance).
2. **`strategy_registry`** store (identity/version/lineage/lifecycle/evidence links).
3. **One-way ingestion API** `POST /api/strategy/candidates` (admin-only, non-executable).
4. **Candidate→opportunity adapter** feeding the existing economics/sim pipeline.
5. **External-knowledge connector framework** (public sources, provenance, trust).
6. **Research validation adapters** (fork replay / OOS on decision history).

## 7. PROPOSED ARCHITECTURE / DATA FLOW
```
Strategy Factory (separate process/repo)
  research → generation → mutation → evolution → GA/search → validation(backtest/WF/OOS/MC)
        │  emits: StrategyIR + provenance + fingerprint + version  (candidate, NON-executable)
        ▼   one-way, authenticated, admin-only ingestion (no reverse control channel)
ArbiCore X (authority)
  ingest+validate IR → strategy_registry → candidate→opportunity adapter
    → discovery/route → quote+freshness → liquidity → gas+flash economics → EV/confidence
    → size optimizer → simulation gate (11 hard checks) → fork/OOS/stress → evidence gate
    → ranking → PAPER/SHADOW (fail-closed) → [operator-gated] future LIVE eligibility
```
Boundary invariant: SF influences **ranking/selection/hypotheses/optimization/research
direction only**; ArbiCore's kill switch, signer, broadcast, allowlists, quote
freshness, repayment, calldata, risk limits, readiness gates are **never** reachable
from SF input.

## 8. DATABASE / SCHEMA IMPACT (additive only)
- New collections (no changes to existing/historical data):
  - `strategy_registry` `{ strategy_id, fingerprint, version, lineage[], source_class(INTERNAL|EXTERNAL|MUTATED|HYBRID), provenance{source,url,ts,trust,confidence}, lifecycle_state, evidence_refs[], created_at }`
  - `strategy_candidates` (raw ingested IR + validation status)
  - `knowledge_sources` (connector provenance/trust audit)
- Indexes: unique `(fingerprint, version)`; `lifecycle_state`; `source_class`.
- **No** modification to `decision_history`, evidence bundles, execution/safety state.

## 9. API IMPACT
- Add (admin-auth, non-executable, behind existing auth): `POST /api/strategy/candidates`
  (ingest IR), `GET /api/strategy/candidates`, `GET /api/strategy/registry/{id}`.
- **No** new endpoint may set execution mode, engage/disengage kill switch, or trigger
  broadcast. Reuse existing `require_auth`/admin gating.

## 10. SECURITY / PROPRIETARY-STRATEGY PROTECTION
- Persist/transport **strategy_id + version + fingerprint + capability descriptors**;
  keep full strategy logic internal. Do **not** emit strategy internals via calldata,
  events, frontend, public APIs, telemetry or exports.
- Honest note: on-chain calldata/state is inherently observable — do **not** claim
  strategies can be made mathematically invisible; the goal is **leakage minimization**.
- SF ingestion is **inbound-only**; no ArbiCore secret, key, or execution control is
  exposed to SF.

## 11. EXTERNAL STRATEGY INTELLIGENCE DESIGN
`Public source → connector → trust/confidence → provenance → extraction → StrategyIR →
candidate → ArbiCore economic eval → simulation/OOS/stress → evidence → ranking →
mutation/improvement → versioned candidate`. Every candidate retains source, URL/ref,
timestamp, provenance, trust, original identity, transformation history,
INTERNAL/EXTERNAL/MUTATED/HYBRID class, validation evidence. **Legitimate public
sources only** — no paywall/robots/access-control/credential bypass. External
candidates are **never** auto-executable.

## 12. LEARNING / META-LEARNING INTEGRATION
Keep ArbiCore's advisory learning canonical (`learning/*`, proven advisory-only:
confidence never flips a hard gate). SF meta-learning may propose research direction /
priors / candidate priorities. Hard rule (already enforced): learning/SF may influence
ranking, confidence, probability, provider/route hypotheses, sizing suggestions,
prioritization — and **never** kill switch, signer, broadcast, repayment, calldata,
quote freshness, risk limits, readiness, authorization. Require versioning + validation
+ rollback + audit trail + future-data-leakage guard on any imported model/policy.

## 13. TEST REQUIREMENTS (for the eventual implementation)
- IR schema validation + fingerprint determinism; malformed/oversized/hostile IR rejected.
- Ingestion is non-executable (candidate cannot reach execution without full ArbiCore gates).
- Boundary tests: SF input cannot alter kill switch / mode / allowlists / broadcast.
- Provenance/trust preserved end-to-end; source_class transitions correct.
- External-connector safety (public-source-only) + rate/robots compliance.
- Future-data-leakage regression for any SF-fed learning.
- Regression: existing economics/optimizer/safety suites remain green.

## 14. IMPLEMENTATION ORDER (after SF repo is provided)
1. Confirm SF A–F verdicts against real SF code (this audit's prerequisite).
2. Define StrategyIR ingest schema + fingerprint (C).
3. `strategy_registry` + candidate store (additive DB).
4. One-way admin ingestion API + candidate→opportunity adapter.
5. Wire candidates through existing economics/sim/evidence (no gate changes).
6. External-knowledge connector framework (public sources).
7. Research validation adapters (fork/OOS).
8. SF meta-learning → advisory inputs only.

## 15. RISK / COMPLEXITY MATRIX
| Item | Complexity | Risk | Notes |
|---|---|---|---|
| StrategyIR ingest schema | M | Low | Additive; well-bounded. |
| strategy_registry / candidate store | M | Low | Additive collections. |
| Ingestion API + adapter | M | Med | Must stay non-executable; boundary tests mandatory. |
| External knowledge connectors | H | Med | Legal/robots compliance; provenance/trust. |
| Research validation (fork/OOS) | H | Med | Needs archive RPC (currently BLOCKED-BY-ENV). |
| Evolution/GA reuse | M–H | Med | Keep out-of-process; architecture only. |
| Any execution-path coupling | — | **Critical** | **Forbidden (F).** |

## 16. WHAT SHOULD NOT BE PORTED (F / E)
- Any SF code that could set execution mode, engage/disengage kill switch, sign, or
  broadcast (**F**). FX-specific market/session/pip/lot logic (**E**). Any reverse
  control channel from SF into ArbiCore safety/execution (**F**).

## 17. RECOMMENDED NEXT ACTION
**Provide the `strategy-factory-canonical` repository to this environment** (read-only
clone/checkout or archive) so the SF-side of §1–§6 can be finalized against real code:
- exact modules present + whether production/functional/dormant/legacy,
- their dependencies (DB/API/env/external services) and test coverage,
- confirmation of the provisional A–F verdicts.
Do **not** paste credentials; a read-only checkout is sufficient. Until then, this
report is complete on the **ArbiCore side** and provisional on the **SF side**, and
**no code will be ported**. Safety posture unchanged: **SHADOW=READY, PAPER/
LIMITED_LIVE/FULL_AUTOMATION=BLOCKED.**
