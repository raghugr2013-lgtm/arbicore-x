# ArbiCore X — Completion Addendum (3 low-risk items) · 2026-06

Follows `CANONICAL_INTEGRATION_AUDIT_2026-06.md`. SHADOW/PAPER only — no live execution enabled.
Baseline `6de846f` preserved as ancestor; changes are incremental and auditable.

## Item 1 — Repaired 3 stale tests (no production behavior weakened)
- `tests/test_t1_multichain_foundation_adversarial.py::TestGasModelSeam`
  - `test_registry_only_base` → `test_registry_canonical_multichain`: now asserts the seam
    ships genuine per-chain gas models for all 6 canonical chains (arbitrum/base/bnb/ethereum/optimism/polygon)
    via the `evm_gas` layer. The old base-only assertion predated `_register_evm_chains()`.
  - `test_case_insensitive_and_none_chain`: polygon/optimism now assert **non-None** real models
    (were stale None asserts); kept case-insensitivity, None-chain, and no-silent-trimming checks.
  - Also fixed the stale "Only Base ships in this batch" comment in `arbicore/chains/gas_model.py`.
- `tests/test_v2119_shadow_certification.py::test_engine_tick_pass_path`
  - Root cause: engine T0-7 provenance gate (`_REAL_PROVENANCE_VALUES`) counts only REAL/VERIFIED_REAL
    evidence toward `executable_rate`; the in-memory `_FakeEvidenceRepo._append` never set
    `source_data_quality`, so EXECUTABLE rows were excluded → exec_rate 0 → FAIL.
  - Fix is in the TEST FAKE only: `_append` now emits `source_data_quality="REAL"` by default (override supported).
    The engine's fail-closed provenance gate is UNCHANGED (not weakened).
- Result: `test_t1... + test_v2119...` = all pass.

## Item 2 — Base Aerodrome/Slipstream TVL/address resolution (genuine on-chain data, fail-closed)
- Finding: the core §4 propagation fix is ALREADY present at baseline —
  `aero_resolver.resolve_and_propagate()` resolves+validates pools on-chain and persists the REAL
  address via `set_runtime_resolved_address()`; the TVL path (`live_quote_provider._resolve_pool_tvls`)
  reads `canonical_pool_by_id(pid).address`, which picks up runtime-resolved addresses; `fresh_fn`
  calls `resolve_and_propagate` before quoting. Empirical GREEN validation requires a live Base RPC
  (absent in preview — NOT fabricated).
- Genuine latent gap fixed: `base_pool_registry.resolved_addresses()` previously returned ONLY
  `DETERMINISTIC_VERIFIED` (UniV3) pools, silently dropping genuinely on-chain-resolved
  `RUNTIME_RESOLVED` Aerodrome/Slipstream addresses — the exact "resolved on-chain yet
  real_address=null" symptom for any consumer of that accessor. Now returns BOTH tiers (both carry a
  real, validated address) while still excluding unresolved pools (fail-closed; no fabricated address).
- New offline test: `tests/test_m2_6_aero_resolution.py::test_resolved_addresses_includes_runtime_resolved_pools`.
- Regression: M2.1/M2.2/M2.6/M3-TVL suites all pass.

## Item 3 — Canonical EmissionBus Opportunities view is the default landing
- `frontend/src/v2/components/AppShell.jsx`: index route `/dashboard` → `<Navigate to="opportunities" replace/>`
  (was `<OpsCenter/>`, which surfaced the SEPARATE legacy MID feed). Legacy OpsCenter remains at `/dashboard/ops`.
- OpportunitiesPage consumes canonical `GET /api/arbicore/opportunities` (`source:"canonical"`); shows an
  honest empty-state (no fabricated rows) since scanners are not running in SHADOW preview.

## Tests run (this session)
- `test_t1_multichain_foundation_adversarial.py` + `test_v2119_shadow_certification.py`: pass.
- `test_m2_6_aero_resolution.py` (+ new test), `test_m2_1`, `test_m2_2`, `test_m3_tvl_composition`,
  phase2 liquidity/multichain/economics: pass.
- testing_agent (iteration_1): backend 76/76 pytest + 3/3 curl; frontend 5/5 scoped checks; 0 critical, 0 minor.

## Exact environment delta for a SHADOW-only activation DRY RUN (NOT enabled now)
Keep ALL execution controls OFF (unchanged):
```
ARBICORE_ENV=validator
ARBICORE_LIMITED_LIVE=0
ARBICORE_FULL_LIVE=0
ARBICORE_AUTOEXEC_AUTOSTART=0
ARBICORE_MIN_NET_PROFIT_USD=35
```
To bring canonical scanners into SHADOW detection (detection-only; emission still gated by
economic/atomic/MEV gates; execution still impossible — no signer, no broadcaster, AutoExecutor off):
```
# master runtime gate (currently 0/off — flip to 'on' only for the dry run)
ARBICORE_RUNTIME_AUTOSTART=on
# per-scanner gates (enable the families you want to observe)
ARBICORE_SCANNER_CEX_ARB=on
ARBICORE_SCANNER_FUNDING_ARB=on
ARBICORE_SCANNER_DEX_ARB=on
ARBICORE_SCANNER_FLASH_LOAN_ARB=on
ARBICORE_SCANNER_LAUNCH_ARB=on          # also needs HELIUS_API_KEY to confirm canonicals
ARBICORE_SCANNER_CROSS_CHAIN_ARB=on     # also needs transfer + chain-liveness providers injected
```
For REAL flash-loan quotes/TVL during the dry run (fail-closed without it — never fabricated):
```
ARBICORE_RPC_URL_BASE=<base rpc>        # or ARBICORE_RPC_URL for the default chain
ARBICORE_USD_NUMERAIRE=USDC             # enable the M2.5 on-chain USD price feed
# optional Aerodrome factory overrides if non-default:
# ARBICORE_AERO_POOL_FACTORY_BASE=... ARBICORE_AERO_CL_FACTORY_BASE=...
```
Then call `activate_canonical_flash_loan_scanner(quoter_registry)` (wires the live Base quote provider).
Verify boot log shows scanners started and `flash_loan_quote_readiness` = ready/active with a live (not noop) quote provider.
Legacy MID pipelines remain OFF unless `LIVE_MARKET_AUTOSTART=1` / `CROSS_AUTOSTART=1` are set (recommend leaving OFF).

## Safety confirmation (unchanged)
LIMITED_LIVE OFF · FULL_LIVE OFF · AUTOEXEC OFF · no signer · no signing · no broadcast ·
no execution/gate bypass · fail-closed intact · no fabricated market data · baseline `6de846f` preserved.
