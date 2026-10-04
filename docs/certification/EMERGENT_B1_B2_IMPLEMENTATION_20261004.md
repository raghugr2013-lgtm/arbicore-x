# ArbiCore X — Emergent B1 + B2 Surgical Implementation (2026-10-04)

Flash-loan multichain: **B1** exact-size chain-aware sizing · **B2** discovery-queue chain fairness.
Code implementation ONLY. No deploy, no SHADOW/PAPER/LIVE, no signing/broadcast, no VPS change.

## 1. Starting baseline commit
- Certified application baseline: `9ed2718b3550066934bd11e99a96503ce75a499f` (`9ed2718`).
- **Provenance note:** `9ed2718` and its five remediation commits (`cb79ef1, df12c3d, 4b25cc3, 1241e6c, 9ed2718`) are **not present in this Emergent pod** (this pod descends from `93a20c9`). Implementation was authored against the pod's reconciled working-tree copies of the three target files, which match the certified behaviour described in the approved review. A portable patch is provided so Cursor can apply/verify onto `9ed2718` independent of ancestry. Cursor's own uncommitted B1/B2 tree, `arbicore-x-v2`, the dirty `quoter.py`, and the scoped-throttle test were **NOT** used as sources.

## 2. Implementation commit hash
- Branch: `phase-b/emergent-b1-b2-impl-20261004`
- Commit: `a181634` (see verify below; amended once to embed this SHA — ancestry unchanged)

## 3. Files changed
- `app/backend/arbicore/runtime/composition.py` (B1)
- `app/backend/arbicore/data/discovery_queue.py` (B2)
- `app/backend/arbicore/models/discovery.py` (B2 — additive field)
- `app/backend/tests/test_emergent_b1_multichain_sizing.py` (new)
- `app/backend/tests/test_emergent_b2_discovery_queue_fairness.py` (new)
- `docs/certification/EMERGENT_B1_B2_IMPLEMENTATION_20261004.md` (this report)

## 4. B1 implementation summary
- Root cause: the canonical live scanner wiring (`_wire_canonical_flash_loan_scanner`) built the exact-size `borrow_sizer` from a **Base-only** price source (`_build_base_exact_size_borrow_sizer` → `MultichainPriceSource({"base": ...})`). Non-Base chains (Ethereum, …) therefore had no feed → `price_usd` None → sizer None → `size_basis=probe` → `size_not_quoted` → Gate 7 never reached. The generalized six-chain infra (`build_multichain_price_source`, `_H05_CHAINS`, `build_h05_borrow_sizer`, `ExactSizeBorrowSizer`) already existed but was invoked only by tests.
- Fix (reuse, no parallel architecture): new async helper `_build_live_h05_borrow_sizer(quoter_registry, base_price_feed)` builds the six-chain price source via the existing `build_multichain_price_source(..., chains=_H05_CHAINS)`, **preserves the live Base feed instance** (`price_source._feeds["base"] = base_price_feed`), and returns `build_h05_borrow_sizer(price_source=...)`. Wired into the canonical async path (`borrow_sizer=b1_sizer`).
- Fail-closed/env-gated: returns `None` unless `ARBICORE_BORROW_SIZER_ENABLED` + `ARBICORE_PRICE_FEED_ENABLED`; if no genuine multichain source yields, it preserves the prior Base-only behaviour; a chain with no RPC / no resolvable real pool is omitted (no fabricated price, no unsafe estimate, no probe-as-exact).
- **Scope decision:** the sync seam `build_controlled_live_safety` (line 517) was intentionally left Base-only — converting it to the async six-chain sizer would require a non-minimal sync→async refactor of a non-canonical composition path. The canonical discovery/verifier sizing path (where the Ethereum `size_not_quoted` originates) is fixed. Flagged for Cursor reconciliation.

## 5. B2 implementation summary
- Root cause: `DiscoveryQueue.claim_batch` drained `batch_size` candidates with no chain fairness (effective `expires_at` ordering via the compound index), letting one chain monopolise the batch and starve Arbitrum/Optimism/BNB. `DiscoveryCandidate` had no queryable `chain` field.
- Fix (smallest safe):
  1. Additive optional top-level `chain` on `DiscoveryCandidate` (back-compat; default `None`).
  2. `upsert_many` stamps `chain` when derivable (from `hint_metric["chain"]`, else the `flash_loan:{provider}:{chain}:...` subject convention); never invents one.
  3. New chain index in `ensure_indexes`.
  4. `claim_batch` now fills the batch **round-robin across chains that currently have eligible candidates** (via `distinct("chain", base_filter)`), each claim using the **identical atomic `find_one_and_update` with the identical eligibility predicate**. Legacy/untagged rows match the `None` bucket and remain claimable.
- Preserved exactly: eligibility predicate (`verified_outcome None`, `expires_at > now`, not claimed), expiry semantics, claim locking, `verified_outcome` behaviour. No opportunity forced; no downstream gate touched; no unsupported chain introduced.

## 6. Focused test results
- `test_emergent_b1_multichain_sizing.py` — **7 passed** (six-chain source; Ethereum exact-size; all supported chains; missing-feed fail-closed; Base feed-instance preservation; canonical wiring uses the six-chain helper; disabled→None Base regression).
- `test_emergent_b2_discovery_queue_fairness.py` — **8 passed** (six-chain fairness; skewed counts; no permanent monopoly; expired never claimed; claimed/processed excluded; legacy-without-chain claimable; expiry semantics unchanged; no unsupported chains; + upsert chain-stamping).
- Combined: **15 passed.**

## 7. Regression test results
- Related sizing/six-chain/quote suites: **93 passed** (`test_h06_canonical_sixchain`, `test_h05_exact_size_sizer`, `test_h05_exact_size_binding`, `test_live_quote_provider_multichain`, `test_multichain_univ3_support`, `test_h06_h07_chain_isolation`, `test_flash_route_to_quote_pipeline`, `test_m2_1_live_quote_provider`).
- Discovery-queue/flash suites: **137 passed, 6 skipped, 1 failed**. The single failure — `_pending_scanner_activation/test_d6_1_verifier_scanner_sources.py::test_only_verifier_constructs_canonical_in_flash_loan_pkg` — is a **pre-existing** AST/package-structure check on the `flash_loan_arbitrage` package (which B1/B2 never touch); it fails identically with the B1/B2 changes stashed. Not a regression.

## 8. Base regression verification
- Base keeps its **existing live price-feed instance** (identity-preserved in `_build_live_h05_borrow_sizer`; asserted by test #5).
- `ExactSizeBorrowSizer` and Base sizing formula unchanged; `_H05_CHAINS` still the six supported chains (asserted).
- All Base-path six-chain/quote regression tests pass (§7).

## 9. Polygon — untouched
- No Polygon code modified. Classified **Class E (transient/stale RPC)** per the certified re-probe; to be re-evaluated in post-implementation six-chain verification.

## 10. $100,000 TVL floor — unchanged
- No change to Gate 8 / TVL logic. B2 does not alter eligibility beyond chain-fair ordering; TVL gating remains downstream in the verifier.

## 11. $25 profitability gate — unchanged
- Gate 7 $25 floor untouched. B1 only lets non-Base chains reach Gate 7 with a genuine exact size; it never alters the floor.

## 12. Risk / safety gates — unchanged
- No change to kill-switch, mode ladder, provider restrictions, quote eligibility, freshness, MEV (Gate 9), or fail-closed behaviour. No fabricated pricing/fallback added.

## 13. Network / RPC configuration — unchanged
- No Network Config, RPC config, Alchemy A/B, or provider endpoint change. `MONGO_URL` was supplied only transiently for the local test run; no `.env`/config file modified.

## 14. VPS deployment — none
- No deploy, no container change, no VPS access. Isolated Emergent branch only.

## 15. Signing / broadcast — none
- No signing, no broadcast, no wallet change. SHADOW posture unchanged; nothing started.

---
Next stage: independent Cursor review of this Emergent implementation before any deployment.
