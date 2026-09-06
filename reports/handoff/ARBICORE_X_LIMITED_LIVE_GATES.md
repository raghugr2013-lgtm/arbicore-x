# ArbiCore X v2 — LIMITED LIVE GATE CHECKLIST

Current status: **LIMITED_LIVE_PROVEN = FALSE**. Every gate below must PASS on
real evidence (no fork-only, no simulation-only, no fabricated data). Until then,
Limited Live stays OFF.

| # | Gate | Current | Evidence required |
|---|---|---|---|
| 1 | Six-chain runtime certification | PARTIAL — RPC + read-only race PASS; operator-authoritative per-chain cert pending on VPS | Operator RPC probe + full DISCOVER→…→SIMULATION per chain |
| 2 | Genuine qualifying opportunity | **FAIL** — 0 found | A real candidate that clears every downstream gate (NOT threshold-lowered) |
| 3 | Positive net economics | **FAIL** — all `negative_gross_edge_all_sizes` | gross edge − gas − slippage − flash cost > profit buffer, real inputs |
| 4 | Flash liquidity | NOT PROVEN | Real borrowable liquidity at size from a supported provider (Balancer V2 / Aave V3) |
| 5 | Fresh market revalidation | NOT PROVEN | Re-quote at execution time within freshness window |
| 6 | Execution capability | UniV3 only (on-chain) | Deployed executor can settle the candidate's venue(s) |
| 7 | Fork / simulation proof | NOT PROVEN | anvil fork run of the full plan succeeds |
| 8 | Controlled real execution | OFF | Single disarmed→armed execution under strict caps + kill switch |
| 9 | On-chain receipt verification | NOT PROVEN | Tx mined, `ExecutionCompleted` event decoded |
| 10 | Repayment verification | NOT PROVEN | Flash principal+premium repaid (Balancer transfer / Aave pull) |
| 11 | Profit / residual verification | NOT PROVEN | Residual forwarded to profit recipient, reconciled |
| 12 | Safety controls | PASS (all OFF) | Kill switch, capital/loss ceilings, max-one execution, signer isolation |
| 13 | Explicit admin approval | NOT GIVEN | Human approval recorded |

Prerequisites blocking gates 6–11 today: the deployed V1 receiver settles UniV3
only (see `ARBICORE_X_ARCHITECTURE_STATE.md`); non-UniV3 candidates cannot pass
gate 6 until Executor V2 is built, tested and deployed. Gate 2/3 are market-
dependent and must be met by a real edge, never by lowering thresholds.

Safety during certification: signing/broadcast/auto-exec/full-live stay OFF; no
intentional execution of a known-bad trade; no threshold lowering.
