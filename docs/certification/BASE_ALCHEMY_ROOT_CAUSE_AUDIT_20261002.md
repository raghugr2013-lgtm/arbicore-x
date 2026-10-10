# Base / Alchemy Root-Cause Audit (READ ONLY) — 2026-10-02

- **Status:** READ ONLY — no restart, redeploy, RPC/config/credential change, campaign interference, or container modify
- **Audit UTC:** ~`2026-10-02T16:35Z` (evidence collected from live container + logs; correlation window frozen to prior cert)
- **Container:** `arbicore-x-backend-new` · Image `arbicore-x-backend:ws-a-befb14e-20261002` · Tip **`befb14e6aa77515daa038e142ff978822a4fab91`**
- **T0 (StartedAt):** `2026-10-02T15:08:52.884157323Z` · RestartCount **0** · Mode **SHADOW**
- **Correlation window:** T0 → `2026-10-02T15:26:00Z` (matches prior `ALCHEMY_POSTFIX_CORRELATION_AUDIT_20261002.md`)
- **Campaign:** `docs/certification/POST_FIX_12H_SHADOW_CAMPAIGN_IN_PROGRESS_20261002.md`
- **Prior correlation:** `docs/certification/ALCHEMY_POSTFIX_CORRELATION_AUDIT_20261002.md`
- **Code meaning reference:** tip `befb14e` `arbicore/execution/quoter.py` (throwaway read-only)

**Secrets:** Alchemy path keys never printed. Fingerprints are `sha256(key)[:8]` only.

---

## Executive verdict (evidence-only)

| Question | Answer |
|---|---|
| Primary Base endpoint | **`https://mainnet.base.org`** (path `/`, no key) |
| Alchemy fallback hostname | **`base-mainnet.g.alchemy.com`** path `/v2/<REDACTED>` |
| Are 327 failovers caused by primary Base errors? | **YES** — all 327 logged as failover **from** `mainnet.base.org` |
| Is Alchemy reached? | **YES** — 38 Base-Alchemy POSTs in correlation window |
| Is endpoint/key configuration wrong? | **YES (effective runtime secondary key)** — see §9 |
| Why 0 successful quotes? | Primary RL → failover → Alchemy **429 / cooldown** (and early HTTP 200s never yielded `status=ok`) |
| Confidence | **HIGH** on endpoints, failover taxonomy, env_sync key swap, 0 ok quotes; **MEDIUM** on exact JSON-RPC body class of the 13×200 (bodies not logged) |

---

## Identity / wiring (verified)

| Field | Observed |
|---|---|
| Docker `Config.Env` / `/proc/1/environ` initial | `ARBICORE_RPC_URL_BASE=https://mainnet.base.org` |
| Docker-wired Alchemy (global) | `ARBICORE_RPC_URL` / `ARBICORE_ARCHIVE_RPC_URL` → `base-mainnet.g.alchemy.com/v2/…` · **fp `5e5d5bb1`** |
| Other chain Alchemy URLs | same fp **`5e5d5bb1`** |
| Persistent Network Config (`GET /api/arbicore/settings/network`) | `rpc_urls.base = ["https://mainnet.base.org", "https://base-mainnet.g.alchemy.com/v2/…"]` · Alchemy entry **fp `ce00e63d`** · `updated_at=2026-09-27T09:31:23Z` · `revision_id=rev-615fa528…` |
| `env_sync` at boot | **`2026-10-02T15:09:08.734Z`** exported `ARBICORE_RPC_URL`, `ARBICORE_RPC_URL_BASE`, `BASE_RPC_URL`, `PROVIDER_RPC_URLS_BASE`, executor |

### Alchemy key split in httpx logs (correlation window)

| Key fp | POSTs | HTTP histogram | When |
|---|---:|---|---|
| **`5e5d5bb1`** (docker-wired) | **14** | **13×200 / 1×400 / 0×429** | `15:09:01`–`15:09:08` (pre / at env_sync) |
| **`ce00e63d`** (persistent network secondary) | **24** | **0×200 / 0×400 / 24×429** | from `15:09:08.928Z` onward |
| **Total** | **38** | **13 / 1 / 24** | matches prior correlation |

**Mechanism:** `arbicore.config.env_sync.sync_env_from_network_config` pushes persistent `rpc_urls.base` into process `os.environ`. Primary list entry becomes `ARBICORE_RPC_URL` / `ARBICORE_RPC_URL_BASE`; full list becomes `PROVIDER_RPC_URLS_BASE`. Quoter `_rpc_url_candidates("base")` then failover-selects Alchemy from **`PROVIDER_RPC_URLS_BASE` → fp `ce00e63d`**, not the docker-wired `5e5d5bb1`.

---

## 1. Base RPC errors causing the 327 failovers

**Census (correlation window):** exactly **327** lines  
`quoter: hop N failing over from mainnet.base.org to base-mainnet.g.alchemy.com (…)`.

These `err=` payloads are the **primary-candidate** failure that triggered failover (code: `quote_route` logs before trying the next URL).

| Category | Count | Log / transport signature |
|---|---:|---|
| **JSON-RPC rate limit** (`code=-32016`, message `over rate limit`) | **9** | Soft provider RL on primary (public Base commonly returns this on **HTTP 200** JSON-RPC body; not HTTP 429) |
| **Client host-cooldown fail-fast** (`code=-32016`, message `HTTP 429 host cooldown (recent rate limit)`) | **318** | `_eth_call` short-circuit after transport HTTP 429 armed per-host cooldown on `mainnet.base.org` (default 60s) — **zero new primary POST** while cooled |
| HTTP status (non-429) as failover trigger | **0** | — |
| Timeout | **0** | — |
| Connection error | **0** | — |
| Invalid request | **0** | — |
| Contract / execution revert (`execution reverted`) | **0** | — |
| Other | **0** | — |
| **Total** | **327** | |

### Supporting primary httpx (same window)

| Host | POSTs | 200 | 429 | other |
|---|---:|---:|---:|---:|
| `mainnet.base.org` | **233** | **217** | **16** | **0** |

- The **16× HTTP 429** on `mainnet.base.org` are what **arm** the primary host cooldown → explain the **318** cooldown-gated failover errs.
- Many of the **217× HTTP 200** still surface JSON-RPC **`-32016 over rate limit`** (the **9** explicit primary soft-RL failovers); httpx status alone under-counts soft RL.

**No** timeout / connect / contract-revert classes appear on the 327 failover lines.

---

## 2. Exact Base primary endpoint

| Item | Value |
|---|---|
| Hostname | **`mainnet.base.org`** |
| Scheme/path | **`https://mainnet.base.org`** (no `/v2/`, no embedded secret) |
| Env (docker initial) | `ARBICORE_RPC_URL_BASE` |
| After `env_sync` | still public Base as list primary; also written onto `ARBICORE_RPC_URL` / `BASE_RPC_URL` |
| Live probe | `GET /api/arbicore/rpc/check` → `rpc_url_masked=mainnet.base.org`, `chain_id=8453` |

---

## 3. Exact Alchemy Base fallback hostname

| Item | Value |
|---|---|
| Hostname | **`base-mainnet.g.alchemy.com`** |
| Path | **`/v2/<REDACTED>`** |
| No other Alchemy Base host in window | confirmed |

---

## 4. Does Alchemy hostname/app correspond to fp `5e5d5bb1`?

| Layer | fp | Match `5e5d5bb1`? |
|---|---|---|
| Docker-wired `ARBICORE_RPC_URL` / archive | **`5e5d5bb1`** | **YES** |
| Early httpx POSTs (`15:09:01`–`15:09:08`) | **`5e5d5bb1`** | **YES** (all 13×200 + 1×400) |
| Persistent network secondary + post-`env_sync` quoter failover POSTs | **`ce00e63d`** | **NO** |
| All 24×429 in correlation window | **`ce00e63d`** | **NO** |

**Conclusion:** Hostname is correct (`base-mainnet.g.alchemy.com`). The **intended post-fix key fp `5e5d5bb1` is wired in Docker**, but **effective quoter failover traffic after `15:09:08Z` uses a different app key (`ce00e63d`)** from stale persistent Network Config.

---

## 5. Classify 13× HTTP 200 Alchemy responses (JSON-RPC ≠ HTTP)

**HTTP 200 ≠ success.** Response **bodies are not logged** (httpx status lines only). Classification is therefore observational + code-path inference.

| Class | Count | Evidence |
|---|---:|---|
| **Successful DEX `eth_call` → HopQuote `status=ok`** | **0** | Zero quoter `status=ok` lines in entire T0→audit window |
| **Boot / non-quote probes** (scanner start, identity, substrate) | **~5–6** (`15:09:01`–`15:09:05`) | Occur under `_autostart_opportunity_scanner` / boot **before** ContinuousScanner and before most failover storm; consistent with `eth_chainId` / early RPC probes on docker key `5e5d5bb1` |
| **Failover-path Alchemy POST that still left hop as `fallback:revert`** | **~7–8** (`15:09:07`–`15:09:08`) | Interleaved with `failing over … status=fallback:revert`; no subsequent `status=ok` → HTTP 200 body was **not** a usable successful quote result (JSON-RPC `error`, empty/unusable `result`, or concurrent non-quote call). **Exact JSON-RPC code not recoverable from logs** |
| **Contract revert** | **0 proven** | No `execution reverted` in quoter errs |
| **Malformed / unusable** | **not separately counted among 200s** | Adjacent **1× HTTP 400** on same key (not in the 13) |

**Bottom line:** all **13** HTTP 200s are on fp **`5e5d5bb1`**; **none** produced a successful quote.

---

## 6. Classify 24× HTTP 429 (Alchemy)

| Signal | Observation |
|---|---|
| Host | `base-mainnet.g.alchemy.com` |
| Key fp | **`ce00e63d` only** (100% of window 429s) |
| httpx line | `"HTTP/1.1 429 Too Many Requests"` |
| Body strings in logs | **No** `Monthly capacity limit exceeded` / `scaling policy` / `throughput` / `compute units` / `Retry-After` |
| Cadence | After first 429s, `_RPC_HTTP_429_COOLDOWN_S` (default **60s**) suppresses further POSTs → sparse ~2 POST bursts when cooldown expires (matches prior correlation) |

| Hypothesis | Verdict |
|---|---|
| Account / monthly CU quota exhaustion | **Not proven in this window** (classic capacity body absent; that class was documented on older capacity incidents, not re-observed here as text) |
| Provider rate limit / throughput / concurrent reject | **Best fit** — transport HTTP 429 + `Too Many Requests`; sustained reject on every post-sync failover hit |
| Per-second client amplification (old 5× bug) | **Not dominant post-`befb14e`** — cooldown + `mr≤1` collapsed amplification (prior correlation); residual 429s remain when cooldown expires |
| Wrong hostname | **No** — host is correct |
| Wrong/stale **key** relative to docker tip | **YES** — 429s are on **`ce00e63d`**, not `5e5d5bb1` |

---

## 7. Why 327 failed quotes → `fallback:revert`

### Code meaning (`befb14e` `quoter.py`)

1. Backend `quote_hop` → `_eth_call(...)`.
2. If `_eth_call` returns any `err` dict → `_fallback_hop(..., status="fallback:revert", error=f"code={code} {message}")`.
3. **Naming:** `fallback:revert` is the hop status for **any JSON-RPC / mapped RPC error**, including **rate-limit `-32016` and HTTP 429 mapped to `-32016`** — **not** exclusively an EVM contract revert.
4. Genuine contract reverts (`execution reverted`) also use this status but **`_should_failover` returns False** for those — and **zero** such messages appear on the 327 lines.
5. `quote_route` on non-ok + `_should_failover` → log `failing over from {primary} to {next}` then retry next candidate with bounded retries.
6. If **every** candidate fails → hop remains `fallback:revert`; route aggregates to `partial` / `fallback:break_even`.

### Observed mapping

| Stage | Result |
|---|---|
| Primary `mainnet.base.org` | `-32016 over rate limit` **or** cooldown fail-fast → `fallback:revert` → failover |
| Alchemy secondary | HTTP **429** → mapped `code=-32016 message=HTTP 429…` → `fallback:revert`; then host cooldown → further attempts fail-fast with **zero POST** |
| Final hop outcome | **327× `fallback:revert`** · **0× `status=ok`** |

---

## 8. Failure-stage map (A–F)

Multi-stage. Evidence per stage:

| Stage | Role in this window | Evidence |
|---|---|---|
| **A — Before Alchemy** | **YES — initiates every failover** | 327× failover **from** `mainnet.base.org`; 9 soft `-32016` + 318 primary cooldown; 16× base.org HTTP 429 |
| **B — Primary Base** | **YES — root trigger** | Same as A; live `/api/arbicore/rpc/check` still reaches Base for chainId/block when not cooled |
| **C — Alchemy transport** | **YES — blocks recovery** | 24× HTTP 429 on fp `ce00e63d`; cooldown arms on hostname `base-mainnet.g.alchemy.com` |
| **D — JSON-RPC** | **YES (primary soft RL); partial on Alchemy 200s** | Primary `-32016 over rate limit`; Alchemy 200 bodies not logged but produced no `ok` quotes |
| **E — DEX `eth_call`** | **Attempted; not proven contract-revert** | Quoter path is `eth_call` to UniV3/Aero/etc.; failures are RPC/RL class, not `execution reverted` |
| **F — ArbiCore quote-processing** | **Labels outcome; does not invent RL** | Maps any `_eth_call` err → `fallback:revert`; failover + cooldown logic; **env_sync** swaps secondary key mid-boot |

**Exact point quotes fail to become successful:** after primary Base rate-limit class failure, the Alchemy failover candidate does not return a usable successful `eth_call` result (429 / cooldown; early 200s never → `status=ok`).

---

## 9. “Is Alchemy endpoint/key configuration wrong?”

### **YES** (effective runtime secondary key) — with nuance

| Claim | Verdict |
|---|---|
| Hostname wrong? | **NO** — `base-mainnet.g.alchemy.com` is correct |
| Docker tip key `5e5d5bb1` invalid/unusable? | **NO** — that key served **13× HTTP 200** (+1×400) in the first ~7s |
| Effective failover key correct for post-fix intent? | **NO** — after `env_sync` (`15:09:08Z`), quoter secondary is persistent **`ce00e63d`** (Network Config from **2026-09-27**), and **all 24×429** hit that key |
| Stale persistent override of docker env? | **YES — proven** by API `rpc_urls.base[1]` fp `ce00e63d` + log `env_sync: exported … PROVIDER_RPC_URLS_BASE` + httpx key split |

---

## 10. “Is primary Base RPC the reason for the 327 failovers?”

### **YES**

- Every one of the **327** failover log lines is `failing over from mainnet.base.org …` with primary-side `err=` in the rate-limit / cooldown class (§1).
- Public Base **HTTP 429 (16)** + soft **`-32016` (9 logged)** are the concrete primary faults.
- Alchemy failure explains **why failover did not restore quotes**, but **does not create** the 327 primary→secondary failover events.

---

## 11. Why 13× HTTP 200 Alchemy still → 0 successful quotes?

**Exact observable reasons (conjoined):**

1. **None of the 13 HTTP 200 responses produced a quoter hop with `status=ok`** (log census: **0**).
2. **~5–6** of the 200s occur in **boot/scanner startup** on fp `5e5d5bb1` before the failover storm — not evidenced as successful DEX quote completions.
3. **~7–8** 200s occur **during** early failover attempts on `5e5d5bb1`, yet interleaved hops remain `fallback:revert` — so those HTTP 200 bodies were **not usable successful quote `eth_call` results** (JSON-RPC error / unusable result / non-quote method). Bodies not logged ⇒ finer JSON-RPC code **not claimable**.
4. After **`15:09:08Z`**, failover Alchemy traffic switches to **`ce00e63d`**, which returns **only HTTP 429** in-window — so the recovery path is transport-rejected, not quote-successful.
5. Quoter then **cooldowns** the Alchemy **hostname**, so most of the 327 paths never obtain a live secondary `eth_call` success.

---

## 12. Extended window note (not the 327 freeze)

For situational awareness only (campaign continues; **do not** redefine the 327):

| Metric (T0 → ~audit refresh) | Approx |
|---|---:|
| Failovers | ~1000 (973 cooldown / 27 over-rate) |
| Alchemy POSTs | ~80 (13×200 / 1×400 / 66×429) |
| Alchemy 429 key | still **`ce00e63d`** |
| Successful quotes | still **0** |

---

## Confidence / evidence level

| Topic | Level | Basis |
|---|---|---|
| Primary endpoint / Alchemy hostname | **HIGH** | env, API, httpx |
| 327 failover err taxonomy | **HIGH** | exact log uniq counts |
| Docker fp `5e5d5bb1` vs effective `ce00e63d` | **HIGH** | sha256[:8] on URL path + Network Config API + env_sync timestamp alignment |
| Alchemy reached | **HIGH** | 38 httpx POSTs |
| 429 = throughput/provider RL vs monthly quota | **MEDIUM** | status text only; capacity body absent |
| Exact JSON-RPC payload class of each of 13×200 | **MEDIUM / LIMITED** | no response bodies in logs |
| `fallback:revert` meaning | **HIGH** | tip `befb14e` source |

---

## Absolute bans observed

No restart, deploy, rebuild, RPC config change, campaign alteration, or credential/env modification was performed. Evidence only.
