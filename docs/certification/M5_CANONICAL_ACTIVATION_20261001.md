# M5 Canonical Activation & Infra Remediation — Checkpoint

- Status: **PASS** (activation wiring; SHADOW / no deploy / no signing / no broadcast)
- Implementation: M5 activation commit on parent below (resolve via `git log -1 --grep='feat(m5)'`)
- Parent SHA: `b0dbb491b40c0063afb27018be391bc7d6d69e45` (docs/harness tip on certified extract-port line)
- Certified baseline preserved: `861af4d60e841ac8abac5891d663e23986c356ad`
- Tag (baseline): `arbicore-extract-port-pass-20261001`
- Date: 2026-10-01
- Scope: M5-A infra seams + M5-B/C/D DiscoverySource activation into canonical scanner

## What changed (surgical)

### M5-A Infra remediation

| Item | Action |
|---|---|
| Polygon / multi-chain RPC capacity | Documented + wired **existing** registry failover: `eth_getLogs` added to `EthJsonRpcProvider` + `RegistryRpcProvider`; Balancer P1b uses `make_eth_get_logs_for_chain_from_env` (same operator-RPC gate as eth_call). Capacity = `PROVIDER_RPC_URLS_<CHAIN>` multi-URL — **quote logic unchanged**. |
| Base/Polygon Balancer getLogs | Fail-closed preserved (`DISCOVERY_UNAVAILABLE` on transport / missing fetcher). No fabricated pools. |
| BNB pathological gas (~1e10) | GENERIC_DEX seam: pathological native USD / gas USD → `UNKNOWN_GAS` (ceilings `_MAX_SANE_NATIVE_USD` / `_MAX_SANE_GAS_USD`). Gate 7 never bypassed. |
| Base/ARB `unknown_gas` | Correct fail-closed when L1 oracle / native price unavailable — not weakened. |

### M5-B GENERIC_DEX activation

- New `GenericDexDiscoverySource` (`flash_loan_generic_dex`) → `build_all_flash_loan_sources`
- Emits 2-hop cross-venue `DiscoveryCandidate`s → existing verifier / Gate 7 / sole `_tick` EmissionBus
- Engine library reused; **no** new emit site; `MIN_ATOMIC_PROFIT_USD=25` immutable

### M5-C Triangular activation

- New `TriangularDiscoverySource` (`flash_loan_triangular`) using `enumerate_cycles` only
- Does **not** call `emit_flash_candidate` / library profit prefilter on the DiscoverySource path
- Library default `min_net_profit_usd` aligned **35 → 25** so Gate 7 remains authoritative
- Canonical Gate 7 floor unchanged at **$25**

### M5-D Balancer P1/P1b activation

- New `BalancerV2DiscoverySource` (`flash_loan_balancer_v2`)
- P1 subgraph: config-aware fail-closed without `ARBICORE_BALANCER_SUBGRAPH_URL_<CHAIN>`
- P1b on-chain: registry-failover `eth_getLogs` when operator RPC configured
- `live_quote_provider`: `_HopPlan` + hop assembly carry `pool_id`/`pool_address`; `_plan_generic_evm` accepts `balancer_v2` **only** with explicit identity (synthetic venue ids rejected)
- Quotes still via existing `BalancerV2Quoter` / P0 — no second quote path

## Files changed

- `app/backend/arbicore/scanners/flash_loan_arbitrage/activation_sources.py` (**added**)
- `app/backend/arbicore/scanners/flash_loan_arbitrage/sources.py`
- `app/backend/arbicore/scanners/flash_loan_arbitrage/scanner.py`
- `app/backend/arbicore/scanners/flash_loan_arbitrage/live_quote_provider.py`
- `app/backend/arbicore/scanners/flash_loan_arbitrage/triangular.py`
- `app/backend/arbicore/scanners/flash_loan_arbitrage/__init__.py`
- `app/backend/arbicore/scanners/generic_dex_route_engine.py`
- `app/backend/arbicore/providers/rpc.py`
- `app/backend/arbicore/providers/rpc_failover.py`
- `app/backend/arbicore/searcher/runtime.py`
- `app/backend/arbicore/data/scanner_config_defaults.py`
- `app/backend/arbicore/data/scanner_config_repo.py`
- `app/backend/tests/test_m5_canonical_activation.py` (**added**)
- `app/backend/tests/_pending_scanner_activation/test_d6_1_verifier_scanner_sources.py`
- `docs/certification/M5_CANONICAL_ACTIVATION_20261001.md` (this file)

**Not modified:** protected execution modules (`mode` / `live_signer` / `broadcast` / `kill_switch` / `pre_broadcast`), GENERIC_DEX/Balancer/triangular **engines** (reuse only), H05/H06 economics floors.

## Tests

| Suite | Result |
|---|---|
| `test_m5_canonical_activation.py` + GENERIC_DEX + Balancer P0/P1/P1b + triangular + Gate7 economics | **195 passed** |
| Gate7 / SHADOW route / RPC reliability / M5 / economics spot | **52 passed** |
| Gate7 floor script | `VERIFY_OK gate7=25 triangular_default=25 scanner_enabled=False` |

Prior extract-port / H05 / H06 / P0 / P1 / P1b / GENERIC_DEX library evidence remains valid (engines unchanged; activation is additive wiring).

## Safety verification

| Check | Result |
|---|---|
| Gate 7 floor | **$25** (`FlashLoanGate7AtomicProfit`, `MIN_ATOMIC_PROFIT_USD`, scanner defaults) |
| SHADOW | Detection-only; no mode ladder promotion in this commit |
| AUTOEXEC / RUNTIME | Scanner default `enabled=False`; no autostart / no AUTOEXEC enable |
| Signing / broadcast | None; no protected module edits |
| EmissionBus | Sole site remains `FlashLoanArbitrageScanner._tick` |
| Divergent Emergent SHAs | Not merged (`f27da21` / `334385e` / `457bad0` / `f4d4c62`) |

## Prior cert evidence — still valid

- H05 exact-size fail-closed (`8fbe599` / `cc3a922` line)
- H06 six-chain (`7c2b1bc` / `7f45ec2`)
- Balancer P0/P1/P1b extract-ports (`520b0cc` / `76eb003` / `d7e2418`)
- GENERIC_DEX extract-port (`f57e853` / `861af4d`)
- Live SHADOW evidence docs on `861af4d` / `b0dbb49` (A=0 profitable)

## New evidence required (post-M5)

1. Live SHADOW re-validation with M5 DiscoverySources registered (operator RPC + optional Balancer subgraph URLs)
2. Polygon capacity proof with `PROVIDER_RPC_URLS_POLYGON` multi-endpoint under load
3. Longer P1b getLogs windows on Base/Polygon with operator Alchemy (not public RPC)

## Remaining M6 blockers (exact)

1. **No profitable live opportunity** yet (prior SHADOW A=0) — economic, not wiring
2. **Alchemy/operator RPC capacity** for continuous six-chain SHADOW (failover exists; endpoints must be provisioned)
3. **Balancer subgraph URLs** unset → P1 correctly `DISCOVERY_UNAVAILABLE` until configured
4. **Base aero_ss / BNB pancake `no_adapter`** — implementation gap; not invented in M5
5. **Gate 8 TVL** for non-Base / Balancer hops still fail-closed without chain-scoped TVL provider
6. **Exact-size sizer** still env-gated off by default (`DENIED_SIZE_NOT_QUOTED` on probe)
7. **PAPER / LIMITED_LIVE / AUTOEXEC** remain intentionally off — M6 only after profitable SHADOW + operator approval
8. **No signing / broadcast / deploy** in this phase

## STOP

No paper execution. No live trading. No production deploy. No AUTOEXEC/RUNTIME enable.
Awaiting explicit review before M6.
