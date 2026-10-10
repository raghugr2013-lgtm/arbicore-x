# Base / Alchemy 429 Root-Cause Audit — 2026-10-02

- Status: **READ-ONLY Gate9** + **workspace-only remediation** (not deployed)
- Container: `arbicore-x-backend-new` (`arbicore-x-backend:g5.79-green-20260927`)
- Campaign start / StartedAt: `2026-10-02T06:19:33Z` — **RestartCount=0 throughout this audit**
- Wired Alchemy key path fingerprint: **`5e5d5bb1`** (confirmed; secrets never printed)
- Dashboard identity: **UNVERIFIABLE** (restated; see §8)

---

## Primary classification (exactly one)

# **RETRY/FAILOVER BUG**

Evidence-backed: QuoterRegistry failover from public Base `-32016` to Alchemy burns the **full** `_RPC_MAX_RETRIES` budget on the **last** candidate (default 4 → **5 POSTs**), with **no host cooldown** and **no use of ProviderRegistry circuit breaker**. Live ratio:

| Signal (logs since campaign start, refreshed this audit) | Value |
|---|---:|
| Quoter failover events (`mainnet.base.org` → Alchemy) | **650** |
| Alchemy Base POSTs | **3266** (10×200 / 3255×429 / 1×other) |
| **Alchemy POSTs / failover** | **5.025** ≈ `_RPC_MAX_RETRIES + 1` |

That multiplier is software amplification on top of a real Alchemy throughput reject — not a credential mismatch return, and not explained by dashboard 445.

---

## 1. Base RPC URLs used by running backend (domains only)

### Env (running container) — domains + fp

| Env var | Domain | Alchemy? | key path_fp |
|---|---|---|---|
| `ARBICORE_RPC_URL_BASE` | `mainnet.base.org` | no | n/a |
| `ARBICORE_RPC_URL` | `base-mainnet.g.alchemy.com` | yes | **5e5d5bb1** |
| `ARBICORE_ARCHIVE_RPC_URL` | `base-mainnet.g.alchemy.com` | yes | **5e5d5bb1** |
| `ARBICORE_RPC_URL_{ETH,ARB,OP,POLY,BNB}` | `*-mainnet.g.alchemy.com` | yes | **5e5d5bb1** |
| `PROVIDER_RPC_URLS[_BASE]` / `PROVIDER_RPC_URL_BASE` | empty | — | — |
| `ALCHEMY_API_KEY` | empty | — | — |
| `ARBICORE_RPC_MAX_RETRIES` | unset → default **4** | — | — |

**Credential mismatch has not returned.** All Alchemy URL path segments fingerprint to **`5e5d5bb1`**. No key replacement indicated.

### QuoterRegistry `_rpc_url_candidates("base")` order

1. `mainnet.base.org` ← `ARBICORE_RPC_URL_BASE` (first)
2. `base-mainnet.g.alchemy.com` ← `ARBICORE_RPC_URL` (Base-only global alias)

Code: `QuoterRegistry._rpc_url_candidates` / `_rpc_url` in `arbicore/execution/quoter.py`; `resolve_rpc_url_from_env` in `arbicore/config/persistent.py` (Base-only `ARBICORE_RPC_URL` alias).

### ProviderRegistry (bootstrap) — separate path

Registry lists:

- `rpc_base_0_mainnet_base_org` — **DEGRADED** (early window; last error ~06:20Z)
- `rpc_base_1_base-mainnet_g_alchemy_c` — **TRIPPED** at ~06:20–06:21Z (`circuit_open_until` ~06:21:11Z; successes=0)

**QuoterRegistry does not consult this circuit breaker.** Alchemy stayed TRIPPED in registry while quoter continued POSTing for hours.

---

## 2. Exact provider / failover path for Alchemy POSTs

```
quote_route(chain=base)
  → _rpc_url_candidates → [mainnet.base.org, base-mainnet.g.alchemy.com]
  → (optional) _verified_chain_endpoints via eth_chainId
  → per hop: backend.quote_hop → _eth_call
       primary (base.org): max_retries=1  (2 attempts)   [RUNNING IMAGE]
       on rate-limit / transport fault (_should_failover):
         failover → Alchemy last candidate: max_retries=None → _RPC_MAX_RETRIES=4
                    → up to 5 POSTs with backoff 0.3×2^attempt
```

Log sample (redacted):

```
quoter: hop 0 failing over from mainnet.base.org to base-mainnet.g.alchemy.com
  (status=fallback:revert err=code=-32016 over rate limit)
```

Public Base often returns **HTTP 200** with JSON-RPC `-32016 over rate limit` (not HTTP 429). That still triggers failover. Alchemy then answers with **HTTP 429**.

Hop breakdown of failovers: hop0≈255, hop1≈204, hop2≈192 — multi-hop routes, not separate duplicate scanner processes.

---

## 3. Why Alchemy returns 429 (mechanisms)

| Hypothesis | Verdict | Evidence |
|---|---|---|
| CU/s monthly capacity exhaustion | **Not proven** this window | Prior M6 reset; success-only CU floor tiny; dashboard CU unverifiable |
| Concurrent / throughput limit on Free Alchemy Base | **Likely contributing** | Nearly all Alchemy POSTs are HTTP 429; 4–10×200 only |
| Retry loop on last candidate | **PROVEN primary amplifier** | 5.025 POSTs/failover = max_retries+1 |
| Identical eth_call replay | **Yes, by design of retry** | Same `eth_call` (+ optional batch `eth_blockNumber`) retried |
| Failover loop (primary soft-RL → Alchemy hard-429) | **PROVEN** | 650 failovers; Alchemy≈99.7% 429 |
| Quoter polling | **Contributor** | Shadow quoting drives continuous hops; not itself a bug |
| Credential / wrong key | **Ruled out for wired runtime** | fp still `5e5d5bb1`; early probe eth_chainId 200 |

**Dominant chain:** public Base soft rate-limit → quoter failover → Alchemy already throughput-limited → **5 hard retries per failover with no cooldown**.

---

## 4. Retry / backoff behaviour

| Layer | File / function | Behaviour |
|---|---|---|
| Quoter `_eth_call` | `execution/quoter.py` | Retries on `-32016` / HTTP 429; sleep `0.3 * 2^attempt`; default max 4 |
| Quoter `quote_route` | same | Intermediate candidates: `max_retries=1`; **last candidate: full budget** (running image) |
| Per-host throttle | `_throttle` | 140ms min interval **per host**; Alchemy and base.org independent → failover not paced as one stream |
| ProviderRegistry RPC | `providers/rpc.py` `EthJsonRpcProvider._call` | Separate bounded backoff + Retry-After; circuit trip |
| `rpc_failover.RegistryRpcProvider` | thin facade over registry | **Not used by QuoterRegistry quote path** |

---

## 5. Does one failure retry immediately / repeatedly?

**Yes.**

1. Primary soft-RL: up to 2 attempts (`mr=1`), then failover.
2. Alchemy: up to **5** attempts immediately (backoff 0.3s, 0.6s, 1.2s, 2.4s…), all typically 429.
3. Next hop / next quote repeats the full Alchemy budget — **no memory** that Alchemy just hard-limited (registry trip is ignored).

---

## 6. Multiple scanner workers duplicating Base quotes?

**Not the primary amplifier.** Failovers appear as hop 0/1/2 on multi-hop routes (expected). No evidence of N independent scanners each multiplying Alchemy by another full factor beyond hop parallelism. The **5× last-candidate retry** dominates.

---

## 7. Does public Base 429 / -32016 cause excessive Alchemy fallback burst?

**Yes — proven.**

- Public HTTP 429 count is modest (~98).
- Soft `-32016` / failover lines: **650**.
- Each drives ~5 Alchemy POSTs → **~3255 Alchemy 429s**.

Without the last-candidate full retry budget, Alchemy volume would be ~2× failover (if `mr=1`) or ~1× with cooldown after first HTTP 429 exhaustion.

---

## 8. Reconcile 2729 vs dashboard 445

Restating prior reconciliation (identity still **UNVERIFIABLE**):

| Signal | Operator dashboard (claimed) | Server logs (wired fp `5e5d5bb1`) |
|---|---|---|
| Requests | 445 / 24h | **2729+** Alchemy POSTs in ~2.5h alone; **3266** by this audit |
| Success | 95.2% / 1h | Alchemy ≃ **0.1–0.3%** |
| Throughput limited | 0% | Continuous Alchemy HTTP 429 |

**Cannot treat 445 as the wired key’s traffic** until operator confirms dashboard key fp = `5e5d5bb1`. Classification of this discrepancy alone would be `DASHBOARD TELEMETRY MISMATCH` / identity gap — **secondary** to the proven retry/failover amplifier.

---

## Exact files / functions

| Path | Symbols |
|---|---|
| `app/backend/arbicore/execution/quoter.py` | `_eth_call`, `_single_call`, `_throttle`, `_is_rate_limited`, `_should_failover`, `QuoterRegistry._rpc_url_candidates`, `QuoterRegistry.quote_route` |
| `app/backend/arbicore/config/persistent.py` | `resolve_rpc_url_from_env`, `resolve_rpc_url` |
| `app/backend/arbicore/providers/bootstrap.py` | `_rpc_urls`, `bootstrap` |
| `app/backend/arbicore/providers/rpc_failover.py` | `RegistryRpcProvider` (unused by quoter path) |
| `app/backend/arbicore/providers/registry.py` | circuit breaker (tripped Alchemy; ignored by quoter) |
| `app/backend/arbicore/providers/rpc.py` | `EthJsonRpcProvider` retry/backoff |

---

## PHASE 2 — Smallest remediation (CERT WORKSPACE ONLY)

### Applied in workspace (NOT deployed to Gate9)

**File:** `app/backend/arbicore/execution/quoter.py`

1. **Bound failover candidate retries** — `quote_route` now uses `_RPC_FAILOVER_CANDIDATE_RETRIES` (default **1**) for **every** candidate including last (was: last → full `_RPC_MAX_RETRIES=4`).
2. **HTTP 429 host cooldown** — after HTTP 429 retries exhausted, mark host for `_RPC_HTTP_429_COOLDOWN_S` (default **60s**). Subsequent `_eth_call`s return rate-limit error with **zero POSTs** so failover can advance or fail closed. Soft JSON-RPC `-32016` on HTTP 200 does **not** arm this cooldown (avoids parking healthy public Base).
3. Clear cooldown on successful call.

Env knobs (optional, defaults safe): `ARBICORE_RPC_FAILOVER_CANDIDATE_RETRIES`, `ARBICORE_RPC_HTTP_429_COOLDOWN_S`.

**Not done:** no Gate9 restart, no config/provider/key change, no new RPC architecture, no gate weaken, no log suppression.

### Infra-only alternative (if code fix deferred)

Raise Alchemy Base throughput (paid CU/s) **and/or** add a third non-Alchemy Base RPC in `ARBICORE_RPC_URL_BASE` CSV ahead of Alchemy — but **do not** change running Gate9 during campaign. Pure infra without the code fix still allows 5× burst into any limited secondary.

---

## Tests required / run (workspace only)

| Test | Result |
|---|---|
| `tests/test_quoter_scoped_throttle.py` (existing + new cooldown / bound-retry cases) | **14 passed** |
| Runner | Throwaway `docker run --rm` with workspace mount — **not** `arbicore-x-backend-new` |

New coverage:

- `test_http_429_arms_cooldown_and_skips_posts`
- `test_soft_jsonrpc_rate_limit_does_not_arm_http_429_cooldown`
- `test_failover_candidate_retries_are_bounded`

---

## Expected effect on Alchemy request rate

| Scenario | Alchemy POSTs per public-Base failover |
|---|---|
| **Running Gate9 image (now)** | ~**5** (observed 5.025) |
| After workspace fix, before cooldown arms | ≤**2** (`mr=1`) |
| After first HTTP 429 exhaustion (60s window) | **0** further POSTs to that host |

Projected vs current campaign: order-of-magnitude drop in Alchemy 429 volume (hundreds → low tens per hour under similar primary soft-RL rate), with fail-closed hop status when both endpoints are limited.

---

## Can the fix be independently tested after Gate 9?

**Yes.** Unit tests already pass offline. Post-campaign: deploy workspace image to a **non-Gate9** instance (or next campaign), reproduce Base soft-RL → Alchemy path, confirm Alchemy POST/failover ratio ≤2 and cooldown skips. Do **not** hot-patch the live Gate9 campaign.

---

## Gate 9 campaign untouched — confirmation

| Check | Value |
|---|---|
| Container | `arbicore-x-backend-new` still running |
| StartedAt | `2026-10-02T06:19:33.513948555Z` (unchanged) |
| RestartCount | **0** |
| Image quoter `quote_route` | still contains `mr = None if ci == n - 1 else 1` (**OLD_FULL_BUDGET**) |
| Cooldown code in running image | **absent** |
| Actions this audit | docker logs / exec read-only env+status; workspace file edits only; throwaway test container |

SHADOW ON / AUTOEXEC OFF / signing=0 / broadcast=0 / Gate7=$25 / Gate8/H05 fail-closed — **not modified**.

---

## STOP

No Gate9 restart, recreation, config change, provider switch, Alchemy key change, or source deploy to the running instance.
