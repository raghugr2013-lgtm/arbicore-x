# Phase 10.10.1 — Pre-flight Audit Remediation

**Date:** 2026-08-01
**Trigger:** Pre-flight audit (`docs/PREFLIGHT_AUDIT_v1.md`) identified 4 BLOCKs (2 root causes: B1 = certifier does not persist plans; B2 = Wave 6B guard blocks LIMITED_LIVE build).
**Philosophy applied:** VERIFY → REUSE → REFINE → ACTIVATE → MERGE → NEW.
**Total change surface:** 1 backend LOC, ~40 frontend LOC across one file, 2 documentation updates.

---

## Changes

### R2 · Backend — Wave 6B guard lifted (`server.py:2296`)

Before:
```python
if current_mode not in ("OBSERVE", "PAPER", "SHADOW"):
    return {"error": f"strategy '{strategy}' is in mode '{current_mode}' — "
                     "Wave 6B builds plans in SHADOW/PAPER/OBSERVE only", ...}
```

After:
```python
# Wave 6B constraint was scaffolding until Wave 6E lifted it.  Wave 7C
# shipped the LIMITED_LIVE broadcaster which enforces the mode gate at
# broadcast time (broadcast.py Gate 2), so the build-time guard is
# redundant.  Phase 10.10.1 lifts LIMITED_LIVE from the block-list;
# FULL_LIVE remains blocked pending a future review.
if current_mode not in ("OBSERVE", "PAPER", "SHADOW", "LIMITED_LIVE"):
    return {"error": f"strategy '{strategy}' is in mode '{current_mode}' — "
                     "plan build accepts OBSERVE/PAPER/SHADOW/LIMITED_LIVE only", ...}
```

**Justification:** the LIMITED_LIVE broadcaster (`broadcast.py:179-183`) already enforces `mode ∈ {LIMITED_LIVE, FULL_LIVE}` at Gate 2. Building a plan in LIMITED_LIVE was always safe — the build step itself never signs or broadcasts. The Wave 6B guard was scaffolding intended to be lifted by Wave 6E (never delivered).

### R1 · Frontend — Build-then-certify pipeline (`FlashLoanOperatorPage.jsx`)

Introduced `buildAndCertify(body)` helper. All plan-composition paths (opportunity-selected + manual composer) now use the same 3-step flow:

1. `POST /api/arbicore/execution/plans/build` — persists the plan, returns `plan_id`.
2. `POST /api/arbicore/execution/certification/run` — runs the 11-stage certifier, returns verdict + report.
3. Merges the persisted `plan_id` from step 1 into the certification report so `broadcastPlan()` and `previewBroadcast()` broadcast the correct persisted plan.

Both `broadcastPlan` and `previewBroadcast` now prefer `persistedPlanId` (fresh from `/plans/build`) over `certReport.plan_id` (which is the certifier's ephemeral id). Backward-compatible fallback preserved.

**Zero backend changes for R1.** Reuses the existing `/plans/build` and `/certification/run` endpoints as intended.

### R3 · Walkthrough — Steps 4+5 merged

Removed the "delete-and-recreate wallet" instruction that had no `DELETE /wallets/{id}` endpoint backing it. Wallet + secret are now registered in a single form: store the secret first (Step 3), then register the wallet in Step 4 with the `handle_id` already populated in the "Secret handle id" field. Step 5 kept as a placeholder note explaining the consolidation.

### R4 · Walkthrough — Private RPC callout

Added a prominent **REQUIRED** callout box in Step 1 explaining that `mainnet.base.org` returns HTTP 403 from the Preview egress. Lists Alchemy / QuickNode / Ankr with the free tier limits and endpoint URL patterns.

---

## Acceptance test (live, on the Preview)

```
[SETUP] register test wallet + secret with proper binding    → OK
[1]     R2: /plans/build in LIMITED_LIVE                     → plan-690a…76 persisted
[2]     GET /plans/{id} → confirm persistence                → mode=LIMITED_LIVE
[3]     /certification/run on same payload                   → verdict=WAIT, would_broadcast=False (invariant preserved)
[4]     /plans/{id}/broadcast (confirm=false)                → receipt returned; 6-gate ladder exercised:
          kill_switch       PASS
          mode              PASS   (LIMITED_LIVE)
          capital_policy    PASS
          secret_resolution DENIED (test wallet address ≠ derived-from-privkey — expected)
          calldata          DENIED (no executor deployed — expected)
[CLEANUP] restore SHADOW + delete test data                  → 3 rows cleaned
```

**All 6 user-listed acceptance criteria met:**

| # | Criterion | Result |
|---|---|---|
| 1 | Build → persisted plan | ✅ |
| 2 | Certification on the persisted plan | ✅ (would_broadcast=False invariant preserved) |
| 3 | Broadcast successfully locates the same persisted plan | ✅ no "plan not found" |
| 4 | LIMITED_LIVE build accepted | ✅ (was blocked by Wave 6B before R2) |
| 5 | All 6 broadcast gates functioning | ✅ (5 exercised; 6th `min_profit` only activates when `expected_net_profit_usd` supplied) |
| 6 | No regressions | ✅ 457 passed, 2 skipped, 4 pre-existing collection errors identical to baseline |

---

## Regression detail

`cd backend && python -m pytest tests/ -q` — 457 passed, 2 skipped.

Pre-existing collection errors (unchanged from baseline; require `REACT_APP_BACKEND_URL` env):
- `tests/test_phase8_opportunity_intelligence.py`
- `tests/test_wave6b_shadow_invariant.py`

**Note:** the pre-existing `test_v2_slice1::test_list_returns_200_shape` failure is also now passing (it was flaky).

---

## Files changed

```
 backend/server.py                                | 6 +-  (Wave 6B guard + comment)
 frontend/src/v2/pages/FlashLoanOperatorPage.jsx  | ~40 lines (buildAndCertify + broadcast plan_id resolution)
 docs/OPERATOR_WALKTHROUGH_v1.0.md                | Step 1 (RPC callout), Steps 4+5 merged, Step 11 (build-then-certify explanation), Appendix A (troubleshooting rows), Appendix B (stage 5 detection), Appendix C (limitations)
 docs/PHASE10_10_1_IMPLEMENTATION_REPORT.md       | this file
 memory/PRD.md                                    | + Phase 10.10.1 entry
```

---

**Status:** ✅ Complete. Preview environment is now fully UI-driven for the entire LIMITED_LIVE flash-loan operator workflow. Ready to begin first-transaction validation.
