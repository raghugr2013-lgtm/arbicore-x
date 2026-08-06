# Infrastructure Validation — pre-Shadow-Certification gate

**Date:** 2026-08-06
**Env:** preview (Kubernetes) · Mongo local · Paper Validation runner enabled

## Result: 🟢 GREEN — cleared to begin Shadow Certification (v2.11.9)

### Verification matrix

| Check | Method | Result |
|---|---|---|
| Mongo DNS resolution | `motor.admin.command('ping')` | ✅ OK |
| Mongo connect (no `Temporary failure in name resolution`) | Backend logs scan (regex: `dns|resolution|refused|timeout`) | ✅ zero hits |
| `ensure_indexes` idempotency | `MongoOpportunityRepository.ensure_indexes()` on live collection with existing indices | ✅ no `IndexOptionsConflict` |
| Paper Validation Framework wiring | `/api/arbicore/validation/metrics` | ✅ runner_enabled=true, is_running=true |
| Runner cycles (6) | metrics `cycles_completed=6` | ✅ zero exceptions |
| Opportunity throughput | `opportunities_processed=14` (14/14 canonical opps) | ✅ full drain |
| EvidenceBundle persistence | `arbicore_paper_evidence` count | ✅ 14 (was 0) |
| EvidenceBundle immutability schema | sample bundle keys | ✅ frozen fields present (schema_version, mode, opportunity_id, outcome, outcome_reason, pipeline_action, plan_id, scanner_family, simulation_backend, stages, validation_id, created_at, inputs) |
| Runner idempotency (restart-safe) | second `run_once` — `opportunities_skipped_dup=70` | ✅ zero re-emitted bundles |
| Outcome vocabulary alignment | 8-value canonical histogram in `/validation/report` | ✅ all 8 slots present |
| Pulse hook | `/dashboard/pulse.paper_validation` | ✅ live total/rate/runner_running/outcome_counts |
| Scanner activity into Mongo | scanner CEX ticker writes visible in logs (Kraken/OKX/KuCoin/Coinbase OK; Binance 451 / Bybit 403 — expected region blocks, not infra) | ✅ writes reach Mongo |

### Non-blocker observation logged

- `arbicore_opportunity_journal.validation_id` not populated on runner-driven pipeline evaluations (19 rows, 0 with `validation_id`). Shadow Certification does **not** depend on the journal link (it consumes `EvidenceBundle.validation_id` directly), so it is out of scope for the certification implementation. Filed as a follow-up hardening task under `paper_validation.wire_journal_validation_id`.

### Environment flags in effect

- `ARBICORE_PAPER_VALIDATION_ENABLED=true` (added to `/app/backend/.env` for continuous cycles)
- `MONGO_URL=mongodb://localhost:27017`
- `DB_NAME=arbicore_x_hotfix_test`

### VPS-side note (Docker Compose `vqb-network` hotfix)

The VPS DNS-resolution failure to `factory-mongo` was resolved by attaching
`arbicore-x-backend` to the external `vqb-network` in
`/app/deployment/compose/docker-compose.yml` (v2.11.9 hotfix). This
validation exercised the **code path** the VPS runs. VPS operator to
verify on-host with:

```bash
docker compose exec arbicore-x-backend python -c \
  "from motor.motor_asyncio import AsyncIOMotorClient as C, os; import asyncio; \
   asyncio.run(C(os.environ['MONGO_URL']).admin.command('ping'))"
```

Expected: `{'ok': 1.0}` with no `getaddrinfo` failure.
