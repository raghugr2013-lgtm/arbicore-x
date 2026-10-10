# G1.6 Closeout — Offline false-arbitrage guard

**Closeout status:** **CLOSED WITH DOCUMENTED LIMITATIONS**  
**Closeout UTC:** `2026-10-09T05:29:42Z`  
**Workspace:** `artifacts/g15/g16_false_arbitrage_guard_20261009/`  
**Mode:** Read-only verification. No collector/Base-tracker/ledger/production changes. Frozen Oct 8 export untouched.

---

## 1. Deliverables present (verified)

| Deliverable | Path | Status |
|---|---|---|
| Guard module | `false_arbitrage_guard.py` | Present |
| Frozen runner | `run_guard_on_frozen.py` | Present |
| Unit tests | `test_false_arbitrage_guard.py` | Present; **11 passed** (re-run this closeout via v2 venv) |
| Methodology | `G1_6_METHODOLOGY.md` | Present |
| Before/after report | `out/G1_6_FROZEN_BEFORE_AFTER.md` + `out/g16_before_after.json` | Present |
| Flagged rows | `out/g16_flagged_rows.jsonl` (222 lines) | Present |
| Mirror links | `out/g16_mirror_links.json` (88 link rows) | Present |
| Prior verdict | `out/G1_6_VERDICT.md` | Present (`PASS WITH LIMITATIONS`) |
| This closeout | `G1_6_CLOSEOUT.md` | Present |

**Not present (by design):** no copy under `app/backend`, no collector/Base-tracker wiring, no production deploy.

---

## 2. Validations actually performed

| Check | Result |
|---|---|
| Frozen winners sha256 | `f525083f2ef218ce4532993c1dcc41e8807d0db68824408d9d4675d4ad871714` — matches MANIFEST + prior G1.6 run |
| Base rows processed | 6287 |
| Classification preserved | **True** (`A:1418 B:4252 C:57 D:560` unchanged) |
| Flag histogram | `NO_FLAG:6065`, `POTENTIAL_CROSS_TX_MIRROR:118`, `REPEATED_POOL_ROUTE:98`, `BOTH_FLAGS:6` |
| Flagged rows | 222 / 6287 |
| Unique mirror pairs | 68 (88 raw link rows) |
| Unit tests (closeout re-run) | **11 passed** in 0.04s |
| Offline-only posture | Guard lives only under this artifacts tree |

---

## 3. Documented limitations (preserved — not claimed complete)

### 3.1 Unavailable sources (binding)

| Asset | Observed this closeout |
|---|---|
| `/workspace/g15` | **Absent** on this host (`ls` → No such file) |
| `code/gcpipe/` (`families_lib.py`, `analyze.py`, …) | Listed in G1.5 `MANIFEST.md` but **not present** in the transferred core export (`…/G1_5_EXPORT_20261008T2216Z/` contains only winners/ledger/`out`/REPORT/MANIFEST) |

G1.6 therefore remains an **offline accounting guard derived from the winners schema**, not a patch against live collector/`gcpipe` code. This limitation is intentional for scope and is **not** closed by this report.

### 3.2 Unverified acceptance criteria (recorded as limitations)

These were **not** independently verified against missing collector/`gcpipe` sources and must not be treated as completed work:

1. **Parity with original G1.5 analyzer / `families_lib` mirror logic** — unverifiable without `/workspace/g15` and `gcpipe` sources.
2. **Live-collector / Base-tracker integration** — out of scope; not done; must remain offline-only until a separate authorised workstream.
3. **Proof that flags equal fraud / zero economic profit** — explicitly non-goal; flags are investigation signals only.
4. **Future 48-hour winners export re-run** — not performed; methodology documents how to point `FROZEN` at a new file without modifying the Oct 8 export.
5. **Production runtime effect** — none; not deployed (correct).

### 3.3 Method parameters (accepted as fixed for this offline package)

- Amount tolerance fixed at 5%; block window ±3 inclusive.
- Same-searcher / same-operator recorded on links but **not** required for a match.
- `inferred_bundle_net_usd` is inferred (union-find sum of original NETs); negatives retained; may be partial if a member NET is missing.

---

## 4. Non-impact confirmation

- Collectors / Base tracker / live ledger / production config: **untouched**
- Frozen Oct 8 winners file: **read-only**; sha unchanged
- Signing / broadcasting / AUTOEXEC / runtime autostart / live trading: **not involved**
- P2 and S1-B: **separate workstreams** — not advanced by this closeout

---

## 5. Closeout verdict

**CLOSED WITH DOCUMENTED LIMITATIONS**

Offline G1.6 deliverables, frozen-data before/after evidence, and unit tests are complete and re-verified. Remaining gaps are the unavailable `/workspace/g15` + `gcpipe` reproducibility sources and the intentionally unverified collector-parity / live-integration criteria listed in §3.
