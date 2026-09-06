# ArbiCore X v2 — FULL LIVE GATE CHECKLIST

Applies ONLY after Limited Live is proven (`ARBICORE_X_LIMITED_LIVE_GATES.md` all
PASS). Full Live is a separate, higher bar requiring sustained operational
evidence and production hardening. All gates below must PASS with real evidence.

| # | Gate | Notes |
|---|---|---|
| 1 | Proven execution across intended chains | Real executed edges on each target chain, not just Base |
| 2 | Proven venue execution cells | Each activated venue (UniV3 + any V2-settled venue) executed for real |
| 3 | Strategy-level proof | Each enabled strategy (DEX↔DEX, cross-DEX, multi-hop, …) executed for real |
| 4 | Reliable Opportunity Race | Stable, continuous, correct candidate selection across the full surface |
| 5 | RPC failover | Automatic failover across redundant operator endpoints per chain |
| 6 | Nonce management | Correct per-signer nonce handling under concurrency |
| 7 | Transaction lifecycle handling | Submit / replace / cancel / confirm / timeout logic |
| 8 | Stale opportunity protection | Reject edges past freshness window before broadcast |
| 9 | Duplicate prevention | No double-submission of the same opportunity |
| 10 | Reorg handling | Detect and reconcile on chain reorganizations |
| 11 | Accounting reconciliation | Every trade reconciled (borrow, swaps, repay, profit) |
| 12 | Exposure limits | Enforced max capital at risk |
| 13 | Trade-size limits | Enforced per-trade size caps |
| 14 | Slippage limits | Enforced global + per-hop minOut policy |
| 15 | Gas controls | Max gas / priority-fee ceilings; abort on gas spikes |
| 16 | Emergency stop | Global kill switch verified under load |
| 17 | Signer isolation | Keys isolated; no exposure in logs/reports/env dumps |
| 18 | Monitoring / alerting | Live dashboards + alerts on failures/anomalies |
| 19 | Long-duration reliability evidence | Sustained multi-day run with clean reconciliation |
| 20 | Explicit admin approval | Human sign-off recorded |

Production protection remains in force throughout (see
`ARBICORE_X_DO_NOT_DRIFT.md`): no production container/deploy/restart/executor/
signing/broadcast/withdrawal changes without explicit admin approval.
