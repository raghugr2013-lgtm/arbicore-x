# ArbiCore X — Canonical Integration & Multi-Chain Readiness Audit

Baseline (immutable): branch `complete-Base-M1-M4-live-shadow-composition`, HEAD `6de846f`
("Recover multichain flash loan discovery layer"). No reset/revert/force-push performed.
Working-tree changes at checkpoint = preview-URL rewrite only (`arbitrum-launch-1`→`elated-banach-10`); preserved.

---

## A. Current Git commit / branch
- Branch: `complete-Base-M1-M4-live-shadow-composition`
- HEAD: `6de846f` (immutable baseline, unchanged)
- Working tree ahead of prior Phase-2 commit `0987357` by 4 commits (0987357 → 0f42dd8 → 19f00d4 → 6de846f). Repo is AHEAD of the previously-known Phase-2 state.

## B. Already implemented (verified present, not just class-exists)
- Canonical runtime composition (`runtime/composition.py`): lazy singletons, EmissionBus, all 6 scanner factories, M3 safety wiring (`build_controlled_live_safety`), evidence sinks, SHADOW route.
- All 6 arbitration families implemented + wired: cex/funding/dex/launch/cross_chain/flash_loan (`arbicore/scanners/*`).
- Flash-loan family is deepest: route_search, triangular, provider_liquidity, provider_selection, flash_provider_optimizer, multichain_economics, ranking, tvl_provider, live_quote_provider, verifier, shadow_route.
- Provider registry/bootstrap: 47 providers (rpc=7, dex=13, cex=6, quote=12, gas=6, metadata=1) across all 6 chains.
- Chain registries (`chains/registries.py`): ethereum/arbitrum/base/optimism/polygon/bnb tokens + DEX factories (no fabricated pools; resolved on-chain).
- Gates: universal 2–5 (`gates/universal.py`); Gate 7 atomic-profit / Gate 8 real-TVL / Gate 9 flash-loan+MEV in flash-loan verifier; M3 authority (`execution/pre_broadcast.py`: PreBroadcastValidator, CircuitBreaker, SeenOpportunityGuard).
- Economics: FlashLoanEconomicsAssessor, chain gas models (all 6), Base L1 GasPriceOracle all-in cost, ROIProbabilityEngine. $35 min-net gate intact.
- Price/TVL: OnChainUsdPriceFeed (M2.5), CachedTVLProvider (M2.6) — fail-closed.
- Evidence: `evidence_bundles` append-only store + signer/verifier; PaperEvidenceRepository.
- Shadow certification engine (`certification/engine.py`) + Paper Validation framework.
- Auth (canonical `users` coll, session cookie, bcrypt, persisted brute-force lockout).
- Frontend v2 (active tree) consuming canonical `/api/arbicore/opportunities`.

## C. Actually missing / dormant / gaps found
- No `.env` files were checkpointed (gitignored) → app could not boot until created. FIXED (local SHADOW `.env`).
- Backend python deps not installed in the venv → FIXED (`pip install -r requirements.txt`).
- Legacy OBSERVE pipelines (`live_market`, `cex_dex`, `dex_dex`) autostarted by DEFAULT and feed a SEPARATE legacy MID store — a parallel opportunity feed distinct from the canonical EmissionBus. This is the duplicate-pipeline risk. FIXED (made opt-in, default OFF).
- Scanner families are DORMANT by default (correct posture) — SHADOW activation requires explicit env (see Q).
- launch_arb venue_provider, cross_chain transfer/liveness providers, funding depth_fetcher are None until operator injects them (verification gap by design).
- 3 stale tests encode pre-multichain / pre-provenance-hardening assumptions (see L/M).

## D. Files changed
- `app/backend/.env` (NEW, local, gitignored) — SHADOW-safe config + auth.
- `app/frontend/.env` (NEW, local, gitignored) — REACT_APP_BACKEND_URL.
- `app/backend/server.py` — legacy `LIVE_MARKET_AUTOSTART`/`CROSS_AUTOSTART` default "1"→"0" (opt-in), with comments.
- `app/backend/arbicore/config/runtime.py` — matching informational defaults →False.

## E. Files intentionally left untouched
All canonical logic: composition.py, every scanner/verifier, gates, economics, price/TVL feeds,
pre_broadcast (M3), evidence, certification, execution adapters/broadcaster, contracts, deployment configs.
NO test was weakened or edited. Baseline commit untouched.

## F. Scanner readiness matrix
| Family | Class | Wired | EmissionBus | Boot state | SHADOW-ready | Executable | Missing piece |
|---|---|---|---|---|---|---|---|
| cex_arb | CEXArbitrageScanner | yes | yes | dormant | yes (CoinGecko ticker src) | no | — |
| funding_arb | FundingArbitrageScanner | yes | yes | dormant | yes | no | order-book depth_fetcher |
| dex_arb | DEXArbitrageScanner | yes | yes | dormant | yes | no | operator graduates sources |
| launch_arb | LaunchArbitrageScanner | yes | yes | dormant | partial | no | HELIUS venue_provider |
| cross_chain_arb | CrossChainArbitrageScanner | yes | yes | dormant | partial | no | transfer + chain_liveness providers |
| flash_loan_arb | FlashLoanArbitrageScanner | yes | yes | detection-on (noop quote) | yes (activate_* wires live) | no | live quote provider + Base RPC |

## G. Chain readiness matrix
| Chain | Registry | Providers | Gas model | active_ready (preview) | Notes |
|---|---|---|---|---|---|
| ethereum | yes | yes | yes | NO (no RPC → fail-closed) | phase2 report present |
| arbitrum | yes | yes | yes | NO | phase2 report present |
| base | yes | yes | yes | NO in preview / proven on real Base RPC (VPS) | M1–M3 validated on VPS |
| optimism | yes | yes | yes | NO | phase2 report present |
| polygon | yes | yes | yes | NO | phase2 report present |
| bnb | yes | yes | yes | NO | phase2 report present |
All chains fail-closed (NOT active_ready) without a live RPC — correct.

## H. Provider readiness matrix
- 47 providers registered at boot (rpc=7, dex=13, cex=6, quote=12, gas=6, metadata=1), all 6 chains.
- Flash-loan borrow providers (`FLASH_LOAN_PROVIDERS`): balancer_v2 (0 bps), morpho_blue (0 bps), aave_v3 (5 bps), uniswap_v3 (pool tier).
- `provider_selection.py`: cheapest-feasible, fail-closed — a provider is feasible only if its liquidity for the borrow asset is KNOWN and ≥ borrow amount. Unknown liquidity never assumed sufficient.

## I. Price / TVL / liquidity status
- Native/stable USD price: OnChainUsdPriceFeed (USDC-denominated, peg-band + freshness + block-lag guarded). None → deny.
- TVL/liquidity: CachedTVLProvider from on-chain reserves; provenance `onchain_reserves`. None → Gate 8 fail-closed.
- OPEN DISCREPANCY (Base, requires real RPC): Aerodrome/Slipstream `real_address`/`TVL` null despite successful route quotes → those routes stay DENIED (correct). See `HANDOFF_NEXT_EMERGENT.md §4`.

## J. Arbitration-family status
DISCOVERABLE: all 6. VERIFIABLE: all 6 once their provider is wired (flash_loan fully verifiable on Base).
ECONOMICALLY VALID + SIMULATABLE: flash_loan on Base (SettlementSimulator/AtomicExecutorSimulator).
EXECUTABLE: NONE (by design — see S).

## K. Execution coverage matrix
| Family | Chain | Quote | Sim | Exec adapter | Signing | Broadcast | Status |
|---|---|---|---|---|---|---|---|
| flash_loan | base | live (on activate) | yes | present (dormant) | none | none | SIMULATABLE, NOT executable |
| flash_loan | other 5 | live (RPC-gated) | partial | present | none | none | DISCOVERABLE/VERIFIABLE |
| dex/cex/funding/launch/cross | all | provider-gated | n/a | n/a | none | none | DISCOVERABLE/VERIFIABLE |
No family is EXECUTABLE: no signer, LIMITED_LIVE/FULL_LIVE off, AutoExecutor off, SHADOW pipeline has no broadcaster.

## L. Tests run
- Canonical offline (with `MONGO_URL`/`DB_NAME=arbicore_test`): M2/M3 (110), Phase-2 (95), regression subset (77) — all green.
- Full suite: 2445 collected.

## M. Tests passed / failed
- Full suite: **2208 passed, 146 skipped**, 238 "failed" + 234 "errors".
- After isolating: the vast majority of failed/errors are (a) xdist parallel-worker "event loop is closed" artifacts (pass when run without `-n`), and (b) `requests`-based integration tests needing external routing + seeded auth.
- Genuine offline failures = 3, all STALE (predate current architecture; NOT regressions, NOT weakened):
  1. `test_t1_multichain_foundation_adversarial::TestGasModelSeam::test_registry_only_base` — asserts gas model supports only `["base"]`; system is now canonical multi-chain (all 6).
  2. `...::test_case_insensitive_and_none_chain` — same base-only assumption.
  3. `test_v2119_shadow_certification::test_engine_tick_pass_path` — in-memory fake evidence omits the REAL/VERIFIED_REAL provenance the hardened engine now requires to count executables (engine correctly fail-closed).

## N. Remaining failures
- The 3 stale tests above (recommend repairing to match canonical multi-chain + provenance reality — repair, not weaken).
- Integration/e2e `requests` tests require the VPS/preview external routing + seeded creds to pass.

## O. Exact VPS configuration changes required
Keep all safety values as-is:
```
ARBICORE_ENV=validator
ARBICORE_LIMITED_LIVE=0
ARBICORE_FULL_LIVE=0
ARBICORE_AUTOEXEC_AUTOSTART=0
ARBICORE_RUNTIME_AUTOSTART=0
ARBICORE_MIN_NET_PROFIT_USD=35
```
NEW (behavioral note from this audit — legacy pipelines now opt-in):
```
# Legacy OBSERVE pipelines now default OFF. To retain the old OpsCenter
# "live/MID" panels, explicitly set on the VPS:
LIVE_MARKET_AUTOSTART=1   # only if you WANT the legacy MID feed
CROSS_AUTOSTART=1         # only if you WANT the legacy cex_dex/dex_dex feed
# Recommended: leave BOTH unset (OFF) so only the canonical EmissionBus feed exists.
```
No secrets in source. Provide JWT_SECRET + ARBICORE_ADMIN_USER/PASS + ARBICORE_OPERATOR_USER/PASS
via VPS env (never commit). Provide per-chain `ARBICORE_RPC_URL_*` to move chains toward active_ready.

## P. Exact commands to deploy safely
1. Pull branch, keep HEAD at/above `6de846f` (do not reset).
2. Ensure VPS `.env` has the safety values in (O) and NO signer key.
3. `pip install -r app/backend/requirements.txt`; build frontend with `REACT_APP_BACKEND_URL` set.
4. Start via existing supervisor/systemd (no uvicorn-by-hand). Confirm `/api/` = 200.
5. Verify boot log: `runtime_config loaded: ... autostart_live=False autostart_cross=False` and NO `live_market: autostarted`.

## Q. Exact SHADOW activation procedure (detection only, no execution)
On the VPS, to bring canonical scanners into SHADOW detection:
```
ARBICORE_RUNTIME_AUTOSTART=on
ARBICORE_SCANNER_CEX_ARB=on
ARBICORE_SCANNER_FUNDING_ARB=on
ARBICORE_SCANNER_DEX_ARB=on
ARBICORE_SCANNER_LAUNCH_ARB=on          # needs HELIUS_API_KEY to confirm
ARBICORE_SCANNER_CROSS_CHAIN_ARB=on     # needs transfer/liveness providers
ARBICORE_SCANNER_FLASH_LOAN_ARB=on
```
Then flash-loan live quotes: call `activate_canonical_flash_loan_scanner(quoter_registry)`
(requires Base RPC env). Detection-only; emission gated by economic/atomic/MEV gates; execution gated by mode ladder + AutoExecutor (all OFF). Substrate (indexes + dormant scanner_config/state) is seeded unconditionally at every boot regardless of these flags.

## R. Remaining blockers before LIMITED LIVE
1. Real-Base Aerodrome/Slipstream address+TVL resolution (Gate 8) — no fabrication.
2. A genuinely profitable real opportunity reaching GREEN end-to-end with `confirm=False` dry-run (`signed_or_broadcast=false`, `broadcast_sent=false`, `safe=true`).
3. Evidence-gated LIMITED-LIVE activation plan + operator approval + secure key provisioning (separate, out of scope here).

## S. Explicit safety confirmation
- LIMITED_LIVE: OFF. FULL_LIVE: OFF. AUTOEXEC: OFF.
- No signer provisioned. No signing enabled. No transaction broadcast.
- No execution bypass. No safety-gate bypass. Fail-closed behavior preserved everywhere.
- No market data / liquidity / opportunities fabricated. Baseline commit `6de846f` unchanged.
