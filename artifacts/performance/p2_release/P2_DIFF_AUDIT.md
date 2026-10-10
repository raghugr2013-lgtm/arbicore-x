# P2 Diff Audit — Included vs Excluded

**Goal:** Prove the release package contains only authorised P2 changes and that unrelated working-tree work remains untouched.

## Method

1. Listed authorised seven-file set.
2. For fully-P2 files: `git diff HEAD -- <file>` (or add-patch for untracked tests).
3. For `discovery_queue.py`: rebuilt **P2-only** file from `HEAD` by applying solely:
   - module docstring durable-`claimed_at` note
   - `mark_processed` stop-clearing-`claimed_at` change  
   Then diffed `HEAD` → that P2-only file.
4. Confirmed working-tree `discovery_queue.py` still contains both P2 and unrelated `queue_status` hunks (not discarded).

## Included hunks (P2)

### 1. `discovery_queue.py` (isolated)

| Hunk | Content |
|---|---|
| Module docstring | Claim lock note: `claimed_at` durable after `mark_processed` |
| `mark_processed` | Remove `"claimed_at": None` from `$set`; still clear `claimed_by` / `claimed_until` |

Patch file: `01_discovery_queue_P2_ONLY.patch`  
Reference file: `discovery_queue_P2_ONLY.py`

Verified **absent** from this patch: `fresh_eligible`, `per_chain_backlog`, `per_strategy_backlog`, expanded `queue_status` signature.

### 2. `models/discovery.py`

Docstring only: `claimed_at` durable; lock fields cleared on process.

### 3. `verifier.py`

Fail-safe timing helpers, stage timers, `evidence_persisted` ternary resolution, diagnostics merge. No RPC client additions.

### 4. `evidence_bundles_repo.py`

`_stamp_insert_evidence_persisted` + call immediately before `insert_one`. No `update_*` APIs added (append-only preserved).

### 5. `test_flashloan_diagnostic_provenance.py`

Assertions accept additive `diagnostics.timing`.

### 6–7. New test modules

Full add patches for focused P2 / Option D coverage.

## Excluded hunks (must NOT ship as P2)

### `discovery_queue.py` working-tree extras (6 non-P2 hunk groups)

Present in **working tree**, **excluded** from `01_discovery_queue_P2_ONLY.patch` / `P2_ONLY_COMBINED.patch`:

| Theme | Examples |
|---|---|
| `queue_status` API expansion | `fresh_window_s`, `include_breakdowns` parameters |
| Fresh backlog metric | `fresh_eligible`, `fresh_cutoff` |
| Breakdown telemetry | `per_chain_backlog`, `per_strategy_backlog` aggregation |

These remain in the live working copy so unrelated work is **preserved**.

### Other dirty-tree paths (not in P2 package)

Scanner / frontend / ledger / server / worker-pool / untracked certification artifacts / etc. — not packaged.

## Isolation result

| Check | Result |
|---|---|
| P2 package excludes `queue_status` backlog hunks | **Pass** |
| Working-tree unrelated `discovery_queue` edits preserved | **Yes** (`fresh_eligible` / `per_chain_backlog` still present in WT) |
| Shared branch commit created | **No** |
| Destructive stash/reset of unrelated work | **No** |

## Packaging note for deployers

Do **not** `git add app/backend/arbicore/data/discovery_queue.py` from the dirty tree for a P2 commit. Use `P2_ONLY_COMBINED.patch` (or replace only the P2 hunks) so unrelated backlog reporting is not accidentally released under the P2 label.
