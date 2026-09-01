# ArbiCore X — Limited-Live Readiness Matrix

Branch: `fix/canonical-scanner-pool-loader-integration` @ `f9f6c90` (deployed).
Posture: **SHADOW / NON-BROADCAST**. `flash_loan_arbitrage` mode pinned to `SHADOW`;
`is_broadcast_allowed()` is true only for `LIMITED_LIVE`/`FULL_LIVE`. No execution
boundary crossed. No signer/broadcast/Limited-Live enabled by this work.

## How this was proven (application readiness vs RPC capacity)
The exact in-image verifier `verify_readiness.py` was run against a **free public
Base RPC failover set** (no paid key) to separate code readiness from RPC capacity:

```
PROVIDER_RPC_URLS_BASE="https://base.publicnode.com,https://base.drpc.org,https://base.meowrpc.com,https://1rpc.io/base,https://mainnet.base.org"
ARBICORE_RPC_URL_BASE="https://base.publicnode.com"
BASE_BALANCER_V2_VAULT="0xBA12222222228d8Ba445958a75a0704d566BF2C8"
ARBICORE_AERO_RESOLVE_MIN_INTERVAL_MS="120"
python /app/verify_readiness.py
```

Result (2026-06, this container, free public RPC):
```
RESULT P0 PASS initial_total=30 initial_unresolved=11 applied=11 loader_nodes=30 real_addr=30 leaks=0 resolved_final=30
P0_REGISTRY_SUMMARY {'total':30,'deterministic_verified':19,'runtime_resolved':11,'runtime_getpool':0,'unresolved':0}
RESULT P1 PASS pool=uniswap_v3:USDC:WETH:500 quote_status=ok out_wei=245943203779 quoter=0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a block=50716840
RESULT P1_BADFEE PASS fallback_status=fallback:break_even
RESULT P2 PASS vault_bal_wei=24911547504746593920 token=WETH decimals=18
RESULT P3 BLOCKED missing_env=ARBICORE_EXECUTOR_ADDRESS_BASE
VERIFY_DONE
```

**Fail-closed negative control** (unreachable RPC) — proves nothing is fabricated:
```
RESULT P0 FAIL applied=0 loader_nodes=19 real_addr=19 leaks=0   # only the 19 deterministic CREATE2 pools; 11 Aerodrome stay unresolved, none invented
RESULT P1 FAIL quote_status=fallback:break_even block=None      # no fake "ok" quote
```

The operator's earlier "5/11 pools resolve" was **purely RPC rate-limiting**
(Alchemy free-tier HTTP 429). The identical code resolves **11/11 → 30/30 real,
0 leaks** the moment adequate (free) RPC capacity is available.

## Matrix

| # | Item | Status | Reason | Evidence | What remains | Blocker class |
|---|------|--------|--------|----------|--------------|---------------|
| 1 | **P0 Discovery/Resolution** | **PASS** | 30 canonical pools: 19 deterministic (CREATE2 KAT) + 11 Aerodrome resolved on-chain via factory `getPool`, token0/1 + pool-type validated; loader sources canonical registry; 0 leaks, 0 unresolved | Verifier P0 PASS; `test_z8_...` 13/13; negative control shows no fabrication | Nothing (logic complete) | — (RPC-capacity only for full 11/11 at once) |
| 2 | **P1 Quote/Economics** | **PASS (logic)** | Live UniV3 QuoterV2 quote returns real out_wei + block + quoter provenance; invalid fee tier → `fallback:break_even` (fail-closed). VPS P1 FAIL was **RPC config**, not code: `ARBICORE_RPC_URL_BASE` pointed at the **keyless Ankr endpoint which now returns `-32000 Unauthorized: API key required`** → every quote fell back. See "P1 root cause" below | Verifier P1 PASS (100 WETH→245,790 USDC @ blk 50717672) with working endpoint; P1_BADFEE PASS | Operator points `ARBICORE_RPC_URL_BASE` at a working Base RPC (free Ankr **with API key**, or keyless publicnode/drpc/mainnet.base.org) | config (dead keyless endpoint) |
| 3 | **P2 Balancer Vault depth** | **PASS** (was BLOCKED) | Authoritative Balancer V2 Vault on Base = `0xBA12222222228d8Ba445958a75a0704d566BF2C8` (canonical singleton per Balancer deployment docs + BaseScan). Real `balanceOf(vault)` read succeeds | Verifier P2 PASS (vault WETH bal 24.9e18) | Operator sets `BASE_BALANCER_V2_VAULT` in VPS `.env` (value confirmed above) | config |
| 4 | **P3 Executor Identity** | **BLOCKED** | No FlashLoanReceiver deployed on Base mainnet (8453). Registry `deploy/executor_deployments.json` records `8453: address=null, deploy_status="not_deployed"`. Address with no bytecode ⇒ correct fail-closed BLOCK | `probe_executor_identity` logic verified; registry file | Operator DEPLOYS executor to Base (out of scope: no deploy/broadcast) then sets `ARBICORE_EXECUTOR_ADDRESS_BASE`. Expected constructor args recorded (vault ✓, aavePool `0xA238Dd80…`, uniRouter `0x2626664c…`) | environment (deployment) |
| 5 | **Shadow execution path** | **PASS** | Full read-only pipeline (discover → resolve → quote → economics/gates → shadow route) exercised; only read-only `eth_call`/`eth_blockNumber` used; no signer touched | Verifier is read-only end-to-end; mode pin `flash_loan_arbitrage=SHADOW` | Nothing | — |
| 6 | **Risk controls** | **PASS (code)** | Gate 7 min-net-profit, Gate 8 fail-closed depth, Gate 9 MEV margin, capital policy incl. `max_daily_loss_usd` stop-loss, kill switch | filter/economics/capital_policy tests | Operator confirms limit VALUES (notional, daily, max_daily_loss_usd) in VPS `.env` | config |
| 7 | **Transaction construction** | **BUILT / HELD** | `calldata.encode_plan_head_call` + `broadcast.py` build unsigned envelopes; atomic pre-broadcast sim exists | broadcast/preflight code + atomic-sim tests | Live preflight `eth_call` sim against a deployed executor (needs item 4) | environment (needs executor) |
| 8 | **Signer readiness** | **DISABLED (by design)** | Autonomous signer `live_signer.py` is a gate-only stub — `signed=False` invariant, emits no signed bytes. Public signer-address probe available but no key path | live_signer code; `probe_signer_readiness` | **Keep disabled** until explicit written operator authorization | INTENTIONALLY GATED (human auth) |
| 9 | **Broadcast gate** | **DISABLED (by design)** | `broadcast.py` has the sole `eth_sendRawTransaction` call site behind 6 gates (circuit-breaker, kill-switch, mode=LIMITED_LIVE, capital, secret, preflight, operator-confirm). Mode pinned SHADOW ⇒ cannot fire | broadcast gate ladder; mode pin | **Keep disabled** until explicit written operator authorization | INTENTIONALLY GATED (human auth) |
| 10 | **Limited-Live gate** | **NO-GO (by design)** | Requires items 4/8/9 + operator eligibility wizard + explicit mode change. Not enabled | `limited_live_eligibility`, `operator_wizard` | Human authorization + executor deploy + signer provisioning | INTENTIONALLY GATED (human auth) |

## P1 root cause (exact) & fix
- **Cause (configuration):** the keyless Ankr Base endpoint `https://rpc.ankr.com/base`
  now rejects all calls with `{"code":-32000,"message":"Unauthorized: You must
  authenticate your request with an API key ..."}`. The P1 quoter
  (`execution/quoter.py`, `QuoterRegistry`) reads a **single** endpoint from
  `ARBICORE_RPC_URL_BASE` (no failover in the quote path, by design — it mirrors
  the read-only URL the broadcaster validates). With that endpoint dead, every
  hop degrades → route `fallback:break_even`. Proven by direct A/B against 5
  endpoints: Ankr-keyless → Unauthorized; publicnode/drpc/meowrpc/mainnet.base.org
  → live quote `out_wei≈2.457e11` (100 WETH → ~245,790 USDC).
- **Code defect fixed (fail-closed preserved):** `_eth_call`'s batch parser only
  matched `id==1`; when a provider answers a batch with a single top-level error
  whose `id` is null (Ankr's behaviour), the error was dropped and the hop
  mis-reported `fallback:rpc_error: decode error: NoneType` instead of the real
  reason. Fixed to surface the actual RPC error (now `fallback:revert code=-32000
  Unauthorized...`), so rate-limit vs auth vs revert are correctly classified for
  the operator. No fabrication; still falls back.
- **Operator fix for P1 green:** set `ARBICORE_RPC_URL_BASE` to a working Base RPC —
  either a **free Ankr account key** (`https://rpc.ankr.com/base/<API_KEY>`) or a
  keyless public endpoint (`https://base.publicnode.com`, `https://base.drpc.org`,
  `https://mainnet.base.org`). Keep the failover list in `PROVIDER_RPC_URLS_BASE`
  for the P0 path (Ankr primary → public fallback is fine there).
- **Backlog (not done, not required for readiness):** give the quote path the same
  multi-endpoint failover the resolver has, so a single dead `ARBICORE_RPC_URL_BASE`
  can't force fallback. Deferred to avoid changing a broadcast-adjacent module
  without need.

### 2026-06 update — Alchemy configured but P1 still FAIL (`block=None`)
- With a healthy Alchemy Base RPC set as `ARBICORE_RPC_URL_BASE`, P0 and P3 both
  reach it fine (P3 returned a real `eth_getCode` → "no bytecode"), proving the
  URL IS resolved and used by the quote path (verifier line 65-70:
  `QuoterRegistry(rpc_url_env="ARBICORE_RPC_URL_BASE")`). So P1's `block=None` +
  passthrough `out_wei` is NOT a URL/config-precedence problem — it is the
  provider rejecting the quoter's **JSON-RPC batch** (`eth_call`+`eth_blockNumber`
  in one array). Public nodes (publicnode/drpc/mainnet.base.org) honour the batch;
  some Alchemy plans answer a batch with a single object / empty array, which the
  old parser turned into a silent fallback with `block=None`.
- **Fix 2 (code, safe):** `_eth_call` now auto-detects a mishandled batch per host
  and transparently retries as **single requests** (`eth_call` + a separate
  best-effort `eth_blockNumber` for provenance). Batch-friendly hosts keep
  batching; batch-averse hosts (Alchemy) degrade to single automatically. Proven:
  batch and forced-single modes return identical result + block on 3 endpoints;
  verifier P1 PASS.
- **Fix 3 (diagnostics):** verifier P1 line now prints `rpc_env`, `rpc_host`,
  `hop_status`, `hop_error` so the exact provider reason is never hidden again
  (e.g. it will show `rpc_host=...alchemy.com hop_status=... hop_error=code=... msg`).
- Net: P1 is application-ready; on the VPS the auto-fallback should make it PASS
  against Alchemy directly. If it still fails, the new `hop_error` field reveals
  the precise Alchemy message for a targeted follow-up.

### P2 value — sourced from project config (NOT invented)
`BASE_BALANCER_V2_VAULT = 0xBA12222222228d8Ba445958a75a0704d566BF2C8`
- `contracts/script/Deploy.s.sol:31` `MAINNET_BALANCER_V2_VAULT` constant + line 58 default.
- `docs/EXECUTOR_PROVISIONING_READINESS.md:32` Base-mainnet row (vault/aavePool/uniRouter).
- `deploy/executor_deployments.json` `8453.constructor_args_expected.balancerVault`.
This is the Balancer V2 canonical singleton (same address every chain) AND the exact
value the project's own deploy scripts/registry use.

## Bottom line
All **non-RPC-capacity, non-deployment application blockers are resolved**. P0/P1/P2
logic is PROVEN on real Base state with free RPC. Remaining gates are:
(a) **RPC capacity** for reliable full-workload runs (item 1 at scale),
(b) **executor deployment** on Base mainnet (items 3-config/4/7),
(c) **explicit human authorization** for signer/broadcast/Limited-Live (items 8/9/10),
which MUST remain BLOCKED until commanded in writing.

## 2026-06 — Alchemy 429 diagnosis, RPC capacity, and P1 failover
### Exact 429 cause (from live diagnostics)
VPS P1 showed `hop_error=code=-32016 HTTP 429 rate limited`, `rpc_host=base-mainnet.g.alchemy.com`.
Note the asymmetry: **P0 PASSED, P1 FAILED on the same Alchemy** — because P0 goes through
the failover registry (routes around a 429) while the quote path had NO failover.
Root cause = Alchemy **free-tier throughput saturation**: free = ~300 CU/s measured over a
**10-second rolling window**; `eth_call` = 26 CU → ~11.5 eth_calls/s. P0 resolution bursts
~44 eth_calls (11 Aerodrome pools × ~4 calls) which saturates that 10s window; P1's quote
lands in the saturated window and 429s through all client retries. Not a code/URL bug —
`ARBICORE_RPC_URL_BASE` IS used by the quote path (P3 uses the same var and reached Alchemy).

### Minimum RPC capacity for Limited-Live (eth_call @ 26 CU)
| Workload | eth_calls | CU | Verdict on Alchemy FREE (300 CU/s, 30M CU/mo) |
|---|---|---|---|
| Verifier one-shot P0+P1+P2 | ~50 | ~1.3k | Marginal — bursts trip 429; **failover fixes it** |
| One scan tick (~40-80 quotes+TVL+gas) | 40-80 | ~1.3-2.9k | Peak burst 2-4× avg → exceeds 300 CU/s |
| Continuous scan, tick 3-5s | — | ~330-970 CU/s sustained | **INSUFFICIENT** (need ~800-1,200 CU/s safe floor) |
| 24/7 monthly | — | ~2.0B CU/mo | Free 30M/mo ≈ <1h of scanning; PAYG ≈ $0.45/1M CU |
- **Safe floor for Limited-Live: ~800-1,200 CU/s (≈30-45 eth_calls/s).**
- **Alchemy plan verdict:** FREE tier is sufficient only for one-shot verification (with
  failover); it is **NOT sufficient for continuous Limited-Live scanning**. A paid tier
  (PAYG/Growth base **10,000 CU/s** ≈ 384 eth_calls/s) gives ~8-12× headroom and is
  more than enough. Alternatively run Alchemy primary + 2-3 free public failovers with
  client throttling for development.

### Controlled throttling knobs (already in code)
- `ARBICORE_RPC_MIN_INTERVAL_MS` (quoter global throttle, default 140 ms ≈ 7 calls/s ≈ 182 CU/s — under free ceiling).
- `ARBICORE_AERO_RESOLVE_MIN_INTERVAL_MS` (P0 resolution pacing, default 150 ms).
- `ARBICORE_RPC_MAX_RETRIES` (default 4). Recommend keeping ≥2 with failover.

### Fix — P1 (and whole quote path) RPC failover [implemented, tested]
`QuoterRegistry.quote_route` now tries an ORDERED endpoint list and fails over per-hop on
transient/provider faults (429, transport, empty), stopping only on a genuine DEX
`execution reverted` (another RPC returns the same) or no-adapter. Endpoint precedence:
`ARBICORE_RPC_URL_<CHAIN>` (may be comma-list) → `PROVIDER_RPC_URLS_<CHAIN>`/`PROVIDER_RPC_URLS`
→ legacy vars. Non-final candidates get a 1-retry budget so a rate-limited primary yields
fast to the failover; the last candidate keeps the full retry budget. Only a clean `ok`
quote is cached (never a transient fallback). Benefits ALL callers (`live_quote_provider`,
`dex_arbitrage/quoter`, `searcher/runtime`), not just the verifier.
Proven (free public RPC): healthy-primary→ok; dead-primary→failover ok; Ankr-unauthorized
primary→failover ok; comma-list→ok; **all-dead→fail-closed `fallback:break_even` (no
fabrication, error surfaced)**. Verifier with a dead primary auto-fails over → **P1 PASS**
(`rpc_host=base.publicnode.com`). Quoter tests 12 passed. Signer/broadcast/executor/live-mode untouched.

