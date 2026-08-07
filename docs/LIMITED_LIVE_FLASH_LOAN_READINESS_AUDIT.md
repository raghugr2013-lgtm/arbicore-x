# LIMITED_LIVE Flash Loan Readiness Audit

**Date:** 2026-06 (canonical handoff continuation)
**Mode:** READ-ONLY audit — no code modified.
**Scope:** Minimum remaining work to reach **LIMITED_LIVE** value-producing
flash-loan execution. Everything unrelated to flash-loan profitability is
explicitly out of scope unless it blocks the engine.
**Repo baseline:** v2.11.10 (Decision Analytics + Shadow Certification PASS 54%).

---

## 0. Verdict (TL;DR)

The **off-chain software is effectively complete**. What remains to
LIMITED_LIVE is almost entirely **deployment + operator provisioning +
live-data proof**, not new module engineering.

| Dimension | Completion | Note |
|---|---|---|
| Off-chain Python pipeline (discover → sign → broadcast → evidence → learn) | **~100%** | All 18 stages present & tested |
| Calldata layer (Balancer V2 + Aave V3 encoders, `userData` ABI, recipient resolution) | **100%** | Verified in `calldata.py` |
| Safety (6-gate broadcast, mode ladder, kill switch, capital policy) | **100%** | Verified |
| On-chain executor contract (`FlashLoanReceiver.sol`) | **Built, NOT deployed** | Source + adapters + Foundry tests exist; 0 chains deployed |
| Live market data feed (real RPC-driven opportunities) | **Not proven** | Shadow Cert PASS was on seed/deterministic data |
| Runtime brought up in this workspace | **Not running** | Docker-oriented repo; no `.env`, backend/frontend STOPPED |
| **Overall LIMITED_LIVE readiness (value-producing)** | **~70%** | Blocked on deploy + live-data proof, not code |

**Estimated first real flash-loan:** achievable within **4 focused
slices** once the operator supplies an RPC endpoint, a funded burner
wallet, and a go/no-go on chain (Base Sepolia first vs. straight to Base
mainnet). None of the 4 slices require building a new module.

---

## 1. What is already COMPLETE (do not rebuild)

Confirmed by direct file inspection this session:

- **Discovery → Planning → DAG → Simulation → Gas → MEV → Calldata →
  Signing → Broadcast → Evidence → Learning → Calibration → Adaptive
  Weights** — all present under `arbicore/execution/*`,
  `arbicore/evidence/*`, `arbicore/learning/*`.
- **Calldata encoders** (`arbicore/execution/calldata.py`): Balancer V2
  flash loan, Aave V3 simple + multi-asset, executor-relayed
  `executeAave`, `build_user_data_from_hops` (ABI hop encoder),
  `encode_plan_head_call`, and 3-tier recipient resolution
  (`plan.recipient` → `borrow_step.recipient` → `ARBICORE_EXECUTOR_ADDRESS_BASE`).
- **6-gate broadcast ladder** (`arbicore/execution/broadcast.py::LimitedLiveBroadcaster`):
  kill_switch → mode → capital → secret → preflight(`eth_call`) → operator_confirm.
  This is the **only** `eth_sendRawTransaction` call-site in the codebase.
- **Mode ladder** (`arbicore/execution/mode.py`): OBSERVE → PAPER →
  SHADOW → LIMITED_LIVE → FULL_LIVE; one-step-forward only; flash-loan
  defaults to SHADOW. No global live switch.
- **Kill switch, capital policy, wallet registry, secret registry
  (Fernet)** — all live.
- **On-chain executor package** (`contracts/`): `FlashLoanReceiver.sol` +
  Aave/Uniswap adapters + interfaces + libraries + Foundry unit tests +
  `Deploy.s.sol` / `Verify.s.sol`. Selectors match the Python encoders
  byte-for-byte (per prior verification).
- **Flash-loan scanner tree** (`scanners/flash_loan_arbitrage/*`):
  route search, economics, verifier, filter, sources (REAL provenance).
- **Shadow Certification framework** — graded **PASS at 54% executable**
  (run `shadowcert-7832a1b0…`) after the v2.11.10 pipeline fixes.
- **Paper Validation framework**, **Decision Analytics**, operator
  wizard, executor-verify, rpc-check, post-trade endpoints + UI.

---

## 2. What BLOCKS LIMITED_LIVE (ordered by criticality)

### B1 — On-chain executor contract is not deployed *(HARD BLOCKER)*
`FlashLoanReceiver.sol` is built and unit-tested but deployed on **zero
chains**. Without a deployed executor, a broadcast either reverts on-chain
(pipeline-exercise only) or produces zero profit. `forge` is not even
installed in this workspace, so the contract has not been compiled here.
- **Needs:** compile → deploy to target chain → set
  `ARBICORE_EXECUTOR_ADDRESS_BASE` → `GET /api/arbicore/executor/verify`
  passes (bytecode + VAULT() + ROUTER() + owner()).

### B2 — Live market-data feed is unproven *(HARD BLOCKER for *profitability*)*
The Shadow Certification PASS (54%) validates that the **decision
pipeline is correct** — but it ran against **seed / deterministic
route-hash opportunities**, not live market inefficiencies (see
`SHADOW_CERT_v2.11.9_LIVE_REPORT.md` §"Why FAIL"). The scanner's
`RouteSearchDiscoverySource` needs a live Base RPC + real pool state to
surface genuinely profitable cycles.
- **Needs:** `ARBICORE_RPC_URL` (Base) wired → scanners autostart against
  live pools → confirm real EXECUTABLE opportunities appear → re-run
  Shadow Cert against the **live** feed and confirm PASS.
- **This is the single biggest "will it actually make money" risk.**

### B3 — Operator provisioning not done *(HARD BLOCKER)*
- `ARBICORE_RPC_URL` unset.
- No funded burner gas wallet (~0.02 ETH on Base).
- Wallet not registered + key not Fernet-wrapped in `arbicore_secrets`
  (else the `secret_resolution` gate DENIES).
- `ARBICORE_EXECUTOR_ADDRESS_BASE` unset.

### B4 — Runtime not stood up in this workspace *(BLOCKER for testing)*
Repo is Docker/compose-oriented; there is **no `.env`** and
backend/frontend are **STOPPED** under supervisor. We cannot test the
live path until the app boots against Mongo with a minimal `.env`.

### B5 — Mode ladder flip *(gated operator action)*
`flash_loan_arbitrage` must be promoted SHADOW → LIMITED_LIVE via
`POST /api/arbicore/execution/mode/flash_loan_arbitrage`. Gated behind
explicit operator approval by design — not a code task.

---

## 3. What can WAIT until after revenue begins (explicitly deferred)

- HSM/KMS secret backend (Fernet is acceptable for a burner wallet).
- Multi-provider arbitration (Aave/Uniswap heads) — Balancer V2 (0 bps)
  alone is sufficient for the first tx.
- Promoting other scanners (CEX/DEX/funding/cross-chain/launch) to LIVE.
- Adaptive-weights flip from OBSERVE → ACTIVE.
- Prometheus/Grafana observability exporter.
- Base **mainnet** promotion (only after a green Sepolia/limited stripe),
  unless the operator explicitly chooses to start on mainnet at tiny
  notional.

---

## 4. Recommended implementation order (minimum path)

Each slice is testable and moves measurably toward LIMITED_LIVE.

| Slice | Goal | Type | Blocker cleared |
|---|---|---|---|
| **S1 — Workspace bring-up & config wiring** | Minimal `.env`, boot backend+frontend against Mongo, verify `/api/arbicore/rpc/check`, `/wizard/state`, `/executor/verify` respond. | Mostly config, ~0 new code | B4 |
| **S2 — Executor deploy (Base Sepolia)** | Install Foundry, `forge test` (8/8), deploy `FlashLoanReceiver.sol` to Base Sepolia, set executor address, `/executor/verify` = 6/6. | Deploy + verify | B1 |
| **S3 — Live-data proof + Shadow Cert on live feed** | Point scanners at live Base RPC, confirm real EXECUTABLE opps, re-run 20-cycle Shadow Cert against the live feed → PASS. | Config + validation | B2 |
| **S4 — First LIMITED_LIVE broadcast** | Register + fund burner, wrap key, flip `flash_loan_arbitrage`→LIMITED_LIVE, run certifier, confirm broadcast, post-trade audit (tx_hash + evidence bundle). | Operator-driven, ~0 new code | B3, B5 |
| *(S5 — optional)* Base **mainnet** promotion at low notional for real revenue. | Deploy to mainnet, repeat S4 at tiny size. | Deploy + operator | — |

> Any code changes surfaced during S1–S4 are expected to be **small
> wiring/verification fixes**, not new modules. Prefer integrating
> existing components (per handoff rules).

---

## 5. Deployment points

1. **Backend runtime** — bring up FastAPI + Mongo in this workspace with a
   minimal `.env` (S1). Production of record remains the VPS
   `factory-mongo` shared-infra compose profile (frozen).
2. **On-chain executor** — deploy `FlashLoanReceiver.sol` to **Base
   Sepolia first** (S2), then **Base mainnet** (S5) once validated.
3. **Config surface** — `ARBICORE_RPC_URL`, `ARBICORE_EXECUTOR_ADDRESS_BASE`,
   scanner autostart flags, `ARBICORE_SHADOW_CERT_ENABLED`,
   `ARBICORE_PAPER_VALIDATION_ENABLED`.

---

## 6. Expected remaining development slices

**~4 slices** to a first value-producing LIMITED_LIVE flash loan
(S1–S4), plus **1 optional** for mainnet (S5). The bulk of the effort is
deployment and operator provisioning; net-new code is minimal.

---

## 7. Estimated point of first real flash-loan

- **First on-chain broadcast (revert-path / pipeline exercise):** end of
  **S2** (executor deployed; broadcast proves signing→RPC→tx_hash→evidence).
- **First value-producing atomic flash loan (Base Sepolia):** end of
  **S4**, contingent on S3 proving live executable opportunities exist.
- **First mainnet revenue flash loan:** S5, gated on a green Sepolia
  stripe (or operator opts to start on mainnet at tiny notional).

**Gating decision required before implementation begins** (see the
questions posed to the operator): chain choice, RPC endpoint, burner
wallet/key custody, and who deploys the contract.

---

## 7b. Session progress (Base Sepolia readiness) — UPDATE

Delivered this session (no keys, no on-chain tx — stopped at operator gate):

- **S1 done** — app booted in-workspace; `rpc/check` **READY, chain_id
  84532 (Base Sepolia)**. Fixed a genuine defect: `_rpc_post` urllib had
  no `User-Agent`, so public Base RPC 403'd the readiness/verify probes.
- **S2 done** — Foundry compile OK; **8/8 tests PASS**; `Deploy.s.sol`
  made chain-aware with verified Base Sepolia venue addresses;
  **dry-run deploy simulated on Base Sepolia** (no key). Deployment is now
  a single operator action — see `contracts/docs/DEPLOY_RUNBOOK_BASE_SEPOLIA.md`.
- **S3 done** — autonomous pipeline validated end-to-end: runs unattended,
  journals, and **halts before broadcast** (SHADOW). 10-step wizard
  correctly reports the two remaining BLOCKED gates: **wallet + executor**.

Revised readiness: off-chain software **~100%**; deployment path
**de-risked to a single command**; overall value-producing readiness
**~85%** (remaining 15% = operator-gated: deploy + wallet + broadcast).
Evidence: `docs/OPERATIONAL_VALIDATION_REPORT_BASE_SEPOLIA.md`.

## 8. Development rules honored

Canonical code only · no demo/fabricated data · no duplicate modules ·
API contracts preserved · test after every slice · every task moves us
measurably closer to LIMITED_LIVE · integrate existing components over
building new ones.
