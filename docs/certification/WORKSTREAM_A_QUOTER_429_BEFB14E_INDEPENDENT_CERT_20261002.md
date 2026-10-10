# Workstream A Quoter 429 (`befb14e`) — Independent Certification

- **Date (UTC):** 2026-10-02T13:03:00Z (initial thin-bundle); **self-contained re-run 2026-10-02T13:21:14Z**; **residual resolution 2026-10-02T14:08:42Z** (authoritative)
- **Host:** `vmi3410070`
- **Cert workspace:** `/home/raghu/projects/arbicore-x-cert` (dirty tree **preserved**; not cleaned/reset)
- **Throwaway inspect dirs:** thin-bundle era `/tmp/ws-a-unpack-try`, `/tmp/ws-a-pack-only`, `/tmp/ws-a-cert-throwaway`; **self-contained:** `/tmp/ws-a-selfcontained-cert-3539633` (+ parent archive `/tmp/ws-a-selfcontained-parent-8e63f25`); **residual:** `/tmp/ws-a-residual-cert-3664979/tip-checkout`
- **Auditor posture:** READ-ONLY vs Gate 9; no deploy; no Gate 9 restart/config/credentials; no production source modification; no GitHub push. Residual work used throwaway clone only (fixture-followup commit local to throwaway).
- **Authoritative artifact (this re-run):** `artifacts/workstream-a-quoter-429-befb14e-selfcontained.bundle`
- **Prior thin bundle (unchanged / superseded for verify):** `artifacts/workstream-a-quoter-429-befb14e.bundle`
- **Expected tip:** `befb14e6aa77515daa038e142ff978822a4fab91`
- **Fixture follow-up (throwaway only, not pushed):** `57f53651d8c7638d0a5f3d2cd8eb2c083fd97f44` on branch `cert/ws-a-fixture-cooldown-isolation`

---

## Authoritative final verdict (residual resolved): **PASS** (tip + fixture-followup) / product tip alone **READY WITH CONDITIONS**

| Criterion | Result |
|---|---|
| Self-contained bundle SHA256 / byte size | **PASS** — `b7f3952e…dff964`, **8199151** bytes |
| `git bundle verify` on empty bare (no external prereq) | **PASS** — “records a complete history” |
| Tip checkout / tree / `git show --stat` | **PASS** — tip `befb14e…`, tree `fdd6f799…` |
| Required base `93a20c9…` present + ancestor | **PASS** — object present; ancestor of tip |
| `_eth_call` 429 bound + cooldown + failover + fail-closed | **PASS** — inspected at tip |
| Fix path live_quote → quote_route → DEX → `_eth_call` | **PASS** |
| NEW RED→GREEN suite on real quote_route path | **PASS** — parent RED (5 POSTs); tip GREEN 5/5 |
| Prior `2b86cda` not overwritten (ancestry + file blob) | **PASS** — ancestor; `providers/rpc.py` blob identical tip vs `2b86cda` |
| Gate 9 untouched (before + after residual run) | **PASS** — StartedAt `2026-10-02T06:19:33Z`, RestartCount `0` |
| Pre-existing quoter regression suite hygiene | **PASS** after fixture-only follow-up `57f5365` — co-run scoped_throttle **11/11**; tip alone still **10/11** (fixture debt, not product bug) — see §13 |

**Residual resolution (exact):** Co-run failure of `test_eth_call_surfaces_error_for_failover` is a **test-fixture / module-level cooldown registry leak**, not a product bug in tip `befb14e`. Prior same-host 429 tests populate `_RPC_HOST_COOLDOWN_UNTIL['h.example']`; autouse fixture reset only `_RPC_LOCKS` / `_RPC_LAST_TS`. Minimal fixture clear restores **11/11**. Full relevant suite after follow-up: amp (5) + scoped_throttle (11) + base_failover + rpc_reliability = **33/33 PASS**. Amplification RED→GREEN remains valid on tip alone.

**Deploy recommendation:** **READY WITH CONDITIONS** — see §13.6. Gate9 campaign **must remain untouched**.

**Historical thin-bundle verdict (superseded for certification of tip trees):** **BLOCKED** — see §1–§11 below (prerequisite `93a20c9…` missing from thin pack). Thin bundle SHA256 `12780813…a6d2` / 45892 bytes left **unchanged**.

**Historical self-contained §12 verdict (superseded by §13):** **CONDITIONAL** on scoped-throttle fixture hygiene.

---

## 0. Cert workspace safety (preserved)

`git status --short` / `git diff --stat` at start (not cleaned):

**Modified (tracked):**
- `app/backend/arbicore/execution/quoter.py` (+/− vs HEAD; **local uncommitted cert material — NOT treated as tip `befb14e`**)
- `app/backend/tests/test_quoter_scoped_throttle.py`
- `docs/certification/M6_POST_ALCHEMY_RESET_SHADOW_20261002.md`
- `reports/shadow_validation/m6_post_alchemy_reset_latest.json`
- `reports/shadow_validation/post_alchemy_reset_probe.json`

**Untracked:** numerous certification docs/reports, phase bundles, `artifacts/workstream-a-quoter-429-befb14e.bundle`, etc.

Cert HEAD remains `9b196cde0c975d0efe94e94f49de05b4244bdbc6` (**≠** prerequisite `93a20c9…`). Production `/home/raghu/projects/arbicore-x-v2` was not modified and also lacks `93a20c9…`.

---

## 1. Transfer verification

| Check | Expected | Observed | Result |
|---|---|---|---|
| Path | artifacts bundle | `/home/raghu/projects/arbicore-x-cert/artifacts/workstream-a-quoter-429-befb14e.bundle` | PASS |
| Size (bytes) | 45,892 | **45892** (`stat` / `wc -c`) | PASS |
| SHA256 (case-insensitive) | `12780813f62a67d663a6c58ff0e91719854b0de2ab9935d651fd9a8436a1a6d2` | **`12780813f62a67d663a6c58ff0e91719854b0de2ab9935d651fd9a8436a1a6d2`** | PASS |

`git bundle list-heads`:

```
befb14e6aa77515daa038e142ff978822a4fab91 refs/heads/engineering/gate9-parallel-93a20c9
```

Bundle text header (prerequisite line only; read from bundle text before `PACK`):

```
-93a20c9222e095bac8c6eae93f161927f7192ae9
```

(`git bundle verify` against this bundle: **FAIL** — missing prerequisite; see §3.)

---

## 2. Prerequisite recovery attempt (failed)

### Required object
`93a20c9222e095bac8c6eae93f161927f7192ae9`

### Searched (non-destructive; exhaustive pass finalized 2026-10-02T13:06:00Z)

**Commands (representative):**

```bash
PREREQ=93a20c9222e095bac8c6eae93f161927f7192ae9
git cat-file -t "$PREREQ"   # per repo
git bundle list-heads <path>   # every .bundle found
git bundle verify <path>       # cert repo + throwaway clones
git fetch origin "$PREREQ"     # read-only; cert + v2
python3 -c "urllib.request.urlopen('https://api.github.com/repos/raghugr2013-lgtm/arbicore-x/commits/'+'$PREREQ')"
find /home/raghu/projects -maxdepth 5 -type d -name .git
find /tmp -maxdepth 3 -type d -name .git
```

| Source | Result |
|---|---|
| `/home/raghu/projects/arbicore-x-cert` (`HEAD=9b196cde…`) | `git cat-file -t` → **missing** |
| `/home/raghu/projects/arbicore-x-v2` | **missing** |
| All other `.git` under `/home/raghu/projects` (14 repos): `arbicore-x-vps-cert`, `arbicore-x-backup-v1.0.1`, `arbicore-p0-validation-20260930`, `arbicore-p1b-validation-20260930`, `arbicore-x-legacy`, `arbicorex-v2/source`, `arbicore-generic-dex-validation-20260930`, `arbicore-x-vps-bundle`, `arbicore-p1-validation-20260930`, `arbicore-triangular-validation-20260930`, `strategy-factory-canonical`, `arbicore-x-h05-validation` | **missing** (tip `befb14e` also **missing** everywhere except throwaway unpack below) |
| Temp cert clones `/tmp/arbicore-ws-a-befb14e-cert`, `/tmp/ws-a-unpack-try`, `/tmp/ws-a-pack-only` (+ phase-a/b cert dirs) | Prereq **missing**; unpack dirs hold **tip commit object** only after prior `unpack-objects`, not full verify |
| Reflog grep `93a20c9` / `befb14e` / `gate9-parallel` in cert + v2 | **no matches** |
| `git ls-remote origin` (cert + v2) grep gate9 / SHAs | **no matching refs** |
| `git fetch origin 93a20c9222e095bac8c6eae93f161927f7192ae9` (cert + v2, read-only) | **`fatal: remote error: upload-pack: not our ref`** |
| GitHub REST (read-only, this finalization pass) | **`93a20c9…` → HTTP 422**; **`befb14e…` → HTTP 422**; **`2b86cda…` → HTTP 422** |
| `.bundle` files on host (`find /home/raghu/projects -name '*.bundle'`) | **9 files** — see table below |

**Every bundle: `list-heads` / prerequisite line / `verify` (cert repo unless noted):**

| Bundle path | list-heads tip | Declared prerequisite | Contains `93a20c9`? | `bundle verify` |
|---|---|---|---|---|
| `artifacts/workstream-a-quoter-429-befb14e.bundle` | `befb14e…` `refs/heads/engineering/gate9-parallel-93a20c9` | `93a20c9…` | **No** (requires external base) | **FAIL** |
| `artifacts/phase-a-h05-cc3a922.bundle` | `cc3a922…` | `5bd9525…` | No | OK (needs `5bd9525…` in repo) |
| `phase-a-h05-cc3a922.bundle` | same | `5bd9525…` | No | OK |
| `phase-a-h05-range-cc3a922-to-8fbe5995.bundle` | `8fbe5995…` | `cc3a922…` | No | OK |
| `phase-b-h06-7f45ec2.bundle` | `7f45ec2…` | `8fbe5995…` | No | OK |
| `phase-b-h06-remediation-only-7c2b1bc.bundle` | `7c2b1bc…` | `7f45ec2…` | No | OK |
| `arbicorex-v2/source/arbicore-x-v1.0.1.bundle` | `main` @ `20bad020…` | *(none)* | No | OK |
| `arbicorex-v2/source/arbicore-x-v1.0.2.bundle` | `main` @ `0789e6a2…` | *(none)* | No | OK |

**Filename / doc grep:** only `artifacts/workstream-a-quoter-429-befb14e.bundle` and this cert doc reference the Workstream A delivery path; no separate base bundle containing `93a20c9…` on disk.

**Conclusion:** Prerequisite **`93a20c9222e095bac8c6eae93f161927f7192ae9` cannot be recovered** from any local object database, any bundle payload on this host, or read-only remote/GitHub lookup. **No commit was fabricated, recreated, or substituted** (hard ban complied). Independent certification of tip implementation/tests remains **BLOCKED** because the bundle-required base cannot be independently verified.

---

## 3. `git bundle verify`

Against cert checkout and against throwaway bare clone `/tmp/ws-a-cert-throwaway`:

```
error: Repository lacks these prerequisite commits:
error: 93a20c9222e095bac8c6eae93f161927f7192ae9
```

**Result: FAIL** (matches operator note).

---

## 4. Partial pack inspection (non-authoritative; does not unblock)

`git index-pack` on the embedded pack reported **20 unresolved deltas** (thin pack vs missing base).

`git unpack-objects -r` recovered **15 undeltified loose objects** into `/tmp/ws-a-unpack-try` (throwaway). Tip **tree** `fdd6f7996a4364885fca31d394eeae75d04b379a` remains **absent**.

### 4.1 Tip / parent / ancestry (from recovered **commit** objects only)

| Role | Full SHA | Notes |
|---|---|---|
| Tip | `befb14e6aa77515daa038e142ff978822a4fab91` | Subject: `fix(quoter): bound HTTP-429 retries + per-host cooldown in execution/quoter.py::_eth_call` |
| Parent of tip | `8e63f252b599ea97b9f563162ba8c1836a1c9e28` | Combined Gate9 parallel workstream summary commit |
| Docs tip | `5a143a8667484cd9e4a765d55079265936925695` | Workstream B/C/D audits |
| Provider hardening | `2b86cdab115223d69a48aeefd4d434dd094eee1e` | `fix(rpc): bound HTTP-429 retries + host cooldown…` (EthJsonRpcProvider path) |
| Tooling | `f0962490c10191ac74677fd0efc60b31df9c4b18` | ESLint ignore globs |
| Required base | `93a20c9222e095bac8c6eae93f161927f7192ae9` | **ABSENT** (parent of `f096249`) |

Recovered parent walk:

```
befb14e6aa77 → 8e63f252b599 → 5a143a866748 → 2b86cdab1152 → f0962490c101 → 93a20c9222e0 (MISSING)
```

`git merge-base --is-ancestor 2b86cdab115223d69a48aeefd4d434dd094eee1e befb14e6aa77515daa038e142ff978822a4fab91` → **exit 0** (commit-graph: `2b86cda` is an ancestor of tip).

### 4.2 `git show --stat` / changed files vs parent

**BLOCKED.** Commands fail with:

```
fatal: unable to read tree e603c56f71633c68cfc7630d76526336cc7e3442
```

(and tip tree `fdd6f799…` absent). No authoritative changed-file list vs parent/base from tip.

### 4.3 Claimed tip behaviour (commit message only — not code proof)

Tip message claims a minimal change **inside** `execution/quoter.py::_eth_call`:

- Path: `live_quote_provider` → `QuoterRegistry.quote_route()` → DEX → `_eth_call`
- Distinct from `providers/rpc.py::EthJsonRpcProvider` (`2b86cda`, claimed left intact)
- `ARBICORE_RPC_MAX_RETRIES_429` (default 1) → `eff_429 = min(retries, 1)` → max **≤2 POSTs** on 429 (vs prior **5**)
- Per-host cooldown `ARBICORE_RPC_RATE_LIMIT_COOLDOWN_S` (default 60s); entry gate fails fast (no POST) to prompt failover
- Fail-closed / no false `ok` quote; economic gates preserved

**Independent code confirmation of those claims at tip SHA: NOT DONE** — no tip `quoter.py` blob/`def _eth_call` recovered.

### 4.4 Recovered undeltified test blob (orphan evidence)

Loose blob `f9cfcddb35d78889058f289ddbec8f34cea78dbf` (174 lines) is the claimed new suite body for `tests/test_quoter_eth_call_429_amplification.py`. It **names** the real path and asserts:

| Test | Intent (from recovered blob text) |
|---|---|
| `test_quote_route_single_candidate_429_is_bounded` | `quote_route` → fail-closed `fallback:break_even`; Alchemy POSTs **≤ 2** |
| `test_quote_route_429_sets_host_cooldown` | second quote does **not** re-POST cooling host |
| `test_quote_route_fails_over_to_healthy_alternate` | status `ok` from alternate; Alchemy ≤2; healthy 1 POST |
| `test_quote_route_all_rate_limited_fails_closed` | `fallback:break_even`, never `ok`; both hosts ≤2 |
| `test_quote_route_healthy_single_post` | healthy path 1 POST |

Also recovered (provider-path / prior Workstream A) blob `7d78955c…` — tests `EthJsonRpcProvider` (provider-level). Per charter: **provider-level tests alone are not accepted** as proof of the quoter amplification fix.

**Cannot bind either blob to tip tree path** without tip tree → cannot treat as certified tip content; **tests were not executed**.

---

## 5. Tests (critical) — not reproduced

| Item | Status |
|---|---|
| Tip working tree checkout | **BLOCKED** |
| Run `test_quoter_eth_call_429_amplification.py` against tip | **NOT RUN** |
| Original amplification (5 POSTs) RED on tip parent | **NOT MEASURED** |
| Max HTTP POST attempts / 429 retry / cooldown / alternate / all-fail | **NOT MEASURED on tip** |
| Existing quoter/RPC regression suite | **NOT RUN** (would require tip or certified base + tip delta) |
| Gate 9 container used for tests? | **No** (forbidden) |

Dirty-tree local edits under cert (`quoter.py` / `test_quoter_scoped_throttle.py`) were **explicitly excluded** as tip evidence.

---

## 6. Amplification root-cause linkage (reference only)

Prior host audit `docs/certification/BASE_ALCHEMY_429_ROOT_CAUSE_20261002.md` classifies the live Gate9 issue as a **RETRY/FAILOVER BUG** on the **QuoterRegistry** path: after public Base `-32016` failover, Alchemy receives ≈ `_RPC_MAX_RETRIES + 1` POSTs (**~5**) with **no host cooldown**, independent of ProviderRegistry trip state.

Tip **commit message** and recovered quoter-path **test blob** are *aligned in intent* with that root cause (bound 429 at `_eth_call`, cooldown, failover, fail-closed). **Linkage is not certified as implemented** because tip `_eth_call` source and GREEN test execution against tip are unavailable.

---

## 7. Prior `2b86cda` ProviderRegistry / EthJsonRpcProvider hardening

| Question | Evidence |
|---|---|
| Is `2b86cda` object present after pack unpack? | **Yes** (commit `2b86cdab115223d69a48aeefd4d434dd094eee1e`) in throwaway unpack only |
| Is it an ancestor of tip `befb14e`? | **Yes** (parent walk + `merge-base --is-ancestor`) |
| Was tip tree inspected to prove EthJsonRpcProvider hardening not reverted? | **No** — tip tree missing |
| Can overwrite/silent revert be ruled out at file level? | **BLOCKED** |

---

## 8. Gate 9 safety (before + after; unchanged)

Container: `arbicore-x-backend-new`

| Field | Required | Observed before | Observed after |
|---|---|---|---|
| StartedAt | `2026-10-02T06:19:33Z` | `2026-10-02T06:19:33.513948555Z` | `2026-10-02T06:19:33.513948555Z` |
| RestartCount | `0` | `0` | `0` |
| Image | `g5.79-green-20260927` | `arbicore-x-backend:g5.79-green-20260927` | same |
| SHADOW | enabled | `ARBICORE_EXECUTION_MODE=SHADOW`, `ARBICORE_SHADOW_CERT_ENABLED=true` | same |
| AUTOEXEC / RUNTIME | disabled | `ARBICORE_AUTOEXEC_AUTOSTART=false`, `ARBICORE_RUNTIME_AUTOSTART=false` | same |

No deploy, no container restart, no env/credential changes, no production edits, no push.

---

## 9. What would unblock full certification

1. Transfer a **real Git object source** for `93a20c9222e095bac8c6eae93f161927f7192ae9` (full base bundle, or push that commit to a fetchable remote), **or** re-export Workstream A as a **self-contained** bundle that includes enough history to resolve tip trees without an external prereq.
2. Independently: `git bundle verify` → throwaway clone of tip → `git show --stat` + changed-file list → inspect tip `_eth_call` → run `test_quoter_eth_call_429_amplification.py` (+ quoter/RPC regressions) in throwaway docker/venv (**not** Gate 9) → re-check Gate 9 StartedAt/RestartCount.
3. Optionally transfer prior `workstream-a-base-failover-2b86cda.bundle` if file-level continuity of provider hardening must be certified beyond commit-graph ancestry.

---

## 10. Hard bans compliance

- Did **not** deploy/activate bundle on Gate 9 or production
- Did **not** restart containers / change env / credentials
- Did **not** modify `/home/raghu/projects/arbicore-x-v2`
- Did **not** discard cert workspace dirty state
- Did **not** push to GitHub
- Did **not** fabricate missing commits
- Did **not** sign/broadcast/enable AUTOEXEC/RUNTIME/live-execute
- Did **not** modify the delivered bundle at `artifacts/workstream-a-quoter-429-befb14e.bundle` (SHA256/size unchanged on finalization pass)

---

## 11. Finalization summary (thin-bundle era — historical only)

| Dimension | Outcome |
|---|---|
| **Verdict** | **BLOCKED** — thin-bundle integrity OK; **ancestry/base + tip tree + code/tests cannot be independently certified** from that artifact |
| **Blocking reason (exact)** | Thin bundle declares prerequisite `93a20c9222e095bac8c6eae93f161927f7192ae9`; object **absent** everywhere searched; `git bundle verify` fails; tip tree `fdd6f799…` unreadable → no `_eth_call` inspection or RED→GREEN test execution on tip |
| **What was verified without full verify** | SHA256 `12780813f62a67d663a6c58ff0e91719854b0de2ab9935d651fd9a8436a1a6d2`, size **45892**, `list-heads` → `befb14e6aa77515daa038e142ff978822a4fab91`, commit-graph from recovered commits in `/tmp/ws-a-unpack-try` only, Gate 9 container unchanged |
| **Gate 9 (re-checked finalization)** | `StartedAt=2026-10-02T06:19:33.513948555Z`, `RestartCount=0`, `Image=arbicore-x-backend:g5.79-green-20260927` |
| **No fabrication statement** | **Confirmed:** missing prerequisite was not synthesized from deltas, cherry-picks, or local dirty-tree edits; cert workspace local `quoter.py` changes are **not** tip evidence |

> **Superseded for tip certification** by §12 (self-contained bundle re-run). Thin bundle file left unchanged on disk.

---

## 12. Self-contained bundle re-run (authoritative) — 2026-10-02T13:21:14Z

### 12.0 Scope / bans

- Artifact: `/home/raghu/projects/arbicore-x-cert/artifacts/workstream-a-quoter-429-befb14e-selfcontained.bundle`
- Throwaway only: `/tmp/ws-a-selfcontained-cert-3539633/{bare.git,checkout}` ; parent RED tree `/tmp/ws-a-selfcontained-parent-8e63f25`
- Tests: throwaway `docker run --rm --network none` with image `arbicore-x-backend:g5.79-green-20260927` mounting tip/parent trees RO — **not** Gate9 container `arbicore-x-backend-new`
- Did **not** modify implementation, Gate9, production `/home/raghu/projects/arbicore-x-v2`, credentials/config, deploy, push, or discard cert dirty tree
- Prior thin bundle left unchanged (SHA256 still `12780813f62a67d663a6c58ff0e91719854b0de2ab9935d651fd9a8436a1a6d2`)

### 12.1 Transfer / integrity

| Check | Expected | Observed | Result |
|---|---|---|---|
| Path | self-contained artifacts bundle | `…/workstream-a-quoter-429-befb14e-selfcontained.bundle` | PASS |
| Size (bytes) | (operator) | **8199151** | PASS |
| SHA256 | `b7f3952e29a5664bb6c7a144e7a76c9df7ba207b3f2ee6a430bb84a3a4dff964` | **`b7f3952e29a5664bb6c7a144e7a76c9df7ba207b3f2ee6a430bb84a3a4dff964`** | PASS |

`git bundle list-heads`:

```
befb14e6aa77515daa038e142ff978822a4fab91 refs/heads/xfer/workstream-a-befb14e
```

Bundle text header (before `PACK`): `# v2 git bundle` + tip ref only — **no** `-93a20c9…` prerequisite line.

### 12.2 `git bundle verify` / import (empty bare — proves self-contained)

Against empty bare `/tmp/ws-a-selfcontained-cert-3539633/bare.git`:

```
…selfcontained.bundle is okay
The bundle contains this ref:
befb14e6aa77515daa038e142ff978822a4fab91 refs/heads/xfer/workstream-a-befb14e
The bundle records a complete history.
```

`git fetch` into bare → checkout tip in throwaway worktree → **PASS**.

### 12.3 Tip / parent / base / ancestry / changed files

| Role | Full SHA |
|---|---|
| Tip | `befb14e6aa77515daa038e142ff978822a4fab91` |
| Tip tree | `fdd6f7996a4364885fca31d394eeae75d04b379a` |
| Parent | `8e63f252b599ea97b9f563162ba8c1836a1c9e28` |
| Required base | `93a20c9222e095bac8c6eae93f161927f7192ae9` (**present**; `merge-base --is-ancestor` → YES) |
| Provider hardening | `2b86cdab115223d69a48aeefd4d434dd094eee1e` (ancestor YES) |

Ancestry `93a20c9..befb14e`:

```
befb14e fix(quoter): bound HTTP-429 retries + per-host cooldown in execution/quoter.py::_eth_call
8e63f25 ## Gate 9 parallel workstream — A complete …
5a143a8 docs(audit): Workstream B/C/D delta plans …
2b86cda fix(rpc): bound HTTP-429 retries + host cooldown … (EthJsonRpcProvider)
f096249 chore(tooling): make root ESLint ignore globs location-independent
```

`git show --stat befb14e` — **2 files**:

| Status | Path |
|---|---|
| M | `app/backend/arbicore/execution/quoter.py` (+52/−11; 63-line net edit region) |
| A | `app/backend/tests/test_quoter_eth_call_429_amplification.py` (+174) |

### 12.4 `_eth_call` behaviour (tip source)

Defaults inspected in tip `execution/quoter.py`:

| Parameter | Default | Effect |
|---|---|---|
| `_RPC_MAX_RETRIES` | **4** (unchanged general budget) | non-429 retries |
| `_RPC_MAX_RETRIES_429` | **1** (`ARBICORE_RPC_MAX_RETRIES_429`) | `eff_429 = min(retries, 1)` → max **≤2** HTTP POSTs on 429 |
| `_RPC_RATE_LIMIT_COOLDOWN_S` | **60** | per-host cooldown after 429 |
| Cooldown gate | `_RPC_HOST_COOLDOWN_UNTIL[host]` | fail-fast **NO POST**; returns `-32016` / “HTTP 429 host cooldown…” so `quote_route` can failover |
| Fail-closed | yes | returns `error_dict`; never fabricates quote result |
| Economic / `quote_route` / `quote_route_strict` | **unchanged** in tip diff | gates preserved |

Parent (`8e63f25`) `_eth_call`: full `retries+1` loop on 429 with **no** independent 429 budget and **no** cooldown → single-candidate amplification **5 POSTs** (measured).

### 12.5 Fix path certification

```
live_quote_provider.make_live_quote_provider
  → quoter_registry.quote_route(chain=…, hops=…)   # scanners/…/live_quote_provider.py ~281, ~453
    → QuoterRegistry.quote_route                      # execution/quoter.py
      → backend.quote_hop (e.g. UniV3QuoterV2)        # calls _eth_call at ~602
        → execution/quoter.py::_eth_call              # direct httpx; DISTINCT from providers/rpc.py
```

Tests drive **real** `QuoterRegistry.quote_route` → `UniV3QuoterV2.quote_hop` → `_eth_call` with POST-counting fake `_post_json`. Provider-only unit tests are **not** used as sole proof.

### 12.6 RED→GREEN + regressions (throwaway docker)

Image: `arbicore-x-backend:g5.79-green-20260927`; `PYTHONPATH=/work`; `pytest -o addopts=` (disable ini xdist) and/or default xdist as noted.

| Suite | Tree | Result | Evidence |
|---|---|---|---|
| `test_quoter_eth_call_429_amplification.py` (5) | tip `befb14e` | **5 passed** | GREEN |
| Same suite overlaid on parent `8e63f25` | parent + tip test file | **3 failed, 2 passed** | RED: single-candidate **5 POSTs** (`assert 5 <= 2`); cooldown re-POST **10==5**; all-rate-limited last host **5 POSTs**; failover+healthy still pass (non-final `mr=1` already ≤2) |
| `test_base_failover_429_amplification.py` + `test_rpc_reliability.py` | tip | **17 passed** | provider-path / rpc regressions OK |
| `test_quoter_scoped_throttle.py` | tip alone / combined | **10 passed, 1 failed** | `test_eth_call_surfaces_error_for_failover` sees cooldown after prior same-host 429 tests; fixture resets locks/ts only |
| Same isolated single test | tip | **1 passed** | behaviour OK when cooldown clear |
| `test_quoter_scoped_throttle.py` | parent `8e63f25` | **11 passed** | proves tip-introduced global cooldown coupling |

**Measured amplification behaviour:**

| Scenario | Parent (pre-fix) | Tip (fix) |
|---|---|---|
| Single candidate persistent 429 | **5** POSTs | **≤2** POSTs |
| Max 429 retries (`_RPC_MAX_RETRIES_429`) | n/a (used full 4) | **1** → attempts `eff_429+1` ≤ **2** |
| Cooldown | none | **60s**; second quote **0** additional POSTs to cooling host |
| Alternate healthy | works (Alchemy still ≤2 as non-final) | `status=ok` from alternate; Alchemy ≤2 |
| All providers 429 | break_even but last host **5** POSTs | `fallback:break_even`, never `ok`; each host ≤2 |

### 12.7 Prior `2b86cda` continuity

- Ancestor of tip: **YES**
- Commits after `2b86cda` touching `app/backend/arbicore/providers/rpc.py`: **none**
- Blob equality tip vs `2b86cda` for `providers/rpc.py`: **`28c167a8a00106993a95f66c30012fea216e8287`** both sides — **not overwritten / not silently reverted**

### 12.8 Link to observed Base/Alchemy HTTP-429 amplification

- `docs/certification/BASE_ALCHEMY_429_ROOT_CAUSE_20261002.md` — classifies live Gate9 as **RETRY/FAILOVER BUG** on QuoterRegistry path; Alchemy POSTs/failover ≈ **5.025** ≈ `_RPC_MAX_RETRIES+1`
- Supporting: `ALCHEMY_CU_OBSERVATION_20261002.md`, `BASE_FAILOVER_FIX_VALIDATION_PROCEDURE_20261002.md`, `GATE9_PARALLEL_WORKSTREAM_INDEPENDENT_CERT_20261002.md`

Tip `_eth_call` bound+cooldown directly addresses that measured multiplier on the **quoter** path (not only ProviderRegistry).

### 12.9 Gate 9 safety (before + after this re-run)

Container: `arbicore-x-backend-new`

| Field | Required | Before | After (2026-10-02T13:21:14Z) |
|---|---|---|---|
| StartedAt | `2026-10-02T06:19:33Z` | `2026-10-02T06:19:33.513948555Z` | **same** |
| RestartCount | `0` | `0` | **0** |
| Image | `g5.79-green-20260927` | `arbicore-x-backend:g5.79-green-20260927` | **same** |
| SHADOW | on | `ARBICORE_EXECUTION_MODE=SHADOW`, `ARBICORE_SHADOW_CERT_ENABLED=true` | **same** |
| AUTOEXEC / RUNTIME | off | both `*_AUTOSTART=false` | **same** |

### 12.10 Self-contained re-run verdict

**CONDITIONAL** — tip artifact is self-contained, tip trees resolvable, `_eth_call` fix matches the proven amplification path, RED→GREEN suite proves 5→≤2 POSTs with cooldown/failover/fail-closed, `2b86cda` intact, Gate9 untouched. Residual condition: pre-existing `test_quoter_scoped_throttle.py` needs cooldown reset in its autouse fixture (not part of tip diff; auditor did not patch). Unblocking to full **PASS** would be a follow-on test-hygiene commit (out of scope for this certify-only run).

---

## 13. Residual resolution — scoped-throttle co-run cooldown leak (2026-10-02T14:08:42Z)

### 13.1 Scope / safety

| Constraint | Observed |
|---|---|
| Cert workspace dirty tree | **preserved** (no reset/clean); local dirty `quoter.py` / scoped_throttle edits **not** used as tip evidence |
| Worktree | throwaway clone from self-contained bundle → `/tmp/ws-a-residual-cert-3664979/tip-checkout` @ `befb14e` |
| Gate9 | **untouched** — StartedAt `2026-10-02T06:19:33.513948555Z`, RestartCount `0`, image `g5.79-green-20260927` (before + after) |
| Production / credentials / config / push | **none** |

Bundle re-check: SHA256 `b7f3952e29a5664bb6c7a144e7a76c9df7ba207b3f2ee6a430bb84a3a4dff964` (matches §12.1).

### 13.2 Independent reproduction (tip `befb14e` alone)

Image: `arbicore-x-backend:g5.79-green-20260927`; `PYTHONPATH=/work`; `pytest -o addopts=`.

| Run | Result |
|---|---|
| `tests/test_quoter_scoped_throttle.py` (full file) | **10 passed, 1 failed** |
| Failure | `test_eth_call_surfaces_error_for_failover` — got `{'code': -32016, 'message': 'HTTP 429 host cooldown (recent rate limit)'}` instead of `message == "boom"` |
| Same test isolated | **1 passed** |

### 13.3 Root cause proof (fixture leak, not product bug)

1. Tip `_eth_call` sets process-global `_RPC_HOST_COOLDOWN_UNTIL[host]` on HTTP 429 (default 60s).
2. Pre-existing tests `test_eth_call_retries_then_succeeds` and `test_eth_call_fail_closed_on_persistent_429` exercise 429 against shared URL `https://h.example/rpc` → host key `h.example`.
3. Autouse `_reset_throttle_state` on tip only resets `_RPC_LOCKS` and `_RPC_LAST_TS` — **does not** clear `_RPC_HOST_COOLDOWN_UNTIL`.
4. Later `test_eth_call_surfaces_error_for_failover` uses the same host; cooldown gate fails fast with **no POST**, so the faked `"boom"` JSON-RPC error is never observed.

Direct script proof (throwaway, tip product module):

```
after_429_err= {'code': -32016, 'message': 'HTTP 429 rate limited'}
cooldown_dict= {'h.example': <future timestamp>}
without_clear_err= {'code': -32016, 'message': 'HTTP 429 host cooldown (recent rate limit)'}
after_clear_err= {'code': -32000, 'message': 'boom'}
ROOT_CAUSE=fixture_module_cooldown_registry_leak
PRODUCT_BUG=no
```

Parent `8e63f25` had no `_RPC_HOST_COOLDOWN_UNTIL` → scoped_throttle **11/11** there; tip introduces the global that pre-existing fixture does not reset. Amp suite already clears cooldown in `_install` (`monkeypatch.setattr(Q, "_RPC_HOST_COOLDOWN_UNTIL", {})`) — consistent with fixture-only debt.

**Conclusion:** certified tip does **not** need a product fix for this residual; only test isolation / fixture hygiene.

### 13.4 Fixture-only follow-up (throwaway branch)

Branch: `cert/ws-a-fixture-cooldown-isolation` (local throwaway; **not pushed**; **not** applied to Gate9 / production / cert dirty tree product files).

Commit: `57f53651d8c7638d0a5f3d2cd8eb2c083fd97f44`

Diff (3 lines in autouse fixture only):

```python
monkeypatch.setattr(q, "_RPC_HOST_COOLDOWN_UNTIL", {}, raising=False)
```

No changes to `execution/quoter.py`.

### 13.5 Re-validation after fixture follow-up

| Suite | Result |
|---|---|
| `test_quoter_eth_call_429_amplification.py` + `test_quoter_scoped_throttle.py` | **16/16 PASS** (amp 5/5 + scoped 11/11) |
| + `test_base_failover_429_amplification.py` + `test_rpc_reliability.py` | **33/33 PASS** |
| Tip `befb14e` alone (no fixture patch) scoped_throttle | remains **10/11** co-run (documented debt) |

### 13.6 Updated verdict and deploy recommendation

| Scope | Cert verdict | Deploy recommendation |
|---|---|---|
| Product tip `befb14e` alone (amplification fix) | Product behaviour **PASS**; suite hygiene still **CONDITIONAL** if merge-gated on tip-as-shipped scoped_throttle co-run | **READY WITH CONDITIONS** — safe to deploy the quoter `_eth_call` 429 bound+cooldown for the measured amplification bug; land fixture follow-up `57f5365` (or equivalent) before treating scoped_throttle co-run as a hard merge gate |
| Tip `befb14e` + fixture follow-up `57f5365` | **PASS** (product + relevant suites 33/33) | **READY** for that combined tree — still **do not** restart/deploy into the frozen Gate9 campaign without a separate campaign decision |

**Explicit Gate9 posture:** campaign remains **untouched / NOT READY to modify** in this certification run (no restart, no image swap, no config/credential change).

**Authoritative summary line:** Residual **CONDITIONAL** from §12 is **resolved as fixture-only**. Full independent cert **PASS** applies to **tip + fixture-followup**. Deploy of original `befb14e` product content alone is **READY WITH CONDITIONS** (include fixture hygiene for CI; keep Gate9 frozen until campaign owner authorizes).
