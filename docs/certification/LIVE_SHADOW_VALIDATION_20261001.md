# Live SHADOW Validation Report — bound to extract-port tip

- Status: **EVIDENCE COMPLETE** (no profitable opportunity claimed)
- Certified tip: `861af4d60e841ac8abac5891d663e23986c356ad`
- Tag: `arbicore-extract-port-pass-20261001`
- Validation finished (UTC): see `reports/shadow_validation/live_shadow_latest.json` → `finished_at`
- Code change for GENERIC_DEX scanner wiring: **NONE**
- Production deploy / signing / broadcast / live trading: **NONE**
- Execution posture observed: SHADOW (read-only RPC)

Harness: `scripts/live_shadow_validation.py` (external; does not modify certified modules).  
Raw JSON: `reports/shadow_validation/live_shadow_latest.json`

---

## Phase 1 — Architecture reconciliation (inspect-only)

Full write-up: `docs/certification/SHADOW_VALIDATION_ARCHITECTURE_RECONCILIATION_20261001.md`

| Question | Answer |
|---|---|
| Canonical discovery pipeline | `FlashLoanArbitrageScanner` → `RouteSearchEngine` → live `QuoterRegistry` → verifier → Gate 7/8/9 ($25) → `EmissionBus` |
| Parallel pipeline | `OpportunityEngine` / `scan-once` (Base `base_venues`; not EmissionBus) |
| GENERIC_DEX connect point | Library today; future smallest wire = DiscoverySource → existing verifier/emit (not a 7th emit site) |
| Balancer surface | Already on canonical `QuoterRegistry` via `BalancerV2Quoter` |
| Integration required for this evidence? | **No** — drive certified `GenericDexRouteEngine` + Balancer modules with live RPCs |

---

## Phase 2 — Balancer live read-only

Production Alchemy endpoints were **429 rate-limited** during validation. Harness used public read-only RPCs (hosts redacted in JSON). Fail-closed behavior preserved.

### P1 — subgraph enumeration

All five Balancer chains returned **`discovery_unavailable`** with explicit missing-URL errors (`ARBICORE_BALANCER_SUBGRAPH_URL_<CHAIN>`). Correct fail-closed posture when config absent.

### P1b — on-chain `PoolRegistered` (`eth_getLogs`)

| Chain | Status | Candidates (window) | Notes |
|---|---|---|---|
| ethereum | ok | 5 | Real poolId/address samples returned |
| arbitrum | ok | 1 | Real candidate |
| optimism | ok | 0 | Honest empty window |
| base | discovery_unavailable / ok (run-dependent) | 0 | RPC/range sensitivity |
| polygon | discovery_unavailable | 0 | getLogs transport errors on public endpoint |

### P0 — discovery + quote

| Proof | Result |
|---|---|
| Ethereum known 80BAL-20WETH pool | **`ok`** — `amount_out_wei=19918655339573085611` for `1e15` WETH in; fee 100 bps; block recorded |
| Same via `QuoterRegistry` / `BalancerV2Quoter` | **`ok`** / hop `ok` (identical out) |
| Arbitrum P1b candidate → P0 retry on pool tokens | **`ok`** — live `queryBatchSwap` succeeded |
| P1b candidates vs WETH/USDC | `token_not_in_pool` (fail-closed; expected) then retry on actual pool tokens |

---

## Phase 3 — GENERIC_DEX live SHADOW

- Scanner/`composition.py` wiring: **not required** for evidence; **not performed**
- Engine: certified `GenericDexRouteEngine` + live `QuoterRegistry`
- Floor: `$25` Gate 7 unchanged
- Synthetic profitable quotes: **not injected**

Real round-trip quotes with economics observed on **ethereum, arbitrum, base, optimism, bnb** (polygon mostly quote-failed on probed UniV3 fee pairs under this run’s RPC/pool resolution).

---

## Phase 4 — Economic evidence (GENERIC_DEX live evaluations)

From `live_shadow_latest.json` economic rollup:

| Bucket | Count | Meaning |
|---|---|---|
| **A** Real profitable (Gate 7 pass) | **0** | No live eligible profitable opportunity |
| **B** Real but economically rejected | **12** | Both legs quoted; net ≤ 0 or below floor |
| **C** Quote failures | **14** | leg1/leg2 fail-closed |
| **D** Liquidity failures | **0** | — |
| **E** Gas failures | **6** | `unknown_gas` / L1 oracle deny |
| **F** RPC/data failures | **0** | (bucket used for price/decimals; RPC often surfaced as C) |
| **G** Unsupported routes | **0** | — |

Examples (B — real quotes, Gate 7 correctly held):

- Base / Optimism / Ethereum / Arbitrum: UniV3 fee-tier cross routes with `leg1_status=ok`, `leg2_status=ok`, negative net (~−$1.3 to −$2.3 on $200 USDC notional), `gate7_pass=false`
- BNB: quotes succeeded but gas USD from public RPC/native pricing was pathological (billions) → still rejected (fail-closed; do not treat as profitable)

**Verdict:** System is **not** profitable on this SHADOW sample. Unit-test greens are excluded from this claim.

---

## Phase 5 — Checkpoint

- Certified modules: **unchanged** at `861af4d`
- Integration commit: **none**
- New PASS tag: **none** (no profitable SHADOW certification; evidence only)
- This report + JSON are the durable binding to `861af4d` / `arbicore-extract-port-pass-20261001`

### Residual (still not implemented)

1. Alchemy operator RPC rate-limit / capacity for continuous six-chain SHADOW
2. Balancer subgraph URL configuration (P1) when enumeration via subgraph is desired
3. GENERIC_DEX → canonical scanner DiscoverySource / EmissionBus wiring
4. Broader venue/pool universe + longer Balancer log windows
5. BNB gas/native-price seam quality under public RPC
6. Dual OpportunityEngine vs canonical scanner reconciliation (architecture only)

---

## STOP

No paper execution. No live trading. No production deploy. Awaiting explicit review/approval before any next phase.
