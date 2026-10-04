# Emergent Design Reconciliation — 2026-10-04

**Scope:** READ-ONLY design reconciliation of Emergent Phase-1 findings **B1 / B2** and Polygon `venue_unreadable` against certified baseline **`9ed2718b3550066934bd11e99a96503ce75a499f`**.  
**Runtime:** container `arbicore-x-backend-new` · image `arbicore-x-backend:flash-discovery-readiness-9ed2718` · `BUILD.git_sha = 9ed2718b3550066934bd11e99a96503ce75a499f`.  
**Constraints honored:** no implementation, deploy, restart, Network Config / RPC change, shadow start, sign, or broadcast.

---

## Verdict fields (required)

1. **B1 confirmed against 9ed2718:** **YES**
2. **B2 confirmed against 9ed2718:** **YES**
3. **B1 preconditions:** **PARTIAL**
4. **Polygon current classification:** **E** (stale/transient historical VU; live re-probe quotes OK) — proximate historical cause was **A** (RPC 529/429)
5. **Difference vs Emergent pod findings:** none material on B1/B2 shape; prior empty-`_backends` probe was a mis-key artifact (dex-keyed registry). Polygon SP-5 resolve timed out on live publicnode/Alchemy — ops/RPC, not a missing H05 builder.
6. **B1 implementation should proceed:** **YES** — wire existing `build_h05_borrow_sizer` into canonical flash-loan scanner; Base-only gap confirmed; structural deps largely present.
7. **B2 implementation should proceed:** **YES** — claim starvation confirmed; Emergent additive chain field / index / fair-claim matches the gap.
8. **Polygon requires a code fix:** **NO** — live quote re-probe succeeded (`status=ok`); historical VU treated as stale/transient (E), proximate cause A (RPC).

---

## 1. B1 — Base-only exact-size sizer wired; H05 unused

**Confirmed: YES** against `/app` on BUILD `9ed2718…` (line refs match workspace checkout of the same functions).

| Symbol | Role on 9ed2718 |
|--------|-----------------|
| `_wire_canonical_flash_loan_scanner` | Canonical flash-loan scanner wiring; injects borrow sizer into `make_live_quote_provider` |
| `_build_base_exact_size_borrow_sizer` | **Live path** — wraps Base feed only: `MultichainPriceSource({"base": price_feed})` |
| `build_h05_borrow_sizer` | Present; **not** called from `_wire_canonical_flash_loan_scanner` |
| `build_multichain_price_source` | Present; builds six-chain `MultichainPriceSource` via `_H05_CHAINS` |
| `build_multichain_quote_provider` | Present (SP-3 seam); not required for B1 wire swap itself |
| `_H05_CHAINS` | `('ethereum','arbitrum','base','optimism','polygon','bnb')` |

**Live evidence (docker inspect / prior probe):**
- `ARBICORE_BORROW_SIZER_ENABLED=true`, `ARBICORE_PRICE_FEED_ENABLED=true`
- `WIRE_CALLS_BASE_SIZER=True`, `WIRE_CALLS_H05=False`, `BASE_ONLY_WIRE=True`
- Secondary Base-only call site also exists in controlled-live safety wiring (`borrow_sizer = _build_base_exact_size_borrow_sizer(price_feed)` ~L517)

**Proposed B1 replacement validity:** **YES** on 9ed2718.  
`_wire_canonical_flash_loan_scanner` is already `async`; replace  
`borrow_sizer=_build_base_exact_size_borrow_sizer(price_feed)`  
with  
`borrow_sizer=await build_h05_borrow_sizer(quoter_registry)`  
(or equivalent that binds the six-chain price source). Keep env gates + fail-closed probe denial (`denied:size_not_quoted`). `make_live_quote_provider` already accepts async `borrow_sizer`.

---

## 2. B2 — Discovery queue has no chain-fair claim

**Confirmed: YES** against code + live Mongo `arbicore_discovery_candidates`.

### Model
- `DiscoveryCandidate` (`models/discovery.py`): **no** top-level `chain` field; chain lives in `hint_metric.chain`.
- Outcome tag `VerifiedOutcome.DENIED_VENUE_UNREADABLE = "denied:venue_unreadable"`.

### Indexes (live + `DiscoveryQueue.ensure_indexes`)
- `candidate_id` unique  
- `(opportunity_type, claimed_until, expires_at)`  
- `(hint_source, hint_observed_at)`  
- `expires_at` TTL (`expireAfterSeconds: 0`)  
- **No chain index**

### Claim path
- `DiscoveryQueue.claim_batch` (`data/discovery_queue.py`): filter = `verified_outcome is None` + `expires_at > now` + claim lock free; **no chain filter, no sort, no fair scheduling, no per-chain quota**.
- `upsert_many`: `$setOnInsert` by `candidate_id` only.

### Starvation evidence (Mongo, certified runtime)
- `CLAIMED_BY_CHAIN_6H`: only `[('base', 3)]` (in-flight `claimed_at`; note `mark_processed` clears claim locks, so verified-at histograms are stronger long-run evidence).
- `LAST_6H` shape: base has Gate-7 failures + VU; ethereum has VU + `size_not_quoted`; arbitrum/optimism/bnb/polygon mostly **UNPROCESSED**; polygon `poly_vu_all=32`, `poly_vu_6h=32`, `poly_unprocessed_eligible≈3012`.

**Emergent additive design** (top-level or indexed chain + fair-claim / round-robin) **matches** this gap on 9ed2718.

---

## 3. B1 preconditions — PARTIAL

Structural constructibility is largely **PASS**; classification is **PARTIAL** because live Polygon SP-5 resolve hit **TimeoutError** (publicnode **529** / Alchemy **429** during price-source build). Do not treat that flake as missing H05 builders.

### QuoterRegistry
- **Not** chain-keyed: `QuoterRegistry._backends` is **dex → backend**.
- Prior probe reporting empty backends per chain was a **mis-key artifact** (looking up chain names in a dex map).
- Default `supported_dexes` on 9ed2718:  
  `uniswap_v3`, `aerodrome`, `aerodrome_slipstream`, `balancer_v2`, `camelot_v3`, `pancakeswap_v3`, `quickswap_v3`, `sushiswap_v2`, `sushiswap_v3`.
- RPC primary set for all six: ethereum, arbitrum, base, optimism, polygon, bnb.

### Per-chain precondition matrix (certified runtime probes)

| Chain | QR backends / dexes | Price feed (`build_multichain_price_source`) | SP-5 / USDC pools | Notes |
|-------|---------------------|----------------------------------------------|-------------------|-------|
| ethereum | present (shared dex set) | yes (`_pair_pool` USDC pairs≈5) | resolve 27 / USDC meta 10 | OK |
| arbitrum | present | yes (USDC pairs≈13) | resolve 55 / USDC 26 | OK |
| base | present | yes (USDC pairs≈7) | static `_base_price_pools` 19 / USDC 9 | OK |
| optimism | present | yes (USDC pairs≈13) | resolve 52 / USDC 25 | OK |
| polygon | present | yes (USDC pairs≈11; feed still built) | **TimeoutError** on SP-5 resolve (25s); publicnode 529 / Alchemy 429 | **PARTIAL** — RPC |
| bnb | present | yes (USDC pairs≈5) | resolve 26 / USDC 10 | OK |

### Other
- `build_multichain_quote_provider`: exists; **callable for all six** chains.
- `build_h05_borrow_sizer`: **constructed successfully** in earlier probe (callback returned).
- Wrong-attr probe (`n_pools=None` / `USDC_POOLS=0`) was looking for `_pools` on feeds; real attrs are `_pair_pool` + `_addr` (USDC present in token maps).

**Preconditions verdict: PARTIAL** (lean constructible / nearly PASS; hold PARTIAL on polygon SP-5 timeout).

---

## 4. Polygon `denied:venue_unreadable` — classification **E**

### Evidence
- Historical Mongo: `poly_vu_all=32` = `poly_vu_6h=32` at earlier probe (all then in-window); subjects include `aave_v3` / `balancer_v2` / `uniswap_v3` polygon WETH/USDT routes; `reason` prefix `flash_loan_route_search:polygon:...`.
- Verifier path (`flash_loan_arbitrage/verifier.py`): falsy `quote_provider` facts → plain `denied:venue_unreadable`.
- Proximate historical ops: publicnode **529** / Alchemy **429** during SP-5 / price-source (SP-5 resolve TimeoutError) — cause class **A** at the time of those VU rows.
- **Live re-probe (exit 0, BUILD `9ed2718…`):** subject `aave_v3` polygon WETH 4-hop `uniswap_v3` route; publicnode **529** failover still observed; then `make_live_quote_provider` → `status=ok`, `size=probe`, `hops=4`, `chain=polygon` (21.57s); multichain QP also `ok`.

### Classification
- **E — stale/transient historical VU; live re-probe quotes OK.**
- Proximate historical cause: **A** (RPC 529/429). Not treated as a standing venue/quote code defect on current runtime.

### Code fix?
**NO** — strengthened by live quote success. No Polygon-specific product fix on this evidence.

---

## 5. Emergent pod vs certified 9ed2718 — deltas

| Topic | Emergent / prior pod | Certified 9ed2718 |
|-------|----------------------|-------------------|
| B1 Base-only wire | Claimed | **Confirmed** (`_build_base_exact_size_borrow_sizer` in `_wire_canonical_flash_loan_scanner`) |
| B1 H05 builders present unused | Claimed | **Confirmed** (`build_h05_borrow_sizer`, `build_multichain_price_source`, `_H05_CHAINS`) |
| B2 no chain-fair claim | Claimed | **Confirmed** (`DiscoveryQueue.claim_batch` + Mongo indexes/model) |
| Empty quoter backends | Some probes reported empty per-chain maps | **Artifact**: `_backends` is dex-keyed; defaults populated |
| Polygon VU | Current-window VU / RPC concern | Live re-probe quotes **OK** → classify **E** (stale/transient); proximate historical **A** RPC |

No material design disagreement on B1/B2. Polygon needs no code fix on this baseline (E; historical A).

---

## 6–8. Proceed recommendations

| # | Item | Proceed? | Why |
|---|------|----------|-----|
| 6 | **B1** | **YES** | Gap is wiring-only; H05 builders + env gates already on 9ed2718; preconditions largely present; polygon SP-5 flake is RPC, not missing sizer code. |
| 7 | **B2** | **YES** | Clear multi-chain starvation under unfair `claim_batch`; Emergent additive chain field/index/fair-claim matches the certified gap. |
| 8 | **Polygon code fix** | **NO** | Classification **E** (live quotes OK); historical VU proximate **A** (RPC). Live re-probe success strengthens no-fix. |

---

## Evidence anchors (function / artifact names)

- `arbicore.runtime.composition._wire_canonical_flash_loan_scanner`
- `arbicore.runtime.composition._build_base_exact_size_borrow_sizer`
- `arbicore.runtime.composition.build_h05_borrow_sizer`
- `arbicore.runtime.composition.build_multichain_price_source`
- `arbicore.runtime.composition.build_multichain_quote_provider`
- `arbicore.runtime.composition._H05_CHAINS`
- `arbicore.execution.quoter.QuoterRegistry` (`_backends`, `supported_dexes`, `quote_route`)
- `arbicore.data.discovery_queue.DiscoveryQueue` (`ensure_indexes`, `upsert_many`, `claim_batch`)
- `arbicore.models.discovery.DiscoveryCandidate` / `VerifiedOutcome.DENIED_VENUE_UNREADABLE`
- `arbicore.scanners.flash_loan_arbitrage.verifier` (falsy facts → `denied:venue_unreadable`)
- Mongo: `arbicore_x.arbicore_discovery_candidates` — counts cited above
- BUILD: `9ed2718b3550066934bd11e99a96503ce75a499f`

---

## Stop

Reconciliation complete. **No code changes outside this document. No deploy / restart / config / shadow / sign / broadcast.**
