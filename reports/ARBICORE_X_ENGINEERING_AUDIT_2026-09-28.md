# ARBICORE X — CURRENT ENGINEERING AUDIT (2026-09-28)

Scope: read-only source-level audit of the ArbiCore X checkout present in this
Emergent workspace. No source files modified. Runtime capability is distinguished
from architecture throughout. Classifications:
IMPLEMENTED+VERIFIED / IMPLEMENTED+NOT_VERIFIED / PARTIAL / MISSING / STALE-LEGACY / BLOCKED.

## 0. Environment reconciliation (must read first)
- This checkout is branch `main` @ `621faea` (VERSION 2.9.2), NOT the G5.79 worktree
  (`3ddde0d`) referenced by the handoff. `/home` is empty; the authoritative
  worktree is not mounted here.
- The G5.130 bridge `sync_provider_registry_rpc_from_env()` is **absent** here
  (0 hits repo-wide). `env_sync.sync_env_from_network_config()` here is the
  pre-G5.130 Phase-10.10 shim (Base-centric, `chain="base"` default) and does
  NOT invoke any provider-registry bridge.
- The three "protected" test files have DIFFERENT sha256 here than the brief's
  worktree values, and `test_gas_model_seam_failclosed.py` is absent. So G5.79/
  G5.130 "close-out" cannot be performed from this checkout — it requires the
  worktree source.
- Test corpus: 2733 collected, 31 collection ERRORS (env-dependent:
  missing `REACT_APP_BACKEND_URL`, `FileNotFoundError`, None DB handles) — these
  are harness/isolation issues in this sandbox, not proven core defects. Targeted
  pure-logic suites pass (phase10 env-sync 4/4; provenance registry 13/13).

## 1. Executive status
Architecture for the six-chain × four-provider × five-route vision is broadly
PRESENT and genuinely fail-closed. The dominant gap between "architecture" and
"runtime capability" is that the live QUOTE→LIQUIDITY path for flash-loan arb is
**Base-only wired**, while route discovery and economics are already chain-generic.
Posture is correctly SHADOW/detection-only; LIMITED_LIVE/FULL_AUTOMATION hard-RED.

## 2. Six-chain matrix (RPC/provider readiness) — PARTIAL
- Provider bootstrap (`providers/bootstrap.py`) reads `PROVIDER_RPC_URL[S]_<CHAIN>`
  for all 6 EVM chains → IMPLEMENTED. `config/runtime.RpcFailover` mirrors it.
- Canonical→provider RPC lifecycle bridge (G5.130) MISSING in this checkout.
- Chain registries (`chains/registries.py`) carry real v3 factory addresses for
  all 6 chains, but no Balancer vault / Morpho singleton / Aave pool addresses.

## 3. Provider matrix — IMPLEMENTED + NOT_VERIFIED
- `FLASH_LOAN_PROVIDERS` chain-support matches the canonical set exactly
  (Aave V3: 6 chains; Balancer V2: 5; Uniswap V3 flash: 5; Morpho Blue: 2).
- Selection kernels (`provider_selection.py`, `flash_provider_optimizer.py`) are
  fail-closed: unknown fee or unknown/insufficient liquidity ⇒ provider infeasible;
  UniV3 fee never assumed (caller must resolve tier). Morpho/Balancer 0-bps treated
  as a REAL fee. No runtime on-chain verification of provider deployment.

## 4. Route matrix — IMPLEMENTED (enumeration), NOT_VERIFIED (executability)
- `RouteSearchEngine` bounded-DFS cycle enumerator; caps exactly match thresholds
  (max_hops 4, wall 5s, candidate_cap 64, min_pool_tvl 100k).
- `discovery/multichain_venues.build_pool_graph` builds a 6-chain venue universe
  from verified registries (synthetic ids, tvl=0.0 → resolved downstream).
- Route FAMILIES (GENERIC_DEX/TRIANGULAR/STABLECOIN/MULTI_HOP/LST_LRT) exist as
  tags (`models/enums.py`, `strategy_tagging.py`) but genuine executability per
  family per chain is not runtime-verified.

## 5. Quote status — PARTIAL / **Base-only (primary bottleneck)**
- `live_quote_provider.make_live_quote_provider` is hardwired to Base via
  `discovery.base_venues.CHAIN="base"` and `canonical_pool_specs()`/`token_address`.
  `runtime/composition.py` wires it only for Base. The other 5 chains have route
  discovery + economics but NO live quoting.
- Quote integrity is strong/fail-closed: partial/reverted/non-closed-cycle quotes
  return None → `denied:venue_unreadable`; verifier has a second integrity boundary.

## 6. Liquidity status — IMPLEMENTED + fail-closed (Base real reads)
- M2.2 `tvl_provider` reads REAL on-chain depth; `_route_min_tvl` fails closed (0.0)
  unless EVERY pool has positive measured TVL. Gate 8 fails closed at TVL<=0
  (old $5M sentinel removed).

## 7. Economics status — IMPLEMENTED + VERIFIED (unit-level, chain-agnostic)
- `aggregate_economics` + `multichain_economics.compute_true_net_profit` converge on
  a single honest identity; any unknown (gas model / provider / route gas / all-in)
  ⇒ DENY. Double-count fix (`gross_is_quote_inclusive`) is correct. Gas
  (`chains/gas_model`, `evm_gas`) fail-closed on missing L1/L2/native inputs.
  MEV (`MevRiskScorer` + Gate 9 cap MEDIUM). Thresholds intact ($25 atomic floor,
  100k TVL, MEV MEDIUM) and env-tunable but not weakened.

## 8. Paper Validation status — IMPLEMENTED + NOT_VERIFIED
- `paper/` engine, runner, simulator, classifier, outcomes, evidence, stage_recorder
  present. No accumulated paper evidence bundles in this sandbox → runtime unproven.

## 9. Evidence status — IMPLEMENTED
- Verifier persists an auditable bundle for EVERY candidate (CONFIRMED and DENIED)
  with per-gate outcomes, provenance (`derive_provenance` fail-closed on DEAD
  sources), diagnostic run/tick identity, `broadcast:false` invariant.
  `evidence/bundle.py`, `audit_provenance.py`, `signer.py` present.

## 10. Meta-Learning status — IMPLEMENTED, OBSERVE-only
- `learning/adaptive_weights_observer` + `_worker` recompute recommendations in
  OBSERVE mode; never applies scores. Recommendation/Autonomous modes not active.

## 11. Certification status — IMPLEMENTED, fail-closed grading
- `certification/thresholds.py` (defaults intact, env-tunable), `runner.py`,
  `engine.py`, terminal-status immutability. Shadow-cert readiness surfaces in
  `control/readiness`. No PASS run recorded here.

## 12. Current blockers (to reach discovery→paper→economic evidence→limited-live)
- B1 (dev): live quote provider is Base-hardwired — blocks 6-chain QUOTE/LIQUIDITY.
- B2 (dev): non-Base pool specs / quoter backends / token maps absent
  (`base_venues`/`base_pool_registry` have no multichain sibling).
- B3 (dev/close-out): G5.130 lifecycle bridge absent in this checkout.
- B4 (runtime/VPS): real 6-chain RPC + provider on-chain verification.
- B5 (runtime): paper-evidence accumulation (needs live quoting on ≥1 non-Base chain).
- B6 (operator/on-chain): non-Base executor deploy; atomic sim requires signer.

## 13. Stale / legacy
- `intelligence/wave1b`, `scanners/wave1b` and any readiness endpoint expecting a
  Wave1B scanner are legacy; canonical `FlashLoanArbitrageScanner` is authoritative.
  Do NOT resurrect Wave1B to satisfy readiness.
- 31 env-dependent test-collection errors are harness/isolation debt, not core.

## 14. Recommended next implementation packages (prioritized)
- PKG-1 (P0, dev-safe): Chain-parameterize the flash-loan live quote provider so
  QUOTE/LIQUIDITY works on all 6 chains (Base path unchanged / regression-frozen).
- PKG-2 (P0, dev-safe, depends on PKG-1): multichain pool-spec + token-address +
  quoter-backend registry (fail-closed empty per unconfigured chain).
- PKG-3 (P1): G5.130 close-out — but ONLY once the authoritative worktree is
  available here; cannot be done from this checkout.
- PKG-4 (P1, dev-safe): route-family executability verifier per (chain, provider,
  family) — enumerate → prove executable, not theoretical.
- PKG-5 (P2, runtime/VPS): 6-chain RPC/provider runtime verification harness.

## 15. Exact files per package
- PKG-1: `arbicore/scanners/flash_loan_arbitrage/live_quote_provider.py`,
  `arbicore/runtime/composition.py` (wiring), new
  `arbicore/discovery/multichain_pool_registry.py`; tests under `tests/`.
- PKG-2: `arbicore/discovery/multichain_venues.py`, `chains/registries.py`,
  new multichain token/pool-spec module.
- PKG-3: `arbicore/config/env_sync.py`, `arbicore/config/persistent.py`,
  `tests/test_phase10_10_env_sync.py` (worktree required).
- PKG-4: `arbicore/scanners/flash_loan_arbitrage/{strategy_tagging,route_search,verifier}.py`.
- PKG-5: VPS harness (Codex) + `providers/bootstrap.py`, `config/runtime.py`.

## 16. Tests required
- PKG-1: per-chain quote-provider unit tests (fail-closed on unconfigured chain,
  closed-cycle enforcement, partial-quote denial) + Base regression parity.
- PKG-2: registry completeness/empty-fail-closed tests.
- PKG-4: family-executability truth tests (no theoretical passes).

## 17. VPS validation required
- PKG-1/2 need real non-Base RPC to prove live quoting (Codex-run, read-only).
- PKG-5 is VPS-only. None of these require signing/broadcast/mode change.

## 18. Risks
- Accidentally widening the Base-frozen path (regression) — keep Base isolated.
- Fabricating non-Base pool specs/TVL — must stay fail-closed (empty > guessed).
- Repo divergence: implementing G5.130 here would fork from the worktree; must
  reconcile source of truth first.
- No threshold/gate/mode changes; SHADOW preserved.

## Smallest next package (proposed, NOT yet implemented)
PKG-1 only: make `make_live_quote_provider(chain=...)` chain-parameterized with a
fail-closed multichain pool/token resolver, leaving the Base path byte-for-byte
behavior-equivalent. Dev-only, no signing/broadcast, needs Codex VPS quoting proof.
STOP for review before coding.
