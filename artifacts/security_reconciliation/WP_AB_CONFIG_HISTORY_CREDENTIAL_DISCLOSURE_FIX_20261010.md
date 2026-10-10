# Emergency Fix — Configuration-History Credential Disclosure

**Date:** 2026-10-10  
**Base (unchanged):** `review/wp-ab-auth-20261010` @ `0e0f6fb31c6e17f39ae320265a95a05be60e5a58`  
**Fix branch:** `review/wp-ab-config-history-redact-20261010`  
**Worktree:** `/tmp/arbicore-review-wp-ab-config-history-fix`  
**Producer worktree:** preserved (not modified for this fix)

## Finding (Emergent Handoff-2)

`GET /api/arbicore/settings/config/history` was unauthenticated and returned configuration-history records containing raw `rpc_urls`. Anonymous synthetic-credential probe → HTTP 200 + exposed test key.

## Fix

| Change | Detail |
|--------|--------|
| Auth | Route now `dependencies=[Depends(_require_operator_dep)]` — same operator gate as `GET .../settings/network` and `.../network/history` |
| Redaction | Response `items` wrapped with `_redact_network_payload` (recursive; covers nested network snapshots under any kind) |
| POST network | `validate` / `draft` / `apply` / `rollback` success + `ValueError` bodies also redacted (Handoff-2 residual POST leak) |

Published review commit `0e0f6fb` was **not** rewritten. No merge to canonical. No production access.

## Diff (exact)

```diff
--- a/app/backend/server.py
+++ b/app/backend/server.py
@@ validate:
-    return {**_NETWORK_CONFIG.validate(patch or {}),
+    return {**_redact_network_payload(_NETWORK_CONFIG.validate(patch or {})),

@@ draft / apply / rollback success + ValueError:
+    _redact_network_payload(...) on draft/config/error strings

@@ config/history:
-@api_router.get("/arbicore/settings/config/history")
+@api_router.get("/arbicore/settings/config/history",
+                dependencies=[Depends(_require_operator_dep)])
...
-    return {"items": items, "count": len(items),
+    return {"items": _redact_network_payload(items), "count": len(items),
```

New tests: `app/backend/tests/test_wp_ab_config_history_redaction.py`

## Test evidence

**Command:**
```bash
cd /tmp/arbicore-review-wp-ab-config-history-fix/app/backend
/tmp/wp_a_auth_venv/bin/python -m pytest \
  tests/test_wp_a_auth_unification.py \
  tests/test_wp_a_emergency_auth_finalization.py \
  tests/test_wp_a_real_handlers.py \
  tests/test_wp_b_kill_switch_auth.py \
  tests/test_wp_ab_config_history_redaction.py \
  -q --tb=short
```

**Result:** `62 passed` (prior 54 + 8 new) in ~10.4s  
**Log:** `/tmp/wp_ab_config_history_fix_pytest.txt`

Coverage in new file:
- Anonymous / forged-token → 401, no synthetic key in body
- Operator authorized → 200, network + nested `rpc_urls` redacted; non-network (telegram) records retained
- `kind=network` filter path redacted
- validate / draft / apply / rollback responses + apply `ValueError` path: no synthetic key

## Scope / non-goals

- No WP-C, deploy, signing, broadcast, strategy activation, secret rotation
- No rewrite of `0e0f6fb`; no canonical merge
- Synthetic credentials only in tests
