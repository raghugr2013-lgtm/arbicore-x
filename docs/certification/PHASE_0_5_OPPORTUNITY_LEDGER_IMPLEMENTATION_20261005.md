# Phase 0.5 — Opportunity Ledger v1 implementation

**Classification: PHASE_0_5_LEDGER_IMPLEMENTATION_PASS**

**Date:** 2026-10-05

The ledger is a stored projection of a discovery candidate, an optional m2.3 verifier bundle, and `observe_strategy_intelligence`. It is not wired into the scanner, the verifier, the API, or the frontend. Nothing in this change starts a process or writes the production database.

No historical backfill was performed. The October 5 candidate and bundle documents were not modified. No SHADOW window was opened. No PAPER run was started. No LIVE execution was started. No commit and no push were made.

---

## Baseline commit

| | |
|---|---|
| Worktree HEAD | `9ed2718b3550066934bd11e99a96503ce75a499f` (`fix(flash-loan): accept a missing BNB chain key and scope providers`) |
| Certified runtime commit | `823a79b617ddb1f19397cf5073b9c516aae4e9fd` (`feat: add strategy intelligence and economics observability phase 0`) |
| Relationship | `9ed2718` is an ancestor of `823a79b` |
| Implementation commit | **None.** Commit was not requested. |

The Phase 0 package is not on `9ed2718`. It was taken from `823a79b` only:

- `app/backend/arbicore/observability/`
- `app/backend/tests/test_phase0_strategy_intelligence.py`

Those files match that commit. Other files `823a79b` also touches (`discovery_queue.py`, `discovery.py`, `composition.py`, and the emergent queue tests) were not checked out. The pre-existing dirty copies of the first three stayed as they were.

Running container, read before and after this change:

| Check | Before | After |
|---|---|---|
| Container | `arbicore-x-backend-new` | same |
| Image | `arbicore-x-backend:phase0-823a79b` | same |
| Container id | `096bcb87b121…d279ea33` | same |
| Started | `2026-10-04T15:14:34.569825639Z` | same |
| PID | `2823992` | same |
| Restart count | `0` | `0` |
| `ARBICORE_EXECUTION_MODE` | `SHADOW` | `SHADOW` |
| `ARBICORE_RUNTIME_AUTOSTART` | `false` | `false` |
| `ARBICORE_AUTOEXEC_AUTOSTART` | `false` | `false` |
| `SIGNING_ACTIVE_KEY_VERSION` | unset | unset |
| Network Config revision | `rev-1068cb9715194f118c99e5f04f9e1bdb` | same |
| Network Config `updated_at` | `2026-10-04T14:24:36.649620+00:00` | same |
| Scanner state `enabled` | six rows, all `false` | six rows, all `false` |
| Certification `shadowcert-5605e7b9-…` | `ABORTED` | `ABORTED` |
| Collection `arbicore_opportunity_ledger` | absent | absent |

RPC URL values were not read into this report.

---

## Files changed

Added for the ledger:

| Path | Role |
|---|---|
| `app/backend/arbicore/opportunity_ledger/__init__.py` | Public exports |
| `app/backend/arbicore/opportunity_ledger/identity.py` | Deterministic ids and mode label |
| `app/backend/arbicore/opportunity_ledger/project.py` | Projection through the Phase 0 observer |
| `app/backend/arbicore/opportunity_ledger/repo.py` | Idempotent upsert of that projection |
| `app/backend/tests/test_opportunity_ledger_v1.py` | Focused tests, in-memory collection only |

Restored from `823a79b` so the ledger can call the existing classifier rather than a new one:

| Path | Role |
|---|---|
| `app/backend/arbicore/observability/__init__.py` | `observe_strategy_intelligence`, `CLASSIFIER_VERSION` |
| `app/backend/arbicore/observability/economics_observation.py` | Stored-field economics reader |
| `app/backend/arbicore/observability/fields.py` | Available / unavailable / not-persisted envelope |
| `app/backend/arbicore/observability/record.py` | Observer entry point |
| `app/backend/arbicore/observability/taxonomy.py` | `phase0.strategy_intelligence.v1` |
| `app/backend/tests/test_phase0_strategy_intelligence.py` | Existing Phase 0 and Gate 7 regression |

Not modified: scanner, route search, quote provider, verifier, economics assessor, Gates 7/8/9, risk controls, kill switch, SHADOW controller, signer, broadcaster, wallet, RPC, Network Config, frontend, Excel, learning engine. The dirty worktree files outside this list were left untouched.

The ledger is not imported by `composition.py`, `server.py`, or the scanner. Calling `project_opportunity_ledger` does not write. `OpportunityLedgerRepo.upsert` writes only the collection it was constructed with. Tests construct an in-memory collection. Production was not given that call.

---

## Schema / model

Collection name, when a later gate writes it: `arbicore_opportunity_ledger`.

Schema version: `opportunity_ledger.v1`.

| Field | Meaning |
|---|---|
| `ledger_id` | Deterministic primary key |
| `opportunity_id` | Existing source id, see derivation |
| `run_id` | Caller-supplied certification or research run |
| `mode` | Evidence label. Not an execution switch |
| `candidate_id` | Discovery candidate id |
| `verifier_bundle_id` | Bundle `bundle_id`, or null |
| `evidence` | Strategy, legs, economics, gates, provenance |
| `annotations` | Empty object on insert. Upsert does not write this field |
| `projected_at` | Projection clock. Not part of the identity |

`evidence.strategy` stores `primary_family`, `secondary_tags`, `confidence`, `evidence`, `classifier_version`, `classification_completeness` (`strategy_completeness` from the observer), and `classification_state`.

Modes with a defined name in this version: `SHADOW`, `PAPER`, `RECOMMENDATION`. `normalize_mode` also accepts another uppercase identifier so a later research label can be stored without a schema migration. Accepting the label does not start that mode. Lowercase and any string containing a URL are rejected.

`OCTOBER_5_SHADOW_RUN_ID` is the constant `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065`. Callers pass it. The projector does not query the certification collection and does not stamp that id onto unrelated rows.

---

## Identity derivation

`candidate_id` and `run_id` must match `^[A-Za-z0-9_.:-]{1,200}$`.

`opportunity_id`:

1. The bundle field `opportunity_id` when it is a non-empty safe identifier. That is the confirmed canonical id (`flash_loan_arb:{subject_id}:{int(timestamp)}` on the confirm path).
2. Otherwise `candidate_id`. Denied rows store null on the bundle, so the ledger uses the discovery id that already exists. A new random id is not created.

`candidate_id` remains the 60-second discovery hash from `make_candidate_id`. The ledger does not replace that rule.

`ledger_id` is `ol1:{mode}:{run_id}:{candidate_id}`.

The same candidate, run, and mode produce the same `ledger_id` on every projection. A second projection updates that one row. It does not insert another.

---

## Source linkage

Each row points at the sources by id:

`ledger_id` → `candidate_id` → `verifier_bundle_id` (null when there is no bundle) → `evidence.strategy.classifier_version` → `run_id`.

The row does not embed the candidate document or the bundle document. Phase 0 output is the strategy block produced by `observe_strategy_intelligence(bundle, candidate)`. Economics and gates are the observer's available values plus the gate objects already stored on the bundle.

---

## Field availability behavior

An observer field is copied only when its status is `available`. Available zero is stored as zero. `unavailable` and `AVAILABLE_NOT_PERSISTED` are stored as null. `total_cost_usd` has no stored source and is always null. The projector does not add fee, gas, and slippage together.

Per-leg `quote` is null. The hop record's price is null, and the observer does not emit a price. `quote_timestamp` is null because no per-leg quote time is stored. `fee_bps`, wei amounts, protocol, venue, pool, block, and source id are copied when the observer marks them available. Leg order follows `hop_index`.

`rpc_identity` is always null. RPC URLs are not read.

---

## Idempotency behavior

`OpportunityLedgerRepo.upsert` filters on `ledger_id`.

- `$set` writes the projection fields.
- `$setOnInsert` sets `annotations` to `{}`.
- A later upsert does not include `annotations`, so a note written there remains.

Unique index requested: `ledger_id`. Secondary index: `(run_id, candidate_id)`.

Tests use an in-memory collection. They do not open a Mongo client.

---

## Phase 0 integration

The only classifier call is `observe_strategy_intelligence` from `arbicore.observability`, version `phase0.strategy_intelligence.v1`.

`classify_strategy` in `strategy_tagging.py` is not called. A closed three-hop token path with pools and no per-leg protocols is stored as `UNCLASSIFIED` / `INCOMPLETE`. The letter shape is not promoted to `TRIANGULAR`.

A two-hop closed path with two pool ids and protocols `uniswap_v3` and `aerodrome_slipstream` is stored as the observer's `DEX_TO_DEX`.

---

## Economics preservation behavior

On the complete-bundle fixture:

| Field | Stored |
|---|---|
| `flash_loan_fee_usd` | `0.0` |
| `slippage_pct` | `0.0` |
| second-leg `fee_bps` | `0` |
| `notional_usd` | `10000.0` |
| `true_net_usd` | `-59.31` (stored `atomic_profit_usd`) |
| `gross_profit_usd` | null |
| `dex_fee_usd` | null |
| `true_net_pct` | null |
| `mev_penalty` | null |
| `total_cost_usd` | null |

On the decision-only fixture, notional, gross profit dollars, and true net are null. The decision net `-146.87` is the observer's parse of the stored Gate-7 sentence, not a new calculation. Gate objects are null because there is no bundle.

---

## Gate preservation

The bundle's `gates.gate_7`, `gate_8`, and `gate_9` status and reason are copied. The fixture keeps `FAIL` / `atomic_profit $-59.31 < floor $25.00`, and Gates 8 and 9 as `NOT_EVALUATED`. `final_observed_status` is the candidate `verified_outcome` string.

No normalized kill-code taxonomy was added.

`FlashLoanGate7AtomicProfit` with empty thresholds still fails `24.99` with `atomic_profit $24.99 < floor $25.00` and passes `25.0` with `atomic-profit gate passed`. The gate module was not edited.

---

## Security / secrets handling

Copied strings are dropped when they contain a URL, a Mongo URI, a private-key banner, or a JWT-shaped token. The replacement is null. `secrets_withheld` becomes true. The dropped text is not stored in the flag.

`git_sha` is kept only when it is 7–40 hex characters. `network_config_revision` is kept only when it matches `rev-` plus 8–64 hex characters. Anything else, including a URL, is stored as null.

`hint_metric.rpc_url` is not a copied field. A test places `supersecretvalue` in the chain, the outcome string, and a git URL. The serialized row does not contain that token, `mongodb://`, or `alchemy.com`.

---

## Tests executed

Interpreter: `/home/raghu/projects/arbicore-x-v2/.venv/bin/pytest`, `PYTHONPATH` set to this worktree's `app/backend`. xdist addopts disabled. No production Mongo.

**39 passed** in 3.39s.

| Module | Result |
|---|---|
| `tests/test_opportunity_ledger_v1.py` | 9 passed |
| `tests/test_phase0_strategy_intelligence.py` | 22 passed, including `test_gate7_and_gate8_thresholds_unchanged` and `test_observer_does_not_invoke_the_economics_formula` |
| `tests/test_t0_correctness.py::test_gate7_floor_is_still_25` | passed |
| `tests/test_m5_canonical_activation.py::test_gate7_floor_still_25` | passed |
| `tests/test_m2_3_evidence_bundle.py` | 6 passed, including Gate 7 denial, Gate 8 denial, and `venue_unreadable` |

Ledger cases covered: deterministic `opportunity_id`, same source identity, idempotent upsert, annotation retention, decision-only null economics, bundle plus Phase 0 persistence, explicit zero, missing economics as null, Gate-7 reason text, `run_id`, secret redaction, leg order, and no family assignment without protocol evidence.

---

## Regression results

Gate 7 floor and reason text are unchanged in the new test and in the existing Phase 0, T0, M5, and M2.3 modules above. Verifier, economics, and gate source files were not part of this diff.

---

## Safety verification

After the tests:

- Container id, image, start time, PID, and restart count are unchanged.
- Execution mode is still `SHADOW`.
- Runtime and autoexec autostart are still `false`.
- Signing active key version is still unset.
- Network Config revision and `updated_at` are unchanged.
- All six scanner-state rows are still `enabled: false`.
- The October 5 certification document is still `ABORTED`.
- `arbicore_opportunity_ledger` does not exist in the production database.

No scanner was resumed. No SHADOW window was opened. No deploy and no restart. No RPC, Network Config, gate, wallet, signer, or broadcaster change.

---

## Explicit statements

No historical production backfill occurred. The October 5 discovery candidates and evidence bundles were not updated.

No SHADOW, PAPER, or LIVE activity occurred. The ledger mode field is a label on a document. This implementation does not start those modes.

PHASE_0_5_LEDGER_IMPLEMENTATION_PASS
