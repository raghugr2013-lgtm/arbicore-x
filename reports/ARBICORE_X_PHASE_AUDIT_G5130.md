# ARBICORE X — G5.79/G5.130 BASELINE AUDIT + GAP MATRIX

Read-only. No source modified. Access caveat: this Emergent workspace holds
`main`@621faea (v2.9.2), NOT the G5.79 worktree (3ddde0d). The G5.130 bridge
`sync_provider_registry_rpc_from_env()` is not present here; findings about it
are contract/mechanism-level. All ArbiCore subsystems below ARE present here and
were traced in source.

## 1. Executive summary
The flash-loan architecture is genuinely fail-closed and largely chain-generic in
its PURE layers (route search, economics aggregation, provider selection, strategy
classification, gates, evidence). Runtime capability, however, is **Base-only**
across three independent layers:
  (a) Quote adapters — `QuoterRegistry._CONTRACT_BY_CHAIN` = {base, base-sepolia};
      every other chain returns `_fallback_hop("no adapter")`.
  (b) [CORRECTED 2026-09-28] Gas models EXIST for all 6 chains — `chains/gas_model`
      dynamically registers Base + evm_gas (arbitrum/optimism/ethereum/polygon/bnb)
      with correct L1 flags; unit-tested by test_phase2_multichain.py. NOT a gap.
      The real gap is the LIVE DEX QUOTE ADAPTER (see (a)) + Base-only TVL/wiring.
  (c) Wiring — `runtime/composition.py` + `live_quote_provider.py` are hardwired to
      Base (`make_base_*`, `base_pool_registry`, base token map, `get_chain_gas_model("base")`).
Consequently only Base can run DISCOVER→QUOTE→LIQUIDITY→ECONOMICS→PROFIT-GATE
→ROUTE→SIMULATION today. The other five chains are DISCOVER + ROUTE-enumeration +
strategy-classification only. This is the correct fail-closed state — nothing is
fabricated — but it is the core roadmap blocker.

## 2. Provider × chain × route capability matrix
Legend per cell dimension: CFG=config-only, DISC=discoverable, RTV=runtime-verifiable,
QV=quote-verifiable, LV=liquidity-verifiable, EV=economics-verifiable,
SIM=simulation-verifiable, PV=paper-ready, EX=exec-ready, EVD=evidence-ready.

Providers (catalog `FLASH_LOAN_PROVIDERS`, CONFIG-ONLY chain support — not runtime-verified):
- Aave V3:      ethereum, arbitrum, base, optimism, polygon, bnb   [CFG]
- Balancer V2:  ethereum, arbitrum, base, optimism, polygon        [CFG]
- Uniswap V3fl: ethereum, arbitrum, base, optimism, polygon        [CFG]
- Morpho Blue:  ethereum, base                                      [CFG]
  (Morpho singleton/selector/fee live in provider code, NOT wired to a runtime
   flash executor on any chain here.)

Route families (`strategy_tagging.classify_strategy`, all 5 IMPLEMENTED as pure
classification; TRIANGULAR also has a dedicated `triangular.py` discovery path):
GENERIC_DEX, STABLECOIN, TRIANGULAR, MULTI_HOP, LST_LRT — chain-agnostic.

Effective runtime capability BY CHAIN (the gating dimension; providers×families are
generic on top of it):
- BASE:      DISC+QV+LV+EV+SIM+EVD ✅  (PV ready pending accumulated evidence; EX blocked: no signer/executor-live)
- ETHEREUM:  DISC only  (QV/LV/EV = MISSING: no quoter adapter, no gas model, no wiring)
- ARBITRUM:  DISC only  (same)
- OPTIMISM:  DISC only  (same)
- POLYGON:   DISC only  (same)
- BNB:       DISC only  (same; also no Balancer/Morpho by catalog)

So of 4×6×5 = 120 theoretical combos, only the BASE column (4 providers × 5
families, subject to real per-route quotes/liquidity) is quote/economics-verifiable
today; the remaining 100 combos are DISCOVER/classification-only (fail-closed).

## 3. Runtime verification matrix (pipeline stage × readiness)
DISCOVER        — ✅ all 6 chains (multichain_venues + route_search)
QUOTE           — ✅ Base only (QuoterRegistry adapters) · ❌ other 5 (fallback:no_adapter)
LIQUIDITY       — ✅ Base only (M2.2 tvl_provider, fail-closed) · ❌ other 5
ECONOMICS       — ✅ Base only (gas model present) · ❌ other 5 (no gas model ⇒ DENY)
PROFIT GATE     — ✅ generic ($25 floor, Gate7) — but only reachable where economics run
ROUTE           — ✅ all 6 (enumeration) · executability verified only on Base
SIMULATION      — ⚠ Base atomic sim wired but BLOCKED until signer authorized (fail-closed)
EXECUTION/SIGN/BROADCAST — ⛔ intentionally OFF (SHADOW); LIMITED_LIVE hard-RED
RECEIPT/REPAY/RECONCILIATION — present in paper/execution modules; runtime unproven
EVIDENCE        — ✅ generic (bundle per CONFIRMED/DENIED, provenance fail-closed)

## 4. Quote / liquidity / economics gap matrix (priority-ordered)
- G1 (P0): No non-Base UniV3 QuoterV2 / DEX quoter addresses.
  File: `execution/quoter.py` (`_CONTRACT_BY_CHAIN`, `_ROUTER_BY_CHAIN`,
  `_DEFAULT_FACTORY_BY_CHAIN`). Effect: QUOTE fails closed off-Base.
- G2 [CORRECTED — NOT A GAP]: gas models EXIST for all 6 chains
  (`chains/gas_model.py` dynamically registers Base + `evm_gas` for
  arbitrum/optimism/ethereum/polygon/bnb, correct L1 flags, fail-closed on no
  RPC; unit-tested by test_phase2_multichain.py). Economics math is chain-generic;
  the missing INPUT is real off-Base quotes (G1).
- G3 (P0): Live wiring Base-hardwired. Files: `runtime/composition.py`
  (`_wire_canonical_flash_loan_scanner`, `build_controlled_live_safety`),
  `scanners/flash_loan_arbitrage/live_quote_provider.py` (`base_venues.CHAIN`,
  `base_pool_registry`).
- G4 (P1): No multichain pool-spec / token-address registry sibling of
  `discovery/base_pool_registry` + `discovery/base_venues`.
- G5 (P1): Non-Base TVL provider absent (only `build_base_tvl_provider`).
- G6 (P2): Route-family executability not proven per (chain,provider,family) —
  currently tags, not verified-executable.
All gaps are fail-closed today (no fabricated capability). Thresholds unchanged.

## 5. Exact explanation of the two test failures
Access caveat: exact worktree bodies/bridge not in this workspace; the analysis
uses the identical Phase-10.10 test bodies present here + the documented bridge
contract. Here (no bridge) all 4 tests pass; the 2 fail only once G5.130 adds
`sync_provider_registry_rpc_from_env()` inside `sync_env_from_network_config`.

Mechanism:
- `test_empty_persistent_leaves_env_alone` asserts `exported == {}` for an EMPTY
  persistent config while a stray `ARBICORE_RPC_URL=https://pre-existing.rpc` is
  set. With the bridge now inside the function, the lifecycle legitimately mirrors
  a canonical RPC into `PROVIDER_RPC_URL_BASE`. If the worktree merges bridge
  output into the returned `exported` dict (or the test also inspects PROVIDER
  keys), `exported` is no longer `{}` → assertion fails. This is a STALE ISOLATION
  ASSUMPTION: the test predates the bridge being part of this function and asserts
  GLOBAL emptiness rather than the ARBICORE-namespace contract it actually targets.
- `test_idempotent` asserts `r1 == r2`. If the bridge reports only keys it
  *changed*, the 2nd call (values already equal) returns a different (smaller)
  export set than the 1st → `r1 != r2`. Idempotency of os.environ END-STATE holds;
  only the returned-dict shape differs. Again a test-shape assumption, not a bridge
  defect.

Classification: **B (stale/incorrect isolation assumptions) + D (PROVIDER_* env
leakage across the combined 3-file validator run)**. NOT A (bridge does not violate
the "single-key, no-fabricated-plural" contract), NOT E (no economics/execution
regression). Consistent with the operator's statement that the bridge is not the
cause.

Smallest correct remediation (to apply IN THE WORKTREE, not here):
1. Add an autouse fixture (or explicit `monkeypatch.delenv`) clearing
   `PROVIDER_RPC_URL[S]_<CHAIN>` and `ARBICORE_RPC_URL_<CHAIN>` for the six chains
   at setup of the Phase-10.10 module → removes cross-suite leakage.
2. Narrow the two assertions to the ARBICORE namespace the tests actually target:
   `test_empty` → assert no `ARBICORE_*` managed keys were exported (filter/inspect
   the ARBICORE keys), not global `exported == {}`.
   `test_idempotent` → assert idempotency over resulting `os.environ` for the
   relevant keys across the two calls (end-state), not raw returned-dict equality.
Do NOT modify the bridge, plural/single semantics, or provider precedence.
Keep this remediation isolated from feature work. NOTE: these two tests already
PASS in THIS checkout (no bridge), so applying the fix here is a no-op/divergence —
it belongs in the G5.79 worktree only.

## 6. Prioritized remaining engineering tasks
- T0: G5.130 test-isolation remediation (worktree only) — closes the 2 failures.
- T1 (P0): Non-Base quoter adapters (real QuoterV2 addresses per chain).
- T2 [REMOVED — gas models already exist for all 6 chains; no work needed].
- T3 (P0): Chain-parameterize live wiring (composition + live_quote_provider),
  Base path regression-frozen.
- T4 (P1): Multichain pool-spec/token-address registry (fail-closed empty per
  unconfigured chain).
- T5 (P1): Non-Base TVL providers.
- T6 (P2): Route-family executability verifier per (chain,provider,family).
- T7 (P2, VPS): 6-chain RPC/provider runtime verification harness (Codex).

## 7. Recommended implementation sequence
T0 (worktree) → T2 (gas models, smallest, unblocks ECONOMICS math) → T1 (quoter
adapters) → T3 (wiring) → T4/T5 (registry+TVL) → T6 → T7. Each step independently
testable; each preserves fail-closed + thresholds + Base behavior.

## 8. Files that would need modification (per task)
- T0: `tests/test_phase10_10_env_sync.py` (worktree).
- T1: `execution/quoter.py`.
- T2: `chains/gas_model.py`, `chains/evm_gas.py`.
- T3: `runtime/composition.py`, `scanners/flash_loan_arbitrage/live_quote_provider.py`.
- T4: new `discovery/multichain_pool_registry.py`, `discovery/multichain_venues.py`.
- T5: new multichain TVL provider module (+ composition wiring).
- T6: `scanners/flash_loan_arbitrage/{strategy_tagging,route_search,verifier}.py`.

## 9. Tests required per change
- T0: module autouse-isolation fixture + narrowed assertions; re-run the 3-file
  validator suite to 32/32.
- T1: per-chain quoter unit tests incl. fail-closed `no_adapter` on unconfigured.
- T2: per-chain gas-model presence + fail-closed None ⇒ DENY.
- T3: Base regression parity + per-chain wiring smoke (fail-closed when chain
  unconfigured).
- T4/T5: registry completeness + empty-fail-closed.
- T6: family-executability truth tests (no theoretical passes).

## 10. Blockers requiring VPS-side (Codex) work
- Real per-chain RPC endpoints to prove T1/T2/T3 live (read-only eth_call).
- 6-chain provider on-chain verification (T7).
- None require signing / broadcast / mode change. Production untouched.
