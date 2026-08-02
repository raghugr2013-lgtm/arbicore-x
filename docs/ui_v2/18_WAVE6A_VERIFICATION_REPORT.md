# Wave 6A · Verification Report — Wallet Registry · Treasury Substrate · Secret Management

**Date:** 2026-07-31  
**Wave:** 6A of the Execution Roadmap  
**Philosophy applied:** VERIFY → REUSE → REFINE → ACTIVATE → MERGE → NEW

---

## 1 · What shipped

| Component | Disposition | Files | LOC |
|---|---|---|---|
| **Per-strategy Execution Mode Ladder** (5-stage: `OBSERVE → PAPER → SHADOW → LIMITED_LIVE → FULL_LIVE`) | NEW (substrate; leverages canonical `services/execution/config.py` flag pattern) | `/app/backend/arbicore/execution/mode.py` | 210 |
| **Wallet Registry** — execution-role-aware, chain-aware | REFINE of canonical `arbicore/data/wallet_profile_repo.py` (added `execution_role`, `whitelisted_venues[]`, `chain`, `secret_handle_id`) | `/app/backend/arbicore/execution/wallet_registry.py` | 165 |
| **Secret Registry** with pluggable backend | REUSE of canonical Fernet vault (`services/vault.py::VAULT_KEY`) + NEW pluggable interface for future HSM/KMS/Fireblocks | `/app/backend/arbicore/secrets/backends.py` + `registry.py` | 240 |
| **12 read-only REST endpoints** (mode / wallets / secrets + audit history) | NEW exposures | `/app/backend/server.py` (additive only) | ~180 |

**Zero code was rewritten** — canonical Wave-1..5 endpoints, workers, and schemas are untouched.

---

## 2 · Approved decisions honoured

| Decision | Implementation |
|---|---|
| Fernet-encrypted vault for MVP | `FernetSecretBackend` (default provider) uses the operator's existing `VAULT_KEY` env — no new key material lifecycle introduced |
| HSM/KMS-compatible architecture | `SecretBackend` Protocol with `SecretRegistry.register_backend(...)` — future HSM/KMS/Fireblocks/Turnkey backends drop in without changing business logic |
| Base as MVP chain | `SUPPORTED_CHAINS = ("base", "ethereum", "arbitrum", "optimism", "polygon")`; `chain="base"` is the wallet-registry default |
| Private-relay pluggability | Deferred to Wave 6C per the plan (no premature coupling) |
| Conservative capital allocation | Deferred to Wave 6D (Wave 6A is purely substrate) |
| 5-stage promotion ladder, no direct promotion | `validate_transition()` enforces: forward must be exactly one step; backward may skip any distance (rollback always allowed); unknown modes rejected; noop is idempotent |
| Deploy defaults | `default_mode_map()` seeds `flash_loan_arbitrage=SHADOW` and every other trading strategy in `TRADING_STRATEGIES=PAPER`. Startup hook `_seed_execution_substrate` populates `db.execution_mode_state` idempotently |

---

## 3 · Endpoints exposed (all read-only + audited transitions)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/arbicore/execution/mode` | Full per-strategy mode map + ladder + defaults |
| GET | `/api/arbicore/execution/mode/{strategy}` | Single-strategy state + `broadcast_allowed` derivation |
| POST | `/api/arbicore/execution/mode/{strategy}` | Ladder-validated transition (returns `error` field on rejection; audits every acceptance) |
| GET | `/api/arbicore/execution/mode/audit/history` | Transition audit trail |
| GET | `/api/arbicore/execution/wallets` | Wallet registry list with chain/role filters |
| GET | `/api/arbicore/execution/wallets/{wallet_id}` | Single-wallet lookup |
| POST | `/api/arbicore/execution/wallets` | Register wallet; validates address / chain / role; rejects `secret_handle_id` on non-gas roles |
| PATCH | `/api/arbicore/execution/wallets/{wallet_id}/role` | Role change; scrubs `secret_handle_id` on downgrade from `gas`; audited |
| GET | `/api/arbicore/execution/wallets/audit/history` | Wallet-lifecycle audit trail |
| GET | `/api/arbicore/execution/secrets` | List of handles — **metadata only** (`cipher`/`plaintext` never leak) |
| GET | `/api/arbicore/execution/secrets/status` | Backend availability, default provider, capability scopes |

**Not exposed** (by design): any endpoint that could return plaintext secret material. `SecretRegistry.resolve()` is Python-only, callable exclusively from a future in-process signer flow.

---

## 4 · Verification

| Layer | Result |
|---|---|
| Local pytest (main-agent-authored) | **51 new tests · 251/251 total green** |
| External URL — testing_agent regression | **21/21 Wave-6A HTTP tests green · 4/4 backward-compat endpoints intact** |
| Ladder invariant | ✅ verified end-to-end (forward skip rejected with `"skips the ladder"`, unknown mode rejected, missing `to_mode` rejected, rollback allowed at any distance) |
| Security invariant | ✅ verified — no `cipher` or `plaintext` string appears in any REST response body |
| Deployment posture | ✅ `flash_loan_arbitrage=SHADOW`, all other trading strategies `PAPER`, `broadcast_allowed=false` for all shipped defaults |
| Backward compatibility | ✅ Wave-1..5 endpoints unchanged (`/intelligence/calibration`, `/weights/current`, `/evidence/status`, `/decisions` all still 200 with contracted shapes) |

testing_agent report: `/app/test_reports/iteration_6.json` — `retest_needed: false`, `should_main_agent_self_test: false`, `success_rate.backend: 100%`, zero critical/minor issues.

---

## 5 · What is deliberately deferred

| Deferred to | Item |
|---|---|
| Wave 6B | Flash-loan adapter + on-chain transaction builder |
| Wave 6C | On-chain simulation + gas estimation refinement + MEV interface (pluggable) |
| Wave 6D | Capital-allocation policy engine + live signer (consumes Wave-6A wallet registry + secret registry) + kill-switch UI |
| Wave 6E | Limited-live flash-loan execution + operator approval integration + gas-wallet integration + execution-readiness certification |

Wave-6A intentionally holds Wave-3/4/5 discipline: no coupling to unwritten waves. When the live signer arrives in 6D it consumes a `SecretHandle` (already produced by the current registry) — no re-architecture required.

---

## 6 · Compliance with engineering philosophy

| Principle | Evidence |
|---|---|
| **VERIFY** | Canonical `services/execution/config.py::shadow_enabled/execution_enabled/wallet_enabled/hard_freeze` reviewed; existing `services/vault.py` Fernet substrate reused verbatim; existing `arbicore/data/wallet_profile_repo.py` shape informed the refined schema |
| **REUSE** | `VAULT_KEY` env, Fernet primitives, canonical audit-log pattern, Wave-3/4/5 repo lifecycle template |
| **REFINE** | Wallet registry schema extended with 4 execution-critical fields without touching profiling / scoring |
| **ACTIVATE** | Mode-ladder substrate makes the previously binary `execution_enabled` flag operational per-strategy |
| **MERGE** | No duplicate implementations introduced |
| **NEW** | Only three additive files: `mode.py`, `wallet_registry.py`, `secrets/*` — kept minimal (615 LOC total) |

---

## 7 · Ready for Wave 6B approval

Wave 6A is production-ready in the substrate sense: it defines the contracts that Waves 6B–6E consume. Nothing in Wave 6A can broadcast on-chain, sign a transaction, or move funds — the substrate is deliberately inert. Wave 6B (Flash-Loan Adapter + Transaction Builder) can begin as soon as this report is approved.
