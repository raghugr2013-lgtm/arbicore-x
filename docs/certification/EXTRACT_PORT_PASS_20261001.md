# Extract-Port Tip — Independent PASS Manifest

- Status: **PASS** (unconditional for extract-port scope)
- Certified tip SHA: `861af4d60e841ac8abac5891d663e23986c356ad`
- Immediate parent: `f57e8538536f4f1921eef3d4739721df4c627e38` (GENERIC_DEX extract)
- Certified H06 baseline: `7c2b1bce4ca97cb3aa753ed9dff6d67a9be168b4`
- Branch: `phase-b/h06-six-chain-runtime`
- Permanent tag: `arbicore-extract-port-pass-20261001`
- Certification date: 2026-10-01
- Certifier: independent VPS auditor (detached checkout `/tmp/arbicore-extract-port-cert-861af4d`)

## Extracted capability commits

| Capability | Implementation SHA | Checkpoint tag |
|---|---|---|
| Balancer P0 (quote adapter) | `520b0cc2351fd5df461b79ff4cf72a19d0b7442e` | `arbicore-p0-balancer-quote-on-h06-20261001` |
| Balancer P1 (enumeration) | `76eb0033325d91767b701b37cde27d427b416d3e` | `arbicore-p1-balancer-enum-on-h06-20261001` |
| Balancer P1b (on-chain source) | `d7e2418415a9a8246268f7bbc92e8bf95aba44fe` | `arbicore-p1b-balancer-onchain-on-h06-20261001` |
| GENERIC_DEX (route engine) | `f57e8538536f4f1921eef3d4739721df4c627e38` | `arbicore-generic-dex-on-h06-20261001` |

Tip `861af4d` is the GENERIC_DEX cert-docs commit atop `f57e853`.

## Provenance / ancestry

- `7c2b1bc` **is** an ancestor of `861af4d`
- Wholesale-source SHAs are **not** ancestors of tip: `f4d4c62`, `f27da21`, `334385e`, `457bad0`
- Delta `7c2b1bc..861af4d`: **15 files, +3560 / −0**, **zero deletions**
- Extracted modules byte-identical to recovered sources; `quoter.py` surgical only (+79 / BalancerV2Quoter + `default_backends` registration)

## Test evidence (docker `arbicore-x-backend:g5.79-green-20260927`, `--network none`)

| Suite | Tip result |
|---|---|
| Balancer P0 (`test_p0_balancer_v2_quote.py`) | 40 passed |
| Balancer P1 (`test_p1_balancer_v2_enumeration.py`) | 36 passed |
| Balancer P1b (`test_p1b_balancer_v2_onchain_source.py`) | 19 passed |
| GENERIC_DEX engine + gas | 53 passed |
| Triangular (`phase2_liquidity` / `price_oracle_triangular_wide` / `strategy_economics`) | 37 passed (in combined) |
| Combined tip (P0+P1+P1b+GENERIC_DEX+H06/H05/SP/mode/Gate7/triangular) | **247 passed** |

Parent baseline separation (`7c2b1bc`):

- H06/H05/safety/triangular + `test_phase10_10_8_live_quoter.py`: **116 passed, 1 failed**
- Identical tip failure: `TestUniV3QuoterV2::test_unsupported_chain` expects `fallback:no_adapter`, observes `fallback:rpc_error` (H06 maps Polygon→UniV3 QuoterV2)
- **Pre-existing on H06; not an extract-port regression.** No tests weakened or deleted.

## Protected safety status

Blob-identical tip vs `7c2b1bc` for:

- `execution/mode.py`, `live_signer.py`, `broadcast.py`, `kill_switch.py`, `pre_broadcast.py`
- `safety/kill_switch.py`
- `economics/net_profit.py`
- `scanners/flash_loan_arbitrage/exact_size_sizer.py`, `filter.py`
- `runtime/composition.py`, `searcher/runtime.py`

Gate 7 default remains `min_atomic_profit_usd = 25.0` (`filter.py`, `searcher/runtime.py`, GENERIC_DEX `MIN_ATOMIC_PROFIT_USD`).

## SHADOW / execution status

- No signing / broadcast / live-execution surface introduced by extract-port
- Flash-loan / searcher defaults remain SHADOW-constrained
- Production env observed at certification (`arbicore-x-backend-new`):
  - `ARBICORE_EXECUTION_MODE=SHADOW`
  - `ARBICORE_AUTOEXEC_AUTOSTART=false`
  - `ARBICORE_RUNTIME_AUTOSTART=false`

## Deployment status

- **No production deploy**, rebuild, or service restart for this certification
- Running backends remain `arbicore-x-backend:g5.79-green-20260927`
- Extract-port is published source only on `phase-b/h06-six-chain-runtime`

## Known limitations (not blocking PASS)

1. No live on-chain Balancer quote/enumeration proof in this cert (offline fail-closed unit tests only)
2. GENERIC_DEX is library-only — not wired into `runtime/composition.py`; no scanner activation; profitable live opportunities not demonstrated
3. `discover_triangular` remains unwired into the production scanner boot path
4. Dual economics pipelines (canonical flash-loan Gate 7 vs OpportunityEngine/scan-once) unresolved architecture residual
5. `reports/READINESS_MATRIX_2026-06.md` documents Gate 7 as `$35` while runtime Gate 7 / filter / GENERIC_DEX floor is `$25` (documentation drift; triangular library emit default `$35` is a separate unwired parameter — see residual report)

## Scope note

This PASS certifies the surgical extract-port onto certified H06 under SHADOW constraints. It does **not** certify Phase C, live trading, production deployment, live Balancer discovery, or profitable GENERIC_DEX opportunities.
