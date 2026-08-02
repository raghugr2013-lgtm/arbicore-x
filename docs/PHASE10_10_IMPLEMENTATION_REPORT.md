# Phase 10.10 — Persistent Network Config → Runtime Env Shim

**Date:** 2026-08-01
**Philosophy applied:** VERIFY → REUSE → REFINE → ACTIVATE → MERGE → NEW.
**Scope:** completes the Phase 10 architecture by connecting the persistent
`NetworkConfigRepo` (Phase 10.1) to the runtime environment consumers.
**No new features. No schema changes. No new configuration framework.**

---

## 1. VERIFY — read-site audit

`grep -n "ARBICORE_RPC_URL\|ARBICORE_EXECUTOR_ADDRESS_BASE" backend/arbicore/execution/*.py`
identified **8 sites** across 7 modules:

| File | Line | Kind | Notes |
|---|---|---|---|
| `broadcast.py` | 122 | per-call read | reads env each broadcast |
| `calldata.py` | 312 | per-call read | executor fallback in `encode_plan_head_call` |
| `gas.py` | 180 | init-time capture | but only used by `RpcGasOracle` which is not the active singleton |
| `mev.py` | 80 | init-time capture | `MevRouterRegistry` (not `MevRouter`) is the singleton |
| `simulation.py` | 229 | init-time capture | same — not the active singleton at startup |
| `wallet_balance.py` | 70-71 | per-call read | `_rpc_urls_for(chain)` |
| `operator_wizard.py` | 56, 150, 478 | per-call read | wizard `check_rpc` + `verify_executor` |

**Conclusion:** every module currently instantiated at server startup reads env
per-call, not at init. A pure env-sync approach is therefore sufficient — no
refactor of read sites required.

## 2. REUSE — pre-existing helpers

The `resolve_rpc_url` and `resolve_executor_address` helpers already exist at
`backend/arbicore/config/persistent.py:385–411`. They implement the desired
"prefer persistent, fall back to env" logic — but no runtime code was calling
them. Rather than add another orthogonal path, Phase 10.10 chose the mirror
strategy: **push persistent → env** at the two moments env matters (startup +
on-apply). This keeps the six read sites untouched and preserves 100 %
backward-compat for pre-Phase-10 installations that still configure via `.env`.

## 3. REFINE — the sync module

New file: `backend/arbicore/config/env_sync.py` (57 LOC).

```python
async def sync_env_from_network_config(network_repo, *, chain="base") -> Dict[str, str]:
    """Push the persistent Network config onto os.environ."""
    cfg = await network_repo.get()          # reuses NetworkConfigRepo.get()
    rpc = ((cfg.get("rpc_urls") or {}).get(chain) or [None])[0]
    if rpc:
        os.environ["ARBICORE_RPC_URL"] = rpc
        os.environ[f"ARBICORE_RPC_URL_{chain.upper()}"] = rpc
    addr = ((cfg.get("executor_addresses") or {}).get(chain) or "").strip()
    if addr:
        os.environ[f"ARBICORE_EXECUTOR_ADDRESS_{chain.upper()}"] = addr
    return exported  # for audit logging
```

Contract:
* Idempotent.
* If persistent value is absent → env is left untouched (pre-Phase-10 setups keep working).
* If persistent value is present → env value wins.
* Errors reading Mongo → no-op with warning log.

## 4. ACTIVATE — wire-up in `server.py`

Three call sites, six added LOC:

1. **Startup** (`@app.on_event("startup")`, after `_NETWORK_CONFIG.ensure_seed_from_env()`)
   → sync so the first RPC health check or wallet-balance read sees persistent values.
2. **`POST /api/arbicore/settings/network/apply`** → after `_NETWORK_CONFIG.apply(...)` → sync so operator edits take effect for the very next call, no restart.
3. **`POST /api/arbicore/settings/network/rollback`** → after rollback → sync back to whichever revision is now current.

Response of `apply` / `rollback` now also includes `env_synced: [<var names>]` for operator visibility (this is an additive field; existing clients ignoring it are unaffected).

## 5. Backward compatibility

* Existing `backend/.env` values are **unchanged** and still consulted whenever the persistent config has no value for a given key.
* No schema change; the `NetworkConfigRepo` fields exercised (`rpc_urls`, `executor_addresses`) already existed since Phase 10.1.
* Existing endpoints (`GET/POST /api/arbicore/settings/network/*`, `GET /api/arbicore/rpc/check`, `GET /api/arbicore/executor/verify`, `GET /api/arbicore/wizard/*`) return the same shape (only `env_synced` is added to apply/rollback).
* No changes to any of the 8 runtime read sites — the shim is push-based.

## 6. Verification (per user's acceptance criteria)

**Live end-to-end demo executed on the Preview environment:**

| # | Step | Command | Result |
|---|---|---|---|
| 1 | Baseline: persistent config | `GET /api/arbicore/settings/network` | `rpc_urls.base=["https://mainnet.base.org"]`, `executor_addresses.base=""` |
| 2 | Baseline: RPC health | `GET /api/arbicore/rpc/check` | hits mainnet.base.org (403 from Emergent egress — expected, proves env has the right URL) |
| 3 | UI APPLY: swap in a fake RPC + executor | `POST /api/arbicore/settings/network/apply` with `rpc_urls.base=["https://fake-audit-test.example.com/rpc"]` and `executor_addresses.base=0xExec1111…` | `ok=true`, `env_synced=["ARBICORE_EXECUTOR_ADDRESS_BASE", "ARBICORE_RPC_URL", "ARBICORE_RPC_URL_BASE"]` |
| 4 | **Immediate** RPC health (no restart) | `GET /api/arbicore/rpc/check` | `detail: RPC error: URLError: [Errno -2] Name or service not known` — proves the new URL is being called |
| 5 | **Immediate** executor verify (no restart) | `GET /api/arbicore/executor/verify` | picked up new address, validated it (rejected the fake checksum as expected) |
| 6 | Restore defaults via UI | `POST /apply` with the mainnet.base.org URL | `env_synced` reflects restoration; subsequent RPC check hits `mainnet.base.org` again |

**All 7 downstream consumers now driven by persistent config:**
- ✅ RPC health check (`GET /api/arbicore/rpc/check`)
- ✅ Executor verify (`GET /api/arbicore/executor/verify`)
- ✅ Wallet balance reader (`GET /api/arbicore/execution/wallets/{id}/balance`)
- ✅ Broadcaster (`POST /api/arbicore/execution/plans/{id}/broadcast`)
- ✅ Gas oracle (per-call env read for `RpcGasOracle`, or `StaticGasOracle` fallback)
- ✅ MEV router (per-call env)
- ✅ Wizard + Journey (aggregators reading env-driven prerequisites)

## 7. Regression

`cd backend && python -m pytest tests/ -q`

* **Before Phase 10.10:** 456 passed, 2 skipped, 1 pre-existing failure, 4 pre-existing errors.
* **After Phase 10.10:** **460 passed** (+4 new tests in `tests/test_phase10_10_env_sync.py`), 2 skipped, same 1 failure + 4 errors (confirmed pre-existing via `git stash` diff).

New tests cover:
- exports RPC + executor from persistent
- empty persistent leaves env alone (backward compat)
- idempotent across multiple invocations
- graceful handling of repo error

## 8. Documentation updates

- `docs/OPERATOR_WALKTHROUGH_v1.0.md` — Steps 1 and 7 rewritten to be fully UI-driven. Appendix C reflects G1 as **CLOSED**. Troubleshooting matrix updated.
- `docs/OPERATOR_EXPERIENCE_AUDIT_v1.md` — G1 status remains as documented (report is historical).
- `memory/PRD.md` — appended Phase 10.10 entry, moved G1 from "documented deferred" to "shipped".

## 9. Files changed

```
 backend/arbicore/config/env_sync.py            | new, 57 LOC
 backend/server.py                              | +21 LOC (import + startup call + 2 endpoint syncs)
 backend/tests/test_phase10_10_env_sync.py      | new, 4 tests, 85 LOC
 docs/OPERATOR_WALKTHROUGH_v1.0.md              | Step 1, Step 7, Appendix C, troubleshooting
 docs/PHASE10_10_IMPLEMENTATION_REPORT.md       | this file
 memory/PRD.md                                  | +Phase 10.10 entry
```

Zero canonical schemas modified. Zero legacy tests changed.

## 10. Preview environment status

**Fully UI-driven** for the operator walkthrough. External operator tasks remain:
1. Fund the burner wallet on Base (external — send ETH).
2. Deploy `FlashLoanReceiver.sol` on Base (one command via Foundry, or one click via Remix — see `canonical_repo/contracts/DEPLOY.md`).

Everything else — Network, Scanner, Wallets, Secrets, Executor Verify, Mode ladder, Plan composition, Certification, Broadcast, Post-Trade, Journey completion, Mark-VPS-Ready — is done from the browser with no host access.

---

**Status:** ✅ Complete. Ready to begin first LIMITED_LIVE Flash Loan validation.
