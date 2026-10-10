# FINAL Alchemy Identity Verification (READ ONLY) — 2026-10-02

- Status: **READ ONLY** — SHADOW / config / containers / RPC / PAYG **untouched**
- Container: `arbicore-x-backend-new`
- Target wired fingerprint: `sha256(key_path_segment)[:8] = 5e5d5bb1`
- Verdict: **IDENTITY UNVERIFIABLE**

---

## Verdict

**IDENTITY UNVERIFIABLE**

Browser dashboard app/key cannot be seen from the server. No operator-supplied dashboard fingerprint-only file was present (checked `/tmp/alchemy_dashboard_key_fp` and similar paths). Request-count discrepancy (dashboard 445 vs server Alchemy ~3k) is **not** used to declare MATCHED or NOT MATCHED.

---

## 1. Server-side fingerprints (no keys printed)

| Env var | Host | Alchemy? | key_len | fp8 |
|---|---|---|---:|---|
| `ARBICORE_RPC_URL` | `base-mainnet.g.alchemy.com` | yes | 26 | **5e5d5bb1** |
| `ARBICORE_ARCHIVE_RPC_URL` | `base-mainnet.g.alchemy.com` | yes | 26 | **5e5d5bb1** |
| `ARBICORE_RPC_URL_ETHEREUM` | `eth-mainnet.g.alchemy.com` | yes | 26 | **5e5d5bb1** |
| `ARBICORE_RPC_URL_ARBITRUM` | `arb-mainnet.g.alchemy.com` | yes | 26 | **5e5d5bb1** |
| `ARBICORE_RPC_URL_OPTIMISM` | `opt-mainnet.g.alchemy.com` | yes | 26 | **5e5d5bb1** |
| `ARBICORE_RPC_URL_POLYGON` | `polygon-mainnet.g.alchemy.com` | yes | 26 | **5e5d5bb1** |
| `ARBICORE_RPC_URL_BNB` | `bnb-mainnet.g.alchemy.com` | yes | 26 | **5e5d5bb1** |
| `ARBICORE_RPC_URL_BASE` | `mainnet.base.org` | no | 0 | n/a |
| `ALCHEMY_API_KEY` | — | — | — | EMPTY / unset |

Unique Alchemy fp: **`5e5d5bb1`** (confirmed). Local `/tmp/arbicore-alchemy-key` (bare key material) also fingerprints to **`5e5d5bb1`**.

---

## 2. Non-secret Alchemy response metadata

| Source | Result |
|---|---|
| Docker logs | httpx status lines only; **no** `x-alchemy-*` headers, **no** app id JSON |
| One redacted probe (`eth_chainId` via wired `ARBICORE_RPC_URL`) | HTTP **200**; headers: `server=istio-envoy`, `x-alchemy-trace-id=<uuid>`, `content-type=application/json`; body result `0x2105` (Base). **No app id / network billing id** |
| Alchemy usage/admin API via RPC key | **Not documented / not available** in this workspace without dashboard JWT — not invented |

Trace IDs are per-request; they do **not** identify the dashboard app for operator comparison.

---

## 3. Operator dashboard fingerprint file

| Path | Present? |
|---|---|
| `/tmp/alchemy_dashboard_key_fp` | **MISSING** |
| `/tmp/alchemy_dashboard_fp` | **MISSING** |
| `/tmp/alchemy_key_fp` | **MISSING** |
| workspace `**/alchemy_dashboard_key_fp` | **MISSING** |

Without an 8-hex dashboard fp (or operator confirmation), browser identity cannot be proven.

**Operator compare instruction:** In the Alchemy dashboard app you are viewing, take the API key path segment (the string after `/v2/`), compute `sha256(key)[:8]` locally, and check whether it equals **`5e5d5bb1`**. Also note the dashboard **app name** and **network** (expect Base / `base-mainnet`). Optionally write only the 8-hex fp to `/tmp/alchemy_dashboard_key_fp` for a future MATCHED/NOT MATCHED close-out.

---

## 4. Actual Alchemy request counts

Prior recon (~08:53Z window): base.org **2926**; Alchemy base **2729** (4×200, 2725×429); other Alchemy chains **0**; operator dashboard claimed **445**.

**Log refresh (this verification, ~09:10Z UTC; logs since ~06:19:40):**

| Host | Total | 200 | 429 | other |
|---|---:|---:|---:|---:|
| `base-mainnet.g.alchemy.com` | **3051** | **10** | **3040** | 1×400 |
| other `*.alchemy.com` | **0** | 0 | 0 | 0 |
| `mainnet.base.org` (not Alchemy) | **3251** | 3156 | 94 | 1×502 |

Counts grow while SHADOW runs; snapshot is live totals since container start.

---

## 5. CU usage / 429 accounting

| Question | Answer |
|---|---|
| Actual CU from server metrics | **unavailable** (no Prometheus CU; logs have no CU counters) |
| Success-only floor (if ~10×200 were `eth_call` @ 26 CU) | **≤260 CU** estimate — not measured |
| Do 429s appear in CU accounting? | **Unknown from server.** They **did reach Alchemy** (real HTTP 429). Whether Free-tier CU meters them is Alchemy-side policy; dashboard CU is only meaningful after key identity match |
| Dashboard 0 CU/s vs live 429 storm | Supports wrong-app **or** 429s-not-CUed — **not** cryptographic proof either way |

---

## 6. Can PAYG be decided safely?

**No.** Identity of the viewed dashboard app vs wired fp `5e5d5bb1` is **UNVERIFIABLE**. Do **not** purchase PAYG from dashboard 445 / 0 CU/s alone, and do **not** infer monthly CU exhaustion solely from ~3k Alchemy 429s without matched-app CU remaining.

After operator confirms dashboard key fp = `5e5d5bb1`, re-read that app’s CU remaining and throughput-limited % before any PAYG decision.

---

## Report card

| Field | Value |
|---|---|
| **Identity** | **IDENTITY UNVERIFIABLE** |
| Dashboard app identity | **UNVERIFIABLE** (no browser access; no fp file) |
| Wired key fingerprint | **5e5d5bb1** |
| Actual Alchemy request count | **3051** Base (`10`×200, `3040`×429, `1`×400); other chains **0** |
| Actual CU usage | **unavailable** (server); success floor estimate ≤260 CU if eth_call |
| 429 in CU accounting? | **Unknown** (requests reached Alchemy; CU metering unproven) |
| PAYG decision safe? | **No** |

---

## STOP

No SHADOW interrupt/restart, no RPC config change, no PAYG purchase, no API keys printed.
