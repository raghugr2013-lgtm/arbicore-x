# ARBICORE_X_CURRENT_STATE.md
Audit type: READ-ONLY. No code/config/db/service/env/production changes made.

## W. Date/time of audit
2026-08-27 ~14:48 UTC.

## A. Deployment identity
Emergent working repository at `/app` (backend symlinked `/app/backend` → `/app/app/backend`;
frontend `/app/app/frontend`). NOTE: this is the Emergent pod, NOT the VPS. The VPS path
`~/projects/arbicore-x-v2` is NOT reachable from here; this audit reflects the `/app` code state,
which is aligned with the VPS symptoms described (Gate-7 $25 atomic floor + swap-fee double-count
both reproduced here).

## B. Git commit/hash
HEAD `2269aea` · branch `complete-Base-M1-M4-live-shadow-composition` · baseline `6de846f` (ancestor).
Commits since baseline: c339457, b19caa2, 066d641, 2269aea. Working tree clean (only gitignored `.env`).

## C. Modified files (since baseline 6de846f)
Functional: `arbicore/execution/quoter.py`, `arbicore/discovery/base_pool_registry.py`,
`arbicore/config/runtime.py`, `arbicore/chains/gas_model.py`, `server.py`,
`frontend/src/v2/components/AppShell.jsx`; test repairs (t1 gas-model, v2119 cert), plus ~47 benign
preview-URL rewrites.

## D. New files
`tests/test_quoter_rpc_precedence.py`, `tests/test_flash_provider_optimizer.py`,
`reports/{CANONICAL_INTEGRATION_AUDIT,COMPLETION_ADDENDUM,BASE_SHADOW_DRYRUN,READINESS_MATRIX}_2026-06.md`,
`reports/base_dryrun_audit_2.json`, this file + certification matrix.

## E. Configuration
Safety env (preview `.env`, gitignored): ARBICORE_ENV=validator, LIMITED_LIVE=0, FULL_LIVE=0,
AUTOEXEC_AUTOSTART=0, RUNTIME_AUTOSTART=0, MIN_NET_PROFIT_USD=35. No RPC key. No signer key.
Gate-7 atomic floor is code-level (filter.py default $25), NOT from `.env`.

## F. Environment variables (secrets redacted)
MONGO_URL=***, DB_NAME=arbicore, JWT_SECRET=***, ARBICORE_ADMIN_USER=admin/PASS=***,
ARBICORE_OPERATOR_USER=operator/PASS=***. No `ARBICORE_RPC_URL*`, no `*PRIVATE_KEY*`/`*SIGNER*`/`*MNEMONIC*`.

## G. Active services/processes
supervisor: backend RUNNING (uvicorn :8001), frontend RUNNING (:3000), mongodb RUNNING. No scanner
loop active (RUNTIME_AUTOSTART=0). No autoexecutor.

## H. Database/migrations
Mongo `arbicore`. Collections observed: users, login_attempts, scanner_config, scanner_state,
arbicore_opportunities (canonical), evidence_bundles. Scanners seeded DORMANT (enabled=False). No ORM migrations.

## I. RPCs
None configured in preview (fail-closed). Resolver `resolve_rpc_url_from_env(chain)` precedence:
`ARBICORE_RPC_URL_<CHAIN>` > `ARBICORE_RPC_URL` > `<CHAIN>_RPC_URL`. VPS supplies per-chain keys.

## J. DEXes
UniswapV3 (QuoterV2), Aerodrome classic (Router.getAmountsOut, stable/volatile+factory),
Aerodrome Slipstream (QuoterV2 + tick_spacing). Base pool universe via dedicated base_pool_registry.

## K. Flash-loan providers
FLASH_LOAN_PROVIDERS: aave_v3 (5bps, 6 chains), balancer_v2 (0bps, 5 chains no BNB),
uniswap_v3 (tier-resolved, 5 chains), morpho_blue (0bps, eth+base). Optimizer=optimize_flash_provider
(cheapest-feasible, fail-closed).

## L. Quote providers
live_quote_provider → QuoterRegistry (on-chain). gross_profit_pct = 100*(final_out-amount_in)/amount_in
from real RouteQuote (post-fee). Rejects None and `fallback:break_even` (fail-closed).

## M. Scanner
FlashLoanArbitrageScanner (canonical). RouteSearchEngine + triangular. Dormant unless
RUNTIME_AUTOSTART + ARBICORE_SCANNER_FLASH_LOAN_ARB. Legacy live_market/cex_dex/dex_dex opt-in (default OFF).

## N. Gates
Gate 7 = atomic_profit_usd ≥ min_atomic_profit_usd (default **$25**, filter.py). Gate 8 = min route TVL
(onchain_reserves). Gate 9 = MEV/congestion. Universal Gates 2–5. M3 = pre_broadcast final authority.

## O. Economics  ⚠️ SEE KNOWN ISSUES
Authoritative FlashLoan path: FlashLoanEconomicsAssessor.assess → aggregate_economics (subtracts
sum of ALL leg fee_bps, incl per-hop swap_fee legs) → atomic_profit_usd → Gate 7.
Triangular path: multichain_economics.compute_true_net_profit (provider fee subtracted separately;
no swap-fee re-subtraction). Two DISTINCT models.

## P. MEV
Gate 9 via eth_feeHistory gasUsedRatio congestion → risk level. Fail-closed when congestion None.

## Q. Evidence/provenance
evidence_bundles append-only; per-candidate gate results, quote/tvl/provider/economics provenance,
source_data_quality (REAL/VERIFIED_REAL gate for cert executable-rate).

## R. Tests
Offline canonical suites pass (M2/M3 110, Phase-2 95, optimizer 8, quoter 4, regression 182+).
testing_agent iterations 1–3 (76/76+3/3 ; 4/4+49/49 ; 199/199), 0 issues. Full suite has pre-existing
xdist + requests-integration failures (environmental).

## S. Certification status
See ARBICORE_X_CERTIFICATION_MATRIX.md. Base = live read-only dry-run proven (UniV3). 5 chains BLOCKED-BY-RPC.
No LIMITED-LIVE certification.

## T. Known issues
1. **DEX swap-fee DOUBLE-COUNT (CONFIRMED)** in the authoritative FlashLoan verifier path — see §4 report.
   Direction: understates atomic_profit → OVER-rejection (fail-closed-safe, but suppresses genuine ops).
2. Base Aerodrome/Slipstream TVL needs a non-throttled RPC to complete Gate-8 (public RPC throttles).
3. Two parallel economics models (verifier vs triangular) — must document authoritative path (done).

## U. Pending work
Verify+fix double-count (design proposed; NOT implemented pending confirmation). VPS six-chain live
validation. Base aero TVL completion. EmissionBus populated-feed proof.

## V. Exact commands used for verification
`git rev-parse HEAD`; `grep min_atomic_profit_usd filter.py`; read economics.py/economics(base)/verifier.py/
live_quote_provider.py/quoter.py; `grep multichain_economics` (only triangular.py imports it);
`supervisorctl status`; offline pytest of optimizer/quoter/m2/m3/phase2 suites.
