# Sprint 1B-β — Scanner Activation (SHADOW MODE)

**Release date:** 2026-08-03
**Wave:** 1B-β (of 3)
**Charter:** Activate the two previously-dormant scanners
(``DEXArbitrageScanner`` and ``FlashLoanArbitrageScanner``) in operator-
controlled shadow mode. Every emission writes validated evidence into
MID. **No live network I/O.**

---

## Scanners activated (all boot DORMANT)

| Scanner ID              | Mode   | Autostart | Adapter                                     |
|-------------------------|--------|-----------|---------------------------------------------|
| `dex_arbitrage`         | shadow | disabled  | `wave1b.adapters.ShadowScannerAdapter`      |
| `flash_loan_arbitrage`  | shadow | disabled  | `wave1b.adapters.ShadowScannerAdapter`      |

Startup log:

```
wave1b-β: registered shadow scanner id=dex_arbitrage (dormant)
wave1b-β: registered shadow scanner id=flash_loan_arbitrage (dormant)
wave1b-β: scanner activation complete — 2/2 registered, all DORMANT
scanners: Wave 1B-β activation summary — count=2 running=[] errored=[] (all boot DORMANT)
```

## Design

Sprint 1B forbids live blockchain RPC, DEX or exchange traffic, and
production quote providers. The real ``DEXArbitrageScanner`` and
``FlashLoanArbitrageScanner`` classes drag in live HTTP aggregator
sources and quoters, so they are left DORMANT (present in the tree but
not instantiated).  In their place, ``ShadowScannerAdapter`` implements
the **exact same lifecycle contract** (``start`` / ``stop`` /
``is_enabled`` / ``is_running`` / ``stats``) but its tick does only:

  1. Reads the latest MID intelligence rows (Wave 1B-α evidence).
  2. Produces one synthetic shadow emission and hands it to
     :class:`ScannerEvidenceBridge`.
  3. The bridge writes a ``mid_opportunities`` row
     (``event_type = "scanner.<id>.emit"``) and a ``mid_routes`` row.
  4. Bumps operator-visible stats: iterations, rows_emitted,
     backlog_size, backlog_dropped, last_run_at, uptime_seconds, errors.

This proves the entire ``scanners → MidEvidenceBridge → MID → engines``
pipeline end-to-end while honouring the "no live I/O" invariant.

## New API endpoints

* `GET  /api/arbicore/scanners/status`               — per-scanner state + bridge stats + intelligence stats.
* `POST /api/arbicore/scanners/{scanner_id}/start`   — operator/admin only (401 without token, 403 for wrong role, 404 for unknown scanner).
* `POST /api/arbicore/scanners/{scanner_id}/stop`    — same auth rules.
* `GET  /api/arbicore/observability`                 — one-shot health for MID + intelligence + scanners + auth.

Also added in this wave (auth v2.0.7):

* `GET /api/auth/diagnostics` — admin-only introspection of the
  ``auth_users`` collection (never returns the hash, only its length
  and prefix).

## Evidence flow (verified live against the preview URL)

```
POST /api/arbicore/scanners/dex_arbitrage/start        (operator bearer)
    → {"scanner_id":"dex_arbitrage","mode":"shadow","started":true,...}

sleep 22s

GET /api/arbicore/observability
    mid.opportunities.count            = 7  (mirrors + scanner emissions)
    mid.routes.count                   = 4
    scanners.running                   = ["dex_arbitrage"]
    scanners.bridge_stats.total_emissions = 4
    scanners.bridge_stats.by_scanner   = {"dex_arbitrage": 4}
    dex_arbitrage stats                = {iterations:4, rows_emitted:4}
```

## VPS authentication regression (v2.0.7)

**Symptom** (reported by user): production login returns
``invalid_credentials`` after a password reset on the VPS, even though
the reset script wrote a fresh bcrypt hash for the admin user.

**Root cause**: ``arbicore.auth.find_user`` filtered on
``{"username": u, "active": True}``. An out-of-band password-reset
script that wrote only ``password_hash`` (leaving ``active`` unset)
would land a document that the seed routine and the reset routine both
considered valid, but that ``find_user`` silently rejected — so login
returned 401 even though authentication was actually possible.

**Fix**: ``find_user`` now filters on
``{"username": u, "active": {"$ne": False}}`` — documents lacking the
``active`` field are treated as active-by-default; only accounts
explicitly deactivated (``active: false``) are rejected. The seed
routine's post-seed verification query was updated to match, so it no
longer emits a false-negative on legacy admin documents.

**Verification (live, on the preview URL against the same Mongo)**:

| Case                                              | Expected | Observed |
|---------------------------------------------------|----------|----------|
| Login admin after `$unset {active}`               | 200      | 200      |
| Login admin after `$set {active:false}`           | 401      | 401      |
| Login admin after `$set {active:true}` (restore)  | 200      | 200      |
| `GET /api/auth/diagnostics` as admin              | 200 + payload | 200 |
| `GET /api/auth/diagnostics` as operator           | 403      | 403      |
| `ensure_seed_users` on DB with legacy admin       | ok=true, verified.admin=true, inserted=[operator] | matches |

## Observability endpoint payload (excerpt)

```json
{
  "mid": {"available": true, "domains": {...11 domain counts + last_ts...}},
  "intelligence": {"available": true, "active_count": 6,
                   "active": ["confidence","roi","route_ranking","economics","entity_scoring","regime"],
                   "bridge_stats": {"total_writes": 0, "by_engine": {}, ...}},
  "scanners": {"available": true, "scanner_count": 2, "running": ["dex_arbitrage"],
               "bridge_stats": {"total_emissions": 4, "by_scanner": {"dex_arbitrage":4},
                                "by_event_type": {"scanner.dex_arbitrage.emit":4},
                                "routes_observed": 4, ...},
               "scanners": [{"id":"dex_arbitrage","mode":"shadow","running":true,
                             "stats":{"iterations":4,"rows_emitted":4,
                                      "backlog_size":0,"backlog_dropped":0,
                                      "last_run_at":"...","uptime_seconds":40}},
                            {"id":"flash_loan_arbitrage","running":false,...}]},
  "auth": {"available": true}
}
```

## Regression results

**1487 passed, 76 skipped, 0 failures**  (previous baseline 1478)

New tests:

* `tests/test_wave1b_beta.py::test_activate_scanners_boots_dormant`
* `tests/test_wave1b_beta.py::test_shadow_scanner_start_stop_lifecycle`
* `tests/test_wave1b_beta.py::test_start_is_idempotent`
* `tests/test_wave1b_beta.py::test_stop_before_start_is_safe`
* `tests/test_wave1b_beta.py::test_bridge_stats_attribute_writes`
* `tests/test_wave1b_beta.py::test_bridge_publish_direct_with_route`
* `tests/test_wave1b_beta.py::test_auth_legacy_document_without_active_can_login`
* `tests/test_wave1b_beta.py::test_auth_active_false_denies_login`
* `tests/test_wave1b_beta.py::test_ensure_seed_users_verifies_legacy_admin_ok`

## Sprint 1B constraints honoured

* No live blockchain RPC calls.
* No live DEX queries.
* No live exchange APIs.
* No production quote providers.
* No production execution.
* Scanners boot DORMANT; only an authenticated operator or admin can
  start/stop them.
* Backward compatibility: no existing endpoint changed, no existing
  test broken.

## Files added

* `arbicore/scanners/wave1b/__init__.py`
* `arbicore/scanners/wave1b/bridge.py`      (`ScannerEvidenceBridge`)
* `arbicore/scanners/wave1b/registry.py`    (`ScannerRegistry`)
* `arbicore/scanners/wave1b/adapters.py`    (`ShadowScannerAdapter`)
* `arbicore/scanners/wave1b/activation.py`  (`activate_scanners`)
* `tests/test_wave1b_beta.py`               (9 tests)
* `docs/RELEASE_NOTES_v2.1.0-beta.md`

## Files modified

* `app/backend/arbicore/auth/__init__.py` — `find_user` tolerant `active` filter + matching seed verification query
* `app/backend/server.py`                 — Wave 1B-β startup + endpoints + `/api/auth/diagnostics`
* `VERSION`                               — bumped to `2.1.0-beta`
