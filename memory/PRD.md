# ArbiCore X — PRD / Working Memory

## Original task
Audit the canonical ArbiCore X repo at immutable baseline `6de846f` (branch
`complete-Base-M1-M4-live-shadow-composition`), determine implemented vs
dormant/miswired/incomplete, then safely complete canonical integration toward a
controlled path to LIMITED LIVE. **SHADOW/PAPER only — execution must remain impossible.**

## Architecture (as-found, canonical)
- FastAPI backend (`app/backend`, symlinked `/app/backend`) + React v2 frontend (`app/frontend/src/v2`) + MongoDB.
- Canonical pipeline: SUPPORTED CHAINS → provider discovery → 6 scanner families →
  EmissionBus → canonical `arbicore_opportunities` repo → verifier/Gates 7/8/9 →
  M3 authority (`pre_broadcast.py`) → evidence → SHADOW/PAPER.
- Runtime composition root: `arbicore/runtime/composition.py`.
- 6 scanner families implemented + wired: cex_arb, funding_arb, dex_arb, launch_arb,
  cross_chain_arb, flash_loan_arb (deepest). All boot DORMANT (scanner_state.enabled=False).
- Universal Gates 2–5: `arbicore/scanners/gates/universal.py`. Gate 7/8/9 in flash-loan verifier.
- Economics: FlashLoanEconomicsAssessor + multichain_economics + chain gas models (6 chains) + Base L1 all-in cost.
- Price/TVL: OnChainUsdPriceFeed (M2.5, peg/freshness-guarded), CachedTVLProvider (M2.6, on-chain reserves). All fail-closed.
- Provider selection: `flash_loan_arbitrage/provider_selection.py` — fee-driven, fail-closed on unknown liquidity.

## Safety posture (unchanged, verified)
LIMITED_LIVE=0, FULL_LIVE=0, AUTOEXEC_AUTOSTART=0, RUNTIME_AUTOSTART=0, MIN_NET_PROFIT_USD=35.
No signer, no broadcast, SHADOW pipeline built with no broadcaster/mode_repo → broadcast structurally impossible.

## What was done (2026-06 audit session)
- Created local `.env` (backend SHADOW-safe values + auth) and frontend `.env` (REACT_APP_BACKEND_URL). `.env` is gitignored (not checkpointed).
- Installed backend deps; backend + frontend running under supervisor; auth + canonical `/api/arbicore/opportunities` verified (returns `source:"canonical"`, empty = fail-closed).
- MINIMAL SAFE CHANGE: legacy OBSERVE-mode pipelines (`live_market`, `cex_dex`, `dex_dex`) that feed the SEPARATE legacy MID store are now OPT-IN (default OFF) to stop duplicate/parallel opportunity generation vs the canonical EmissionBus feed.
  - `server.py`: `LIVE_MARKET_AUTOSTART` / `CROSS_AUTOSTART` default "1"→"0".
  - `arbicore/config/runtime.py`: matching informational defaults →False.
- Verified: canonical offline suites pass (M2/M3 110, Phase-2 95, regression 77). Full suite 2208 passed; remaining failures are xdist event-loop artifacts + requests-based integration tests (external routing/auth) + 3 STALE offline tests (base-only gas-model assertion; shadow-cert fake missing provenance) — NOT product regressions, NOT weakened.

## Full audit report
`/app/reports/CANONICAL_INTEGRATION_AUDIT_2026-06.md` (sections A–S).

## Known blockers before LIMITED LIVE (require real Base RPC on VPS; not reproducible in preview)
1. Aerodrome/Slipstream canonical address + TVL resolution discrepancy (real_address/TVL null despite successful quotes) — Gate 8 stays fail-closed. See `HANDOFF_NEXT_EMERGENT.md §4`.
2. Need a genuinely profitable real opportunity to reach GREEN end-to-end (fail-closed dry-run) before any evidence-gated LIMITED-LIVE plan.
(Note: the older MEV `congestion=None` TypeError from the handoff is ALREADY fixed at this baseline — `fresh_fn` DENYs before `mev.classify`.)

## Backlog / next (SHADOW-safe)
- P1: Resolve Aerodrome/Slipstream TVL/address resolution on real Base RPC (no fabrication).
- P1: Reconcile the 3 stale tests to the canonical multi-chain / provenance-hardened reality (repair, not weaken).
- P2: Wire funding_arb order-book depth_fetcher; inject cross_chain transfer/liveness providers for verification.
- P2: OpsCenter landing page still surfaces legacy MID widgets (now honestly empty) — consider making Opportunities (canonical) the default landing.
