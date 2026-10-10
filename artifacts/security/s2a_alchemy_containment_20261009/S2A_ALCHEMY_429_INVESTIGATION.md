# S2-A — Post-cutover HTTP 429 investigation (read-only)

**Verdict: ACCEPTABLE WITH EXPLANATION**  
**UTC:** `2026-10-10T08:25Z` (approx.)  
**Scope:** Log analysis only · no mutations · no revocation · g5.79 untouched

Evidence: `cutover_429_investigation.json`

---

## Summary

The earlier acceptance tally of **11** httpx lines containing the substring `429` **over-counted**. Many matches were **millisecond fields** in timestamps (e.g. `06:59:19,429`) on otherwise successful `200 OK` lines—not HTTP 429 responses.

**True httpx responses with status 429 in the recreate→accept window: 5.**

Rate-limit incidence is comparable to baseline once normalized; events were a **brief post-recreate cluster**, not a sustained multi-hour storm. Fallback behaviour on Base public RPC worked as designed.

---

## Corrected counts vs baseline

| Metric | Post-cutover scan (~90m) | Preflight baseline (60m) |
|---|---:|---:|
| httpx requests parsed | 3348 | 1593 |
| True HTTP **429** status | **5** | 2 |
| 429 per 1000 httpx | **1.49** | 1.26 |
| 429 per hour (normalized) | **~3.3** | 2.0 |
| HTTP 401/403 | 0 | 0 |
| HTTP 5xx | 0 | 0 |
| Naive “line contains 429” (prior) | 11 | 2 |

Request volume was higher post-cutover (~2232 httpx/h vs ~1593/h), consistent with recreate + resumed SHADOW traffic—not evidence of credential failure.

---

## Event timeline (secret-free)

All **5** true 429s fall in a **~35 second** window right after recreate:

| Time (UTC) | Chain | Host (no path/key) | Notes |
|---|---|---|---|
| `06:58:42.981` | base | `mainnet.base.org` (public) | Quoter path; cooldown + failover to Base Alchemy |
| `06:59:16.756` | polygon | `polygon-mainnet.g.alchemy.com` | Burst |
| `06:59:17.033` | polygon | same | Burst |
| `06:59:17.700` | polygon | same | Burst |
| `06:59:17.936` | polygon | same | Burst |

- **First → last span:** ~35 s (`06:58:42`–`06:59:17`)  
- **After `06:59:19`:** Polygon Alchemy returns **200**; no further true 429 statuses in the remainder of the ~90m window  
- **Sustained multi-hour 429 pattern:** **No**  
- **Clustered:** **Yes** (sub-second gaps within the Polygon burst)

5-minute bucket: only `2026-10-10 06:55` (covers recreate).

---

## Fallback behaviour

App logs (redacted) show expected Base handling:

1. `rpc_429 host=mainnet.base.org chain=base … kind=http_429`  
2. `kind=cooldown_gate`  
3. `quoter: hop 2 failing over from mainnet.base.org to base-mainnet.g.alchemy.com` (`fallback:revert`, public `-32016` / 429 cooldown)

This is the documented public-Base → Alchemy failover path, **not** a new-primary auth failure. No evidence of fallback-registry thrash across Mongo slots `[1]`–`[5]`.

---

## Chain / provider attribution

| Class | Count | Assessment |
|---|---:|---|
| Public Base (`mainnet.base.org`) | 1 | Expected; ENV Base still public |
| Alchemy Polygon | 4 | Short burst; recovered within ~2 s |
| Other chains (eth/arb/op/bnb/base Alchemy) | 0 true 429 in window | Clean |

---

## Verdict rationale

| Question | Answer |
|---|---|
| Credential / cutover failure? | **No** — no 401/403; primaries healthy; Polygon recovered to 200 |
| Transient vs sustained? | **Transient** (~35 s at startup) |
| Fallback as expected? | **Yes** (Base public → Alchemy) |
| Block revoke readiness? | **No** — does not invalidate primary cutover PASS |

**ACCEPTABLE WITH EXPLANATION** — elevated naive count explained; true 429 rate ≈ baseline; no revoke blocker from this signal alone.

---

## Non-actions (confirmed)

No key revocation, config changes, restarts, P2, or execution enablement performed. SHADOW / AUTOEXEC=false / RUNTIME=false / legacy stopped / g5.79 out of scope preserved.
