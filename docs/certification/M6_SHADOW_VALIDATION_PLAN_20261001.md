# M6 SHADOW Validation Plan — Post-M5 Activation

- Status: **PLAN ONLY** (no implementation in this document’s commit scope beyond planning text)
- Depends on: M5 PASS tag `arbicore-m5-canonical-activation-pass-20261001` → `05dacdb3eb3cc2f6555aee77b8a9811206891bc5`
- Extract-port baseline: `861af4d60e841ac8abac5891d663e23986c356ad`
- Date: 2026-10-01
- Posture: **SHADOW only** — no PAPER, no LIMITED_LIVE, no AUTOEXEC, no RUNTIME, no signing, no broadcast, no production deploy without explicit operator approval

## Objective

Re-validate six-chain live SHADOW **after** M5 DiscoverySource activation so evidence is bound to the activated canonical scanner path (GENERIC_DEX / triangular / Balancer → verifier → Gate 7 $25 → EmissionBus), not library-only harness calls.

## Scope

### In scope

1. Six-chain live SHADOW re-validation with M5 sources registered
2. Polygon RPC / gas seams / Balancer `getLogs` capacity proofs
3. Profitable-evidence goals under Gate 7 ($25) without synthetic profitable quotes
4. Explicit stop conditions and approval gates before any mode promotion

### Out of scope (this plan phase)

- M6 code changes beyond optional harness/docs needed for read-only validation
- PAPER / AUTOEXEC / RUNTIME enable
- Signing, broadcast, production rebuild/deploy
- Lowering Gate 7 or weakening fail-closed paths

## Preconditions (must hold before M6 runs)

| # | Precondition | Evidence |
|---|---|---|
| P1 | M5 unconditional PASS tagged | `arbicore-m5-canonical-activation-pass-20261001` → `05dacdb` |
| P2 | Production containers remain SHADOW | `ARBICORE_EXECUTION_MODE=SHADOW` |
| P3 | Autostart off | `ARBICORE_AUTOEXEC_AUTOSTART=false`, `ARBICORE_RUNTIME_AUTOSTART=false` |
| P4 | Gate 7 still $25 | filter / GENERIC_DEX / scanner defaults |
| P5 | No deploy of M5 image required for planning; if code is exercised from a mount/worktree, it must be exact `05dacdb` (or a later cert tip that preserves M5 blobs) |

## Workstreams

### W1 — Six-chain live SHADOW re-validation (activated path)

**Goal:** Drive the **canonical** scanner DiscoverySource path (or equivalent harness that instantiates M5 `GenericDexDiscoverySource` / `TriangularDiscoverySource` / `BalancerV2DiscoverySource` + live `QuoterRegistry`) on ethereum, arbitrum, optimism, base, polygon, bnb.

**Steps:**

1. Bind validation to SHA `05dacdb` (or tagged M5 tip); record `git rev-parse HEAD` in JSON report.
2. Confirm `build_all_flash_loan_sources` registers the three M5 sources when config flags are on.
3. Run read-only ticks / harness windows per chain with operator RPC where available.
4. Bucket economics identically to prior live SHADOW:
   - **A** Real profitable (Gate 7 pass)
   - **B** Real quotes, economically rejected
   - **C** Quote failures
   - **D** Liquidity failures
   - **E** Gas failures (`unknown_gas` / pathological)
   - **F** RPC/data failures
   - **G** Unsupported routes (`no_adapter`, etc.)
5. Persist JSON under `reports/shadow_validation/` + durable markdown under `docs/certification/`.

**Success (evidence complete, not necessarily profitable):** all six chains exercised; fail-closed reasons explicit; A/B/C/E counts recorded; no mode promotion.

**Success (economic):** A ≥ 1 with reproducible quote + gas + Gate 7 metadata (still SHADOW-only).

### W2 — Polygon RPC / gas seams

**Goal:** Prove Polygon is usable under M5 failover, not only public-RPC failure modes.

**Steps:**

1. Provision `PROVIDER_RPC_URLS_POLYGON` (multi-URL) and confirm `rpc_explicitly_configured("polygon")`.
2. Exercise `make_eth_call_for_chain_from_env("polygon")` and `make_eth_get_logs_for_chain_from_env("polygon")`.
3. Re-run GENERIC_DEX evaluations on Polygon UniV3 fee pairs previously quote-failed.
4. Record gas model outcomes (priced vs `UNKNOWN_GAS`); never treat pathological gas as profitable.

**Exit:** Polygon moves from “mostly F/C” to measurable B/A/E with operator RPC; failover rotates endpoints under 429/timeout without fabricating data.

### W3 — Balancer getLogs (P1b) + optional P1 subgraph

**Goal:** Longer Base/Polygon (and ethereum/arbitrum/optimism) `PoolRegistered` windows via registry `eth_getLogs`; optional subgraph when URLs set.

**Steps:**

1. With operator Alchemy (or equivalent), run P1b windows sized beyond prior public-RPC failures.
2. Keep fail-closed: missing fetcher / transport → `DISCOVERY_UNAVAILABLE` (no fabricated pools).
3. If operator sets `ARBICORE_BALANCER_SUBGRAPH_URL_<CHAIN>`, re-run P1; otherwise document intentional unset.
4. For discovered pools with explicit `pool_id`/`pool_address`, spot-check P0 `queryBatchSwap` (read-only).

**Exit:** Base/Polygon P1b no longer stuck solely on public-RPC transport errors; at least one multi-chain P0 quote path remains green.

### W4 — Profitable evidence goals

**Goal:** Seek **A ≥ 1** under Gate 7 $25 without injecting synthetic profitable quotes.

**Rules:**

- Real quoter outputs only
- Pathological gas → `UNKNOWN_GAS` (M5 seam) — not bucket A
- Gate 8 TVL fail-closed remains authoritative where TVL provider absent
- Exact-size sizer remains env-gated unless explicitly enabled for a named SHADOW experiment (document env; default off)

**If A stays 0:** publish evidence-complete report (same as pre-M5 live SHADOW); do **not** invent profitability; do **not** lower Gate 7.

## Blockers carried from M5 PASS (exact)

| # | Blocker | M6 action |
|---|---|---|
| 1 | No profitable live opportunity (prior A=0) | W1/W4 re-measure on activated path |
| 2 | Alchemy/operator RPC capacity | W2 provision multi-URL; measure 429/failover |
| 3 | Balancer subgraph URLs unset | W3 optional config; keep fail-closed if unset |
| 4 | Base aero_ss / BNB pancake `no_adapter` | Track as implementation gap; do not invent adapters in “validation only” |
| 5 | Gate 8 TVL missing for non-Base / Balancer | Document deny rates; TVL provider work is separate approval |
| 6 | Exact-size sizer default off | Leave off unless named SHADOW experiment approved |
| 7 | PAPER / LIMITED_LIVE / AUTOEXEC off | **Hard stop** — remains off through M6 plan execution |
| 8 | No signing / broadcast / deploy | **Hard stop** |

## Stop conditions (hard)

Stop and escalate for explicit approval if any of the following is requested or observed:

1. Enabling `PAPER`, `LIMITED_LIVE`, `FULL_LIVE`, AUTOEXEC, or RUNTIME autostart
2. Any signing, broadcast, or transaction submission
3. Production image rebuild/deploy of M5/M6 without a separate deploy cert
4. Proposal to lower Gate 7 below **$25** or skip Gate 8 fail-closed
5. Synthetic profitable quote injection presented as live A-bucket evidence
6. Merging divergent Emergent SHAs (`f27da21` / `334385e` / `457bad0` / `f4d4c62`)

## Deliverables

1. `reports/shadow_validation/live_shadow_<UTC>.json` bound to M5 tip
2. `docs/certification/M6_SHADOW_VALIDATION_*_20261001.md` (evidence report — after runs)
3. Updated blocker list: which of (1)–(8) cleared vs still open
4. Explicit recommendation: remain SHADOW **or** request separate approval for next mode (not auto-promoted)

## Suggested execution order

1. Confirm P1–P5 + docker env still SHADOW/autostart false
2. W2 Polygon RPC provisioning smoke (read-only)
3. W3 Balancer getLogs longer windows
4. W1 full six-chain activated SHADOW window
5. W4 economic rollup + durable docs
6. STOP for review — no mode changes

## STOP

M6 is **SHADOW validation only**. No paper execution. No live trading. No production deploy. No AUTOEXEC/RUNTIME enable until explicit operator approval after profitable SHADOW evidence and separate review.
