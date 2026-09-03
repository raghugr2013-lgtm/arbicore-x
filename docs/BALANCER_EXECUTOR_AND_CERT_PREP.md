# Balancer V2 Executor Review + Trace-RPC Integration + P0 Certification Prep

**Mode:** REVIEW / PREPARATION ONLY. No execution/signer/broadcast/kill-switch/gate/
readiness/learning/Mongo changes. No feature built. Safety unchanged:
`effective_kill_engaged=true`, `live_execution_enabled=false`,
SHADOW=READY · PAPER/LIMITED_LIVE/FULL_AUTOMATION=BLOCKED.

---

## B. BALANCER V2 EXECUTOR REVIEW (audit only)

### Question: does ArbiCore already support Balancer V2 flash liquidity?
**Yes — the borrow side is already supported in code.** Evidence
(`arbicore/execution/calldata.py`):
- `encode_executor_execute(...)` encodes `FlashLoanReceiver.execute(address[] tokens,
  uint256[] amounts, bytes userData)` (selector `0x64ba4bc1`) — the **Balancer V2**
  LIMITED_LIVE entry point. The receiver opens its `_authorized` window, calls the
  Balancer V2 Vault `flashLoan(...)`, and receives the `receiveFlashLoan` callback.
- `encode_plan_head_call(...)` explicitly accepts **both** `balancer_v2` and `aave_v3`
  providers (raises `NotImplementedError` for anything else).
- `encode_balancer_v2_flash_loan(...)` (direct-to-Vault) exists and is unit-tested.
- Economics model Balancer: `net_profit.py` has `flash_loan_fee_bps` (Balancer = 0 bps);
  `provider_selection.py` prefers 0-fee venues (Balancer V2, Morpho Blue) then Aave V3 (5 bps).
- Vault address wired for Base: `0xBA12222222228d8Ba445958a75a0704d566BF2C8`.

### So what is actually missing / limited?
1. **Swap-leg venue restriction (the real constraint).** The executor callback only encodes
   **Uniswap V3** swap hops — `executor_capability.py` `SUPPORTED_DEXES = {"uniswap_v3"}`, and
   `build_user_data_from_hops(...)` emits `SwapHop[]` that the receiver executes via
   `SwapRouter02.exactInputSingle` per hop. Uniswap **V2** and **Aerodrome** legs are **not**
   executor-encodable (Aerodrome is explicitly UNSUPPORTED; unknown venues are UNVERIFIABLE →
   fail-closed). This is a **DEX-coverage** limit, not a flash-provider limit.
2. **On-chain self-test coverage gap.** `execution/technical_validation.py` exercises the
   **Aave V3** path only (`executeAave`). There is **no Balancer-V2 equivalent** self-test, so
   the Balancer path — though code-complete — is **UNPROVEN on-chain** (and proof needs RPC +
   a deployed executor anyway; see §C/§D).

### Mapping to today's real Base sample (correcting the MEV report)
Of the 7 observed arb-shaped flash txs today:
- **6 of 7** = **Balancer V2 flash + 2× Uniswap V3 swaps** → **route shape the current executor
  CAN encode** (Balancer borrow ✓ + Uniswap V3 hops ✓). *This corrects the earlier MEV report,
  which under-stated Balancer support by generalising from the Aave-only self-test.*
- **1 of 7** (`0x42756211…`) = Balancer flash + Uniswap V3 **+ Uniswap V2** → the V2 leg is
  **not** executor-encodable → executor-INCOMPATIBLE under the current Uniswap-V3-only callback.

### Can the existing architecture support it cleanly?
Yes — no new flash-provider work is required; the borrow path exists. The only clean extension
needed for broader capture is **adding Uniswap V2 (and optionally Aerodrome) swap-hop encoding**
to the executor callback + `SUPPORTED_DEXES` — but that is a **contract-side + calldata** change
and is **out of scope now** (no execution changes permitted).

### Security / safety implications (if a Balancer self-test or V2 hops were later added)
- Balancer borrow is **fee-free**, so first-tx cost is lower — no new signer/broadcast authority
  is introduced; the same 5-gate path (`KILL_SWITCH → MODE → CAPITAL → SECRET → PREFLIGHT`) applies.
- The receiver's `_authorized`/`_pendingProvider` re-entry guards must remain intact — a
  direct-to-Vault call still triggers `NotAuthorized()` (`0xea8e4eb5`); do not bypass.
- Adding new swap venues widens the on-chain attack surface (router allowlists, arbitrary-target
  risk). Any addition must keep the executor's allowlisted-router / no-arbitrary-target property
  (as the Aerodrome settlement adapter already enforces).
- Executor-capability must stay **fail-closed** (UNVERIFIABLE venue ⇒ denied).

### Minimum implementation to *prove* Balancer (when approved, not now)
- A `technical_validation`-style **Balancer self-test** (borrow tiny WETH via Balancer Vault →
  one real Uniswap V3 hop → repay; dry `eth_call` state-override first) — ~60–90 LOC, mirrors the
  Aave harness. Requires RPC + deployed executor.
- No borrow-side code change needed. (Uniswap V2 hop support is a *separate, larger*
  contract+calldata change — defer unless justified.)

### Does observed activity justify adding it?
- **Balancer proof: justified** — 6/7 of today's real Base flash-arbs used exactly the
  Balancer + Uniswap V3 shape the executor already encodes; proving it unlocks the majority of
  the observed opportunity class (once economics/RPC are live).
- **Uniswap V2 hop support: not yet justified** on this sample (1/7). Re-evaluate after a
  trace-enabled full-window scan quantifies how much value routes through V2/Aerodrome legs.

**Recommendation (B):** when approved and RPC is available, add the **Balancer on-chain
self-test only**; hold Uniswap-V2/Aerodrome executor swap-hop support pending trace-based
value evidence. **Do not implement now.**

---

## C. TRACE-ENABLED BASE RPC — INTEGRATION REQUIREMENTS (prepared; not wired)

No RPC is provisioned yet, so nothing is wired. When you provide the URL(s), integration uses
the **existing** config conventions — **no code change required**, credentials **env-only**
(never in code/Git/logs/reports/frontend).

### Required capabilities
| Need | Method(s) | Used by |
|---|---|---|
| Base mainnet read | `eth_chainId`, `eth_getBlockByNumber`, `eth_getTransactionReceipt`, `eth_getLogs`, `eth_call` | scanners, economics, sim gate |
| **Trace** (net-profit reconstruction) | `debug_traceTransaction` (callTracer) **or** `trace_transaction`/`trace_block` | MEV replay (§2 of your directive) |
| **Archive/historical** | `eth_call`/`eth_getBalance` at historical block, `--fork-block-number` | fork lifecycle, block-pinned atomic sim |

The public `mainnet.base.org` endpoint used in the MEV test supports the read + logs methods but
**NOT** `debug_trace*`/`trace_block` and is not archive — hence a provider such as
Alchemy/QuickNode (trace + archive tier) is required.

### Env keys the code already reads (set in `backend/.env`; then `sudo supervisorctl restart backend`)
- `ARBICORE_RPC_URL_BASE` **>** `ARBICORE_RPC_URL` **>** legacy `BASE_RPC_URL`
  (`config/persistent.py: resolve_rpc_url_from_env`, `first_rpc_endpoint` — comma-separated
  lists supported; first endpoint used for single-POST methods).
- `ARBICORE_ARCHIVE_RPC_URL` — archive/trace endpoint for fork + block-pinned diagnostics
  (referenced by the atomic-sim/fork readiness checklist in `server.py`).
- `ARBICORE_EXECUTOR_ADDRESS_BASE` — deployed `FlashLoanReceiver` (address only) for
  bytecode/executor proofs.
- Signer key (if ever a live self-test) stays in the **encrypted vault / KMS**, **never** `.env`.

### Wiring steps (when URL provided)
1. You paste the trace/archive RPC URL(s) (I will not print them back).
2. Add `ARBICORE_RPC_URL` (+ `ARBICORE_ARCHIVE_RPC_URL`) to `backend/.env` via a single-key edit
   (leave `MONGO_URL`/`DB_NAME` untouched).
3. `sudo supervisorctl restart backend`; verify `eth_chainId==0x2105` and `debug_traceTransaction`
   returns a trace for a known tx (fail-closed if unsupported — do not fabricate).
4. **No execution/safety code changes.** RPC only enables read/trace/sim proofs.

---

## D. P0 CERTIFICATION PREPARATION (real evidence only; BLOCKED until RPC)

Each proof below is prepared with the exact real-evidence procedure. All remain **BLOCKED-BY-
ENVIRONMENT** now (no trace/archive RPC, no `ARBICORE_EXECUTOR_ADDRESS_BASE`, `anvil` not
installed). **No gate will be weakened to obtain PASS.**

| Proof | Real evidence procedure | Blocker |
|---|---|---|
| **Base chain-ID** | `eth_chainId` == `0x2105` (8453) via `TechnicalValidator._chain_id()` | needs `ARBICORE_RPC_URL` |
| **Executor bytecode** | `eth_getCode(ARBICORE_EXECUTOR_ADDRESS_BASE)` non-empty + hash/ABI-selector check (`execute`,`executeAave`,`receiveFlashLoan`,`executeOperation`) | needs RPC + deployed executor address |
| **Atomic eth_call simulation** | `TechnicalValidator.preflight()` dry-run with WETH `stateDiff` override (execute=false) → no revert | needs RPC |
| **Fork lifecycle** | `AnvilRevmForkBackend`/`AnvilForkHarness`: `anvil --fork-url <archive>` → read-only checks → teardown | needs archive RPC **and** `anvil` binary (Foundry) — **not installed** |
| **Fork-based validation** | deterministic route tests via `/arbicore/engine/run-fork-validation` (fail-closed without RPC) | needs archive RPC + anvil |
| **Flash-loan on-chain verify** | Aave path via `technical_validation` (execute=false dry sim); Balancer path needs new self-test (§B) | needs RPC + executor |

### Install prerequisite you can pre-stage (no RPC needed, safe)
- **Foundry/anvil** is absent (`command -v anvil` → not found). Installing `anvil` is a
  read-only tooling prerequisite for fork proofs; it introduces **no** execution authority.
  (Not installed in this task — flagged for approval since it modifies the toolchain.)

### Order once RPC arrives
1. chain-ID → atomic eth_call sim → executor bytecode (fast, read-only).
2. install anvil → fork lifecycle → fork-based route validation.
3. flash on-chain verify (Aave dry-run; Balancer self-test if approved).
4. Re-run the MEV quantitative replay (directive §2) through the **existing** ArbiCore
   economics/EV/liquidity/slippage/sizing — no second economics model.

---

## SUMMARY

- **Findings:** ArbiCore **already supports Balancer V2 flash borrow** in code; the real limits
  are Uniswap-V3-only swap hops and an Aave-only on-chain self-test. **6/7** of today's real Base
  arbs match the executor's encodable shape (Balancer + 2× Uniswap V3) — correcting the earlier
  MEV report.
- **Blockers:** no trace/archive Base RPC; no `ARBICORE_EXECUTOR_ADDRESS_BASE`; `anvil` not
  installed. All P0 proofs honestly BLOCKED; nothing fabricated.
- **Exact RPC requirements:** trace-capable (`debug_traceTransaction`/`trace_block`) + archive
  Base RPC; set `ARBICORE_RPC_URL`(+`_BASE`) and `ARBICORE_ARCHIVE_RPC_URL` in `backend/.env`
  (env-only, no code change).
- **Exact Balancer V2 gap:** borrow = supported; missing = a Balancer on-chain self-test
  (~60–90 LOC, needs RPC+executor) and (separately, deferred) Uniswap-V2/Aerodrome swap-hop
  encoding (contract+calldata change; not yet justified — 1/7 sample).
- **Recommended next implementation (await approval):** Balancer on-chain self-test only, after
  trace RPC + executor address are provided; then run the quantitative MEV replay + P0 proofs.
- **Files changed:** none (review/prep only). **Commit:** none. **Tests:** none run (no code
  changed).
- **Safety verification:** unchanged — `effective_kill_engaged=true`, `live_execution_enabled=
  false`; SHADOW=READY, PAPER/LIMITED_LIVE/FULL_AUTOMATION=BLOCKED; signer/broadcast/kill/
  allowlists/gates/readiness/learning/Mongo/`main` all untouched.

*Stopping for approval before any implementation.*

---

## INFRASTRUCTURE STATUS UPDATE (2026-09-03)

- **Anvil/Foundry: INSTALLED** (approved read-only fork tooling). `anvil 1.8.1`
  (commit 982849d3, 2026-08-28), also `forge`/`cast` 1.8.1. Binaries persist at
  `/root/.foundry/bin`; symlinked into `/usr/local/bin` so the backend PATH resolves it.
  Verified live: `GET /api/arbicore/engine/fork-status` →
  `anvil_installed=true, anvil_path=/usr/local/bin/anvil, ready_to_run=false,
  reason="archive/fork RPC not configured (ARBICORE_ARCHIVE_RPC_URL)"`.
  *Caveat:* `/usr/local/bin` is non-persistent across pod restarts; re-run
  `ln -sf /root/.foundry/bin/anvil /usr/local/bin/anvil` if `anvil_installed` ever flips false.
  No live-execution flag enabled; anvil is for fork lifecycle / fork validation / deterministic
  sim only.
- **Trace/archive Base RPC: NOT PROVIDED** → items blocked below.
- **Executor address (`ARBICORE_EXECUTOR_ADDRESS_BASE`): NOT PROVIDED** → Balancer self-test +
  bytecode proof blocked.

### What is now unblocked vs still blocked
| Item | Status | Needs |
|---|---|---|
| Anvil install (fork prerequisite) | ✅ DONE | — |
| Base chain-ID proof | BLOCKED | `ARBICORE_RPC_URL` |
| Atomic eth_call sim | BLOCKED | `ARBICORE_RPC_URL` |
| Executor bytecode proof | BLOCKED | RPC + `ARBICORE_EXECUTOR_ADDRESS_BASE` |
| Fork lifecycle / fork validation | BLOCKED | `ARBICORE_ARCHIVE_RPC_URL` (anvil now present) |
| Flash on-chain verify (Aave dry) | BLOCKED | RPC + executor |
| Balancer V2 self-test | BLOCKED | RPC + executor |
| MEV quantitative replay | BLOCKED | trace-capable RPC |

No code changed; no Mongo impact; safety posture unchanged.
