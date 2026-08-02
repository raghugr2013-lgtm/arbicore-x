# Operator Readiness Audit — Fresh, File-Verified

**Purpose:** Determine, from canonical files only, exactly what already exists in ArbiCore X that supports the production objective:

> Continuous Discovery LIVE + Paper Trading for all strategies + SHADOW Flash-Loan execution + eventual LIMITED LIVE Flash-Loan execution using a funded Gas Wallet.

**Audit method:** Direct file inspection of both trees:

- Running codebase: `/app/backend`, `/app/frontend`
- Canonical bundle: extracted to `/tmp/cx/repo/app/{backend,frontend}` from `/app/arbicore-x-v1.0.2.bundle`

**Classification legend:**
`✅` production ready · `🟡` exists but needs refinement · `🟠` exists but dormant / not exposed · `🔴` missing (justification required)

**No code was modified. Read-only audit.**

---

## Executive summary (up-front)

The canonical repository contains **substantially more capability than is currently active in `/app/backend`**. In particular, the entire **`arbicore/scanners/*` discovery tree** (including a complete `FlashLoanArbitrageScanner`), the entire **`services/execution/*` runtime** (safety interlock, sizing, shadow engine, opportunity gate, wallet observer, ledger, fund tracker), the `services/vault.py` Fernet vault, and the `services/balances.py` polling service are **all present in the canonical bundle but not yet imported into `/app/backend`**. Waves 3–6E have built the *learning + execution substrate* — the *discovery + operator-facing runtime* is still dormant in the source-of-truth bundle awaiting activation.

**Bottom line:** for our production goal (SHADOW Flash-Loans + Paper Trading + Discovery LIVE), roughly **75 % of the required capability already exists in the canonical source and needs ACTIVATION**, ~20 % exists in `/app/backend` and needs **UI wiring only**, and only ~5 % is genuinely NEW code (all UI, no backend).

**Direct answer to the guiding question — can the platform already support connecting a funded Gas Wallet safely?** Yes, mechanically. The Wallet Registry (`/app/backend/arbicore/execution/wallet_registry.py`) and Secret Registry (`/app/backend/arbicore/secrets/`) accept registration and encrypted-at-rest storage today, and the Wave 6D `LiveSigner` gate ladder holds every strategy at SHADOW/PAPER by default. What is missing is the **operator-facing UI surface** — no v2 page currently posts to those endpoints.

---

## 1. Wallet & Treasury Audit

| Capability | Status | Canonical file(s) | Currently active in `/app/backend`? | UI exposed? | Notes / Action |
|---|---|---|---|---|---|
| **Wallet Registry** | ✅ Exists | `/app/backend/arbicore/execution/wallet_registry.py` (mirrored into running tree from Wave 6A) | Yes — server startup calls `_WALLET_REGISTRY.ensure_indexes()` | ❌ | Endpoints live at `/api/arbicore/execution/wallets`. Roles: `gas` / `treasury` / `watch_only`. **UI missing.** |
| **Vault Registry (exchange-key vault)** | 🟠 Dormant | `/tmp/cx/repo/app/backend/services/vault.py` (Fernet, `SUPPORTED_EXCHANGES = xt/mexc/gate/bitmart/coinstore`) | **Not imported** into `/app/backend` | ❌ | Sibling to Wave 6A `SecretRegistry` but for CEX API keys. **Activate as-is** if any CEX/paper strategy needs live public tickers with authenticated endpoints. |
| **Secret Registry (private-key handles)** | ✅ Exists | `/app/backend/arbicore/secrets/registry.py`, `backends.py` (Fernet backend, `resolve()` handle-only) | Yes | ❌ | Handles are opaque; plaintext never leaks. Ready for HSM/KMS backend swap. **UI missing.** |
| **Treasury (per-route P&L ledger)** | 🟠 Dormant | `/tmp/cx/repo/app/backend/api.py` line 352 `/treasury/{route_id}` — reads `db.treasury_col`, aggregates positions + transfers | **Not imported** — no `treasury_col` in running `services/db.py` | ❌ | Full canonical impl including funding, settlement, conversion path. **Activate + expose.** |
| **Capital Allocation** | ✅ Exists | `/app/backend/arbicore/execution/capital_policy.py` (Wave 6D) + canonical `/tmp/cx/repo/app/backend/arbicore/intelligence/capital.py::CapitalSizer` + `/tmp/cx/repo/app/backend/services/execution/sizing.py` | Wave 6D wired; canonical sizer dormant | ❌ | `CapitalPolicyRepo` seeds 7 per-strategy policies on startup. Endpoints live at `/api/arbicore/execution/capital-policy`. **UI missing.** |
| **Wallet Profiles** | ✅ Exists | `wallet_registry.py::WalletProfile` (role, chain, address, secret_handle_id, provenance, verification, audit) | Yes | ❌ | **UI missing.** |
| **Chain Support** | 🟡 Refine | Wave 6A supports ethereum/base/arbitrum/optimism/polygon by mode-ladder default. Canonical bundle adds BSC + BlockDAG (chain-id 1404). | Partial | ❌ | For flash-loan MVP: Base is the target chain; ethereum is optional. No new code — just seed extra chains via `WalletRegistryRepo.add()` when needed. |
| **Address Validation** | ✅ Exists | `wallet_registry.py` — `_validate_evm_address()` (0x + 40 hex, checksum-agnostic) | Yes | n/a | |
| **Balance Tracking (EVM native)** | 🟠 Dormant | `/tmp/cx/repo/app/backend/connectors/evm_wallet.py::EVMWatchConnector.get_balance()` — RPC failover, per-network config | **Not imported** | ❌ | 53 LOC, zero dependencies. **Copy + wire under `arbicore/execution/balances.py`** (or activate canonical connector). |
| **Balance Tracking (CEX)** | 🟠 Dormant | `/tmp/cx/repo/app/backend/services/balances.py::BalanceService` — 60 s polling, per-exchange status, 429 back-off, USD valuation, snapshot persistence | **Not imported** | ❌ | 223 LOC, production-grade. **Activate as-is** for the PAPER-mode balance surface. |
| **Gas Tracking** | 🟡 Refine | Wave 6C `StaticGasOracle` (running) + `RpcGasOracle` (opt-in, reads `eth_gasPrice`) | Yes | ❌ | For live production, set `ARBICORE_RPC_URL` in `backend/.env`. **UI missing.** |
| **Receiving Wallet** | 🟠 Dormant | `wallet_registry.py` supports arbitrary roles — set `execution_role="treasury"` and label it. Canonical bundle also has `observer_config.coinstore_bdag_deposit_address` pattern in `services/execution/wallet_observer.py`. | Registry active; treasury/receiver semantics not distinguished | ❌ | **No new code needed** — semantic layering only. Convention: `role=treasury, purpose=receive_profits`. |
| **Funding Wallet** | 🟠 Dormant | Same registry; convention `role=gas, purpose=funding`. Canonical `services/execution/fund_tracker.py` (505 LOC) computes funding + settlement events. | **fund_tracker not imported** | ❌ | Activate `fund_tracker` for LIMITED-LIVE reconciliation. |
| **Watch-only Wallet** | 🟠 Dormant | `wallet_registry.py::execution_role="watch_only"` + canonical `EVMWatchConnector` (53 LOC) + `services/execution/wallet_observer.py` (707 LOC) | Registry supports role; observer dormant | ❌ | The canonical wallet_observer is **complete**: RPC block-walking with cursor, failover, cycle auto-linking, Coinstore sell-stamp. **Activate.** |
| **Gas Wallet** | ✅ Exists | `wallet_registry.py` — `execution_role="gas"` is the only role that maps to a `secret_handle_id`. `LiveSigner` refuses any non-`gas` wallet during signing. | Yes | ❌ | **This is the exact role the operator will register for LIMITED-LIVE.** UI needed. |
| **Hot Wallet** | 🟠 Dormant | Same registry (semantic layering). Fernet-backed. Canonical bundle has no additional hot-wallet abstraction. | Registry active | ❌ | Add a `secret_backend` metadata field (`fernet` vs `hsm`) — 1-line refinement in Wave 6A registry if needed for LIMITED_LIVE. |
| **Cold Wallet** | 🔴 Missing (but justified deferral) | — | — | — | Cold-wallet integration = **out of MVP scope**. No hardware-wallet or air-gapped signer path needed for the SHADOW/LIMITED-LIVE goal. **Do not build.** |
| **Multisig** | 🔴 Missing (justified deferral) | — | — | — | Multi-sig (Safe / Squads) is a **treasury upgrade** post-MVP. Not needed for a single-operator Gas Wallet. **Do not build.** |
| **Wallet Health** | 🟡 Refine | Canonical `services/execution/safety_interlock.py::evaluate()` computes a READY/WAIT/BLOCKED health card. Wave 6D `KillSwitchRepo` covers global stop. Balance-service exposes per-exchange health. | Wave 6D wired; interlock dormant | ❌ | Compose these into a single `/api/arbicore/execution/wallets/{id}/health` — **refinement only**. |
| **Wallet Reconciliation** | 🟠 Dormant | `services/execution/wallet_observer.py::_record_event()` + `_match_candidates()` — auto-matches on-chain tx to cycle state with a ±2% amount tolerance. Full audit log in `observer_events`. | **Not imported** | ❌ | **Activate** during LIMITED_LIVE prep. Zero new code. |
| **Transaction History** | 🟠 Dormant | `services/execution/wallet_observer.py::list_events()` + `services/execution/ledger.py` (186 LOC) + canonical `api.py::/transfers` (line 514) | **Not imported** | ❌ | Two canonical surfaces (observer events + transfers). **Activate.** |
| **Profit Collection** | 🟠 Dormant | `services/execution/wallet_observer.py::stamp_coinstore_sell()` + canonical `api.py::/treasury/{route_id}` P&L rollup + `services/execution/fund_tracker.py` | **Not imported** | ❌ | The complete USDT → BDAG → USDT profit-collection state machine is already implemented (BDAG-specific but adaptable). **Activate.** |
| **Treasury Dashboard** | 🟠 Dormant (backend) / 🔴 Missing (frontend) | Canonical `api.py::/treasury/{route_id}` returns `{summary, funding, settlement, conversion, ledger}` per-route. No React page consumes it. | **Not imported** | ❌ | Backend activation + **new UI page** required. |

### Operator usage summary for existing wallet capabilities

**As of today, an operator can already:**

1. `POST /api/arbicore/execution/wallets` — register a Gas Wallet (`{name, chain, execution_role:"gas", address:"0x…", secret_handle_id:"<from-secret-registry>"}`).
2. `POST /api/arbicore/execution/secrets` (Wave 6A) — store the corresponding private key (or vault handle) encrypted-at-rest via Fernet; `resolve()` returns the material to the signer only. **Plaintext never leaks in any response.**
3. `GET /api/arbicore/execution/wallets` — list registered wallets.
4. `GET /api/arbicore/execution/wallets/{id}` — inspect a wallet (role, chain, address, provenance, verification, audit).
5. `GET /api/arbicore/execution/mode` — see the ladder is at SHADOW/PAPER for every strategy (deploy default).
6. `POST /api/arbicore/execution/plans/build` — build a flash-loan plan against the wallet (Wave 6B).
7. `POST /api/arbicore/execution/plans/{id}/simulate` — run gas + MEV + slippage + noop-simulator (Wave 6C).
8. `POST /api/arbicore/execution/plans/{id}/sign` — dry-run the gate ladder; SHADOW mode returns `receipt.signed=false, gate_ladder.mode=DENIED` (Wave 6D).
9. `POST /api/arbicore/execution/certification/run` — run the full 11-stage E2E audit (Wave 6E).
10. `POST /api/arbicore/execution/kill-switch/engage` / `disengage` — emergency global stop.

**All ten steps work today with curl.** No UI wires them up.

---

## 2. Flash-Loan Infrastructure Audit

| Capability | Status | Canonical file(s) | Notes |
|---|---|---|---|
| **Flash Loan Adapters** | ✅ Exists (dual) | Wave 6B `arbicore/execution/adapters.py` (Aave/Balancer/Uniswap flash) + canonical `arbicore/scanners/flash_loan_arbitrage/economics.py::FLASH_LOAN_PROVIDERS` | Wave 6B is the **execution-side** adapter set (deterministic, DAG-facing). Canonical bundle carries the **discovery-side** provider catalog with the same three providers. Same fee semantics (Aave 5 bps, Balancer 0 bps, Uniswap V3 pool-tier). |
| Aave | ✅ | `arbicore/execution/adapters.py::AaveV3FlashAdapter` (5 bps) + canonical `arbicore/scanners/flash_loan_arbitrage/sources.py::aave_v3_flashloan_real` |  |
| Balancer | ✅ | `arbicore/execution/adapters.py::BalancerV2FlashAdapter` (0 bps) + canonical source `balancer_v2_flashloan_real` |  |
| Uniswap V3 Flash | ✅ | `arbicore/execution/adapters.py::UniswapV3FlashAdapter` (pool-tier) + canonical source `uniswap_v3_flashloan_real` |  |
| **Provider Registry** | ✅ Exists | Wave 6B `AdapterRegistry` + canonical `arbicore/scanners/flash_loan_arbitrage/scanner.py::FlashLoanArbitrageScanner._source_registry` | Both registries are protocol-based and drop-in extensible. |
| **Execution Planner** | ✅ Exists | Wave 6B `arbicore/execution/planner.py::ExecutionPlanner.build()` | Deterministic; produces `ExecutionPlan` with sha256 `plan_hash`. |
| **Execution DAG** | ✅ Exists | Wave 6B `arbicore/execution/dag.py` — Borrow → Swap[+] → Repay → Profit with `validate_dag()` invariant | |
| **Transaction Builder** | 🟡 Refine | Wave 6B produces plans; **bytes-level calldata encoding is intentionally deferred to the LIMITED-LIVE enabling wave** (see Wave 6E report §7 item 1). No ABI-encoding today — that's the Wave 6D "calldata-encoding barrier". | For SHADOW / PAPER this is exactly right. For LIMITED-LIVE: add `eth-abi` and encode the six adapter call signatures. |
| **Flash Loan Repayment** | ✅ Exists | Wave 6B `planner.py::_build_repay_step()` — `min_break_even_wei = borrow + premium` computed in dry-run | Verified in `dry_run_economics` stage. |
| **Profit Calculator** | ✅ Exists | Wave 6B `DryRunEngine.evaluate()` computes `gross_profit_wei`, `net_profit_usd`, `profitable` boolean + canonical `arbicore/scanners/flash_loan_arbitrage/economics.py::FlashLoanEconomicsAssessor.assess()` (returns `FlashLoanEconomicsResult` with atomic_profit_usd + roi) | Two calculators exist — Wave 6B is the plan-time one; canonical is the discovery-time one. Both compatible. |
| **Fee Calculator** | ✅ Exists | Same modules. `provider_fee_bps()` respects Uniswap V3 pool-tier override. | |
| **Route Optimizer** | 🟠 Dormant | Canonical `arbicore/scanners/flash_loan_arbitrage/route_search.py::RouteSearchEngine` — bounded DFS (max_hops, wall-clock cap, TVL floor) | **Not imported** into `/app/backend`. **Activate** as part of the discovery-tree activation wave. |
| **Opportunity Execution** | 🟡 Refine (barrier held) | Wave 6B plan → Wave 6C simulate → Wave 6D gate ladder → **Wave 6D calldata-encoding barrier** | End-to-end wired except the final barrier. |
| **Execution Certification** | ✅ Exists | Wave 6E `arbicore/execution/certification.py::ExecutionCertifier` — 11-stage deterministic pipeline | |

### Complete execution pipeline (as-wired today)

```
Discovery         ── 🟠 dormant (canonical FlashLoanArbitrageScanner not imported)
    ↓
Opportunity emit  ── 🟠 dormant (canonical EmissionBus not imported)
    ↓
Plan build        ── ✅ Wave 6B  (POST /api/arbicore/execution/plans/build)
    ↓
Simulate          ── ✅ Wave 6C  (Noop | eth_call simulator)
    ↓
Gas estimate      ── ✅ Wave 6C  (static | rpc gas oracle)
    ↓
Slippage          ── ✅ Wave 6C  (deterministic band)
    ↓
MEV route         ── ✅ Wave 6C  (public_rpc | flashbots_protect)
    ↓
Capital policy    ── ✅ Wave 6D  (per-strategy min-of-4 binding)
    ↓
Kill switch       ── ✅ Wave 6D  (global emergency stop)
    ↓
Live signer       ── 🟡 Wave 6D  (gate ladder complete; bytes-level encoding deferred)
    ↓
Broadcast         ── 🔴 held at Wave 6D calldata-encoding barrier — by design
    ↓
Evidence          ── ✅ Wave 5   (Ed25519 signed bundles)
    ↓
Learning feedback ── ✅ Waves 3/4 (calibration + adaptive weights in OBSERVE)
```

---

## 3. End-to-End Execution Pipeline Audit

| Stage | Exists? | Active? | UI exposed? | Production-ready? | Refine? | Missing? |
|---|---|---|---|---|---|---|
| Discovery | ✅ Canonical | 🟠 Dormant | ❌ | Yes (after activation) | Import `arbicore/scanners/*` + `arbicore/emission_bus.py` + `arbicore/data/*` from bundle | No new code |
| Opportunity Scoring | ✅ Canonical | 🟠 Dormant | ❌ | Yes (after activation) | Part of same import — `arbicore/intelligence/roi_probability.py`, `arbicore/intelligence/validators/*` | No |
| Learning (real vs synthetic) | ✅ Canonical | 🟠 Dormant | ❌ | Yes | `arbicore/intelligence/roi_probability.py::ROIProbabilityEngine` | No |
| Calibration (Wave 3) | ✅ | ✅ | ❌ | Yes | — | UI missing |
| Adaptive Weights (Wave 4) | ✅ | ✅ (OBSERVE) | ❌ | Yes | — | UI missing |
| Planning (Wave 6B) | ✅ | ✅ | ❌ | Yes | — | UI missing |
| Simulation (Wave 6C) | ✅ | ✅ | ❌ | Yes | — | UI missing |
| Gas Estimation (Wave 6C) | ✅ | ✅ | ❌ | Yes | — | UI missing |
| MEV Routing (Wave 6C) | ✅ | ✅ | ❌ | Yes | — | UI missing |
| Slippage (Wave 6C) | ✅ | ✅ | ❌ | Yes | — | UI missing |
| Capital Policy (Wave 6D) | ✅ | ✅ | ❌ | Yes | — | UI missing |
| Kill Switch (Wave 6D) | ✅ | ✅ | ❌ | Yes | — | UI missing |
| Signing (Wave 6D) | ✅ (gate ladder only) | ✅ | ❌ | SHADOW ready; LIMITED-LIVE needs calldata encoding | Add ABI encoding | UI missing |
| Execution / Broadcast | 🔴 held by design | — | — | — | — | Deliberate — Wave 6D barrier |
| Evidence (Wave 5) | ✅ | ✅ | ❌ | Yes | — | UI missing |
| Learning Feedback | ✅ | ✅ | ❌ | Yes | — | UI missing |
| Certification (Wave 6E) | ✅ | ✅ | ❌ | Yes | — | UI missing |

---

## 4. Wallet Integration Audit — the operator flow

- **Where is a wallet registered?** — `POST /api/arbicore/execution/wallets` (backend ✅, UI ❌).
- **Where is the gas wallet configured?** — Same endpoint with `execution_role="gas"` + `secret_handle_id` (backend ✅, UI ❌).
- **Where is signing enabled?** — Signing is **held at the Wave-6D barrier by design**. Enabling flow: (a) promote strategy mode with `POST /api/arbicore/execution/mode/{strategy}` from PAPER → LIMITED_LIVE (auditable, single-step forward transition only); (b) implement bytes-level calldata encoding (LIMITED-LIVE enabling task).
- **Where are balances displayed?** — Backend: canonical `services/balances.py` (CEX, dormant) + canonical `connectors/evm_wallet.py::get_balance` (native, dormant). **UI: nowhere yet.**
- **Where is gas balance displayed?** — Same as above. Nowhere today.
- **How are secrets stored?** — Wave 6A `SecretRegistry` with `FernetSecretBackend` (AES-128-CBC + HMAC-SHA256 via `cryptography.fernet.Fernet`). Handle-based access; plaintext is `resolve()`-only, never surfaced.
- **How is Secret Registry connected?** — Wallet Registry stores a `secret_handle_id` per Gas Wallet. `LiveSigner._resolve_secret()` calls `SecretRegistry.resolve(handle_id)`; a resolved-length proof reaches the gate ladder — never the plaintext.
- **How does signing occur?** — 4-gate ladder in `LiveSigner.sign_plan()`: kill_switch → mode → capital → secret_resolution. Wave 6D holds at calldata-encoding even when all four PASS.
- **How is broadcasting enabled?** — Only when a strategy is in `LIMITED_LIVE` (single-step, gated) AND the LIMITED-LIVE enabling tasks (Wave 6E report §7) are complete.
- **Which execution mode controls broadcasting?** — `ExecutionMode` ladder: `OBSERVE → PAPER → SHADOW → LIMITED_LIVE → FULL_LIVE`. `is_broadcast_allowed(mode)` returns True only for the last two.
- **Which configuration screens already exist?** — Legacy pages (`Settings.jsx`, `Execution.jsx`, `OperatorConsole.jsx`, etc.) predate Wave 6. **No page currently talks to any `/api/arbicore/execution/*` endpoint.**
- **Which configuration screens are missing?** — All of them: Wallet Registration, Secret Registration, Mode Ladder, Capital Policy, Kill Switch, Certification, Plans, Evidence. (Scoped in the UI-v2 roadmap.)

---

## 5. Operator Workflow Audit — MVP end-to-end

| Step | Existing backend | Existing UI | Existing APIs | Existing docs | Missing backend | Missing UI | Refinements |
|---|---|---|---|---|---|---|---|
| 1. Create Wallet (external — e.g. MetaMask) | n/a | n/a | n/a | n/a | n/a | n/a | Operator action outside the app |
| 2. Fund Gas Wallet | n/a | n/a | n/a | n/a | n/a | n/a | Operator action outside the app |
| 3. Register Wallet | ✅ | ❌ | `POST /api/arbicore/execution/wallets` | Wave 6A verification report | — | Wallet Registry page | — |
| 4. Configure Secret Registry | ✅ | ❌ | `POST /api/arbicore/execution/secrets` | Wave 6A verification report | — | Secret Registry page (write-only form; never displays plaintext) | For LIMITED-LIVE: register HSM/KMS backend via `SecretRegistry.register_backend()` |
| 5. Enable SHADOW | ✅ (default) | ❌ | `GET /api/arbicore/execution/mode` — default already SHADOW for flash_loan_arbitrage | Wave 6A | — | Mode ladder page | — |
| 6. Continuous Discovery | 🟠 Dormant in canonical bundle | ❌ | Not yet mounted | Canonical `arbicore/scanners/*` | Activate `arbicore/{emission_bus, data, intel, intelligence, models, scanner, scanners}` from bundle. NO new code. | Discovery + Opportunities pages | — |
| 7. Simulation | ✅ | ❌ | `POST /api/arbicore/execution/plans/build` + `.../plans/{id}/simulate` | Waves 6B + 6C | — | Plan detail page with Simulate button | — |
| 8. Validation | ✅ | ❌ | `POST /api/arbicore/execution/certification/run` | Wave 6E | — | Certification page (11-stage timeline) | — |
| 9. Promote to LIMITED_LIVE | ✅ (endpoint) | ❌ | `POST /api/arbicore/execution/mode/{strategy}` — single-step forward transition, audited | Wave 6A | Add pre-flight interlock check | Mode-promotion modal with pre-flight checklist | Wire safety_interlock output |
| 10. Execute first flash loan | 🟡 Held at Wave 6D barrier by design | ❌ | (barrier) | Wave 6E §7 | ABI-encode 6 adapter signatures; deploy + verify executor contract | Live plan execution page | Add `eth-abi` |
| 11. Monitor | 🟠 Backend dormant (wallet_observer, ledger, fund_tracker) | ❌ | Once activated | Canonical | Activate observer + ledger + fund_tracker | Observability dashboard | — |
| 12. Withdraw Profits | 🟠 Dormant | ❌ | Once activated: `POST /api/observer/coinstore-sell`, `GET /api/treasury/{route_id}` | Canonical `api.py` + `wallet_observer.py` | Activate treasury endpoint set | Treasury / Profit Collection page | — |

---

## 6. Operator Guide Readiness

The complete Flash-Loan Operator Manual **cannot yet be written end-to-end** — but the *SHADOW-only Operator Manual* can be, today. Every backend surface needed for SHADOW execution + Paper Trading is live.

**Proposed manual — SHADOW edition (writable today)**

```
1.  Introduction & safety posture (SHADOW invariant, kill switch)
2.  System overview (Discovery → Planning → Simulation → Evidence)
3.  First-time setup
     3.1  Create a burner Gas Wallet in MetaMask (external)
     3.2  Register the wallet via /api/arbicore/execution/wallets
     3.3  Store the private key via /api/arbicore/execution/secrets
     3.4  Confirm mode ladder is SHADOW for flash_loan_arbitrage
4.  Continuous Discovery (activated canonical scanners)
5.  Building & simulating a plan
6.  Reading a certification report
7.  Kill-switch drill
8.  Evidence bundles & audit trail
9.  Roll-back / rollback playbook
```

**Proposed manual — LIMITED-LIVE edition (needs the enabling tasks first)**

```
… everything above, plus:
10. Bytes-level calldata encoding & executor contract deployment
11. HSM/KMS backend registration
12. RPC & MEV relay configuration
13. Promoting a strategy from PAPER → LIMITED_LIVE (single-step, audited)
14. First live execution — the 14-day validation window
15. Withdrawing profits (canonical treasury endpoint)
16. Incident response & the kill-switch audit
```

The LIMITED-LIVE edition is blocked on the 5 enabling tasks in Wave 6E report §7 — not on missing documentation surface.

---

## 7. Gap Analysis Table

| Capability | Exists | Refine | Activate | Build New | Canonical file reference |
|---|:-:|:-:|:-:|:-:|---|
| Wallet Registry | ✅ | | | | `/app/backend/arbicore/execution/wallet_registry.py` |
| Vault Registry (CEX) | | | ✅ | | `/tmp/cx/repo/app/backend/services/vault.py` |
| Secret Registry (EVM) | ✅ | | | | `/app/backend/arbicore/secrets/registry.py`, `backends.py` |
| Treasury ledger | | | ✅ | | `/tmp/cx/repo/app/backend/api.py:352` + `services/db.py:24 (treasury_col)` |
| Capital Allocation (execution) | ✅ | | | | `/app/backend/arbicore/execution/capital_policy.py` |
| Capital Sizer (discovery) | | | ✅ | | `/tmp/cx/repo/app/backend/arbicore/intelligence/capital.py`, `services/execution/sizing.py` |
| Wallet Profiles | ✅ | | | | `/app/backend/arbicore/execution/wallet_registry.py::WalletProfile` |
| Address Validation | ✅ | | | | `/app/backend/arbicore/execution/wallet_registry.py::_validate_evm_address` |
| Balance Tracking — EVM native | | | ✅ | | `/tmp/cx/repo/app/backend/connectors/evm_wallet.py::EVMWatchConnector` |
| Balance Tracking — CEX | | | ✅ | | `/tmp/cx/repo/app/backend/services/balances.py::BalanceService` |
| Gas Oracle | ✅ | 🟡 | | | `/app/backend/arbicore/execution/gas.py` (RpcGasOracle needs `ARBICORE_RPC_URL`) |
| Receiving Wallet | ✅ | | | | Registry (semantic) |
| Funding Wallet | ✅ | | | | Registry (semantic) |
| Watch-only Wallet | ✅ | | ✅ | | Registry + `/tmp/cx/repo/app/backend/services/execution/wallet_observer.py` |
| Gas Wallet | ✅ | | | | Registry + Secret Registry |
| Hot Wallet | ✅ | | | | Registry (semantic) |
| Cold Wallet | | | | 🔴 (deferred — out of MVP) | — |
| Multisig | | | | 🔴 (deferred — out of MVP) | — |
| Wallet Health | | 🟡 | ✅ | | `/tmp/cx/repo/app/backend/services/execution/safety_interlock.py` |
| Wallet Reconciliation | | | ✅ | | `/tmp/cx/repo/app/backend/services/execution/wallet_observer.py` |
| Transaction History | | | ✅ | | `wallet_observer.py::list_events`, `services/execution/ledger.py`, canonical `api.py::/transfers` |
| Profit Collection | | | ✅ | | `wallet_observer.py::stamp_coinstore_sell` + `services/execution/fund_tracker.py` |
| Treasury Dashboard | | | ✅ | 🟡 (UI) | Backend canonical `api.py::/treasury/{route_id}`. Frontend page missing. |
| Flash-loan Adapters (execution) | ✅ | | | | `/app/backend/arbicore/execution/adapters.py` |
| Flash-loan Adapters (discovery) | | | ✅ | | `/tmp/cx/repo/app/backend/arbicore/scanners/flash_loan_arbitrage/*` |
| Flash-Loan Scanner | | | ✅ | | `arbicore/scanners/flash_loan_arbitrage/scanner.py::FlashLoanArbitrageScanner` |
| Route Optimizer | | | ✅ | | `arbicore/scanners/flash_loan_arbitrage/route_search.py::RouteSearchEngine` |
| Emission Bus | | | ✅ | | `/tmp/cx/repo/app/backend/arbicore/emission_bus.py` |
| Discovery Queue | | | ✅ | | `/tmp/cx/repo/app/backend/arbicore/data/discovery_queue.py` |
| Opportunity Verifier | | | ✅ | | `arbicore/scanners/opportunity_verifier.py` |
| Opportunity Gate | | | ✅ | | `/tmp/cx/repo/app/backend/services/execution/opportunity_gate.py` |
| ROI Probability | | | ✅ | | `arbicore/intelligence/roi_probability.py` |
| MEV Risk Classifier | | | ✅ | | `arbicore/intelligence/validators/mev_risk.py` |
| Slippage Validator | ✅ | | ✅ | | `/app/backend/arbicore/execution/slippage.py` (execution mirror) + canonical `arbicore/intelligence/validators/slippage.py` |
| Planning | ✅ | | | | `/app/backend/arbicore/execution/planner.py` |
| DAG | ✅ | | | | `/app/backend/arbicore/execution/dag.py` |
| Bytes-level Calldata Encoding | | | | 🔴 (LIMITED_LIVE only) | Wave 6E §7 item 1 |
| Executor Contract | | | | 🔴 (LIMITED_LIVE only) | Wave 6E §7 item 2 |
| Simulation | ✅ | | | | `/app/backend/arbicore/execution/simulation.py` |
| MEV Router | ✅ | | | | `/app/backend/arbicore/execution/mev.py` |
| Capital Policy | ✅ | | | | `/app/backend/arbicore/execution/capital_policy.py` |
| Kill Switch | ✅ | | | | `/app/backend/arbicore/execution/kill_switch.py` |
| Live Signer (gate ladder) | ✅ | 🟡 for LIMITED_LIVE | | | `/app/backend/arbicore/execution/live_signer.py` |
| Signing (bytes) | | | | 🔴 (LIMITED_LIVE only) | Wave 6E §7 item 1 |
| Certification | ✅ | | | | `/app/backend/arbicore/execution/certification.py` |
| Evidence Bundles | ✅ | | | | `/app/backend/arbicore/evidence/signer.py` |
| Calibration | ✅ | | | | `/app/backend/arbicore/learning/concrete/calibrator_isotonic.py` |
| Adaptive Weights | ✅ | | | | `/app/backend/arbicore/learning/concrete/adaptive_weights_observer.py` |
| Wallet Registry UI | | | | 🟡 (UI only) | — |
| Secret Registry UI | | | | 🟡 (UI only) | — |
| Mode Ladder UI | | | | 🟡 (UI only) | — |
| Capital Policy UI | | | | 🟡 (UI only) | — |
| Kill Switch UI | | | | 🟡 (UI only) | — |
| Certification UI | | | | 🟡 (UI only) | — |
| Discovery / Opportunities UI | | | | 🟡 (UI only) | — |
| Treasury / Profit UI | | | | 🟡 (UI only) | — |
| Operator Manual (SHADOW edition) | | | | 🟡 (docs only) | — |
| Operator Manual (LIMITED-LIVE edition) | | | | 🟡 (docs after §7 tasks) | — |

**Legend:** ✅ = capability present · 🟡 = present but needs refinement / new UI · 🔴 = truly new build.

---

## 8. Final Recommendation

### 1. Can ArbiCore X already support the complete operator workflow for SHADOW flash-loan execution?

**Yes — mechanically via API today. UI-facing, no.** Every backend surface for the SHADOW workflow is in place. What is missing is a UI that consumes them and (optionally) the activation of the canonical discovery tree so opportunities appear automatically instead of being posted by hand.

### 2. What is still missing before LIMITED_LIVE?

Five enabling tasks (all documented in Wave 6E report §7):

1. Bytes-level calldata encoding for the six adapter call signatures (add `eth-abi` or `web3-py`)
2. Executor contract deployment + verification on Base mainnet
3. HSM/KMS backend registered with `SecretRegistry.register_backend()`
4. `ARBICORE_RPC_URL` set to a Base mainnet endpoint + `ARBICORE_SIMULATOR=eth_call`
5. MEV relay registration (public routing on Base; MEV-Blocker/Flashbots-Protect on Ethereum)

### 3. What is still missing before FULL_LIVE?

All of §7 above, plus:

- A 14-day LIMITED_LIVE validation window with clean evidence + certifier verdicts
- Formal executor-contract audit
- Multi-signer plan (per-signer daily notional caps)
- Post-mortem review of LIMITED_LIVE incidents (if any)

### 4. Which remaining work is UI only?

- Wallet Registry / Secret Registry / Mode / Capital Policy / Kill Switch / Certification pages
- Discovery + Opportunities pages (once §5 backend activation is done)
- Treasury / Profit Collection dashboard
- The Slice 1–6 UI-v2 roadmap already scopes these.

### 5. Which remaining work is backend only?

- **Activate** (import + wire, NO new code): `arbicore/{emission_bus, data, intel, intelligence, models, scanner, scanners, shadow}` from the canonical bundle + `services/execution/{wallet_observer, safety_interlock, sizing, opportunity_gate, ledger, fund_tracker, ...}` + `services/{balances, vault}` + `connectors/evm_wallet.py`.
- **Refine** (small, targeted): compose canonical `safety_interlock.evaluate()` into a per-wallet health card.
- **New** (deferred to LIMITED_LIVE enabling wave): calldata encoding, executor contract deploy, HSM backend adapter.

### 6. Which remaining work is operational documentation only?

- SHADOW-edition Operator Manual (writable today)
- LIMITED-LIVE-edition Operator Manual (after §7 tasks)
- Runbook: kill-switch drill, mode-ladder promotion, secret rotation, incident response

### 7. Can the existing codebase already support connecting a dedicated Gas Wallet (MetaMask or compatible) safely through the Wallet Registry and Secret Registry?

**Yes — safely, today, via API.** The Wallet Registry (`arbicore/execution/wallet_registry.py`) accepts an EVM address with role `gas`; the Secret Registry (`arbicore/secrets/registry.py` + `backends.py`) stores the corresponding private key encrypted-at-rest via Fernet (AES-128-CBC + HMAC-SHA256). The two are bound by a `secret_handle_id` on the wallet document. The Wave 6D `LiveSigner` gate ladder holds every strategy at SHADOW/PAPER at deployment time — even if the operator registers a fully-funded Gas Wallet, no transaction can be broadcast until (a) the strategy is explicitly promoted to `LIMITED_LIVE` in an audited single-step transition, and (b) the calldata-encoding barrier is lifted.

There is no UI surface for this today; the mechanically-safe path is via curl (or, equivalently, a UI page against the same endpoints).

### 8. What exact steps will the operator perform inside ArbiCore X before the first flash-loan execution?

Once the SHADOW-edition UI is delivered (Slices 1–4 of UI-v2 + Wallet page), the *entire* pre-execution sequence inside ArbiCore X is:

1. **Wallets → New** — enter address, chain=`base`, role=`gas`. Save.
2. **Secrets → New** — paste private key (write-only field). Bind to the wallet by `secret_handle_id`. Save. (Plaintext never leaves the backend.)
3. **Mode Ladder** — confirm `flash_loan_arbitrage` is `SHADOW` (the deploy default).
4. **Discovery** — verify continuous scanner emissions are flowing (post-activation).
5. **Opportunities** — pick one; click **Build Plan**.
6. **Plan Detail** — click **Simulate**. Inspect the 11-stage certification.
7. **Kill Switch** — click **Engage** and **Disengage** as a drill. Confirm audit log.
8. **Evidence** — verify the last plan produced a signed evidence bundle.
9. (LIMITED_LIVE only, after enabling tasks in §7) **Mode Ladder → flash_loan_arbitrage → Promote to LIMITED_LIVE**. Confirm the pre-flight checklist. Submit.
10. **Plan Detail → Broadcast** — the only step that ever sends bytes to the chain, gated by all four Wave-6D gates + the mode ladder.

Steps 1–8 are all SHADOW-safe and cause zero fund movement. Step 9 is a single, audited state transition. Step 10 is the first — and only — moment funds move.

---

## Recommendation to the engineering lead

**Do not rebuild anything.** The two waves of remaining work — before we can ship a complete SHADOW MVP — are, in this order:

1. **Wave 7A · Canonical Discovery Activation** (backend, ~1 day). Import the dormant canonical modules (`arbicore/emission_bus.py`, `arbicore/{data,intel,intelligence,models,scanner,scanners,shadow}`, `services/execution/{wallet_observer,safety_interlock,sizing,opportunity_gate,ledger,fund_tracker,shadow}`, `services/{balances,vault}`, `connectors/evm_wallet.py`) into `/app/backend/`. Add minimal `server.py` wiring. No new code. This lights up Continuous Discovery, Paper Trading, Wallet Reconciliation, Treasury ledger, and Profit Collection **immediately** — every one of these features already exists in the canonical bundle.

2. **Wave 7B · UI Activation (Slices 1–4)** (frontend, ~3–5 days). Build the v2 pages that already have selectors filed (`docs/ui_v2/*`) against the endpoints that are already live: Home / Wallets / Secrets / Mode / Capital / Kill Switch / Simulation / Certification / Discovery / Opportunities / Treasury.

Only **after** Wave 7A + 7B (and the 14-day SHADOW validation window from Wave 6E report §5.5) should the LIMITED_LIVE enabling tasks (§7) be scheduled.

**No code was modified during this audit. All findings are file-verified.**
