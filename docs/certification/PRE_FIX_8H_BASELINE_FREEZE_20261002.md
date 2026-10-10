# PRE-FIX 8h Baseline Freeze — 2026-10-02

- **Freeze stamp (UTC):** `2026-10-02T14:44:46Z`
- **Kind:** Clean **PRE-FIX** baseline freeze for accelerated 8h SHADOW confidence
- **Posture:** READ-ONLY vs Gate9 / campaign / production — **no deploy, restart, rebuild, recreate, or runtime/env change**
- **Workspace:** `/home/raghu/projects/arbicore-x-cert`
- **Hash inventory sidecar (metrics untouched):** `reports/shadow_validation/accel_8h_checkpoint_20261002T142017Z.FREEZE_HASH_INVENTORY.json`

---

## 1. Operator-stated 8h checkpoint (verified against artifacts — not invented)

| Field | Operator-stated | Recorded evidence |
|---|---|---|
| Verdict | HEALTHY WITH OBSERVATIONS | MD + JSON `health_status` = **HEALTHY WITH OBSERVATIONS** |
| Runner elapsed | ~8.01h | JSON `campaign.elapsed_hours` = **8.0095** |
| Cycles | 5,740 | **5740** |
| Exceptions | 0 | **0** |
| Restart count | 0 | **0** (container + campaign) |
| Opportunities | 0 | `opportunities_seen` / `processed` = **0 / 0** |
| Paper evidence | 0 | pulse `total=0`; EXECUTABLE=0; paper_pnl=0 |
| Image | g5.79-green-20260927 | `arbicore-x-backend:g5.79-green-20260927` |
| SHADOW / AUTOEXEC / RUNTIME | ON / OFF / OFF | `ARBICORE_EXECUTION_MODE=SHADOW`; `*_AUTOSTART=false` |

**Binding narrative:** `docs/certification/SHADOW_ACCELERATED_8H_CHECKPOINT_20261002.md`  
**Machine evidence:** `reports/shadow_validation/accel_8h_checkpoint_20261002T142017Z.json`  
**API raw:** `reports/shadow_validation/accel_8h_checkpoint_api_raw_20261002T142017Z.json`  
**Latest pointer:** `accel_8h_checkpoint_latest.json` **byte-identical** to timestamped JSON (`cmp` YES).

Checkpoint content was **not rewritten** for this freeze (no metric edits). Only this freeze record + hash inventory sidecar were added.

---

## 2. Final evidence / artifact SHA256 inventory

| Artifact | SHA256 |
|---|---|
| `docs/certification/SHADOW_ACCELERATED_8H_CHECKPOINT_20261002.md` | `42305fa1e4e0bf60d29243917ea2b5a800bf0af85e39400bf88f63958879dab7` |
| `reports/shadow_validation/accel_8h_checkpoint_20261002T142017Z.json` | `021c5ece36115284e9f8a62d6af8018869febe34b9ce292eb5b61b8e0dd6f54b` |
| `reports/shadow_validation/accel_8h_checkpoint_api_raw_20261002T142017Z.json` | `0554b330d5c0ff07fbbec3cf9cf5460b5fc861fecf6f7251d148b4f3e1b2a1c3` |
| `reports/shadow_validation/accel_8h_checkpoint_latest.json` | `021c5ece36115284e9f8a62d6af8018869febe34b9ce292eb5b61b8e0dd6f54b` |

Related (referenced by checkpoint / prepare package; frozen for cross-link):

| Artifact | SHA256 |
|---|---|
| `docs/certification/POST_8H_12H_SHADOW_VALIDATION_PACKAGE_20261002.md` | `86620cb29f6680492fad70cf1fc3802acdd4c9289d383ca80d31e379b992cd60` |
| `docs/certification/WORKSTREAM_A_QUOTER_429_BEFB14E_INDEPENDENT_CERT_20261002.md` | `5814aaefc75ab902dfa57deac807e345648f48a54dc330ad0efccf6591f3ff2e` |
| `artifacts/workstream-a-quoter-429-befb14e-selfcontained.bundle` | `b7f3952e29a5664bb6c7a144e7a76c9df7ba207b3f2ee6a430bb84a3a4dff964` (8199151 B) |
| Thin bundle (NOT deploy source) `…befb14e.bundle` | `12780813f62a67d663a6c58ff0e91719854b0de2ab9935d651fd9a8436a1a6d2` (45892 B) |

---

## 3. Gate9 container — READ-ONLY confirmation at freeze

Container: `arbicore-x-backend-new`

| Field | Required | Observed at freeze |
|---|---|---|
| StartedAt | ~2026-10-02T06:19:33Z | **`2026-10-02T06:19:33.513948555Z`** |
| RestartCount | 0 | **0** |
| Image | g5.79-green-20260927 | **`arbicore-x-backend:g5.79-green-20260927`** |
| ImageId | (continuity) | `sha256:aaadc3a9cc78d695a9e7e2d16681babc71c576033ad3764061a918946d8e993a` |
| Health | healthy | **healthy** |
| Status | running | **running** |

Safety env (inspect Config.Env, no mutation):

| Key | Value |
|---|---|
| ARBICORE_EXECUTION_MODE | SHADOW |
| ARBICORE_SHADOW_CERT_ENABLED | true |
| ARBICORE_AUTOEXEC_AUTOSTART | false |
| ARBICORE_RUNTIME_AUTOSTART | false |
| ARBICORE_PAPER_VALIDATION_ENABLED | true |
| ARBICORE_SCANNER_AUTOSTART | true |

Campaign **continues untouched**. Official Gate9 (≥24h) earliest still ≈ `2026-10-03T06:19:43Z`. This freeze is **not** Gate9 PASS / Gate10 PASS.

---

## 4. Campaign / deploy stance (binding)

| Action | Status |
|---|---|
| Gate9 restart / recreate / rebuild | **NOT DONE** |
| Deploy Workstream A / image swap | **NOT DONE** |
| Env / credentials / signing / broadcast change | **NOT DONE** |
| Production `/home/raghu/projects/arbicore-x-v2` modified | **NOT DONE** |
| Cert workspace dirty tree reset | **NOT DONE** (preserved) |
| PAPER / 12h start / AUTOEXEC / RUNTIME / live | **NOT DONE** |

**Intended later sequence (document only):**  
8h PRE-FIX (this freeze) → certified WA quoter fix deploy (after explicit GO) → fresh 12h SHADOW → compare → official 24h Gate9.

Cross-link: `docs/certification/POST_8H_12H_SHADOW_VALIDATION_PACKAGE_20261002.md` (rollback §10; deploy checklist §9).  
Staging package (prepared, not deployed): `artifacts/deploy_staging/workstream-a-befb14e/` + `docs/certification/WORKSTREAM_A_BEFB14E_DEPLOY_PACKAGE_PREPARED_20261002.md`.
