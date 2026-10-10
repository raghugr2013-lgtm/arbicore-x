# R4-SCRUB Phase A — Quarantine execution report

**Verdict: PASS**  
**Authorisation:** R4-SCRUB Phase A only (quarantine · no shred · no Phase B)  
**Evidence dir:** `artifacts/security/r4_scrub_phase_a_20261010T122730Z/`  
**Quarantine:** `/home/raghu/arbicore_backups/r4_scrub_quarantine_20261010T122730Z/` (`0700`)  
**Hold until (UTC):** `2026-10-24T12:29:00Z` (≥ 14 days)  
**Destroy / Phase B:** **NOT DONE** — require separate authorisation  

**R4 live rotation verdict (unchanged):** **PASS WITH LIMITATIONS**  
**Overall security gate / P2:** **BLOCKED**

---

## Timeline (UTC)

| Time | Event |
|---|---|
| `12:28:59Z`–`12:29:00Z` | Target-by-target precheck of exact 17 reviewed paths — **PASS** |
| `12:29:00Z` | `mv` 8 local + 9 `/tmp` into quarantine; per-file sha256 + secret sha12 integrity — **PASS** |
| `12:29:06Z` | Post checks S1–S6 — **PASS** |
| `12:29:13Z` | Duplicate invocation aborted (sources already absent) — no-op; see [`DUPLICATE_RUN_NOTE.json`](DUPLICATE_RUN_NOTE.json) |

---

## Precheck gates

| Gate | Result |
|---|---|
| Exact set equals preflight `scrub_candidates` (17) | **PASS** |
| No overlap with live `.env`, running ENV, approved recovery (12), R4 escrow | **PASS** |
| Each target regular file; generation admin `6780d7b21193` / JWT `7013ef842946` | **PASS** |
| Live already on new secrets `112c88ac69e1` / `f98650d468b2`; digest healthy | **PASS** |

---

## Moves completed (17)

Quarantine layout: `local_upgrade_backups/` (8) · `tmp_ephemeral/` (9). Dest mode `0600`. Full map: [`move_map.json`](move_map.json).

### Local upgrade backups (8)

| Source (basename) | Dest sha256 (prefix) | Admin/JWT sha12 |
|---|---|---|
| `.env.pre-m25-usd-numeraire-20260912T121226Z` | `f657fe532b8bc981…` | `6780d7b21193` / `7013ef842946` |
| `.env.g5.27-backup-20260927-101642` | `82990251962eccb7…` | same |
| `.env.pre-paper-20260916T112833Z` | `56b4f9ce658d751b…` | same |
| `.env.backup.20261002-081704` | `53cd026f00262efd…` | same |
| `.env.g5.62-backup-20260927-105923` | `e59572655b338f0f…` | same |
| `.env.bak-20260916-133913` | `c48cf417398243ae…` | same |
| `.env.pre-executor-owner-refresh-20260912T100117Z` | `c9b3e3adc8c380f6…` | same |
| `.env.pre-t2-wss-20260911T160217Z` | `8d68426c74397a6d…` | same |

Sources under `/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/` — **all absent** after move.

### `/tmp` ephemeral (9)

| Source | Dest sha256 (prefix) |
|---|---|
| `/tmp/arbicore_ctr_all.env` | `3f9acf9fce19a3d4…` |
| `/tmp/arbicore-runtime-cert-ad64a50.env` | `5f6fc8d2f4fb2c6a…` |
| `/tmp/arbicore-x-backend.env` | `35fdc396a4bdb62d…` |
| `/tmp/arbicore-runtime-cert.env` | `543ac228561880ef…` |
| `/tmp/arbicore-x-candidate.env` | `c8aa06d21925a775…` |
| `/tmp/arbicore-backend-p0-3.env` | `c26ca39d10cb7653…` |
| `/tmp/arbicore-backend.env` | `0c677850b5c0c1c2…` |
| `/tmp/arbicore-x-runtime.env` | `192bdab7fa57298b…` |
| `/tmp/arbicore-production-env.backup` | `fc81a2c88a513327…` |

All carry admin/JWT sha12 `6780d7b21193` / `7013ef842946`. Sources **absent** after move.

---

## Verification

| ID | Check | Result |
|---|---|---|
| S1 | Live `.env` + container ENV new sha12s; digest `69fe2459…`; healthy; old fingerprints absent from active runtime | **PASS** |
| S2 | All 17 sources absent; all 17 destinations present | **PASS** |
| S3 | 12 approved recovery paths still present | **PASS** |
| S4 | Four legacy containers still **exited** (not started/removed) | **PASS** |
| S5 | R1 `/docs` 404 · R2 setup 503 · `/api/` 200 | **PASS** |
| S6 | SHADOW · AUTOEXEC/RUNTIME false · no BOOTSTRAP · no private-key ENV · `arbicore_app` | **PASS** |
| Integrity re-verify | Per-file sha256 + secret sha12 vs `move_map` | **PASS** ([`integrity_reverify.json`](integrity_reverify.json)) |

**Untouched:** g5.79 app running · Foreman mongo running · live `.env` · running ENV · R4 escrow · approved recovery · no shred.

---

## Restoration (before destroy only)

```bash
artifacts/security/r4_scrub_phase_a_20261010T122730Z/restore_from_quarantine.sh
```

Reverses `move_map.json` destinations → original sources via `mv`. Valid only while quarantine contents exist and destroy has not been authorised.

---

## Retention / next authorisations

| Item | Status |
|---|---|
| Quarantine hold | **Active** until ≥ `2026-10-24T12:29:00Z` |
| Permanent shred/destroy of quarantine | **Blocked** — needs separate auth after hold |
| Phase B (`docker rm` 4 legacy) | **Blocked** — not authorised |
| Optional `/tmp` files without admin/JWT | **Not touched** |

---

## Out of scope (confirmed not modified)

Live `.env` · running container ENV · 12 approved recovery items · 4 stopped legacy containers · R5 keys · R6 provider credentials · RPC/network config · strategy/P2 · g5.79/Foreman.

**Stopped after Phase A — awaiting review. No destroy, Phase B, R5, R6, or P2.**
