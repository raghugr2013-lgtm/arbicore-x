# Base→Alchemy Failover Fix — Controlled Validation Procedure

- **Date:** 2026-10-02
- **Status:** PROCEDURE ONLY — **no deploy**, **no Gate9 touch**
- **Root cause:** `docs/certification/BASE_ALCHEMY_429_ROOT_CAUSE_20261002.md`  
  Classification: **RETRY/FAILOVER BUG** (~5 Alchemy POSTs / failover on production image)
- **Proposed fix (workspace, undeployed):** `app/backend/arbicore/execution/quoter.py`  
  - `max_retries=1` on **every** failover candidate (incl. last) via `_RPC_FAILOVER_CANDIDATE_RETRIES`  
  - **60s** HTTP-429 host cooldown via `_RPC_HTTP_429_COOLDOWN_S`
- **Alchemy identity:** wired fp **`5e5d5bb1`**; dashboard **UNVERIFIABLE**
- **Optional harness:** `scripts/measure_base_failover_logs.py` (read-only log parse; **refuses** Gate9 container name)

---

## HARD RULES (non-negotiable)

1. **Do NOT** run this procedure against the live Gate 9 campaign container `arbicore-x-backend-new`.
2. **Do NOT** restart, recreate, reconfigure, re-key, or hot-patch Gate 9.
3. **Do NOT** alter the SHADOW campaign (mode, AUTOEXEC, signing, broadcast, Gate7/8/H05).
4. Freeze Gate 9 for the duration of this A/B: observe-only if needed; never instrument it as the treatment or baseline host.
5. Baseline and treatment run on an **isolated throwaway container** or **second stack** only.
6. Never print Alchemy key path segments; redact to host + optional fp8 only.
7. Stop after measurement + comparison table. Deploy decision is a **separate** operator step after PASS.

---

## Gate 9 pre-flight confirmation (read-only; optional)

Before starting isolated work, confirm Gate 9 is still the frozen campaign image:

| Check | Expected (campaign freeze) |
|---|---|
| Name | `arbicore-x-backend-new` |
| Image | `arbicore-x-backend:g5.79-green-20260927` (or campaign-frozen tag) |
| RestartCount | unchanged vs campaign start |
| StartedAt | unchanged |
| Running `quote_route` | still `mr = None if ci == n - 1 else 1` (**OLD_FULL_BUDGET**) |
| Cooldown symbols | **absent** in running image |

**2026-10-02 procedure-author inspect (read-only):** RestartCount=0; StartedAt=`2026-10-02T06:19:33.513948555Z`; image tag above; running quoter still OLD_FULL_BUDGET. **Gate9 untouched by this procedure authoring.**

---

## 1. Preconditions

| # | Precondition | Notes |
|---|---|---|
| P1 | Gate 9 campaign **complete** or **explicitly frozen** | Do not wait on this procedure inside the live campaign window if it risks operator pressure to patch Gate9 |
| P2 | Gate9 container **frozen** | No restart / config / key / SHADOW change |
| P3 | Workspace fix present + unit tests green | `tests/test_quoter_scoped_throttle.py` (cooldown + bound-retry cases) |
| P4 | Isolated host available | Throwaway `docker run` **or** second compose stack — **not** `arbicore-x-backend-new` |
| P5 | Same image tag for **baseline** | Prefer exact Gate9 tag: `arbicore-x-backend:g5.79-green-20260927` |
| P6 | Patched image/binary for **treatment** | Build from workspace `quoter.py` only; same config shape as Gate9 RPC ordering |
| P7 | Comparable RPC topology | Candidates: `mainnet.base.org` → `base-mainnet.g.alchemy.com` (fp `5e5d5bb1` or dedicated throwaway Alchemy key — never log path) |
| P8 | Safety posture on isolated stack | SHADOW ON; AUTOEXEC OFF; signing=0; broadcast=0; fail-closed Gate7/8/H05 **honest** |
| P9 | Log level | httpx INFO (or equivalent) so `HTTP Request: POST … "HTTP/1.1 NNN …"` lines are present |
| P10 | Measurement tool ready | Optional: `scripts/measure_base_failover_logs.py` pointed at **isolated** log capture only |

### Forbidden targets

```
arbicore-x-backend-new     ← live Gate 9 — NEVER
any container sharing Gate9 network namespaces / volumes for “convenience”
hot-mount of patched quoter.py into Gate9
```

---

## 2. Experimental design (A/B)

### Arms

| Arm | Image / code | Expected Alchemy POSTs / Base→Alchemy failover |
|---|---|---|
| **Baseline (B)** | Gate9-equivalent tag (`g5.79-green-20260927`) | ~**5** (`_RPC_MAX_RETRIES+1`) |
| **Treatment (T)** | Workspace-patched quoter (`mr=1` all candidates + 60s HTTP-429 cooldown) | ≤**2** before cooldown; **0** further POSTs to that host while cooldown armed |

### Run order

1. Start **baseline** isolated container → capture window W_B (see §4).
2. Stop baseline container (do not touch Gate9).
3. Start **treatment** isolated container with **same** env shape / load profile → capture window W_T.
4. Prefer sequential same-host windows under similar wall-clock / load; if parallel, use **separate** Alchemy apps/keys so CU/429 contention does not cross-contaminate (still never print keys).

### Load profile (keep comparable)

- Same scanner / quoter duty cycle as intended post-Gate9 validation (SHADOW quoting on Base).
- Same primary/secondary RPC order.
- Do **not** artificially spam Alchemy outside the app path; the bug is the in-app failover amplifier.
- Optional: if public Base soft-RL (`-32016`) is rare in the window, extend duration rather than injecting synthetic load into Gate9 or production keys carelessly.

---

## 3. Metrics to record (BOTH arms)

Record every row for baseline **and** treatment over the comparable window, then normalize to **per hour** where noted.

| ID | Metric | Unit | How derived |
|---|---|---|---|
| M1 | Base failover events / hour | events/h | Count `quoter: hop N failing over from mainnet.base.org to base-mainnet.g.alchemy.com` ÷ window hours |
| M2 | Alchemy requests / failover | ratio | Alchemy Base POSTs in window ÷ Base→Alchemy failover events (same window) |
| M3 | Alchemy HTTP 429s / hour | count/h | httpx lines host=`base-mainnet.g.alchemy.com` status=429 ÷ hours |
| M4 | `eth_call` volume | count (/h optional) | Prefer app counters if exposed; else approximate via POST volume to Base RPC hosts during quote path (document method) |
| M5 | Successful quote responses | count + rate | Hop/route `status==ok` counts; or validation metrics `quote`/`EXECUTABLE` proxies — **label source** |
| M6 | Average / peak request rate | req/s | Sliding 10s (avg) and 1s (peak) bins over httpx POSTs to Alchemy Base host |
| M7 | Cooldown activations | count | Treatment only (baseline=0 expected). Count skip-path signals: hop errors containing `host cooldown`, or optional redacted counter if instrumented later. **Do not** add logging to Gate9. |
| M8 | Opportunity detection impact | A/B/C/E **or** quote-ok / fallback rates | Reuse paper/validation histogram or M6-style A/B/C/E if the isolated stack emits them; otherwise report quote `ok` vs `fallback:*` rates. **Fail-closed must remain honest** — never treat cooldown/rate-limit failures as successful quotes. |

### Derived (required for pass/fail)

| ID | Derived | Formula |
|---|---|---|
| D1 | Amplification factor | M2 = Alchemy_POSTs / failover_events |
| D2 | 429 reduction | `(M3_B - M3_T) / M3_B` (if M3_B > 0) |
| D3 | Quote honesty check | fallback/rate-limit outcomes still classified as non-ok; no inflation of M5 via coerced success |

---

## 4. Duration

| Parameter | Requirement |
|---|---|
| Minimum comparable window per arm | **30–60 minutes** continuous |
| Prefer | **≥60 minutes** if Base soft-RL rate is low (<~10 failovers) so M2 has n≥20 failovers |
| Start/end markers | Wall-clock ISO-8601 UTC stamped in the results JSON; align log `--since` / `--until` or file slice to the same bounds |
| Warm-up | Discard first **2–5 minutes** after container healthy (optional but recommended) |
| Cool-down between arms | Stop baseline fully before treatment; wait ≥60s so no shared process leftovers |

If either arm yields **&lt;10** Base→Alchemy failovers, **extend** that arm rather than declaring PASS on M2.

---

## 5. Exact measurement method (no secrets)

### 5.1 Preferred: capture logs from isolated container → offline parse

```bash
# EXAMPLE ONLY — replace NAME with isolated throwaway container (NOT Gate9)
ISOLATED=arbicore-failover-baseline-$$   # or treatment name
OUT=reports/shadow_validation/failover_${ISOLATED}_$(date -u +%Y%m%dT%H%M%SZ).log

# Capture (host-side). Do not `docker logs` Gate9 for this A/B.
docker logs --since 60m "$ISOLATED" 2>&1 \
  | sed -E 's#(g\.alchemy\.com/v2/)[^"[:space:]]+#\1REDACTED#g' \
  > "$OUT"

# Measure (script refuses Gate9 container names if --container is used)
python3 scripts/measure_base_failover_logs.py \
  --log-file "$OUT" \
  --arm baseline \
  --window-minutes 60 \
  --out reports/shadow_validation/failover_metrics_baseline.json
```

### 5.2 What to count in logs (host filter)

| Signal | Match (domains only; path redacted) |
|---|---|
| Failover event | `quoter: hop .* failing over from mainnet.base.org to base-mainnet.g.alchemy.com` |
| Alchemy POST | `HTTP Request: POST https://base-mainnet.g.alchemy.com/` (+ status token) |
| Public Base POST | `HTTP Request: POST https://mainnet.base.org` |
| Alchemy 429 | same Alchemy POST line with `"HTTP/1.1 429` |
| Alchemy 200 | `"HTTP/1.1 200` on Alchemy host |
| Cooldown skip (treatment) | error / hop text containing `host cooldown` (if surfaced in logs); else infer from M2→0 Alchemy POSTs during known 429 streaks |
| Soft primary RL | failover `err=code=-32016` (HTTP 200 on base.org is normal) |

**Redaction rule:** any `/v2/<secret>` → `/v2/REDACTED` or host-only. Optional fp8 = `sha256(path_segment)[:8]` offline — never print the segment.

### 5.3 Optional in-process counters (isolated builds only)

If a future isolated build adds redacted counters, accept:

- `failover_events_total{from=mainnet.base.org,to=alchemy}`
- `rpc_http_posts_total{host=…,status=…}`
- `rpc_http_429_cooldown_activations_total{host=…}`

Do **not** backport counter plumbing into the live Gate9 image for this procedure.

### 5.4 Opportunity / quote-ok (honest fail-closed)

On the **isolated** stack only:

- Prefer `GET /api/arbicore/validation/metrics` + report histogram if auth allows on the throwaway stack.
- Or count pipeline/paper outcomes A/B/C/E if that campaign instrumentation is present.
- Minimum honest substitute: fraction of quoted routes/hops with `status==ok` vs `fallback:*` / rate-limit errors over the same window.

**Integrity rule:** a hop that fails because Alchemy is cooling down or 429-limited must remain non-ok. PASS on Alchemy volume with inflated ok rates is an automatic **FAIL**.

### 5.5 Safety signals (both arms)

Confirm throughout isolated runs:

| Signal | Required |
|---|---|
| Signing attempts | 0 |
| Broadcast / submit | 0 |
| Execution mode | SHADOW |
| AUTOEXEC | OFF |
| Gate9 campaign | untouched |

---

## 6. Pass / fail criteria (for later deploy decision)

Deploy the workspace fix **only if all PASS rows hold**. This procedure itself does not deploy.

| # | Criterion | PASS | FAIL |
|---|---|---|---|
| C1 | Alchemy POSTs / failover (M2) | **≤ 2.0** on treatment (target ≤2; ideally ~1–2) | Treatment M2 ≥ 3 or still ≈5 |
| C2 | Alchemy 429s / hour (M3) | **Meaningful drop** vs baseline: ≥**70%** reduction **or** absolute M3_T ≤ 0.3× M3_B | No meaningful drop under comparable failover rate |
| C3 | Cooldown behaviour (M7) | Treatment shows cooldown skips after first HTTP-429 exhaustion (M7≥1 if sustained 429s) **or** M2 collapses toward ≤1 under continuous 429 | Continuous ≤2 POST bursts every failover with no skip despite sustained 429 |
| C4 | Fail-closed honesty (M5/M8/D3) | Rate-limit / cooldown paths remain non-ok; no false-positive profitable/EXECUTABLE inflation | Ok-rate inflated by treating RL as success |
| C5 | No signing / broadcast | 0 / 0 on isolated stack | Any signing or broadcast |
| C6 | SHADOW held | Isolated stack stays SHADOW; **Gate9 SHADOW campaign unchanged** | Any Gate9 mutation or live-mode promotion |
| C7 | Baseline sanity | Baseline M2 ≈ **4.5–5.5** (confirms Gate9-equivalent amplifier still present) | Baseline already ≤2 → wrong image / wrong path measured |
| C8 | Opportunity detection | M8 not collapsed to silent zero-scan; quote attempts continue; failures explicit | Scanner wedged / metrics missing with no explanation |

**Conditional PASS:** C1+C2+C4+C5+C6+C7 hold, but C3 weak because Alchemy returned mostly 200s (no 429 to arm cooldown) — document as “bound-retry validated; cooldown not stressed” and optionally re-run under known limited secondary.

**NO-GO deploy** if treatment requires Gate9 restart during the live campaign, or if measurement was taken from `arbicore-x-backend-new`.

---

## 7. Explicit: do not run against live Gate 9

| Action | Against Gate9 (`arbicore-x-backend-new`)? |
|---|---|
| Use as baseline measurement host for this A/B | **NO** |
| Deploy patched `quoter.py` / rebuild in place | **NO** |
| Restart / recreate / env change | **NO** |
| Point optional script `--container arbicore-x-backend-new` | **BLOCKED** by script deny-list |
| Read-only `docker inspect` / operator campaign freeze check | Allowed (not part of A/B arms) |

Historical Gate9 log ratios in the root-cause doc may be **cited** as prior evidence that baseline≈5, but the controlled A/B **must** be re-measured on isolated containers with comparable windows.

---

## 8. Results comparison table (fill after both windows)

Copy into the results note / JSON sidecar:

| Metric | Baseline (B) | Treatment (T) | Δ (T−B) | PASS? |
|---|---:|---:|---:|:---:|
| Window start (UTC) | | | — | — |
| Window end (UTC) | | | — | — |
| Window hours | | | — | — |
| Base failover events | | | | — |
| Base failover events/hour (M1) | | | | — |
| Alchemy POSTs (Base host) | | | | — |
| Alchemy POSTs / failover (M2) | | | | C1 |
| Alchemy 429s | | | | — |
| Alchemy 429s/hour (M3) | | | | C2 |
| eth_call volume (M4) | | | | — |
| Successful quotes (M5) | | | | C4 |
| Quote ok rate (M5) | | | | C4 |
| Avg Alchemy req/s (M6) | | | | — |
| Peak Alchemy req/s (M6) | | | | — |
| Cooldown activations (M7) | 0 (expected) | | | C3 |
| A/B/C/E or ok/fallback (M8) | | | | C4/C8 |
| Signing / broadcast | 0/0 | 0/0 | — | C5 |
| Image tag / quoter build id | | | — | C7 |
| Gate9 RestartCount/StartedAt | unchanged | unchanged | — | C6 |

**Verdict line (required):** `PASS` | `CONDITIONAL PASS` | `FAIL` — with one-sentence rationale referencing C1–C8.

Artifact path suggestion:

`reports/shadow_validation/base_failover_ab_YYYYMMDDTHHMMSSZ.json`

---

## 9. Isolated stack sketch (informational — not executed by this doc)

```text
# Baseline (Gate9-equivalent image) — throwaway name only
docker run -d --name arbicore-failover-baseline \
  --env-file <isolated-env-no-gate9-secrets-reuse-policy> \
  arbicore-x-backend:g5.79-green-20260927

# Treatment — build from cert workspace; do not retag over Gate9 running container
docker build -t arbicore-x-backend:failover-fix-20261002 <workspace-backend-context>
docker run -d --name arbicore-failover-treatment \
  --env-file <same-shape-isolated-env> \
  arbicore-x-backend:failover-fix-20261002
```

Env shape must preserve Base candidate order (`ARBICORE_RPC_URL_BASE` → public Base; `ARBICORE_RPC_URL` → Alchemy Base). Do not point isolated treatment at Gate9 Mongo/journals unless operator explicitly wants shared read-only evidence — default is fully throwaway.

---

## 10. Optional measurement script

- Path: `scripts/measure_base_failover_logs.py`
- Mode: **read-only** parse of a log file **or** `docker logs` from a **non-Gate9** container
- Deny-list includes: `arbicore-x-backend-new`
- Output: redacted JSON metrics (M1–M3, M6; M7 if `host cooldown` seen; stubs for M4/M5/M8 to fill manually)
- Does not restart containers, does not change env, does not call Alchemy

---

## 11. STOP

This document + optional script are the deliverable. **No deploy.** **No Gate9 restart.** **No SHADOW campaign change.** After Gate 9 completes, run the isolated A/B, fill §8, then decide deploy in a separate change window.
