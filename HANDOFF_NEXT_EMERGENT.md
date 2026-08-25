# ArbiCore X — FINAL HANDOFF TO NEXT EMERGENT ACCOUNT

> **This is a FREEZE + HANDOFF document. It is NOT a request to activate live trading.**
> Read this top-to-bottom before touching any code. Production and live execution are FROZEN.

---

## 0. HARD SAFETY FREEZE (do NOT change any of these)

The next Emergent MUST NOT enable or modify any of the following until the full
evidence chain (Section 7) is GREEN and the operator explicitly approves:

- `LIMITED_LIVE` — MUST stay disabled
- `FULL_LIVE` — MUST stay disabled
- signing / private keys — MUST NOT be provisioned
- `eth_sendRawTransaction` / live broadcasting — MUST NOT be enabled
- automatic execution — MUST stay off
- production proxy — MUST NOT be switched
- production container / image — MUST NOT be replaced or promoted

Every failure path in the system MUST remain **fail-closed** (deny + return None).
Do NOT weaken any gate, and do NOT fabricate/mock/default any market data
(prices, TVL, liquidity, congestion, pool addresses) to force a green result.

---

## 1. CURRENT ARCHITECTURE / STATUS

| Component | Status | Notes |
|---|---|---|
| **M1** — Canonical Base pool registry | ✅ DONE | Base pool registry + venues graph in place |
| **M2.1** — Live quote provider | ✅ DONE (proven on real Base RPC) | `make_live_quote_provider` in `arbicore/scanners/flash_loan_arbitrage/live_quote_provider.py`. **FIX applied this session**: now passes venue-specific quote params (`tick_spacing` for Slipstream, `stable` for Aerodrome-classic) so non-UniV3 hops quote genuinely instead of degrading to a fabricated break-even passthrough. |
| **M2.5** — On-chain USD price feed | ✅ DONE (proven on real Base RPC) | `OnChainUsdPriceFeed` — `arbicore/searcher/price_feed.py` |
| **M2.6** — TVL / liquidity provider | ⚠️ DONE but with an OPEN DISCREPANCY | `CachedTVLProvider`. Route quotes execute for Aerodrome/Slipstream, but `canonical_resolved=true` while `real_address=null` and `TVL=null` for those pools (see Section 4). |
| **M3.0** — Atomic pre-broadcast revalidation & circuit breakers | ✅ DONE | `arbicore/execution/pre_broadcast.py` — `PreBroadcastValidator`, `CircuitBreaker`, `SeenOpportunityGuard`. Fail-closed. |
| **M3.0 wiring** — App-level composition | ✅ DONE | `arbicore/runtime/composition.py` `build_controlled_live_safety()` wires validator + breaker into `LimitedLiveBroadcaster`. `require_revalidation=True`. |
| **M3.0 fresh_fn diagnostics** | ✅ DONE this session | Per-stage logging via logger `arbicore.m3_0.fresh_fn`; `_flashloan_available` per-stage logging. Return semantics UNCHANGED (fail-closed). |
| **VPS validation harness** | ✅ DONE this session | `scripts/m3_0_vps_validate.py` — read-only, `confirm=False`, never signs/broadcasts. Adds `_probe_fresh_stages()` step-by-step probe + `FIRST_BLOCKING_STAGE`. |

### Deployment / branch state (FROZEN)
- **Production image/SHA:** `arbicore-x-backend:2.9.2-78b2a8c` — **DO NOT PROMOTE / DO NOT REPLACE**
- **Isolated validator base SHA:** `32d86e6`
- **Branch:** `complete-Base-M1-M4-live-shadow-composition`
- **Live flags:** `LIMITED_LIVE=off`, `FULL_LIVE=off`
- **Signing:** none (no keys provisioned)
- **Proxy:** unchanged (production proxy NOT switched)
- **Automatic execution / broadcasting:** off

---

## 2. PROVEN WORKING ON REAL BASE RPC (VPS isolated validator)

The isolated VPS validator (read-only, no signing, no broadcast) has demonstrated
against **real Base RPC**:

- ✅ Base RPC connectivity
- ✅ `QuoterRegistry`
- ✅ `OnChainUsdPriceFeed`
- ✅ `CachedTVLProvider`
- ✅ live quote provider (`make_live_quote_provider`)
- ✅ `FlashLoanEconomicsAssessor`
- ✅ `PreBroadcastValidator`
- ✅ `CircuitBreaker`
- ✅ Uniswap V3 route quote
- ✅ Aerodrome route quote
- ✅ Aerodrome Slipstream route quote
- ✅ Balancer V2 flash-loan availability
- ✅ fail-closed broadcast protection

**Real VPS Balancer V2 Vault audit (WETH):**
- available ≈ **24.388 WETH**
- required ≈ **4.012 WETH**
- `available = true`

> The M2.1 spec-passthrough fix (Section 1) is confirmed effective: Aerodrome and
> Slipstream hops now return genuine on-chain route quotes on the VPS rather than
> a fabricated passthrough.

---

## 3. CURRENT REAL-BASE BLOCKER (EXACT)

After the M2.1 fix, the route now quotes on real Base RPC, and the fresh
revalidation now fails at a **later** stage:

```
stage = mev

TypeError: float() argument must be a string or a real number, not 'NoneType'
```

**Path:**
```
composition.py
    mev.classify(source_chain_congestion=None, destination_chain_congestion=None, ...)
        ↓
bridge_intelligence.py
    float(source_chain_congestion)   # source_chain_congestion is None → TypeError
```

### DO NOT
- Do NOT invent, hard-code, or default a fake congestion value.
- Do NOT wrap it in a `try/except` that silently substitutes 0 / any placeholder.

### REQUIRED APPROACH
- Identify the **legitimate real source** of `source_chain_congestion`
  (real on-chain/base-fee/mempool/gas telemetry) and wire that real source into the
  MEV assessment at the point `fresh_fn` builds `mev.classify(...)` in
  `arbicore/runtime/composition.py`.
- For an atomic same-chain Base flash-loan arbitrage, confirm what congestion signal
  is even semantically meaningful (this is single-chain atomic, `is_atomic=True`),
  and whether `bridge_intelligence.classify` is the correct assessor for an atomic
  same-chain opp vs. a cross-chain bridge opp. If congestion is not applicable to
  atomic same-chain, the correct fix may be to pass a real Base gas/congestion metric
  OR to route atomic opps through an atomic-appropriate MEV path — NOT to fake a value.
- If the legitimate source is unavailable → the system MUST remain **fail-closed**
  (deny), not proceed with a defaulted value.

---

## 4. SECOND ISSUE — ECONOMICS + TVL/ADDRESS RESOLUTION DISCREPANCY

The current **test** opportunity is economically bad and must continue to be DENIED:
```
gross_profit_pct        ≈ -0.5569%
min_pool_tvl_usd_in_route = 0.0
```

Discrepancy to investigate (do NOT fabricate addresses or weaken gates):
- Aerodrome and Slipstream pools show:
  - `canonical_resolved = true`
  - `real_address = null`
  - `TVL = null`
- …**even though their route quotes execute successfully** on real Base RPC.

### REQUIRED APPROACH
- Investigate the gap between **quote discovery** (which succeeds) and
  **canonical address / TVL resolution** (which returns null).
  - Likely area: Aerodrome/Slipstream `getPool`/pool-resolution path
    (`arbicore/searcher/aero_resolver.py`, `arbicore/discovery/base_pool_registry.py`)
    is not populating `real_address`, so `CachedTVLProvider.get_pool_tvl_usd` has no
    address to read reserves from → TVL null → `min_pool_tvl_usd_in_route=0.0`.
- Do NOT fabricate pool addresses.
- Do NOT weaken the TVL or economic gates. An unprofitable / zero-TVL opp MUST stay DENIED.

---

## 5. DIAGNOSTIC (HARNESS) INCONSISTENCY

The `scripts/m3_0_vps_validate.py` step-probe reported:
```
FIRST_BLOCKING_STAGE = "none - all fresh stages resolved (validation should be GREEN)"
```
while the ACTUAL `fresh_fn` failed at:
```
stage = mev  (TypeError, see Section 3)
```

**Cause:** `_probe_fresh_stages()` does NOT yet replicate the `mev` and `economics`
stages (nor the downstream pre-broadcast gates), so it under-reports.

### REQUIRED
Make the diagnostic probe cover **every actual M3.0 stage**, in the exact order
`fresh_fn` (in `composition.py`) executes them, plus the `PreBroadcastValidator`
gates (in `pre_broadcast.py`):
1. plan shape (`route_pools`, `cycle_token_path` length)
2. pool resolution (canonical id → real address)
3. TVL (per-pool on-chain reserves)
4. head block
5. borrow price (USD)
6. route quote (per-hop status/error)
7. facts / hop_legs
8. **economics** (net profit, gross_profit_pct) ← MISSING
9. **MEV** (`mev.classify`, congestion source) ← MISSING (this is where it actually fails)
10. flash-loan availability (Balancer Vault balanceOf)
11. freshness / reorg / deadline (pre_broadcast gates) ← MISSING
12. profit buffer (pre_broadcast gate) ← MISSING
13. duplicate opportunity (`SeenOpportunityGuard`) ← MISSING

`FIRST_BLOCKING_STAGE` must then reflect the FIRST stage that actually blocks
(matching `fresh_fn` + validator reality). Keep the harness read-only (`confirm=False`).

---

## 6. IMPORTANT — DO NOT CHASE A GREEN TEST ARTIFICIALLY

The goal is **NOT** to make the current (unprofitable) test opportunity pass.
The correct end-to-end chain is:

```
genuine opportunity
    ↓ fresh real market data
    ↓ real quote
    ↓ real TVL / liquidity
    ↓ real MEV assessment
    ↓ real economics
    ↓ ALL safety gates GREEN
```

Only a **genuinely profitable** opportunity may reach GREEN.
An unprofitable / zero-TVL opportunity MUST continue to be DENIED.

---

## 7. REQUIRED NEXT MILESTONE

```
M3.0 real Base validation
    ↓ genuine opportunity reaches GREEN
    ↓ confirm=false dry-run
    ↓ signed_or_broadcast = false
    ↓ broadcast_sent = false
    ↓ safe = true
```
Only AFTER that evidence exists → prepare the **evidence-gated Limited-Live
activation plan** (still no keys, no broadcast, operator approval required).

---

## 8. PRODUCTION MUST NOT BE PROMOTED YET

- Do NOT deploy the validator image to production.
- Do NOT switch the proxy.
- Do NOT replace `arbicore-x-backend:2.9.2-78b2a8c`.
- Do NOT provision signing keys.
- Do NOT enable `LIMITED_LIVE` / `FULL_LIVE`.

---

## 9. NEXT ACTIONS (in order)

**NEXT ACTION #1** — Root-cause and fix the MEV `source_chain_congestion=None`
failure (Section 3). Wire the REAL congestion source (or route atomic same-chain
opps through the correct atomic MEV path). Fail-closed if unavailable. No fake defaults.

**NEXT ACTION #2** — Make `FIRST_BLOCKING_STAGE` in `scripts/m3_0_vps_validate.py`
exactly match `fresh_fn` + `PreBroadcastValidator` execution (add economics, MEV,
freshness/reorg/deadline, profit-buffer, duplicate-guard stages). Section 5.

**NEXT ACTION #3** — Investigate Aerodrome/Slipstream canonical address + TVL
resolution discrepancy (`real_address=null` / `TVL=null` despite successful quotes).
Section 4. No fabricated addresses, no weakened gates.

**NEXT ACTION #4** — Run the isolated real-Base validation harness again on the VPS
(read-only, `confirm=False`).

**NEXT ACTION #5** — Find / validate a genuinely profitable opportunity (real data).

**NEXT ACTION #6** — Perform a complete fail-closed dry-run and confirm:
`signed_or_broadcast=false`, `broadcast_sent=false`, `safe=true`.

**NEXT ACTION #7** — ONLY after all evidence is GREEN, prepare the evidence-gated
Limited-Live activation plan (operator approval + keys handled separately).

---

## 10. KEY FILES

- `arbicore/runtime/composition.py` — `build_controlled_live_safety()`: `fresh_fn`
  (per-stage logging), `_flashloan_available`, and the `mev.classify(...)` call (blocker).
- `arbicore/scanners/flash_loan_arbitrage/live_quote_provider.py` — `make_live_quote_provider._provider`:
  spec-passthrough fix (fee / tick_spacing / stable).
- `arbicore/execution/pre_broadcast.py` — `PreBroadcastValidator`, `CircuitBreaker`,
  `SeenOpportunityGuard` (fail-closed gates).
- `arbicore/searcher/price_feed.py` — `OnChainUsdPriceFeed` (M2.5).
- `arbicore/searcher/aero_resolver.py`, `arbicore/discovery/base_pool_registry.py`,
  `arbicore/discovery/base_venues.py` — pool resolution / TVL address source (Section 4).
- `arbicore/intelligence/bridge_intelligence.py` — `classify()` → `float(source_chain_congestion)` (blocker origin).
- `scripts/m3_0_vps_validate.py` — read-only VPS validation harness + `_probe_fresh_stages()`.
- Tests: `tests/test_m2_1..2_6*.py`, `tests/test_m3_0_pre_broadcast.py`, `tests/test_m3_0_wiring.py`
  (offline; last run 80/80 PASS, iteration_8).

## 11. HOW TO RUN THE READ-ONLY VALIDATOR (VPS, no signing/broadcast)

```
# inside the isolated validator container (real Base RPC env present)
python -m scripts.m3_0_vps_validate '<opportunity_plan_json>'
# → prints JSON audit: fresh_stage_probe.FIRST_BLOCKING_STAGE + verdict{safe, signed_or_broadcast, broadcast_sent}
# confirm=False always → never signs, never broadcasts.
```

Offline preview note: this repo's preview container has NO Base RPC and does NOT
boot the HTTP server (by design). All offline verification is via pytest with
`MONGO_URL=mongodb://localhost:27017 DB_NAME=arbicore_test`.
