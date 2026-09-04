# Pre-Flight Operator Audit — Before First LIMITED_LIVE Flash Loan

**Date:** 2026-08-01
**Type:** READ-ONLY (no code modifications; test writes cleaned up)
**Environment:** Preview (`https://p0-3-certification.preview.emergentagent.com`)
**Requester intent:** confirm end-to-end operator flow is safe to execute before spending real ETH.

---

## Verdict

**🔴 DO NOT PROCEED with LIMITED_LIVE Flash Loan yet.**

Two architectural blockers (B1, B2) prevent the certification-to-broadcast handoff from working. They are small, additive fixes (~5 LOC each) but they are prerequisites. Everything else is either **PASS** or **WARN with clean workaround**.

---

## PASS — verified working (10 items)

| # | Capability | Evidence |
|---|---|---|
| P1 | Persistent Network config + Phase 10.10 env sync | `POST /apply` with fake URL → immediate `/rpc/check` calls the new URL. Confirmed on this run. |
| P2 | Scanner config persistence (global + families) | `GET /settings/scanner` returns global + `flash_loan_arb` providers structure intact. |
| P3 | Wallet registration (post G3 fix) | `POST /wallets` returns `{item: {wallet_id, label, secret_handle_id, ...}}`; frontend correctly reads `data.item`. |
| P4 | Secret storage (Fernet write-only) | `POST /secrets` returns `{ok:true, handle:{handle_id:"sec-...", mask:"...."}}`. Plaintext never appears in response. |
| P5 | Secret ↔ Wallet linking | Wallet POST with `secret_handle_id` correctly preserves the handle in the stored row (verified end-to-end with a fresh secret + wallet pair, cleaned up after). |
| P6 | Executor Verify code path | All 6 checks execute; `address_configured:BLOCKED — ARBICORE_EXECUTOR_ADDRESS_BASE is un…` with helpful detail; will flip green once contract deployed and address applied. |
| P7 | Journey endpoint returns 14 live stages | `GET /wizard/journey` returns full stage list with dynamic status; progress calculation correct. |
| P8 | Post-trade + evidence read APIs | `/post-trade/latest` returns receipts/calibration/evidence/adaptive_weights structure. `/intelligence/evidence/history` and `/intelligence/calibration/history` populated (3 historical entries each). |
| P9 | Broadcast gate ladder wired end-to-end (structurally) | Gates 1–3 PASS on a valid plan; Gates 4–5 correctly DENY when secret/executor missing. All 6 gate slots present in receipt. |
| P10 | Kill switch, mode set/get | `POST /execution/mode/{strategy}` with `{"to_mode": "..."}` works; audit history captured. |

---

## WARN — works with caveats (5 items)

### W1 · RPC 403 on public Base endpoint (not a code issue)

- **Symptom:** `mainnet.base.org` returns `HTTP 403 Forbidden` from the Preview's egress IP.
- **Cause:** Base's public RPC rate-limits/blocks cloud provider IP ranges.
- **Impact:** `GET /rpc/check` returns `WAIT`; Journey stage 2 sits at `BLOCKED`; wizard `rpc` step also `BLOCKED`.
- **Recommended action for operator:** provision a **private RPC endpoint** (Alchemy / QuickNode / Ankr — free tiers all work) and paste the URL into Settings › Network → APPLY. **This is not optional for reliable operation.**

### W2 · No wallet DELETE endpoint (walkthrough instruction breaks)

- **Symptom:** `DELETE /api/arbicore/execution/wallets/{id}` is not defined; requests return no-op.
- **Impact:** Walkthrough Manual Step 5 says "delete the wallet you just created and re-register with the handle_id". This instruction cannot be followed via API or UI.
- **Clean workaround (no code change needed):** re-order the walkthrough — store the secret **first** (Step 3), then register the wallet **with the handle_id already populated** in the form. Never need to delete.
- **Recommendation:** update walkthrough Step 4/5 to reflect the natural order. (**Documentation-only fix, no code change.**)

### W3 · Secret POST response shape is `{handle: {handle_id}}` (not flat)

- **Symptom:** first-time integrators may read `data.handle_id` and get `undefined`.
- **Impact:** none for the operator UI (Settings › Secrets already handles the correct shape).
- **Recommendation:** documented; no action.

### W4 · Mode set endpoint requires `to_mode` (not `mode`) in body

- **Symptom:** `POST /execution/mode/{strategy}` with `{"mode": "X"}` returns `to_mode is required`.
- **Impact:** the Operator page's mode-ladder buttons — verified in code review — send `to_mode` correctly. No user-facing issue.
- **Recommendation:** documented; no action.

### W5 · Journey polling is reactive, not push-based

- **Symptom:** Journey badges flip within ~5 seconds of a state change (frontend polls; backend re-derives status on each GET).
- **Impact:** cosmetic. Operator experience is fluid.
- **Recommendation:** documented in Walkthrough Appendix.

---

## 🔴 BLOCK — must be fixed before LIMITED_LIVE (4 items, 2 root causes)

### B1 · `POST /certification/run` does NOT persist plans

- **Symptom:** the certifier returns `report.plan_id` (e.g. `plan-eabc81137fc643ffa6a5511ff94174d5`), but `GET /plans/{plan_id}` returns `plan: null`.
- **Verified:** replicated on this run — certification returned plan_id, GET returned null, broadcast returned `"plan 'plan-…' not found"`.
- **Impact:** the FlashLoanOperatorPage broadcast flow — both the pre-existing auto-discovery path AND the new G4 Manual Plan Composer — is broken end-to-end. The broadcast button will always error with "plan not found".
- **Root cause:** `server.py:2626–2654` `v2_execution_certification_run` calls `_EXECUTION_CERTIFIER.certify(...)` but never calls `_EXECUTION_PLANS_REPO.insert(...)`. `/plans/build` does insert; `/certification/run` does not.
- **Historical note:** `/certification/run` was designed as a "would-this-broadcast?" preview endpoint (asserts `would_broadcast=False`). It was never expected to feed broadcast. The FlashLoanOperatorPage's `broadcastPlan(certReport.plan_id)` wire-up was incorrect from Wave 7C onwards.

### B2 · `POST /plans/build` refuses LIMITED_LIVE strategies (Wave 6B leftover)

- **Symptom:** when `flash_loan_arbitrage` is in mode `LIMITED_LIVE`, `/plans/build` returns:
  > `"strategy 'flash_loan_arbitrage' is in mode 'LIMITED_LIVE' — Wave 6B builds plans in SHADOW/PAPER/OBSERVE only"`
- **Verified:** replicated on this run.
- **Root cause:** `server.py:2296` — `if current_mode not in ("OBSERVE", "PAPER", "SHADOW"): return error`. Guard was scaffolding for Wave 6B safety. A comment in the code says "that will land in Wave 6E" — Wave 6E was never delivered, so the guard was never relaxed.
- **Impact:** after the operator promotes the strategy to LIMITED_LIVE (walkthrough Step 10), they cannot compose a new plan through `/plans/build`. The Wave 6B guard blocks it.
- **Note:** the LIMITED_LIVE broadcast pipeline itself (`LimitedLiveBroadcaster.broadcast_plan`, `broadcast.py:179–183`) already enforces mode at Gate 2 (must be LIMITED_LIVE or FULL_LIVE). So building a plan in LIMITED_LIVE mode is safe — building alone never broadcasts. The Wave 6B build-time guard is redundant with the broadcast-time gate.

### B3 · Manual Plan Composer (G4) wires to the wrong endpoint

- **Symptom:** consequence of B1. The composer's "Run full certification (manual plan)" button posts to `/certification/run`; the resulting plan_id is not broadcastable.
- **Impact:** the composer produces a valid certification verdict (PASS/WAIT/HARD_NO) — that stage works — but the operator cannot then click Broadcast because the plan_id doesn't exist in the plans repo.
- **This is a wiring error in the G4 fix I shipped**, exposed only by this audit. Recommended remedy is R1 below.

### B4 · FlashLoanOperatorPage auto-discovery `certifyPlan` has the same wiring error

- **Symptom:** same as B3. Pre-existing before G4.
- **Impact:** even before the manual composer existed, an operator could not have broadcast a certified opportunity — the certification path never persisted the plan.

---

## Broadcast pipeline structural test — the workaround IS valid

I ran a controlled "build-then-promote-then-broadcast" workaround on this environment to verify the pipeline itself is functional:

```
[1] Set mode SHADOW                        → OK
[2] POST /plans/build (SHADOW plan)        → persisted plan_id
[3] Set mode LIMITED_LIVE                  → OK
[4] POST /plans/{id}/broadcast (confirm=false) → gates ran to Gate 5:
        gate kill_switch          PASS
        gate mode                 PASS       (LIMITED_LIVE)
        gate capital_policy       PASS
        gate secret_resolution    DENIED     (wallet has no secret_handle_id)
        gate calldata             DENIED     (no executor deployed)
```

**Interpretation:** the 6-gate ladder is 100 % wired and functional. Gates 4 and 5 correctly deny because the test wallet is intentionally under-provisioned. Once the operator has (a) a gas wallet with secret linked, (b) an executor deployed and configured, the workaround path will run all 6 gates to PASS and broadcast.

**However**, this workaround requires the operator to build in SHADOW, promote to LIMITED_LIVE, broadcast — and if they compose Tx#2, they must go back to SHADOW to build, then promote again. That is not the operator experience the walkthrough describes, and it is a footgun.

---

## Remaining operator blockers before first LIMITED_LIVE tx

| Blocker | Type | Fix |
|---|---|---|
| B1 + B3 + B4 (certifier doesn't persist) | code | R1 |
| B2 (plans/build refuses LIMITED_LIVE) | code | R2 |
| W1 (public RPC 403) | operator action | provision private RPC |
| W2 (walkthrough delete-and-recreate) | doc | R3 |
| No FlashLoanReceiver deployed yet | external | operator task |
| No gas wallet with secret linked yet | operator action | walkthrough Steps 3+4 (post-R3 order) |
| Burner wallet unfunded | external | operator task |

---

## Recommended actions (in priority order)

### R1 · P0 — Fix certification-to-broadcast handoff (~10 LOC)

**Option A (preferred):** modify `/certification/run` to persist the plan on non-HARD_NO verdicts. Small change to `server.py:2626-2654`.

**Option B:** modify the frontend so the "Run full certification" button chains `POST /plans/build` first (which persists), then `POST /certification/run` for the verdict display. Keeps backend unchanged. Frontend-only.

**Recommendation:** **Option B** is preferable — it keeps the backend contract stable and aligns better with the "REUSE existing endpoints" principle. Ship an updated `certifyManualPlan` (and the pre-existing `certifyPlan`) that:
1. POSTs `/plans/build` with the composed payload → captures `plan_id`
2. POSTs `/certification/run` with the same payload → captures `report` (for verdict display)
3. Broadcasts using the `plan_id` from step 1.

Adds ~5 LOC to `FlashLoanOperatorPage.jsx`. Zero backend changes.

### R2 · P0 — Lift Wave 6B guard on `/plans/build` for LIMITED_LIVE (~1 LOC)

Change `server.py:2296` from:
```python
if current_mode not in ("OBSERVE", "PAPER", "SHADOW"):
```
to:
```python
if current_mode not in ("OBSERVE", "PAPER", "SHADOW", "LIMITED_LIVE"):
```

The broadcast pipeline enforces mode independently at Gate 2, so this is safe. The comment on line 2292 that says "that will land in Wave 6E" is the design intent.

### R3 · P1 — Update walkthrough Steps 3–5 order (docs only)

Reorder:
- Step 3 (currently): Store Secret → keep as-is
- Step 4 (currently): Register Wallet — **update to**: "paste the handle_id from Step 3 into the Secret handle id field"
- Step 5 (currently "Link the Secret to the Wallet, using delete-and-recreate") → **delete this step entirely** (linking now happens at registration in Step 4)
- Renumber remaining steps 6→5, 7→6, etc.

### R4 · P1 — Add prominent private-RPC recommendation to walkthrough Step 1

Add a callout box: **"The Preview environment cannot reach `mainnet.base.org` due to egress restrictions. You MUST provide a private RPC endpoint (Alchemy / QuickNode / Ankr — free tiers all work)."**

---

## Summary

The **10 PASS items** demonstrate that Phase 10.10, the G2/G3/G4 fixes, and the underlying broadcast pipeline are all structurally sound.

The **2 root-cause BLOCKs** (B1 = certifier doesn't persist; B2 = build-in-LIMITED_LIVE guard) prevent the certified-plan → broadcast handoff and are hard prerequisites for the first LIMITED_LIVE tx. Together they require ~6 lines of code across two files: 5 LOC in `FlashLoanOperatorPage.jsx` (R1 · Option B), 1 LOC in `server.py:2296` (R2), plus the doc reorder (R3) and RPC callout (R4).

Once R1 + R2 are shipped, the operator flow is truly end-to-end UI-driven except for the two external tasks (funding the burner, deploying the contract).

**Estimated implementation time (when approved): ~15 minutes + regression test.**
