# ArbiCore X — VPS Multichain Runtime Certification Procedure

Read-only runtime certification of the multi-venue opportunity surface against
REAL operator RPC. NO signing, NO broadcast, NO execution, NO mode change. This
is the bridge between the offline repo/capability certification (which runs
anywhere) and a future controlled execution proof (operator-gated, separate).

> Safety envelope for this whole procedure: `LIMITED_LIVE=off`, `FULL_LIVE=off`,
> signing/broadcast/auto-exec/withdrawals OFF, kill switch engaged. Every failure
> path is fail-closed. No pool/TVL/quote/opportunity is ever fabricated.

## 0. Prerequisites (operator provides)
Per-chain RPC endpoints (comma-separated lists allowed) via the registry-backing
keys the economic gate consumes:

```
PROVIDER_RPC_URLS_ETHEREUM=...
PROVIDER_RPC_URLS_ARBITRUM=...
PROVIDER_RPC_URLS_OPTIMISM=...
PROVIDER_RPC_URLS_POLYGON=...
PROVIDER_RPC_URLS_BNB=...
PROVIDER_RPC_URLS_BASE=...
```
`ARBICORE_RPC_URL_<CHAIN>` / `<CHAIN>_RPC_URL` are accepted at the DISCOVERY
level but are NOT sufficient for the economic gate (by design — see
`multichain_readiness.provider_registry_rpc_configured`). No signer key is
provisioned in this phase.

## 1. Offline repo + capability certification (baseline, runs anywhere)
```
cd app/backend
python -m scripts.arbicore_certify            # human
python -m scripts.arbicore_certify --json     # machine-readable evidence
```
PASS ⇒ repository integrity + protected-file integrity + compile + safety posture
(all OFF) + chain/venue/provider/strategy matrix. Runtime dimensions are reported
`requires_vps_runtime` — a PASS here does NOT certify any live capability.

Current offline surface (branch `takeover/limited-live-seam-cc8db95`):
`matrix rows=75 · discoverable=65 · quote_path_connected=55 · limited_live=0`.
`venue_families`: canonical_base 3/3, univ3 7/7, univ2 1/1, algebra 2/2,
solidly 0/1, curve 0/1.

## 2. VPS read-only reachability + live pool-resolution preflight
Run on the VPS with the operator RPC env set:
```
cd app/backend
python -m scripts.vps_multichain_preflight            # human
python -m scripts.vps_multichain_preflight --json     # evidence
```
This composes ONLY read-only building blocks and reports, per chain × venue ×
flash-loan provider:
- operator RPC + gas-model + the exact readiness blocker,
- structural `quote_path_connected`,
- **LIVE venue-aware pool resolution** for a deterministic probe set via the same
  per-chain `eth_call` seam the live quote provider uses. It now exercises every
  wired venue family:
  - `univ3` — Uniswap V3 + Sushi V3 (arb) + Pancake V3 (bnb): `getPool` + state,
  - `univ2` — Sushi V2 (eth): `getPair` + `getReserves`,
  - `algebra` — Camelot V3 (arb) + QuickSwap V3 (poly): `poolByPair` + state.
  Base is served by its canonical registry (use step 3).
- eligible flash-loan providers per chain.

A chain with no operator RPC is reported `no_operator_configured_rpc` and skipped
(fail-closed). A pool that is nonexistent / unreadable / zero-liquidity is
EXCLUDED (never counted as resolved).

## 3. Base canonical runtime depth (already-proven path)
```
cd app/backend
python -m scripts.m3_0_real_candidate_scan            # Base flash-loan candidate scan (read-only)
python -m scripts.vps_canonical_audit                 # Base canonical audit
```

## 4. Live quote / economics probe (read-only, per candidate)
For any candidate surfaced by step 2/3, exercise the real end-to-end economics
WITHOUT execution:
```
python -m scripts.m3_0_vps_validate '<opportunity_plan_json>'   # confirm=False always
```
Verify in the audit JSON: `verdict.safe`, `signed_or_broadcast=false`,
`broadcast_sent=false`, and the `FIRST_BLOCKING_STAGE`.

## 5. Interpretation / capability ladder (never collapsed)
For each chain × venue, advance ONLY on real evidence:
`IMPLEMENTED → CONFIGURED (RPC) → DISCOVERABLE (live pool resolved) →
QUOTABLE (live quote) → LIQUIDITY-VERIFIED (real reserves/TVL) →
ECONOMICALLY-VALID (net > gates) → SIMULATABLE (fork) → LIMITED-LIVE ELIGIBLE`.
`LIMITED-LIVE ELIGIBLE` additionally requires explicit admin approval — a static
or read-only report can NEVER assert it.

## 6. Remaining venue seams (honest gaps after this phase)
- Algebra QUOTE adapter (Camelot/QuickSwap dynamic-fee QuoterV2) — Algebra pools
  are DISCOVERABLE (poolByPair) but not yet quote-connected.
- Solidly/Velodrome and Curve resolvers — not implemented (explicit blockers).
- Fork quoter addresses (Sushi V3 / Pancake V3 / Sushi V2) are sourced from
  official docs and MUST be re-verified live on first VPS run (the harness reads
  them via eth_call; a wrong/renamed deployment fails closed, never fabricates).

## 7. Controlled execution proof — prerequisites (do NOT run yet)
Not part of this phase. Requires, in addition to the above: a dedicated
low-value funded signer, an explicitly-allowed chain/venue/strategy/provider, a
strict capital + per-trade-loss ceiling, max-one execution, kill switch armed,
withdrawals disabled, Full-Live disabled, and explicit human approval to ENTER
Limited-Live. Until a real controlled transaction completes its full lifecycle,
`LIMITED_LIVE_PROVEN=false`.
