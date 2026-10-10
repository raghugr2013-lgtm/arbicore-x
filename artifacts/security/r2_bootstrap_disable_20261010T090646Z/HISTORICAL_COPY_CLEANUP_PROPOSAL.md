# Proposed follow-on: bootstrap-token historical copy cleanup

**Status:** proposal only — **not authorised** by R2-DISABLE  
**Related inventory:** `artifacts/security/r2_bootstrap_preflight/token_location_inventory.json`  
**Live path:** clean after R2-DISABLE (ENV + active `.env` have no `ARBICORE_BOOTSTRAP_TOKEN`)

## Goal

Reduce residual risk from disk copies of the **retired** bootstrap token (sha12 `d5a682fbe887` and older `f5748db3f254`) without touching production runtime, approved recovery archives without policy review, or unrelated secrets.

## Suggested bounded phases (separate auths)

| Phase | Scope | Action | Risk |
|---|---|---|---|
| C1 | `/tmp/arbicore*.env`, `/tmp/*runtime*.env`, obvious one-off dumps | Delete or shred listed paths from inventory `tmp_paths` | Low — ephemeral |
| C2 | Local non-approved `.env.*` backups under `arbicore-x-v2/deployment/upgrade/backend/` that are not the R2 recovery backup | Operator review list → delete or move to encrypted offline store | Medium — may be useful for other rollbacks |
| C3 | Stopped legacy Config.Env (b7/h05/w1) | Remove/recreate containers **without** starting them, after other secret rotations as applicable | Medium — must stay stopped |
| C4 | Approved `arbicore_backups/s1b_*`, `s2a_alchemy_cutover_*`, R2 pre-disable backup | **Retain** restricted; optional offline copy then wipe host copies under DR policy | High process — do not auto-delete |

## Rules

- Never print or log token values.  
- Prefer path+sha12 attestation before/after.  
- Do not modify live `.env` or running backend ENV in cleanup phases.  
- Do not start legacy containers.  
- Keep at least one offline escrow of the R2 pre-disable `.env` until operator confirms no rollback need.

## Acceptance for a future cleanup auth

- Live ENV/`.env` still lack bootstrap token.  
- Targeted paths gone or attested moved offline.  
- Approved archives either retained 0600 or explicitly migrated per sign-off.  
- Backend digest/controls unchanged by cleanup.
