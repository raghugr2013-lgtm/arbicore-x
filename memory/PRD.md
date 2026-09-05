# ArbiCore X v2 — Engineering PRD / Handoff Memory

## Project
Multi-network arbitrage backend (FastAPI/Python). SHADOW / detection-only /
fail-closed. GitHub is source of truth; VPS is the runtime-proof environment.
Working branch: `fix/p0-3-runtime-v3-liquidity-filter`.

## P0 status
- P0-1 Dynamic Capital: COMPLETE
- P0-2 Base RPC wiring: COMPLETE
- P0-3 Base Flash-Loan Discovery: IN PROGRESS — engineering/tests substantially
  complete; **NOT certified** (requires real VPS/Base runtime proof).

## Core, static invariants
- Canonical pool registry (`base_pool_registry`) is pure/deterministic — never
  mutated/deleted by runtime filtering (30 Base pools: 19 UniV3 + 11 Aerodrome).
- Runtime UniV3 `liquidity()` eligibility may EXCLUDE currently-unusable pools;
  zero/missing/malformed/unreadable/timed-out liquidity FAILS CLOSED.
- Aerodrome/Slipstream never subjected to the UniV3 `liquidity()` rule.
- Mode ladder OBSERVE→PAPER→SHADOW→LIMITED_LIVE→FULL_LIVE; broadcast only in
  LIMITED_LIVE/FULL_LIVE. No signing/broadcast/withdrawal enabled.
- Disposable validator = `scripts/run_vps_validator_audit.sh` (curated modules)
  against ephemeral Mongo; never production Mongo; no `--remove-orphans`.

## Implemented this workspace (dates)
- 2026-06: Section 6 — regression coverage for the Base UniV3 runtime liquidity
  eligibility filter. New `tests/test_z9_base_v3_liquidity_eligibility.py`; wired
  into validator module list. Commit `3a7b918`.
- 2026-06: Phase 4 — startup-budget remediation of
  `composition._refresh_base_v3_eligibility`: bounded concurrency
  (`asyncio.Semaphore`, default 8) + fail-closed pre-seed baseline + per-call
  timeout (default 2.0s ⇒ stalled read EXCLUDED) + caller fail-closed fallback
  (`_failclosed_exclude_all_base_univ3`). Independent adversarial module
  `tests/t1_verify/test_t1_z9_independent_verification.py`. Certification doc
  `docs/P0-3_CERTIFICATION_AND_CAPABILITY_MATRIX.md`. Commit `3bfaa5b`.
  Validator: 158 passed / 0 failed (PASS).
- 2026-06: Gas-model seam (item 3) — BaseGasModel.from_env() fails closed unless
  PROVIDER_RPC_URL(S)_BASE is explicitly set (public default no longer opens the
  M3 all-in-cost gate). Rewired stale test_base_all_in_cost.py to the registry
  seam (11/11). New test_gas_model_seam_failclosed.py. Commit `142084e`.
- 2026-06: Multichain readiness gate (item 4) — arbicore/runtime/multichain_
  readiness.py + GET /api/arbicore/multichain/readiness. Honest per-network
  status; NEVER limited-live eligible from code/config alone; economic dimension
  requires PROVIDER_* (ARBICORE_RPC_URL_BASE alone => economic_gate_rpc_not_
  configured). Endpoint error path keeps full SHADOW safety envelope. New
  test_multichain_readiness_gate.py. Commit `bd969ee`. Validator: 182 passed / 0.
- DEFERRED (item 5): behavior-preserving extraction of Base eligibility/wiring
  helpers out of composition.py — dedicated test-guarded refactor, only after
  items 3/4 reviewed/stable (per directive).
- 2026-06: RouteSearch → chain/venue-aware quote wiring (commit `1f1d68f`).
  RouteSearchDiscoverySource now emits `route_hops` + a deterministic probe
  `borrow_amount_wei` for NON-Base cycles so the generic EVM path in
  `live_quote_provider` runs end-to-end (Base regression-frozen: `_plan_base`
  untouched, no route_hops emitted). New `chains/registries.probe_amount_wei`
  (<=6dec→200u, 18dec→0.05u, else fail-closed None — a PROBE only, never
  liquidity/capacity/trade-size/eligibility). New
  `searcher/runtime.make_eth_call_for_chain_from_env` (generic per-chain
  eth_call seam; real only when operator RPC configured; never Base fallback)
  wired into the canonical SHADOW quote provider in composition (additive,
  fail-closed; signer/broadcast untouched). Honest `quote_path_connected` flag
  + `quote_path_connected_count` (=40) added to the opportunity matrix/certify
  — STRUCTURAL connectivity only; quote/liquidity/economic stay
  `requires_runtime`, no cell limited-live eligible. New
  `tests/test_flash_route_to_quote_pipeline.py` (20 offline cases, all 14
  acceptance items) wired into the validator. Validator: 231 passed / 0 failed.
  Flash-loan SOURCE scope stays locked to {ethereum,arbitrum,base,optimism,
  polygon} (test_chain_scope_locked); bnb proven quote-capable at the provider
  layer only.

## Known blockers / backlog
- P0-3 VPS/Base runtime proof (live discovery→quote→liquidity→economics→evidence
  persist+readback) — mandatory, cannot be produced in Emergent.
- Non-Base networks (ethereum/arbitrum/optimism/polygon/bnb): IMPLEMENTED, need
  per-chain RPC config + health before limited-live eligibility.
- Pre-existing, out-of-scope failure (fails identically at 01a8989):
  `test_t1_multichain_foundation_adversarial.py::TestGasModelSeam::test_from_env_no_rpc_is_fail_closed`
  (env-driven). Not fixed.
- `composition.py` ~1.9k lines (> guideline) — future dedicated refactor only.

## Do-not-touch (VPS-local)
`scanners/dex_arbitrage/scanner.py`, `deployment/compose/docker-compose.yml`,
stash@{0} "VPS-local changes before P0-3 sync", branch
`backup/vps-before-p0-3-sync`. Preserve compose mapping `127.0.0.1:18001:8001`.
No merge to main, no force-push, no auto-deploy.
