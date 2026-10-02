# ArbiCore X — Changelog

## 2026-06 · Gate 9 parallel engineering workstream (isolated branch)

**Branch:** `engineering/gate9-parallel-93a20c9` (off certified `93a20c9`, which contains H06 `7c2b1bc`).
**Gate 9 VPS:** untouched throughout (workspace-only; pod has no VPS access). No history rewrite, no push.

### Workstream A — Base failover / HTTP-429 remediation (CODE)
- Root cause proven (RED test): `EthJsonRpcProvider._call` treated HTTP 429 like 5xx, retrying the
  same rate-limited host up to `ARBICORE_RPC_MAX_RETRIES` (4–5 POSTs) → Alchemy 429 amplification after
  `-32016` failover from public Base RPC.
- Minimal delta (inside existing provider abstraction; no new subsystem/registry change):
  - `ARBICORE_RPC_MAX_RETRIES_429` (default 1) — 429 retry budget split from 5xx/network/malformed.
  - `ARBICORE_RPC_RATE_LIMIT_COOLDOWN_S` (default 60) — per-host cooldown after a 429; `_call`-entry
    gate fails fast (retryable, no POST) so the registry fails over to a valid alternate.
- Preserved: provider abstraction/ordering, fail-closed, quote/economic/opportunity semantics. 429s
  never hidden, never converted to a success.
- Tests: NEW `tests/test_base_failover_429_amplification.py` (6, RED→GREEN incl. registry-level
  `-32016 → bounded Alchemy → valid alternate`); updated `tests/test_rpc_reliability.py` 429-exhaustion
  assertion to the bounded contract. 17 focused passed; 83 passed / 2 pre-existing infra failures
  (MONGO_URL) — zero regression.
- Commit `2b86cdab115223d69a48aeefd4d434dd094eee1e` (parent `f096249`).
- Bundle `/app/artifacts/workstream-a-base-failover-2b86cda.bundle`
  SHA256 `83abc1770b1e7a6628984b61880aacbbc62f0513a46466f4996ae8dd95cd4446`.

### Tooling (separate commit)
- `chore(tooling)` ESLint ignore globs made location-independent (nested `arbicore-x/app/frontend/src`
  was crashing the pre-completion linter). No engine behaviour. Commit `f0962490c10191ac74677fd0efc60b31df9c4b18`.

### Workstreams B / C / D — read-only audits (DOCS, no code)
- B `artifacts/WORKSTREAM_B_capability_delta_plan.md` — every capability already exists; nothing
  rebuilt/reclassified. Minor frozen TRIANGULAR live-loop wiring gap. Cross-chain execution: do not build.
- C `artifacts/WORKSTREAM_C_economic_evidence_audit.md` — verifier+assessor+evidence bundle already
  reconstruct the decision; no new engine/schema. Optional post-Gate9 read-only reproducibility check only.
- D `artifacts/WORKSTREAM_D_promotion_architecture_audit.md` — ladder OBSERVE→PAPER→SHADOW→LIMITED_LIVE
  →FULL_LIVE is real, one-step-forward, broadcast-gated to LIMITED_LIVE+. No Recommendation Mode needed.
  Future human-authorization gate documented, frozen.
- Docs commit `5a143a8667484cd9e4a765d55079265936925695`.
- Combined branch bundle `/app/artifacts/workstream-abcd-5a143a8.bundle`
  SHA256 `3ace63824f88138376545eb597e1eff7899979dc600808682504a24a7962a3c5`.

**Status:** awaiting independent Cursor certification of the above commits/bundles after Gate 9.
No code in B/C/D; no live execution; SHADOW posture unchanged.
