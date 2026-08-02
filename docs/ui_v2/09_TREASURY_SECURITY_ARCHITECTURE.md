# ArbiCore X — Phase II · Treasury & Security Engine Architecture

**Generated:** 2026-07-31
**Purpose:** Design the production architecture for the Treasury & Security
Engine that will back UI v2 Slices 4 and 5, resolve the institutional-audit
P0 gaps (evidence, kill-switch, compliance, transfer approvals), and
consolidate today's scattered treasury logic into one coherent engine.
**Non-goal:** No implementation in this document. No code generation
unless required to demonstrate a gap.

**Reference sources**
- `docs/ui_v2/01_BACKEND_CAPABILITY_AUDIT.md` — canonical layer 5
  (portfolio/treasury/ledger).
- `docs/ui_v2/07_INSTITUTIONAL_AUDIT.md` §5 — treasury & security gaps.
- `docs/ui_v2/08_PREVIEW_TO_PROD_INTEGRATION_AUDIT.md` — endpoint contracts.

---

## 0 · Design principles

1. **Reuse over rebuild.** Every subsystem below has an existing partial
   implementation in the canonical repo. This design formalises boundaries
   and moves logic into the right home, it does not introduce a new
   engine.
2. **Single source of truth per domain.** No sibling service should hold
   authoritative treasury state.
3. **Read/write separation.** Read paths are cached composed endpoints;
   write paths are transactional, audit-logged, and idempotent.
4. **Least secrets exposure.** Secrets never leave the Secret Management
   subsystem. Every other subsystem holds only handles.
5. **Approval-first mutations.** Any state-changing action beyond a
   whitelist requires an Approval Workflow record — even if 1-of-1.
6. **Determinism and reproducibility.** Every mutation writes an Audit
   Log entry that includes enough context to replay the decision.

---

## 1 · Top-level architecture

```
                             ┌────────────────────────────────────────┐
                             │            UI v2 (operator)            │
                             │  Portfolio · Settings · Operations     │
                             └───────────────┬────────────────────────┘
                                             │  REST (already contract-frozen)
                                             ▼
                    ┌────────────────────────────────────────────────┐
                    │       Treasury & Security Engine (T&S)         │
                    │                                                │
                    │  ┌─────────────┐   ┌────────────────────────┐  │
                    │  │  Treasury   │◄──┤  Capital Allocation    │  │
                    │  │  (ledger,   │   └────────────────────────┘  │
                    │  │  vaults,    │              ▲                │
                    │  │  balances)  │              │                │
                    │  └──────┬──────┘   ┌──────────┴──────────┐     │
                    │         │          │  Risk Policies      │     │
                    │         │          └──────────┬──────────┘     │
                    │         │                     │                │
                    │  ┌──────▼───────┐   ┌─────────▼──────────┐     │
                    │  │  Wallet      │   │  Approval          │     │
                    │  │  Registry    │◄──┤  Workflows         │     │
                    │  └──────┬───────┘   └─────────┬──────────┘     │
                    │         │                     │                │
                    │  ┌──────▼───────┐   ┌─────────▼──────────┐     │
                    │  │  Vaults      │   │  Audit Log         │     │
                    │  │  (custody)   │◄──┤  (append-only)     │     │
                    │  └──────┬───────┘   └────────────────────┘     │
                    │         │                                      │
                    │  ┌──────▼───────┐   ┌────────────────────┐     │
                    │  │  Exchange    │◄──┤  Gas Management    │     │
                    │  │  Registry    │   └────────────────────┘     │
                    │  └──────┬───────┘                              │
                    │         │                                      │
                    │         │        ┌────────────────────┐        │
                    │         └───────►│ Secret Management  │        │
                    │                  │ (KMS handle only)  │        │
                    │                  └────────────────────┘        │
                    └────────────────────────────────────────────────┘
                                             │
                                             ▼
                    ┌────────────────────────────────────────────────┐
                    │  Downstream engines (unchanged)                │
                    │  Scanners · Scoring · Execution · Interlock    │
                    └────────────────────────────────────────────────┘
```

The T&S engine is a **read/write facade** that fronts eight cooperating
subsystems, all served by two shared cross-cutting services (Audit Log,
Secret Management). Everything downstream (scanners, execution, interlock)
consumes T&S as a read-only client for balance, deployable capital, and
risk state.

---

## 2 · Subsystem boundaries

The following ten subsystems are the concrete divisions the user asked
for. Each row is fully expanded in §3–§12.

| # | Subsystem | Owns | Consumed by |
|---|---|---|---|
| 1 | Treasury | Ledger entries, vault snapshots, PnL | Portfolio → Ledger, Treasury, Deployable |
| 2 | Wallet Registry | Wallet identifiers, chains, roles | Vaults, Exchange Registry, Transfers |
| 3 | Vaults | Custody + reconciliation of on-chain balances | Portfolio → Treasury, Balances |
| 4 | Exchange Registry | CEX + PERP venue metadata + connectivity | Ops → Venues, Settings → Exchanges |
| 5 | Secret Management | KMS handles, API-key custody, rotation | Every subsystem via opaque handle |
| 6 | Gas Management | Per-chain gas policy + reserves | Execution router, Capital Allocation |
| 7 | Capital Allocation | Deployable snapshot, bucket policy | Portfolio → Deployable, Allocation |
| 8 | Approval Workflows | N-of-M sign, thresholds, quorum | Every mutating T&S endpoint |
| 9 | Audit Log | Append-only mutation record | Ops → Alerts, evidence exports |
| 10 | Risk Policies | Position/notional/venue limits, kill-switch | Interlock, Execution router |

---

## 3 · Treasury (ledger + vaults + PnL)

**Responsibility.** Book of record for every asset movement, PnL
attribution, and reconciled vault snapshot.

**Existing code to reuse**
- `TreasuryLedger` — already appears in the canonical audit as the
  authoritative repository for entries and vaults.
- `ExposureAnalyzer` — reads from Treasury but does not own state.
- `AllocationPolicy` — reads from Treasury.

**Interfaces (read)**
- `TreasuryLedger.entries(kind?, cursor?, limit?)`
- `TreasuryLedger.vault_snapshot()`
- `TreasuryLedger.transfers(status?)`
- `TreasuryLedger.pnl_summary(window)` — new composed method.

**Interfaces (write, all via Approval Workflow)**
- `TreasuryLedger.post_entry(entry)` — internal only; called by
  Execution + Transfer subsystem.
- `TreasuryLedger.reconcile(vault_id)` → returns diff report.

**Missing capabilities**
- **Signed evidence export** (`EvidenceBundle.export(cycle_id)`) — P0.
- **Reconcile diff report** — currently fire-and-forget.
- **Running balance at read** — must move from persisted counter to
  read-time projection (see integration audit §10).
- **Slippage attribution field** on PNL/FEE entries.

**Refinements**
- Add `entry.kind ∈ {PNL, FEE, TRANSFER, DEPOSIT, WITHDRAW,
  RECONCILE_ADJ}`; expand the last for reconcile-diff bookings.
- Add `entry.correlation_id` for cross-subsystem tracing.

---

## 4 · Wallet Registry

**Responsibility.** Address-book. Owns identity, chain, role, and
metadata of every wallet. Never holds keys — points to Secret Management
handles.

**Existing code to reuse**
- Currently split across on-chain scanners' address maps and vault
  configuration. **Consolidation required.**

**Interfaces**
- `WalletRegistry.list(chain?, role?)`
- `WalletRegistry.get(id)`
- `WalletRegistry.roles()` — enum: `treasury`, `hot`, `dex`, `bridge`,
  `staking`, `airdrop`, `disposal`.

**Missing capabilities**
- **Unified registry** — today wallet metadata lives in whichever
  scanner defined it.
- **Chain-aware address validation.**
- **Role transitions** — moving a wallet from `hot` to `treasury`
  should be an approval workflow, not a config edit.

**Refinements**
- Return `wallet.secret_handle` (opaque) — never a key.
- Include `wallet.compliance_flags` populated from Compliance Registry
  (see §12).

---

## 5 · Vaults (custody + reconciliation)

**Responsibility.** For each vault, own its custody model, signer set,
last reconciled state, and reconciliation operation.

**Existing code to reuse**
- Vault snapshot embedded in `TreasuryLedger.vault_snapshot()`.
- Some multisig helper code in the canonical repo (per audit).

**Interfaces**
- `VaultService.list()`
- `VaultService.get(id)`
- `VaultService.reconcile(id)` → `ReconcileReport`
- `VaultService.cosigner_status(vault_id)` — new (institutional audit
  SEC-1).

**Vault kinds & minimum signers**
- `COLD` — 2-of-3 minimum.
- `HOT` — 1-of-1 (constrained by risk-policy caps).
- `MULTISIG` — 3-of-5 minimum.
- `EXCHANGE` — venue custody; 0 signers (external attestation only).

**Missing capabilities**
- **Per-cosigner status** with last-signed timestamp.
- **Reconcile diff** as a structured object, not a log line.
- **Threshold enforcement** at write time (see Approval Workflows).

**Refinements**
- Move vault reconcile from synchronous HTTP to a 202-accepted job
  with a WS/poll status endpoint (integration audit §5 risk).
- Publish reconcile Merkle root to audit log.

---

## 6 · Exchange Registry

**Responsibility.** Metadata + connectivity + credential handles for
every venue (CEX + DEX + PERP). Never plaintext keys.

**Existing code to reuse**
- `VenueRegistry.status_snapshot()` (canonical `/api/venues/status`).
- `VenueRegistry.test_connectivity()`.
- Existing `VenueRegistry.list_configured()`.

**Interfaces**
- `ExchangeRegistry.list()`
- `ExchangeRegistry.test(key)` → connectivity + latency
- `ExchangeRegistry.rotate_key(key)` — new (institutional audit SEC-3).
- `ExchangeRegistry.set_role(key, role)` — via approval.
- `ExchangeRegistry.set_read_only(key, bool)` — via approval.

**Missing capabilities**
- **API-key rotation** as a first-class action.
- **Per-venue role** (`primary`, `secondary`, `excluded`) as
  approval-gated state, not config.
- **Compliance flag join** — mark venues restricted per jurisdiction.

**Refinements**
- Payload must always mask keys (contract test already enforces).
- Add `venue.secret_handle` linking to Secret Management.
- Add rate-limit budget metric.

---

## 7 · Secret Management

**Responsibility.** Single home for every credential: API keys, seed
phrases, HSM PINs, TLS client certs, webhook tokens. Nothing else in
T&S touches raw secrets.

**Existing code to reuse**
- Whatever key store the canonical repo uses today (per audit, likely
  env-var + encrypted-at-rest file or KMS). **Consolidation required.**

**Interfaces (never returns raw secret)**
- `SecretManagement.put(handle, plaintext)` — write-only, no read
  outside subsystem.
- `SecretManagement.rotate(handle)` — generates + stores + returns new
  handle metadata.
- `SecretManagement.use(handle, purpose)` — internal-only surface for
  signing / API calls; scoped by purpose.
- `SecretManagement.metadata(handle)` — safe: last-rotated,
  next-rotation-due, mask.

**Missing capabilities**
- **Unified store.** Today keys leak between env-vars, config files,
  and (worst case) source. Consolidate.
- **Rotation SLA.** Enforce per-secret rotation cadence.
- **Purpose scoping.** A secret configured for `order_place` should
  not be usable for `withdraw`.

**Refinements**
- All handles are opaque UUIDs.
- All secret-adjacent audit-log entries redact any 20+ char alnum
  substring by default.
- Support envelope-encryption if canonical repo uses KMS.

---

## 8 · Gas Management

**Responsibility.** Per-chain gas policy, reserves, and price-feed
strategy. Feeds Execution router with a policy handle; feeds Capital
Allocation with reserve targets.

**Existing code to reuse**
- Whatever the Execution router uses today (per audit, per-chain
  hard-coded values). **Extract into subsystem.**

**Interfaces**
- `GasManagement.policy(chain)` → `GasPolicy`
- `GasManagement.reserves()` → per-chain minimum wallet balance
- `GasManagement.set_policy(chain, policy)` — via approval

**Missing capabilities**
- **Tunable policy** exposed via UI (institutional audit 1.4.4).
- **Automatic top-up trigger** when reserves fall below threshold.
- **Gas oracle multi-source** (RPC + Chainlink + median).

**Refinements**
- Gas policy is versioned; changes are audit-logged.
- Reserves feed into Capital Allocation's deployable-usd calc.

---

## 9 · Capital Allocation

**Responsibility.** Compute deployable capital per venue; enforce
allocation policy per bucket; produce rebalance proposals.

**Existing code to reuse**
- `CapitalRouter.deployable_snapshot()` (canonical `/api/portfolio/deployable`).
- `AllocationPolicy.status()`.

**Interfaces**
- `CapitalAllocation.deployable()` → per-venue snapshot.
- `CapitalAllocation.allocation_status()` → target vs actual by bucket.
- `CapitalAllocation.propose_rebalance()` — new (institutional audit
  1.5.8) → list of suggested transfers.
- `CapitalAllocation.utilisation_pct(venue?)`.

**Missing capabilities**
- **Per-strategy reservations** — today deployable is a scalar per
  venue; production must reflect scanner-family reservations.
- **Rebalance proposals** — one-click hint on Under/Over rows.
- **Utilisation-based back-pressure** — signal into scanners to slow
  down when utilisation > threshold.

**Refinements**
- Must agree with Interlock gate `capital_deployable` — same
  source-of-truth (integration audit 4.4 risk).
- Deployable = venue_balance_usd − gas_reserve_usd − pending_orders_usd
  (formalise in doc + tests).

---

## 10 · Approval Workflows

**Responsibility.** N-of-M sign-off for state-changing operations that
exceed a whitelist. Owns the state machine `PROPOSED →
APPROVED_BY_A → APPROVED_BY_B → EXECUTED / REJECTED / EXPIRED`.

**Existing code to reuse**
- No first-class implementation in canonical repo per audit.
  **New subsystem.** *(This is the one gap that qualifies as "new
  code" under Phase-II rules — the capability genuinely does not
  exist today.)*

**Interfaces**
- `ApprovalWorkflow.propose(op)` → workflow id
- `ApprovalWorkflow.approve(id, actor)` → new state
- `ApprovalWorkflow.reject(id, actor, reason)`
- `ApprovalWorkflow.status(id)`
- `ApprovalWorkflow.list(pending=true)`

**Operations that MUST go through approval**
- Outgoing transfers above threshold (default: > $50k, configurable).
- Vault reconcile that produces a non-zero diff.
- Exchange role change (`primary` ↔ `excluded`).
- API-key rotation.
- Execution policy PATCH on `max_position_usd`, `max_daily_notional_usd`,
  `auto_execute_enabled`.
- Interlock DISARM (two-person confirm).
- Kill-switch trigger (single actor + typed confirm — no quorum, but
  fully audit-logged).
- Operational mode toggles (`maintenance_mode`, `read_only`,
  `trading_paused`).

**Missing capabilities**
- Entire subsystem.

**Refinements**
- Whitelist bypass (small transfers, alert ack, etc.) is configured in
  code, not in DB — reduces DB-driven privilege escalation.
- Expiration policy (24 h default) prevents stale approvals.

---

## 11 · Audit Log

**Responsibility.** Append-only record of every mutation across T&S
(and, ideally, execution). Signed at bundle export; queryable by
correlation ID.

**Existing code to reuse**
- `DecisionAuditLog` (verdicts) — narrower scope, but same shape.
  Reuse the storage engine.

**Interfaces**
- `AuditLog.append(entry)` — internal only, never HTTP.
- `AuditLog.query(cursor?, filters?)` — Ops → Alerts + evidence
  bundling.
- `AuditLog.bundle(cycle_id | opp_id)` → materials for signed
  evidence export.

**Missing capabilities**
- **Cross-subsystem coverage** — today only decisions are audit-logged.
- **Signed bundle export** — the P0 evidence gap.
- **Correlation ID discipline** — every mutation must include the
  originating request's correlation ID.

**Refinements**
- Storage: append-only Mongo collection with time-based partition +
  weekly Merkle root written to Treasury Ledger for tamper-evidence.
- Retention: 7 years (regulatory default), configurable.
- PII redaction rules applied at write, not at read.

---

## 12 · Risk Policies

**Responsibility.** Own the enforceable limits and produce the "would
this pass?" answer for any proposed action.

**Existing code to reuse**
- `SafetyInterlock.snapshot()` + gates.
- `ExecutionPolicy` (Slice 5 settings back-end).
- Various per-scanner threshold configs.

**Interfaces**
- `RiskPolicies.evaluate(action)` → `{allowed, gates_passed, gates_failed}`
- `RiskPolicies.limits()` — current effective limits (position, notional,
  per-venue, per-asset).
- `RiskPolicies.compliance_flags(target)` — new (see below).
- `RiskPolicies.kill_switch(reason)` — new (institutional audit SEC-5).
- `RiskPolicies.emergency_state()` — is the system currently in
  post-kill-switch state?

**Missing capabilities**
- **Compliance flags per venue/asset** (institutional audit 1.6.7 /
  SEC-4).
- **Global kill-switch API** — endpoint + WS broadcast to every live
  session.
- **Per-venue notional cap** — today only global caps exist.
- **Per-asset concentration limit** — today only bucket allocation.

**Refinements**
- Every risk-policy evaluation is audit-logged including the input
  action shape.
- `evaluate` is idempotent and side-effect free — safe to call from
  UI as a "would this work?" precheck (basis for approval-workflow UX).

---

## 13 · Cross-cutting concerns

### 13.1 Idempotency
Every mutating endpoint accepts an `Idempotency-Key` header. Approval
Workflow uses this to de-dupe re-submissions across UI reloads.

### 13.2 Correlation IDs
UUID generated at HTTP-ingress; propagated through every subsystem
call; written to Audit Log; surfaced in UI toasts and Ops → Alerts.

### 13.3 Read-model caching
Read endpoints (`deployable`, `allocation`, `exposure`, `positions`,
`balances`, `treasury`, `vaults`) are composed and 60 s cached per
actor. Cache is invalidated at write.

### 13.4 Testing
- Unit tests per subsystem (business rules).
- Contract tests per HTTP endpoint (already exist for Slices 0–5).
- Integration tests: `evaluate → propose → approve → execute → audit`.
- Chaos tests: partial-failure of each subsystem must degrade to
  read-only, never silent-corrupt.

### 13.5 Deployment posture
- T&S engine deploys as part of the existing backend container. No new
  process boundary. No new database — reuse existing Mongo + KMS.
- Feature flag `TS_ENGINE_ENABLED` for staged rollout.

---

## 14 · Endpoint alignment (what the UI will see)

No UI contract change is required. The engine sits behind the same
routes the Preview→Prod audit already documents. What changes is:

- Every write endpoint now returns an approval workflow id when the
  action crossed the threshold (existing UI can ignore this field;
  future UI additions render it).
- Every response carries a `correlation_id` (existing UI can ignore).
- Approval-required responses may return 202 with `Retry-After` or
  a workflow status URL.

Detailed contract deltas are captured in the Preview→Prod audit CX-A
through CX-H.

---

## 15 · Ownership map (recommended)

| Subsystem | New service module | Existing repo module to absorb |
|---|---|---|
| Treasury | `arbicore/treasury/ledger.py` | `TreasuryLedger` (existing) |
| Wallet Registry | `arbicore/treasury/wallets.py` | scattered address maps |
| Vaults | `arbicore/treasury/vaults.py` | vault snapshot in ledger |
| Exchange Registry | `arbicore/treasury/exchanges.py` | `VenueRegistry` |
| Secret Management | `arbicore/security/secrets.py` | env-var + config file (consolidate) |
| Gas Management | `arbicore/execution/gas.py` | inline gas constants |
| Capital Allocation | `arbicore/treasury/capital.py` | `CapitalRouter` + `AllocationPolicy` |
| Approval Workflows | `arbicore/security/approvals.py` | **new** |
| Audit Log | `arbicore/security/audit.py` | `DecisionAuditLog` (extend) |
| Risk Policies | `arbicore/security/risk.py` | `SafetyInterlock` + `ExecutionPolicy` |

---

## 16 · Open questions for the user

1. **Approval-workflow quorum defaults.** Two-of-N for outgoing
   transfers above $50k — is $50k the right threshold for
   Wave-A production posture?
2. **Kill-switch policy.** Single-actor typed-confirm is proposed —
   should this require the same MFA re-prompt used at login?
3. **Compliance registry source.** Is there a jurisdiction database
   already in-house, or should this subsystem stand up its own from
   a public feed (e.g., OFAC + FCA + MAS)?
4. **Retention window.** 7 years is the regulated default; confirm
   for the deployment jurisdiction.
5. **Hardware key requirement.** Does the deployment target require
   HSM-backed signing for outgoing vault transfers? If yes, the
   Approval Workflow → Secret Management interface must go through
   a hardware attestation step, not just KMS handles.

---

## 17 · Deliverable status

- [x] Ten subsystem boundaries defined with responsibilities.
- [x] Existing code to reuse identified per subsystem.
- [x] Missing capabilities enumerated per subsystem.
- [x] Cross-cutting concerns spelled out.
- [x] Ownership map ties subsystems to canonical module paths.
- [ ] Open questions answered by user — pending.

No implementation performed. No code generated except the module-path
recommendations in §15.
