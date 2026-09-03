# EXECUTOR READINESS AUDIT — RPC Config Consistency (Phase 2D)

## The comma-separated-RPC defect (root cause of "verifier sees no bytecode")

`ARBICORE_RPC_URL` may hold a **comma-separated** list of endpoints. Consumers
split into two camps:

**Correct (enumerate / split):** `providers/bootstrap.py` (`_csv`),
`execution/quoter.py` (`_add` splits each value), `execution/wallet_balance.py`
(`_rpc_urls_for`), `config/env_sync.py` (exports the list's primary),
`config/persistent.ensure_seed_from_env` (splits into a list).

**BUGGY (used the joined string as ONE URL) → FIXED:**
- `config/persistent.resolve_rpc_url_from_env` — the canonical sync resolver.
- `config/persistent.resolve_rpc_url` (async env-fallback branch).
- `execution/simulation.py::EthCallSimulator._rpc_url`.
- `execution/gas.py::RpcGasOracle._rpc_url`.
- `server.py` — **5** `TechnicalValidator(rpc_url=os.environ.get("ARBICORE_RPC_URL",""))`
  call sites. This is the executor/technical verifier that historically POSTed to a
  malformed comma-joined URL and reported **no bytecode** while a direct single-URL
  RPC found the deployed executor.

## Fix (single canonical selector, no test patched)

Added `config/persistent.first_rpc_endpoint(raw)` — returns the first non-empty,
stripped endpoint from a (possibly comma-separated) value, else `None`. Routed
**every** previously-raw consumer through it (resolver, async fallback, simulator,
gas oracle, all 5 `TechnicalValidator` call sites). Consumers that already
enumerate endpoints were left unchanged (they were correct).

## Regression proof
`tests/test_phase2_rpc_config_consistency.py` (6 tests, all pass): the selector,
the resolver, `RpcGasOracle`, `EthCallSimulator`, and `_rpc_urls_for` all select
`https://rpc-a…` (the first endpoint) from a comma-separated env — and **none**
ever returns the joined string. This pins consistency so consumers cannot drift.

## What remains YELLOW / BLOCKED (honest)
- **On-chain bytecode / ABI / chain-id verification, flash-provider compatibility,
  router/token allowlist on-chain checks, calldata/userData/amountOutMinimum, and
  atomic fork simulation** require a live/archive RPC endpoint, which is **not
  provisioned** in this environment (`.env` deliberately has no RPC → SHADOW,
  fail-closed). These CANNOT be truthfully certified here and remain **BLOCKED**.
- The verifier code path is now correct; with a real `ARBICORE_RPC_URL` provisioned,
  it will select a valid endpoint and can perform the on-chain checks. Until then,
  any route claiming a venue the deployed executor does not support MUST be
  classified `NON_EXECUTABLE` (the sim gate's `provider_ok`/allowlist checks enforce
  this fail-closed).
