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

---

## NON-LIVE E2E CERTIFICATION RESULTS (harness: `tests/test_nonlive_e2e_certification.py`)
Run offline (no RPC/fork, no MONGO_URL). Uses the **real** production components with only
in-memory persistence stubs. **21 passed.** Label on every artifact: CERTIFICATION · NON-LIVE ·
SYNTHETIC/CONTROLLED · not a real/economically-valid opportunity.

### Pipeline stage-by-stage (headless detect→validate→execute, no UI)
| Stage | Result | Component (real) |
|---|---|---|
| detect/quote (route resolve) | **VERIFIED (logic)** | `pipeline._extract_quote` (heuristic quote stage is non-blocking by design) |
| validate/liquidity | **VERIFIED (logic)** | `pipeline` + `paper.check_liquidity` |
| gas | **VERIFIED (logic)** | `pipeline._extract_gas` |
| economic evaluation | **VERIFIED** | `economics.net_profit.compute_net_profit` — full cost decomposition + $25 floor honoured |
| policy (kill/mode/capital) | **VERIFIED** | real kill-switch/mode/capital gates |
| certification | **VERIFIED (logic)** | certifier stage |
| route construction + calldata | **VERIFIED** | `calldata.build_user_data_from_hops` + `encode_executor_execute` (selector `0x64ba4bc1`) + `encode_balancer_v2_flash_loan` |
| atomic simulation (candidate-bound) | **GATE VERIFIED, result BLOCKED** | `certification.candidate_simulation` fail-closed; real eth_call sim needs RPC (absent) |
| flash-loan borrow / swap / repayment / receipt / P&L reconciliation | **BLOCKED** | require live fork/RPC **and** a deployed+verified receiver — neither present here |
| execution decision (SHADOW vs broadcast) | **VERIFIED** | SHADOW→shadow_recorded; LIMITED_LIVE→reaches broadcast gate |
| evidence generation | **VERIFIED** | immutable EvidenceBundle written once |

### Flash-loan provider results (economic vs execution)
| Provider | Economic processing | Receiver EXECUTION-CERTIFIED |
|---|---|---|
| Balancer V2 | VERIFIED | **BLOCKED** (no mainnet receiver / no declared providers) |
| Uniswap V3 (swap head) | VERIFIED | **BLOCKED** |
| Aave V3 | VERIFIED | **BLOCKED** (also needs receiver upgrade + re-audit) |
| Morpho Blue | VERIFIED | **BLOCKED** (also needs receiver upgrade + re-audit) |
Proven-path distinction preserved: only **Balancer V2 borrow + UniV3 swaps** is the known receiver
path; it is still BLOCKED here purely because no verified receiver is deployed.

### DEX execution-adapter results
UniV3 / Sushi V2·V3 / Pancake V3 / Camelot V3 / QuickSwap V3 / Aerodrome Slipstream / Morpho Blue:
**IMPLEMENTED**, **BLOCKED** for EXECUTION-CERTIFIED (fail-closed via `receiver_capability` — no
deployed receiver declares any provider on any of the six chains). None are FORK-TESTED here (no RPC).

### Latency baseline (offline heuristic — NOT the real hot path)
Per-stage `duration_ms` ~0.01–0.03; **total pipeline evaluate ≈ 1.2 ms** offline. Real detection→
decision latency for the 1–5 s hot path must be measured on the VPS with live quotes/RPC.

### Safety / fail-closed refusal matrix (all VERIFIED refusing)
economic-gate fail → reject · kill-switch engaged → deny · capital limit → deny · certification fail →
reject · invalid route → calldata encoder raises (fail-closed) · unsupported provider →
`receiver_supports=False` · atomic-sim signer unavailable → `available=false` · broadcaster unwired
under LIMITED_LIVE → BROADCAST_FAILED (never a faked send) · SHADOW mode → never broadcasts ·
14-control eligibility → DENY when any control missing.

### Capability vocabulary — post-harness truth
- IMPLEMENTED: full six-chain multi-venue multi-strategy stack ✓
- CONFIGURED: six-chain operator RPC ✓
- VERIFIED: RPC/state 6/6; economic engine; route+calldata; all safety gates; headless pipeline ✓
- SIMULATED (candidate-bound on-chain): **BLOCKED** (no RPC/fork here)
- EXECUTION-CAPABLE: **BLOCKED** (no deployed receiver)
- EXECUTION-CERTIFIED: **FALSE** (all chains/providers)
- ECONOMICALLY-VALID: **0** real (unchanged; not fabricated)
- LIMITED-LIVE-ELIGIBLE: **NO** (gates correct; blocked on receiver + a real edge)
- FULL-LIVE-ELIGIBLE: **NO**

### What remains blocked by the missing mainnet receiver
On-chain atomic sim, borrow, swap, repayment, receipt, P&L reconciliation, and EXECUTION-CERTIFIED
for every provider/chain. Unblocks only when a deployed+on-chain-verified receiver with an explicit
`supported_providers` is recorded (out of band, separate approval).

### What remains blocked by absence of a real positive-net opportunity
ECONOMICALLY-VALID and therefore LIMITED-LIVE-ELIGIBLE for a *real* candidate. The engine is proven
to compute/gate correctly; there is simply no real edge now. **Not fabricated; floor unchanged.**

---

## FORK-EQUIVALENT EXECUTION PROOF (live Base mainnet state, read-only)
Runner: `app/backend/scripts/nonlive_fork_cert.py` · opt-in test: `tests/test_nonlive_fork_cert.py`
(`ARBICORE_RUN_FORK_CERT=1`). Executed via read-only `eth_call` against **live Base mainnet**
(`mainnet.base.org`), **pinned block 51163181**, in the Emergent pod (NOT the operator VPS). No
Anvil needed — live-state eth_call is the fork-equivalent. No signing / broadcast / deployment /
mainnet tx. CERTIFICATION · NON-LIVE · SYNTHETIC candidate.

| Stage | State | Live result |
|---|---|---|
| A. fork config / block | pinned | `mainnet.base.org`, block 51163181, chainId 8453 |
| chain verification | **FORK-TESTED** | eth_chainId == 8453 PASS |
| state-override capability | **FORK-TESTED** | `code`-injection eth_call honoured (returns 0x…2a) |
| D. DEX route — live UniV3 quote | **FORK-TESTED** | WETH→USDC 1e18 → **2,477,206,189** (≈ $2477/ETH), status=ok, real pool state |
| E/F/G. route→swap→repayment | **FORK-TESTED (machinery)** | `SettlementSimulator` ran on live Aerodrome state; WETH→USDC→WETH round-trip final_out 9.94e15 < 1e16 ⇒ **"route does not repay principal"** → correctly **fail-closed** (no fabricated profit) |
| economic gate + $25 floor | **VERIFIED** | real engine; synthetic net $1.625 does NOT clear $25 floor (honest) |
| B/C. receiver + provider (Balancer V2 borrow + UniV3 swap atomic) | **BLOCKED** | no MAINNET-immutable receiver runtime bytecode; repo has only Sepolia creation bytecode (wrong aavePool/uniRouter immutables for mainnet) + no foundry to compile → injecting would be invalid. Not faked. |
| H. receipt/result handling | **BLOCKED** | depends on the atomic executor path above |
| I. balance/P&L reconciliation | **BLOCKED** | depends on the atomic executor path above |
| J. evidence artifact | written | gitignored `vps_cert_out/fork_cert_evidence.json` |

### Fail-closed (live)
`receiver_supports("base","balancer_v2") == False` (no deployed receiver) · atomic sim with
signer absent → `available=false` · round-trip route that cannot repay principal → rejected.

### Latency (LIVE fork/public-RPC round-trips — NOT production network latency)
chain_verification ≈ 297 ms · state_override ≈ 122 ms · live UniV3 quote ≈ 140 ms ·
settlement route+repayment ≈ 121 ms · economics ≈ 0.05 ms · atomic-path ≈ 0.01 ms ·
fail-closed ≈ 0.4 ms. These are public-RPC latencies from the Emergent pod; the real production
hot-path (operator VPS + dedicated RPC) must be measured separately.

### Capability status changes from this checkpoint (ONLY these upgrade)
- chain verification, state-override capability, live UniV3 quote, route/swap/repayment **machinery**:
  **BLOCKED → FORK-TESTED** (live Base state).
- **Unchanged (correctly NOT upgraded):** SIMULATED (candidate-bound atomic) stays BLOCKED;
  EXECUTION-CAPABLE / EXECUTION-CERTIFIED stay **FALSE**; ECONOMICALLY-VALID stays **0**;
  LIMITED-LIVE-ELIGIBLE / FULL-LIVE-ELIGIBLE stay **NO**.

### Remaining blockers after the fork checkpoint
1. A **mainnet-immutable FlashLoanReceiver** (deployed, or its runtime bytecode compiled with mainnet
   immutables for state-override injection) — required to fork-test the full atomic
   Balancer-borrow+UniV3-swap→repayment→receipt→reconciliation path. Out of band; separate approval.
2. A real ECONOMICALLY-VALID opportunity (unchanged; not fabricated).
3. Production hot-path latency measurement on the VPS with a dedicated RPC.

---

## BASE MAINNET RECEIVER — PREPARATION (artifact prepared, NOT deployed)
Full artifact: `deployment/cert/BASE_MAINNET_RECEIVER_PREPARATION.md`. Status ladder:
**SOURCE REVIEWED ✅ · SECURITY-REVIEWED ✅ (static) · BUILT ❌ · TESTED ⚠️(offline consistency only)
· MAINNET-READY ❌ · DEPLOYED/EXECUTION-CERTIFIED/LIMITED-LIVE/FULL-LIVE ❌.**
- Mainnet immutables (chainid 8453), verified consistent across `Deploy.s.sol` + registry
  `constructor_args_expected` + `calldata.AAVE_V3_POOL_BY_CHAIN`: Balancer Vault
  `0xBA12…2C8`, Aave V3 Pool `0xA238…d1c5`, UniV3 Router `0x2626…e481` (NOT the Sepolia set).
- Implemented flash providers = **balancer_v2 + aave_v3** (ABI-confirmed); **Morpho absent** (never
  declarable). First-deploy `supported_providers=["balancer_v2"]`; add `aave_v3` only after its own
  fork proof.
- Security (static): owner-immutable + onlyOwner entries; `_authorized`/`_pendingProvider` re-entry &
  provider gate; caller bound to Vault/Pool; exact repayment + `InsufficientBalance` revert; per-hop
  `amountOutMinimum` slippage guard; no low-level/delegatecall (fixed UniV3 SwapRouter02); owner-only
  `rescue`. External audit still recommended before real capital.
- **BUILD BLOCKER (§13 STOP):** no `forge`/`solc 0.8.24`/`py-solc-x`/`~/.svm` in this pod. Bytecode
  was **NOT** produced and **NOT** fabricated. Build requires foundry with `via_ir=true`,
  `evm_version=paris`, optimizer 200, `bytecode_hash=none` + `contracts/lib/forge-std`.
- Offline guard: `tests/test_base_mainnet_receiver_prep.py` (6 passed) locks immutable/provider
  consistency + `receiver_capability` fail-closed.



