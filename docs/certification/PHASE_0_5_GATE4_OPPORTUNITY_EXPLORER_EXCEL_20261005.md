# Phase 0.5 Gate 4 — Opportunity Explorer and Excel export

**Classification: PHASE_0_5_GATE4_PASS**

**Date:** 2026-10-05

Research surface over the Opportunity Ledger. It does not read discovery candidates or verifier bundles, and it does not start a scanner, a SHADOW window, or a trade. The running production process was not restarted and was not given this code. The acceptance numbers below were produced by executing the same read model and workbook builder the new routes call, against the 288 stored ledger rows.

No commit and no push.

---

## Baseline

| | |
|---|---|
| Worktree HEAD | `9ed2718b3550066934bd11e99a96503ce75a499f` |
| Implementation commit | None. Commit was not requested. |
| Certified runtime | `arbicore-x-backend:phase0-823a79b`, container id `096bcb87b121…d279ea33`, PID `2823992`, restart count `0` |
| Ledger run | `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065` |

Unrelated dirty files (`discovery_queue.py`, `discovery.py`, `composition.py`, and pre-existing untracked docs and tests) were not edited.

---

## Files changed

| Path | Role |
|---|---|
| `app/backend/arbicore/opportunity_ledger/read_model.py` | Summary, filters, sort, pagination, detail, timeline |
| `app/backend/arbicore/opportunity_ledger/export_xlsx.py` | Seven-sheet workbook |
| `app/backend/arbicore/opportunity_ledger/store.py` | Ledger-collection reads only |
| `app/backend/arbicore/routes/ledger_explorer.py` | Read-only HTTP routes |
| `app/backend/server.py` | Mounts that router |
| `app/backend/tests/test_ledger_explorer.py` | API-model and workbook tests |
| `app/frontend/src/v2/pages/LedgerExplorerPage.jsx` | Research page |
| `app/frontend/src/v2/lib/ledgerFormat.mjs` | Null, zero, leg order, page window |
| `app/frontend/src/v2/lib/ledgerFormat.test.mjs` | Display and control-surface checks |
| `app/frontend/src/v2/lib/api.js` | Ledger GET helpers |
| `app/frontend/src/v2/lib/nav.js` | Ledger nav entry |
| `app/frontend/src/v2/components/AppShell.jsx` | Route `/dashboard/ledger` |

---

## API

All routes require the existing `require_auth` dependency. There are no POST, PUT, or DELETE handlers.

| Method | Path |
|---|---|
| GET | `/api/arbicore/ledger/runs` |
| GET | `/api/arbicore/ledger/runs/{run_id}/summary` |
| GET | `/api/arbicore/ledger/opportunities` |
| GET | `/api/arbicore/ledger/opportunities/{ledger_id}` |
| GET | `/api/arbicore/ledger/runs/{run_id}/export` |

The list endpoint asks Mongo only for the columns the table needs. Legs and the economics block are not in that projection. Detail and export load the full ledger document for one `run_id` or one `ledger_id`.

Run start and end shown in the UI are the minimum and maximum `verified_at` values stored on the ledger rows. They are labeled `ledger verified_at span`. The certification document is not queried.

The page is at `/dashboard/ledger`. Its only action is Download Excel. The page source does not contain resume, kill, broadcast, wallet, threshold, or sign controls.

---

## Ledger source of truth

`summarize`, `apply_filters`, `paginate`, and `build_workbook` accept ledger documents. They do not open `arbicore_discovery_candidates` or `evidence_bundles`. Family, decision net, gates, and legs are read from `evidence` on the ledger row.

A list item does not include `legs` or `economics`. Confirmed on the October 5 page-1 response built by `paginate`: 25 items, `has_legs` false, `total` 288.

---

## October 5 validation

Executed read-only against `arbicore_opportunity_ledger` for this run. Other runs in the collection: 0.

| Check | Result |
|---|---|
| Rows | 288 |
| Verifier-backed | 180 |
| Decision-only | 108 |
| `DEX_TO_DEX` | 17 |
| `CROSS_PROTOCOL` | 8 |
| `CROSS_POOL` | 27 |
| `MULTI_HOP` | 27 |
| `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | 83 |
| `MULTI_DEX` | 34 |
| `TRIANGULAR` | 92 |
| Mean decision net | `-345.3213194444445` (half-up `-$345.32`) |
| Best | `-59.31` (`31df13631b18c7175c30`) |
| Worst | `-1709.9` |
| `>= $0` | 0 |
| `>= $25` | 0 |
| Filter `DEX_TO_DEX` | 17 |
| Filter decision-only | 108 |
| Filter verifier-backed | 180 |

Chains: ethereum 45, arbitrum 54, base 54, optimism 45, polygon 45, bnb 45.

Providers: `aave_v3` 134, `balancer_v2` 82, `uniswap_v3` 72.

Stored Gate 7 status object: `FAIL` 180, unavailable 108, `PASS` 0. The 108 decision-only rows have no gate object; their decision net and final status text are still the stored Gate-7 sentence. The UI shows the stored status and the final status separately. It does not invent a `FAIL` object for those 108.

The page does not hardcode 288, 180, 108, or the family counts. Those fields are rendered from the summary payload.

---

## Excel

Workbook built from the same 288 ledger rows.

| Sheet | Data rows |
|---|---:|
| Summary | run id, period, totals, distributions, best and worst |
| Opportunities | 288 |
| Price Path | 1003 stored legs |
| Economics | 288 |
| Strategy Intelligence | 288 |
| Timeline | 756 |
| Learning Dataset | 288 |

Sheet names and order match the seven required names.

Timeline rows are 288 `DISCOVERED` (`hint_observed_at`) + 288 `VERIFIED` (`verified_at`) + 180 `BUNDLE_RECORDED` (`bundle_created_at`). Stages without a stored timestamp are omitted. No classified or executed stage is added.

Focused tests on a synthetic 288-row ledger shape also check that slippage `0` stays `0`, `gross_profit_usd` stays blank, the first two price-path legs stay in index order (`USDC` then `WETH`), and `DEX_TO_DEX` is the stored family.

---

## Secret sanitization

`sanitize` drops strings that contain a URL, a Mongo URI, a private-key banner, or a JWT-shaped token. Detail responses and workbook cells pass through it.

The synthetic workbook test plants `supersecretvalue` in a chain URL and a Mongo URI. The saved workbook does not contain that token.

The workbook generated from the 288 stored rows had 0 cells matching those secret patterns.

---

## Tests

| Suite | Result |
|---|---|
| `tests/test_ledger_explorer.py` | 6 passed |
| `tests/test_opportunity_ledger_v1.py` | 9 passed |
| `src/v2/lib/ledgerFormat.test.mjs` | 4 passed |
| `test_gate7_floor_is_still_25` | passed |
| `test_gate7_and_gate8_thresholds_unchanged` | passed |

Explorer tests cover summary totals, family counts, filters, sort, pagination, slim list rows, null versus zero, Gate 7 reason text, leg order, timeline omission, seven sheets, and secret stripping.

Display tests cover unavailable versus `0`, leg reordering, the page window for 288 rows, and the absence of execution-control words on the page.

Gate 7 source was not edited. The floor remains `$25`.

---

## Safety

After the read-only check:

| Check | Value |
|---|---|
| Image | `arbicore-x-backend:phase0-823a79b` |
| Container id / PID / restarts | unchanged / `2823992` / `0` |
| Execution mode | `SHADOW` |
| Signing active key | unset |
| Network Config revision | `rev-1068cb9715194f118c99e5f04f9e1bdb` |
| Network Config `updated_at` | `2026-10-04T14:24:36.649620+00:00` |
| Scanner `enabled` | six rows, all `false` |
| Ledger rows for this run | 288 |

No SHADOW, PAPER, or RECOMMENDATION run was started. No scanner was resumed. No deploy and no restart. The temporary copy of the ledger package used to execute the read model inside the container was removed. The production process does not yet serve `/api/arbicore/ledger` or `/dashboard/ledger`; those routes exist in this worktree.

---

## Discrepancies

None on the certified counts, family distribution, mean, best, or the `$0` and `$25` counts.

The stored Gate 7 object is `FAIL` on the 180 bundle rows and absent on the 108 decision-only rows. That matches how the ledger was projected. The final observed status on the decision-only rows remains the Gate-7 denial text.

PHASE_0_5_GATE4_PASS
