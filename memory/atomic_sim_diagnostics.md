# Atomic-Sim Diagnostics (A + B) — 2026-06

## What was added (diagnosis/parity only — NO execution changes)
- **B**: `POST /engine/run-atomic-sim` now returns a full `artifact` (executor, entrypoint,
  selector, from, borrow token/amount, flash_vault, settlement_target, tokens, amounts, hops with
  fee_ppm/amountOutMin/sqrtLimit, userData, profit_recipient, calldata_hex) + `execution_context`.
  NEVER echoes private key / vault material / RPC URL.
- **A**: `POST /engine/run-atomic-sim` accepts optional body `{block_number, fork_rpc}`.
  - `fork_rpc` → run eth_call against operator fork endpoint (url not echoed).
  - `block_number` → prefers LOCAL anvil fork (`anvil_fork()` ctx mgr, `--fork-block-number`),
    falls back to archive-RPC historical eth_call `hex(block)`.
- Honest semantics preserved: only a `live_rpc_latest` PASS updates `_ATOMIC_LIVE_RUN`
  (feeds SIMULATION_ONCHAIN). Block-pinned/fork runs stored in `_ATOMIC_DIAG_RUN` (`diagnostic=true`)
  and NEVER flip the live matrix. signed/broadcast always false.

## KEY TRUTH (do not re-litigate)
- The atomic sim was NEVER GREEN in Emergent. Tests assert `passed is False`
  (iter16:109, iter17:105, iter18:101) and SIMULATION_ONCHAIN=YELLOW. VPS reproduces Emergent
  exactly — NO parity divergence. The revert is deterministic economics: WETH→USDC→WETH round trip
  through the SAME 0.05% pool loses ~10bps → cannot repay the 0-fee Balancer loan.
- 0 profitable fixtures exist in accumulated evidence (alerts=0, executable=0). To reach
  ATOMIC_SIM=GREEN needs a genuinely profitable EXECUTABLE_UNIV3 route (real live spread ≥ costs)
  OR a block-pinned fork where a real spread existed (proof-of-mechanics, distinct from live GREEN).

## PREVIEW-ONLY TEST CONTRADICTION (not a code regression)
- Preview pod has NO persistent anvil. Older tests assume anvil ABSENT
  (`test_p0_executor_entrypoint::test_fork_harness_readiness_no_fake_green`,
  `iter16::test_run_fork_validation_honest_no_anvil`, `iter16::test_fork_status`); newer authoritative
  tests assume anvil PRESENT (iter17/iter18 FORK_VALIDATION GREEN).
- On the VPS anvil 1.7.1 IS installed → iter17/18 pass (authoritative). In preview, installing anvil
  (`~/.foundry/bin` → symlink `/usr/local/bin/anvil`) flips iter17/18 green and the stale no-anvil
  assertions red. This contradiction is environment-dependent and unrelated to A/B.
- A/B + calldata + execution-capability + atomic-gate suites: 75/75 PASS. Public-RPC
  `RPC_STATE_OVERRIDE` probe is occasionally flaky (rate-limit) → passes on retry; a dedicated VPS RPC
  removes this.
