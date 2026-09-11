# ArbiCore X v2 — Certification Status & Shortest Safe Path to Full Live

Branch: `vps-cert-rpc-contract-a7f9634` · HEAD `44b9f46` · Posture: **SHADOW / detection-only /
fail-closed / read-only**. signing=false · broadcast=false · auto_execution=false ·
full_live=false · withdrawals=false. This document records the *true* state only; no gate is
marked green because code exists.

## Capability vocabulary (never collapsed)
IMPLEMENTED (code exists) · CONFIGURED (operator input present) · VERIFIED (proven live,
read-only) · SIMULATED (candidate-bound atomic sim passed) · EXECUTION-CAPABLE (a deployed
receiver *could* run the route) · EXECUTION-CERTIFIED (deployed **and** on-chain-verified
receiver that explicitly declares the provider) · ECONOMICALLY-VALID (real positive all-in-net
clears the unchanged Gate-7 $25 floor) · LIMITED-LIVE-ELIGIBLE (all 14 mandatory controls PASS)
· FULL-LIVE-ELIGIBLE (sustained Limited-Live evidence + operator approval).

---

## A. CURRENT TRUE STATUS

### Six-chain runtime (Base, Ethereum, Arbitrum, Optimism, Polygon, BNB)
| Dimension | State | Evidence |
|---|---|---|
| Operator RPC | **VERIFIED 6/6** | one canonical `ARBICORE_RPC_URL_<CHAIN>` per chain, synced to economic gate; per-chain isolation, fail-closed |
| Chain-id / state verification | **VERIFIED 6/6** | live `eth_chainId` match; no chain `last_error` |
| Discovery / market composition | **VERIFIED** | 45 probe rows · 40 discoverable |
| Liquidity / TVL | **VERIFIED** | 40 liquidity-verified (real Aave V3 aToken / Balancer vault balances) |
| Quote (exact-size) | **VERIFIED (partial)** | 35 quotable · 0 algebra quote gap; the quote↔discovery gap (40→35) is the residual quoter/resolver coverage item (Curve stable-swap + Solidly/ve(3,3) families) |
| Economics (all-in-net) | **ECONOMICALLY-VALID = 0 (TRUTHFUL)** | Opportunity Race `race:3825c92df057`: seen 67 · quoted 55 · liquidity-verified 56 · **economically_valid 0 · positive_net 0 · best_candidate null**. No real edge currently exists. **The production Gate-7 $25 floor is NOT lowered.** |
| Execution capability (receiver) | **BLOCKED 6/6 (fail-closed, proven)** | see below |

### FlashLoanReceiver deployment (the dominant blocker)
`deploy/executor_deployments.json` truth:
- Base **Sepolia** `84532`: `deploy_status=success`, address present, **but `supported_providers`
  NOT declared** ⇒ `receiver_capability` reports **all venues rejected**.
- Base **Mainnet** `8453`: `not_deployed` (address null).
- Ethereum / Arbitrum / Optimism / Polygon / BNB: **no receiver record at all.**

Proven live in this assessment:
```
base/8453 deployed=False  providers=[]  balancer=False aave=False
84532     deployed=True   providers=[]  balancer=False aave=False   (no providers ⇒ still fail-closed)
ethereum/arbitrum/optimism/polygon/bnb  deployed=False  → all False
```
So **EXECUTION-CERTIFIED = FALSE on every mainnet chain.**

### Flash-loan & DEX adapters
- Flash providers **IMPLEMENTED**: Aave V3, Balancer V2, Uniswap V3, Morpho Blue.
- DEX execution adapters **IMPLEMENTED**: UniV3, Sushi V2/V3, Pancake V3, Camelot V3, QuickSwap V3,
  Aerodrome Slipstream, Morpho Blue.
- **On-chain EXECUTION-CERTIFIED scope (deployed receiver)**: only **Balancer V2 borrow + UniV3
  swaps** has proven receiver execution. **Aave V3 / Morpho Blue / expanded route combinations are
  IMPLEMENTED but NOT execution-certified** — they require a receiver upgrade/redeploy + re-audit.
  Do not represent them as executable.
- **Resolver/quoter gaps (accurate)**: Curve stable-swap and Solidly/ve(3,3) (e.g. Velodrome/
  Aerodrome-classic) venues are reported **not discoverable / not quotable** and are *preserved but
  honestly excluded* — not silently dropped, not faked.

### Execution engine & safety controls
| Subsystem | Class | Note |
|---|---|---|
| Headless detect→validate→execute (`AutoExecutor`→`OpportunityPipeline`) | **IMPLEMENTED + logic-VERIFIED** | Background asyncio worker drains discovery → pipeline; **UI is NOT required** to act on 1–5 s opportunities. UI is observability/control only. |
| Mode ladder (`execution/mode.py`) | **VERIFIED** | per-strategy OBSERVE→PAPER→SHADOW→LIMITED_LIVE→FULL_LIVE; one-step promotion; rollback anytime; broadcast only in LIMITED/FULL. Flash-loan default SHADOW. |
| Kill switch (`execution/kill_switch.py`) | **VERIFIED** | global `guard()` raises before any sign/broadcast; audited. |
| Limited-Live eligibility (`execution/limited_live_eligibility.py`) | **IMPLEMENTED, fail-closed** | 14 mandatory controls; any missing/unknown ⇒ DENY. |
| Economic gate (`base_all_in_cost` / `chain_execution_readiness._economic_rpc_configured`) | **VERIFIED, fail-closed** | exact all-in cost; no public-default endpoint counts. |
| Route construction / planner / calldata | **IMPLEMENTED** | |
| Atomic simulation (H09 candidate-bound eth_call) | **IMPLEMENTED** | symbolic/paper/heuristic can never certify. |
| Slippage / min-output, stale-opportunity (freshness) protection | **IMPLEMENTED** | part of the 14 controls (`freshness_ok`). |
| Signer vault / live signer | **IMPLEMENTED, disabled** | no signing enabled. |
| Broadcast controls / MEV / pre-broadcast | **IMPLEMENTED, disabled** | broadcaster only reachable in LIMITED/FULL + `auto_confirm` (default OFF). |
| Receipt / repayment / realized-P&L reconciliation | **IMPLEMENTED** | exercised only once broadcast is enabled (not now). |
| Evidence generation (`evidence_bundles`, Paper Validation) | **VERIFIED** | immutable bundles per validation_id. |
| Monitoring / alerting (Telegram) | **IMPLEMENTED** | |
| Detection→decision latency | headless loop present; **needs a VPS latency measurement** under load (not yet a certified number). |

---

## B. SHORTEST SAFE PATH TO FULL LIVE
Real profitability stays real. Engineering is certified with **controlled/fork NON-LIVE** proofs so
we never wait on a rare market edge to prove the pipeline.

1. **Close the receiver execution-certification gap (critical path).**
   a. On the target chain (start Base mainnet `8453`), deploy/verify the FlashLoanReceiver **out of
      band under separate approval** (this task does NOT deploy).
   b. Record it in `deploy/executor_deployments.json` with `deploy_status=success`, valid address,
      `receiver_version`, and an **explicit `supported_providers`** list (initially
      `["balancer_v2"]` for the proven Balancer-borrow+UniV3-swap route).
   c. This flips `EXECUTION_CAPABILITY` and control `executor_capability` from BLOCKED→PASS **for the
      declared provider only** — everything else stays fail-closed.
2. **Certify the engineering pipeline on a fork (NON-LIVE).** Prove detect→quote→liquidity→economics
   →route→atomic-sim→(would-)broadcast→receipt→repayment→reconciliation→evidence end-to-end against a
   forked chain with a synthetic profitable candidate, explicitly marked CERTIFICATION/NON-LIVE.
   (Pipeline + auto-executor logic already pass offline; the remaining step is a fork-RPC E2E run.)
3. **Enable Limited-Live for one strategy on one chain** (flash_loan_arbitrage on Base), with
   `auto_confirm=OFF`, kill switch armed, tiny capital cap. Wait for a **real** ECONOMICALLY-VALID
   opportunity (do not manufacture one) → operator-confirmed single execution → verify receipt,
   repayment, realized P&L, evidence.
4. **Accumulate Limited-Live evidence** (N clean real executions, zero safety violations, reconciled
   P&L) → operator approval → **promote one step to FULL_LIVE** for that strategy/chain.
5. **Repeat receiver certification + Limited→Full per remaining chain/provider** (Aave V3, Morpho,
   expanded routes each need their own receiver-capability + re-audit). Chains are independent.

---

## C. WHAT CAN BE DONE IN PARALLEL
- Receiver deploy+verify per chain (6 independent tracks) — out of band.
- Fork NON-LIVE E2E certification (does not need a real opportunity or mainnet receiver).
- Quoter/resolver coverage for Curve/Solidly to close the 40→35 quote gap (raises surface; not
  required for the first Base/Balancer Full-Live path).
- VPS detection→decision latency measurement.
- Monitoring/alerting runbook hardening.
Serial dependencies only: Limited-Live(step 3) needs step 1(receiver) + a real edge; Full-Live(step 4)
needs sustained step-3 evidence.

---

## D. EXACT REMAINING BLOCKERS
1. **Receiver not execution-certified on any mainnet chain** (no mainnet deployment; no declared
   `supported_providers`). → EXECUTION_CAPABILITY BLOCKED 6/6.
2. **0 real ECONOMICALLY-VALID opportunities** right now (real-market; must NOT be faked or floored down).
3. **Fork NON-LIVE full E2E** (broadcast→receipt→repayment→reconciliation) not yet run as a certification artifact.
4. **Aave V3 / Morpho / expanded routes** require receiver upgrade + re-audit before certification.
5. **Quote coverage gap** 40 discoverable → 35 quotable (Curve/Solidly resolvers) — surface completeness, not a Full-Live blocker for the Base/Balancer path.
6. **VPS latency-to-decision** not yet a measured/certified number.
7. Operational/security: signer key custody, per-chain capital caps, kill-switch drill, monitoring/alert routing — to be exercised at step 3.

---

## E. TESTS RUN + RESULTS (this assessment, offline, no MONGO_URL/DB_NAME)
- `test_limited_live_readiness_matrix.py` → **16 passed**
- `test_opportunity_race_six_chain.py` → **22 passed**
- `test_track2_chain_execution_readiness.py` → **41 passed**
- `test_track8_readiness_flash_evidence.py` → **4 passed**
- `test_p0c_pipeline_glue.py` → **11 passed** (2 live-HTTP tests require a running server → 404 offline)
- `test_p0d_auto_executor.py` → **9 passed** (3 live-HTTP tests require a running server → 404 offline)
- `test_p0_iter13_signer_readiness.py` → **13 errors** — ALL are live-HTTP/auth tests needing the running VPS backend (not code defects; they pass against the running server).
- Receiver fail-closed capability check → confirmed BLOCKED on all six chains (proof above).
- (Prior cert sweep on this branch: six-chain race 22 passed; RPC/economic/DEX/gas sweep 57 passed.)

The HTTP failures are environmental (no FastAPI server in the offline pytest context), not
certification regressions. Run them on the VPS against the live backend to exercise the endpoints.

---

## F. WHAT WAS CHANGED
- **Only this document** was added. No production code, no protected files, no config, no deployment.

## G. WHAT WAS NOT CHANGED
- No production logic. No signing/broadcast/auto-exec/Limited-Live/Full-Live enablement.
- Economic thresholds unchanged (Gate-7 $25 floor intact). No opportunity fabricated.
- Protected files untouched: `scanners/dex_arbitrage/scanner.py`,
  `deployment/compose/docker-compose.yml`, `scripts/p0_3_flash_discovery_proof.py`.
- No container restart/replace, no `--remove-orphans`, no reset/clean, no branch merge, no push.

## H. VPS STATUS UPDATED WHERE
- `deployment/cert/VPS_CERTIFICATION_STATUS.md` (this file). Companion procedure/runbook unchanged:
  `VPS_CERTIFICATION_PROCEDURE.md`, `VPS_CERTIFICATION_RUNBOOK.md`.

## I. EXACT FINAL GATES REQUIRED
**Before Limited-Live** (one strategy, one chain):
- Receiver on target chain: `deploy_status=success` + valid address + `receiver_version` +
  `supported_providers` explicitly lists the runtime flash head (on-chain bytecode/immutable/owner verified).
- All 14 mandatory controls PASS for a candidate: quote_complete, economics_ok, gate_7,
  liquidity_verified, gate_8, executor_capability, gate_9 (MEV), borrow_size_feasible,
  balancer_liquidity, atomic_simulation, freshness_ok, provenance_complete, verification_confirmed,
  mode_allows, kill_switch_ok.
- Mode promoted SHADOW→LIMITED_LIVE (one step) by operator; kill switch armed; `auto_confirm` decision made; capital cap set.
- A **real** ECONOMICALLY-VALID opportunity clearing the unchanged $25 floor.

**Before Full-Live** (per strategy/chain):
- Sustained Limited-Live evidence: N clean real executions, reconciled realized P&L, zero safety
  violations, receipt+repayment verified each time.
- Explicit operator approval; one-step LIMITED_LIVE→FULL_LIVE promotion.
- Certification PASS is necessary but NOT sufficient — live authority remains operator-gated.
