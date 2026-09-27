# ArbiCore X — G5 Engineering Handoff

Date: 2026-09-27

## 1. Purpose

This document records the current ArbiCore X certification state before continuing G5 engineering work.

The objective is to preserve the completed G3/G4 certification state and provide a precise handoff for the remaining G5 work.

---

## 2. Certification Status

### G3 — GREEN / CLOSED

V2 migration and backend capability validation completed.

### G4.1 — GREEN

Real Base Sepolia deployed V2 runtime validation completed.

### G4.2 — GREEN

Real Base mainnet fork validation completed.

8/8 V2 fork validation tests passed.

### G4.3 — GREEN

V2 backend freeze, settlement, capability, provider and Base Sepolia validation completed.

### G4.4F — GREEN

Real Base Sepolia UniV3 discovery completed.

Verified:

- Base Sepolia UniV3 factory
- WETH/USDC pools
- pool code
- token0/token1
- fee tiers
- positive liquidity
- slot0
- Quoter V2
- real read-only quotes

### G4.5 — GREEN

V2 paper/shadow validation suite:

120 passed.

No signing or broadcasting occurred.

---

## 3. V2 Safety Boundary

The following remain unchanged:

- V2 executor contracts
- deployed V2 receiver
- economic thresholds
- fail-closed behaviour
- scanner activation state
- live execution state

No scanner has been started.

No transaction has been signed.

No transaction has been broadcast.

---

## 4. G5 Current State

G5 is not yet GREEN.

Current control mode remains SHADOW.

The current blocker is the M2.5 live on-chain USD price path.

### Confirmed working

- Base RPC provider infrastructure exists.
- Persistent Base network configuration supports multiple RPC URLs.
- QuoterRegistry supports multiple candidates and chain identity verification.
- Base.org successfully returned Base chain identity.
- Base.org successfully returned block number.
- Base.org has previously passed valid contract-read validation.
- Base UniV3 real quote infrastructure has produced a successful real quote.
- Canonical WETH/USDC pool discovery is correct.
- Exact WETH → USDC pool/hop resolution is correct.
- M2.5 price-feed construction succeeds.

### Current failure

The running ProviderRegistry currently has only one Base provider:

`mainnet.base.org`

Its lightweight block-number call succeeds, but `eth_call` requests are returning HTTP 429 rate-limit errors.

The existing Alchemy Base endpoint is present in persistent configuration but is not currently registered as a second live ProviderRegistry endpoint.

---

## 5. Root Cause Found

The persistent Network Configuration supports:

`rpc_urls.base = [primary, fallback, ...]`

However, `sync_env_from_network_config()` exports only the primary RPC into:

- `ARBICORE_RPC_URL`
- `ARBICORE_RPC_URL_BASE`
- `BASE_RPC_URL`

The ProviderRegistry bootstrap already supports the plural configuration:

`PROVIDER_RPC_URLS_BASE`

and registers every endpoint independently with priorities:

- provider 0 → priority 100
- provider 1 → priority 101

The existing certification function:

`sync_provider_registry_rpc_from_env()`

is intentionally a single-endpoint contract and must NOT be changed casually.

Existing tests explicitly preserve this contract.

---

## 6. Architectural Conclusion

Do NOT rewrite the existing certification RPC synchronization contract.

The preferred architecture is:

Persistent Network Configuration
    ↓
rpc_urls.base[]
    ↓
controlled provider-registry synchronization
    ↓
PROVIDER_RPC_URLS_BASE
    ↓
existing ProviderRegistry bootstrap/refresh
    ↓
multiple Base providers

The existing:

`ARBICORE_RPC_URL_BASE`

primary/certification semantics must remain intact.

---

## 7. Next Engineering Task

Before implementation:

1. Audit ProviderRegistry register/deregister/replace semantics.
2. Determine the smallest safe registry refresh mechanism.
3. Preserve strict chain isolation.
4. Preserve fail-closed behaviour.
5. Preserve existing certification semantics.
6. Add regression tests before production mutation.

Required regression coverage:

- persistent primary + fallback RPC registration
- provider priority ordering
- explicit PROVIDER_RPC_URLS_* precedence
- chain isolation
- fail-closed empty configuration
- stale provider removal/replacement
- network-config rollback
- no scanner activation
- no transaction side effects

---

## 8. Prohibited Changes During This Work

Do NOT:

- lower economic thresholds
- weaken profit gates
- fabricate quotes
- fabricate liquidity
- use synthetic WETH prices for production evidence
- modify V2 executor security checks
- start the scanner
- enable live execution
- sign transactions
- broadcast transactions
- restart production without explicit approval
- replace fail-closed logic with permissive fallback behaviour

---

## 9. Required Emergent Handoff

Emergent should continue from this checkpoint rather than redesigning G3/G4.

The requested implementation is the smallest safe bridge from the persistent multi-RPC Network Configuration to the existing ProviderRegistry multi-RPC mechanism.

Before any production mutation, Emergent must return:

1. proposed files changed
2. exact design
3. regression tests
4. test results
5. confirmation that V2 executor code is untouched
6. confirmation that economic thresholds are unchanged
7. confirmation that scanner/signing/broadcast remain disabled

Only after review should any production configuration change be considered.

---

## 10. Current Git Checkpoint

Checkpoint tag:

`G5-checkpoint-20260927`

Canonical V2 certification worktree:

`/home/raghu/projects/arbicore-x-v2-sync-20260926`

Canonical certification branch:

`cert/vps-current-20260925`

---

## 11. Final Safety State

At handoff:

- G3: GREEN / CLOSED
- G4: GREEN
- G5: IN PROGRESS
- Scanner: OFF
- Signing: OFF
- Broadcasting: OFF
- Transactions: NONE
- V2 executor: FROZEN
- Economic thresholds: UNCHANGED
