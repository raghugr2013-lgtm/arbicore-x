# POST-PAYG 1h SHADOW Smoke Validation — 2026-10-03

> **READ-ONLY** — No config change / APPLY / restart / recreate / deploy / source modification.
> **NOT** official Gate 9 / Gate 10. SHADOW only; AUTOEXEC/RUNTIME remain OFF.

- **Verdict:** **HEALTHY**
- **Window:** T0=APPLY `2026-10-03T04:57:17Z` → T1=`2026-10-03T05:57:17Z` (exactly **1 hour**)
- **Collected at (UTC):** `2026-10-03T06:08:47.390297+00:00` (~11.5 min past T1)
- **Container:** `arbicore-x-backend-new` · Image `arbicore-x-backend:ws-a-befb14e-20261002`
- **Prior APPLY verify:** `ALCHEMY_PAYG_POST_APPLY_VERIFICATION_20261003.md` (APPLY confirmed `2026-10-03T04:57:17Z`)
- **12h POST-FIX baseline:** `POST_FIX_12H_SHADOW_VALIDATION_REPORT_20261002.md`
- **Machine evidence:** `reports/shadow_validation/post_payg_1h_smoke_20261003T060847Z.json`
- **API raw:** `reports/shadow_validation/post_payg_1h_smoke_api_raw_20261003T060847Z.json`
- **Latest pointer:** `reports/shadow_validation/post_payg_1h_smoke_latest.json`
- **Secrets:** Alchemy keys redacted; fingerprints = `sha256(/v2/key)[:8]`

---

## Executive summary

| Layer | Result | Why |
|---|---|---|
| RPC / Alchemy PAYG infra | **PASS** | fp `cd505118` · Alchemy **1527×200 / 0×429 / 0×400** · stale `ce00e63d` **ABSENT** · chainId **8453** |
| Product-fix (amplification/cooldown) | **N/A (0 failovers) — no ~5× sample** | Failovers=**0**; cooldown=**0** |
| Safety | **HELD** | SHADOW; AUTOEXEC/RUNTIME OFF; kill engaged=True; live_execution=False |
| Continuity | **PASS** | RestartCount=**0**; StartedAt=`2026-10-02T15:08:52.884157323Z` |
| Economic / opportunities | **ABSENT** | opportunities=0; EXECUTABLE=0; status=ok=0 — **not** treated as infrastructure failure |

**Overall: HEALTHY** — PAYG primary healthy with sustained HTTP 200s; stale key absent; no failover/amplification recurrence; safety held; zero opportunities is market/economic, not RPC failure.

---

## Window identity

| Field | Value |
|---|---|
| T0 (APPLY) | `2026-10-03T04:57:17Z` |
| T1 (smoke end) | `2026-10-03T05:57:17Z` |
| Collect | `2026-10-03T06:08:47.390297+00:00` |
| Log first/last in window | `2026-10-03T04:57:17.902000+00:00` → `2026-10-03T05:57:06.563000+00:00` |
| env_sync in window | **1** (APPLY-triggered; no later overwrite) |
| Network Config updated_at | `2026-10-03T04:57:17.836236+00:00` |
| revision_id | `rev-7c93bb93e65b4f5a9b7340bf513437c0` |
| NC `rpc_urls.base` (redacted) | `['https://base-mainnet.g.alchemy.com/v2/<REDACTED:fp=cd505118>', 'https://mainnet.base.org/']` |

---

## Metrics 1–17 (APPLY → APPLY+1h only)

| # | Metric | Value |
|---:|---|---|
| 1 | Successful RPC calls (HTTP 200 Alchemy + public Base) | **1527** |
| 2 | Alchemy HTTP 200 / 429 / 400 | **1527 / 0 / 0** (total=1527) |
| 3 | Base public-RPC calls (`mainnet.base.org`) | **0** (none — traffic on Alchemy primary) |
| 4 | Failovers | **0** base→Alchemy (total events=0) |
| 5 | Cooldown activations | **0** |
| 6 | Alchemy requests / failover (amplification) | **N/A — 0 failovers (Alchemy primary; no failover-path amplification sample)** |
| 7 | Quote attempts | status=ok=0; fallback:revert=0; failover proxy=0 |
| 8 | Successful quotes `status=ok` | **0** |
| 9 | `fallback:revert` count | **0** |
| 10 | Opportunities detected | **0** |
| 11 | EXECUTABLE opportunities | **0** |
| 12 | Paper evidence | report.total=0; paper.analyses=0; evidence.total=0 |
| 13 | Exceptions | runner=0; tracebacks=0; ERROR lines=0 |
| 14 | Container restarts | RestartCount=**0**; StartedAt=`2026-10-02T15:08:52.884157323Z` (unchanged vs cutover) |
| 15 | `cd505118` effective | **YES** · NC primary=`cd505118` · log posts=`{'cd505118': 1527}` · rpc/check=`base-mainnet.g.alchemy.com` |
| 16 | `ce00e63d` absent | **YES — ABSENT** |
| 17 | env_sync no overwrite | **YES** · env_sync count=1; primary still PAYG |

### Alchemy by fingerprint (window)

| fp8 | posts | status mix |
|---|---:|---|
| `cd505118` | 1527 | {'200': 1527} |

---

## vs 12h POST-FIX campaign

| Metric | 12h POST-FIX (pre-PAYG) | 1h post-PAYG smoke | Δ |
|---|---:|---:|---|
| Alchemy HTTP 200 | 13 (boot `5e5d5bb1` only) | **1527** (`cd505118`) | Sustained primary success |
| Alchemy HTTP 429 | **996** (all `ce00e63d`) | **0** | Storm cleared |
| Dominant Alchemy fp | `ce00e63d` (stale) | **`cd505118`** | PAYG live |
| Stale `ce00e63d` | PRESENT | **ABSENT** | Eliminated |
| Failovers | 15,059 | **0** | Collapsed (Alchemy primary) |
| Cooldown | 14,591 | **0** | Idle |
| Amplification median (3s) | 2.0 | **N/A (0 failovers)** | No ~5× return |
| `status=ok` quotes | 0 | **0** | Still 0 |
| Opportunities / EXECUTABLE | 0 / 0 | **0 / 0** | Still absent (economic) |
| Overall | CONDITIONAL (RPC BLOCKED_OBSERVED) | **HEALTHY** | Infra unblocked |

**Interpretation:** The 12h campaign’s Alchemy 429 storm on stale `ce00e63d` is gone. PAYG primary `cd505118` serves Base with sustained HTTP 200s and **zero** 429s in the smoke hour. Zero opportunities / zero `status=ok` remain **economic/market**, not RPC-identity failure.

---

## Safety posture

| Control | Observed |
|---|---|
| `ARBICORE_EXECUTION_MODE` | `SHADOW` |
| `ARBICORE_SHADOW_CERT_ENABLED` | `true` |
| `ARBICORE_AUTOEXEC_AUTOSTART` | `false` |
| `ARBICORE_RUNTIME_AUTOSTART` | `false` |
| `live_execution_enabled` | `False` |
| Kill `effective_kill_engaged` | `True` (reason=`boot_default`) |
| RestartCount | `0` |
| Safety held | **True** |

---

## rpc/check

| Field | Value |
|---|---|
| status | `READY` |
| chain_id | `8453` |
| block_number | `52109191` |
| rpc_url_masked | `base-mainnet.g.alchemy.com` |
| is_base_mainnet | `True` |

---

## Verdict rules applied

| Rule | Result |
|---|---|
| BLOCKED triggers | none |
| CONDITIONAL triggers | none |
| HEALTHY criteria (PAYG works, stale absent, amp bounded/N/A, safety held; opps may be 0) | MET |

**Final verdict: HEALTHY**

---

## Absolute bans compliance

| Ban | Observed |
|---|---|
| No config change / APPLY / restart / recreate / deploy | **Held** |
| No AUTOEXEC / RUNTIME / live enable | **Held** |
| No source modification | **Held** |
| Secrets redacted (fp8 only) | **Held** |
