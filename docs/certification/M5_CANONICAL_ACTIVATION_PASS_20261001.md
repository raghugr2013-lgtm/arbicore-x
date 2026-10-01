# M5 Canonical Activation — Independent PASS Manifest

- Status: **PASS** (unconditional for M5 activation scope)
- Certified tip SHA: `05dacdb3eb3cc2f6555aee77b8a9811206891bc5`
- Immediate parent: `b0dbb491b40c0063afb27018be391bc7d6d69e45` (live SHADOW evidence docs)
- Certified extract-port baseline: `861af4d60e841ac8abac5891d663e23986c356ad`
- Extract-port tag: `arbicore-extract-port-pass-20261001`
- Branch: `phase-b/h06-six-chain-runtime`
- Permanent tag: `arbicore-m5-canonical-activation-pass-20261001`
- Certification date: 2026-10-01 (UTC)
- Certifier: independent VPS auditor (detached worktree `/tmp/arbicore-m5-cert-05dacdb`)

## Provenance / ancestry

- Parent of `05dacdb` is exactly `b0dbb491b40c0063afb27018be391bc7d6d69e45`
- `861af4d` **is** an ancestor of `05dacdb` (`git merge-base --is-ancestor` exit 0)
- Log `861af4d..05dacdb`:
  1. `8648770` docs(cert): record extract-port independent PASS for 861af4d
  2. `b0dbb49` docs(cert): record live SHADOW validation evidence on 861af4d
  3. `05dacdb` feat(m5): activate GENERIC_DEX/triangular/Balancer DiscoverySources on canonical scanner

## Diff scope (exactly 15 files)

`git show --stat / --name-status 05dacdb` — **15 files, +1445 / −27**:

| Status | Path |
|---|---|
| M | `app/backend/arbicore/data/scanner_config_defaults.py` |
| M | `app/backend/arbicore/data/scanner_config_repo.py` |
| M | `app/backend/arbicore/providers/rpc.py` |
| M | `app/backend/arbicore/providers/rpc_failover.py` |
| M | `app/backend/arbicore/scanners/flash_loan_arbitrage/__init__.py` |
| A | `app/backend/arbicore/scanners/flash_loan_arbitrage/activation_sources.py` |
| M | `app/backend/arbicore/scanners/flash_loan_arbitrage/live_quote_provider.py` |
| M | `app/backend/arbicore/scanners/flash_loan_arbitrage/scanner.py` |
| M | `app/backend/arbicore/scanners/flash_loan_arbitrage/sources.py` |
| M | `app/backend/arbicore/scanners/flash_loan_arbitrage/triangular.py` |
| M | `app/backend/arbicore/scanners/generic_dex_route_engine.py` |
| M | `app/backend/arbicore/searcher/runtime.py` |
| M | `app/backend/tests/_pending_scanner_activation/test_d6_1_verifier_scanner_sources.py` |
| A | `app/backend/tests/test_m5_canonical_activation.py` |
| A | `docs/certification/M5_CANONICAL_ACTIVATION_20261001.md` |

**PASS-scoped:** activation wiring + infra seams + tests/docs only. No protected execution modules in the diff.

## Protected module blob identity

All blob-identical tip vs parent `b0dbb49` **and** vs extract-port `861af4d`:

| Module | Result |
|---|---|
| `execution/mode.py` | UNCHANGED |
| `execution/live_signer.py` | UNCHANGED |
| `execution/broadcast.py` | UNCHANGED |
| `execution/kill_switch.py` | UNCHANGED |
| `execution/pre_broadcast.py` | UNCHANGED |
| `safety/kill_switch.py` | UNCHANGED |
| `economics/net_profit.py` | UNCHANGED |
| `scanners/flash_loan_arbitrage/exact_size_sizer.py` | UNCHANGED |
| `scanners/flash_loan_arbitrage/filter.py` | UNCHANGED |
| `runtime/composition.py` | UNCHANGED (not in M5 diff) |

## Gate 7 / SHADOW / broadcast

| Check | Result |
|---|---|
| `FlashLoanGate7AtomicProfit` default | `min_atomic_profit_usd = 25.0` (filter.py blob-identical) |
| `GENERIC_DEX MIN_ATOMIC_PROFIT_USD` | `25.0` (immutable floor via `max(MIN_ATOMIC_PROFIT_USD, …)`) |
| `searcher/runtime.py` `g7_floor_usd` | `25.0` (M5 only added `make_eth_get_logs_for_chain_from_env`) |
| Triangular library default | **35 → 25** (aligns *to* Gate 7; never below $25; DiscoverySource path still uses canonical Gate 7) |
| Scanner family default | `flash_loan_arb.enabled = False` |
| Discovery source flags | `generic_dex` / `triangular` / `balancer_v2` config-enabled but dormant until chains/providers/operator state |
| Gate7 VERIFY script | `VERIFY_OK gate7=25 triangular_default=25 scanner_enabled=False` |
| Production docker (`arbicore-x-backend-new`) | `ARBICORE_EXECUTION_MODE=SHADOW`, `ARBICORE_AUTOEXEC_AUTOSTART=false`, `ARBICORE_RUNTIME_AUTOSTART=false` |
| Signing / broadcast | None in M5; protected modules untouched |

## Independent test evidence

Image: `arbicore-x-backend:g5.79-green-20260927`, mount detached `05dacdb` backend at `/app`, `--network none`.

| Suite | Result |
|---|---|
| Suite A — M5 + GENERIC_DEX + Balancer P0/P1/P1b + triangular + RPC reliability | **195 passed** |
| Suite B — M5 + SHADOW route + RPC reliability + D6.1 economics/gates + H06 eth_call gate | **52 passed** |
| Gate7 floor script | `VERIFY_OK gate7=25 triangular_default=25 scanner_enabled=False` |
| Continuity — H05 sizer + H06 six-chain/gate + wave6a mode | **55 passed** |

Suite A files:

- `tests/test_m5_canonical_activation.py`
- `tests/test_generic_dex_route_engine.py`
- `tests/test_generic_dex_gas_integration.py`
- `tests/test_p0_balancer_v2_quote.py`
- `tests/test_p1_balancer_v2_enumeration.py`
- `tests/test_p1b_balancer_v2_onchain_source.py`
- `tests/test_phase2_liquidity_triangular.py`
- `tests/test_phase2_price_oracle_triangular_wide.py`
- `tests/test_rpc_reliability.py`

No tests weakened, deleted, or skipped.

## Prior cert evidence — still valid

| Evidence | Binding |
|---|---|
| H05 exact-size fail-closed | `8fbe599` / `cc3a922` line; sizer blob-identical through M5 |
| H06 six-chain | tag `arbicore-h06-sixchain-pass-20261001` → `7c2b1bc` |
| Balancer P0 / P1 / P1b | `520b0cc` / `76eb003` / `d7e2418` |
| GENERIC_DEX extract-port | `f57e853` / tip `861af4d` + tag `arbicore-extract-port-pass-20261001` |
| Live SHADOW evidence (A=0 profitable) | docs on `861af4d` / `b0dbb49` — pre-activation; engines reused |

M5 is additive DiscoverySource wiring + infra remediation on top of certified extract-port. Library engines remain the certified implementations; Gate 7 / protected execution surface unchanged.

## What M5 certifies (and does not)

**Certifies:** canonical scanner can register GENERIC_DEX / triangular / Balancer DiscoverySources into existing verifier → Gate 7 ($25) → sole `_tick` EmissionBus; getLogs registry failover seam; pathological gas fail-closed as `UNKNOWN_GAS`.

**Does not certify:** profitable live opportunities; production deploy; PAPER / LIMITED_LIVE / AUTOEXEC / RUNTIME enable; continuous six-chain operator-RPC capacity under load.

## Remaining blockers deferred to M6

1. No profitable live opportunity yet (prior SHADOW A=0)
2. Alchemy/operator RPC capacity for continuous six-chain SHADOW
3. Balancer subgraph URLs unset → P1 `DISCOVERY_UNAVAILABLE` until configured
4. Base aero_ss / BNB pancake `no_adapter` gaps
5. Gate 8 TVL fail-closed without chain-scoped TVL provider (non-Base / Balancer)
6. Exact-size sizer env-gated off by default
7. PAPER / LIMITED_LIVE / AUTOEXEC remain intentionally off
8. No signing / broadcast / deploy without explicit approval

## STOP

No paper execution. No live trading. No production deploy. No AUTOEXEC/RUNTIME enable.
Tag `arbicore-m5-canonical-activation-pass-20261001` points **exactly** at `05dacdb3eb3cc2f6555aee77b8a9811206891bc5`.
This manifest commit is intentionally **after** the tagged tip (same pattern as extract-port PASS).
