# Strategy IR — Native ArbiCore Ingestion Contract

**Purpose.** Receive Strategy Factory (separate upstream) research output as a
**non-executable** candidate and route it into ArbiCore's *existing* downstream
pipeline. Strategy IR is **DATA ONLY** — a hypothesis, never an authorized action.

## Boundary
- **Strategy Factory (upstream, out-of-process):** research, generation, mutation,
  evolution, optimization, external intelligence. NOT imported into ArbiCore.
- **ArbiCore (downstream authority):** discovery → quote → economics → optimizer →
  simulation → evidence → PAPER/SHADOW. Sole authority for all execution/safety.
- Integration is **one-way**: SF → Strategy IR → admin ingestion → registry →
  existing pipeline. **No reverse control path.**

## Schema (`arbicore/strategy_ir/schema.py`)
`strategy_id, strategy_version(≥1), strategy_fingerprint(derived), strategy_type
(allow-listed), parameters{}, constraints{}, required_capabilities[], route_hints[],
provenance{source, source_ref, timestamp, trust, confidence}, source_class
(INTERNAL|EXTERNAL|MUTATED|HYBRID), lineage[], created_at`.

- **Fingerprint** = `sfp_` + sha256 over the SEMANTIC definition (type + params +
  constraints + capabilities + route_hints), excluding volatile fields. Same
  semantics ⇒ same identity; a semantic change ⇒ a new strategy.
- **Versioning:** integer ≥ 1; registry unique key = `(fingerprint, version)`.

## Security boundary (enforced + tested)
`validate_non_executable()` recursively **rejects** any `FORBIDDEN_KEYS`
(case/dash-insensitive) anywhere in the payload: private keys, signer, calldata,
userData, broadcast, execution_mode, kill_switch, authorize/execute, bypass/skip
simulation, allowlist/profitability/repayment/quote-freshness/risk/readiness
overrides, enable_live, etc. Unknown `strategy_type` is rejected.

The **adapter** (`adapter.py`) emits an opportunity *hypothesis* that is engineered
to FAIL the existing simulation gate (quote `UNAVAILABLE`, no calldata, repayment
not modelled, gas unknown) — so a candidate can never execute from ingestion; it
must independently pass the real downstream gates. Proven:
`decide_opportunity(adapter_output)` → `would_execute == False`.

## Ingestion API (`routes/strategy_ir.py`, admin-authenticated)
- `POST /api/strategy/candidates` — ingest (validate → register). Anon → 401.
- `GET  /api/strategy/candidates` — list.
- `GET  /api/strategy/registry/{id}` — registry entry.
- `POST /api/strategy/candidates/{id}/preview-hypothesis` — operator inspection;
  explicitly non-executable.

## Storage (additive Mongo collections only)
- `strategy_registry` — unique `(strategy_fingerprint, strategy_version)`.
- `strategy_candidates` — ingested IR + `lifecycle_state=INGESTED`, `executable=false`.
No existing collection migrated/reset/deleted.

## What Strategy Factory is NOT allowed to control
Kill switch, signer, broadcast, execution mode, allowlists, quote freshness,
repayment, calldata validation, profitability/simulation gates, readiness, live
mode. It may only *influence* research metadata (trust/confidence) which is advisory.

## Future extension points (not built now)
- Learning **governance** (validation → versioned promotion → rollback) on the
  existing advisory learning loop — deferred.
- External-knowledge connectors (public sources) feeding Strategy IR — deferred.
- EVM backtest/walk-forward/Monte-Carlo research adapters — deferred.

## Hardening (verified — iteration_5→7)
- **Server-authoritative identity:** `strategy_id = "sid_"+sha256(fingerprint:version)`
  — client-supplied id ignored; canonical, collision-free, un-spoofable (unique-indexed).
- **Idempotent duplicates:** same (fingerprint,version) → same canonical id, one
  registry doc, one candidate row with `ingest_count`.
- **`extra='forbid'`** on `StrategyIR`/`StrategyProvenance` → root-level execution-ish
  fields are 422 (not silently dropped).
- **Size/cardinality caps:** parameters/constraints ≤200 keys, capabilities/route_hints
  ≤100, 256KB payload → 422.
- **Value scan:** forbidden token in `required_capabilities` → 422.
- Verified: 85/85 pytest (`tests/test_phase3_strategy_ir*.py`) + live-endpoint assertions,
  0 critical / 0 minor; fail-closed safety posture unchanged.
