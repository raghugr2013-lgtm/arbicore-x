# Wave 6B · Verification Report — Provider-Agnostic Execution Framework

**Date:** 2026-07-31  
**Wave:** 6B of the Execution Roadmap  
**Philosophy applied:** VERIFY → REUSE → REFINE → ACTIVATE → MERGE → NEW

---

## 1 · Canonical Verification Report

Before writing any code the canonical repository (`arbicore-x-v1.0.2.bundle`) was re-extracted and inspected for existing execution, routing, transaction-building, flash-loan, ABI, DEX, and provider abstractions.

| Component sought | Canonical location | Finding | Decision |
|---|---|---|---|
| Flash-loan provider catalog | `arbicore/scanners/flash_loan_arbitrage/economics.py::FLASH_LOAN_PROVIDERS` | ✅ Present. Aave V3 (5 bps), Balancer V2 (0 bps), Uniswap V3 (pool-tier). Chain support incl. Base. **Operator-locked.** | **REUSE** — surfaced verbatim via new adapters. Fee semantics preserved. |
| Flash-loan opportunity verifier | `arbicore/scanners/flash_loan_arbitrage/verifier.py` | ✅ Present. 325 LOC. Produces `CanonicalOpportunity` with legs; consumes a `QuoteProvider`. **Does not build calldata.** | **REUSE** — inputs to the planner. |
| Route search / cycle enumeration | `arbicore/scanners/flash_loan_arbitrage/route_search.py` | ✅ Present. 192 LOC DFS + TVL gate. | **REUSE** — planner consumes its `RouteCycle` shape. |
| DEX quoter framework | `arbicore/scanners/dex_arbitrage/quoter.py` | ✅ `BaseDEXQuoter` ABC + `EVMV3Quoter` (uniswap_v3 / pancake_v3 / aerodrome × ethereum/arbitrum/base) | **REUSE** — Wave 6C will bind live quoters into the DryRunEngine. |
| `DEXQuoteResult` value object | same file | ✅ Present. | **REUSE**. |
| Executable-quote resolver | `services/execution/executable_quote.py` | Present but **CEX-side only**. | Not applicable to flash-loan planning. |
| **Execution DAG / on-chain plan** | ❌ | Not present. | **NEW** — `arbicore/execution/dag.py`. |
| **Adapter protocols (flash-loan + DEX)** | ❌ | Not present. Provider metadata is a plain dict; there is no `FlashLoanAdapter` / `DexAdapter` contract. | **NEW** — `arbicore/execution/adapters.py`. |
| **Planner (compose DAG)** | ❌ | Not present. | **NEW** — `arbicore/execution/planner.py`. |
| **Dry-run engine (pure Python economics)** | Partial via `flash_loan_arbitrage/economics.py::FlashLoanEconomicsAssessor` (economics for filtering) | Present for discovery-time economics; not per-plan. | **REFINE** — reused fee semantics; added `DryRunEngine` that operates on the DAG. |
| On-chain simulator (`eth_call`) | ❌ | Not present. | **DEFERRED to Wave 6C** — non-negotiable prerequisite for any broadcast. |
| Live signer / broadcast | ❌ (`connectors/evm_wallet.py` is `private_keys: never`) | Not present. | **DEFERRED to Wave 6D**. |

Conclusion: only 4 net-new modules are introduced. Every provider fee, chain support tuple, and DEX quoter interface is inherited from canonical.

---

## 2 · Components Reused vs Refined vs Newly Created

| Type | Component | Source | Reused / refined |
|---|---|---|---|
| REUSE | `FLASH_LOAN_PROVIDERS` fee schedule (5/0/pool-tier bps) | canonical | Fee semantics fed straight into `AaveV3FlashLoanAdapter`, `BalancerV2FlashLoanAdapter`, `UniswapV3FlashLoanAdapter` |
| REUSE | Provider `supports_chains` tuples | canonical | Adapter `.supports(chain)` method returns the same tuple |
| REUSE | `BaseDEXQuoter` addresses for Base (Uniswap V3, Aerodrome) | canonical | Copied verbatim into `ADDRESS_BOOK["base"]` with env override capability |
| REUSE | `DEXQuoteResult` shape | canonical | Wave 6C will feed this into the DryRun engine |
| REUSE | Wave 6A `ExecutionModeRepo` (broadcast guard) | preview | `assert_broadcast_allowed` consults the same repo the future signer will |
| REUSE | Wave 6A `WalletRegistryRepo` | preview | Planner consumes `signer_wallet_id` as a reference; never touches key material |
| REUSE | Wave 5 canonical-JSON hashing pattern | preview (Wave 5) | `plan_hash()` uses the same `sha256:<hex>` scheme so evidence signing composes trivially in Wave 6E |
| REFINE | Fee accounting for Uniswap V3 flash | canonical (static catalog default) | Adapter now surfaces the `fee_bps_default` **but** the `flash_fee_bps_override` at plan-build time takes precedence — matches canonical verifier semantics for pool-tier-aware fees |
| NEW | `arbicore/execution/dag.py` — `ExecutionStep`, `ExecutionPlan`, `validate_dag`, `plan_hash` | — | 170 LOC |
| NEW | `arbicore/execution/adapters.py` — Adapter protocols, 3 flash-loan + 2 DEX adapters, `AdapterRegistry` | — | 300 LOC |
| NEW | `arbicore/execution/planner.py` — `ExecutionPlanner`, `DryRunEngine`, `ExecutionPlansRepo`, `assert_broadcast_allowed` | — | 220 LOC |
| NEW | 4 REST endpoints in `server.py` | — | ~90 LOC additive |

**Total net-new: ~780 LOC. Zero existing code was rewritten.**

---

## 3 · Architecture Diagram — Execution Pipeline (Wave 6B state)

```
              ┌──────────────────────────────────────────────────┐
              │ Wave 6A Substrate (unchanged)                    │
              │                                                  │
              │   ExecutionModeRepo   WalletRegistry             │
              │   (SHADOW default)    (Base gas wallet)          │
              │   SecretRegistry      (audit trail)              │
              └──────────┬───────────────────┬───────────────────┘
                         │                   │
                         │ reads mode        │ reads wallet_id
                         │                   │ (reference only)
                         ▼                   ▼
      ┌───────────────────────────────────────────────────────┐
      │                    ExecutionPlanner                    │
      │  ─────────────────────────────────────────────         │
      │  Inputs:                                               │
      │    · strategy, chain (Base), borrow_token / amount     │
      │    · flash_loan_provider  (aave_v3 | balancer_v2 |     │
      │                             uniswap_v3)                │
      │    · swap_hops = [{dex, token_in, token_out,           │
      │                    amount_in_wei, min_out_wei,         │
      │                    fee_tier_bps}, …]                   │
      │    · signer_wallet_id (Wave 6A reference)              │
      │                                                        │
      │  Composes DAG via AdapterRegistry:                     │
      │                                                        │
      │       ┌─────────┐  ┌─────────┐  ┌─────────┐            │
      │       │ BORROW  │→ │ SWAP[+] │→ │  REPAY  │            │
      │       │  (fl)   │  │  (dex)  │  │  (fl)   │            │
      │       └─────────┘  └─────────┘  └────┬────┘            │
      │                                       │                │
      │                                 ┌─────▼─────┐          │
      │                                 │  PROFIT   │          │
      │                                 │(reconcil.)│          │
      │                                 └───────────┘          │
      │                                                        │
      │  Validates DAG · computes deterministic plan_hash      │
      └────────────┬───────────────────────────────────────────┘
                   │
                   ▼
      ┌───────────────────────────────────────────────────────┐
      │                    DryRunEngine                        │
      │  Pure Python — no chain calls.                         │
      │  · flash_fee_bps / flash_fee_wei from adapter          │
      │  · min_break_even_wei = borrow + premium               │
      │  · gross_profit / gas_estimate / net_profit_usd        │
      │  · profitable flag                                     │
      └────────────┬───────────────────────────────────────────┘
                   │
                   ▼
      ┌───────────────────────────────────────────────────────┐
      │            ExecutionPlansRepo (db.execution_plans)     │
      │  Append-only.  Indexed by plan_id + (strategy,        │
      │  created_at) + plan_hash.                              │
      └────────────┬───────────────────────────────────────────┘
                   │
                   ▼    (Wave 6E will attach this to Wave 5 signer via
                        source_component="execution_plan")
                   ══► future: signed evidence bundle per plan
```

**Hard invariants at Wave 6B:**
- `mode="SHADOW"` on every persisted plan.
- No private key or signed transaction anywhere in the pipeline.
- `assert_broadcast_allowed` exists but is **only** referenced from the future signer path — Wave 6B endpoints never invoke it.
- Every adapter output uses **placeholder symbols** (`__signer_wallet__`, `__deadline_plus_5m__`, `__factory__`) that a live signer must resolve before broadcast; unresolved placeholders would cause any broadcast attempt to fail loud.

---

## 4 · Test Results

| Suite | Result |
|---|---|
| Unit — DAG + Adapters + Planner + DryRun (`test_wave6b_unit.py`) | **26 / 26 pass** |
| HTTP contract (`test_v2_wave6b.py`) | **14 / 14 pass** |
| Full local pytest across Waves 1–6B | **291 / 291 pass** |
| testing_agent regression (`/app/test_reports/iteration_7.json`) | **100% backend success, 300/300 in agent-authored suite (added 9 SHADOW-invariant/security tests). `retest_needed=false`. Zero critical / minor issues. Zero action items.** |

Verified end-to-end via external `REACT_APP_BACKEND_URL`:

- Deterministic `plan_hash` across repeated builds of identical bodies.
- Every persisted plan carries `mode="SHADOW"`.
- No signed transaction, private key, or secret material anywhere in Wave-6B endpoint responses.
- Provider / chain / adapter rejections return an `error` field (never a partially-built plan).
- Wave 6A + intelligence endpoints still respond with contracted shapes.

---

## 5 · Remaining Gaps Before Wave 6C

| Gap | Why deferred | Wave-6C plan |
|---|---|---|
| Bytes-level ABI encoding of step args | Requires `eth-abi`; not needed for planning, only for on-chain simulation | Add `eth-abi` (or `web3-py`) as a Wave-6C dep; encode `steps[*].calldata` alongside the structured intent |
| `eth_call` dry-run against an actual node | Requires an RPC provider (Alchemy / Infura / self-hosted). Config-driven | Introduce `SimulatorBackend` protocol; ship `EthCallSimulator` and `NoopSimulator` |
| Live gas oracle (`eth_gasPrice` / `eth_feeHistory`) | Requires RPC provider | Refine `DryRunEngine.gas_estimate_usd` to consume `GasOracle` protocol |
| MEV private-relay interface | Explicitly deferred to Wave 6C per the plan | `MevRouterBackend` protocol; standard RPC default; Flashbots / MEV-Blocker as opt-in |
| Uniswap V3 flash-borrow pool address resolution | Depends on canonical `RouteSearchEngine` output which carries the pool address | Planner will pull `contract_address` from the RouteCycle when Wave 6C wires the live quoter |
| Aerodrome factory address plumbing | Placeholder `__factory__` symbol today | Resolve from the Aerodrome deploy address on Base |

None of the gaps affect the SHADOW-mode planning surface. Wave 6B ships a complete, evidence-grade plan payload that Wave 6C's simulator will consume verbatim.

---

## 6 · Compliance With Engineering Philosophy

| Principle | Evidence |
|---|---|
| **VERIFY** | Canonical bundle re-extracted; provider catalog, verifier, quoter, and DEX router addresses inspected before writing any adapter. Documented in §1. |
| **REUSE** | Fee schedule, chain-support tuples, DEX router addresses, canonical-JSON hashing scheme, Wave 6A repos — all reused verbatim. |
| **REFINE** | Uniswap V3 flash fee resolution (pool tier > catalog default) refined into `flash_fee_bps_override` at plan-build time. |
| **ACTIVATE** | Wave 6A `assert_broadcast_allowed` gate is exposed to the planner but intentionally inert — it will be hot-wired by Wave 6D signer. |
| **MERGE** | No duplicate implementations introduced. |
| **NEW** | Four minimal files (`dag.py`, `adapters.py`, `planner.py`, endpoints) — ~780 LOC net-new. |

---

## 7 · Ready for Wave 6C approval

Wave 6B is production-ready in the planning sense: every flash-loan opportunity discovered by the canonical scanner can now be turned into a fully-specified, deterministic, persistable, evidence-hashable execution plan on Base — without touching a private key, without a live RPC, and without touching any prior contract.

Wave 6C (on-chain simulation + gas estimation + MEV interface) can begin immediately upon approval of this report.
