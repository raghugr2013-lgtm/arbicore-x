# ArbiCore X v2 — Complete Independent Two-Phase Audit

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

No source, configuration, or secret changes were made. The original audit produced this report and an administrative handoff entry. The subsequent report-only export updates **only this report**, with an identical downloadable copy outside the repository; it does not update source, configuration, secrets, or handoff memory. Actual environment values, private keys, credentials, operator permissions, wallet funding, current markets, deployed bytecode, and production access controls were not inspected or attested.

Coverage includes every major subsystem and the principal discovery-to-execution flows. It is **not** a formal proof of every function, a complete smart-contract security certification, or a claim that all defects have been found. Broad legacy CEX/operator workflows and frontend behavior received sampled static coverage, not browser or execution testing.

---

# Phase A — COMPLETE CURRENT-STATE AUDIT

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

**Finding totals:** **0 confirmed Critical; 10 High; 7 Medium observation groups; 4 Low groups.** The Low groups include the complete 38-item unused-import/local inventory in the inspected Python subset, plus an operator-only diagnostic-RPC hardening observation. H07-H09 include capability/activation blockers, not merely exploitable defects. Severity and engineering priority are separate: a High six-chain capability gap may be P1, whereas a High integrity/security defect is P0. Detailed export preparation added M07's directly evidenced mocked status responses; no earlier finding was removed or shortened.

**Readiness conclusion:** 0/6 requested mainnets are demonstrated by this audit to have fresh, exact-size, economically valid, fully simulated, authorized profitable execution. This means **not proven**, not “arbitrage never exists” or “no transaction has ever occurred.”

## 2. What the application actually contains

### Whole-app architecture assessment

The system is an evolutionary architecture with **multiple overlapping orchestration and readiness layers**, not one uniformly composed multichain execution engine. That distinction explains many of the findings.

```text
React operator / legacy settings / v2 dashboards
                 |
           FastAPI server.py
                 |
    +------------+-------------------+----------------------+
    |                                |                      |
Canonical scanners             Base opportunity       Manual plans /
and verifiers                  engine / discovery     operator workflow
    |                                |                      |
DiscoveryCandidate             Route graph / search        |
    |                                |                      |
Chain/venue quote + liquidity + economics + provenance      |
    |                                |                      |
CanonicalOpportunity --> emission / Mongo evidence / journal|
    +--------------------------------+----------------------+
                                     |
                       planner / quote / simulation
                                     |
                      readiness / mode / capital controls
                                     |
                    LimitedLiveBroadcaster.broadcast_plan
                                     |
               preflight + confirmation + final validation
                                     |
                    verified-chain RPC submission
                                     |
                   FlashLoanReceiver (UniV3 router)
                   Balancer receiveFlashLoan callback
                   or Aave executeOperation callback
                                     |
                       repayment / profit forwarding
```

This is a **logical subsystem map**, not an assertion that every arrow is currently connected for every chain or strategy. The read-only multichain opportunity race/certifier is another evaluation path; it does not cure the canonical scanner's missing composition or constitute a six-chain live broadcaster.

**Composition:** `app/backend/arbicore/runtime/composition.py` supplies scanner factories and final controlled-live safety. `app/backend/server.py:288-408` additionally assembles journal, paper validation, shadow certification, operator readiness and Base atomic simulation. Factory defaults must be considered together with startup injection: bridge/Helius providers can be attached later. Conversely, `server.py` leaves automatic broadcast confirmation off (`app/backend/server.py:447-480`). This dispersed construction makes it easy for standalone capability to diverge from the live path.

**Persistence:** Motor connects through `MONGO_URL` and `DB_NAME` (`app/backend/services/db.py:10-11`). Evidence storage creates unique bundle IDs and run attribution indexes and strips Mongo `_id` before returning inserted documents (`app/backend/arbicore/data/mongo/evidence_bundles_repo.py:25-45`). These are useful implementation properties, not proof that production indexes exist, backups restore, or runtime evidence is complete. The audit did not query Mongo or certify every repository serialization path.

**Front/back boundaries:** the browser can request operator actions but must not be the authorization boundary. `AuthContext` implements cookie-based user state; v2 pages consume several backend-specific notions of READY, connected, certified and signing-eligible. H01-H03 show missing server-side access checks; M01/M06/M07 show why authenticated UI presentation still cannot attest trading capability.

**Evolution and duplication:** global control modes, per-strategy execution modes, wallet readiness, operator wizard readiness, canonical flash assessment, shadow certification and execution certification coexist. They are not interchangeable. For example, the Control Center refuses live modes while the per-strategy route can transition toward them, and `LiveSigner` is an unsigned-envelope preview while `LimitedLiveBroadcaster` is a real transaction path.

**Architectural conclusion:** retain the implemented research/evidence/safety components, but require one authoritative chain/venue/provider capability contract and one candidate-bound execution proof. Do not solve the duplication by hiding unsupported chains or counting registry entries as integrations.

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

#### Strategy implementation evidence index

| Strategy | Exact implementation anchors | Classification |
|---|---|---|
| CEX | `app/backend/arbicore/scanners/cex_arbitrage/scanner.py` — `CEXArbitrageScanner`; `app/backend/arbicore/runtime/composition.py:851-894` — `get_cex_arb_scanner` and CoinGecko source registration | Discovery/verifier implementation; live exchange trading not established |
| Funding | `app/backend/arbicore/scanners/funding_arbitrage/scanner.py` — scanner implementation; `app/backend/arbicore/runtime/composition.py` — `get_funding_arb_scanner` | Research/verification implementation; hedge execution and liability management not established |
| DEX | `app/backend/arbicore/scanners/dex_arbitrage/scanner.py` — scanner implementation; `app/backend/arbicore/scanners/flash_loan_arbitrage/route_search.py` — route-search module | Partially connected execution scope; standalone search and quotes are broader than receiver compatibility |
| Flash | `app/backend/arbicore/scanners/flash_loan_arbitrage/scanner.py`; `app/backend/arbicore/scanners/flash_loan_arbitrage/verifier.py` — `FlashLoanOpportunityVerifier.verify`; `app/backend/arbicore/runtime/composition.py` — `_wire_canonical_flash_loan_scanner` | Partially implemented and blocked by H04-H10 |
| Cross-chain | `app/backend/arbicore/scanners/cross_chain_arbitrage/scanner.py` — `CrossChainArbitrageScanner`; `app/backend/arbicore/scanners/cross_chain_arbitrage/transfer_provider.py` — `LiFiTransferProvider`; `app/backend/arbicore/runtime/composition.py:1816-1843` — provider/liveness registration | Transfer quote and verification implementation; asynchronous execution/finality/recovery not proven |
| Launch | `app/backend/arbicore/scanners/launch_arbitrage/scanner.py` — `LaunchArbitrageScanner`; `app/backend/arbicore/runtime/composition.py:964-1011` — `get_launch_arb_scanner`; startup Helius attachment at `app/backend/arbicore/runtime/composition.py:1768-1773` | Optional provider integration, not six-chain EVM launch execution |

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

### Implementation-state classification used in this report

| State | Meaning | Concrete examples at the audited commit |
|---|---|---|
| **IMPLEMENTED** | Non-placeholder source implements a bounded function; current runtime success remains a separate claim | UniV3 quoting, pool resolver families, Mongo evidence repository, real broadcaster signing/submission code |
| **PARTIALLY IMPLEMENTED** | Important pieces exist but the complete specified flow is not composed/provisioned | Six-chain flash path, Aave live integration, broad cross-venue execution, bridge execution |
| **BLOCKED** | A known source constraint, missing mandatory input or deployment record prevents promotion | `_throttle` mismatch; BNB source exclusion; unsupported receiver venue; missing non-Base deployment; missing provider liquidity |
| **MISSING** | No required implementation was identified in the relevant authoritative path | Curve and Velodrome resolver/quote/plan support; Morpho/UniV3-flash receiver heads; exact candidate simulation in the multichain harness |
| **MOCKED / SIMULATED / HEURISTIC** | Output is synthetic, symbolic, test-oriented or derived from model assumptions rather than measured execution | `NoopSimulator`; placeholder paper calldata; unsigned `LiveSigner` envelopes; hardcoded vault/exchange status and exchange-test responses (M07) |
| **GENUINELY EXECUTION-CAPABLE CODE** | Source can actually invoke a signer and submit a transaction when all reachable conditions are met | `LimitedLiveBroadcaster.broadcast_plan` plus the compatible receiver; not categorically mock-only |
| **GENUINELY EXECUTION-CAPABLE CHAIN / ROUTE** | Exact deployment, provider, venue, caller, amount, economics and simulation are verified together | **Not established for any of the six mainnets by this static audit.** Source capability is not chain/route certification |
| **UNKNOWN / UNVERIFIED** | Evidence was not gathered or was insufficient; not converted to PASS or to “does not exist” | Actual environment/RPC access, deployed bytecode, vault key custody, current pools/profitability, historical transaction outcomes |

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

### Critical findings

**No Critical finding was confirmed in the completed audit.** This is not a guarantee of absence. No anonymous direct signing or demonstrated loss-of-funds exploit was established, and the audit did not attempt one. Security severity remains High where a reachable unauthorized state change was proven statically but broadcast has additional independent barriers.

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

### M07 — Vault readiness, exchange connectivity and connection tests are explicitly MOCKED

**Severity:** Medium · **Priority:** P1 · **Class:** false readiness / misleading operator information · **Confidence:** confirmed statically during export evidence completion.

- **Files / functions:** `app/backend/server.py:3039-3047` — `v2_settings_vaults`; `app/backend/server.py:3050-3052` — `v2_settings_vault_reconcile`; `app/backend/server.py:3070-3088` — `v2_settings_exchanges`, `v2_settings_exchange_test`.
- **Evidence:** `v2_settings_vaults` returns literal cold/hot/multisig/exchange entries, abbreviated placeholder addresses and `state="READY"`, stamping them with the current time. `v2_settings_vault_reconcile` simply echoes `ok=True` and timestamps; it does not reconcile custody. `v2_settings_exchanges` returns a literal list with placeholder masked keys and connection/read-only flags. `v2_settings_exchange_test` computes `ok = key != "gate-io"` and returns a fixed 62 ms latency on success. It performs no exchange API call or credential validation.
- **Impact:** an operator can mistake a canned status and newly generated timestamp for current custody, permission or connectivity evidence. An arbitrary unknown exchange key other than `gate-io` receives this synthetic success response. This is particularly misleading in an application whose purpose depends on genuine financial connectivity.
- **Boundary:** these responses do not prove actual credentials, account access, balances, custody or live trading. They do not invalidate separate real balance/provider implementations elsewhere. No secret value was read; the masked strings in this handler are source literals.
- **Required fix:** explicitly mark these surfaces **MOCKED** and never use them as readiness evidence; replace them with authenticated, provider-derived state and measured tests in a separately authorized engineering task. Missing integrations must be UNKNOWN/NOT_CONFIGURED, not CONNECTED or READY. A reconcile action must either perform a verifiable operation or state that it is unavailable.

### Medium-finding function/class evidence index

The following index makes the supporting symbol explicit where a grouped finding spans multiple modules. All substantive evidence and impact are retained above.

| Finding | Functions/classes and exact paths |
|---|---|
| M01 | `ExecutionReadinessEngine._simulation`, `ExecutionReadinessEngine._contracts` — `app/backend/arbicore/control/readiness.py:335-365`; `NoopSimulator.simulate` — `app/backend/arbicore/execution/simulation.py:160-192`; `ExecutionCertifier.certify` — `app/backend/arbicore/execution/certification.py:232-243`; `OpportunityPipeline._run_simulate_stage` — `app/backend/arbicore/execution/pipeline.py:482-510`; `AnvilForkHarness` — `app/backend/arbicore/execution/executor_entrypoint.py:217-244` |
| M02 | `_cell_state`, `build_opportunity_matrix` — `app/backend/arbicore/discovery/opportunity_engine.py:192-237`; `audit_execution_capability` — `app/backend/scripts/executor_capability_audit.py` |
| M03 | `FlashLoanEconomicsAssessor.assess` — `app/backend/arbicore/scanners/flash_loan_arbitrage/economics.py:161-170`; `FlashLoanOpportunityVerifier._chain_congestion` — `app/backend/arbicore/scanners/flash_loan_arbitrage/verifier.py:477-484`; `read_aave_liquidity` — `app/backend/arbicore/scanners/flash_loan_arbitrage/provider_liquidity.py:173-217`; `EvmGasConfig.from_env`, `make_evm_all_in_cost_estimator.estimate` — `app/backend/arbicore/chains/evm_gas.py:94-110`, `app/backend/arbicore/chains/evm_gas.py:183-208`; `compute_true_net_profit` — `app/backend/arbicore/scanners/flash_loan_arbitrage/multichain_economics.py:78-101` |
| M04 | `_size_sweep`, `_evaluate_candidates` — `app/backend/scripts/vps_runtime_certify.py:216-250`, `app/backend/scripts/vps_runtime_certify.py:317-350` |
| M05 | `PreBroadcastValidator.validate` — `app/backend/arbicore/execution/pre_broadcast.py:120-137`; `build_controlled_live_safety.fresh_fn` — `app/backend/arbicore/runtime/composition.py:757-767`; `FlashLoanReceiver.receiveFlashLoan`, `FlashLoanReceiver.executeOperation` — `contracts/contracts/core/FlashLoanReceiver.sol:158-177`, `contracts/contracts/core/FlashLoanReceiver.sol:218-229` |
| M06 | `ExecutionReadinessEngine.can_transition` — `app/backend/arbicore/control/readiness.py:489-505`; `ExecutionModeRepo.transition` — `app/backend/arbicore/execution/mode.py:183-211`; `build_wizard_state` — `app/backend/arbicore/execution/operator_wizard.py:631-643`; `LiveSigner.sign_plan` — `app/backend/arbicore/execution/live_signer.py:222-233`; `WalletIntelligenceEngine._token_price_usd` — `app/backend/arbicore/capital/wallet_intelligence.py:128-133`; `_cookie_flags` — `app/backend/services/auth.py:85-90`; module-level CORS registration — `app/backend/server.py:6528-6534` |
| M07 | `v2_settings_vaults`, `v2_settings_vault_reconcile`, `v2_settings_exchanges`, `v2_settings_exchange_test` — `app/backend/server.py:3039-3052`, `app/backend/server.py:3070-3088` |

## 6A. All Low findings and static-maintenance observations

### L01 — Readiness calculations assign two unused gate variables

**Severity:** Low · **Priority:** P2 · **Class:** maintainability / misleading safety logic · **Confidence:** confirmed by static lint and source inspection.

**Evidence:** `assess_candidate_readiness`, `app/backend/arbicore/scanners/flash_loan_arbitrage/readiness_assessment.py:77-81`, assigns `executor_pass` and `balancer_pass` but never reads them. `_as_pass` in `app/backend/arbicore/execution/limited_live_eligibility.py:79-101` maps only explicit allow/deny words; other status words become unknown. The unused assignments can misleadingly suggest that they are the operative gate.

**Impact/boundary:** unnecessary ambiguity in code that should make denial semantics obvious. This finding does not establish an active bypass; the current readiness function uses other results for its final assessment.

**Required fix:** remove or deliberately integrate the redundant values only after documenting one canonical typed status contract. Do not change a fail-closed result simply to make a dead variable appear useful. No cleanup was performed.

### L02 — Three execution/operator locals are created but not consumed

**Severity:** Low · **Priority:** P2 · **Class:** maintenance / unfinished-path ambiguity · **Confidence:** confirmed statically.

| Exact location | Function/class | Evidence |
|---|---|---|
| `app/backend/arbicore/execution/discovery.py:283` | `ContinuousDiscovery._evaluate_candidate` | `canonical = CanonicalOpportunity(...)` is assigned but the local is never read |
| `app/backend/arbicore/execution/operator_journey.py:56` | `build_journey` | `prereq_by_key` is constructed but never read |
| `app/backend/arbicore/execution/pipeline.py:650` | `OpportunityPipeline._extract_quote` | `synth_hops` is constructed but never read |

**Impact/boundary:** dead local results make it difficult to tell whether intended canonical evidence, prerequisite mapping or synthetic quote data actually participates in the flow. The assignment alone does not prove that all canonical persistence is missing or that another correct path does not exist. Constructor side effects must be considered before removal.

**Required fix:** document and connect any intended consumer, or remove the unused calculation after confirming no necessary side effect. Keep synthetic quote behavior explicitly identified and outside financial certification.

### L03 — Complete unused-import inventory in the inspected execution/runtime subset

**Severity:** Low · **Priority:** P3 · **Class:** static maintenance / dependency clarity · **Confidence:** confirmed lint diagnostics, with explicit-export intent requiring human review.

The targeted inventory used the **audited Git source via standard input**, `ruff check` limited to `F401,F841`, and disabled its cache. It did not execute/import application code, install anything, fix files, or create application test files. Exact scope: `app/backend/arbicore/execution`, `app/backend/arbicore/runtime`, `app/backend/arbicore/chains`, and `app/backend/arbicore/scanners/flash_loan_arbitrage`. It produced **38 diagnostics: 33 F401 imports below, plus the 5 F841 locals in L01-L02**. This is not a whole-repository clean-lint claim, nor a runtime test pass.

All entries below are **module-level imports**, not methods. No items in this verified subset have been omitted for length.

| Exact path and line | Unused imported symbol (F401) |
|---|---|
| `app/backend/arbicore/execution/auto_executor.py:42` | `..data.journal.ExecutionStatus` |
| `app/backend/arbicore/execution/auto_executor.py:42` | `..data.journal.LearningLabel` |
| `app/backend/arbicore/execution/broadcast.py:28` | `dataclasses.field` |
| `app/backend/arbicore/execution/calldata.py:33` | `dataclasses.field` |
| `app/backend/arbicore/execution/calldata.py:34` | `datetime.datetime` |
| `app/backend/arbicore/execution/calldata.py:34` | `datetime.timezone` |
| `app/backend/arbicore/execution/calldata.py:35` | `typing.Tuple` |
| `app/backend/arbicore/execution/discovery.py:37` | `dataclasses.field` |
| `app/backend/arbicore/execution/gas.py:25` | `dataclasses.field` |
| `app/backend/arbicore/execution/mev.py:21` | `dataclasses.field` |
| `app/backend/arbicore/execution/operator_wizard.py:32` | `arbicore.execution.calldata.BALANCER_V2_VAULT_BY_CHAIN` |
| `app/backend/arbicore/execution/operator_wizard.py:33` | `arbicore.execution.calldata.UNISWAP_V3_ROUTER_BY_CHAIN` |
| `app/backend/arbicore/execution/operator_wizard.py:37` | `arbicore.execution.executor_interface.GETTER_VAULT_SIG` |
| `app/backend/arbicore/execution/operator_wizard.py:37` | `arbicore.execution.executor_interface.GETTER_ROUTER_SIG` |
| `app/backend/arbicore/execution/planner.py:23` | `datetime.datetime` |
| `app/backend/arbicore/execution/planner.py:23` | `datetime.timezone` |
| `app/backend/arbicore/execution/planner.py:31` | `.gas.StaticGasOracle` |
| `app/backend/arbicore/execution/planner.py:34` | `.simulation.SimulatorBackend` |
| `app/backend/arbicore/execution/quoter.py:53` | `dataclasses.field` |
| `app/backend/arbicore/execution/settlement_simulator.py:24` | `typing.Optional` |
| `app/backend/arbicore/execution/wallet_health.py:20` | `dataclasses.field` |
| `app/backend/arbicore/runtime/__init__.py:12` | `.composition.get_regime_classifier` — may be intended as a package export |
| `app/backend/arbicore/runtime/__init__.py:14` | `.composition.get_regime_worker` — may be intended as a package export |
| `app/backend/arbicore/runtime/__init__.py:16` | `.composition.get_sequence_miner` — may be intended as a package export |
| `app/backend/arbicore/runtime/__init__.py:18` | `.composition.get_survival_analytics` — may be intended as a package export |
| `app/backend/arbicore/scanners/flash_loan_arbitrage/filter.py:14` | `typing.Optional` |
| `app/backend/arbicore/scanners/flash_loan_arbitrage/provider_liquidity.py:27` | `dataclasses.field` |
| `app/backend/arbicore/scanners/flash_loan_arbitrage/route_search.py:21` | `dataclasses.field` |
| `app/backend/arbicore/scanners/flash_loan_arbitrage/route_search.py:22` | `typing.Tuple` |
| `app/backend/arbicore/scanners/flash_loan_arbitrage/scanner.py:14` | `typing.Awaitable` |
| `app/backend/arbicore/scanners/flash_loan_arbitrage/shadow_route.py:12` | `typing.Optional` |
| `app/backend/arbicore/scanners/flash_loan_arbitrage/verifier.py:15` | `...intelligence.roi_probability.ROIProbabilityEngine` |
| `app/backend/arbicore/scanners/flash_loan_arbitrage/verifier.py:18` | `...models.enums.MevRiskLevel` |

**Impact/boundary:** misleading dependencies, review noise and uncertain export intent. These diagnostics are not evidence of a trading failure or security compromise by themselves. Public re-exports may be intentional and must not be removed blindly.

**Required fix:** remove genuine dead imports; explicitly declare intentional package exports. Run a scoped static check after any separately authorized cleanup. Do not mix cosmetic cleanup into emergency financial-control repairs.

### L04 — Operator-provided diagnostic RPC needs an explicit network-access policy

**Severity:** Low, conditional hardening observation · **Priority:** P2/P3 · **Class:** privileged outbound-request surface · **Confidence:** input-to-request path confirmed; exploit not attempted.

**Evidence:** `v2_engine_run_atomic_sim`, `app/backend/server.py:5285-5304`, accepts `fork_rpc` and passes it to `_run_live_atomic_sim`. The latter uses the endpoint override at `app/backend/server.py:5131-5142`; `AtomicExecutorSimulator` sends JSON-RPC via its HTTP client. The route **does** require `_require_operator_dep`; this is distinct from H01's anonymous configuration mutation.

**Impact/boundary:** an authorized or compromised operator session can direct diagnostics toward an arbitrary reachable endpoint. Internal/private fork endpoints may be legitimate, so this is a policy/control requirement, not a claim that every private URL is an exploit. No metadata-service access, response exfiltration or unrestricted anonymous SSRF was demonstrated.

**Required fix:** define permitted schemes/destinations and private-network exceptions explicitly, reject credentials in URLs, enforce timeouts/response limits and an appropriate egress policy. Keep secrets out of errors and evidence. Preserve authenticated, clearly labeled read-only fork diagnostics.

## 7. Historical evidence reconciliation

| Artifact in target commit | What it records | What it does not prove |
|---|---|---|
| `deploy/executor_deployments.json` | Base mainnet success record at `0x0e3fdb0f0e615a517588bd44ac6c78bb7615927f`, deployment tx `0x39ce6224caffb17ee4fb846d2239157daa5a1af5ea5fcfdea0548f7020b336ff`, block 50991980; Base Sepolia also recorded | Fresh bytecode/owner/router/pool verification, source equivalence, current state or arbitrage execution/P&L |
| `reports/EXECUTOR_CAPABILITY_AUDIT.json` | 15 venue cells; 13 discoverable/quotable/route-constructable; 6 execution-capable; recorded flash support only Balancer | Artifact is stale relative to target source's Aave head and omits chain-specific deployment/adapter constraints. These are structural counts, not live passes |
| `reports/VPS_RUNTIME_CERT_public.json` | Historical public-RPC report: 62 probe rows, 56 quotable, 15 candidates, 0 economically valid, 0 execution-ready; all candidates negative gross at sampled sizes; Base skipped | Exact-commit/operator-authoritative runtime, positive-path certification, all-market profitability or current state |
| `reports/VPS_RUNTIME_CERT_public_phase5_harnessfix.json` | Historical public-RPC report: 45 rows, 40 quotable, 7 candidates, 0 economic/execution-ready; Base skipped; Anvil unavailable | Successful provider/economic/simulation stages; H09 means zero results are not solely a market issue |
| `scripts/arbicore_certify.py` implementation | `repo_capability_pass` covers selected compilation, protected integrity and safety settings; explicitly leaves P0-3 false and runtime unverified | Whole-app integration correctness, authorization coverage, deployment identity, exact route execution or profitability |

No historical pass count was rerun or accepted as proof for this commit. The handoff PRD was useful orientation but is stale in places, including receiver flash-provider support and broad “non-Base only needs RPC” claims. The initial report's 101 line-range references across 43 distinct files were resolved against the target Git snapshot. Export preparation adds precise symbol and Low-severity evidence, and the expanded report is reference-checked again before export. Targeted AST inspection additionally confirmed the throttle signature/call mismatch and the unprotected router/endpoint declarations, without executing application code.

## 8. Existing safeguards worth preserving

- Owner-gated receiver entrypoints and callback caller/provider checks; Aave initiator check; repayment enforcement.
- Unsupported swap venues are rejected by the settlement dispatcher; absent chain deployments stay denied.
- Complete-quote checks reject partial/fallback routes in canonical verification; missing route TVL yields a closed gate.
- Controlled broadcaster requires revalidation; missing fresh inputs are denied. Kill switch, strategy mode, capital, slippage, chain-ID preflight and explicit confirmation are separate barriers.
- The automatic pipeline defaults to `auto_confirm=False`; read-only tools do not enable live execution.
- Evidence stores preserve candidate/run attribution, and learning/certification components distinguish real from simulated provenance.

These strengths are real source features, **not** a global safety certification. H01-H10 show why safety must be assessed across the complete composed path rather than from selected safe modules.

## 8A. Detailed execution architecture assessment

### The real submission path

`LimitedLiveBroadcaster.broadcast_plan` in `app/backend/arbicore/execution/broadcast.py:422-778` is the financial boundary. It is not the same object as `LiveSigner.sign_plan`, whose receipt remains an unsigned preview. The server wires controlled-live safety rather than granting unconditional submission.

| Execution stage | Implemented source boundary | Current assessment |
|---|---|---|
| Plan / flash head encoding | `encode_plan_head_call`, `app/backend/arbicore/execution/calldata.py:532-632` | Balancer and Aave heads implemented. The function resolves an executor recipient; a missing one raises. It may fall back to empty callback data in exercise mode, which should not be treated as a valid arbitrage payload. |
| Venue/deployment compatibility | `evaluate_settlement`, `app/backend/arbicore/execution/settlement_dispatcher.py:165-278` | Unsupported current-receiver venues and missing deployment records are denied; adapter existence does not bypass this. |
| Kill switch and strategy mode | `LimitedLiveBroadcaster.broadcast_plan`, `app/backend/arbicore/execution/broadcast.py:422-479` | Independent guards exist, but the mode/config inputs need the authorization repairs in H01-H03. |
| Capital, secret and preflight eligibility | `LimitedLiveBroadcaster.broadcast_plan`, `app/backend/arbicore/execution/broadcast.py:480-707` | Several sequential constraints; source presence does not prove actual funding/key custody, endpoint integrity or policy adequacy. |
| Confirmation and revalidation | `LimitedLiveBroadcaster.broadcast_plan`, `app/backend/arbicore/execution/broadcast.py:708-778`; `build_controlled_live_safety.fresh_fn`, `app/backend/arbicore/runtime/composition.py:659-767` | Explicit confirmation and late validation exist. Exact-size and chain-composition defects remain. |
| Sign/send | `LimitedLiveBroadcaster.broadcast_plan`, `app/backend/arbicore/execution/broadcast.py:708-778` | Actual signing and RPC submission code is present; not invoked by this audit. Public RPC submission is not private MEV protection. |
| Contract callbacks | `FlashLoanReceiver.receiveFlashLoan`, `FlashLoanReceiver.executeOperation`, `contracts/contracts/core/FlashLoanReceiver.sol:135-229` | Owner-authorized entry/callback protocol and repayment constraints exist; one UniV3 router restricts venue coverage. |
| Post-trade evidence | Journal/outcome/evidence repositories and post-trade UI | Existing surfaces do not by themselves demonstrate durable transaction idempotency, nonce coordination, reorg handling, finality and reconciled realized net profit. These require explicit acceptance evidence. |

### Important execution boundaries

- **Detection versus spending:** background scanners, opportunity race, discovery tick and auto-executor scheduling must not be equated with authorized transaction broadcast. The default `auto_confirm=False` is material.
- **Borrow source versus swap venue:** Aave/Balancer callback support and UniV3 hop support are separate dimensions. Adding a flash-provider class cannot make a different swap ABI executable, and adding a swap quoter cannot add a receiver callback.
- **Source versus deployed code:** the source receiver has an Aave head, but the recorded Base deployment must be independently matched to exact bytecode and constructor inputs. This audit does not assert that every historical recorded deployment contains the target source's features.
- **On-chain solvency versus net profitability:** repayment of principal/premium is necessary, not sufficient. Gas and off-chain risk can make a solvent transaction economically negative. Quote and minimum-output protections must match the actual amount and route.
- **Continuous same-chain arbitrage versus cross-chain execution:** one EVM transaction cannot wait for an ordinary asynchronous bridge and repay a flash loan after destination finality. Cross-chain strategy requires separately designed inventory, funding and recovery.

## 8B. Security and authentication/authorization assessment

### Authentication implemented; authorization incomplete

`app/backend/services/auth.py` implements bcrypt password verification, JWT access/refresh tokens, cookie transport, session-version checks and lockout. `app/backend/routes/auth.py` provides the auth routes, and `app/frontend/src/context/AuthContext.jsx` maintains browser user state. These are real components. This audit did not test login, password recovery, session expiry, cookie delivery, vault decryption or deployed role provisioning.

The primary confirmed security issue is **not that authentication is entirely absent**. It is that sensitive routes fail to require it. `api_router` is created without a global authentication dependency at `app/backend/server.py:584`; selected handlers attach `_require_operator_dep`, others do not. A UI login page and CORS policy cannot protect direct backend requests.

### Exact mutation surface supporting H01-H03

All paths below are within the `/api` prefix. This is the concrete reviewed surface, not a claim that every route in the application has been exhaustively classified.

| Handler / exact source | Route family | Evidence / effect |
|---|---|---|
| `v2_settings_account_update` — `app/backend/server.py:3030-3036` | PATCH `/arbicore/settings/account` | Writes `_ACCOUNT_REPO.patch`, actor is literal `operator`; no handler operator dependency |
| `v2_settings_execution_update` — `app/backend/server.py:3061-3067` | PATCH `/arbicore/settings/execution` | Writes `_EXECUTION_SETTINGS.patch`; no operator dependency |
| `v2_execution_mode_transition` — `app/backend/server.py:3400-3413` | POST `/arbicore/execution/mode/{strategy}` | Client-controlled actor and transition target; H02 |
| `v2_discovery_tick`, `v2_discovery_start`, `v2_discovery_stop` — `app/backend/server.py:4160-4181` | POST `/arbicore/execution/discovery/{tick,start,stop}` | Calls worker methods without authentication |
| `v2_settings_network_draft`, `v2_settings_network_apply`, `v2_settings_network_rollback` — `app/backend/server.py:5879-5924` | Network configuration draft/apply/rollback | Persistent and process-environment execution inputs; H01 |
| `v2_settings_telegram_update`, `v2_settings_telegram_test`, `v2_settings_telegram_emit` — `app/backend/server.py:5960-6004` | Telegram update/test/manual alert | Changes notification settings and initiates sends; no operator dependency. No bot token was inspected. |
| `v2_settings_scanner_global_draft`, `v2_settings_scanner_global_apply` — `app/backend/server.py:6037-6058` | Scanner global draft/apply | Writes/applies scanner settings with non-authenticated actor attribution |
| `v2_settings_scanner_family_draft`, `v2_settings_scanner_family_apply` — `app/backend/server.py:6103-6128` | Scanner family draft/apply | Same pattern at per-family scope |
| `v2_settings_scanner_pause`, `v2_settings_scanner_resume`, `v2_settings_scanner_reload` — `app/backend/server.py:6159-6186` | Scanner operational control | Direct operational state changes without operator dependency |
| `v2_ledger_emit` — `app/backend/server.py:6309-6319` | POST `/arbicore/learning/ledger/emit` | Triggers journal-to-learning consumption; authorization absent at handler |
| `v2_pipeline_evaluate` — `app/backend/server.py:6332-6354` | POST `/arbicore/pipeline/evaluate` | Accepts evaluation input and runs pipeline work without operator dependency |
| `v2_autoexec_start`, `v2_autoexec_stop`, `v2_autoexec_tick` — `app/backend/server.py:6371-6386` | Auto-executor scheduling/control | Starts/stops/ticks worker without authentication; automatic confirmation remains off |

Validation/rollback and notification/operational settings handlers in these same families must be included in the eventual deny-by-default authorization inventory, not repaired piecemeal. The mocked reconcile and exchange-test handlers in M07 are misleading responses, not evidence that genuine custody reconciliation or exchange tests can be performed anonymously.

### Protected/limiting controls and remaining uncertainty

- Operator dependency is explicitly present on signer ingestion/deletion (`app/backend/server.py:4995-5024`) and the atomic-simulation endpoint (`app/backend/server.py:5285-5304`), as well as selected discovery actions. The review did not claim every endpoint is anonymous.
- The security review found role/confirmation barriers around direct broadcast and kill-switch operations. H01-H03 therefore describe unauthorized **control-state/input mutation**, not a reproduced direct signing bypass.
- Owner/provider callback checks constrain the contract. They do not authenticate HTTP settings or validate off-chain market data.
- Cookie security is configuration-dependent (`_cookie_flags`), and credentialed wildcard CORS is an inappropriate default boundary; no specific browser exploit was tested (M06).
- Operator-configured diagnostic RPCs require a considered egress policy (L04). No generalized secret-exfiltration proof is claimed.
- Secret custody, encryption-key strength, production network ACLs, account permissions and incident controls remain unverified. No secret inventory or value scan was performed.

## 8C. RPC assessment

The code has real RPC functionality, retries, rate-limit handling, fallbacks, quote cache and chain-identity-aware components. Its weakness is **inconsistent use across consumers**.

1. **Configuration is not connectivity.** `build_multichain_readiness_report` in `app/backend/arbicore/runtime/multichain_readiness.py` differentiates structural readiness and required runtime proof. Actual URLs/keys were not inspected; this audit does not certify any chain as configured or reachable.
2. **Discovery and economics have different config contracts.** `_cell_state` distinguishes `rpc_explicitly_configured` from `provider_registry_rpc_configured` (`app/backend/arbicore/discovery/opportunity_engine.py:144-148`). A URL used by one component may not provision the other.
3. **Persistent resolver hardening is not universal.** `QuoterRegistry` maintains its own endpoint precedence and can leak global Base RPC into non-Base requests (H06). Chain identity must be validated before quote use, not only before transaction submission.
4. **Throttle API drift breaks consumers.** `_throttle(scope)` changed while two call sites still invoke it without a parameter (H04). This is a deterministic interface failure, not a rate-limit diagnosis.
5. **Fresh block height is not coherent state.** `_single_call` can collect block height separately from the quote; cached/unpinned hops need block/hash binding (M05). Merely including a block number in a report does not prove that all route facts came from that state.
6. **Endpoint trust remains a security boundary.** RPCs can influence quotes, contract getters, balances, gas and preflight results. H01 permits unauthorized endpoint changes; L04 covers authorized diagnostics. Logs/evidence must avoid leaking credentials embedded in URLs.

Relevant exact functions: `QuoterRegistry._rpc_url_candidates`, `_rpc_url`, `quote_route`, `_single_call`, `_eth_call`, `_throttle_scope`, `_throttle` in `app/backend/arbicore/execution/quoter.py`; `make_eth_call_for_chain_from_env` in `app/backend/arbicore/searcher/runtime.py`; `EvmChainAdapter.capability` in `app/backend/arbicore/chains/evm_adapter.py`. Source-level failover exists; no live provider outage or failover experiment was run.

## 8D. Economic and trading-correctness assessment

### Inputs that must refer to the same exact candidate

The economic object should bind chain, provider, input token/decimals, token-unit amount, USD conversion, ordered venues/pools/hops, fee tiers, output quotes, minimum outputs, block/hash and expiry. The current probe/notional mismatch (H05) violates that binding before the final dollar-profit comparison. A generic percent edge, token TVL or nominal flash notional cannot repair it.

### Findings by economic layer

| Layer | Current source behavior | Consequence / finding |
|---|---|---|
| Input sizing | `_plan_base` uses a probe; verifier and final safety multiply percentage return by a separately selected USD size | H05: nonlinear price impact not represented at execution size |
| Size search | `_size_sweep` chooses gross-profit best; later net evaluation still references the original amount | M04: neither net-optimal nor coherently propagated |
| Borrow capacity | Provider optimizer requires liquidity; multichain caller supplies `None` | H09: positive economic certification cannot complete |
| DEX depth | Base TVL provider installed for canonical multichain verification; token-balance TVL differs from active V3 depth | H07/M03: non-Base composition and execution-depth proof missing |
| Premium | Aave reader default 5 bps; configurable gas flash-fee term can coexist with provider premium deduction | M03: unmeasured fee assumption / conditional double counting |
| Gas and data | Chain-aware models exist, but canonical estimates and configurable calldata-size assumptions coexist with actual estimation paths | M03: model estimate must not be presented as exact all-in cost |
| USD prices | Stable/derivative assumptions appear in harness and wallet reporting | M03/M04/M06: nominal units are not measured dollar value |
| MEV and expiry | Metadata-only MEV router, public submission, optional deadline and height-only freshness | M05/M06: slippage/repayment alone do not guarantee intended net outcome |
| Post-trade learning | Evidence/outcome framework exists; research outcomes differ from realized account P&L | P2: calibrate against reconciled receipts and costs before profitability claims |

**Positive accounting property:** quote-return amounts already reflect pool trading fees in the paths designed that way; do not blindly deduct DEX fees twice when revising cost logic. Conversely, flash premiums, transaction gas/L1 costs, revert risk and bridge/CEX costs where applicable require explicit ownership. The report does not claim that every path currently double-counts fees; M03's flash-fee issue is conditional on the relevant nonzero configuration term.

**Market conclusion:** the historical samples recorded no economic winner. That does not establish universal absence of profit. Equally, an assumed positive edge or a high confidence score cannot override missing exact-size market/liquidity/economic evidence.

## 8E. Certification/readiness assessment and FALSE READINESS register

The newer opportunity matrix is careful to leave runtime states unverified and limited-live false. The problem is that **other component labels and reports still admit broader interpretations**, and the canonical path is narrower than raw adapter registries.

| ID / apparent readiness | Actual supporting evidence | What is falsely inferred | Finding / correct classification |
|---|---|---|---|
| FR01 — “RPC configured” | Environment-key presence | Correct chain, healthy endpoint, valid market/economic data | H06 / RPC configured only; runtime UNKNOWN |
| FR02 — “quote path connected” | Resolver flag plus quote-backend membership, repeated across strategy labels | Every strategy reaches canonical quoting/execution | H07, M02 / structural component support, not complete integration |
| FR03 — “execution capable” six-cell count | UniV3 adapter/DEX membership | Six deployed, adapter-compatible execution engines | H08, M02 / chain/deployment/receiver constraints missing |
| FR04 — “executor deployed” / identity READY | Registry/env address and sometimes incomplete getter observations | Correct deployed bytecode and all immutables verified | H10 / known record or UNKNOWN identity; not READY on missing evidence |
| FR05 — “Aave supported” | Catalog, liquidity helper and receiver head | Final canonical M3 accepts Aave, including BNB | H07/H08 / partial implementation; M3 Balancer-only and BNB adapter mismatch |
| FR06 — “profitable” / profit buffer PASS | Probe return percentage multiplied by another USD size | Exact transaction is net profitable | H05 / mismatched modeled economics |
| FR07 — “simulation PASS” | Noop/heuristic or RPC capability result | Exact deployed-state candidate was simulated | H04, M01 / MOCKED/HEURISTIC or capability-only evidence |
| FR08 — “Anvil available” | Binary/process/capability check | Positive candidate simulation completed | H09, M01 / infrastructure only |
| FR09 — “repo capability PASS” | Selected compilation, integrity and safety configuration | Whole-app runtime/production certification | Historical evidence section / static repository check only |
| FR10 — “ready to broadcast” wizard | Component aggregation excluding certification WAIT | Candidate-specific economic/simulation approval complete | M06 / prerequisites only, not eligibility |
| FR11 — “signing eligible” receipt | `LiveSigner` unsigned placeholders | Signed transaction or broadcast capability proof | M06 / preview; distinguish actual `LimitedLiveBroadcaster` |
| FR12 — “private/MEV routing” | Routing decision metadata | Private submission/inclusion protection | M06 / metadata only |
| FR13 — “vault READY / reconciled now” | Literal placeholder objects / timestamp echo | Verified custody, signers, balances or reconciliation | M07 / **MOCKED** |
| FR14 — “exchange CONNECTED / 62 ms test” | Literal statuses; `key != "gate-io"` | Valid credentials, permissions and actual exchange request | M07 / **MOCKED** |
| FR15 — “real learning outcomes” | Post-emission market/state observation | Realized live arbitrage net returns | P2 / distinguish research labels from receipt-reconciled P&L |

This register covers false-readiness **claims or interpretations**, not assertions that every corresponding frontend label is malicious or every handler broadcasts unsafely. Some modules already label their own limitations correctly. The remedy is consistent evidence semantics throughout the application.

### High-finding symbol index

| Finding | Principal exact symbols (paths/ranges appear in each finding) |
|---|---|
| H01 | `v2_settings_network_draft`, `v2_settings_network_apply`, `v2_settings_network_rollback` (`app/backend/server.py`); environment sync module (`app/backend/arbicore/config/env_sync.py`); `LimitedLiveBroadcaster._rpc_url` (`app/backend/arbicore/execution/broadcast.py`) |
| H02 | `v2_execution_mode_transition`; `ExecutionModeRepo.transition`; `LimitedLiveBroadcaster.broadcast_plan`; `ExecutionReadinessEngine.can_transition` |
| H03 | `v2_pipeline_evaluate`; `v2_autoexec_start`, `v2_autoexec_stop`, `v2_autoexec_tick`; additional exact mutation handlers listed in section 8B |
| H04 | `_throttle`; `AtomicExecutorSimulator._raw_eth_call`; `WalletIntelligenceEngine._eth_call` |
| H05 | `_plan_base`, `make_live_quote_provider._provider`; `FlashLoanOpportunityVerifier.verify`; `FlashLoanEconomicsAssessor.assess`; `build_controlled_live_safety.fresh_fn` |
| H06 | `QuoterRegistry._rpc_url_candidates`, `QuoterRegistry._rpc_url`, `QuoterRegistry.quote_route`; `_single_call` |
| H07 | `_plan_generic_evm`; `_wire_canonical_flash_loan_scanner`; `build_base_tvl_provider`; Base V3 reserve-reader closure; `_IN_SCOPE_CHAINS`; `build_controlled_live_safety._flashloan_available`, `build_controlled_live_safety.fresh_fn` |
| H08 | `FlashLoanReceiver.receiveFlashLoan`, `FlashLoanReceiver.executeOperation`; `evaluate_settlement`; `AaveV3FlashLoanAdapter`, `UniswapV3SwapAdapter`; deployment registry document |
| H09 | `_evaluate_candidates`; `compute_true_net_profit`; provider optimizer; `_certify_chain` |
| H10 | `inspect_executor`; `probe_executor_identity`; `resolve_executor_address`; independent `probe_signer_readiness` boundary |

---

# Phase B — FORWARD ENGINEERING / UPGRADE ASSESSMENT

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

## 9A. Recommended safe engineering sequence

**This is a proposed sequence, not execution instructions or approval. No step below was performed.** The user must separately authorize any future repository changes, tests, runtime checks, contract work or live actions. Preserve all six chains and all specified strategy/venue requirements throughout.

| Step | Work and dependency | Exit criterion before progressing |
|---|---|---|
| 0 — Evidence handoff | Preserve exact audited commit/tree, report and open findings; record a separate authorized change baseline | Scope and acceptance criteria agreed; no accidental remediation mixed into audit/export |
| 1 — Close unauthorized control paths | P0 H01-H03 before relying on runtime inputs/modes; review all mutating routes together | Deny-by-default role enforcement; authenticated actor attribution; unauthorized cases denied without side effects |
| 2 — Unify chain/RPC and configuration identity | H06 plus H01 dependent-state invalidation; one per-chain resolver and immutable config revision | Wrong-chain endpoints rejected before evidence use; no global Base leakage; caches bound to verified identity |
| 3 — Repair hard interface failures | H04 using isolated, deterministic RPC substitutes first | Atomic/wallet consumers follow common RPC contract; malformed/timeout/429/error conditions remain explicit and safe |
| 4 — Bind amounts and economics | H05 and M03-M05; one exact-size candidate representation across consumers | Independently recomputable route, token amount, fee, gas and net; selected size propagated; expiry mandatory |
| 5 — Make all readiness states truthful | H10, M01/M02/M06/M07; remove implicit promotion of mocked/config-only evidence | Missing mandatory evidence never READY; MOCKED/HEURISTIC visibly separated; all matrices agree on stage semantics |
| 6 — Complete six-chain canonical composition | H07/H09 after shared invariants; parallel chain-specific implementation is appropriate | Each chain's actual scanner and final validator share quote, liquidity, provider, gas and evidence services; no allowlist-only activation |
| 7 — Complete/version receiver compatibility | H08 with independently reviewed contract/ABI design before any deployment decision | Exact flash heads and swap ABIs covered; callback/approval/repayment/min-output/min-profit/expiry constraints assessed; chain deployment plan explicit |
| 8 — Certify deterministic and fork behavior | Separately authorized offline/unit/contract tests, then isolated fork tests of exact candidates | Reproducible caller/calldata/block/evidence; no synthetic result admitted as deployed-state proof; negative cases covered |
| 9 — Read-only operator-environment proof | Separately authorized RPC/bytecode/market/evidence checks on **all six chains**, no signer enabling | Verified chain/deployment/immutables, fresh liquidity/quotes, real costs, exact-call success and persisted evidence for each candidate |
| 10 — Production operating controls | P2 idempotency, nonce/finality/P&L, backups, alerts, stop/recovery and egress controls | Durable restart/reorg/revert handling, measured risk limits, coherent operator authorization and reconciled outcomes |
| 11 — Separate promotion decision | No automatic promotion from this audit, a green dashboard or test pass | Explicit user/operator authorization, bounded policy and independent review; any live transaction belongs to a new task |
| 12 — Evidence-led expansion/optimization | P2/P3 wider strategies/providers/universe after safe baseline | Measured, held-out outcome improvement; no scope removed to manufacture a green matrix |

**Do not invert this order:** do not fund/enable a signer to debug a quoter; do not broaden supported-chain lists before wiring chain-valid liquidity/execution; do not disable provider/TVL/simulation checks to obtain a profitable candidate; do not install Anvil and assume H09 is fixed; do not deploy a receiver before its exact compatibility and security requirements are reviewed.

### Finding-to-priority index

| Priority | Findings / required work |
|---|---|
| **P0** | H01-H06 and H10; mandatory evidence/expiry and security-dependent portions of M01/M05/M06 |
| **P1** | H07-H09; M01-M05 and M07; candidate/chain/provider composition, receiver engineering, exact certification and coherent readiness |
| **P2** | M06 operational convergence, L01-L02, L04 policy hardening; transaction lifecycle/P&L/recovery; broader strategy execution |
| **P3** | L03 maintenance, low-risk L04 polish after policy exists; measured search/ranking/calibration/provider expansion |

Severity and priority are intentionally not identical. A Low unused import should not consume emergency security credits, and a High six-chain capability gap must remain on the roadmap even when a Base-only path is nearer completion.

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

**Phase A complete:** fixed-commit source review; whole-app, execution, security, authentication/authorization, RPC, economics and certification assessments; six-chain, venue, strategy and flash-provider matrices; explicit false-readiness register; historical-evidence reconciliation; **0 confirmed Critical, 10 High, 7 Medium groups and 4 Low groups**, with all 38 scoped static-maintenance diagnostics enumerated.

**Phase B complete:** P0/P1/P2/P3 roadmap and per-chain acceptance evidence without narrowing the six-chain target.

**Not performed:** application tests, runtime probes, live simulation, source/configuration fixes, signer enabling, transaction broadcast, deployment, commits, merges or PRs. No profitable execution or production readiness is claimed.

**Suggested product improvement:** an evidence-linked capability dashboard showing, for every chain/venue/strategy, the exact last completed gate, first blocker and evidence age would make false readiness much harder to introduce or misunderstand.

### Standalone export

- Requested complete report: `/app/audit_report.md`.
- Identical downloadable Markdown artifact outside the repository: `/mnt/data/audit_report.md`.
- Both phases and all findings are in this single document; no external appendix, application account, repository checkout or network access is needed to read it.
- Source paths and line ranges refer to the audited commit, not the current worktree. The exported file is checked for byte-for-byte equality with the requested report.
- No Git add/commit/push, PR, merge, deployment, source/configuration edit or remediation was performed as part of preparing this export.

**STOP — report delivered; no fixes implemented.**