# Workstream B — Capability Delta Plan (read-only audit)

Branch: `engineering/gate9-parallel-93a20c9`  ·  Base: `93a20c9`  ·  Code changes: **NONE** (audit only)
Governing rule honoured: INSPECT → PROVE GAP → (delta plan). No capability was rebuilt. No
capability was reclassified as proven. Gate 9 VPS untouched.

> Scope note: every capability the brief asked about **already exists in code**. The genuine
> "missing pieces" below are overwhelmingly **runtime exercise + SHADOW evidence accumulation +
> independent certification**, or **operator / on-chain actions** — *not* code. No minimal code
> delta is proposed unless a true wiring gap is demonstrated; none was.

---

## Shared substrate (used by all flash capabilities — do NOT rebuild)

| Concern | Existing implementation | Status |
|---|---|---|
| Cycle enumeration | `scanners/flash_loan_arbitrage/route_search.py` — `RouteSearchEngine` depth-bounded DFS, `max_hops=4`, TVL gate, wall/candidate caps | implemented, wired (`scanner.py` L67–75, 239–243) |
| Discovery sources | `.../sources.py` — `RouteSearchDiscoverySource` (emits candidates), `FlashLoanProviderHealthSource` (informational) | implemented, wired |
| Strategy tagging | `.../strategy_tagging.py` — `classify_strategy()` → GENERIC_DEX / STABLECOIN / TRIANGULAR / MULTI_HOP / LST_LRT | implemented, tested |
| Economics | `.../economics.py` (`FlashLoanEconomicsAssessor`, `FLASH_LOAN_PROVIDERS`, `provider_fee_bps`) + `.../multichain_economics.py` (`compute_true_net_profit`) | implemented; double-count fix present |
| Verifier / evidence | `.../verifier.py` (796 L) — per-gate outcomes, `_build_evidence_bundle`, CONFIRMED/DENIED, SHADOW sink | implemented, wired |
| Gates | Gate7 $25 floor, Gate8 liquidity/TVL, Gate9 MEV, freshness (quote-age ≤12s / block-lag) — all in verifier | implemented, fail-closed |

---

## Flash-loan borrow providers (liquidity sources — NOT arb "capabilities"; do NOT rebuild)

`.../provider_liquidity.py` + `.../provider_selection.py` + `economics.py::FLASH_LOAN_PROVIDERS`.

| Provider | Fee | Chains | On-chain read | Classification |
|---|---|---|---|---|
| Balancer V2 | 0 bps (config-verified) | eth/arb/base/op/polygon (singleton Vault `0xBA12…F2C8`) | `read_balancer_liquidity` (hasCode + ERC20.balanceOf on Vault) | implemented, real read |
| Aave V3 | 5 bps | eth/arb/base/op/polygon/bnb (per-chain Pool) | `read_aave_liquidity` (getReserveData → aToken.balanceOf) | implemented, real read |
| Morpho Blue | 0 bps | eth/base (singleton via `MorphoBlueFlashLoanAdapter`) | `_morpho_singleton` resolve | implemented, real read |
| Uniswap V3 | pool-tier (caller-resolved) | eth/arb/base/op/polygon | verifier resolves actual tier | implemented |

**Selection** (`select_flash_loan_provider`): cheapest-feasible, fail-closed — a provider is feasible
only when its liquidity for the borrow asset is **KNOWN and ≥ borrow**; unknown liquidity is never
assumed. **No delta. Do not rebuild. Do not re-wire Aave.**

---

## Capability-by-capability delta

### 1. GENERIC_DEX × Aave/Balancer/Morpho — **strongest proven surface**
- Files: route_search, sources, verifier, economics, provider_liquidity/selection.
- Tests: 3 generic_dex-tagged files + the broad aave(51)/balancer(69)/morpho(16) suites.
- Runtime wiring: `scanner.py` fully wired; M5 activation PASS, M6 SHADOW PASS.
- Evidence: full evidence bundles emitted (CONFIRMED/DENIED).
- Classification: **PROVEN / strongest exercised.**
- Genuine missing piece: **none.**  Minimal delta: **none.**  Certification: already covered by Gate 9 campaign.

### 2. TRIANGULAR — Class C (implemented end-to-end, not yet certified)
- Files: `.../triangular.py` — `enumerate_cycles`, `evaluate_cycle`, `discover_triangular[_multi]`,
  live `UniV3QuoteClient` (real `quoteExactInputSingle`, best-of-fee-tier, fail-closed on unquotable leg),
  true-net via `compute_true_net_profit`, emits `StrategyType.TRIANGULAR` on the **canonical** model
  (no parallel pipeline). $35 net gate; **never lowered**.
- Tests: 11 triangular test files (enumeration + economics + emit).
- Runtime wiring: **GAP (minor).** `route_search` enumerates closed cycles generically, but the
  dedicated `discover_triangular` live enumerator is **not shown wired into the live scanner loop**
  (`scanner.py` references `route_search` only). It is reachable but not exercised in the SHADOW run.
- Evidence: none accumulated (because not exercised).
- Classification: **Class C — keep.** Do NOT reclassify as proven.
- Minimal delta (only if a future gate requires triangular proof): wire `discover_triangular_multi`
  behind an existing per-chain config flag into the scanner's discovery pass (reuse, no new pipeline),
  then let SHADOW accumulate evidence. **No code until that gate is explicitly authorised.**
- Tests required then: one wiring/integration test (config-flag on → triangular candidates flow to
  verifier) + regression that GENERIC_DEX path is unchanged.
- Certification: independent Cursor cert of the wiring commit + a SHADOW evidence window.

### 3. MULTI_HOP (>3 legs) — Class C
- Files: `route_search.py` (`max_hops=4` → structurally enumerates >3-leg cycles) + `strategy_tagging`
  (tags MULTI_HOP) + generic verifier/economics (multi-hop `hop_legs` supported in `economics.assess`).
- Tests: 8 multi_hop-tagged files.
- Runtime wiring: enumerated + tagged + priced through the **generic** route path (no dedicated
  enumerator, by design). Whether 4-hop cycles actually clear gates in practice is **market-dependent**.
- Evidence: whatever the generic path has produced (shared with GENERIC_DEX).
- Classification: **Class C — keep.**
- Genuine missing piece: **none structural.** Minimal delta: **none** (it rides the proven generic path).
  Any "improvement" (hop-specific gas scaling tuning) is NOT justified now.
- Certification: would require a naturally-discovered profitable >3-hop CONFIRMED candidate.

### 4. STABLECOIN — Class D / tagging
- Files: `strategy_tagging.py` (`STABLE_SYMBOLS`, classified when every leg is a stable).
- Tests: 8 stablecoin-tagged files.
- Runtime wiring: **tag only** over GENERIC_DEX/route cycles — no dedicated peg-aware economics.
- Classification: **Class D / tagging — keep.** Do NOT elevate.
- Genuine missing piece: a dedicated peg/stable-spread economic model **is not required** for the
  current campaign. Minimal delta: **none.** (Build only if a roadmap gate demands peg-arb economics.)

### 5. LST_LRT — Class D / tagging
- Files: `strategy_tagging.py` (`LST_LRT_SYMBOLS`; highest-priority tag).
- Tests: 3 lst_lrt-tagged files.
- Runtime wiring: **tag only.** Same posture as STABLECOIN.
- Classification: **Class D / tagging — keep.** Minimal delta: **none.**

### 6. CROSS_CHAIN — detection-oriented; execution NOT proven
- Files: `scanners/cross_chain_arbitrage/*` (`verifier.py`, `transfer_provider.py`), enum
  `CROSS_CHAIN_ARBITRAGE`.
- Tests: 35 cross_chain-tagged files (detection/verification).
- Classification: **detection-only — keep.** Execution requires a separate settlement / inventory /
  solver architecture that does not exist and must not be inferred from same-chain flash capability.
- Delta: **DO NOT BUILD cross-chain execution.** Detection may remain documented/audited only.

---

## Summary ledger

| Capability | Exists | Wired (live) | Tested | Evidence | Class | Code delta now |
|---|---|---|---|---|---|---|
| GENERIC_DEX ×Aave/Bal/Morpho | ✅ | ✅ | ✅ | ✅ | **Proven** | none |
| TRIANGULAR | ✅ (full) | ⚠ not in live loop | ✅ (11) | — | C | none until gate authorises wiring |
| MULTI_HOP | ✅ (generic) | ✅ (generic path) | ✅ (8) | shared | C | none |
| STABLECOIN | ✅ (tag) | tag only | ✅ (8) | — | D/tag | none |
| LST_LRT | ✅ (tag) | tag only | ✅ (3) | — | D/tag | none |
| CROSS_CHAIN | ✅ (detect) | detect only | ✅ (35) | — | detect | **do not build exec** |

**Net recommendation:** no capability code should be written during Gate 9. The only *code* delta
with a demonstrable (minor) wiring gap is TRIANGULAR live-loop wiring — and even that stays frozen
until a roadmap gate explicitly authorises it and Cursor certifies. Everything else is either proven,
rides the proven generic path, is correctly tag-only, or is deliberately detection-only.
