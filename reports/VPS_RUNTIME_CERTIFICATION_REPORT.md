# ArbiCore X — Read-only Runtime Certification + Opportunity Race (live RPC)

From `scripts/vps_runtime_certify.py` against LIVE mainnet RPC (read-only).
Safety: signing/broadcast/auto-exec/full-live/withdrawals OFF, kill switch
engaged. No signing, no broadcast, no execution, no private keys, no synthetic
values. Nothing here asserts limited-live eligibility.

> IMPORTANT — RPC provenance: this run used PUBLIC RPC endpoints from the preview
> container (heads/quotes are REAL). It is NOT the operator/archive VPS run the
> brief requested: this container has no operator RPC and no VPS access. The
> authoritative operator run must be executed on the VPS with
> `PROVIDER_RPC_URLS_<CHAIN>` set (runbook:
> docs/VPS_MULTICHAIN_RUNTIME_CERTIFICATION.md). Operator numbers are NOT
> substituted with public numbers.


## 2026-06 — Phase-5 certification-harness fix + re-run (branch takeover/limited-live-seam-cc8db95)

Two certification-harness defects were fixed (source unchanged otherwise; the 3
protected files and `main`/production untouched; all execution OFF):

1. **Import path (Step-6 `ModuleNotFoundError: No module named 'arbicore'`).**
   The authoritative VPS cert invokes the harnesses by DIRECT PATH
   (`python /app/scripts/vps_multichain_preflight.py`), which put `scripts/` on
   `sys.path[0]` instead of the app root. `vps_multichain_preflight`,
   `vps_runtime_certify` and `arbicore_certify` now prepend their own APP_ROOT to
   `sys.path`, so `import arbicore` resolves under BOTH `python -m scripts.<name>`
   and direct-path invocation. Verified: `python scripts/vps_multichain_preflight.py
   --json` now exits 0 and returns real content (was ModuleNotFoundError).

2. **Provenance contamination.** `arbicore_certify` reported the inherited
   production `ARBICORE_GIT_SHA=bd969ee…` / tag `p0-3-bd969ee` even though the
   isolated image is `ad64a5083d6ead0fee1e221f96f63b1c2e479eb3`. In `.git`-stripped
   IMAGE mode the baked `BUILD_INFO.json` is now authoritative; a disagreeing
   runtime env is reported as `provenance_contamination` and IGNORED (never emitted
   as the identity). Checkout mode still certifies the live working tree.

Regression: `tests/test_cert_harness_invocation_and_provenance.py` (7 tests, all
pass) — direct-path invocation of both harnesses, and image-mode provenance
(BUILD_INFO wins over stale env; env-unverified fallback; checkout live-git wins).

**Public-RPC proxy re-run with the FIXED harness (direct-path invocation, this
container — NOT the operator/archive VPS run):**
- Preflight live pool resolution: ethereum 9/9, optimism 6/6, polygon 12/12,
  arbitrum 14/15, bnb 15/20 pools resolved; base via canonical registry. Every
  chain blocker `requires_vps_runtime_proof_and_admin_approval` (never eligible).
- Runtime race: probe_rows 45 · discoverable 40 · liquidity_verified 40 ·
  quotable 40 (algebra_quote_gap 0) · candidates 7 · economically_valid 0 ·
  execution_ready 0. All 7 candidates eliminated at NET_ECONOMICS
  `negative_gross_edge_all_sizes`; 5 pools `pool_invalid_or_unreadable` (fail-closed).
  Fork simulation `anvil_available=false` (VPS-only). `LIMITED_LIVE_PROVEN=false`.
- Evidence: `reports/PREFLIGHT_PUBLIC_PROXY_phase5_harnessfix.json`,
  `reports/VPS_RUNTIME_CERT_public_phase5_harnessfix.json`.

**Exact blockers requiring the actual VPS (cannot run in this container, not
converted to success):**
- No Docker daemon → the isolated image `arbicore-x-backend:phase5-ad64a50`
  cannot be rebuilt/run here. Rebuild+run commands: runbook §0b/§2.
- No operator/archive RPC (`PROVIDER_RPC_URLS_<CHAIN>` unset natively) → only a
  public-RPC PROXY is possible here; operator numbers are NOT substituted.
- No anvil → fork simulation gate is `SIMULATION_UNAVAILABLE` here.
- No funded signer + Limited-Live OFF → no controlled execution proof.

Base must be certified FIRST on the VPS (only chain with operator/economic RPC),
then every other chain probed for real configured-RPC availability; a chain with
no operator RPC is reported `no_operator_configured_rpc`, never a pass.

## RPC health (this run)
| chain | head block | latency |
|---|---|---|
| arbitrum | 502065831 | 130ms |
| bnb | 120146986 | 188ms |
| ethereum | 25912491 | 267ms |
| optimism | 156514459 | 233ms |
| polygon | 93281777 | 151ms |
| base | (skipped — canonical path via scripts.m3_0_real_candidate_scan) | — |

## Runtime state ladder (probe rows = chain×venue×pair×fee)
probe_rows 62 · discoverable 56 · liquidity_verified 56 · **quotable 56** ·
algebra_quote_gap 0 · candidates 15 · **economically_valid 0** · execution_ready 0

### Chain × venue [discoverable, liquidity_verified, quotable] — ALL quotable
| venue | disc | liq | quotable |
|---|---|---|---|
| uniswap_v3 (5 chains) | 36 | 36 | 36 |
| pancakeswap_v3 (bnb) | 5 | 5 | 5 |
| sushiswap_v3 (arbitrum) | 5 | 5 | 5 |
| **camelot_v3 (arbitrum, Algebra)** | 3 | 3 | **3** |
| **quickswap_v3 (polygon, Algebra)** | 4 | 4 | **4** |
| sushiswap_v2 (ethereum) | 3 | 3 | 3 |

Every discovered + liquidity-verified pool is now genuinely QUOTABLE on live
chain, including all Algebra pools (Camelot V3 / QuickSwap V3) via the newly
wired + LIVE-VERIFIED Algebra dynamic-fee quoter.

## Algebra quoter — live verification
- Camelot V3 quoter `0x0Fc73040b26E9bC8514fA028D998E73A254Fa76E` (Arbitrum):
  0.05 WETH → 123.63 USDC. ABI `quoteExactInputSingle(address,address,uint256,
  uint160)→(uint256,uint16)`, dynamic fee, limitSqrtPrice=0.
- QuickSwap V3 quoter `0xa15F0D7377B2A0C0c10db057f641beD21028FC89` (Polygon):
  0.05 WETH → 123.52 USDC. Same Algebra ABI.
- Off-map chain (e.g. camelot_v3 on ethereum) fails closed (`fallback:no_adapter`).
- NOT a fabricated Uniswap V3 path — a distinct verified Algebra interface.

## NET economics gate (fail-closed) — candidate matrix
DISCOVERED → LIQUIDITY_VERIFIED → QUOTABLE → **ECONOMICALLY_VALID** → VERIFIABLE →
SIMULATABLE → LIMITED_LIVE_ELIGIBLE.

Each candidate is a REAL cross-venue round (buy borrow→other on the best venue,
sell other→borrow on another venue), gross edge priced ON-CHAIN, then run through
`compute_true_net_profit` (gas via chain gas model, route gas via quoter gas
estimate, flash-loan fee/liquidity via provider optimizer). Any missing/
unverifiable input ⇒ conservative DENY.

**15 candidates evaluated. 0 reach ECONOMICALLY_VALID. All eliminated at
NET_ECONOMICS: `negative_gross_edge`** — i.e. no positive edge exists even BEFORE
costs (real arbitrage was simply not present on these liquid pairs at the probed
block). Representative:
| chain | pair | route | gross USD |
|---|---|---|---|
| arbitrum | WETH/USDC | camelot_v3→uniswap_v3 | −0.0345 |
| arbitrum | WETH/USDT | uniswap_v3→sushiswap_v3 | −0.4427 |
| bnb | WETH/USDC | pancakeswap_v3→uniswap_v3 | −0.1407 |
| bnb | USDC/USDT | uniswap_v3→pancakeswap_v3 | −0.000033 |
| ethereum | WETH/USDT | uniswap_v3→sushiswap_v2 | −0.4895 |
| polygon | WETH/USDC | uniswap_v3→quickswap_v3 | −0.000009 |

(Full list in reports/VPS_RUNTIME_CERT_public.json.) Note: where gross HAD been
positive, the next gates would still apply — provider liquidity/fee is UNKNOWN in
this read-only container (`no_flash_provider`), route gas for Algebra hops is
unknown (no quoter gas estimate), and fork simulation needs anvil (VPS). None was
relaxed to force a pass.

## Candidate matrix summary
| stage | count |
|---|---|
| DISCOVERED (probe rows) | 56 |
| LIQUIDITY_VERIFIED | 56 |
| QUOTABLE | 56 |
| cross-venue candidates formed | 15 |
| ECONOMICALLY_VALID | **0** |
| VERIFIABLE | 0 (no candidate passed econ) |
| SIMULATABLE | 0 (anvil not present here) |
| LIMITED_LIVE_ELIGIBLE | **0** |

`LIMITED_LIVE_PROVEN = false`. `execution_ready_candidate = None`.

## Exact blockers
- Every candidate: `negative_gross_edge` (no real arbitrage at the probed block).
- Secondary (would apply if gross were positive): `no_flash_provider`
  (provider liquidity/fee feed absent read-only), Algebra route-gas unknown,
  no fork simulation (anvil absent).
- RPC: public endpoints, not operator archive nodes (item-1 authoritative run
  is an operator/VPS prerequisite — not substituted here).

## Recommendation (next step)
1. Operator/VPS: run `vps_runtime_certify` + `vps_multichain_preflight` +
   `arbicore_certify` with operator `PROVIDER_RPC_URLS_<CHAIN>` for authoritative
   numbers, and provide provider-liquidity inputs so the flash gate can compute
   true net (instead of conservative DENY).
2. Keep the race running continuously on the VPS — arbitrage is transient; a
   positive `negative_gross_edge`→positive flip must be caught in real time.
3. Only after a genuinely net-positive candidate is INDEPENDENTLY verified,
   passes MEV/risk + fork simulation, and persists evidence → prepare the
   operator-gated single-execution proof harness (DISARMED; explicit human
   approval; kill switch; capital + per-trade-loss ceilings; max-one execution;
   failure limit; no withdrawals; receipt + repayment verification;
   reconciliation; persistent evidence). NOT before — not staged this phase.

---

## PHASE 5 ADDENDUM — multi-hop, dynamic sizing, fork-sim status

- **Algebra multi-hop:** IMPLEMENTED + LIVE-VERIFIED. `QuoterRegistry.quote_route_strict`
  chains real per-hop Algebra quotes (no UniV3 approximation, no passthrough) and
  fails closed if ANY hop is unsupported. Live: Camelot WETH→USDC→USDT (both hops
  real Algebra, per-hop quoter+block provenance) = 123.78 USDT; unsupported middle
  hop ⇒ ok=False (partial). 
- **Dynamic trade-size optimization:** each surviving candidate is swept over sizes
  (0.25×/1×/4×/16×/64× the probe). Every candidate this run is non-positive at ALL
  sizes ⇒ reason `negative_gross_edge_all_sizes`. A fixed probe size is never used
  as proof of profitability.
- **Fork simulation:** `SIMULATION_UNAVAILABLE` (no anvil in this container). No
  candidate is ever marked SIMULATABLE from a quote alone.
- **Race result (public RPC):** probe_rows 62 · discoverable 56 · liquidity_verified
  56 · quotable 56 · candidates 15 · **economically_valid 0** · execution_ready 0.
  Gate histogram: {NET_ECONOMICS:negative_gross_edge_all_sizes: 15}.
- **Candidate 7-state matrix:** DISCOVERED 56 → LIQUIDITY_VERIFIED 56 → QUOTABLE 56
  → ECONOMICALLY_VALID 0 → VERIFIABLE 0 → SIMULATABLE 0 (SIMULATION_UNAVAILABLE) →
  LIMITED_LIVE_ELIGIBLE 0.
- **Execution-proof harness:** NOT prepared/armed (precondition NET_POSITIVE+VERIFIED+
  SIMULATION_PASS unmet). LIMITED_LIVE_PROVEN=false.
- **Item 1 (operator/archive VPS run):** still BLOCKED — no operator RPC/VPS access;
  public numbers NOT substituted for operator results.
