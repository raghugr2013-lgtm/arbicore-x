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
| 2 | **P1 Quote/Economics** | **PASS** | Live Uniswap V3 QuoterV2 quote returns real out_wei with block + quoter provenance; invalid fee tier degrades to `fallback:break_even` (fail-closed) | Verifier P1 PASS (100 WETH→245,943 USDC @ blk 50716840) + P1_BADFEE PASS | Nothing (logic complete) | — |
| 3 | **P2 Balancer Vault depth** | **PASS** (was BLOCKED) | Authoritative Balancer V2 Vault on Base = `0xBA12222222228d8Ba445958a75a0704d566BF2C8` (canonical singleton per Balancer deployment docs + BaseScan). Real `balanceOf(vault)` read succeeds | Verifier P2 PASS (vault WETH bal 24.9e18) | Operator sets `BASE_BALANCER_V2_VAULT` in VPS `.env` (value confirmed above) | config |
| 4 | **P3 Executor Identity** | **BLOCKED** | No FlashLoanReceiver deployed on Base mainnet (8453). Registry `deploy/executor_deployments.json` records `8453: address=null, deploy_status="not_deployed"`. Address with no bytecode ⇒ correct fail-closed BLOCK | `probe_executor_identity` logic verified; registry file | Operator DEPLOYS executor to Base (out of scope: no deploy/broadcast) then sets `ARBICORE_EXECUTOR_ADDRESS_BASE`. Expected constructor args recorded (vault ✓, aavePool `0xA238Dd80…`, uniRouter `0x2626664c…`) | environment (deployment) |
| 5 | **Shadow execution path** | **PASS** | Full read-only pipeline (discover → resolve → quote → economics/gates → shadow route) exercised; only read-only `eth_call`/`eth_blockNumber` used; no signer touched | Verifier is read-only end-to-end; mode pin `flash_loan_arbitrage=SHADOW` | Nothing | — |
| 6 | **Risk controls** | **PASS (code)** | Gate 7 min-net-profit, Gate 8 fail-closed depth, Gate 9 MEV margin, capital policy incl. `max_daily_loss_usd` stop-loss, kill switch | filter/economics/capital_policy tests | Operator confirms limit VALUES (notional, daily, max_daily_loss_usd) in VPS `.env` | config |
| 7 | **Transaction construction** | **BUILT / HELD** | `calldata.encode_plan_head_call` + `broadcast.py` build unsigned envelopes; atomic pre-broadcast sim exists | broadcast/preflight code + atomic-sim tests | Live preflight `eth_call` sim against a deployed executor (needs item 4) | environment (needs executor) |
| 8 | **Signer readiness** | **DISABLED (by design)** | Autonomous signer `live_signer.py` is a gate-only stub — `signed=False` invariant, emits no signed bytes. Public signer-address probe available but no key path | live_signer code; `probe_signer_readiness` | **Keep disabled** until explicit written operator authorization | INTENTIONALLY GATED (human auth) |
| 9 | **Broadcast gate** | **DISABLED (by design)** | `broadcast.py` has the sole `eth_sendRawTransaction` call site behind 6 gates (circuit-breaker, kill-switch, mode=LIMITED_LIVE, capital, secret, preflight, operator-confirm). Mode pinned SHADOW ⇒ cannot fire | broadcast gate ladder; mode pin | **Keep disabled** until explicit written operator authorization | INTENTIONALLY GATED (human auth) |
| 10 | **Limited-Live gate** | **NO-GO (by design)** | Requires items 4/8/9 + operator eligibility wizard + explicit mode change. Not enabled | `limited_live_eligibility`, `operator_wizard` | Human authorization + executor deploy + signer provisioning | INTENTIONALLY GATED (human auth) |

## Bottom line
All **non-RPC-capacity, non-deployment application blockers are resolved**. P0/P1/P2
logic is PROVEN on real Base state with free RPC. Remaining gates are:
(a) **RPC capacity** for reliable full-workload runs (item 1 at scale),
(b) **executor deployment** on Base mainnet (items 3-config/4/7),
(c) **explicit human authorization** for signer/broadcast/Limited-Live (items 8/9/10),
which MUST remain BLOCKED until commanded in writing.
