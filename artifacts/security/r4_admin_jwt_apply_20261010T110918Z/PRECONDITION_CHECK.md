# R4-APPLY mandatory precondition check

**Result: READY** (verified from implementation + live login probe before mutation)

| Condition | Evidence | Status |
|---|---|---|
| JWT rotate + recreate invalidates old cookies; fresh login still uses Mongo `password_hash` | `services/auth.py` `_secret()`/`decode_token`; `routes/auth.py` `login` → `verify_password(..., user["password_hash"])` | **VERIFIED** |
| `ARBICORE_ADMIN_PASS` boot seed only; does not overwrite existing hash | `ensure_provisioned_users()` insert-only (`existed` → continue; never updates `password_hash`) | **VERIFIED** |
| `POST /api/auth/change-password` updates intended admin `password_hash` | Loads user by JWT `sub`/`id`; verifies current; `$set` `password_hash` + `session_version++` | **VERIFIED** |
| Safe recovery path | Restore `backend.env.pre-r4` + recreate; if hash already changed, restore users dump / change-password new→old | **VERIFIED** (procedure recorded; dump taken in apply) |
| Live ENV password still authenticates pre-apply | Login **200** + `/me` **200** (admin id `eeeeb6d9-…`) | **VERIFIED** |

UTC recorded by orchestrator JSON.
