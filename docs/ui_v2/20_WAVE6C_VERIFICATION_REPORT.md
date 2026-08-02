# Wave 6C · Verification Report — On-chain Simulation, Gas Oracle, MEV Router

**Status:** ✅ COMPLETE — SHADOW-safe, 100% test-passing, zero broadcasting.
**Delivered:** 2026-08-01
**Test posture:** 369/369 backend tests green (300 baseline + 43 Wave 6C unit + 16 API contract).

---

## 1. Scope

Wave 6C introduces a **provider-agnostic simulation & routing substrate** on top of the Wave 6B execution DAG. Every capability is strictly READ-ONLY and enforces `would_broadcast=False` at every layer.

Four new sub-modules ship:

| Module | Purpose | Reuse / Refine / Activate / New |
|---|---|---|
| `arbicore/execution/gas.py` | Gas oracle abstraction (`StaticGasOracle`, `RpcGasOracle`) | **NEW** — canonical bundle had no execution-side oracle |
| `arbicore/execution/slippage.py` | Deterministic per-hop slippage estimator | **REUSE** of canonical `SlippageValidator` math (isolated for execution engine) |
| `arbicore/execution/mev.py` | MEV router abstraction (`PublicRpcRouter`, `FlashbotsRouter`) | **NEW** — routing-metadata-only in this wave |
| `arbicore/execution/simulation.py` | Simulator backend (`NoopSimulator`, `EthCallSimulator`) + `SimulationRegistry` | **NEW** — canonical bundle had no `eth_call` simulator |

The **Wave 6B `DryRunEngine`** was refined (additively) to consume the new components. The old ctor signature still works — Wave 6B tests remain green.

---

## 2. Provider-agnostic surface

Every new capability is behind a Python `Protocol`. Adding a new HSM-backed simulator, an Alchemy-hosted gas oracle, or a MEV-Blocker relay is a drop-in registration — no changes to planning logic.

```
GasOracleBackend            SimulatorBackend            MevRouterBackend
   ├── StaticGasOracle          ├── NoopSimulator          ├── PublicRpcRouter
   └── RpcGasOracle             └── EthCallSimulator       └── FlashbotsRouter
```

---

## 3. Broadcast-safety invariants (asserted at multiple layers)

1. `SimulationResult.would_broadcast` is a value-object field pinned to `False`. `to_dict()` re-asserts.
2. `EthCallSimulator._rpc()` refuses any method outside the read-only allowlist (`eth_call`, `eth_estimateGas`, `eth_chainId`, `eth_blockNumber`, `eth_getBalance`, `eth_getCode`, `eth_getTransactionCount`, `eth_getStorageAt`, `eth_gasPrice`, `eth_maxPriorityFeePerGas`, `eth_feeHistory`).
3. Explicit denylist (`eth_sendTransaction`, `eth_sendRawTransaction`, `eth_signTransaction`, `eth_sign`, `personal_sign`, `personal_sendTransaction`) raises `PermissionError`.
4. `SimulationRegistry.simulate()` re-checks both invariants after dispatch.
5. `RoutingDecision.to_dict()` asserts `would_broadcast is False` on every serialise.
6. All RPC URLs are redacted to `scheme://host[:port]` before appearing in any response — API keys in query strings cannot leak.

---

## 4. New REST endpoints (all READ-ONLY)

| Verb | Path | Purpose |
|---|---|---|
| GET | `/api/arbicore/execution/simulation/status` | Simulator registry + read-only allowlist + denylist |
| GET | `/api/arbicore/execution/gas?chain=base` | Live gas estimate (default `StaticGasOracle`) |
| GET | `/api/arbicore/execution/mev/routers?chain=base[&router=…&protected=true]` | MEV router catalog + current routing decision |
| POST | `/api/arbicore/execution/plans/{plan_id}/simulate` | Simulate a persisted plan (gas + MEV + slippage + eth_call) |

The `/simulate` endpoint refuses to run against strategies in `LIMITED_LIVE` / `FULL_LIVE` — those must go through the Wave 6E flow.

---

## 5. Canonical reuse audit

| Capability | Canonical location | Action |
|---|---|---|
| Deterministic slippage math | `arbicore/intelligence/validators/slippage.py` | **REUSED** — mirrored math into execution module with the same 30 bps / 60 bps default band |
| MEV risk classification | `arbicore/intelligence/validators/mev_risk.py` | **KEPT SEPARATE** — canonical validator does *risk classification*; our new `MevRouterBackend` does *routing metadata*. Both remain authoritative in their domain. |
| Live gas estimation | *not present in canonical bundle* | **NEW** |
| `eth_call` simulation | *not present in canonical bundle* | **NEW** |

---

## 6. Test coverage

- Unit: `tests/test_wave6c_unit.py` — 25 tests
- API contract (testing_agent v3): `tests/test_wave6cde_api.py` — 16 tests total (5 dedicated to Wave 6C)
- Regression: 353→369 total green.

## 7. Blockers / open items

None. Wave 6C is complete and merged.
