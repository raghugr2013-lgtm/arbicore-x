# ArbiCore X — VPS Runtime Certification Runbook (multichain)

**Posture: SHADOW / detection-only / fail-closed.** Nothing in this runbook
signs, broadcasts, quotes-for-execution, or enables LIMITED_LIVE / FULL_LIVE.
All commands are READ-ONLY.

## Frozen checkpoint
- Code is frozen at commit **`1f1d68f841bb93ac62b3b9b857751b4bbf0ec16f`**
  (discovery → quote → liquidity → economics plumbing connected; Base P0-3
  regression-frozen).
- Do **not** build additional venue resolvers, touch execution/signing/
  broadcast, deploy, or merge until this VPS run reports which capability seams
  actually block real opportunities.

## Prerequisites (isolated validator env — NEVER production Mongo)
- `MONGO_URL`, `DB_NAME` — dedicated validator Mongo (never production).
- Per-chain operator RPC (see Step 1). Read-only endpoints only.

---

## Step 1 — Verify operator RPC configuration (all 6 chains)

Two distinct RPC notions are gated separately (intentional, honest blockers):

| Purpose | Recognised env keys (per `<CHAIN>`) |
|---|---|
| **Discovery / quote / pool-resolution** (`rpc_explicitly_configured`) | `PROVIDER_RPC_URLS_<CHAIN>` · `PROVIDER_RPC_URL_<CHAIN>` · `ARBICORE_RPC_URL_<CHAIN>` · `<CHAIN>_RPC_URL` |
| **Economic all-in-cost gate** (`provider_registry_rpc_configured`) | `PROVIDER_RPC_URLS_<CHAIN>` · `PROVIDER_RPC_URL_<CHAIN>` **only** |

`<CHAIN>` ∈ `BASE ETHEREUM ARBITRUM OPTIMISM POLYGON BNB`. A hardcoded public
default never counts. `ARBICORE_RPC_URL_<CHAIN>` enables discovery/quote but
**not** the economic gate (→ blocker `economic_gate_rpc_not_configured`); set
`PROVIDER_RPC_URLS_<CHAIN>` for the full path.

Base-only extras used by the Base depth scan: `ARBICORE_USD_NUMERAIRE=USDC`,
`ARBICORE_NATIVE_PRICE_USD`, `BASE_BALANCER_V2_VAULT`,
`ARBICORE_AERO_CL_FACTORY_BASE`.

**Verify (offline, no RPC round-trips):**
```bash
cd /app/app/backend
python3 -c "from arbicore.runtime.multichain_readiness import build_multichain_readiness_report as r; import json; print(json.dumps(r()['networks'], indent=2, default=str))"
```
Read `rpc_configured`, `economic_rpc_configured`, `blocker` per chain. Equivalent
HTTP surface (when the app is up): `GET /api/arbicore/multichain/readiness`.

---

## Step 2 — Run the existing certification harness

```bash
cd /app/app/backend

# 2a. Repo + capability + safety + CHAIN|VENUE|STRATEGY matrix (offline)
python3 -m scripts.arbicore_certify --json > /tmp/certify.json
python3 -m scripts.arbicore_certify           # human summary

# 2b. Multichain reachability + blocker preflight (LIVE read-only pool probe
#     for any chain with an operator RPC; Base handled by canonical registry)
python3 -m scripts.vps_multichain_preflight --json > /tmp/preflight.json
python3 -m scripts.vps_multichain_preflight   # human summary
```

Interpret:
- `arbicore_certify` — `quote_path_connected` (structural wiring only, NOT
  runtime QUOTABLE) and `quote_path_connected_count`. Repo/protected-file
  integrity + safety flags must be green.
- `vps_multichain_preflight` — per chain × venue × provider: readiness blocker,
  `quote_path_connected_venues`, eligible flash-loan providers, and the LIVE
  `live_pool_probe` (`N/M pools resolved`, with per-pair `reason` on failure).

Neither report can make a cell QUOTABLE / ECONOMICALLY_VALID / LIMITED_LIVE.

---

## Step 3 — Real opportunity race (currently reachable/healthy cells)

**Base (full depth, existing harnesses):**
```bash
cd /app/app/backend
# Runs canonical Base cycles through the REAL M3 controlled-live safety layer
# (real quotes, M2.5 price, M2.6 TVL, economics, MEV, Balancer liquidity).
ARBICORE_USD_NUMERAIRE=USDC ARBICORE_M3_AUDIT_FILE=/tmp/base_scan.json \
  python3 -m scripts.m3_0_real_candidate_scan

# One canonical scanner tick + attributable evidence read-back + per-CONFIRMED
# limited-live readiness (executor cap, Balancer liquidity, atomic sim, freshness).
python3 -m scripts.vps_canonical_audit > /tmp/base_audit.json
```

**Non-Base (ethereum / arbitrum / optimism / polygon / bnb):** the LIVE pool
resolution race is `vps_multichain_preflight` (Step 2b) — it resolves real
UniV3 pools via the canonical parallel resolver over the same per-chain
`eth_call` seam the live quote provider uses. Only cells the preflight reports
as `resolved` are candidates for the deeper per-stage measurement below.

> Scope note: the flash-loan **discovery-source** config scope is locked to
> `{ethereum, arbitrum, base, optimism, polygon}` (see
> `tests/test_d6_0_substrate.test_chain_scope_locked`); BNB is quote-capable at
> the provider layer but is not emitted by the discovery source. Non-Base deep
> per-stage measurement (quote→TVL→economics→sim→evidence) runs through the
> canonical scanner once that chain is enabled + reachable — it is intentionally
> gated by the preflight reachability result, not pre-wired.

---

## Step 4 — Measurement map (what each stage proves)

`scripts.m3_0_real_candidate_scan` / `scripts.m3_0_vps_validate` emit a
per-candidate `_probe_fresh_stages` breakdown. Map to the required metrics:

| Metric | Where (stage / field) |
|---|---|
| Pool resolution | Base: `stage_2_pools[].real_address`; Multichain: preflight `live_pool_probe[].pool_address` |
| Real liquidity / TVL | `stage_2_pools[].onchain_tvl_usd` + `stage_6.min_pool_tvl_usd_in_route` (must have `tvl_provenance == onchain_reserves`) |
| Live quote | `stage_5_route_quote` (per-hop) + `stage_6.gross_profit_pct`/`route_quote_status == ok` |
| Gas | `stage_6.tx_gas_units` + `stage_10_all_in_cost` |
| Swap fees | economics `total_swap_fee_pct` (embedded in the quote-inclusive gross) |
| Flash-loan fees | economics `flash_loan_fee_usd` + `stage_7_flashloan_availability` |
| Slippage | economics `total_slippage_pct` |
| Atomic economics | `stage_9_economics` + `stage_10_all_in_cost.atomic_profit_usd` |
| Simulation | `stage_13_atomic_simulation` (needs deployed executor + inputs) |
| Evidence | CONFIRMED bundle persisted; read back via `scripts.vps_canonical_audit` (`find_for_audit`) |

`FIRST_BLOCKING_STAGE` in each probe names the single stage that fails closed.

---

## Step 5 — Identify the FIRST genuinely verified opportunity

A candidate is **verified** only when, on real runtime data:
- `route_quote_status == ok` (every hop live, closed cycle), and
- `tvl_provenance == onchain_reserves` with `min_pool_tvl_usd_in_route > 0`, and
- economics net/atomic profit computed and positive after gas + swap + flash-loan
  fees + slippage, and
- MEV gate passes, and
- `m3_final_gates.ok == true` (Base) / all applicable gates pass.

Record its chain / venue / provider / route / block. This is a **detection**
result: it is NOT authorization to execute.

---

## Step 6 — LIMITED-LIVE guardrails (do not relax)

Do **not** label any cell LIMITED-LIVE ELIGIBLE unless every applicable gate
actually passes on live data **and** an administrator has approved it. Executor
capability, Balancer flash-loan liquidity, exact-tx atomic simulation and
freshness are all fail-closed in `vps_canonical_audit` — CONFIRMED is never
treated as executable. No signer is provisioned; the broadcaster is exercised
only with `confirm=False`.

---

## Step 7 — Report exact blockers (by chain / venue / provider)

Collect blockers from three layers and tabulate per chain × venue × provider:

- **Readiness** (`multichain_readiness`): `no_operator_configured_rpc` ·
  `no_gas_model` · `economic_gate_rpc_not_configured` · `empty_route_universe` ·
  `requires_vps_runtime_proof_and_admin_approval`.
- **Matrix** (`opportunity_engine`): `univ3_factory_unregistered` ·
  `no_pool_resolver_for_venue_family` · `no_quoter_adapter_for_venue` ·
  `requires_vps_runtime_proof`.
- **Live pool probe** (preflight): `chain_rpc_unavailable` ·
  `pool_invalid_or_unreadable` · `resolve_error:<Type>` ·
  `handled_by_canonical_registry` (Base).
- **Per-stage** (m3 probe): `FIRST_BLOCKING_STAGE`.

Only after this table shows **which seams actually prevent real opportunities**
should additional venue-family resolvers (Curve / Balancer / Sushi V2 /
Velodrome / Camelot) be prioritised — build the resolver the data proves is on
the critical path first.

---

## Safety invariants (must hold throughout)
- No signing, no broadcast, no auto-execution, no LIMITED_LIVE/FULL_LIVE.
- Never production Mongo; no `--remove-orphans`.
- Protected files untouched: `scanners/dex_arbitrage/scanner.py`,
  `deployment/compose/docker-compose.yml`, `scripts/p0_3_flash_discovery_proof.py`.
- No pool address / TVL / quote / opportunity is ever fabricated; every
  unavailable input fails closed.

## Still VPS/runtime-dependent (cannot be produced offline)
Real per-chain RPC health, live pool resolution + reserves/TVL, live quotes,
gas, all-in economics, atomic simulation (deployed executor), CONFIRMED evidence
persistence/read-back, and administrator approval for any limited-live step.
