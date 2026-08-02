# Wave 6D · Verification Report — Capital Allocation, Kill Switch, Live Signer

**Status:** ✅ COMPLETE — SHADOW-safe, gate ladder enforced, zero broadcasting.
**Delivered:** 2026-08-01
**Test posture:** 369/369 backend tests green (18 new Wave 6D unit + 6 new Wave 6D API contract).

---

## 1. Scope

Wave 6D introduces the **operational safety substrate** that governs whether an execution plan can ever be broadcast. Three independent, composable subsystems ship:

| Module | Purpose | Reuse / Refine / Activate / New |
|---|---|---|
| `arbicore/execution/capital_policy.py` | Per-strategy sizing policy + allocator | **REUSE** of canonical `arbicore/intelligence/capital.py::CapitalSizer` math (mirrored for execution) + **NEW** repo/audit trail |
| `arbicore/execution/kill_switch.py` | Global emergency stop with audit trail | **NEW** — canonical bundle had per-flow safety interlock, none of them a *global* kill switch |
| `arbicore/execution/live_signer.py` | 4-gate ladder to enforce broadcast eligibility | **NEW** — first live-signer surface; still emits NO signed bytes at this wave |

---

## 2. Gate ladder (the authoritative broadcast boundary)

Every signing request runs the ladder in order:

```
1. Kill switch        → must be DISENGAGED
2. Mode ladder        → strategy must be in LIMITED_LIVE or FULL_LIVE
3. Capital policy     → allocator.approved must be true
4. Secret resolution  → wallet.execution_role='gas' AND secret_handle_id resolves
```

Any gate `DENIED` → `receipt.signed=false, would_broadcast=false, denied_reasons=[…]`.
All four `PASS` → `receipt.signed=false, would_broadcast=false, envelopes=[pending_calldata_encoding, …]`.

**Wave 6D barrier:** even when every gate passes, the signer holds at bytes-level calldata encoding. This is intentional — real EVM signing lands in a future refinement once the executor contract is verified. This barrier is asserted in unit tests (`test_all_gates_pass_still_holds_at_wave6d_barrier`).

---

## 3. Capital policy defaults (per-strategy, seeded on startup)

| Field | Default | Meaning |
|---|---|---|
| `max_pool_percent` | 0.005 (0.5%) | Cap by borrow-pool liquidity |
| `max_wallet_percent` | 0.20 (20%) | Cap by reference gas-wallet native balance |
| `max_per_plan_usd` | $2,500 | Absolute per-plan ceiling |
| `daily_notional_usd` | $10,000 | Rolling 24-hour notional cap |
| `max_concurrent_plans` | 3 | Reserved for future execution scheduler |
| `min_net_profit_usd` | $0.50 | Refuse plans below the floor |

Binding logic = `min(pool, wallet, per_plan_cap, daily_remaining)`. Deterministic. Fully tested.

---

## 4. New REST endpoints

| Verb | Path | Purpose |
|---|---|---|
| GET | `/api/arbicore/execution/capital-policy` | List all seeded policies |
| GET | `/api/arbicore/execution/capital-policy/{strategy}` | Read one |
| PATCH | `/api/arbicore/execution/capital-policy/{strategy}` | Update (audited) |
| POST | `/api/arbicore/execution/capital-policy/{strategy}/evaluate` | Preview an allocation decision |
| GET | `/api/arbicore/execution/kill-switch` | Read current state |
| POST | `/api/arbicore/execution/kill-switch/engage` | Engage (requires `reason`) |
| POST | `/api/arbicore/execution/kill-switch/disengage` | Disengage (requires `reason`) |
| GET | `/api/arbicore/execution/kill-switch/audit` | Audit trail |
| POST | `/api/arbicore/execution/plans/{plan_id}/sign` | Run the 4-gate ladder against a stored plan |

---

## 5. Broadcast safety invariants

1. `LiveSigningReceipt.would_broadcast` field pinned to `False`. `to_dict()` re-asserts.
2. `KillSwitchRepo.guard()` raises `KillSwitchEngagedError` — the signer surface catches it and returns `gate_ladder.kill_switch=DENIED`.
3. Even in `LIMITED_LIVE`, when all four gates PASS, the receipt is still `signed=false` — Wave 6D holds at the calldata-encoding barrier.
4. **Zero plaintext secret material** ever appears in a `LiveSigningReceipt` — the signer only performs a length check on resolved key material, never surfaces it. Unit-tested: `test_receipt_never_leaks_secret_material`.

---

## 6. Persistence & audit trails

New Mongo collections:

- `capital_policy` (one doc per strategy) + `capital_policy_audit` (append-only)
- `kill_switch_state` (single global row, key='global') + `kill_switch_audit`

Every write is audited with `actor`, `reason`, `at`. Idempotent seed on startup.

---

## 7. Canonical reuse audit

| Capability | Canonical location | Action |
|---|---|---|
| Sizing math (pool/wallet/per-trade) | `arbicore/intelligence/capital.py::CapitalSizer` | **REUSED** — mirrored, layered on daily_notional + min_profit gates |
| Sizing targets (BSC/Coinstore balance) | `services/execution/sizing.py` | Not migrated — that resolver is BDAG-specific; a future refinement can plug it into `CapitalAllocator.evaluate()` via the `available_liquidity_usd` param |
| Safety interlock pattern | `services/execution/safety_interlock.py` | **STUDIED** — the READY / WAIT / BLOCKED pattern informed the Wave 6E certification composite verdict |
| Global kill switch | — | **NEW** |
| Live signer gate ladder | — | **NEW** |

---

## 8. Test coverage

- Unit: `tests/test_wave6d_unit.py` — 18 tests
- API contract (testing_agent): `tests/test_wave6cde_api.py` — 6 dedicated to Wave 6D
- Full regression: 369/369 green.

---

## 9. Blockers / open items

None. Wave 6D is complete and merged.
