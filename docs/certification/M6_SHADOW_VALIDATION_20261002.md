# M6 Six-Chain SHADOW Validation — Evidence Report

- Status: **PASS (evidence-complete)** — A=0 profitable live opportunities (valid honest outcome)
- Date: 2026-10-02 (UTC labeling; run finished 2026-10-01T19:16:33Z)
- Validation START SHA (pre-evidence): `7ec144009b38fd94f7a0a977b41f4a92abdef750`
- Evidence FINAL SHA (docs/harness only; no certified-module change): `c640481acd73c858db6b9402060956aef2b234e3`
- Branch: `phase-b/h06-six-chain-runtime`
- M5 certified tip: `05dacdb3eb3cc2f6555aee77b8a9811206891bc5`
- M5 tag: `arbicore-m5-canonical-activation-pass-20261001`
- Plan: `docs/certification/M6_SHADOW_VALIDATION_PLAN_20261001.md`
- Machine evidence: `reports/shadow_validation/m6_shadow_latest.json`
- Harness: `scripts/m6_shadow_validation.py` (reuses `scripts/live_shadow_validation.py`)

---

## 1. Exact starting SHA

`7ec144009b38fd94f7a0a977b41f4a92abdef750`  
(`docs(cert): record M5 canonical activation PASS and M6 SHADOW plan`)  
`05dacdb` **is** an ancestor of HEAD (`git merge-base --is-ancestor` exit 0).

## 2. Exact Git branch

`phase-b/h06-six-chain-runtime`

## 3. Working tree status (at validation start)

Clean for tracked certified modules. Untracked only: prior live_shadow JSON stamps, git bundles, and (this phase) M6 harness/evidence outputs before commit.

## 4. M5 certification reference

| Item | Value |
|---|---|
| Manifest | `docs/certification/M5_CANONICAL_ACTIVATION_PASS_20261001.md` |
| SHA | `05dacdb3eb3cc2f6555aee77b8a9811206891bc5` |
| Tag | `arbicore-m5-canonical-activation-pass-20261001` |
| Ancestry | M5 tip is ancestor of validation HEAD |

## 5. Environment safety posture

Observed in validation process (sourced from production SHADOW container + enforced):

| Variable | Value |
|---|---|
| `ARBICORE_EXECUTION_MODE` | `SHADOW` |
| `ARBICORE_SHADOW_CERT_ENABLED` | `true` |
| `ARBICORE_SCANNER_AUTOSTART` | `true` |
| `ARBICORE_AUTOEXEC_AUTOSTART` | `false` |
| `ARBICORE_RUNTIME_AUTOSTART` | `false` |
| H05 `ARBICORE_PRICE_FEED_ENABLED` | `false` |
| H05 `ARBICORE_BORROW_SIZER_ENABLED` | `false` |
| Signing / broadcast / funds / deploy | **not reached / 0 / NO** |

Production container `arbicore-x-backend-new` independently verified SHADOW / AUTOEXEC off / RUNTIME off before the run.

## 6. Six-chain results

Chains exercised: **ethereum, arbitrum, base, optimism, polygon, bnb**.

| Chain | GENERIC_DEX summary | Notes |
|---|---|---|
| ethereum | C=2 | Real RPC; quotes fail-closed on probed pairs |
| arbitrum | C=8 | Quote failures dominant |
| base | B=2, C=5, E=1 | Real economics rejected + `unknown_gas` fail-closed |
| optimism | C=2 | Quote failures |
| polygon | C=6 | Operator Alchemy + multi-RPC failover provisioned |
| bnb | C=6 | Quote failures (no pathological gas treated as profit) |

## 7. GenericDex results

- Path: certified `GenericDexRouteEngine` + live `QuoterRegistry` (same economics surface Gate 7 $25).
- M5 `GenericDexDiscoverySource` **registered** via `build_all_flash_loan_sources` (`flash_loan_generic_dex`).
- DiscoverySource smoke with empty/minimal pool graph → 0 candidates (honest; inventory-dependent).
- Live route evaluations produced real B/C/E buckets — **no synthetic quotes**.

## 8. Triangular results

- `TriangularDiscoverySource` registered (`flash_loan_triangular`).
- Canonical Gate 7 authoritative on DiscoverySource path (`canonical_gate7_floor_usd=25.0` in hint metrics when candidates exist).
- Library `discover_triangular` default `min_net_profit_usd` = **25.0** (aligned to Gate 7).
- **$35 vs $25 drift:** **NONE** on this tip (library default already 25; prior docs drift closed by M5).
- Discovery smoke candidates: 0 (pool inventory empty in harness loader — not fabricated).

## 9. Balancer P1/P1b results

| Chain | P1 subgraph | P1b on-chain (window=50000) | P0 |
|---|---|---|---|
| ethereum | `discovery_unavailable` (URL unset) | `discovery_unavailable` (`HTTPStatusError` resolving latest block — capacity/transport) | `rpc_error` on known 80BAL-20WETH (same transport class; fail-closed) |
| arbitrum | `discovery_unavailable` | `discovery_unavailable` | — |
| base | `discovery_unavailable` | **`ok`** (0 candidates; honest empty window; 26 chunks) | no identity for P0 |
| optimism | `discovery_unavailable` | `discovery_unavailable` | — |
| polygon | `discovery_unavailable` | `discovery_unavailable` | — |

- Subgraph URLs intentionally unset → correct fail-closed `discovery_unavailable`.
- No fabricated pools.
- Prior extract-port SHADOW proved Ethereum known-pool P0 `ok` under different RPC capacity; this M6 window hit Alchemy/HTTP transport errors on ethereum getLogs/P0 — classified as **infrastructure**, not a Gate/safety defect. No certified module patch applied.

## 10. Polygon RPC results

| Check | Result |
|---|---|
| `rpc_explicitly_configured("polygon")` | True |
| `provider_registry_rpc_configured("polygon")` | True |
| Multi-URL provisioned | **Yes** (2): Alchemy + publicnode (validation env) |
| `make_eth_call_for_chain_from_env` | **ok** (`result_present=true`) |
| `make_eth_get_logs_for_chain_from_env` | **ok** (200-block probe, 0 logs) |
| Failures classified | none on this probe |

GENERIC_DEX Polygon still mostly **C** (quote/pool resolution), not “unconfigured RPC”.

## 11. Gas / native-price results

| Chain | E / unknown_gas | Pathological gas treated as A? |
|---|---|---|
| base | E=1 (`unknown_gas`) | **No** — fail-closed |
| ethereum / arbitrum / optimism / polygon / bnb | E=0 this sample | N/A |
| BNB pathological | not observed this sample | would remain non-A |

No gas seam patches applied. Fail-closed preserved.

## 12. Gate 7 results

| Check | Result |
|---|---|
| Floor | **$25.00** |
| `MIN_ATOMIC_PROFIT_USD` | 25.0 |
| Filter default | 25.0 |
| Rejects $24.99 | Yes |
| Accepts $25.00 | Yes |
| Triangular library default | 25.0 (no drift below / above Gate 7) |
| **Verdict** | **PASS — not lowered** |

## 13. Gate 8 / TVL results

| Check | Result |
|---|---|
| Floor | $100,000 min pool TVL |
| Unverifiable TVL (0) | fail-closed deny |
| Weakened for M6? | **No** |
| Note | Missing chain-scoped TVL providers remain a carried blocker; deny rates not converted to passes |

## 14. H05 sizing status

| Item | Status |
|---|---|
| `ARBICORE_PRICE_FEED_ENABLED` | false |
| `ARBICORE_BORROW_SIZER_ENABLED` | false |
| Exact-size path | **disabled_by_environment** |
| Live exact-size execution | **not enabled / not exercised** |

## 15. Counts A/B/C/D/E/F

From GENERIC_DEX live evaluations (`m6_shadow_latest.json` → `economic_evidence`):

| Bucket | Count |
|---|---|
| **A** Real profitable (Gate 7) | **0** |
| **B** Real economically rejected | **2** |
| **C** Quote failures | **29** |
| **D** Liquidity failures | **0** |
| **E** Gas failures | **1** |
| **F** RPC/data failures | **0** |
| **G** Unsupported | **0** |

## 16. Economically rejected categories

- `below_floor_or_nonpos:base` × 2 (real two-leg quotes; net ≤ 0 / below $25)
- `unknown_gas:base` × 1 (gas input deny — fail-closed, not A)

## 17. Infrastructure failure categories

- Quote fail counts per chain (ethereum 2, arbitrum 8, base 5, optimism 2, polygon 6, bnb 6)
- Balancer P1 subgraph unavailable on all Balancer chains (config unset — expected)
- Balancer P1b transport/`HTTPStatusError` on ethereum/arbitrum/optimism/polygon under this window
- Ethereum Balancer P0 known-pool `rpc_error` (capacity/transport; fail-closed)

## 18. Fail-closed events (sample)

Recorded in JSON `fail_closed_events` (9): Balancer P1 unavailable (5 chains) + P1b discovery_unavailable (ethereum/arbitrum/optimism/polygon). Base P1b succeeded as empty-ok. Gate 7/8 probes fail-closed as designed. No synthetic recovery.

## 19. Whether any code was changed

**Certified modules:** NO.  
**Validation harness / evidence:** YES (external) — `scripts/m6_shadow_validation.py` (+ reuse of existing `live_shadow_validation.py`); docs + JSON reports only outside protected execution surface.

## 20. Exact Git diff if code changed

No protected-module diff. Evidence commit scope (intended):

- `scripts/m6_shadow_validation.py` (new harness)
- `docs/certification/M6_SHADOW_VALIDATION_20261002.md` (this report)
- `reports/shadow_validation/m6_shadow_*.json` / `m6_shadow_latest.json`

## 21. Test results

| Suite | Result |
|---|---|
| M5 Suite A analogue (m5 + generic_dex + gas + P0/P1/P1b + rpc + phase2 triangular) | **195 passed** |
| H05 sizer + H06 six-chain/gate + M5 activation continuity | **55 passed** |
| Tests weakened / deleted / skipped | **None** |

## 22. Production safety verification

| Check | Result |
|---|---|
| Execution mode SHADOW | Yes |
| AUTOEXEC off | Yes |
| RUNTIME off | Yes |
| Signing | **NOT REACHED** |
| Broadcast | **0** |
| Funds moved | **0** |
| Production deploy | **NO** |
| Gate 7 $25 | PASS |
| Gate 8 not weakened | Yes |
| M5 sources registered | Yes |

## 23. Final M6 disposition

**PASS (evidence-complete).** Six-chain live SHADOW re-validation after M5 DiscoverySource activation completed honestly with **A=0**. Gate 7 remains $25; Gate 8 fail-closed; H05 exact-size remains env-gated off; signing/broadcast/AUTOEXEC/RUNTIME untouched. Polygon multi-RPC seam exercised successfully. Balancer subgraph remains intentionally unset; ethereum Balancer P0/P1b hit operator-RPC transport limits this window (capacity blocker, not safety regression).

**Remain SHADOW.** Do not promote to PAPER / LIMITED_LIVE / AUTOEXEC / RUNTIME without separate approval and profitable SHADOW evidence under Gate 7.

### Blockers carried (updated)

| # | Blocker | M6 status |
|---|---|---|
| 1 | No profitable live opportunity (A=0) | **Still open** (re-measured) |
| 2 | Alchemy/operator RPC capacity | **Partially mitigated** (Polygon multi-URL ok; ethereum Balancer getLogs/P0 still capacity-sensitive) |
| 3 | Balancer subgraph URLs unset | **Still open** (fail-closed correct) |
| 4 | Base aero_ss / BNB pancake `no_adapter` | **Still open** (not built in M6) |
| 5 | Gate 8 TVL gaps | **Still open** (not weakened) |
| 6 | Exact-size default off | **Confirmed off** |
| 7 | PAPER / LIMITED_LIVE / AUTOEXEC off | **Hard stop held** |
| 8 | No signing / broadcast / deploy | **Hard stop held** |

## STOP

No paper execution. No live trading. No production deploy. No AUTOEXEC/RUNTIME enable.
