# Alchemy CU Observation (READ ONLY) — Gate9 SHADOW

- Status: **OBSERVATION ONLY** — campaign / config / containers / providers / source **untouched**
- Date: 2026-10-02
- Container: `arbicore-x-backend-new` (`arbicore-x-backend:g5.79-green-20260927`)
- Campaign start: `2026-10-02T06:19:43Z` (Gate9 = 24h)
- Observation window end: `2026-10-02T08:27:31Z` (~2.13h elapsed; ~21.87h remaining)
- Machine JSON: `reports/shadow_validation/alchemy_cu_observation_20261002T082731Z.json`
- Latest pointer: `reports/shadow_validation/alchemy_cu_observation_latest.json`
- Key path fingerprint (sha256[:8] of API-key path segment only): **`5e5d5bb1`** (matches post-alchemy-reset evidence; no secrets printed)

---

## 1. Configured Alchemy RPC domains (env)

| Env var | Domain | Alchemy? | key path_fp |
|---|---|---|---|
| `ARBICORE_RPC_URL` | `base-mainnet.g.alchemy.com` | yes | `5e5d5bb1` |
| `ARBICORE_ARCHIVE_RPC_URL` | `base-mainnet.g.alchemy.com` | yes | `5e5d5bb1` |
| `ARBICORE_RPC_URL_ETHEREUM` | `eth-mainnet.g.alchemy.com` | yes | `5e5d5bb1` |
| `ARBICORE_RPC_URL_ARBITRUM` | `arb-mainnet.g.alchemy.com` | yes | `5e5d5bb1` |
| `ARBICORE_RPC_URL_OPTIMISM` | `opt-mainnet.g.alchemy.com` | yes | `5e5d5bb1` |
| `ARBICORE_RPC_URL_POLYGON` | `polygon-mainnet.g.alchemy.com` | yes | `5e5d5bb1` |
| `ARBICORE_RPC_URL_BNB` | `bnb-mainnet.g.alchemy.com` | yes | `5e5d5bb1` |
| `ARBICORE_RPC_URL_BASE` | `mainnet.base.org` | **no** | n/a (no path) |

Same key material across five Alchemy L1/L2 URLs + Base Alchemy archive/primary (`ARBICORE_RPC_URL`).

---

## 2. Metrics / log sources inspected (non-invasive)

| Source | Result |
|---|---|
| Prometheus `/metrics` on `:8001` | **404** — no Prometheus scrape endpoint |
| `/api/arbicore/observability` | Available; provider registry present |
| `/api/arbicore/providers/status` | Available; Base public RPC DEGRADED; Base Alchemy TRIPPED early |
| `/api/arbicore/certification/shadow/current` | Auth required — not probed further |
| Docker logs since campaign start | Primary evidence (`httpx` INFO + `quoter` + `providers.registry`) |
| `LOG_LEVEL` | `WARNING` (method names mostly absent except WARNING/INFO paths) |

**Provider registry (Base only, early window):**

- `rpc_base_0_mainnet_base_org`: DEGRADED — `eth_call -> 429` (successes=14, failures=10; last ~06:20Z)
- `rpc_base_1_base-mainnet_g_alchemy_c`: TRIPPED — `eth_call -> 429` (successes=0, failures=5; circuit open ~06:21Z)
- Other Alchemy chain registry rows: successes=0 / failures=0 (idle in registry counters)

**Note:** `httpx` INFO lines log full RPC URLs including path secrets. Operators should treat container logs as sensitive; this evidence file redacts all keys.

---

## 3. Alchemy public CU method weights (reference)

From Alchemy public compute-unit costs table (`https://www.alchemy.com/docs/reference/compute-unit-costs`). Live WebFetch was unavailable to this observation agent — confirm against current docs if billing-critical.

| Method | CU / call (published) |
|---|---|
| `eth_blockNumber` | 10 |
| `eth_chainId` | 10 |
| `eth_call` | 26 |
| `eth_getLogs` | 75 |
| `debug_traceCall` / `debug_traceTransaction` | 309 |

App quoter path (`arbicore.execution.quoter`): read-only **`eth_call`**, optionally batched/paired with **`eth_blockNumber`**; retries on `-32016` / HTTP 429 (default max retries=4).

---

## 4. Successful vs 429 / rejected (Alchemy)

**httpx POST volume in observation window (Base Alchemy only):**

| Host | HTTP requests | HTTP 200 | HTTP 429 |
|---|---:|---:|---:|
| `base-mainnet.g.alchemy.com` | **2306** | **4** | **2294** (~99.8%) |
| Other Alchemy chains (eth/arb/op/poly/bnb) | **0** | 0 | 0 |

**Non-Alchemy (for context, not CU):** `mainnet.base.org` ≈ 2457 POSTs, ≈2347×200 / ≈94×429 — primary successful quoter path.

**Quoter:** ≥455 `over rate limit` (`code=-32016`) on `mainnet.base.org` → failover to Base Alchemy (then mostly Alchemy HTTP 429).

**Method-name log counts (string matches since campaign start):** `eth_call`=15 (all early registry WARNING), `eth_getLogs`/`eth_blockNumber`/`eth_chainId`/`debug_trace`/`eth_subscribe` = **0**.

**Classification:** Ongoing Alchemy 429s behave like **throughput / concurrent rate limits** on Base Alchemy under quoter failover pressure — distinct from the earlier monthly-capacity exhaustion class that was cleared on key fp `5e5d5bb1` (see M6 post-alchemy evidence). Exact CU billing of rejected 429s is Alchemy-side; scenarios below bound both interpretations.

---

## 5. Highest-CU methods

| Rank | Method | Evidence in this window |
|---|---|---|
| 1 | **`eth_call`** | Dominant; quoter + early registry; nearly all Alchemy Base POSTs |
| 2 | `eth_blockNumber` (possible companion) | Not named in logs; quoter may batch/pair it |
| — | `eth_getLogs` | **Not observed** in campaign logs (historical Free-tier range limits remain a separate issue) |
| — | `debug` / `trace` | **Not observed** |

---

## 6. CU rate estimates

Observation span ≈ **2.13h**. Remaining Gate9 ≈ **21.87h**. Monthly = rate × 24 × 30.

| Scenario | Assumption | CU/h | CU remaining Gate9 | CU / 24h Gate9 | CU / month | vs 30M Free |
|---|---|---:|---:|---:|---:|---|
| **A** | Only HTTP **200** billed as `eth_call` (26 CU) | ~49 | ~1.1k | ~1.2k | ~35k | **0.1%** — fine |
| **B** | All Alchemy attempts billed as `eth_call` | ~28.1k | ~616k | ~676k | ~20.3M | **~68%** — under 30M, little headroom |
| **C** | All attempts billed as `eth_call`+`eth_blockNumber` (36 CU) | ~39.0k | ~852k | ~935k | ~28.1M | **~94%** — at risk |

**Best current reading:** Scenario **A** if throughput 429s are not CU-billed; **B/C** as upper bounds if Alchemy charges attempts before reject. Dashboard CU remaining is authoritative — not available from this read-only container view.

---

## 7. Is Free-tier 30M CU/month sufficient?

- **For remaining Gate9 alone:** yes under all scenarios (even C ≪ 30M for ~22h).
- **Sustained monthly at this attempt rate:**  
  - If 429s **not** billed → **yes** (trivial).  
  - If attempts **are** billed as `eth_call` → **marginal yes** (~20M/mo).  
  - If billed as call+blockNumber → **at risk** (~28M/mo).  
- Multi-chain `eth_getLogs` / simulation-trace activity (not seen here) would consume additional CU quickly (75 / 309 CU each).

---

## 8. Disproportionate consumer

**Base Alchemy `eth_call` driven by quoter failover** from public `mainnet.base.org` rate limits, amplified by retries. Almost every Alchemy Base POST is **HTTP 429**; only **4** successes in ~2.13h. Other Alchemy chains idle in httpx logs. `eth_getLogs` / trace are **not** the current CU burn in this Gate9 window.

---

## STOP

No SHADOW restart, config change, container change, provider change, source edit, or production action performed.
