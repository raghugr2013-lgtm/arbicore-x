# Architecture Reconciliation — Live SHADOW Validation Prep

- Status: **INSPECT-ONLY** (no implementation in this document)
- Certified tip: `861af4d60e841ac8abac5891d663e23986c356ad`
- Tag: `arbicore-extract-port-pass-20261001`
- Date: 2026-10-01

## 1. Canonical scanner pipeline

**Owner:** `FlashLoanArbitrageScanner`
(`app/backend/arbicore/scanners/flash_loan_arbitrage/scanner.py`)

**Wiring:** `runtime/composition.py` —
`get_flash_loan_arb_scanner()`, `_wire_canonical_flash_loan_scanner()`,
`activate_canonical_flash_loan_scanner()`,
`run_single_canonical_flash_loan_audit_tick()`.

**Flow:**

1. Discovery sources (`sources.py` via `RouteSearchEngine.search`)
   → `DiscoveryCandidate` into `DiscoveryQueue`
2. Claim → `FlashLoanOpportunityVerifier` (`verifier.py`)
3. Live quotes via `live_quote_provider.make_live_quote_provider` /
   `make_multichain_quote_provider` → shared `QuoterRegistry`
4. Economics: `FlashLoanEconomicsAssessor.aggregate_economics`
5. Gates: Gate 7 (`filter.FlashLoanGate7AtomicProfit`, default **$25**),
   Gate 8 liquidity, Gate 9 MEV
6. Emission: sole INV-2 site `FlashLoanArbitrageScanner._tick` → `EmissionBus`

**Boot posture:** detection can be enabled; non-Base chains dormant by default
(H06). Execution remains mode-ladder gated (SHADOW).

## 2. OpportunityEngine / scan-once pipeline

**Owner:** `OpportunityEngine`
(`app/backend/arbicore/economics/opportunity_engine.py`)

**API surface:** `/api/arbicore/engine/scan-once` (and related engine routes).

**Flow:**

1. `RouteSearchEngine` over **Base-frozen** `base_venues.build_pool_graph`
2. `QuoterRegistry` quotes
3. `quote_provider.build_opportunity_from_route`
4. `opportunity_decision.decide_opportunity` (net_profit / confidence / EV /
   size / optional atomic sim)

**Not** an EmissionBus call site. Parallel research/API orchestrator.
Composition comments mark `base_venues` as regression-frozen for this engine
while the canonical scanner uses `base_pool_registry` / multichain graphs.

## 3. RouteSearchEngine

**Owner:** `RouteSearchEngine`
(`app/backend/arbicore/scanners/flash_loan_arbitrage/route_search.py`)

Pure DFS cycle enumeration over `PoolNode` graphs. Shared substrate used by:

- Canonical `FlashLoanArbitrageScanner` sources
- `OpportunityEngine` (Base venue graph)

No quotes, no economics, no emission.

## 4. Triangular path

**Owner:** `discover_triangular` / `discover_triangular_multi`
(`scanners/flash_loan_arbitrage/triangular.py`)

Library emit helper with default `min_net_profit_usd=35.0`. Callers today:
self + unit tests only. **Not wired** into composition / scanner boot /
EmissionBus.

## 5. GENERIC_DEX path

**Owner:** `GenericDexRouteEngine`
(`scanners/generic_dex_route_engine.py`)

Library-only 2-venue exact-size evaluator. Reuses:

- `QuoterRegistry` (incl. BalancerV2Quoter)
- `FlashLoanEconomicsAssessor` + `$25` floor (`MIN_ATOMIC_PROFIT_USD`)
- chain gas model

**Not** imported by `composition.py`. No discovery source. No EmissionBus.

## 6. Balancer path

| Layer | Module | Role |
|---|---|---|
| P0 | `discovery/balancer_v2_pool_discovery.py` + `BalancerV2Quoter` in `execution/quoter.py` | Identity → on-chain metadata → `queryBatchSwap` |
| P1 | `discovery/balancer_v2_pool_enumeration.py` | Candidate source → P0 re-validate → quote |
| P1b | `discovery/balancer_v2_onchain_source.py` | `PoolRegistered` via `eth_getLogs` (injected fetcher) |

Balancer quotes already feed the **same** `QuoterRegistry` surface used by
canonical live quote provider and GENERIC_DEX. No second quote path.

---

## Answers (reconciliation decisions — not yet implemented)

### Which pipeline is canonical for opportunity discovery?

**`FlashLoanArbitrageScanner` + `RouteSearchEngine` + verifier + Gate 7/8/9 +
EmissionBus.** This is the sole authorised FLASH_LOAN_ARBITRAGE emit site.

### Which components are duplicated?

| Surface | Canonical | Parallel / library |
|---|---|---|
| Cycle search | `RouteSearchEngine` (shared) | — |
| Pool universe | `base_pool_registry` / `multichain_venues` | `base_venues` (OpportunityEngine only) |
| Quotes | `QuoterRegistry` (shared) | — |
| Economics | `FlashLoanEconomicsAssessor` + Gates | `OpportunityEngine` / `compute_net_profit` decision chain |
| Triangular | — | `discover_triangular` ($35 library default, unwired) |
| GENERIC_DEX | — | `GenericDexRouteEngine` (library, $25) |

### Which path should own opportunity discovery?

Canonical scanner. OpportunityEngine remains API/research. Triangular and
GENERIC_DEX should **feed** the canonical verifier/EmissionBus if/when
integrated — not become a second emit site.

### Quotes → gas → economics → Gate 7 → emission (canonical)

```
RouteSearchEngine cycles
  → DiscoveryCandidate
  → live_quote_provider (QuoterRegistry hops, TVL)
  → FlashLoanOpportunityVerifier
       → FlashLoanEconomicsAssessor
       → Gate7 ($25) / Gate8 / Gate9
  → EmissionBus (scanner._tick only)
```

### Where should GENERIC_DEX connect (smallest surgical point)?

**Preferred (future, not this phase unless required):** add a
`DiscoverySource` that yields GENERIC_DEX-shaped candidates (or evaluate
route pairs and map to `DiscoveryCandidate`), then reuse the existing
verifier + EmissionBus path. Do **not** add a seventh emit site.

**For live SHADOW evidence now:** drive `GenericDexRouteEngine` as a
library against live `QuoterRegistry` + real price/gas — no composition
change required. Scanner EmissionBus wiring remains a residual.

### Should Balancer feed the same canonical quote/economic surface?

**Yes.** Already does via `BalancerV2Quoter` in `QuoterRegistry.default_backends`.
Canonical hops with `dex=balancer_v2` + explicit `pool_id`/`pool_address`
use P0. Enumeration (P1/P1b) should only supply identities into that same
surface.

### $25 vs $35

- Gate 7 / filter / searcher / GENERIC_DEX: **$25** (runtime)
- Triangular library emit default: **$35** (unwired)
- `reports/READINESS_MATRIX_2026-06.md`: documents $35 → documentation drift

---

## Live-validation posture (this phase)

- Read-only RPC (`eth_call` / `eth_getLogs`) only
- No signing, broadcast, production deploy, or mode promotion
- Certified modules unmodified; harness is external evidence
- Preserve report against `861af4d` if no integration commit is required
