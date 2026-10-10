# ArbiCore X — First Live Path Decision Memo

**Date:** 2026-10-05
**Role:** independent principal architect / trading-system reviewer
**Mode:** read-only review. No source edit, no deploy, no restart, no config or Mongo write, no mode change, no signing, no broadcast. The only artifact created is this memo.

**Decision:** **CONDITIONAL GO for LIVE 0 (one engineering transaction on Base mainnet). NO-GO for any strategy canary on the existing generic DEX universe.** The first strategy trade (LIVE 1) is gated by a single time-boxed measurement with a hard kill rule, not by more audits.

---

## 0. Executive recommendation (one page)

1. **Live-testing an existing generic DEX strategy is not rational today.** Across two certified windows (544 Gate-7 evaluations), zero candidates reached $0, let alone $25. Every stored gross spread on the 180 complete bundles is negative *before* gas, flash fee, or the MEV haircut. Live execution can only subtract from a quote (decay, competition, gas). It cannot turn a negative pre-trade quote into a profit. A canary with Gate 7 unchanged would never fire. A canary with Gate 7 lowered would only buy losses, because nothing clears $0 either. So the Gate 7 debate is moot for now.

2. **The hypothesis "profitability is discovered through real execution" is only half true.** Real execution measures the gap between a *positive* predicted edge and the realized fill. It needs a positive prediction to exist first. Today there is none.

3. **You are over-auditing, and also measuring the wrong thing.** About 90 certification documents in roughly five days, several re-reading the same 288 rows, plus SHA-stamping commits ("stop POST-M6 FINAL SHA self-reference churn"). Meanwhile the deployed commit was never pushed. The best stored gross on Base USDC/WETH (-0.091%) is roughly the sum of the two pools' fees. That is pools sitting exactly at the edge of their no-arbitrage band. A 60-second poller, with 46 seconds to 15 minutes between discovery and verification, *should* see exactly this on blue-chip pairs. More audits of that poller cannot change the answer. Only a block-level measurement can.

4. **The fastest *responsible* first real trade is an engineering transaction, not a strategy trade.** The codebase already has a Technical Validation flow. It executed a real flash loan on Base Sepolia (`0x7b61cdb6…5f20`) and has never run on mainnet. One Base-mainnet run costs cents. It proves the real executor, real mainnet addresses, real gas (including the L1 data fee), real `eth_sendRawTransaction`, receipt parsing, and evidence persistence. It does not touch the strategy mode ladder or Gate 7. When an edge does appear, the gap from "found" to "traded" becomes hours instead of another build cycle.

5. **There are two blockers you didn't list, and they are worse than the GitHub gap:**
   - **Three legacy backends share production state.** `arbicore-x-b7-candidate`, `arbicore-x-backend-h05`, and `arbicore-x-backend-w1` run against the production database `arbicore_x` with the same `VAULT_KEY` and `JWT_SECRET` as production. All three have scanner autostart on. They are actively burning the Base Alchemy quota (live 429s in their logs right now). Once a signing key is in the vault, old code can decrypt it and see the shared kill-switch and mode state. This must be fixed before any key is loaded.
   - **The post-trade loss loop is not wired.** Nothing writes `realized_loss_usd` and nothing calls `CircuitBreaker.record_outcome`. So the daily stop-loss and the breaker can never trip from real trades. This is mandatory before LIVE 1, not before LIVE 0.

6. **Provenance repair is small.** I verified that the running container's code is byte-identical to `823a79b` (the only difference is the `tests/` directory, which `.dockerignore` excludes), and the Dockerfile matches. The problem is "unpushed and mislabeled", not "unknown code running". Push, tag, commit the `/tmp` override, rebuild from a clean tag checkout, and verify five identities. About half a day.

7. **Sequence:** about **4–6 working days to LIVE 0**. In parallel, a **72-hour per-block Base SHADOW measurement** produces a binary LIVE 1 decision around **day 8–10**. If that measurement finds nothing, stop DEX atomic arbitrage on this infrastructure. Do not start another audit loop.

**Path verdict:** Path A (research first) is the loop itself. Path B (strategy canary) as written is a canary that cannot fire, and per-trade human approval is incompatible with opportunities that live for seconds. **Path C is correct in shape, with two corrections:** the canary is an *engineering* canary, and the research track is *one* measurement with a kill rule, not open-ended alpha discovery.

---

## 1. Current state (verified on the VPS and in the repo today)

| Item | Verified value | Source |
|---|---|---|
| Production backend | `arbicore-x-backend-new`, image `arbicore-x-backend:phase0-823a79b` (`sha256:768b4410…`), up ~26h, healthy | `docker ps`, `docker inspect` |
| Running code | Byte-identical to `git archive 823a79b app/backend`, except `tests/` (excluded by `.dockerignore`) | `diff -rq` of the container `/app` against the git tree |
| `BUILD_INFO.json` | `git_sha=823a79b6…`, `build_time=2026-10-04T14:58:40Z`, `image_digest=unset`, `image_ref=unset` | container file |
| Container label `arbicore.gitsha` | `2a6fadb8…` (wrong) | `docker inspect` labels |
| Env `ARBICORE_VERSION` / `ARBICORE_BUILD_TIME` | `arbicore-x-cert-baseline-99059c0-20260914-dirty` / `2026-09-14T09:11:11Z` (stale; inherited from `backend/.env`) | container env |
| Launch config | `docker-compose.prod.yml` plus **`/tmp/arbicore-phase0-823a79b-override.yml`** (ephemeral, uncommitted) | compose labels |
| Source checkout of the deployed commit | `/tmp/arbicore-b1b2-reconcile-9ed2718` worktree, clean, at `823a79b` | `git worktree list` |
| GitHub | `823a79b` and `62ec784` absent. Closest remote: `phase-b/h06-six-chain-runtime` at `6482a77` (docs on top of `9ed2718`) | `git ls-remote origin` |
| Dockerfile | `deployment/upgrade/backend/Dockerfile` at `823a79b` is identical to the one used | `diff` |
| Frontend | `27dfab4` (present on GitHub via `phase-b/h06-six-chain-runtime`) | `docker ps`, `git branch -a --contains` |
| Execution posture | `ARBICORE_EXECUTION_MODE=SHADOW`, `AUTOEXEC_AUTOSTART=false`, `RUNTIME_AUTOSTART=false`, scanner autostart on | container env |
| Base executor `0x0E3FDb0F…927f` | Deployed. **V1 `FlashLoanReceiver`** (`receiverVersion()` reverts; has `aavePool`, no Morpho). Owner `0x0a43F432…Fa89`. Holds 0 ETH, 0 USDC | Base `eth_call` / `eth_getBalance` |
| Executor signer/owner `0x0a43…Fa89` | ~0.00634 ETH, nonce 1 (only the deployment). **Has never traded** | Base RPC |
| "Gas wallet" `0x998d…aad25` | ~0.00000055 ETH (effectively empty), nonce 3 | Base RPC |
| Base WSS / T2 per-block searcher | `ARBICORE_T2_SEARCHER_ENABLED=true` but no WSS URL configured. Status endpoint reported `enabled=false, running=false` in prior certs | env, prior docs |
| Legacy backends on prod DB | `b7-candidate` (`2.9.3-99059c0-b7`), `h05` (`h05-cert-20260911`), `w1` (`wallet-security-w1`): all `DB_NAME=arbicore_x` on `factory-mongo`, **same VAULT_KEY and JWT_SECRET hash as production**, scanner autostart on, actively hitting Base Alchemy with 429s | `docker inspect` (hashed), `docker logs` |
| Admin credential | Admin password is present as **plaintext in the container env** and is a guessable pattern. The UI is public (`144-91-78-175.sslip.io`) | container env (value not reproduced here) |
| Alchemy key | Legacy containers log the full Alchemy URL, including the key, at INFO level | `docker logs` |

---

## 2. What is genuinely production-ready today

- **Detection and refusal.** The scanner, quoter, economics assessor, and Gate 7 reliably detect and refuse unprofitable atomic cycles. Two certified windows agree.
- **The single broadcast path** (`execution/broadcast.py`). It is the only `eth_sendRawTransaction` call site in the codebase. Its gate ladder is real and fail-closed: circuit breaker, kill switch, per-strategy mode (`LIMITED_LIVE`/`FULL_LIVE` only), capital allocator, isolated vault signer that must match the configured signer, a nonzero per-hop `amountOutMinimum` guard, chain-id check, `eth_call` plus `eth_estimateGas` preflight, explicit `confirm=true`, and M3.0 pre-broadcast revalidation (`require_revalidation=True`; requires net ≥ `$25 + $10` buffer by default, block lag ≤ 5, TVL, flash-loan availability, duplicate guard).
- **Atomic loss bound.** The flash-loan executor reverts unless the loan is repaid, and the executor holds no funds. Worst-case loss per attempt is the gas paid by the signer. On Base that is cents.
- **Kill switch.** It is a Mongo-backed global flag checked before signing, with an audit trail. Rollback on the mode ladder is always allowed and immediate.
- **Technical Validation** (`execution/technical_validation.py`, `POST /api/arbicore/wizard/technical-validation`). It already supports a dry mode (`execute=false`, `eth_call` with state override) and a real mode, and it persists evidence to `arbicore_technical_validations`. It is proven on Base Sepolia.
- **Deployed code identity.** The content matches `823a79b`. Only the metadata is wrong.

## 3. What is NOT production-ready

| Gap | Why it matters | Blocks |
|---|---|---|
| Legacy backends share the prod DB, vault key, and JWT secret | Old code can read and decrypt the signer once it is loaded, sees the same kill-switch and mode rows, pollutes evidence collections, and burns the RPC quota | LIVE 0 |
| Admin password in plaintext env, guessable, public UI | The operator role can arm modes, disengage the kill switch, and call `/execution/plans/{id}/broadcast` | LIVE 0 |
| Alchemy key in INFO logs (legacy containers) | Credential leak; quota theft | LIVE 0 (rotate) |
| Deployed commit not on GitHub; wrong label; stale version env; override in `/tmp` | You cannot certify or reproduce what is live. A `/tmp` wipe loses the launch recipe | LIVE 0 |
| Technical Validation is testnet-shaped | Defaults to Sepolia USDC. The key comes from env `ARBICORE_VALIDATION_SIGNER_KEY`, which `docker inspect` exposes, not from the vault | LIVE 0 |
| No realized-P&L reconciliation | `realized_loss_usd` has no writer, `CircuitBreaker.record_outcome` has no caller on the broadcast path, and the breaker state is in-memory (resets on restart). The stop-loss is therefore inert | LIVE 1 |
| Capital policy is wrong for flash loans | Sizing is capped at 20% of the *gas wallet* USD balance (`max_wallet_percent`). For an atomic flash loan, the principal is not at risk. With the gas wallet empty, every plan is denied. The wallet read (`0x998d…`) is also not the wallet that pays gas (`0x0a43…`, the tx sender). Separately, `policy.get(x) or DEFAULT` turns an operator value of `0` into the default (for example, `max_daily_loss_usd=0` becomes `$100`) | LIVE 1 |
| V1 executor has no on-chain profit floor | A tx that preflights at $35 can land at $0.01 and still succeed. Gate 7 is then only a pre-trade estimate, not an invariant | LIVE 1 |
| Per-trade human approval vs. opportunity lifetime | Atomic L2 opportunities live for one block or less. A human click takes minutes | LIVE 1 design |
| No block-level opportunity measurement on any chain | The only cadence ever measured is a 60-second poller | LIVE 1 decision |
| Research tooling provenance | `opportunity_ledger/`, `ledger_explorer.py`, and their tests are untracked in the cert worktree (about 120 untracked paths) | Nothing live; housekeeping |

## 4. What previous audits have already proven (accept and stop re-proving)

- In the quoted sample (the `flash_loan_route_search` poller, mostly USDC/WETH/WBTC blue-chip cycles), there is **no gross edge**. 180/180 bundles have gross ≤ 0. Two independent windows agree. *Accepted.*
- Gas, flash fee, and slippage did not cause the losses. The quote did. The $50 "MEV" term is a model constant, not an observation. *Accepted.*
- The TRUMP mechanism is COMPETITION_ERASED. Uniswap v4 is INSUFFICIENT_EVIDENCE. The liquidation census found 0 competition-surviving cells ≥ $25. *Accepted. None justify a build.*
- The fail-closed safety stack holds in SHADOW (no signing, no broadcast through any certified run). *Accepted.*
- The flash-loan executor works end-to-end on a real chain (Sepolia Phase A). *Accepted.*

What they have **not** proven, and cannot prove by re-reading stored rows: whether positive-gross states exist on Base **at block granularity**, and for how many blocks they survive.

## 5. Audits and research that can stop now

Stop all of these immediately. None has a decision it can still change.

- Any further forensic, ranking, or recomputation of the Oct-4 (256) or Oct-5 (288/180) rows, including the "Triangular by chain" and "Cross-Protocol 4 bundles" reads. Even if a chain slice is less negative, it stays negative, and the poller cadence is the binding issue.
- Any further generic 30-minute SHADOW of `flash_loan_route_search`.
- The Phase 0.5 ledger/explorer/Excel program (0.5-C through 0.5-H).
- The liquidation census expansion (Arbitrum, Euler, Fluid, Silo, Optimism long slice, BNB, size sweep, N+1 replay).
- E-series historical replays (TRUMP, v4, bridge).
- Six-chain RPC tuning, rotation certifications, and network-config UI certifications.
- SHA-stamping documentation commits. One deploy record per deploy replaces them (section 10).
- Patch 1 efficiency, Route Search v2, MEV modelling, chain-specific models.

The one-block stratified census recommended by `STRATEGIC_ALPHA_AUDIT_BEFORE_LIVE1_20261005.md` is **replaced** by the per-block measurement in section 19. Its useful panels (stables, LST, fee tiers on Base) ride along inside that measurement, because the Base venue registry already contains those pairs. A one-block snapshot of an equilibrium market mostly re-measures the fee band.

## 6. Minimum issues to fix before LIVE

**Before LIVE 0 (the first real transaction):**

| # | Fix | Size |
|---|---|---|
| M1 | Remove the three legacy backends' access to production state: stop them, or repoint them to an isolated DB with different secrets | Ops, ~1h |
| M2 | Rotate the admin password (strong, not in compose env), rotate the Alchemy keys that appeared in logs, rotate `JWT_SECRET`. Issue a **production-only** `VAULT_KEY`; re-encrypt or confirm the vault is empty first (prior certs say the signing key is absent) | Ops, ~2h |
| M3 | Canonical provenance chain (section 10) | ~½ day |
| M4 | Technical Validation on mainnet: accept Base USDC (`0x8335…2913`) as the swap-out token, and resolve the owner key from the `evm_sign` vault the same way `broadcast.py` Gate 4 does (no raw env key on mainnet). Keep `execute=false` as the default | Code, ~½ day + tests |
| M5 | Signer wallet holds ≤ 0.01 ETH. The executor holds nothing. No other funds on any key this VPS can decrypt | Ops |
| M6 | Kill-switch drill on the deployed build: engage, confirm that a broadcaster dry run (`confirm=false`) shows `kill_switch: DENIED`, then disengage | Ops, ~15 min |

**Additionally before LIVE 1 (the first strategy trade):** L1–L6 in section 20.

## 7. Is LIVE 0 / a controlled canary appropriate?

- **Engineering canary (LIVE 0): yes.** It has a bounded cost (cents), a bounded blast radius (≤ 0.01 ETH signer), and is fully reversible. It retires real execution-path risk, and it does not touch Gate 7 or the strategy ladder.
- **Strategy canary on the existing generic DEX universe: no.** There is no positive candidate to execute. Arming signing for a strategy that cannot produce a candidate adds attack surface (a hot key in the vault, an armed broadcast endpoint) and yields zero information.

## 8. Exactly what path LIVE 0 uses

- **Path:** the existing Technical Validation flow. It is *not* the strategy broadcaster, because the broadcaster correctly refuses anything that does not clear Gate 7 plus the buffer.
- **Chain:** Base mainnet (chain id 8453). It has the cheapest gas, the deployed executor, and the healthiest RPC in prior windows.
- **Transaction:** an Aave V3 flash loan of `1e13` wei WETH (about 0.00001 WETH), one Uniswap V3 swap of `1e12` wei WETH to USDC (fee tier 5 bps), repaid with the 5 bps premium from a tiny pre-fund wrapped from the signer's own ETH. Expected outcome: success, a residual of a fraction of a cent in USDC to the profit recipient, and total cost dominated by gas (cents).
- **Label:** `ENGINEERING_CANARY`. It is not a strategy trade, not counted as P&L, and not used to argue profitability.

What LIVE 0 teaches, which nothing offline can: mainnet router and pool addresses in the executor, the actual gas used against the estimate, the Base L1 data fee, inclusion latency through the configured RPC, receipt and `ExecutionCompleted` event decoding, evidence persistence, nonce handling, and the operator workflow end-to-end.

## 9. Why not a strategy canary (answering the critical question directly)

> "Is it technically and economically rational to LIVE-test an existing generic DEX strategy if it currently has no demonstrated positive opportunity?"

**No.**

- **Economically:** expected P&L per armed hour is zero (no candidates) or negative (if gates are loosened). Expected information is zero, because nothing is sent.
- **Technically:** the system is built correctly so that it *cannot* send these trades. Preflight `eth_call` would revert on a negative cycle, and revalidation demands net ≥ $35. Going live on this universe means either waiting forever, or weakening the gates that make the system safe.
- **Structurally:** the poller cadence (60 seconds, with 46 s – 15 min from discovery to verification) cannot observe transient L2 dislocations, which are closed within the same block by competitors. Live execution does not fix detection latency.

Do not manufacture a strategy. There is none to name today.

## 10. Minimum canonicalization remediation

Goal: GitHub commit = Docker build source = image identity = running code = certification identity. Do not do a refactor. Do one canonical deploy, and make it the deploy that also ships the LIVE 0 build tasks, so the chain is exercised once and for real.

1. **Push now (no deploy):** `git push origin phase-0/strategy-intelligence-observability-20261004`, which contains `62ec784` and `823a79b`. Create an annotated tag `prod/823a79b-20261004`. Verify with `git ls-remote`.
2. **Commit the launch recipe:** move the `/tmp/arbicore-phase0-823a79b-override.yml` content into the repo. Preferred: put `IMAGE_TAG`, `GITSHA`, `GITTAG`, `APP_VERSION`, and `BUILD_TIME` in `deployment/upgrade/compose/.env`, so `docker compose up` needs no override. Remove `ARBICORE_VERSION` and `ARBICORE_BUILD_TIME` from `deployment/upgrade/backend/.env`, so `BUILD_INFO.json` is the single source of truth.
3. **Build only from a clean checkout of a pushed tag**, under a non-`/tmp` path (for example `~/projects/arbicore-releases/<sha>`). Pass `GITSHA` so both labels resolve, and add `org.opencontainers.image.revision=<sha>`.
4. **Verify five identities** after recreate. Every one must equal the tag's full SHA:
   - `git ls-remote origin refs/tags/<tag>^{}`
   - image label `arbicore.gitsha` and `org.opencontainers.image.revision`
   - container label `arbicore.gitsha`
   - `BUILD_INFO.json.git_sha` and env `ARBICORE_GIT_SHA`
   - content: `diff -rq` of `git archive <sha> app/backend` against the container `/app` shows only `tests/`
   - also record the image ID in `ARBICORE_IMAGE_DIGEST` / `BUILD_INFO.image_digest`.
5. **One deploy record** per deploy (a single short file: tag, SHA, image ID, the five checks, operator, time). This replaces SHA-stamping commits.
6. **Keep** the `phase0-823a79b` image as the rollback target. Do not prune it.

Not required before LIVE 0: frontend changes (`27dfab4` is already on GitHub), cleaning up the other validator containers and mongos (housekeeping; only M1's three backends are blocking), or migrating the research tooling into git (do it, but it does not gate LIVE).

## 11. Minimum safety gate

**Mandatory before LIVE 0:** M1, M2, M5, M6 (section 6), plus:

- The kill switch is checked on the Technical Validation path, or the operator engages it immediately after the run. Verify which applies. If the path ignores the kill switch, add the same `guard()` call before signing. This is a one-line, M4-sized change.
- Strategy modes stay SHADOW. `AUTOEXEC_AUTOSTART=false`.
- Exactly one signer key exists, it is in the vault, and the production container alone can decrypt it.

**Mandatory before LIVE 1:** everything above, plus L2 (reconciliation into the breaker and allocator; breaker state persisted) and L4 (on-chain floor).

## 12. Minimum economic gate

- **LIVE 0:** none. It is not a trade for profit. Cost cap: total spend ≤ 0.002 ETH including any retry. Stop on the first unexpected outcome.
- **LIVE 1** (all must hold for each broadcast; mostly already implemented):
  - Gate 7: modeled `atomic_profit_usd ≥ $25` (unchanged).
  - Pre-broadcast revalidation at the latest block: net ≥ $25 + $10 buffer (already the code default), with a fresh quote, block lag ≤ 5, TVL, and flash-loan availability.
  - Exact-transaction `eth_call` plus `estimateGas` succeed.
  - Gate 8 PASS and Gate 9 PASS. The MEV penalty is reported as its own number.
  - On chain: last-hop `amountOutMinimum` ≥ repay + Gate-7 floor (L4), so a landed trade below $25 reverts rather than succeeding at a loss.
- **The evidence bar to arm LIVE 1 is deliberately low:** at least 3 distinct qualifying states in 72 hours of per-block Base SHADOW (section 19). It is low because each armed attempt risks cents and teaches a lot. The bar is "a positive candidate exists", not "profitability is proven".

**Future decision, flagged rather than recommended:** the $25 floor is an economic-quality threshold, not a safety threshold. On Base the risk per atomic attempt is gas, measured in cents. If the per-block measurement shows a steady flow of $5–$25 states and none above $25, revisiting the floor is a legitimate, explicit owner decision at that point. It is not legitimate today, and it would not help today.

## 13. Minimum live capital / risk envelope (concept)

| Parameter | LIVE 0 | LIVE 1 (initial) |
|---|---|---|
| Chain | Base only | Base only |
| Executor | Existing V1 `0x0E3F…927f` | Same (do not deploy V2 now) |
| Flash provider | Aave V3 (built into Technical Validation) | Balancer V2 first (0 fee), Aave V3 allowed |
| Signer balance (the true max loss) | ≤ 0.01 ETH | ≤ 0.01 ETH, refilled manually only |
| Funds in executor | 0 | 0 |
| Profit recipient | Signer is acceptable | A cold address not decryptable on the VPS |
| Flash principal cap | Dust | $10k per plan (price-impact bound; principal is not at risk) |
| Broadcasts | 1 (max 2 if the first fails for a diagnosable reason) | ≤ 5 per armed window, ≤ 1 in flight |
| Daily realized loss cap | n/a | $5 (gas), enforced by the wired allocator and breaker |
| Consecutive failures before trip | n/a | 2 |
| Armed window | n/a | ≤ 4 hours, auto-disarm back to SHADOW |
| Strategy scope | n/a | Only the route family that Track 2 identified, allowlisted pools only |

Capital-policy correction for LIVE 1 (L3): the gas wallet balance must bound **gas spend and loss**, not flash principal. Until code reflects that, the operator must set explicit positive values. Set `max_wallet_percent` high enough not to bind the principal, set `max_per_plan_usd=10000`, `max_daily_loss_usd=5`, and `max_concurrent_plans=1`. The plan's `signer_wallet_id` must point at the wallet that actually pays gas. Do not use `0` to mean "off".

## 14. First-trade approval workflow

**LIVE 0 (per-transaction human approval; no time pressure):**

1. The operator confirms the deploy record shows all five identity checks PASS.
2. The operator confirms the M1 and M2 checklist (legacy backends detached, secrets rotated).
3. The operator loads the signer into the vault and confirms `signer_status.matches_expected=true` for `0x0a43…Fa89`.
4. Run Technical Validation with `execute=false` on Base mainnet. Expect the dry run to show success, a predicted gas figure, and a predicted residual.
5. A second person (or the owner, after a 10-minute pause) reviews the dry-run output: chain id 8453, executor address, router, token addresses, amounts, gas limit.
6. The owner approves. Run once with `execute=true`.
7. Capture the evidence (section 15). Unload the signer from the vault, or leave it loaded only if LIVE 1 preparation is imminent.

**LIVE 1 (envelope approval, not per-trade):** atomic opportunities on Base live for about one block. A human cannot approve per trade. The owner approves an **armed window**: chain, route allowlist, max broadcasts, max loss, duration. The system then executes autonomously *inside* that envelope, through the full broadcaster gate ladder. Any breaker trip, kill switch, or window expiry returns to SHADOW. Re-arming is a new human approval. The AI has no authority to arm, extend, or widen an envelope.

## 15. Monitoring requirements

Per broadcast (mandatory from LIVE 0):

- tx hash, nonce, block number, status, gas used against the estimate, effective gas price, L1 data fee, total fee in ETH and USD
- `ExecutionCompleted` event fields: provider, asset, borrowed, premium, residual
- signer, executor, and profit-recipient balances before and after
- the timeline: decision, sign, submit, inclusion
- the predicted against realized delta. For LIVE 1 this is *the* learning signal.

Continuous (mandatory from LIVE 1):

- kill-switch state, mode map, breaker status, armed-window state and remaining budget
- alerts (Telegram support exists in `notifications/telegram.py`) on: any broadcast, any revert, any breaker trip, a signer balance drop above 0.002 ETH, any mode change, any vault access

## 16. Rollback / kill-switch requirements

| Lever | Effect | Time |
|---|---|---|
| Engage kill switch | Every signing path is denied before signing | Seconds |
| Mode back to SHADOW | Always allowed, by ladder rule | Seconds |
| Drain signer to cold | Removes the only funds at risk | 1 tx |
| Unload signer from vault | Nothing can sign | Minutes |
| Container rollback | Re-run compose with `IMAGE_TAG=arbicore-x-backend:phase0-823a79b` | Minutes |
| Executor | V1 is owner-only and holds nothing; an idle signer makes it inert. No pause function is needed | n/a |

Requirement: drill the kill switch on the deployed build before LIVE 0 (M6). For LIVE 1, the breaker must call the kill switch on trip (`on_trip` exists; verify the wiring).

## 17. Exact build tasks

Only these. Each must be small, tested, committed, and pushed.

| ID | Task | Needed for |
|---|---|---|
| B1 | Technical Validation mainnet support: Base USDC swap-out token; owner key from the vault (reuse the `signer_status` and `secret_registry.resolve` logic from `broadcast.py`); refuse raw env keys when chain id is 8453; call `kill_switch.guard()` before signing | LIVE 0 |
| B2 | Post-broadcast reconciliation: poll the receipt for any `broadcast_sent=true`; write `realized_pnl_usd` and `realized_loss_usd` (gas on revert, or the negative delta) onto the plan; call `CircuitBreaker.record_outcome`; persist breaker events so a restart does not reset them | LIVE 1 |
| B3 | Capital policy: treat explicit `0` as `0` (replace `x or DEFAULT` with `None`-checks); bind the wallet constraint to gas and loss, not flash principal, for `flash_loan_arbitrage`; read the balance of the actual tx sender | LIVE 1 |
| B4 | Calldata: set the last-hop `amountOutMinimum` ≥ borrowed + premium + Gate-7 floor in token units | LIVE 1 |
| B5 | Armed-window control: an operator-only endpoint that sets `LIMITED_LIVE` with an expiry, a max-broadcast counter, and a route allowlist; auto-revert to SHADOW on expiry or exhaustion; fully audited | LIVE 1 |
| B6 | Track 2 config glue only, if needed: whatever wiring keeps the existing T2 Base searcher from running in SHADOW on the VPS (the readiness doc lists price source and pool→token map) | Track 2 |

Explicitly **not** built: a V2 executor deployment, new strategy families, v4, a liquidation engine, MEV or backrun infrastructure, a private relay, ML, or frontend work.

## 18. Exact deployment tasks

1. **D1 (ops, now, no deploy):** M1 and M2. Stop or isolate `arbicore-x-b7-candidate`, `arbicore-x-backend-h05`, and `arbicore-x-backend-w1` from `arbicore_x`; rotate secrets.
2. **D2 (git, now):** push the branch and tag the deployed commit (section 10, step 1).
3. **D3:** merge B1 (plus B6 if ready) on top of `823a79b`, push, and tag `prod/<sha>-<date>`.
4. **D4:** build from a clean tag checkout. Deploy with the committed compose and `.env`. Verify the five identities. Write the deploy record. Run post-deploy integrity (existing procedure, one pass).
5. **D5:** run the M6 kill-switch drill.
6. **D6:** LIVE 0 (section 20).
7. **D7 (later):** B2–B5 through the same chain (D3 and D4) before LIVE 1.

## 19. Exact SHADOW / PAPER requirements

- **No separate PAPER campaign.** For atomic flash loans, the exact-transaction `eth_call` preflight is a stronger paper test than a simulated fill.
- **LIVE 0:** the only shadow requirement is a Technical Validation **dry run on Base mainnet** (`execute=false`) that passes against the deployed build.
- **Track 2 (the single alpha measurement, which gates LIVE 1):**
  - **What:** the existing T2 per-block Base searcher (`searcher/wss_ingest.py`, `live_base.py`, `revm_backend.py`), in SHADOW, driven by Base WSS `newHeads` and pool logs, over the Base venue registry. That registry includes USDC/USDT, USDC/DAI, WETH/wstETH, cbETH, weETH, rETH, and multiple Uniswap V3 fee tiers.
  - **Measure:** per block, the count of states with modeled net ≥ $35, Gate 8 PASS, and exact-transaction `eth_call` success at that block; plus survival of each such state to block N+1 and N+2.
  - **Time box:** 3 working days to get it running. If it cannot run by then, fall back to per-block HTTP re-quoting of the 10 largest Base registry pools for the same 72 hours. Then 72 hours of measurement.
  - **Hygiene:** while it runs, pause non-Base scanners to remove self-inflicted 429 contention. This is an owner decision; it is not an RPC topology change.
  - **Kill rule:** fewer than 3 qualifying states in 72 hours means the conclusion is "this infrastructure cannot capture atomic DEX arbitrage on Base". The owner then makes a business decision: stop DEX atomic arbitrage, or fund a different class of infrastructure (co-located node, sub-block latency), which is a separate project. **No new audit cycle.**
  - **Pass rule:** 3 or more qualifying states means arm LIVE 1 for the route family that produced them. The N+1 survival rate sets expectations (if it is 0%, expect most attempts to be denied at preflight, which costs nothing).

## 20. Exact LIVE 0 activation gate

All boxes must be checked by a human. The AI does not check them.

- [ ] Deploy record shows all five identity checks equal to a **pushed** tag SHA
- [ ] `arbicore-x-b7-candidate`, `arbicore-x-backend-h05`, `arbicore-x-backend-w1` have no access to `arbicore_x` and do not share the production `VAULT_KEY`
- [ ] Admin password, `JWT_SECRET`, and the exposed Alchemy keys are rotated; the production `VAULT_KEY` is unique
- [ ] All strategy modes are SHADOW; `AUTOEXEC_AUTOSTART=false`
- [ ] Kill-switch drill passed on this build
- [ ] Signer `0x0a43…Fa89` balance ≤ 0.01 ETH; the executor holds 0
- [ ] Signer is in the vault and `matches_expected=true`; no raw key in any container env
- [ ] Technical Validation dry run on chain 8453 PASS; addresses reviewed by a second person
- [ ] Owner's written approval for **one** `execute=true` run, spend cap 0.002 ETH
- [ ] Afterwards: evidence captured (section 15); the result is labelled `ENGINEERING_CANARY`

**LIVE 1 gate (summary):** LIVE 0 PASS; B2–B5 deployed through the canonical chain; Track 2 pass rule met; the envelope in section 13 is configured; alerts are live; the owner approves one armed window.

## 21. What to explicitly STOP doing

1. Auditing stored rows from the poller (section 5).
2. Running generic SHADOW windows and re-reading the mean.
3. Treating a document that stamps a SHA as provenance. Push the commit instead.
4. Running candidate or legacy containers against production state.
5. Asking whether to "go live" with a strategy that has no positive candidate.
6. Designing per-trade human approval for second-lived opportunities.
7. Expanding chain count before one chain has made one trade.
8. Opening new alpha families (liquidations, v4, TRUMP, cross-chain, stable+cross-protocol builds) before Track 2 resolves.
9. Requiring LIVE to wait for a "certification" of things LIVE 0 will measure directly (gas, inclusion, receipts).

## 22. Estimated sequence from today to first real trade

| Day (working) | Work | Output |
|---|---|---|
| 0 | D1 (isolate legacy backends, rotate secrets), D2 (push and tag) | Prod state isolated; deployed commit on GitHub |
| 0–2 | B1 (plus B6 in parallel); Track 2 bring-up starts | Tested commits, pushed |
| 2–3 | D3 and D4 canonical build and deploy; five identities verified; deploy record | Canonical prod |
| 3 | D5 kill-switch drill; LIVE 0 dry run | Dry run PASS |
| 3–4 | **LIVE 0: first real mainnet transaction** | Receipt plus evidence |
| 3–8 | Track 2: 72 hours per-block Base SHADOW; B2–B5 built in parallel | Qualifying-state count |
| ~8–10 | **LIVE 1 decision** (binary, by the section 19 rule) | Arm one window, or stop DEX atomic arb |
| 10+ | If armed: first strategy broadcast, whenever a qualifying state appears | First strategy trade (not schedulable) |

The first real blockchain transaction is realistic in **4–6 working days**. The first strategy trade **cannot be scheduled honestly**. It depends on whether a qualifying state exists, and Track 2 answers that in about 10 days.

## 23. GO / NO-GO / CONDITIONAL GO

| Scope | Verdict | Condition |
|---|---|---|
| LIVE 0: engineering canary, Base mainnet, Technical Validation, ≤ 0.002 ETH | **CONDITIONAL GO** | Section 20 checklist: M1–M6, B1, canonical deploy |
| Strategy canary on the existing generic DEX universe (any family, any chain) | **NO-GO** | No positive candidate exists; live execution cannot create one |
| Lowering Gate 7 to enable trades | **NO-GO** | Would not help (0 candidates ≥ $0) and would only buy losses |
| LIVE 1: first strategy trade, Base, one route family, armed window | **CONDITIONAL GO, evidence-gated** | Track 2 pass rule plus B2–B5 plus the section 13 envelope |
| Further research and audit programs listed in section 5 | **STOP** | — |

**Bottom line:** yes, you are over-auditing. The way out of the loop is not to trade a strategy that has nothing to trade. Do three concrete things: make one real mainnet transaction this week to retire execution risk, take the one measurement that matches how L2 arbitrage actually works, and accept its answer, including "stop", without starting another audit.
