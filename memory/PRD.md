# ArbiCore X — PRD / Working Memory

## Origin
External GitHub clone (raghugr2013-lgtm/arbicore-x). FastAPI backend `/app/app/backend`,
Solidity `/app/contracts`. Objective: controlled, capital-light Base flash-loan arbitrage.
System MUST remain SHADOW/PAPER until explicit operator approval. No deploy/broadcast/sign.

## Canonical baseline (Phase 0 repo reconciliation)
- `main` is canonical & newest (v2.9.2 + 69 commits ≈ v2.11.x).
- `hotfix/auth-routing` fully merged; `archive-v1` + `feature/ui-v2-slices-0-2` are stale archives.
- No execution/contract code exists off-main. No merge/cherry-pick required.

## Architecture (verified)
- On-chain executor `FlashLoanReceiver.sol`: Aave V3 + Balancer V2 flash; Uniswap V3 SwapRouter02 settlement ONLY.
- Off-chain quoting is multi-venue & real (`eth_call`): UniV3, UniV2, Aerodrome (SlipStream+classic), Curve, Balancer, Jupiter.
- Route graph: `route_search.py` DFS cycle enumerator (max_hops cfg).
- Broadcast: single site `broadcast.py` behind 6-gate ladder. Mode default SHADOW.

## Done — 2026-08-20 (Phase 0 security blockers, verified by testing_agent)
- S1: remediation documented (rotate leaked GitHub token; platform "Save to Github"). NOT auto-modified.
- S2: pipeline kill-switch now uses authoritative `KillSwitchRepo.state()` (was broken `.get()`), denies when engaged.
- S3: `OpportunityPipeline.auto_confirm` default False; auto-executor no longer autonomously confirms broadcasts.
- S4: `/api/arbicore/wizard/technical-validation` now requires operator auth + enforces kill-switch, approved executor, dedicated signer, chain allowlist (Base Sepolia default; mainnet blocked), token allowlist on execute=true.
- S5: `LimitedLiveBroadcaster` binds capital sizing to real gas-wallet balance via injected `WalletBalanceReader`.
- S6: broadcaster `slippage_guard` gate rejects zero/absent `amountOutMinimum` / empty userData on live-capable path.
- Tests: 32/32 (wave7 + new tests/test_phase0_s2_s6_security.py); full regression 96/97 → 97/97 after test update.
- Env bootstrap: created backend/.env (local Mongo, DB_NAME=arbicore_x) + frontend/.env; seeded single admin.

## Executable coverage: still ~30% (unchanged by Phase 0 — safety only).

## Backlog (approved plan, NOT yet implemented — need operator go + live Base RPC infra)
- P0.1 Aerodrome on-chain adapter (SlipStream+classic) + userData/calldata venue tagging + tests.
- P0.2 Adaptive flash-loan size optimizer (grid → max risk-adjusted EV, with max_loss).
- P0.3 Wire live Base pool inventory into route_search.pool_loader + live QuoteProvider into flash-loan verifier (replace noop).
- P0.4 Confidence v2 (multi-factor, explainable) + EV = P(success)*net − P(failure)*max_loss.
- P0.5 Base fork test + historical replay + shadow certification harness.
- Discovery layer (research-only): broad Base venue/token/opportunity indexing (parallel workers, bounded concurrency).
- P1: UniV4, UniV2, Curve, Balancer-swap, safe 0x adapters. P2: cross-chain, CEX/DEX, liquidations, MEV.

## Credentials
See /app/memory/test_credentials.md (operator / ShadowOperator!2026).
