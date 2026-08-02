# Pending — Scanner-tree Activation Tests

These test files were carried forward from the legacy `arbicore-x` v1.0.2 repository.
They exercise endpoints/routes that live in canonical modules currently DORMANT in
`server.py` per the merge decision (4b — modules imported into the tree, not wired
into the FastAPI app until controlled per-module validation).

**Modules pending activation:**
- `backend/routes/` (auth, execution, observation, portal, portfolio, vault, venues, alerts)
- `backend/services/` (auth, balances, capability, collector, discovery, exchange_private, execution, health_analytics, holdprob, key_health, observation, portal_price, seed, telegram_alerts, vault, venue_monitor, ws_manager)
- `backend/arbicore/{intel, intelligence, scanner, scanners, shadow, runtime}`
- `backend/connectors/`, `backend/core/`, `backend/engines/`, `backend/diagnostics/`

**Activation plan (post v2.0.0):**
Per the v2.0.0 roadmap, each dormant module cluster will be activated under a controlled
validation wave. When a wave activates the module cluster that a test in this directory
covers, the corresponding test file should be moved back to `tests/`.

**These files are NOT included in the default regression run** (pytest.ini scopes `tests/`
top-level only; this subdirectory is excluded from collection).
