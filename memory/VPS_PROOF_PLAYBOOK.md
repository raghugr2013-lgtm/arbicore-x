# ArbiCore X — Proof Playbook & Final Go-Live Gates

SHADOW / non-broadcast throughout. Nothing here signs, broadcasts, or enables
Limited-Live. `verify_readiness.py` is strictly read-only (`eth_call` /
`eth_blockNumber` only).

## A. Reproduce the readiness proof (free RPC, no paid key)
In the backend container (`docker exec -w /app <container> ...`) or locally from
`app/backend` with `PYTHONPATH=.`:

```
PROVIDER_RPC_URLS_BASE="https://base.publicnode.com,https://base.drpc.org,https://base.meowrpc.com,https://1rpc.io/base,https://mainnet.base.org" \
ARBICORE_RPC_URL_BASE="https://base.publicnode.com" \
BASE_BALANCER_V2_VAULT="0xBA12222222228d8Ba445958a75a0704d566BF2C8" \
ARBICORE_AERO_RESOLVE_MIN_INTERVAL_MS="120" \
python /app/verify_readiness.py
```
Expect: `RESULT P0 PASS ... loader_nodes=30 real_addr=30 leaks=0`, `RESULT P1 PASS`,
`RESULT P1_BADFEE PASS`, `RESULT P2 PASS`, `RESULT P3 BLOCKED` (until executor deployed).

These public endpoints are free/community Base RPCs (verified reachable, chainId
`0x2105`). They are development/verification aids for small read-only workloads —
NOT a production capacity guarantee.

> **P1 pitfall (root cause of the VPS P1 fallback):** the keyless Ankr endpoint
> `https://rpc.ankr.com/base` now returns `-32000 Unauthorized: API key required`.
> The quote path reads a SINGLE endpoint from `ARBICORE_RPC_URL_BASE` (no failover),
> so if that points at keyless Ankr, P1 always falls back. Point `ARBICORE_RPC_URL_BASE`
> at a working endpoint — free Ankr **with an API key** (`https://rpc.ankr.com/base/<API_KEY>`)
> or a keyless public one (publicnode/drpc/mainnet.base.org). Ankr may remain primary
> in `PROVIDER_RPC_URLS_BASE` for the P0 failover path.

## B. Remaining blockers
1. RPC capacity — full-workload P0/P1 need more throughput than a single free
   endpoint. (Not a code bug: rate-limited RPC → fail-closed, never fabricated.)
2. Executor deployment — no FlashLoanReceiver on Base mainnet (8453) yet
   (registry: `not_deployed`). Blocks P3 + live preflight sim.
3. Human authorization — signer / broadcast / Limited-Live remain gated closed.

## C. Exact RPC capacity requirement
A single verifier pass issues ~44 Aerodrome resolution `eth_call`s (11 pools ×
~4 calls) + a couple of quote calls, paced ~120-150 ms apart. Free single
endpoints often 429 under this burst; the failover set above absorbs it.
For continuous Limited-Live scanning you want a provider that comfortably serves
**~25-50 req/s sustained on Base with `eth_call` + `debug_traceCall`**
(preflight revert decoding uses `debug_traceCall`). Recommended: one paid
Alchemy/Ankr/dRPC Base endpoint as primary + ≥1 free public as failover, set via
`PROVIDER_RPC_URLS_BASE` (comma-separated; primary first).

## D. Final tests to run AFTER purchasing Alchemy/Ankr (still read-only)
1. `PROVIDER_RPC_URLS_BASE="<paid_base_url>,https://base.publicnode.com"` and
   `ARBICORE_RPC_URL_BASE="<paid_base_url>"`, then rerun `verify_readiness.py`
   → P0/P1/P1_BADFEE/P2 PASS with no 429 in logs.
2. After the executor is deployed and `ARBICORE_EXECUTOR_ADDRESS_BASE` is set:
   rerun → **P3 PASS** (identity_status=READY, router/vault match registry).
3. With executor set, run the atomic pre-broadcast simulation probe
   (`probe_atomic_simulation`) → preflight `eth_call` succeeds off-chain (no send).

## E. Conditions that MUST be PASS before Limited-Live may be enabled
- P0, P1, P1_BADFEE, P2 PASS on the production RPC (no 429).
- P3 PASS (executor deployed, bytecode present, router+vault match, entrypoint
  selector present).
- Risk-control values confirmed in `.env` (notional/daily caps, `max_daily_loss_usd`).
- Atomic pre-broadcast simulation PASS against the deployed executor.
- Operator eligibility wizard PASS + kill switch disengaged.
- ≥2 Base RPCs configured (primary + failover).

## F. Conditions that MUST remain BLOCKED until explicit written human authorization
- Real EVM signer enablement (`live_signer` is a `signed=False` stub — do not wire a key).
- `eth_sendRawTransaction` broadcast (the sole call site in `broadcast.py`, 6-gate ladder).
- Mode change `flash_loan_arbitrage` SHADOW → LIMITED_LIVE / FULL_LIVE.
- Any `confirm=true` broadcast request.
These stay disabled until the operator commands it in writing.
