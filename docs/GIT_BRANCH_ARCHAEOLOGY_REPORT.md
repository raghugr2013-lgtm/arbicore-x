# ArbiCore X — Git Branch Archaeology Report

_Generated during the FINAL MASTER autonomous engineering pass. Read-only Git
inspection; no history rewritten, no branches/tags deleted, no force-push._

## 1. Repository facts

- Remote: `origin` → `github.com/raghugr2013-lgtm/arbicore-x.git`
- Checked-out branch on clone: **`main`**
- `main` HEAD: **`43230f6`** — "Clarify limited live readiness authorization" (2026-08-22)
- Working tree on arrival: modified only by an automated **preview-URL rewrite**
  (`defi-exec-audit…` → `arbicore-canonical-1…`) across 44 test/doc files —
  cosmetic, no logic change.

## 2. Branches reviewed (all remote branches)

| Branch | HEAD | Date | Purpose | Verdict |
|---|---|---|---|---|
| `main` | `43230f6` | 2026-08-22 | Mainline | **Behind canonical** (ancestor of c284183) |
| `fix/canonical-scanner-pool-loader-integration` | **`c284183`** | 2026-09-01 | Known-good baseline + 99-test safety gate, stop-loss, RPC failover | **CANONICAL** |
| `complete-Base-M1-M4-live-shadow-composition` | `0a04d4d` | 2026-08-29 | Base M1–M4 live-shadow composition | Superseded (ancestor of c284183 lineage) |
| `checkpoint/2026-08-31-pre-limited-live` | `166a5cc` | 2026-08-31 | Provider failover / M2.5 checkpoint | Folded into c284183 |
| `flashloan-live-shadow` | `8e49fa7` | 2026-08-24 | Base WSS runtime + activation runbook | Feature branch; WSS SHADOW work |
| `scanner-bootstrap-validator-fix` | `515b49f` | 2026-08-22 | Scanner bootstrap + validator-contract fix | Folded / superseded |
| `hotfix/auth-routing` | `57b0e72` | 2026-08-05 | v2.9.3 auth routing hotfix | Merged historically |
| `feature/ui-v2-slices-0-2` | `a4580d0` | 2026-07-30 | UI v2 slices | Merged historically |
| `archive-v1` | `f372911` | 2026-07-29 | v1 archive | Historical archive only |

Tags: `v1.0.0 … v2.9.2` (20 tags). Latest release tag = **v2.9.2**, matching the
known-good image `arbicore-x-backend:2.9.2-c284183`.

## 3. Canonical determination (evidence-based)

**Canonical = `c284183` (branch `fix/canonical-scanner-pool-loader-integration`).**

Evidence:
- `git merge-base --is-ancestor 43230f6 c284183` → **true**: current `main` HEAD is
  an **ancestor** of c284183.
- `git log c284183..main` → **empty**: `main` contains **no** commits absent from c284183.
- `git log main..c284183` → **~20 commits** present only in c284183, including:
  - `0935070` feat(safety): additive operator STOP-LOSS (`max_daily_loss_usd`)
  - `52a6011` fix(providers): deterministic Base RPC provider lifecycle (P0 registry bug)
  - `7aea7c0` P1 RPC failover (Alchemy 429) — "signer/broadcast/executor/live-mode untouched"
  - `c284183` 99-test deterministic safety gate wired into CI — "no protected logic touched; SHADOW enforced"

Therefore c284183 is simultaneously the **newest**, **most complete**, and
**safest** line, and it is a strict superset of `main`. It matches the directive's
declared known-good baseline exactly (commit `c284183…`, image `2.9.2-c284183`).

## 4. Conflicts / duplication / lost work

- **No unresolved conflicts** in the working tree.
- **Lost/unmerged safety work:** the stop-loss, RPC failover, and 99-test safety
  gate commits live on c284183 and were **never fast-forwarded into `main`**. They
  are additive and fail-closed per their commit messages. Recovering them = fast-
  forward `main` → c284183 (no rewrite, no conflict, since `main` is an ancestor).
- **Duplicate auth implementations (historical, already resolved):** two auth trees
  existed — canonical Tree-A (`routes/auth.py` + `services/auth.py`, collection
  `users`) and legacy Tree-B (`auth_users`). Tree-B is retired/ gated off since
  v2.9.3 (`ARBICORE_LEGACY_AUTH_SEED != '1'`). Confirmed only Tree-A is mounted.

## 5. Recovered vs rejected

- **Recovered / adopted as canonical:** c284183 lineage (safety gate + stop-loss +
  RPC failover). Recommended action: fast-forward `main` to c284183 via the
  operator's "Save to GitHub" flow (non-destructive).
- **Rejected for resurrection:** `archive-v1` (v1, superseded); legacy Tree-B auth
  seed (retired, would reintroduce dual-store drift). No unsafe execution code was
  incorporated.

## 6. Relation summary

```
archive-v1 (v1) ──✗ rejected
main (43230f6) ──────────────► c284183  (fast-forward; main ⊂ c284183)  ◄── CANONICAL
                                  ▲
   flashloan-live-shadow / checkpoint / complete-Base-M1-M4 ── folded/superseded
```
