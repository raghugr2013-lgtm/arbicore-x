# Workstream A (`befb14e`) — Deployment Staging Package

- **Prepared (UTC):** 2026-10-02T14:44:46Z
- **Status:** PREPARE ONLY — **DO NOT DEPLOY** without explicit operator authorization
- **Product tip:** `befb14e6aa77515daa038e142ff978822a4fab91`
- **Authoritative source:** `artifacts/workstream-a-quoter-429-befb14e-selfcontained.bundle`
- **SHA256:** `b7f3952e29a5664bb6c7a144e7a76c9df7ba207b3f2ee6a430bb84a3a4dff964` (8199151 bytes)
- **Throwaway verify clone:** `/tmp/ws-a-deploy-prep-freeze-20261002` (not Gate9; not production; not dirty-reset of cert tree)

## Layout

| Path | Contents |
|---|---|
| `meta/tip_identity.txt` | tip / tree / parent / subject / dates |
| `meta/ancestry_*.txt` | history walk + ancestor checks (`93a20c9`, `2b86cda`, rpc blob continuity) |
| `meta/show_stat.txt` / `name_status.txt` | `git show` inventory |
| `meta/fixture_followup_status.txt` | `57f5365` test-hygiene only (NOT in product package) |
| `meta/bundle_pointer.txt` | self-contained vs thin bundle |
| `product_diff/*.diff` | exact tip product diffs |
| `tip_files/...` | tip blobs of changed product/test files (build inventory) |

## Rollback target (current live Gate9)

| Item | Value |
|---|---|
| Image tag | `arbicore-x-backend:g5.79-green-20260927` |
| ImageId | `sha256:aaadc3a9cc78d695a9e7e2d16681babc71c576033ad3764061a918946d8e993a` |
| Override | `/tmp/arbicore-g579-prod-override.yml` |
| Runtime GIT_SHA (override) | `4fec11f92fecb7f7ef1f56e39cddf18277845470` |
| Procedure | `POST_8H_12H_SHADOW_VALIDATION_PACKAGE_20261002.md` §10 |

## Cert pointers

- `docs/certification/WORKSTREAM_A_QUOTER_429_BEFB14E_INDEPENDENT_CERT_20261002.md` §12–§13
- `docs/certification/PRE_FIX_8H_BASELINE_FREEZE_20261002.md`
- `docs/certification/WORKSTREAM_A_BEFB14E_DEPLOY_PACKAGE_PREPARED_20261002.md`
