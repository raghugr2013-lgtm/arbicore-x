# ArbiCore X — Base Live-SHADOW Readiness Report

**Stage:** Stage 1 — Software Completion of the Base flash-loan searcher (live-SHADOW). No live execution, no broadcasting, no VPS deploy. `main@43230f6` baseline.

## Software-complete (this stage)
`searcher/live_base.py` (all fail-closed, SHADOW, injectable/testable):
- **WSS subscriber** `BaseWssSubscriber` — consumes newHeads/logs, `decode_sync_log` → `runtime.ingest_log` (PoolStateCache), `newHead` → `runtime.scan_block`; asserts `broadcast is False`.
- **Real on-chain TVL hooks** `make_base_reserves_fn` (eth_call `getReserves()` decode) + `make_base_price_fn` (USD price source) → feed `OnChainReserveTVLProvider`; any missing datum → None → **Gate 8 fail-closed**.
- **Real Anvil fork** `AnvilProcessLauncher`/`_AnvilHandle` — `anvil --fork-url <BASE_RPC>` + JSON-RPC `eth_call`; plugs into `AnvilRevmForkBackend` (fails closed without binary/rpc/tx_builder/decoder).
- **Evidence bridge** `candidate_to_canonical` — accepted SHADOW candidate → **REAL** `CanonicalOpportunity` → reuses the EXISTING verifier/paper/shadow/certification/evidence pipeline via the T0-2 REAL-only write-gate (no new evidence path).
- **Readiness classifier** `base_live_readiness()` — reports each dependency ready/blocker with category.
- **Control-center metrics** exposed via existing `/engine/flash-loan/readiness`, `/certification/provenance-split`, plus `ScanMetrics` (cycles/survivors/sim_ok/gate7_rej/gate8_rej/stale_hops/candidates/scan_latency/broadcasts=0).

## Tests / performance
- New `tests/test_t2_live_base.py` **5 passed**; combined relevant suite **92 passed, 0 regressions**; `server.py` compiles.
- Local scan benchmark: **0.484 ms** for an 84-cycle full scan → **~2,066 scans/sec**; kernels V2 2.71M/s, fast-filter ~357K cycles/s → ample per-block headroom on Base.

## Consolidated blocker register (to reach live-SHADOW on VPS)
| Blocker | Category | Resolution |
|---|---|---|
| Base RPC not set in this env | CONFIGURATION | Set `ARBICORE_RPC_URL_BASE` (already present on VPS = Alchemy) |
| Base WSS URL | CONFIGURATION | Set `ARBICORE_WSS_URL_BASE` (tier-1 provider WSS endpoint) |
| `anvil` binary | CONFIGURATION | Present via Dockerfile Foundry/Anvil v1.7.1 on the VPS image |
| Executor address / calldata | CONFIGURATION+SOFTWARE | Set `ARBICORE_EXECUTOR_ADDRESS_BASE`; provide the atomic-route `tx_builder` (executor ABI/calldata) — the only remaining **SOFTWARE** hook, provider-specific |
| USD price feed | CONFIGURATION | Wire `price_source` (oracle/quoter) into `make_base_price_fn` |
| Pool→tokens/decimals map | CONFIGURATION | Supply per-pool `(token0,token1,dec0,dec1)` from the Base venue registry |
| Live latency/candidate/sim metrics | VALIDATION | Measure on VPS with flag=on in SHADOW |
| Real arbitrage frequency on Base | MARKET | Observed during SHADOW; not a code blocker |
| Live execution | SAFETY | Intentionally NOT enabled (SHADOW-only) |

No SOFTWARE blockers remain except the executor `tx_builder` (needs the deployed executor contract ABI/address — VPS artifact). Everything else is CONFIGURATION/VALIDATION/MARKET/SAFETY.

## Safety (unchanged)
SHADOW-only; `broadcasts=0` asserted; $25 Gate 7 intact; Gate 8 real-liquidity/fail-closed; REAL provenance only (write-gate); no synthetic in real funnel; no auto-promotion; no gate weakening; not deployed.

## Exact operator action (VPS, flag-gated SHADOW)
1. Set `ARBICORE_T2_SEARCHER_ENABLED=true`, `ARBICORE_WSS_URL_BASE=<wss>`, `ARBICORE_EXECUTOR_ADDRESS_BASE=<addr>` (RPC + anvil already present).
2. Provide the `tx_builder` (executor calldata) + `price_source` + pool→tokens map, and start `BaseWssSubscriber` on the Base WSS.
3. Observe `/engine/flash-loan/readiness`, `/certification/provenance-split`, and ScanMetrics; record the VALIDATION metrics. Keep mode SHADOW.
