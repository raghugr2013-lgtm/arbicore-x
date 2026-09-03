# ArbiCore X — Strategy IP + Phase 3 Certification Gap Audit

**Type:** READ-ONLY audit. No code, schema, safety, or Mongo data changed.
**Baseline:** HEAD `a4039f0` on `phase3/final-proof-completion`; `main` untouched.
**Safety posture (unchanged, re-verified in code):**
SHADOW = READY · PAPER = BLOCKED · LIMITED_LIVE = BLOCKED · FULL_AUTOMATION = BLOCKED.
Kill switch, signer, broadcast, execution engine, learning engine and Strategy IR
implementation were **not** modified. No critical live exposure was found (see §3),
so no fix was implemented — this stops at the report, awaiting approval.

---

## 1. Remaining Phase 3 certification blockers

Re-derived directly from `arbicore/control/readiness.py`, `execution/technical_validation.py`,
`searcher/revm_backend.py`, `execution/executor_entrypoint.py` (AnvilForkHarness) and the
`/api/arbicore/engine/*` routes in `server.py`. Every blocker below is **environment/RPC/binary
dependent** and is correctly reported fail-closed in code (returns `no_base_rpc_configured` /
YELLOW/RED — never a fabricated GREEN).

| # | Blocker | Where | Current state | Gate it unblocks |
|---|---|---|---|---|
| B1 | **Base chain-ID verification** | `technical_validation.TechnicalValidator._chain_id()` (`eth_chainId`) | Cannot run — no RPC | Executor / on-chain proofs |
| B2 | **Executor bytecode / ABI verification** | readiness `_contracts()`; `server.py:4875` ("until an executor address + bytecode are provided") | RED — needs `eth_getCode` + `ARBICORE_EXECUTOR_ADDRESS_BASE` | LIMITED_LIVE CONTRACTS gate |
| B3 | **Atomic flash-loan simulation (eth_call preflight)** | `technical_validation.preflight()`, `/arbicore/wizard/technical-validation`, `/arbicore/engine/run-atomic-*` | Fail-closed; `eth_call` needs RPC | SIMULATION gate |
| B4 | **Fork lifecycle validation** | `searcher/revm_backend.AnvilRevmForkBackend._preflight()`, `execution/executor_entrypoint.AnvilForkHarness` | Blocked twice: **anvil binary NOT installed** *and* no fork/archive RPC | PAPER + LIMITED_LIVE fork gate |
| B5 | **Fork-based validation routes** | `/arbicore/engine/fork-status`, `/arbicore/engine/run-fork-validation`, block-pinned atomic diagnostic | Ready-to-run harness; returns fail-closed without RPC/anvil | Deterministic route (A–J) proofs |
| B6 | **Flash-provider on-chain availability** | Aave V3 / Balancer V2 modelled allowlist | IMPLEMENTED + UNVERIFIED — on-chain check needs RPC | Flash provider certification |
| B7 | **Learning-loop end-to-end proof** | advisory learning loop | YELLOW — needs real historical outcome data (observe→update→rollback + no-future-leakage) | PAPER learning evidence |

Everything else in `FINAL_CERTIFICATION_PHASE3.md` is already GREEN (git baseline, auth/API
security, admin bootstrap, economics, optimizer sweep, RPC-config selector, simulation-gate
logic, DB safety, frontend/API truth, CI submodule fix) and is unaffected by this audit.

---

## 2. Exact environment / RPC requirements to close §1

Provide as backend `.env` values (address/URL only — **never** a private key in `.env`;
the signer stays in the encrypted vault / KMS):

| Var | Purpose | Needed for | RPC methods exercised |
|---|---|---|---|
| `ARBICORE_RPC_URL` | Read-only Base mainnet/Sepolia RPC | B1, B2, B3, B6 | `eth_chainId`, `eth_getCode`, `eth_call` (with `stateDiff` override), `eth_gasPrice`, `eth_estimateGas` |
| `ARBICORE_ARCHIVE_RPC_URL` | Archive/trace RPC (historical block state) | B4, B5 fork sim | archive `eth_call` at `--fork-block-number`, state-override |
| `ARBICORE_EXECUTOR_ADDRESS_BASE` | Deployed `FlashLoanReceiver` address | B2 | `eth_getCode` bytecode/hash + callback allowlist check |
| **anvil binary** (Foundry) | Local fork engine (`anvil --fork-url`) | B4, B5 | subprocess launch + fork `eth_call` |
| `ARBICORE_VALIDATION_SIGNER_KEY` (vault/KMS, **not .env**) | Engineering signer for *execute=true* self-test only | Optional B6 broadcast proof | `eth_sendRawTransaction` (testnet only; never mainnet in this build — `_MAINNET_CHAIN_IDS` blocked) |

**Confirmed absent right now:** none of `ARBICORE_RPC_URL / ARBICORE_ARCHIVE_RPC_URL /
ARBICORE_EXECUTOR_ADDRESS_BASE / ARBICORE_VALIDATION_SIGNER_KEY` are set, and `anvil` is not
installed. So B1–B6 are honestly BLOCKED-BY-ENVIRONMENT, not failed. Do **not** fabricate,
mock, or weaken these to force a pass. No safety change is required or permitted to run them.

---

## 3. Strategy IP exposure findings (read-only audit of 16 surfaces)

| # | Surface | Finding | Exposure |
|---|---|---|---|
| 1 | Strategy IR API responses | `POST /candidates` returns identity only (`registered, duplicate, strategy_id, fingerprint, version, lifecycle_state, executable=false`). `GET /candidates` & `GET /candidate` return **full alpha** (parameters/constraints/route_hints) but **admin-only**. | Contained (admin) |
| 2 | Strategy registry | `get_registry_entry()` returns **identity only** — `strategy_id, fingerprint, version, type, source_class, provenance, lineage, created_at`. **Alpha (parameters/constraints/route_hints) is NOT stored in the registry.** Good separation. | Low |
| 3 | Strategy candidates | Alpha lives here (parameters/constraints/route_hints/required_capabilities). Admin-only reads. | Contained (admin) |
| 4 | Frontend exposure | **Zero** references to `/api/strategy`, `strategy_ir`, `fingerprint`, or `preview-hypothesis` in `frontend/src`. Alpha never reaches the browser bundle. | None |
| 5 | Logs | `routes/strategy_ir.py:35` logs `fingerprint + version + username + duplicate` at INFO. **Parameters/constraints/route_hints are never logged.** Fingerprint = identity, not the strategy. | Low (identity only) |
| 6 | Evidence bundles | Technical-validation evidence bundles carry chain/tx/gas — no Strategy IR alpha. Adapter output is not persisted into the journal. | None |
| 7 | Provenance | `provenance.source` / `source_ref` (URL/commit/DOI) stored in registry + candidate; returned admin-only. `source_ref` could reference a private location (see §4). | Low–Medium |
| 8 | Database access | Two additive collections (`strategy_registry`, `strategy_candidates`). Access is via admin-only routes; no public/aggregation read path exists. | Contained |
| 9 | Admin vs non-admin | All 4 routes wrapped by `require_admin` (403 non-admin, 401 anon). Verified in `routes/strategy_ir.py`. | Enforced |
| 10 | Strategy parameters | The core alpha. Stored + returned admin-only; never logged, never in frontend. | Contained (admin) |
| 11 | Route hints | Alpha-adjacent (which venues/fee-tiers). Admin-only; passed as *hints only* into adapter output (not persisted). | Contained (admin) |
| 12 | Lineage | Parent fingerprints (identity chain). Registry + candidate, admin-only. Reveals *relationships*, not strategy content. | Low |
| 13 | Fingerprints | `sfp_sha256(semantic-definition)`. Identity/integrity only — **does not by itself disclose the strategy**. Appears in logs + `opportunity_id` prefix in adapter output. | Low |
| 14 | API serialization | `to_registry_doc()` and route responses are explicit dict projections (`{"_id":0}`). No accidental raw-Mongo/ObjectId leak. `extra='forbid'` blocks unknown fields inbound. | Good |
| 15 | Error messages | `_scan_forbidden` 422 echoes the **offending key name + path** back to the caller; type/size validators echo bounds. Caller is the admin who sent it, so this is self-disclosure only. | Minor |
| 16 | Monitoring / telemetry | Only the INFO log line (#5). No metrics/telemetry emit parameters or route_hints. | Low |

**Net:** the current architecture **adequately protects proprietary strategies today** —
alpha (parameters/constraints/route_hints/capabilities) is admin-gated, never rendered in the
frontend, never logged, and kept out of the identity-only registry. **No critical live
exposure.** The residual items are defence-in-depth, not active leaks.

---

## 4. Field classification (PUBLIC / INTERNAL / CONFIDENTIAL / EXECUTION-SENSITIVE)

| Field | Class | Should cross SF → ArbiCore? | Rationale |
|---|---|---|---|
| `strategy_type` | PUBLIC | Yes | Archetype label (e.g. `triangular`); no alpha |
| `source_class` | PUBLIC | Yes | Provenance category tag |
| `strategy_id` | INTERNAL | Derived (not trusted from client) | Server-authoritative identity |
| `strategy_version` | INTERNAL | Yes | Versioning key |
| `created_at` / `lifecycle_state` | INTERNAL | Server-set | Bookkeeping |
| `provenance.source` / `.timestamp` / `.trust` / `.confidence` | INTERNAL | Yes | Advisory metadata (never a gate) |
| `strategy_fingerprint` | CONFIDENTIAL (identity) | Derived | Reveals existence/dedup relationships, not content |
| `lineage` | CONFIDENTIAL | Yes | Parent-strategy relationships |
| `provenance.source_ref` | CONFIDENTIAL | Yes, if public reference | Could point at a private/restricted location — see §5 |
| `parameters` | **EXECUTION-SENSITIVE** | Yes (required to evaluate) | The alpha — thresholds, sizes, tolerances |
| `constraints` | **EXECUTION-SENSITIVE** | Yes | Alpha — bounds, max_hops, guards |
| `route_hints` | **EXECUTION-SENSITIVE** | Yes (hints only) | Alpha — venues/fee-tiers/paths |
| `required_capabilities` | **EXECUTION-SENSITIVE** | Yes | Alpha-adjacent — needed rails |

**Boundary rule:** the EXECUTION-SENSITIVE fields **must** cross the boundary (ArbiCore cannot
economically evaluate a hypothesis without them) — so the protection requirement is *not* to
block them at ingress but to guarantee they never egress to a lower-privilege surface. That is
already the case (§3). Registry-vs-candidate separation (identity vs alpha) is the right model
and should be preserved: any future read surface should read from the **registry** (identity)
by default and require explicit admin scope for the **candidate** (alpha).

---

## 5. External strategy provenance / originality findings

**Goal:** Strategy Factory should generate *independent hypotheses from public research*, not
copy another party's proprietary strategy/code/private repo/credentials/restricted material.

**Current state:** `SourceClass = {INTERNAL, EXTERNAL, MUTATED, HYBRID}` +
`provenance{source, source_ref, trust, confidence}`. Provenance is stored but **not validated**;
`EXTERNAL` is ambiguous — it cannot distinguish "derived from a public arXiv/GitHub-public
source" from "lifted from a private/restricted source". There is no `GENERATED`, no
`PUBLIC_RESEARCH`, and no `PROPRIETARY_EXTERNAL/RESTRICTED` marker, and no quarantine path.

**Gap:** originality/provenance is currently *descriptive*, not *enforced*. Nothing today
prevents a candidate whose true origin is restricted from being ingested as plain `EXTERNAL`.

**Minimum practical controls (recommended, not a DRM/anti-copy system):**
1. Extend `SourceClass` to: `PUBLIC_RESEARCH`, `INTERNAL`, `GENERATED`, `MUTATED`, `HYBRID`,
   `PROPRIETARY_EXTERNAL` (a.k.a. `RESTRICTED`).
2. Require non-empty `provenance.source_ref` for `PUBLIC_RESEARCH` / `EXTERNAL`-origin classes
   (a citable public reference), fail-closed if missing.
3. Fail-closed quarantine: ingest `PROPRIETARY_EXTERNAL/RESTRICTED` into a
   `lifecycle_state=QUARANTINED` that is **not** eligible for the adapter/preview path until an
   admin explicitly clears it — mirrors the existing FORBIDDEN_KEYS fail-closed philosophy.
4. Keep it advisory-only for scoring (no execution authority) — consistent with current design.

---

## 6. Controls already present (verified in code)

- `require_admin` on all four Strategy IR routes (401 anon / 403 non-admin).
- No frontend exposure of any Strategy IR field (grep-confirmed).
- `FORBIDDEN_KEYS` recursive deep-scan (keys + capability values) → execution authority stripped, 422.
- `extra='forbid'` on `StrategyIR` + `StrategyProvenance` → unknown/execution-ish fields 422.
- Server-authoritative identity (`strategy_id` derived from `fingerprint:version`; client id ignored).
- Registry stores **identity only**; alpha isolated to the candidate store.
- Adapter emits a deliberately non-executable, fail-closed hypothesis (quote UNAVAILABLE, no calldata, repayment false, gas unknown).
- Size/cardinality caps (≤200 params/constraints, ≤100 caps/route_hints, 256KB payload).
- Explicit dict projections (`{"_id":0}`) — no raw-Mongo/ObjectId leakage.
- Parameters/constraints/route_hints never logged.

## 7. Controls missing (defence-in-depth — none critical)

- **M1** No field-classification/redaction layer to guarantee identity-only projection if a lower-privilege read path is ever added later.
- **M2** Fingerprint present in INFO logs and in `opportunity_id` prefix (identity, minor).
- **M3** 422 error echoes offending parameter key name/path (self-disclosure to the admin caller; minor).
- **M4** No enforced provenance originality model (§5): no `PUBLIC_RESEARCH`/`GENERATED`/`PROPRIETARY_EXTERNAL` classes, no `source_ref` requirement, no quarantine.
- **M5** No explicit "confidential" tag travelling with a candidate so a future journal/evidence surface knows not to echo parameters/route_hints if a candidate is ever promoted into the live opportunity journal.

## 8. Recommended minimal fixes + LOC estimates (NOT implemented — awaiting approval)

| ID | Fix | Priority | Est. LOC |
|---|---|---|---|
| F1 (M4) | Extend `SourceClass` (+`PUBLIC_RESEARCH/GENERATED/PROPRIETARY_EXTERNAL`), require `source_ref` for external-origin, quarantine `RESTRICTED` (`lifecycle_state=QUARANTINED`, excluded from adapter/preview) | High (governance) | ~40–60 |
| F2 (M1/M5) | `public_view()` / registry-only projection helper + a `confidential=true` marker on candidate docs; adapter/preview return identity-tagged output | Medium | ~25–40 |
| F3 (M2) | Downgrade fingerprint log to DEBUG (or hash-prefix truncate) | Low | ~2 |
| F4 (M3) | Return generic 422 reason (drop echoed key name/path; keep server-side detail in logs) | Low | ~6–10 |
| F5 | Add provenance/originality unit tests (quarantine, missing source_ref, classification) | Medium | ~60–90 (tests) |

Total core (F1–F4): ~75–110 LOC; with tests (F5): ~135–200 LOC. No execution/safety code touched by any fix.

## 9. Certification impact

- **§1 blockers (B1–B7):** RPC/archive/anvil/executor/outcome-data dependent. Zero impact from IP work — they stay BLOCKED-BY-ENVIRONMENT until credentials/binary are provided. Providing §2 unblocks PAPER/LIMITED_LIVE technical proofs (still gated by operator authorization).
- **IP fixes (F1–F5):** raise the Strategy-Factory-boundary certification from "adequate/contained" to "enforced provenance + defence-in-depth". They do **not** change SHADOW readiness and do **not** unblock any higher mode. Purely governance/hardening.
- **Safety ladder unchanged:** SHADOW = READY; PAPER/LIMITED_LIVE/FULL_AUTOMATION = BLOCKED.

## 10. Final recommended sequence

1. **Now (no env needed):** approve + implement IP governance F1→F4 (+F5 tests) — pure additive, admin-only, advisory, fail-closed. Re-run `test_phase3_strategy_ir*` + new provenance tests.
2. **When read-only Base RPC provided (`ARBICORE_RPC_URL`):** run B1 chain-ID, B2 executor bytecode (needs `ARBICORE_EXECUTOR_ADDRESS_BASE`), B3 atomic eth_call sim, B6 flash-provider on-chain check.
3. **When archive RPC + anvil installed:** run B4/B5 fork lifecycle + deterministic route (A–J) validation.
4. **When historical outcome data provided:** run B7 learning-loop end-to-end (observe→update→rollback + no-future-leakage).
5. **Operator decision only:** any mode promotion above SHADOW — never auto-enabled.

---

**Conclusion.** No critical live security exposure. Proprietary-strategy alpha is already
admin-gated, un-logged, and absent from the frontend; the registry/candidate identity-vs-alpha
split is sound. Remaining Phase 3 blockers are strictly environment/RPC/anvil/outcome-data
dependent and honestly reported fail-closed. The only genuine *design gap* is enforced external
**provenance/originality** (§5, F1). Per directive, **no fix has been implemented — awaiting
your approval.**
