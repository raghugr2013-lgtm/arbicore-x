# Emergent Clean Code + Certification Handoff

**Date (UTC):** 2026-10-04  
**Classification:** see final section  
**Runtime actions:** none (no deploy, restart, Network Config change, RPC change, or application-code modification)

---

## A. Certified application baseline

```text
9ed2718b3550066934bd11e99a96503ce75a499f
```

| Check | Result |
|---|---|
| Subject | `fix(flash-loan): accept a missing BNB chain key and scope providers` |
| Live `BUILD_INFO.git_sha` | `9ed2718b3550066934bd11e99a96503ce75a499f` |
| Image tag | `arbicore-x-backend:flash-discovery-readiness-9ed2718` |
| Image Id | `sha256:92a51023b75675f5be2d584345c6b3b7d2de44f66c659d4c291051879d842cfb` |
| `git diff 9ed2718 HEAD -- app/backend` | **empty** (no application-code differences) |

**Emergent must begin from this SHA for application code.**

Do **not** use:
- host dirty working tree
- `arbicore-x-v2` HEAD (`5bd9525…` on `emergent/arbitrage-engineering-handoff-20260930`)

---

## B. Documentation-only commits after baseline

| Commit | Role |
|---|---|
| `ab2d6d5b8fc92b6deb47469152497a98d0245fcb` | Already present before this handoff: post-remediation pre-SHADOW coverage audit (docs-only) |
| `e503551f3a74041600ee6e0405c2b86be2bc0a89` | Oct 4 flash-loan readiness / pipeline / blocker pack + Git–VPS integrity + this clean-handoff report (docs-only) |

No application-code commit is part of this handoff preparation.

---

## C. Exact certification reports included

### Committed as part of this handoff (docs-only)

- `docs/certification/FLASH_LOAN_DISCOVERY_RUNTIME_READINESS_20261004.md`
- `docs/certification/FLASH_LOAN_DISCOVERY_SIX_CHAIN_PIPELINE_CERT_20261004.md`
- `docs/certification/FLASH_LOAN_SIX_CHAIN_BLOCKER_DIAGNOSTIC_20261004.md`
- `docs/certification/EMERGENT_HANDOFF_GIT_VPS_INTEGRITY_20261004.md`
- `docs/certification/EMERGENT_CLEAN_HANDOFF_20261004.md` (this file)

### Already committed on the docs tip before this handoff

- `docs/certification/PRE_SHADOW_STRATEGY_COVERAGE_AUDIT_POST_REMEDIATION_20261003.md` (`ab2d6d5`)

### Related evidence still outside this docs commit (explicitly not required for code baseline)

Other Oct 2–3 cert/report files may remain untracked in the workspace. They are **not** required to reconstruct the certified product tip `9ed2718`. Emergent should not treat an incomplete docs tree as a product-code mismatch.

---

## D. Explicitly excluded host-only changes

| Path | Why excluded |
|---|---|
| `app/backend/arbicore/execution/quoter.py` (dirty) | Host-only; **not** in deployed image. Container SHA matches `9ed2718` / clean HEAD, not the dirty working tree. |
| `app/backend/tests/test_quoter_scoped_throttle.py` (dirty) | Host-only test delta; not part of certified deployed product. |
| `arbicore-x-v2` working tree / HEAD | Different branch tip; not the remediation baseline. |

---

## E. Current runtime image

```text
arbicore-x-backend:flash-discovery-readiness-9ed2718
sha256:92a51023b75675f5be2d584345c6b3b7d2de44f66c659d4c291051879d842cfb
```

Container: `arbicore-x-backend-new` (running). Image unchanged by this handoff task.

---

## F. Current Network Config revision

```text
rev-d069f13244ba44da81f97e72f7cfce5b
```

Verified live from Mongo `arbicore_x.arbicore_config` (`_id=network`), `updated_at=2026-10-03T15:27:57.368745+00:00`.  
Six-chain Alchemy A (`cd505118`) → B (`124bc59c`) applied configuration remains in place. **Not modified** by this handoff.

---

## G. Five remediation commits already incorporated in `9ed2718`

| Commit | Subject |
|---|---|
| `cb79ef17ad52b8458babeb074adf38c6f0873da3` | scanner enabled-state cache mirror |
| `df12c3dfb21630d98f7c8a70334a2d22787e0f86` | measured pool TVL before $100k floor |
| `4b25cc3b829b67b2590bc0d7169c7a3ea1e772bb` | plan hops on registered quoters |
| `1241e6ca23a9dc875aa19e1e5c4f36cdb12bc5e9` | triangular legs from quotable pools |
| `9ed2718b3550066934bd11e99a96503ce75a499f` | BNB chain key + provider scope |

All are ancestors of the deployed baseline.

---

## H. Current known blockers (from certified diagnostic)

Source: `FLASH_LOAN_SIX_CHAIN_BLOCKER_DIAGNOSTIC_20261004.md`  
**PRE-SHADOW GO: NO** until these are addressed surgically on top of `9ed2718`.

1. **Ethereum** — multichain / H05 sizing still Base-wired → `size_basis=probe` → `denied:size_not_quoted` (Gate 7 never reached).
2. **Arbitrum / Optimism / BNB** — `DiscoveryQueue.claim_batch` is `expires_at`-ordered without chain fairness → verifier starvation (0 ever verified) despite TVL-qualified candidates.
3. **Polygon** — in-window handoff gap; historical `venue_unreadable` coincided with RPC degradation and needs re-test after handoff fairness is fixed.

Safety gates (`$100k` TVL floor, `$25` Gate 7, no signing/broadcast) remain intentional and must not be weakened for handoff.

---

## I. Explicit baseline statement

> **Emergent must begin from application commit `9ed2718b3550066934bd11e99a96503ce75a499f` and must not treat dirty host changes or `arbicore-x-v2` as the product baseline.**

Documentation commits after that tip are certification/handoff only and do not change application code.

---

## Verification performed for this handoff

| Check | Result |
|---|---|
| `git diff 9ed2718 HEAD -- app/backend` empty | **PASS** |
| Dirty `quoter.py` / scoped-throttle **not** staged | **PASS** |
| Oct 4 flash-loan cert docs secret-scan (no raw keys) | **PASS** (policy language / public address only) |
| Docs-only commit (no `app/` paths) | **PASS** (see commit) |
| Live image still `flash-discovery-readiness-9ed2718` / `9ed2718` | **PASS** |
| Network Config still `rev-d069f13244ba44da81f97e72f7cfce5b` | **PASS** |

---

## Final classification

**CLEAN_EMERGENT_HANDOFF**

Rationale: certified product baseline is unambiguous (`9ed2718`), application tree at Git tip matches that baseline, host-only dirty product files are excluded, live image and Network Config are unchanged, and the Oct 4 flash-loan certification pack is tracked via a docs-only commit.

**STOP.**
