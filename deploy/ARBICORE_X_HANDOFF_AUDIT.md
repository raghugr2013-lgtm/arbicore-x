# ArbiCore X — Emergent → VPS Production Handoff & Autonomous Execution Readiness Audit

*Read-only audit. No production code was modified. Every conclusion is tagged
**FACT** (verified from source/tests/git/runtime), **INFERENCE** (reasoned from
facts), or **RECOMMENDATION** (proposed action, not yet implemented).*

Audit basis: workspace `/app/app/backend` (+ `/app/deploy`), git `HEAD=313e0c2`
(`git describe = v2.9.2-93-g313e0c2`), tests in `arbicore/.../tests`, live runtime.

---

## 0. Executive verdict

**FACT.** ArbiCore X is fundamentally sound at the *component* level: the safety
model, evidence/learning DB, quoting, fork validation, and atomic-sim
infrastructure all work and are test-backed. The problems are **not** a VPS bug
and **not** a broken arbitrage engine.

**INFERENCE.** The pain is ~ **60% architecture complexity + source drift**,
**25% process/prompting**, **10% market-opportunity scarcity**, **5% genuine
bugs**. The dominant cause is *multiple coexisting architecture generations that
were never frozen into one canonical path*, plus a *deployment identity model
that let Emergent-source ≠ Git ≠ Docker ≠ VPS drift silently* (the `v2.9.2`
tag literally reads "Deployment profile disambiguation (fixes factory-mongo
misdeploy)" — evidence this already bit you once).

**The two blocked wizard prerequisites are the perfect microcosm** — one is an
intentional safety gate (`secret_available`), the other is a real *internal
interface drift* (`executor_verified`), not a VPS problem. See §4-blockers.

---

## 1. Current architecture (as actually wired)

**FACT — two discovery planes coexist:**

| Plane | Class / file | State | Role |
|---|---|---|---|
| **Active shadow engine** | `ContinuousScanner` → `OpportunityEngine` (`economics/opportunity_engine.py:486`; instantiated `server.py:332`) | **RUNNING** (90s) | Real Base market data → quotes → economics → funnel/evidence. Produces the `candidate_universe / real_quotes / negative_economics / executable` numbers you see. Shadow/paper-safe. |
| **Wave-1B shadow adapters** | `ShadowScannerAdapter` for `dex_arbitrage`, `flash_loan_arbitrage` (`scanners/wave1b/activation.py`) | **DORMANT** (never autostart) | Harness that registers the two named families; operator-started only. |
| **"Real" family scanners** | `DEXArbitrageScanner`, `FlashLoanArbitrageScanner`, `CEX/Funding/Launch/CrossChain` (`scanners/*/scanner.py`, wired in `runtime/composition.py`) | **GATED OFF** behind `ARBICORE_RUNTIME_AUTOSTART` (unset → disabled, `server.py:6787`) | Full runtime generation; intentionally not started. |
| **Live cross scanners** | `LiveMarketScanner`, `CexDexScanner`, `DexDexScanner` (`scanners/live/*`; `server.py:7291-7413`) | conditionally instantiated | Yet another generation. |

**INFERENCE.** That is **four** scanner generations in one tree. Only the
`ContinuousScanner`/`OpportunityEngine` plane is authoritative today; the rest
are dormant/gated/legacy. `activation.py` itself documents the intent: the real
`DEXArbitrageScanner`/`FlashLoanArbitrageScanner` are "present in the tree but
not instantiated … forbidden by the Sprint 1B charter." So the dormancy is
**C — intentional shadow architecture — layered on top of B — incomplete
migration** (the real classes were never wired to a live quoter and never
retired either).

---

## 2. Canonical source of truth (the fix for "Emergent ≠ Git ≠ Docker ≠ VPS")

**FACT.** Emergent commits to the workspace git after every step. There is **no
`origin` remote inside the Emergent pod** — GitHub push happens only via the
platform "Save to Github" button. Tags exist up to `v2.9.2`.

**RECOMMENDATION — adopt this single hierarchy and never deviate:**

```
Authoritative ranking (top wins on any disagreement):
  1. Git tag on origin/main         ← THE source of truth (immutable, signed)
  2. Docker image built FROM that exact tag (labelled with the commit sha)
  3. VPS running container == that image digest
  4. Emergent workspace             ← a DRAFT until pushed & tagged
  5. VPS working directory          ← must be read-only / never hand-edited
```

**Prove parity with these exact checks (run on VPS):**
```bash
# (1) what tag/commit is source
git -C /home/raghu/projects/arbicore-x-v2 describe --tags --always --dirty   # must NOT say "-dirty"
git rev-parse HEAD
# (2) image was built from that commit (label baked at build time — see §14 SOP)
docker inspect arbicore-x-backend --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}'
docker inspect arbicore-x-backend --format '{{ index .Config.Labels "org.opencontainers.image.version" }}'
# (3) running container digest == built image digest
docker inspect arbicore-x-backend --format '{{ .Image }}'
docker image inspect <image> --format '{{ .Id }}'
# (4) runtime self-reports the same identity (add /api/version — see §4 identity)
curl -s https://arbicorex.coinnike.com/api/arbicore/version
```
All four must agree on the **same commit sha**. If they don't, you have drift.

---

## 3. Emergent → VPS parity assessment

**FACT.** The atomic-sim "parity bug" does not exist. Tests explicitly assert the
losing fixture reverts: `test_iter16_signer_atomic_sim.py:109`,
`test_iter17_…:105`, `test_iter18_…:101` all `assert passed is False`, and
`SIMULATION_ONCHAIN` is asserted **YELLOW**. The VPS reproduces Emergent exactly.
Your own investigation reached the correct conclusion. **Independently verified.**

**FACT.** Fork validation uses the *correct* executor getters and passes on both
sides. Real difference between Emergent-preview and VPS is only *environmental*:
preview has no persistent Anvil and uses a free public RPC (rate-limit flake on
`RPC_STATE_OVERRIDE`); VPS has Anvil 1.7.1 + Alchemy. Neither changes program
behaviour.

**INFERENCE.** There is therefore **no code parity gap**. The remaining gaps are
(a) the executor-verify interface drift (§4), (b) deliberate safety gates, and
(c) no profitable market opportunity yet.

---

## 4. Current blockers — exact causes

### `secret_available = BLOCKED`
**FACT** (`operator_wizard.py:782-797`). The gas wallet has **no Fernet-wrapped
private key handle bound** (`secret_handle_id` empty or not in the secret
registry). **This is an intentional safety state** — you deliberately have not
injected a signing key. Canonical procedure to satisfy it (only when you choose
to go controlled-live): register the burner key via
`/api/arbicore/execution/secrets` (Fernet-wrapped with the existing `VAULT_KEY`),
then re-register the wallet with the returned `handle_id`. **Do NOT do this until
Gate 12.**

### `executor_verified = BLOCKED` — REAL DRIFT BUG (not a VPS problem)
**FACT.** The authoritative recovered ABI (`executor_entrypoint.py:34`) says the
deployed executor's getters are **`VAULT()`** (selector `411557d1`) and
**`ROUTER()`** (`32fe7b26`), plus `owner()`. Fork validation reads exactly those.

**FACT.** But `operator_wizard.verify_executor` (`operator_wizard.py:113-115`)
probes **different, non-existent function names**:
`balancerVault()`, `uniRouter()`, **and `aavePool()`**. The deployed
Balancer-V2+UniV3 executor has none of those selectors → every call returns
empty/reverts → `vault_matches / router_matches / aave_pool_matches` all BLOCKED
→ `executor_verified = BLOCKED`.

**INFERENCE.** `operator_wizard.py` is a **left-over from an earlier
"Aave-V3-first" executor generation** that was never reconciled when the executor
was re-specified to Balancer-V2 + UniV3. This is precisely the "multiple
architectural generations coexisting" problem — the wizard and the fork validator
disagree about what the executor *is*.

**RECOMMENDATION (do NOT implement during this audit).** Reconcile
`verify_executor` to the canonical ABI: probe `VAULT()`/`ROUTER()` (the selectors
`executor_entrypoint.py` already knows), drop the `aavePool()` requirement for the
Balancer+UniV3 head (or make it head-specific). One canonical executor-interface
constant module consumed by *both* the wizard and the fork validator.

### `scanner_family_enabled = WAIT`, `mode_limited_live = WAIT`
**FACT.** Intentional — the Flash-Loan family is not enabled and mode is SHADOW.
Correct for current safety posture.

---

## 5. Old vs new architecture — KEEP / MIGRATE / DEPRECATE / REMOVE

| Layer | Implementation | Verdict | Why |
|---|---|---|---|
| Discovery | `OpportunityEngine` + `ContinuousScanner` | **KEEP (canonical)** | Only plane producing real evidence today |
| Discovery | wave1b `ShadowScannerAdapter` (dex/flash) | **MIGRATE → fold into engine** | Redundant harness; keep only if it adds evidence the engine doesn't |
| Discovery | `runtime/composition.py` real family scanners | **DEPRECATE (freeze)** or **MIGRATE** | Gated-off generation; either wire ONE (flash-loan) to the canonical engine or retire |
| Discovery | `scanners/live/*` (Live/CexDex/DexDex) | **DEPRECATE** unless actively used | 4th generation → sprawl |
| Executor verify | `operator_wizard.verify_executor` (Aave naming) | **REMOVE/REPLACE** | Wrong interface (§4) |
| Executor ABI | `executor_entrypoint.py` (`VAULT()/ROUTER()`) | **KEEP (canonical)** | Matches deployed bytecode |
| Calldata | `execution/calldata.py` (Balancer V2 + UniV3 SwapHop[]) | **KEEP (canonical)** | Test-backed, matches executor |
| Atomic sim | `atomic_executor_sim.py` (+ new A/B diag) | **KEEP** | Correct, honest semantics |
| Aerodrome settlement | `aerodrome_settlement.py` | **DEPRECATE** unless a live head | Extra venue generation |

**RECOMMENDATION.** Declare ONE canonical path: `OpportunityEngine → calldata.py
→ executor_entrypoint (VAULT()/ROUTER()) → atomic_executor_sim`. Everything else
is KEEP-frozen, MIGRATE, or DEPRECATE. Do it as an explicit, approved refactor —
not incrementally.

---

## 6. Canonical scanner architecture (target)

**RECOMMENDATION.**
- **Discover:** `OpportunityEngine` enumerates the route universe and quotes it
  (real Base quotes) — this is the canonical discoverer. Retire the parallel
  scanner generations.
- **Canonical opportunity object:** the `OpportunityEngine` route/opportunity
  record persisted to `mid_opportunities` — one schema, one writer.
- **Economic validation:** `OpportunityEngine` economics (gas + fees + price
  impact + EV) — the funnel stage `negative_economics → positive_net →
  positive_ev`.
- **Atomic simulation submit:** only `positive_ev` + `executable` candidates get
  built into calldata and handed to `atomic_executor_sim.simulate_atomic`.

---

## 7. Canonical execution pipeline

**FACT/RECOMMENDATION.** Your proposed pipeline is essentially correct. Placement:
```
Market Data ─ OpportunityEngine (quoters)
  ↓ Opportunity Discovery ─ OpportunityEngine → mid_opportunities
  ↓ Route Quoting ─ quoter.py / adapters.py
  ↓ Economic Validation ─ OpportunityEngine economics (EV, gas, fees, impact)
  ↓ Execution Candidate ─ calldata.py (flash-loan construction + calldata gen)
  ↓ Atomic Simulation ─ atomic_executor_sim.py (eth_call / Anvil fork)   ← executor verification (executor_entrypoint VAULT()/ROUTER()) belongs HERE as a precondition
  ↓ Paper Execution ─ paper broker (SHADOW/PAPER)
  ↓ Risk Gate ─ kill-switch + mode ladder + certifier (11-stage)
  ↓ Human Approval / Autonomous Policy
  ↓ Signing ─ signer_vault.py (Fernet)   ← secret_available gate
  ↓ Broadcast ─ LimitedLiveBroadcaster
  ↓ Receipt → Post-trade Verification → Learning (adaptive weights/calibration)
```
- **Flash-loan construction & calldata:** `calldata.py`.
- **Executor verification:** precondition to atomic sim; must use the canonical
  `VAULT()/ROUTER()` interface (fix §4).
- **Signer:** `signer_vault.py`, only unlocked at Gate 12.
- **Risk engine:** kill-switch + mode + certifier, enforced at broadcast gate.
- **Paper broker / broadcast / post-trade:** as wired; keep broadcast gated.

---

## 8. Autonomous execution gates — status & required evidence

| Gate | Status | Evidence required | Never bypass? |
|---|---|---|---|
| 1 Infrastructure | ✅ PASS | backend healthy, container up | — |
| 2 RPC | ✅ PASS | `eth_chainId=8453`, block advancing (Alchemy) | — |
| 3 Provider/quotes | ✅ PASS | live UniV3 quotes returning | — |
| 4 Scanner running | ✅ PASS | `ContinuousScanner.running=true` | — |
| 5 Opportunity discovery | ✅ PASS | `candidate_universe>0`, `real_quotes>0` | — |
| 6 Real profitable quote | ❌ BLOCKED | ≥1 route `positive_ev`, `executable≥1` | — |
| 7 Atomic sim PASS | ❌ BLOCKED (depends on 6) | a *profitable* route eth_call/fork `passed=true` | **NEVER** — no fake green |
| 8 Paper execution | ⏸ pending 6-7 | paper fills logged in `arbicore_paper_evidence` | — |
| 9 24h validation | ⏸ | continuous run, uptime, non-negative paper P&L | — |
| 10 72h validation | ⏸ | sustained 72h, drawdown within limits | — |
| 11 Risk controls | partial | kill-switch READY ✅; caps/limits configured | **NEVER** |
| 12 Signer | ❌ BLOCKED (intentional) | Fernet key bound, `secret_available=READY` | **NEVER** unlock early |
| 13 Controlled live | 🔒 locked | Gates 1-12 green + `executor_verified` fixed + `mode=LIMITED_LIVE` + human confirm | **NEVER** auto |
| 14 Governed autonomy | 🔒 locked | sustained live track record + policy + circuit breakers | **NEVER** un-governed |

**FACT.** Gates 1-5 pass. **INFERENCE.** Gates 6-7 are blocked purely by *market
scarcity* (no profitable route right now), not by a code defect. Gate 12 blocked
intentionally. Gate 13 additionally blocked by the §4 executor-verify drift.

---

## 9. Is the atomic-sim objective wrong? — YES, partly

**FACT/RECOMMENDATION.** Forcing `atomic_simulation = PASS` on the *representative
losing fixture* is the wrong goal — that fixture is designed to lose (same-tier
round trip). The correct objective is exactly your flow:
```
find a genuinely profitable live Base opportunity → quote → positive net EV →
construct the exact flash-loan route → atomic-simulate THAT route → PASS →
paper execute → validate → controlled live.
```
The app already supports this: `OpportunityEngine` discovers, `calldata.py`
constructs, `atomic_executor_sim` simulates the *real* candidate. The new A/B diag
lets you also **block-pin a historical block where a spread existed** to prove
executor mechanics (distinct from live GREEN). Only a `live_rpc_latest` pass flips
the live matrix — keep it that way.

---

## 10. Market opportunity — "none right now" vs "can't find them"

**FACT (current funnel):** 134 universe / 228 evaluated / 164 real quotes / 64
quote failures / **164 negative economics / 0 positive net / 0 positive EV / 0
sim pass / 0 executable**. 15 liquidity measured.

**INFERENCE — it is currently "no profitable opportunities," but the scanner is
also under-powered to find the rare ones.** Two things are simultaneously true:
1. Base 2-hop same-family arbs are genuinely near-zero after fees+gas most of the
   time → 164 negative is *honest*, not a bug.
2. The discoverer is **narrow**: 15/164 liquidity-measured suggests thin
   liquidity/price-impact coverage; 64/228 quote failures (~28%) is high; DEX
   coverage appears UniV3-centric; 90s cadence misses fleeting spreads.

**RECOMMENDATION (diagnosis targets — audit, don't patch yet):** audit, in order,
(a) **quote-failure reasons** (28% is the biggest lever), (b) **DEX/venue
coverage** (add Aerodrome/Sushi/1inch-style multi-venue so cross-DEX spreads
appear), (c) **liquidity/price-impact model** (only 15 measured), (d) **cadence**
(faster loop or mempool/event-driven for fleeting spreads), (e) **gas/fee
assumptions** (verify not over-charging and killing marginal-positive routes),
(f) **route topology** (2-hop only vs triangular/multi-venue). Do NOT relax the
economic model to manufacture positives.

---

## 11. Prompting SOP (recommended template)

**RECOMMENDATION.** For every material change, prompt Emergent with:
```
CONTEXT: <feature/bug + canonical component it touches>
CONSTRAINTS: read-only unless approved; ONE canonical path; NO new compatibility
  layer — REPLACE the old implementation; do not enable downstream gates.
ASK:
 1. Read /app/memory/PRD.md + the canonical module(s) named below.
 2. Inspect current implementation; name exact files + line ranges.
 3. Explain current behaviour with evidence (tests/log/curl).
 4. Propose a plan. If it changes architecture, STOP for my approval.
 5. Implement only the approved scope.
 6. Run the exact existing test suite; report pass/fail counts.
 7. Report: changed files, commit sha, deployment impact, migration impact,
    rollback procedure.
 8. STOP. Do not chain the next task.
CANONICAL MODULES: <list>
DEFINITION OF DONE: <observable, testable outcome>
```
**Never** send "fix this". **Always** say "REPLACE, do not add a compatibility
layer" when superseding an implementation.

---

## 12. STOP-DOING list (blunt)

- Stop treating an **Emergent test PASS as proof of profitable live execution**.
- Stop chasing the **losing fixture to GREEN** — it is meant to lose.
- Stop **hand-editing code on the VPS** — VPS is deploy-only, never a source.
- Stop **deploying without an immutable commit sha + image digest** baked in.
- Stop letting **multiple scanner/executor generations coexist** un-frozen.
- Stop treating **configuration presence as functional readiness** (an env var
  set ≠ a verified capability — cf. `executor_verified` drift).
- Stop **enabling downstream gates before upstream ones pass**.
- Stop **changing multiple architectural layers in one prompt**.
- Stop assuming **UI routes == backend routes** (verify against OpenAPI).
- Stop running the **atomic sim against the public RPC for tracing** — use local
  Anvil (full trace).

## 13. DO-EVERY-TIME list

`DESIGN → (approve if architecture) → IMPLEMENT one canonical path → TEST (exact
existing suite) → COMMIT (sha) → TAG (semver) → BUILD (image labelled with sha) →
DEPLOY (additive, non-destructive) → VERIFY (identity + smoke + funnel + safety) →
ACCEPT → only then continue.` One change, one commit, one image, one verified
deploy. Keep SHADOW/locks until a gate is genuinely met.

## 14. Production deployment SOP

1. **Source freeze** — `git status` clean; no `-dirty`.
2. **Commit + tag** — `git tag -a vX.Y.Z -m "…"; push via Save-to-Github`.
3. **Tests** — run the exact suite; record pass counts in the tag message.
4. **Docker build with identity labels**:
   `docker build --label org.opencontainers.image.revision=$(git rev-parse HEAD)
   --label org.opencontainers.image.version=vX.Y.Z -t arbicore-x-backend:vX.Y.Z .`
5. **Image identity** — record `docker image inspect --format '{{.Id}}'` (digest).
6. **VPS deploy (additive, non-destructive)** — per `VPS_CONTINUITY_RUNBOOK.md`:
   backup `factory-mongo→arbicore_x`, capture pre-counts, then
   `docker compose build backend frontend opportunity-center` +
   `up -d --no-deps …`. Never `down -v`; preserve `VAULT_KEY/MONGO_URL/DB_NAME`.
7. **Env config** — presence-only check; never print secrets.
8. **DB migrations** — additive/optional fields only; STOP on any destructive
   migration.
9. **Health checks** — `/api/` 200; anon `/api/arbicore/*` → 401.
10. **Route inventory** — snapshot OpenAPI path count; diff vs previous deploy.
11. **Backend smoke** — readiness-matrix, executor-abi, run-fork-validation,
    run-atomic-sim (expect honest YELLOW), signer status (present/matches).
12. **Frontend smoke** — key pages load; API base correct.
13. **Scanner checks** — `ContinuousScanner.running=true`, funnel advancing.
14. **RPC checks** — chain 8453, block advancing, debug_traceCall works.
15. **Execution safety** — SHADOW; LIMITED_LIVE + FULL_AUTOMATION locked;
    AUTOEXEC/RUNTIME autostart false; kill-switch armed.
16. **Post-count continuity** — `post_count ≥ pre_count` every collection.
17. **Rollback** — redeploy prior image tag for the 3 app services; DB untouched.

## 15. Scores & root-cause split

| Dimension | Score | Rationale |
|---|---|---|
| Architecture | **6/10** | Sound components, but 4 scanner generations + executor-interface drift = unfrozen canon |
| Code quality | **8/10** | Test-backed, honest semantics, typed; drift is the exception |
| Deployment model | **5/10** | No enforced identity chain; a misdeploy already happened (v2.9.2 tag) |
| Production parity | **8/10** | No code parity gap; only env + one drift bug |
| Scanner readiness | **6/10** | Discovers reliably; coverage/quote-failure/cadence limit rare-opp capture |
| Execution readiness | **4/10** | Blocked by executor-verify drift + intentional signer gate |
| Autonomy readiness | **2/10** | Correctly far away; gates 6-14 not met (by design) |

**Root-cause split (INFERENCE):** C architecture complexity **~35%**, E/D
source-of-truth + deployment identity **~25%**, D process/prompting **~15%**,
G market scarcity **~15%**, A genuine bugs **~5%** (the executor-verify drift),
F config **~5%**. → **Answer: H (a combination), dominated by C + E/D.**

**Is ArbiCore X fundamentally sound? YES.** You are not fighting a broken engine
or a VPS bug. You are fighting *unfrozen architecture + weak deployment identity +
market scarcity*. All three are fixable with process, not rewrites.

---

## 16. Exact next 10 actions (in order)

1. **Freeze the canonical path** (design doc, approved): OpportunityEngine →
   calldata.py → executor_entrypoint(VAULT()/ROUTER()) → atomic_executor_sim.
   Mark all other scanner/executor generations KEEP-frozen/DEPRECATE.
2. **Fix the executor-verify drift** (§4): make `verify_executor` use the
   canonical `VAULT()/ROUTER()` selectors and drop/guard `aavePool()`; share one
   executor-interface constant with `executor_entrypoint.py`. *(approved change)*
3. **Add deployment identity** — `/api/arbicore/version` returning commit sha,
   image digest, build ts, tag; bake `--label …revision/version` at build.
4. **Establish the source-of-truth parity check** (§2 four commands) as a deploy
   gate; forbid VPS hand-edits.
5. **Audit quote failures** (64/228 ≈ 28%) — categorise reasons; this is the
   biggest opportunity-discovery lever.
6. **Expand DEX/venue coverage** (multi-venue cross-DEX) so real spreads surface;
   verify liquidity/price-impact model (only 15/164 measured).
7. **Tune cadence** for fleeting spreads (faster loop / event-driven) — SHADOW.
8. **Run block-pinned proof-of-mechanics** (new A) on a historical block where a
   spread existed → prove executor path end-to-end without going live.
9. **When a live positive-EV route appears**, let it flow Gate 6→7 naturally;
   only then does SIMULATION_ONCHAIN go GREEN honestly.
10. **Start 24h→72h paper validation** (Gates 8-10) once Gate 7 passes on a real
    route; keep signer (Gate 12) locked until you consciously choose Gate 13.

## Final recommendation

**RECOMMENDATION.** Treat this as a *governance + convergence* effort, not a
debugging effort. (1) Freeze one canonical path and delete/deprecate the rest.
(2) Fix the one real drift bug (executor-verify). (3) Enforce an immutable
Emergent→Git→Docker→VPS identity chain. (4) Invest discovery effort in coverage,
not in forcing a losing fixture green. Do these and the system becomes one
controlled, traceable pipeline whose only remaining gate to autonomy is a genuine,
validated, profitable track record — exactly where a system like this *should*
be gated.
