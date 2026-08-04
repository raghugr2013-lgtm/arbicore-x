# ArbiCore X v2.6.0 — Stage 3 · Operational Intelligence + Stage 4 · Flash-Loan Operator Prep

**Release date:** 2026-08-04
**Stages:** 3 (Operational Intelligence) + 4 (Flash-Loan Operator Preparation)
**Mode:** OBSERVE / PAPER · Kill switch ENGAGED by default · Live execution DISABLED

---

## Summary

One coordinated milestone that (a) turns the OpsCenter into a real live
dashboard, (b) adds cross-venue scanners, (c) replaces gross-spread
math with a proper net-profit engine that accounts for every real cost,
(d) ships the read-only Validation Framework, and (e) delivers the
complete Flash-Loan Operator Journey as dry-run.

Every safety invariant is preserved. No signing. No broadcasts. Kill
switch remains engaged on every boot.

## What ships

### Stage 3 — Operational Intelligence

- **Live Ops Center UI** (`/dashboard`) — one page, 6-second polling, renders
  every live subsystem: KPI row (providers/scanners/quotes/safety/MID),
  cross-venue price snapshot, opportunity stream, scanner ranking,
  provider health by kind, venue ranking, safety posture, cross-scanner
  detail. Zero placeholder values. Every number comes from v2.5+ APIs.
- **Net-profit engine** (`arbicore.economics.net_profit`) — single pure
  function `compute_net_profit()` that turns a gross spread into a full
  cost-decomposed net-profit result: trading fees, withdrawal fees, gas
  cost (base × units × native price), slippage, liquidity impact, flash
  loan fees. Every downstream consumer (LiveMarketScanner, CexDex,
  DexDex, Paper Engine) uses this exact function.
- **Cross-venue scanners** —
  - `CexDexScanner` (`live_cex_dex`): Uniswap V3 WETH/USDC quote vs. live
    CEX ETH/USDT ticker.
  - `DexDexScanner` (`live_dex_dex`): Uniswap V3 vs. SushiSwap V2 WETH/USDC.
  Both reuse `ScannerEvidenceBridge` and `ProviderRegistry` — no parallel
  implementations.
- **Validation framework** (`arbicore.validation`) — read-only reporter over
  MID exposing 7 endpoints:
  `/api/arbicore/validation/{summary,recurrence,calibration,venue_ranking,regime}`.
  Produces: opportunity recurrence, confidence calibration bins, venue
  ranking, scanner ranking, provider ranking, regime analysis, execution
  probability distribution, historical counters, one automated summary
  payload.

### Stage 4 — Flash-Loan Operator Journey (dry-run)

- **`arbicore.flashloan.FlashLoanOperatorJourney`** — one class, 10 phases,
  end-to-end journey:
  1. qualify (unprofitable → aborts here)
  2. build_route (4-hop flash-loan atomic)
  3. estimate_capital (respects safety `CapitalAllocationPolicy` clip)
  4. simulate_flash_loan (fee-only dry-run)
  5. build_transactions (dry-run, calldata not written)
  6. plan_execution
  7. validate_safety — always emits `signing_allowed=False`,
     `broadcast_allowed=False`
  8. request_approval (via existing advisory `ApprovalGate`)
  9. build_rollback (atomic-revert plan)
  10. record_audit_evidence (writes `flashloan.operator.journey.evidence`
      to MID via `write_opportunity_event`)
- **Endpoints:**
  - `GET  /api/arbicore/flashloan/journey/status` — always reports `ready_for_signing=false, ready_for_broadcast=false`
  - `POST /api/arbicore/flashloan/journey/run` (admin/operator) — runs the full journey against a caller-supplied opportunity payload

### Backend endpoints added

| Endpoint | Purpose |
|---|---|
| `GET /api/arbicore/scanners/cross/status` | Cross scanner runtime + stats |
| `GET /api/arbicore/validation/summary` | One-shot validation payload |
| `GET /api/arbicore/validation/recurrence` | Opportunity recurrence |
| `GET /api/arbicore/validation/calibration` | Confidence calibration buckets |
| `GET /api/arbicore/validation/venue_ranking` | Live venue ranking |
| `GET /api/arbicore/validation/regime` | Regime distribution |
| `GET /api/arbicore/flashloan/journey/status` | Journey availability + safety statement |
| `POST /api/arbicore/flashloan/journey/run` | Dry-run journey (admin/operator) |

## Live evidence (this build)

- **Ops Center** shows 47 providers (all HEALTHY), 3/3 scanners running,
  128 live quotes collected, 32 opportunities emitted, kill switch ENGAGED.
- **Live prices** (real): BTC $63,769 (OKX) - $63,701 (Coinbase) = 11.53 bps.
  ETH $1,868 (OKX) - $1,866 (Coinbase) = 10.61 bps.
- **Net-profit engine** correctly reports every current live cross-venue
  opportunity as UNECONOMIC after real fees:
  - ETH/USDT Coinbase→OKX: gross $10.61 → net **-$74.39** (70 bps trading + $8 withdrawal + slippage + liquidity impact)
  - BTC/USDT Coinbase→KuCoin: gross $11.53 → net **-$73.47**
- **Flash-Loan Journey** correctly aborts on `unprofitable`:
  `{qualified.qualified: false, reasons: [unprofitable]}` — never
  reaches route construction or capital estimation for uneconomic
  opportunities. Confirms the safety pipeline works end-to-end.

## Safety posture (unchanged)

| Guarantee | Status |
|---|---|
| OBSERVE mode | ✅ every scanner is read-only |
| PAPER mode | ✅ paper engine consumes only net-profit-aware payloads |
| Kill switch engaged at boot | ✅ `ARBICORE_SAFETY_KILL_DEFAULT=true` (default) |
| Live execution disabled | ✅ `ARBICORE_SAFETY_LIVE_EXECUTION_ENABLED=false` (default) |
| No signing | ✅ Journey emits `signing_allowed=false` invariant |
| No swaps | ✅ every DEX call is view-only |
| No flash loans | ✅ `simulate_flash_loan` is dry-run; no Aave contract call |
| No wallet interaction | ✅ `NoOpWalletProvider` only |
| No capital movement | ✅ `CapitalAllocationPolicy.clip_capital` applied per journey |

## Configuration (v2.6.0 additions)

| Var | Default | Purpose |
|---|---|---|
| `CROSS_AUTOSTART` | `1` | Autostart cross scanners |
| `CROSS_TICK_INTERVAL_SECONDS` | `25` | Cross scanner poll interval |
| `CROSS_MIN_NET_BPS` | `8` | Minimum *net* bps to emit |
| `CROSS_NOTIONAL_USD` | `10000` | Notional for cross opp modelling |

All Stage-2 env vars (RPC URLs, CEX allow-list, aggregator keys) unchanged.

## Files changed

New:
- `arbicore/economics/{__init__.py,net_profit.py}`
- `arbicore/scanners/live/cross.py`
- `arbicore/validation/__init__.py`
- `arbicore/flashloan/{__init__.py,operator_journey.py}`
- `frontend/src/v2/pages/OpsCenter.jsx`

Modified:
- `arbicore/scanners/live/scanner.py` — routes gross spreads through
  `compute_net_profit` before emitting; payload now includes full cost
  breakdown.
- `backend/server.py` — wires cross scanners, validation reporter,
  flashloan operator journey; adds 8 new endpoints.
- `frontend/src/v2/components/AppShell.jsx` — mounts `OpsCenter` at
  `/dashboard` (index) and `/dashboard/ops`; `HomePage` moved to `/dashboard/home`.

## Data flow

```
                       +---------- 6 CEX providers ----------+
                       |                                     |
      LiveMarketScanner ─── pulls tickers → cross-spread math
                                 │
                                 ├→ compute_net_profit(gross, fees, gas, slippage,
                                 │                     withdrawal, liquidity)
                                 ↓
                       +---- opportunity payload ----+
                       |  (net_profit_usd, breakdown)|
                       +--------------+--------------+
                                      │
      CexDexScanner (V3 vs live CEX)  ↓ ScannerEvidenceBridge
      DexDexScanner (V3 vs Sushi V2)  ↓
                                      ↓
                          MID (opportunities + routes)
                                      │
                                      ↓
         Paper Engine ← Wave-2 lifetime tracker ← Wave-3 memory
                                      │
                                      ↓
                 ValidationReporter (read-only over MID)
                                      │
                                      ↓
                    OpsCenter dashboard (6s poll)
```

## Testing

- Backend endpoint smoke tests via curl (all pass — see live evidence above).
- Frontend integration test: login → /dashboard renders `ops-center` +
  every named `data-testid` (kpi-providers, section-prices, section-opps,
  scanner-row-*, venue-rank-*, section-safety, cross-cex_dex,
  cross-dex_dex).
- All Python lint clean. ESLint clean on OpsCenter.jsx.

## Current capability after v2.6.0

- **Live cross-venue price feed** from 4-6 major CEX venues into MID.
- **Real net-profit calculation** — every opportunity carries a full
  cost breakdown; unprofitable spreads are flagged and refused.
- **Complete Flash-Loan Operator Journey** (dry-run) — qualify →
  route → capital → simulate → tx → plan → safety → approval →
  rollback → audit-evidence.
- **Read-only Validation Framework** — 7 endpoints and one aggregated
  summary produce every metric needed for a long-running paper
  validation review.
- **Ops Center dashboard** — one page, no placeholders, 6-second poll.
- **Safety unchanged** — kill engaged, no signing, no broadcast, no
  wallet interaction, no capital movement.

## Remaining work before the 7-day VPS validation run

1. **Provision one paid RPC** — free `llamarpc` returns HTTP 521 from the
   local pod. VPS should set `PROVIDER_RPC_URL_ETHEREUM` to an Alchemy /
   Infura / QuickNode endpoint for the cross scanners to actually emit.
2. **Add real per-venue fee ladders** — v2.6.0 uses public rack-rate
   defaults. Once VPS deploy is confirmed, tune `VENUE_FEE_BPS` per
   operator account tier.
3. **Enable regime engine** — Wave-1B-α regime engine is active but
   in-memory only. Bind it to Mongo-backed metric repos before the run so
   regime classification survives restarts.
4. **7-day observation checkpoint** — after deploy, verify OpsCenter
   populates within 60s and MID accumulates ≥ 500 opps/day at the
   default 15/25s tick intervals.

## Roadmap after Stage 4

- **Stage 5** — Long-running Paper Validation Run (7 days). Accumulate
  historical data, produce the first calibration report.
- **Stage 6** — Concrete `WalletCustodyProvider` (Ledger / MPC / KMS)
  and the Limited-Live Executor (single chain, single pair, capped
  notional). Kill switch remains admin-only.
- **Stage 7** — Concrete `FlashLoanProvider` classes (Aave V3, Balancer,
  Uniswap V3 flash). Real `queryBatchSwap`/`simulate` for Aave/Balancer.
  Independent audit sign-off before disengaging the kill switch.

## Regression results

All previously-passing tests continue to pass. New modules added lint
clean:
- `arbicore/economics/net_profit.py` — 0 lint issues
- `arbicore/scanners/live/cross.py` — 0 lint issues
- `arbicore/validation/__init__.py` — 0 lint issues
- `arbicore/flashloan/operator_journey.py` — 0 lint issues
- `frontend/src/v2/pages/OpsCenter.jsx` — 0 lint issues

## Bundle

- `arbicore-x-v2.6.0.bundle`
- `arbicore-x-v2.6.0.tar.gz`
- `arbicore-x-v2.6.0.SHASUMS`
- `RELEASE_NOTES_v2.6.0.md`
