# Test credentials — ArbiCore X hotfix/auth-routing

## Verified locally against a fresh `arbicore_x_hotfix_test` Mongo db

**These are LOCAL VERIFICATION credentials only.** Production must go
through `/api/auth/setup` on first boot to create its own admin.

| Field    | Value                                                              |
| -------- | ------------------------------------------------------------------ |
| Endpoint | `/api/auth/setup` (POST, first-run) then `/api/auth/login` (POST)  |
| Username | `admin`                                                            |
| Password | `hotfix-v293`  *(local Playwright run; step 21 of the transcript uses `testtest123`)* |

Cookies set by successful `setup` or `login`:
- `access_token`  (httpOnly, `SameSite=Lax`, `Path=/`, 30-minute TTL)
- `refresh_token` (httpOnly, `SameSite=Lax`, `Path=/`, 7-day TTL)

Reset:
```
docker compose exec arbicore-x-backend python reset_admin.py --dry-run   # inspect
docker compose exec arbicore-x-backend python reset_admin.py             # apply
```
