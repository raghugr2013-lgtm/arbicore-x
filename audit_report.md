# ArbiCore X v2 — Independent Two-Phase Audit

**Audit date:** 2026-09-08 UTC  
**Audited commit:** `2e6f253dd354248e0ad861b2011bdfbcef63eb97`  
**Audited Git tree:** `ddfd9b3669e8254146a62d7b8fc37e60717af366`  
**Requested branch:** `astra-audit-limited-live-5f8475a`  
**Verified reference:** `origin/astra-audit-limited-live-5f8475a` resolves to the audited commit.  
**Method:** independent, static, read-only source and evidence review.  
**Verdict:** **NOT PRODUCTION-READY. Six-chain profitable execution is not established.**

## Scope, provenance, and limitations

The assignment is a two-phase independent audit: Phase A establishes the actual application state; Phase B recommends P0/P1/P2/P3 engineering toward broad activation on **Base, Ethereum, Arbitrum, Optimism, Polygon, and BNB Chain**. No chain is removed from the assessment or roadmap.

The workspace checkout was **not** the requested version: it was on `takeover/limited-live-seam-cc8db95`, HEAD `5f8475a73d67d5c0580da79e81fc9b5e42465f7d`, with pre-existing working-tree edits. The target commit was already available locally. Source evidence was therefore read from Git objects at the requested commit, rather than from the checkout. **No checkout, fetch, reset, commit, merge, or PR was performed.** All source line references below refer to the target commit, not HEAD.

No application processes, imports, tests, RPC probes, API requests, database queries, fork simulations, signer operations, or transactions were run for this audit. Static analysis included source inspection and separate functional and security reviews; the functional review reported a Python static lint scan with unused-import/local findings, but JavaScript lint was unavailable due to a linter-engine error. Neither is runtime verification. Existing reports were inspected as historical artifacts, not independently reproduced evidence.

No source, configuration, or secret changes were made. Deliverables are this report and an administrative audit entry in the handoff memory. Actual environment values, private keys, credentials, operator permissions, wallet funding, current markets, deployed bytecode, and production access controls were not inspected or attested.

Coverage includes every major subsystem and the principal discovery-to-execution flows. It is **not** a formal proof of every function, a complete smart-contract security certification, or a claim that all defects have been found. Broad legacy CEX/operator workflows and frontend behavior received sampled static coverage, not browser or execution testing.

---

# Phase A — Current-State Audit

## 1. Executive summary

ArbiCore X v2 contains substantial arbitrage research infrastructure: six scanner families, chain/token/venue registries, genuine RPC-backed quote adapters, pool resolvers, economic models, Mongo evidence stores, operator dashboards, an owner-gated flash receiver, and a real guarded broadcast implementation. It is **not merely a mock application**.

However, the presence of these components does not constitute a connected, profitable, six-chain trading system:

1. **Three High security findings expose operator controls without authentication.** Anonymous application-level requests can change network/executor configuration, strategy execution modes, and other operational state. Direct broadcast still requires an authenticated operator and additional gates; this is not a finding of anonymous immediate fund transfer.
2. **A deterministic function-signature mismatch breaks atomic simulation and wallet ERC-20 reads.** `_throttle(scope)` is called without an argument from two consumers.
3. **Canonical flash profitability reuses probe-sized quotes at a different dollar notional.** Its dollar profit estimate and final revalidation are not reliably tied to the exact trade amount.
4. **RPC isolation is incomplete.** The quoter can prefer a global Base endpoint for another chain even though the persistent resolver was hardened against this.
5. **Non-Base canonical flash connectivity is incomplete.** Fork/Algebra/V2 venues have standalone adapters but are rejected by the canonical generic quote planner; its TVL provider remains Base-bound. BNB is explicitly excluded from the canonical flash source and from relevant execution-adapter chain lists.
6. **Receiver support is narrower than the discovery surface.** Source implements Balancer V2 **and Aave V3** borrowing, but swaps use one immutable Uniswap V3 router. Other venues require a new/versioned receiver. Only Base mainnet and Base Sepolia deployments are recorded; five requested mainnets have no deployment record. A recorded deployment is not an independently verified deployment.
7. **The multichain certification path cannot currently prove the promised end state.** It supplies no provider-liquidity inputs to a mandatory liquidity-gated optimizer and does not execute its candidate simulation stage. Historical negative candidates do not exercise these missing positive-path dependencies.

**Finding totals:** 0 confirmed Critical; **10 High** (including capability/activation blockers, not all exploitable defects); 6 Medium observation groups. Severity and engineering priority are separate: a High six-chain capability gap may be P1, whereas a High integrity/security defect is P0.

**Readiness conclusion:** 0/6 requested mainnets are demonstrated by this audit to have fresh, exact-size, economically valid, fully simulated, authorized profitable execution. This means **not proven**, not “arbitrage never exists” or “no transaction has ever occurred.”

## 2. What the application actually contains

| Subsystem | Factual source state | Boundary / evidence |
|---|---|---|
| Backend and persistence | FastAPI composition; Motor/Mongo repositories for configuration, opportunities, evidence, journals, outcomes, modes and capital | `app/backend/server.py`; `app/backend/services/db.py:10-11`. Database availability, indexes and stored production state were not checked. |
| Frontend / operator experience | React legacy views plus v2 Control Center, Live Ops, discovery, opportunities, capital, settings, flash operator, wizard and post-trade views | `app/frontend/src/v2/lib/nav.js:27-123`; `app/frontend/src/v2/pages/FlashLoanOperatorPage.jsx:711-720`; controls and labels are not execution proof. |
| Authentication / vault | Cookie JWT auth, bcrypt, session-version revocation, lockout; vault/secrets abstractions; selected endpoints require operator roles | `app/backend/services/auth.py:48-69`, `app/backend/services/auth.py:85-163`; missing authorization elsewhere is H01-H03. Actual secrets were not read. |
| Canonical discovery | Six scanner families emit verifier-built canonical opportunities through an emission bus; discovery candidates are separate from verified opportunities | `app/backend/arbicore/runtime/composition.py:851-1056`, `app/backend/arbicore/runtime/composition.py:1192-1406`. Default and startup wiring differ by scanner. |
| Base discovery / search | Canonical pool registry, runtime UniV3 liquidity exclusion, Aerodrome resolution, graph/cycle search; separate continuous Base opportunity engine | `app/backend/arbicore/runtime/composition.py:1067-1190`, `app/backend/arbicore/runtime/composition.py:1239-1272`; missing/zero liquidity is excluded. |
| Multichain discovery | UniV3-family, V2 and Algebra resolvers; token/factory registries; bounded parallel discovery and a six-chain opportunity race | `app/backend/arbicore/discovery/opportunity_engine.py:72-130`; race delegates non-Base evaluation to the certification harness, inheriting H09. |
| Quotes | Eight registered quote backends: UniV3, Aerodrome classic/Slipstream, Sushi V2/V3, Pancake V3, Camelot, QuickSwap | `app/backend/arbicore/execution/quoter.py:873-881`; direct backend presence exceeds canonical connectivity (H07). Strict/complete quote checks are present. |
| Economics / sizing | Quote-inclusive fee accounting, flash fees, chain gas models, size search, provider optimizer, profit/TVL/MEV gates | H05, H09 and M03-M04 prevent treating all outputs as exact executable net profit. |
| Planning / settlement | Adapter registry, DAG/plan construction, executor-relayed calldata for Balancer/Aave, eight-cell settlement classifier | `app/backend/arbicore/execution/calldata.py:532-632`; `app/backend/arbicore/execution/settlement_dispatcher.py:165-278`; route descriptions are not necessarily fully provisioned transactions. |
| Simulation | Symbolic/no-op, heuristic paper, RPC simulation, exact atomic call and Anvil scaffolding coexist | H04 and M01. Backend/method/overrides must accompany every result; an `ok` boolean alone is inadequate. |
| Execution / safety | Real `LimitedLiveBroadcaster`; kill switch, mode, capital, secret, slippage, preflight, confirmation and revalidation checks | `app/backend/arbicore/execution/broadcast.py:422-778`. It really can sign/send if gates pass; it must not be described as categorically incapable of broadcasting. |
| Automation | Background opportunity pipeline/executor exists; server does not opt into `auto_confirm=True` | `app/backend/server.py:447-480`; `app/backend/arbicore/execution/pipeline.py:118-131`. Autonomous detection/evaluation is not autonomous live trading. |
| Evidence / learning | Mongo bundles and audit attribution; provenance partitioning; state-observer outcome learning, calibration and confidence workers | `app/backend/arbicore/data/mongo/evidence_bundles_repo.py:19-45`; `app/backend/arbicore/certification/engine.py:66-82`; `app/backend/arbicore/learning/concrete/outcome_tracker.py:75-81`. Market-outcome learning is not reconciled realized trading P&L. |
| Legacy CEX / BlockDAG operations | Read-only private balance fetchers, manual opportunity and operator workflow/reporting modules | `app/backend/services/exchange_private.py:1-14`; `app/backend/services/execution/manual_engine.py:1-66`. Not proof of an integrated automated CEX trading or withdrawal path. Legacy breadth was sampled. |
| Packaging / operations | Docker, compose, nginx, monitoring/runbooks, build provenance and packaged deployment registry | `deployment/docker/backend/Dockerfile:75-105`. HTTP health/compilation/image identity do not prove RPC, markets, database provenance or execution readiness. No deployment was checked or changed. |

### Strategy assessment — preserve the full scope

| Strategy family | Existing implementation | What is not established |
|---|---|---|
| CEX arbitrage | Discovery sources, CoinGecko hints, order-book verifier and canonical scanner | Automated order placement, inventory/rebalance, settlement and profitable execution across venues |
| Funding arbitrage | Funding sources, economics, verification, scanner | Live hedge execution, borrowing/funding liabilities, liquidation management and realized carry |
| DEX arbitrage | Quote cache, quoter/verifier, multi-hop/cross-venue route search | Broad venue execution through the receiver; coherent exact-size net and state proof |
| Flash-loan arbitrage | Canonical scanner, evidence, two receiver flash heads, quote and safety components | Connected six-chain/provider/venue end-to-end operation; H04-H10 |
| Cross-chain arbitrage | LI.FI/Stargate transfer quote implementations and liveness loader are attached during startup | Bridge initiation/finality/recovery and a capitalized multi-transaction strategy. Ordinary asynchronous bridging cannot repay a same-transaction flash loan across chains. |
| Launch arbitrage | Launch sources, entity/wallet intelligence and optional Helius venue provider | Helius-oriented coverage is not six-EVM-chain launch execution. Per-chain launch venue/strategy certification remains necessary. |

Startup context matters: `app/backend/arbicore/runtime/composition.py:1816-1843` attaches bridge providers/liveness; `app/backend/arbicore/runtime/composition.py:1768-1773` attaches Helius in its conditional startup path. Factory-level `None` providers alone would incorrectly imply those integrations never attach. Conversely, source registration does not mean a scanner is enabled or a venue is reachable.

## 3. Certification vocabulary

These states must remain distinct and candidate-specific:

1. **DISCOVERY IMPLEMENTED:** resolver/search code exists for this chain, venue and strategy.
2. **CONFIGURED:** actual operator inputs exist; this audit did not inspect them.
3. **RPC VERIFIED:** a permitted endpoint reports the expected chain and a fresh, trustworthy block.
4. **LIQUIDITY VERIFIED:** both executable DEX depth and borrow-provider availability cover the exact amount at the relevant state.
5. **QUOTABLE:** every ordered hop has a valid quote for that amount, chain, venue and block context.
6. **ECONOMICALLY VALID:** exact route output minus actual premium, gas, L1/data costs and explicit risk allowance meets policy.
7. **ROUTE CONSTRUCTABLE:** exact calldata targets verified deployment(s) and matches the quoted route.
8. **SIMULATABLE / SIMULATED:** infrastructure capability is distinct from a completed exact-transaction simulation with the intended caller and state.
9. **EXECUTION CAPABLE:** provider, receiver version, router ABI, caller, wallet and chain are compatible; not permission to trade.
10. **RUNTIME CERTIFIED:** all evidence is coherently bound, persisted/read back, fresh and replayable.
11. **LIMITED-LIVE ELIGIBLE:** candidate certification plus operator approval, mode, kill switch, capital and final revalidation.
12. **EXECUTION PROVEN:** an authorized submitted transaction has a receipt, finality, repayment and reconciled realized net outcome. Not attempted here.

Code-level flags do not advance later states. A pool balance is not active concentrated-liquidity depth; an RPC URL is not a verified RPC; a quoter is not a swap executor; a gas-wallet balance is not flash capacity; an Anvil process is not a simulated route.

## 4. Six-chain capability matrix

**Legend:** “adapter exists” and “resolver exists” are static capabilities, not current successes. **U** means actual configuration/runtime state unverified by this audit. **Blocked** denotes a concrete source/recorded-capability blocker, not a failed live experiment.

| Chain | Discovery and standalone quote surface | Config / RPC | Canonical liquidity and economics | Route / receiver / deployment | Simulation and activation |
|---|---|---|---|---|---|
| **Base — 8453** | UniV3 plus Aerodrome classic/Slipstream; canonical liquidity filter and real quote paths exist | U; discovery and economic RPC contracts differ | Base TVL/price path exists; final M3 borrowing is Balancer-only; exact-size quote mismatch H05 | Receiver source: UniV3 swaps, Balancer/Aave heads. Base deployment recorded, not independently verified. Aerodrome is not receiver-compatible | Atomic path broken by H04. No profitable runtime-certified or limited-live execution established |
| **Ethereum — 1** | UniV3 and Sushi V2 resolvers/quoters; Curve resolver absent | U; quoter global-RPC leakage H06 | Canonical generic path permits only UniV3; Base-bound TVL; race/harness provider-liquidity input missing | Plan adapter classes exist, but Base-only common address book and no chain deployment record. Sushi/Curve outside current receiver schema | Generic/paper scaffolding is not exact proof; no registered execution deployment; activation blocked |
| **Arbitrum — 42161** | UniV3, Sushi V3 and Camelot Algebra standalone resolvers/quoters | U; H06 | Canonical forks/Algebra rejected, TVL not chain-composed; L1-cost model exists but no certified positive route | Fork/Algebra plan adapters need provisioned routers and a new receiver; no chain deployment record | No coherent exact-candidate simulation/certification; activation blocked |
| **Optimism — 10** | UniV3 exists; Velodrome V2 resolver/quoter absent | U; H06 | Canonical TVL not chain-composed; OP-stack gas model exists; harness cannot complete provider gate | UniV3 adapter class exists; common targets not provisioned by that address book; no chain deployment record | No coherent exact-candidate simulation/certification; activation blocked |
| **Polygon — 137** | UniV3 and QuickSwap Algebra standalone resolvers/quoters | U; H06 | QuickSwap rejected by canonical planner; TVL not chain-composed; native-POL gas model exists | QuickSwap plan adapter exists but receiver incompatible; no chain deployment record | No coherent exact-candidate simulation/certification; activation blocked |
| **BNB Chain — 56** | UniV3 and Pancake V3 resolvers/quoters exist in standalone tools | U; H06 | **Explicitly excluded from canonical flash discovery**. Aave catalog/liquidity reader includes BNB, but its execution adapter does not | UniV3 swap adapter also excludes BNB. Pancake adapter exists with configured router requirement; no deployment record; no Balancer support in catalog | Cannot become canonical flash executable merely by configuring RPC; activation blocked |

Common non-Base blockers are source-level and cannot be resolved solely by supplying RPC URLs or a funded signer. A Base Sepolia record is not evidence for any mainnet.

### Venue-by-venue matrix (15 registered chain/venue cells)

| Chain / venue | Resolver | Direct quote backend | Plan adapter | Current receiver swap compatibility |
|---|---|---|---|---|
| Base / Uniswap V3 | Canonical | Exists | Exists, Base address book | Yes, schema-level only |
| Base / Aerodrome classic | Canonical/runtime resolver | Exists | Exists | No — new receiver required |
| Base / Aerodrome Slipstream | Canonical/runtime resolver | Exists | Exists; configured router needed | No — new receiver required |
| Ethereum / Uniswap V3 | Exists | Exists | Class exists; common target address book lacks chain | Schema only; no deployment record |
| Ethereum / Sushi V2 | Exists | Exists | Exists; configured router needed | No |
| Ethereum / Curve stable | **Missing** | **Missing** | **Missing** | No |
| Arbitrum / Uniswap V3 | Exists | Exists | Class exists; common target address book lacks chain | Schema only; no deployment record |
| Arbitrum / Sushi V3 | Exists | Exists | Exists; configured router needed | No |
| Arbitrum / Camelot V3 | Algebra resolver | Exists | Exists; configured router needed | No |
| Optimism / Uniswap V3 | Exists | Exists | Class exists; common target address book lacks chain | Schema only; no deployment record |
| Optimism / Velodrome V2 | **Missing** | **Missing** | **Missing** | No |
| Polygon / Uniswap V3 | Exists | Exists | Class exists; common target address book lacks chain | Schema only; no deployment record |
| Polygon / QuickSwap V3 | Algebra resolver | Exists | Exists; configured router needed | No |
| BNB / Uniswap V3 | Exists | Exists | **Class rejects BNB** | Not deployable/executable from this classification |
| BNB / Pancake V3 | Exists | Exists | Exists; configured router needed | No |

This is broader than the canonical flash path: its non-Base `_plan_generic_evm` only accepts `uniswap_v3`. Direct tool capability and canonical runtime connectivity must be displayed separately.

### Flash/liquidity matrix

| Provider | Catalog chain scope | Liquidity implementation | Receiver / runtime truth |
|---|---|---|---|
| Balancer V2 | Base, Ethereum, Arbitrum, Optimism, Polygon | Code/balance/USD sufficiency reader; M3 Base vault check | Receiver head and calldata exist; **Base M3's only accepted provider**. No BNB catalog support |
| Aave V3 | All six in economics catalog and pool map | Reserve/aToken balance reader exists; fee defaults to 5 bps | Receiver head and calldata exist, but M3 explicitly rejects it; Aave execution adapter excludes BNB |
| Uniswap V3 flash | Five non-BNB catalog chains | Provider optimizer requires resolved fee and liquidity; no demonstrated full canonical borrow-proof wiring | Borrow/repay adapter exists; **no matching receiver flash head** |
| Morpho Blue | Ethereum and Base | Optimizer/catalog and env-address adapter exist; no demonstrated canonical liquidity integration | **No receiver flash head**; zero catalog fee does not establish usable flash capacity |

Evidence: `app/backend/arbicore/scanners/flash_loan_arbitrage/economics.py:29-56`; `app/backend/arbicore/scanners/flash_loan_arbitrage/provider_liquidity.py:143-232`; `app/backend/arbicore/execution/adapters.py:86-93`; `app/backend/arbicore/runtime/composition.py:524-550`.

## 5. Critical / High findings

### H01 — Unauthenticated network configuration can redirect signer RPC and executor settings

**Severity:** High · **Priority:** P0 · **Class:** authorization / execution-input integrity · **Confidence:** confirmed statically.

- **Evidence:** `app/backend/server.py:5879-5904` (`v2_settings_network_draft`, `v2_settings_network_apply`) and `app/backend/server.py:5910-5924` (rollback) lack an operator dependency. `app/backend/arbicore/config/env_sync.py:56-76` writes RPC/executor values into process environment. `LimitedLiveBroadcaster._rpc_url`, `app/backend/arbicore/execution/broadcast.py:259-260`, reads that environment. No application-wide authorization guard compensates for these routes.
- **Impact:** a caller that can reach the API can persistently alter RPC/executor configuration. Subsequent operator reads/preflight and the send endpoint can be directed through an attacker-controlled RPC, compromising input integrity and availability. A separate outer infrastructure ACL could restrict exposure, but none was verified here.
- **Boundary:** authenticated operator confirmation, signer/owner constraints and other broadcast gates still exist. Anonymous immediate signing/theft was not demonstrated.
- **Required fix:** authenticate and authorize every config mutation; derive actor from session; validate chain identity and allowed RPC destinations; revalidate dependent objects after changes; use revisioned, consistent configuration rather than mixed hot/cached state.

### H02 — Unauthenticated per-strategy mode changes bypass the intended operator boundary

**Severity:** High · **Priority:** P0 · **Class:** authorization / safety-control integrity · **Confidence:** confirmed statically.

- **Evidence:** `v2_execution_mode_transition`, `app/backend/server.py:3400-3413`, accepts a client-supplied actor and invokes `ExecutionModeRepo.transition`, `app/backend/arbicore/execution/mode.py:183-211`. The broadcaster uses that same repository at `app/backend/arbicore/execution/broadcast.py:469-479`.
- **Impact:** anonymous callers can advance valid ladder steps, roll back modes to disrupt trading, and forge audit attribution. The Control Center's separate hard block on LIMITED_LIVE (`app/backend/arbicore/control/readiness.py:489-505`) does not guard this route.
- **Boundary:** mode is only one gate; this is not a direct broadcast authorization bypass by itself.
- **Required fix:** operator/admin authorization on strategy transitions; server-derived actor; compare-and-set transitions; unify the control-mode and strategy-mode authorization policy and evidence requirements.

### H03 — Missing authentication extends across operational mutation endpoints

**Severity:** High · **Priority:** P0 · **Class:** systemic API authorization / operational integrity · **Confidence:** confirmed statically.

- **Evidence:** `app/backend/server.py:6332-6354` exposes arbitrary pipeline evaluation; `app/backend/server.py:6371-6386` exposes auto-executor start/stop/tick without an operator dependency. The separate security review also identified settings, discovery, scanner configuration, Telegram and learning writes in the same router family.
- **Impact:** unauthorized worker control, resource consumption, configuration mutation and contamination of operator/research records. CORS is not an authentication mechanism.
- **Boundary:** the server's pipeline retains `auto_confirm=False`, so this finding does not establish automatic transaction submission.
- **Required fix:** deny-by-default route authorization, explicit public-route allowlist, rate limits, server-derived actors, and an endpoint authorization inventory with negative-access checks.

### H04 — Throttle signature regression prevents atomic simulation and wallet token reads

**Severity:** High · **Priority:** P0 · **Class:** deterministic runtime defect / activation blocker · **Confidence:** confirmed by caller/callee signatures; not executed.

- **Evidence:** `app/backend/arbicore/execution/quoter.py:263-271` requires `_throttle(scope)`. `AtomicExecutorSimulator._raw_eth_call`, `app/backend/arbicore/execution/atomic_executor_sim.py:44-53`, calls `_throttle()` without an argument. `WalletIntelligenceEngine._eth_call`, `app/backend/arbicore/capital/wallet_intelligence.py:88-95`, does the same.
- **Impact:** once those calls are reached, Python argument binding raises `TypeError` before HTTP I/O. Atomic capability checks return failure; exact atomic simulations report RPC errors. Wallet ERC-20 read paths fail or propagate errors according to their outer callers. The mandatory Base atomic runner is wired at `app/backend/server.py:403-408`.
- **Boundary:** this is generally a safe denial, not unsafe transaction execution; fixing the error does not certify the rest of the route.
- **Required fix:** update every consumer to the host-scoped throttle contract (prefer a shared public RPC client interface); audit callers for interface drift; verify real consumer paths with isolated RPC substitutes in a later authorized engineering phase.

### H05 — Canonical profitability and final revalidation scale a probe quote to a different notional

**Severity:** High · **Priority:** P0 · **Class:** economic correctness / false profitability · **Confidence:** confirmed statically.

- **Evidence:** `_plan_base`, `app/backend/arbicore/scanners/flash_loan_arbitrage/live_quote_provider.py:94-120`, always takes `probe_amount(borrow_token)`. `_provider` receives `borrow_amount_usd` but does not use it to size the quote (`app/backend/arbicore/scanners/flash_loan_arbitrage/live_quote_provider.py:194-237`). The verifier selects a separate USD amount (`app/backend/arbicore/scanners/flash_loan_arbitrage/verifier.py:100-107`) and applies the probe percentage in `assess` at lines 187-202. Final M3 revalidation similarly multiplies `borrow_usd` by this percentage in `app/backend/arbicore/runtime/composition.py:659-662` and `app/backend/arbicore/runtime/composition.py:721-732`.
- **Impact:** price impact is nonlinear; a small probe's edge cannot certify a larger trade. The $25 gate and final profit buffer can evaluate a dollar profit not quoted at the actual transaction size. Non-Base metadata also explicitly supplies a probe amount, not an executable size. This can create false confirmations, failed executions or net profit below the advertised policy.
- **Boundary:** full-call preflight, slippage bounds and repayment checks remain; they do not make the mismatched dollar-profit estimate valid. No loss or profitable candidate was observed.
- **Required fix:** carry exact token-unit input, token decimals, trustworthy USD price, per-hop outputs and block context through quote → economics → calldata → final revalidation. Re-quote every candidate size and reject any amount/route mismatch. Keep probes research-only.

### H06 — Quoter endpoint selection reintroduces cross-chain RPC leakage

**Severity:** High · **Priority:** P0 · **Class:** chain isolation / quote provenance · **Confidence:** confirmed statically.

- **Evidence:** `QuoterRegistry._rpc_url_candidates`, `app/backend/arbicore/execution/quoter.py:939-944`, adds the default global `ARBICORE_RPC_URL` before the chain-specific RPC and adds global fallback pools for every chain. `_rpc_url` also prefers the global variable at `app/backend/arbicore/execution/quoter.py:899-913`. The quote loop passes the intended chain and selected endpoint independently (`app/backend/arbicore/execution/quoter.py:1039-1050`). Quote RPC helpers query `eth_call`/block height, not expected-chain identity (`app/backend/arbicore/execution/quoter.py:279-319`).
- **Impact:** with global Base plus non-Base endpoints configured, a non-Base quote first uses Base. It can fail on the wrong chain or, if addresses/ABI happen to work there, accept and cache a quote under the wrong intended-chain key. A genuine revert can stop failover before the correct endpoint is tried.
- **Boundary:** the broadcast path has its own chain-ID check; it does not retroactively repair discovery/quote/economic evidence. The persistent resolver's Base-only global alias does not govern this independent endpoint-list implementation.
- **Required fix:** one chain-scoped endpoint resolver for all consumers; restrict global Base aliases to Base; verify endpoint chain identity before use/failover; bind cache entries and evidence to verified chain, endpoint generation and block.

### H07 — Canonical six-chain flash connectivity is incomplete despite registered adapters

**Severity:** High · **Priority:** P1 · **Class:** runtime integration / six-chain scope blocker · **Confidence:** confirmed statically.

- **Evidence:** canonical `_plan_generic_evm` explicitly rejects `dex != "uniswap_v3"` at `app/backend/arbicore/scanners/flash_loan_arbitrage/live_quote_provider.py:153-168`; `_wire_canonical_flash_loan_scanner` installs only `build_base_tvl_provider` at `app/backend/arbicore/runtime/composition.py:1348-1368`. Its reserves reader ignores the chain argument and searches Base metadata (`app/backend/arbicore/searcher/v3_state.py:188-212`). `_IN_SCOPE_CHAINS` excludes BNB (`app/backend/arbicore/scanners/flash_loan_arbitrage/sources.py:35-37`, `app/backend/arbicore/scanners/flash_loan_arbitrage/sources.py:102-108`). M3 rejects all non-Balancer borrowing at `app/backend/arbicore/runtime/composition.py:537-550` and re-quotes as Base at lines 659-662.
- **Impact:** Sushi/Algebra/Pancake standalone quoters do not make canonical flash routes work. Typical non-Base pools have no TVL metadata in the Base provider and are denied; it is not a chain-valid liquidity source. BNB cannot emit canonical flash candidates even with enabled configuration. Aave cannot pass final M3 despite its receiver head.
- **Required fix:** compose per-chain, per-venue resolver/quote/TVL/price/liquidity/gas/simulation services into the actual scanner and final validator; implement and verify BNB's complete source/provider/adapter path; preserve fail-closed behavior rather than merely broadening allowlists.

### H08 — Broad venue/chain execution requires deployment and receiver engineering, not just configuration

**Severity:** High · **Priority:** P1 · **Class:** execution capability / product-scope blocker · **Confidence:** confirmed source and recorded inventory; on-chain state unverified.

- **Evidence:** `FlashLoanReceiver` owns one immutable `uniRouter` and explicitly fixes the swap set (`contracts/contracts/core/FlashLoanReceiver.sol:46-61`); both callbacks run UniV3 hops (`contracts/contracts/core/FlashLoanReceiver.sol:145-149`, `contracts/contracts/core/FlashLoanReceiver.sol:213-216`). The dispatcher rejects other venues (`app/backend/arbicore/execution/settlement_dispatcher.py:221-234`) and requires a deployment record (`app/backend/arbicore/execution/settlement_dispatcher.py:248-278`). `deploy/executor_deployments.json` contains only Base 8453 and Base Sepolia 84532 records. Aave and UniV3 swap adapter chain lists exclude BNB (`app/backend/arbicore/execution/adapters.py:86-93`, `app/backend/arbicore/execution/adapters.py:226-232`). The common address book is Base-only (`app/backend/arbicore/execution/adapters.py:34-47`).
- **Impact:** registered route adapters cannot settle Aerodrome, Sushi, Pancake, Camelot or QuickSwap through this receiver. Missing non-Base deployments and adapter/target provisioning block five mainnets. UniV3/Morpho flash adapters do not add receiver callbacks.
- **Boundary:** source supports **both** Balancer and Aave heads; old “Balancer-only receiver” reports are stale. Final M3 is nevertheless Balancer-only (H07). The existing receiver cannot be upgraded in place; owner is immutable as well.
- **Required fix:** versioned receiver design with explicit supported flash heads and per-hop venue/router schemas; narrowly allowlisted adapters, no arbitrary execution; independent contract assessment and per-chain deployment/bytecode/immutable verification in a separately authorized phase. Complete chain aliases/address books and calldata integration; do not mark all six executable based on class membership.

### H09 — Multichain runtime certification cannot complete positive economics or candidate simulation

**Severity:** High · **Priority:** P1 · **Class:** certification pipeline / hidden structural blockers · **Confidence:** confirmed statically.

- **Evidence:** `_evaluate_candidates` passes `liquidity_by_provider=None` and `fee_bps_by_provider=None` into `compute_true_net_profit` at `app/backend/scripts/vps_runtime_certify.py:346-350`. The optimizer defaults `require_liquidity=True` and rejects every missing liquidity value (`app/backend/arbicore/scanners/flash_loan_arbitrage/flash_provider_optimizer.py:70-83`, `app/backend/arbicore/scanners/flash_loan_arbitrage/flash_provider_optimizer.py:119-128`). After a hypothetical positive economic result the harness unconditionally labels `SIMULATION_UNAVAILABLE_no_anvil`, without invoking a simulator (`app/backend/scripts/vps_runtime_certify.py:354-360`). Its Anvil check is only availability metadata. Base is intentionally skipped by this script (`app/backend/scripts/vps_runtime_certify.py:128-133`).
- **Impact:** a better RPC, actual arbitrage, or installing Anvil alone cannot complete this certification path. All positive-gross candidates reaching the provider gate lack required inputs. The six-chain race reuses this non-Base evaluator; historical negative samples conceal the later missing dependencies.
- **Required fix:** populate actual borrow-provider liquidity, fees and policy flags; propagate the chosen exact-size route into calldata and a real candidate simulation; make stage-specific reasons reflect what actually ran. Include the canonical Base path in one coherent evidence orchestrator while retaining all six chains.

### H10 — Executor identity can become READY when mandatory getter evidence is missing

**Severity:** High · **Priority:** P0 · **Class:** fail-open readiness classification · **Confidence:** confirmed statically.

- **Evidence:** `inspect_executor` returns `ok=True` after nonempty code even if getter reads return `None` (`app/backend/arbicore/execution/executor_entrypoint.py:82-117`). `probe_executor_identity` only records router/vault mismatches if both expected **and observed** values are truthy, then returns `READY` when no mismatches were recorded (`app/backend/arbicore/scanners/flash_loan_arbitrage/live_readiness_probes.py:398-413`). It does not verify the Aave immutable. `resolve_executor_address` returns a Base env address before consulting the requested chain (`app/backend/arbicore/scanners/flash_loan_arbitrage/live_readiness_probes.py:271-286`).
- **Impact:** bytecode containing the expected selector plus missing router/vault reads can be labeled `executor_identity_confirmed_onchain`. Missing expected registry identity can also remove comparisons. This is not a valid on-chain identity proof and can mislead the readiness matrix.
- **Boundary:** signer-owner matching independently fails closed if owner is absent (`app/backend/arbicore/scanners/flash_loan_arbitrage/live_readiness_probes.py:299-315`); full transaction gates remain. A missing router/vault read with a readable owner still creates a false identity claim.
- **Required fix:** require explicit expected identity and successful, nonzero, exactly matched getter reads for the selected provider; verify chain and bytecode/artifact identity; require selector evidence positively true; unknown/missing evidence must be UNKNOWN/DENY, never READY. Resolve executor addresses per requested chain.

## 6. Medium findings and other important observations

### M01 — Readiness and simulation labels collapse unlike evidence classes

**Priority P1.** `ExecutionReadinessEngine._simulation` reports GREEN from an RPC env variable (`app/backend/arbicore/control/readiness.py:335-341`). Its contract check combines address presence with an Aerodrome encoder self-test (`app/backend/arbicore/control/readiness.py:343-365`), not an on-chain compatible receiver. `NoopSimulator` returns `ok=True` without chain access (`app/backend/arbicore/execution/simulation.py:152-192`), and `ExecutionCertifier` maps that boolean to simulation PASS (`app/backend/arbicore/execution/certification.py:232-243`). The paper pipeline supplies placeholder target/calldata when absent (`app/backend/arbicore/execution/pipeline.py:482-510`). The fork harness checks infrastructure/state overrides, not an arbitrage route (`app/backend/arbicore/execution/executor_entrypoint.py:217-244`).

**Required fix:** expose simulation tiers (symbolic/heuristic/RPC-capability/exact-call/fork) and state overrides explicitly; only exact candidate-bound evidence may satisfy live certification. Keep no-op/paper tools, clearly marked **MOCKED / HEURISTIC**, outside financial proof. The global Control Center still blocks live modes, limiting direct impact.

### M02 — “Connected” matrices multiply component membership, not real strategy integrations

**Priority P1.** `build_opportunity_matrix` repeats each chain/venue state across five strategy labels (`app/backend/arbicore/discovery/opportunity_engine.py:231-237`), while `quote_path_connected` is just resolver availability plus backend membership (`app/backend/arbicore/discovery/opportunity_engine.py:192-208`). This does not prove, for example, funding execution through a DEX or an EVM launch strategy. The standalone executor audit computes execution capability from adapter membership and supported DEX membership, not chain-specific deployment or adapter `supports(chain)` (`app/backend/scripts/executor_capability_audit.py`, `audit_execution_capability`). Its six “execution-capable” UniV3 cells must not be read as six deployed execution engines.

**Required fix:** report applicable strategy/venue combinations, callable runtime path, required configuration, receiver support and deployment separately; do not omit any chain, and distinguish NOT_APPLICABLE from NOT_IMPLEMENTED. Preserve runtime-unverified and limited-live-false flags.

### M03 — Several economic/liquidity values remain estimates, not “actual all-in” proofs

**Priority P1.** Canonical verifier gas falls back to per-chain estimates (`app/backend/arbicore/scanners/flash_loan_arbitrage/economics.py:161-170`); absent chain liveness becomes congestion `30.0` (`app/backend/arbicore/scanners/flash_loan_arbitrage/verifier.py:477-484`). Aave's liquidity reader accepts a default 5-bps fee and checks token availability, not all live reserve flash flags or a measured premium (`app/backend/arbicore/scanners/flash_loan_arbitrage/provider_liquidity.py:173-217`). The gas model uses a configurable 1,200-byte assumption if no transaction is supplied (`app/backend/arbicore/chains/evm_gas.py:94-110`, `app/backend/arbicore/chains/evm_gas.py:183-208`). `compute_true_net_profit` subtracts the provider fee in addition to an environment-configured gas-model flash-fee term (`app/backend/arbicore/scanners/flash_loan_arbitrage/multichain_economics.py:78-101`), so a nonzero shared flash-fee setting can double count.

**Required fix:** explicitly label model inputs; measure provider premium/policy and exact transaction gas/data fees; assign one owner to each fee component; distinguish V3 pool token TVL from active executable liquidity; require trustworthy native/stable/derivative pricing. Final Base M3 does use a real congestion read and all-in gate, so not every economics path uses the verifier defaults.

### M04 — “Dynamic optimal size” in the certification harness is not net-optimal or propagated

**Priority P1.** `_size_sweep` ranks gross profit (`app/backend/scripts/vps_runtime_certify.py:216-250`). The later net gate still uses the original probe amount/gross/gas (`app/backend/scripts/vps_runtime_certify.py:332-350`), not the size sweep's best candidate. Stable borrow pricing is set to `1.0` at lines 317-321.

**Required fix:** optimize exact-size net profit after gas/premium/risk, propagate the winning amount/hops, and retain fail-closed USD provenance. The current code can miss a candidate profitable only at another size; this is not proof of optimum sizing.

### M05 — Deadline and block-height-only freshness are weaker than advertised

**Priority P1.** The pre-broadcast deadline returns PASS when `deadline_ts` is absent (`app/backend/arbicore/execution/pre_broadcast.py:133-137`); composed revalidation reads it from the plan (`app/backend/arbicore/runtime/composition.py:757-767`) without a populated canonical deadline path identified. Reorg checking compares heights, not block hashes (`app/backend/arbicore/execution/pre_broadcast.py:120-131`). Quote helpers may read the head after an unpinned call, and routes can use cached hops. Receiver callbacks enforce repayment but no explicit route-level minimum net profit or deadline (`contracts/contracts/core/FlashLoanReceiver.sol:158-177`, `contracts/contracts/core/FlashLoanReceiver.sol:218-229`).

**Required fix:** require a deadline, bind exact quotes/calldata to block hashes and configuration versions, validate final freshness, and design appropriate on-chain expiry/minimum-profit protection. Account for gas/revert risk separately. Existing block-lag, slippage and repayment controls reduce but do not eliminate these gaps.

### M06 — Operational configuration and UI still express conflicting readiness concepts

**Priority P2 (security-related configuration aspects P0/P1).** The global Control Center permanently refuses LIMITED_LIVE/FULL_AUTOMATION, whereas the separate per-strategy ladder admits LIMITED_LIVE/FULL_LIVE. The wizard can label final prerequisites READY while excluding certification WAIT from its WAIT aggregation (`app/backend/arbicore/execution/operator_wizard.py:631-643`). Frontend pages show these different backend notions. `LiveSigner` produces unsigned placeholder envelopes (`app/backend/arbicore/execution/live_signer.py:222-233`), whereas the broadcaster contains real signing. MEV routers are routing metadata only (`app/backend/arbicore/execution/mev.py:1-15`); actual broadcast uses the public RPC send method. Wallet intelligence values stable tokens at $1 and several staking derivatives at ETH price (`app/backend/arbicore/capital/wallet_intelligence.py:128-133`).

**Required fix:** unify mode/readiness semantics, label wallet-only readiness as such, require candidate certification for any “ready to broadcast” banner, distinguish unsigned previews from signed transactions, and do not imply private MEV submission or market-accurate valuation from metadata. Also restrict credentialed CORS origins and explicitly require secure cookie settings for production (`app/backend/server.py:6528-6534`; `app/backend/services/auth.py:85-90`).

## 7. Historical evidence reconciliation

| Artifact in target commit | What it records | What it does not prove |
|---|---|---|
| `deploy/executor_deployments.json` | Base mainnet success record at `0x0e3fdb0f0e615a517588bd44ac6c78bb7615927f`, deployment tx `0x39ce6224caffb17ee4fb846d2239157daa5a1af5ea5fcfdea0548f7020b336ff`, block 50991980; Base Sepolia also recorded | Fresh bytecode/owner/router/pool verification, source equivalence, current state or arbitrage execution/P&L |
| `reports/EXECUTOR_CAPABILITY_AUDIT.json` | 15 venue cells; 13 discoverable/quotable/route-constructable; 6 execution-capable; recorded flash support only Balancer | Artifact is stale relative to target source's Aave head and omits chain-specific deployment/adapter constraints. These are structural counts, not live passes |
| `reports/VPS_RUNTIME_CERT_public.json` | Historical public-RPC report: 62 probe rows, 56 quotable, 15 candidates, 0 economically valid, 0 execution-ready; all candidates negative gross at sampled sizes; Base skipped | Exact-commit/operator-authoritative runtime, positive-path certification, all-market profitability or current state |
| `reports/VPS_RUNTIME_CERT_public_phase5_harnessfix.json` | Historical public-RPC report: 45 rows, 40 quotable, 7 candidates, 0 economic/execution-ready; Base skipped; Anvil unavailable | Successful provider/economic/simulation stages; H09 means zero results are not solely a market issue |
| `scripts/arbicore_certify.py` implementation | `repo_capability_pass` covers selected compilation, protected integrity and safety settings; explicitly leaves P0-3 false and runtime unverified | Whole-app integration correctness, authorization coverage, deployment identity, exact route execution or profitability |

No historical pass count was rerun or accepted as proof for this commit. The handoff PRD was useful orientation but is stale in places, including receiver flash-provider support and broad “non-Base only needs RPC” claims. Final document checks resolved all 101 line-range references across 43 distinct files against the target Git snapshot. Targeted AST inspection additionally confirmed the throttle signature/call mismatch and the unprotected router/endpoint declarations, without executing application code.

## 8. Existing safeguards worth preserving

- Owner-gated receiver entrypoints and callback caller/provider checks; Aave initiator check; repayment enforcement.
- Unsupported swap venues are rejected by the settlement dispatcher; absent chain deployments stay denied.
- Complete-quote checks reject partial/fallback routes in canonical verification; missing route TVL yields a closed gate.
- Controlled broadcaster requires revalidation; missing fresh inputs are denied. Kill switch, strategy mode, capital, slippage, chain-ID preflight and explicit confirmation are separate barriers.
- The automatic pipeline defaults to `auto_confirm=False`; read-only tools do not enable live execution.
- Evidence stores preserve candidate/run attribution, and learning/certification components distinguish real from simulated provenance.

These strengths are real source features, **not** a global safety certification. H01-H10 show why safety must be assessed across the complete composed path rather than from selected safe modules.

---

# Phase B — Forward Engineering Assessment

## 9. Prioritized engineering program

Recommendations only. **Nothing in this section has been implemented or executed.** P0 work protects integrity and repairs hard failures; P1 builds complete six-chain capability. Base is the best-developed reference path, **not a reduction of scope**. Other chains can be engineered and certified in parallel once shared invariants are established.

### P0 — Repair security, correctness and proof integrity before promotion

| Workstream | Required outcome / acceptance evidence | Findings |
|---|---|---|
| Authorization boundary | All network/mode/settings/worker/pipeline mutations require authenticated authorized roles; spoofed actor ignored; explicit public routes; authorization regression matrix | H01-H03 |
| Atomic/wallet RPC interface | All throttle consumers use the same scoped contract; no caller-signature errors; consumer-level failure/timeout/429 handling; missing input stays denied | H04 |
| Chain identity isolation | Chain-scoped endpoints and cache identity; no Base-global fallback for non-Base; wrong-chain endpoints rejected before quote/liquidity use | H06 |
| Exact economic amount | One immutable exact-size route object through quote, cost, calldata and final validation; any input/output/chain/venue mismatch denied | H05 |
| Executor identity | Expected chain, artifact, owner, router and chosen flash head immutables positively verified; missing data cannot become READY | H10 |
| Safety/evidence discipline | Preserve live-off/fail-closed posture until separately authorized; label heuristic evidence; require deadline and candidate-bound proof; do not treat health/compile as certification | M01, M05 |

### P1 — Complete broad six-chain end-to-end activation capability

1. **Canonical chain service composition:** inject chain-specific discovery, quotes, prices, V3 depth, provider liquidity, fees, gas, simulation and evidence services into scanner, race, verifier and final broadcaster. Eliminate the separate partially connected paths in H07/H09.
2. **Receiver and provider expansion:** design a versioned receiver for explicit cross-venue routing and required flash providers. Complete Curve and Velodrome discovery/quote/plan support rather than dropping them. Audit router ABIs, callbacks, approvals, repayment, slippage, deadlines and profit protection. Plan independent review and verified deployment on every requested chain; do not enable from an address string alone.
3. **BNB first-class parity:** resolve catalog/source/adapter/chain-ID inconsistencies; implement BNB-compatible provider and gas/price paths. Do not merely add `bnb` to a list.
4. **Candidate certification harness:** measure provider liquidity/premium, optimize net rather than gross, propagate selected size, build exact calldata, run genuine fork/exact-call validation, and persist/read back coherent evidence. Keep market rejection separate from missing software or operator configuration.
5. **Cost and capital truth:** use exact transaction estimates and native-token prices; separate gas wallet, borrow-provider capacity, DEX executable depth and risk limits. Avoid fee double counting and unguarded stable/derivative assumptions.
6. **One operator readiness model:** reconcile Control Center, per-strategy modes, flash wizard and candidate eligibility. “Ready” must name its scope and evidence, not silently promote component readiness to trading readiness.

### Per-chain P1 deliverables — no scope narrowing

| Chain | Required work beyond shared P0 |
|---|---|
| Base | Restore atomic path; exact-size economics; finish Aave live availability; receiver support for classic/Slipstream Aerodrome; verify recorded deployment/immutables, then certify exact candidates |
| Ethereum | Compose UniV3/Sushi paths and genuine TVL/provider inputs; implement Curve; receiver and deployment provisioning; mainnet gas/MEV/capital evidence |
| Arbitrum | Compose Sushi/Camelot alongside UniV3; active-liquidity and fee semantics; accurate posting-cost evidence; receiver/deployment and exact-route certification |
| Optimism | Complete Velodrome V2 resolver/quote/plan/receiver path; OP data-fee evidence; per-chain TVL/provider composition and deployment |
| Polygon | Compose QuickSwap Algebra with UniV3; POL-denominated gas/price and dynamic-fee handling; receiver/deployment and exact-route evidence |
| BNB | Remove source/adapter inconsistencies only after real support exists; Aave/Pancake/UniV3 compatibility; BNB-native cost/price evidence; receiver/deployment and canonical certification |

### P2 — Production operating discipline and strategy breadth

- Durable execution idempotency, nonce reservation and per-wallet concurrency across restarts/workers; distinguish submitted, pending, mined, reverted, replaced and reorged transactions. Do not equate a transaction hash with success.
- Receipt/event reconciliation of principal, premium, profit recipient, gas and realized net P&L; loss limits tied to actual outcomes; auditable incident/stop decisions.
- Measured per-chain RPC health, freshness, rate-limit and candidate-latency budgets; failover tests; visibility of every exclusion and missing dependency.
- Restore/recovery drills, Mongo indexes/retention, durable evidence versioning, build/image provenance and configuration-revision binding.
- Private submission integrations where appropriate, with explicit no-silent-public-fallback policy. Existing MEV routing metadata does not provide this.
- Mature CEX/funding execution and cross-chain inventory/bridge finality/recovery as independently certified workflows; do not force them into same-transaction flash semantics.
- Six-EVM-chain launch intelligence/execution coverage where intended; distinguish optional Solana/Helius research from requested-chain capability.
- Consolidate duplicated registries, validators and mode systems; preserve audited behavior while reducing composition complexity. Improve frontend component-specific errors and consistent readiness labels.

### P3 — Optimization after truthful, stable capability

- Net-profit and execution-success attribution by chain, venue, strategy, size and provider; evidence-backed route ranking and adaptive calibration.
- Larger token/pool universe, smarter search pruning and latency optimizations only after deterministic state/amount binding.
- Provider/venue expansion with versioned compatibility certification instead of global “supported” labels.
- Confidence calibration, market-regime analysis and capital optimization evaluated against held-out real outcomes, not synthetic success counts.

## 10. Proposed acceptance evidence for each chain

To progress beyond “implemented,” a future separately authorized engineering/certification effort should produce a single candidate-bound bundle containing:

- Full commit and image identity, configuration revision, audit/run/candidate IDs, chain ID and verified RPC identity; no secret values.
- Pinned block number **and hash**, timestamp, quote expiry, pool/factory/token identities and decimals, ABI/fee/tick-spacing metadata.
- Exact input size, ordered per-hop quoted outputs, minimum outputs and full route calldata hash.
- DEX executable liquidity/depth, actual provider available borrow amount, provider policy/fee and borrower/callback compatibility.
- Native/USD/borrow-token price evidence; premium, gas/L1/data costs, slippage/risk allowance and independently recomputable expected net.
- Verified receiver bytecode/artifact, immutables, supported head/venues and public caller identity; no signer secret.
- Exact-transaction simulation result, backend, block, target, caller, overrides and repayment/profit deltas. Heuristic/code-injection/funded-fork evidence must be distinguished from deployed-state/no-override evidence.
- Persisted evidence with successful readback, a reproducible replay specification, and explicit PASS/FAIL/UNKNOWN for every required gate.
- Operator policy/approval, mode, kill switch and capital checks only for a separately authorized promotion process. **The present audit authorizes none of these actions.**

First live execution would be a separate decision after those conditions: bounded exposure, explicit authorization and complete receipt/finality/net-P&L reconciliation. No live command, signer enabling, deployment or transaction is included in this audit.

## 11. Final disposition

**Phase A complete:** fixed-commit source review, major subsystem inventory, six-chain and venue/provider matrices, historical-evidence reconciliation, ten High findings and six Medium observation groups.

**Phase B complete:** P0/P1/P2/P3 roadmap and per-chain acceptance evidence without narrowing the six-chain target.

**Not performed:** application tests, runtime probes, live simulation, source/configuration fixes, signer enabling, transaction broadcast, deployment, commits, merges or PRs. No profitable execution or production readiness is claimed.

**Suggested product improvement:** an evidence-linked capability dashboard showing, for every chain/venue/strategy, the exact last completed gate, first blocker and evidence age would make false readiness much harder to introduce or misunderstand.

**STOP — report delivered; no fixes implemented.**