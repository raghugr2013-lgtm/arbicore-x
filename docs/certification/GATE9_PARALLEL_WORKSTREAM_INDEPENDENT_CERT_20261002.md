# Gate 9 Parallel Workstream — Independent Certification

- **Date (UTC):** 2026-10-02T10:27:41Z
- **Cert workspace:** `/home/raghu/projects/arbicore-x-cert`
- **Auditor posture:** READ-ONLY vs Gate 9; no deploy; no Gate 9 restart/config; no bundle import to production
- **STOP:** Neither Emergent bundle was deployed. Gate 9 runtime was not modified.

---

## Final verdicts

| Stream | Verdict | Reason |
|---|---|---|
| **Workstream A** (Base failover engine `2b86cda`) | **BLOCKED** | Claimed bundle absent on cert host; commit objects absent locally and on `origin`; ancestry / SHA256 / changed-files / tests unverifiable |
| **Workstreams B/C/D** (docs `5a143a8`) | **BLOCKED** | Claimed combined bundle absent; docs commit unverifiable; Emergent audit text not inspectable |

Independent spot-checks of B/C/D *themes* against prior VPS certification docs/code are recorded below as **informational only** — they do **not** lift the BLOCKED verdict for the Emergent docs commit.

---

## Gate 9 VPS untouched (explicit)

Read-only `docker inspect` / `docker exec` source probe only. No restart, recreate, config edit, image rebuild, or deploy.

| Check | Value |
|---|---|
| Container | `arbicore-x-backend-new` |
| Status | `running` (healthy) |
| StartedAt | `2026-10-02T06:19:33.513948555Z` (**unchanged** from prior audits this campaign) |
| RestartCount | **0** |
| Image | `arbicore-x-backend:g5.79-green-20260927` |
| Id | `446ed354ec5606142cd36afe86987276ea0774a096ad8d301ebc4d988f8d7b91` |
| Running quoter path | Still **OLD_FULL_BUDGET** (`mr = None if ci == n - 1 else 1`); **no** workspace cooldown / failover-candidate-bound code in Gate 9 image |

Campaign posture (not modified by this cert): SHADOW on / AUTOEXEC off / signing=0 / broadcast=0 — verified by non-interference only (no config writes).

---

## Bundle path search (exhaustive)

Claimed Emergent paths (historical pattern: Emergent agent FS `/app/artifacts/...`):

| Path | Result |
|---|---|
| `/app/artifacts/workstream-a-base-failover-2b86cda.bundle` | **ABSENT** (`/app` does not exist on this host) |
| `/app/artifacts/workstream-abcd-5a143a8.bundle` | **ABSENT** |
| `/home/raghu/projects/arbicore-x-cert/artifacts/workstream-a-base-failover-2b86cda.bundle` | **ABSENT** |
| `/home/raghu/projects/arbicore-x-cert/workstream-a-base-failover-2b86cda.bundle` | **ABSENT** |
| `/home/raghu/projects/arbicore-x-cert/artifacts/workstream-abcd-5a143a8.bundle` | **ABSENT** |
| `/home/raghu/projects/arbicore-x-cert/workstream-abcd-5a143a8.bundle` | **ABSENT** |
| `/tmp/workstream-a-base-failover-2b86cda.bundle` | **ABSENT** |
| `/tmp/workstream-abcd-5a143a8.bundle` | **ABSENT** |

Broader search (`find` over `/home/raghu`, `/tmp`, `/app`, `/var/tmp`, `/opt`, `/srv`, `/data`, `/mnt`, `/media`; name patterns `workstream*.bundle`, `*2b86cda*`, `*5a143a8*`, `*gate9-parallel*`, `*base-failover*.bundle`):

- **0** matching workstream bundles
- **0** files named with `2b86cda` or `5a143a8`
- Existing unrelated bundles only (phase-a/b H05/H06, etc.) — none match claimed SHA prefixes `83abc177…` / `3ace6382…`

Git object probe:

| Object | Local cert repo | `arbicore-x-v2` / `arbicore-x-vps-cert` / legacy | `git ls-remote origin` |
|---|---|---|---|
| `2b86cda` | not a valid object | absent | no matching tip / branch |
| `f096249` | not a valid object | absent | no matching tip / branch |
| `5a143a8` | not a valid object | absent | no matching tip / branch |
| `refs/heads/engineering/gate9-parallel-93a20c9` | n/a | n/a | **empty** (branch not on origin) |

**Conclusion:** Artifacts remain on Emergent’s isolated `/app/artifacts` filesystem and were **not** transferred to the certification VPS (same failure mode previously seen when `/app/artifacts/phase-b-h06-*.bundle` was claimed before a workspace copy existed).

---

## Workstream A — verification checklist (all blocked)

Claimed:

- Branch: `engineering/gate9-parallel-93a20c9`
- Engine commit: `2b86cda` · parent: `f096249`
- Bundle: `workstream-a-base-failover-2b86cda.bundle`
- SHA256: `83abc177…cd4446` (truncated claim; full digest not supplied to cert host)

| # | Check | Result |
|---|---|---|
| — | Bundle present + SHA256 | **BLOCKED** — file missing; cannot hash |
| — | Ancestry `f096249` → `2b86cda` | **BLOCKED** — cannot import / `git rev-parse` / parent walk |
| — | Changed files vs parent | **BLOCKED** — no tree |
| 1 | RED test proves prior retry amplification | **BLOCKED** — tests not available |
| 2 | Implementation limited to `EthJsonRpcProvider` | **BLOCKED** — cannot list changed files; see architecture note |
| 3 | `ARBICORE_RPC_MAX_RETRIES_429` default **1** | **BLOCKED** |
| 4 | `ARBICORE_RPC_RATE_LIMIT_COOLDOWN_S` default **60s** | **BLOCKED** |
| 5 | HTTP 429 cooldown / fail-fast | **BLOCKED** |
| 6 | Provider ordering preserved | **BLOCKED** |
| 7 | Fail-closed preserved | **BLOCKED** |
| 8 | Economic gates untouched | **BLOCKED** |
| 9 | No signing / broadcast / mode changes | **BLOCKED** |
| 10 | 17 focused tests + broader suite claim | **BLOCKED** — no throwaway docker test run possible without source |

No TEMP detached clone was created under `/tmp/...` because there is nothing to `git bundle unbundle` / `git fetch` from.

### Architecture discrepancy vs prior VPS root-cause (CONDITIONAL note)

Prior independent Gate 9 root-cause (`docs/certification/BASE_ALCHEMY_429_ROOT_CAUSE_20261002.md`) classified the amplifier as:

> **RETRY/FAILOVER BUG** in `QuoterRegistry` / `execution/quoter.py`: last failover candidate uses full `_RPC_MAX_RETRIES` (default 4 → ~5 POSTs), no HTTP 429 host cooldown; ProviderRegistry circuit breaker **not** consulted by the quote path.

Live evidence: ~5.025 Alchemy POSTs per quoter failover.

Emergent Workstream A is **claimed** as an `EthJsonRpcProvider`-scoped fix (`providers/rpc.py`) with knobs `ARBICORE_RPC_MAX_RETRIES_429` / `ARBICORE_RPC_RATE_LIMIT_COOLDOWN_S`.

| Path | Touches proven ampifier? |
|---|---|
| `QuoterRegistry._eth_call` / `quote_route` last-candidate budget | **Yes** (this is the measured path) |
| `EthJsonRpcProvider._call` (ProviderRegistry) | **Separate path**; registry was already TRIPPED while quoter kept POSTing |

**If** Emergent’s shipped delta is *only* `EthJsonRpcProvider` and does **not** change `quoter.py` candidate retries / cooldown, the fix would be **architecturally incomplete** relative to the proven amplifier → would warrant **CONDITIONAL** even after bundle arrival (both layers can be valid hardening; quoter path is the campaign-critical one).

**Workspace-only** (not Gate 9, not Emergent bundle) already contains a *different* remediation in `app/backend/arbicore/execution/quoter.py`:

- `ARBICORE_RPC_FAILOVER_CANDIDATE_RETRIES` default **1**
- `ARBICORE_RPC_HTTP_429_COOLDOWN_S` default **60**

That local delta is **not** certified here as Workstream A, was **not** deployed, and uses **different env names** than Emergent’s claimed knobs. Treat as evidence of path divergence only.

---

## Workstreams B/C/D — docs commit blocked; theme spot-check

Claimed:

- Docs commit: `5a143a8`
- Bundle: `workstream-abcd-5a143a8.bundle`
- SHA256: `3ace6382…a3c5`

**Ancestry / checksum / file list:** **BLOCKED** (bundle missing).

### Informational reconciliation with prior VPS audits (not Emergent commit cert)

Against workspace tip + prior cert docs (`ARBITRAGE_CAPABILITY_MATRIX_AUDIT_20261002.md`, addendum, `24H_PARALLEL_READINESS_AUDIT_20261002.md`, code):

| Claimed audit conclusion | Independent spot-check | Aligns? |
|---|---|---|
| Capability implementations already exist (matrix incomplete but non-empty) | GENERIC_DEX / TriangularDiscoverySource / cross-chain detection scanner / flash adapters present; STABLECOIN/LST largely tagging-only | **Yes** (prior audit FINAL STATUS READY) |
| Economic / evidence chain needs no new engine/schema | Gate7/8 fail-closed; pipeline journals SHADOW; paper evidence collection exists; 24h audit: “Do not build a new evidence system” | **Yes** |
| Actual mode ladder + broadcast gating | `pipeline.py`: `OBSERVE→PAPER→SHADOW→LIMITED_LIVE→FULL_LIVE`; `BROADCAST_MODES={LIMITED_LIVE,FULL_LIVE}`; SHADOW/PAPER terminate at `SHADOW_RECORDED` | **Yes** |
| Frozen TRIANGULAR live-loop wiring gap | Matrix class **C**: M5 DiscoverySource wired; M6 triangular **0 candidates**; no GENERIC_DEX-comparable live triangular eval campaign | **Yes** (inventory / live-loop depth gap, not “code absent”) |
| Cross-chain execution deferred | Detection **D** / executable **E**; scanner docstring detection-only; default disabled | **Yes** |

These spot-checks support that Emergent’s *stated themes* match prior VPS certification conclusions — but **cannot** certify that docs commit `5a143a8` contains those conclusions, only those conclusions, or no contradictory engine/schema proposals.

---

## Test verification

| Item | Result |
|---|---|
| Import bundle → TEMP clone | **Not run** (no bundle) |
| 17 focused tests (throwaway docker, not Gate 9) | **Not run** |
| Broader suite claim | **Unverified** |
| Gate 9 container used as test runner | **No** (forbidden; not done) |

---

## Discrepancies summary

1. **Delivery gap:** Bundles advertised at `/app/artifacts/...` are not on the cert VPS — primary BLOCKED cause (repeat of prior Emergent→VPS handoff pattern).
2. **Remote absence:** Branch `engineering/gate9-parallel-93a20c9` and commits `2b86cda` / `f096249` / `5a143a8` not on `origin`.
3. **Architecture path mismatch (conditional risk):** Emergent claims `EthJsonRpcProvider` fix; proven Gate 9 Alchemy amplifier is `QuoterRegistry` last-candidate retry. Env knob names also differ from workspace quoter remediation.
4. **Truncated SHA256 claims:** Only prefixes supplied (`83abc177…cd4446`, `3ace6382…a3c5`); full digests cannot be checked until files arrive.
5. **No deploy / no Gate 9 change** performed by this certification.

---

## Unblock requirements (next cert pass)

1. Copy both bundles onto the cert host (e.g. workspace `artifacts/` or `/tmp/`), or publish commits to a reachable remote.
2. Supply **full** SHA256 digests.
3. Re-run this procedure: TEMP detached clone, ancestry `f096249`→`2b86cda`, `git diff --name-status` vs parent, verify env defaults + RED test semantics, throwaway docker tests (not Gate 9).
4. For Workstream A: explicitly confirm whether `quoter.py` is in the changed-file set; if not, expect **CONDITIONAL** relative to VPS root-cause even if EthJsonRpcProvider tests pass.
5. For B/C/D: diff docs commit vs parent; confirm no engine/schema/mode/broadcast deltas beyond documentation.

---

## STOP

- **No deploy** of either bundle
- **No** Gate 9 restart / config / image change
- **Workstream A:** **BLOCKED**
- **Workstreams B/C/D:** **BLOCKED**
- Gate 9 `StartedAt=2026-10-02T06:19:33.513948555Z`, `RestartCount=0`, image `arbicore-x-backend:g5.79-green-20260927` — **untouched**
