# Alchemy Dashboard Reconciliation (READ ONLY) — 2026-10-02

- Status: **READ ONLY** — SHADOW / source / config / providers / containers **untouched**; **no PAYG purchase**
- Container: `arbicore-x-backend-new` (StartedAt `2026-10-02T06:19:33Z`, running)
- Campaign / log window: `2026-10-02T06:19:43Z` → `2026-10-02T08:53:22Z` (~**2.56h**; container has no earlier logs)
- Wired key path fingerprint: **`sha256[:8]=5e5d5bb1`** (API-key path segment only; credential never printed)
- Operator dashboard (claimed for this Alchemy app): 445 req / 24h · 0 avg CU/s / 5m · 95.2% success / 1h · 86.5% success / 24h · 1 invalid · 0% throughput limited

---

## 1. Dashboard app/key vs wired fp `5e5d5bb1`

| Check | Result |
|---|---|
| Server: `ARBICORE_RPC_URL` / `ARBICORE_ARCHIVE_RPC_URL` host | `base-mainnet.g.alchemy.com` |
| Server: path-segment fp on Base Alchemy + eth/arb/op/poly/bnb Alchemy URLs | **`5e5d5bb1`** (all match) |
| Server: `ARBICORE_RPC_URL_BASE` | `mainnet.base.org` (not Alchemy; no key path) |
| Server: `ALCHEMY_API_KEY` env | unset/empty (key only embedded in RPC URL paths) |
| Dashboard UI key / app id | **Not visible from server** |

**Can verify from server:** wired RPC URLs use Alchemy host + path fp `5e5d5bb1`.

**Cannot verify from server:** that the operator’s open Alchemy dashboard app/key is the same material as fp `5e5d5bb1`. **Operator must confirm** dashboard key fingerprint matches `5e5d5bb1`.

---

## 2. Were the ~2294 429s from `mainnet.base.org` or Alchemy?

**Alchemy.** Re-inspected `httpx` INFO lines (`HTTP Request: POST https://<host>/... "HTTP/1.1 <status>"`). Classification is by **URL host** (equivalent to Host for these POSTs).

| Host | Role | HTTP total (this window) | 200 | 429 | other |
|---|---|---:|---:|---:|---:|
| `mainnet.base.org` | public Base RPC | **2926** | 2831 | **94** | 502×1 |
| `base-mainnet.g.alchemy.com` | wired Base Alchemy | **2729** | **4** | **2725** | 0 |
| other `*.alchemy.com` | eth/arb/op/poly/bnb | **0** | 0 | 0 | 0 |

Prior observation (~2294 Alchemy 429 over ~2.13h) is the same stream; count grew to **2725** Alchemy 429 by ~08:53Z (~2.56h). Public `base.org` contributes only **94** 429s in the whole window.

Sample (redacted):  
`POST https://base-mainnet.g.alchemy.com/v2/<REDACTED> "HTTP/1.1 429 Too Many Requests"`

---

## 3. Actual requests that reached Alchemy (by host)

| Alchemy host | Requests | Successful (200) | 429 |
|---|---:|---:|---:|
| `base-mainnet.g.alchemy.com` | **2729** | **4** | **2725** |
| All other Alchemy hosts | **0** | 0 | 0 |

**Public RPC (not Alchemy):** `mainnet.base.org` = **2926** (2831×200).

Quoter path: frequent failover `mainnet.base.org` → `base-mainnet.g.alchemy.com` after public `-32016 over rate limit` (543 log hits), then Alchemy returns HTTP 429.

---

## 4. Reconciliation vs dashboard **445** requests / 24h

| Signal | Dashboard | Server logs (wired fp) |
|---|---|---|
| Window | last **24h** | **~2.56h** only (container start) |
| Request count | **445** | **2729** Alchemy POSTs in 2.56h alone |
| Success last hour | **95.2%** | Alchemy last hour: **0.1%** (1/1031); public Base last hour: **100%** |
| Throughput limited | **0%** | Continuous Alchemy **429** (~80 in last 5m) |
| Invalid | 1 | not separately labeled in httpx |

**Discrepancy is not explained by “log sample vs full day” in the direction that helps the dashboard:** the short post-start window already exceeds 445 Alchemy hits by **~6×**, and last-hour success on Alchemy is incompatible with 95.2%.

Most plausible explanations (ordered):

1. **Wrong Alchemy app/key on the dashboard** relative to wired fp `5e5d5bb1` (operator confirmation required). Dashboard 0% throughput-limited vs live Alchemy 429 storm is the strongest contradiction.
2. **Metric definition gap** (e.g. dashboard “requests” / “throughput limited” not counting the same events as client-visible HTTP 429) — possible but **cannot alone** reconcile 445 vs 2729 if the same key is billed/shown.
3. **Not** “retries uncounted on server”: each httpx POST is a separate outbound attempt; retries **are** counted in log totals.
4. **Not** mis-attribution of public RPC as Alchemy: hosts are distinct in logs.

Until the operator confirms dashboard key = `5e5d5bb1`, treat **445 as unverified for this runtime**.

---

## 5. Are the 429s billable Alchemy requests or public-RPC failures?

| Class | Host | Count | Billable Alchemy? |
|---|---|---:|---|
| Public RPC 429 | `mainnet.base.org` | 94 | **No** (not Alchemy) |
| Alchemy HTTP 429 | `base-mainnet.g.alchemy.com` | **2725** | **Yes, they reached Alchemy** (real POSTs to Alchemy). Whether they consume **CU** is Alchemy-side policy — **not proven from logs**. |

No response-body strings such as `Monthly capacity limit exceeded` / `throughput` / `scaling policy` appear in this campaign’s non-httpx logs (httpx only records status lines). So capacity-vs-throughput **message class is not re-derived here**; behavior is consistent with sustained Alchemy reject-on-429 under failover load.

Dashboard **0 avg CU/s last 5m** alongside ~80 Alchemy 429s in last 5m (if same app) would imply **429s are not CU-consuming** — but that inference is only valid after key match is confirmed.

---

## 6. Actual Alchemy CU (from logs/metrics)

| Source | CU |
|---|---|
| Prometheus `/metrics` | **404** — unavailable |
| Container logs | **No CU counters** |
| Method names in campaign logs | Almost absent (`LOG_LEVEL=WARNING`); early registry shows `eth_call` failures |
| Dashboard (operator) | 0 avg CU/s last 5m — **not independently verified** |

**Actual CU from server evidence: unknown / not available.**

**Floor only if** the 4 HTTP 200s were single `eth_call` each at published 26 CU: **≤104 CU** in-window — **estimate, not measured**. Do **not** treat 2725×429 as proven CU burn. **No monthly cost estimated from 2294/2725.**

---

## 7. Report totals (this reconciliation)

| Metric | Value |
|---|---:|
| Public RPC requests (`mainnet.base.org`) | **2926** |
| Actual Alchemy requests (`base-mainnet.g.alchemy.com`) | **2729** |
| Successful Alchemy requests (HTTP 200) | **4** |
| Alchemy HTTP 429s | **2725** |
| Other Alchemy-chain requests | **0** |
| Actual CU (logs/metrics) | **unavailable** |
| Estimated CU (success-only eth_call floor) | **≤104** (unverified method) |
| Dashboard 445 reconciliation | **Does not match** wired-key log volume or success rates |

---

## 8. Conclusion — is PAYG currently necessary?

### **UNCLEAR**

**Reason:**

1. Server proves heavy **Alchemy-host** 429 traffic on wired fp `5e5d5bb1`, but the operator dashboard (445 / 95.2% / 0% throughput limited / 0 CU/s) **does not reconcile** with that traffic — so either the dashboard is a **different app/key**, or dashboard counters omit most of these attempts. Operator must confirm key match.
2. **Monthly CU PAYG** is **not supported by dashboard numbers** (low request count, 0 CU/s) **if** that dashboard is the wired key — but that “if” is unverified and contradicted by log volume.
3. Base SHADOW quoting is currently carried by **public `mainnet.base.org` successes**; Alchemy Base is effectively unusable as failover (≃99.9% 429). That is a **throughput/availability** problem on Alchemy Base, distinct from proven monthly CU exhaustion in this window — and **does not by itself prove PAYG is required** without confirmed billing/CU from the matching app.

**Do not buy PAYG from this report.** Confirm dashboard key fp = `5e5d5bb1`, then re-read CU remaining / throughput-limited % on that app.

---

## STOP

No SHADOW restart, config/source/provider change, container change, or PAYG purchase performed.
