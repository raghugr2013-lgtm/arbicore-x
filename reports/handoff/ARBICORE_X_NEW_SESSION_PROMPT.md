# ArbiCore X v2 — NEW SESSION PROMPT (paste as FIRST message to the new account)

---

You are taking over **ArbiCore X v2**, an existing, safety-critical, six-chain
DEX flash-loan arbitrage searcher/executor. You have ZERO conversational history.
Do NOT assume anything about prior work beyond what the repository and the handoff
files state.

BEFORE DOING ANYTHING ELSE:
1. Read these files in order (they are the source of truth):
   - `reports/handoff/ARBICORE_X_NEW_ACCOUNT_HANDOFF.md`
   - `reports/handoff/ARBICORE_X_CURRENT_STATE.md`
   - `reports/handoff/ARBICORE_X_ARCHITECTURE_STATE.md`
   - `reports/handoff/ARBICORE_X_VERIFIED_EVIDENCE.md`
   - `reports/handoff/ARBICORE_X_DO_NOT_DRIFT.md`
   - `reports/handoff/ARBICORE_X_LIMITED_LIVE_GATES.md`
   - `reports/handoff/ARBICORE_X_FULL_LIVE_GATES.md`
   - `reports/handoff/ARBICORE_X_NEXT_ACTIONS.md`
   - `reports/ARBICORE_X_CURRENT_STATE_RECONCILIATION.md`
2. Inspect the current Git state: branch `takeover/limited-live-seam-cc8db95`,
   confirm HEAD, confirm the tracked working tree is clean. Do NOT delete the
   untracked artifact `reports/phase5-vps-authority-ad64a50/`.
3. Do NOT modify anything yet — no code, no config, no contracts, no deploy, no
   broadcast, no restart, no merge, no commit.

THEN, in your first reply, report back:
- A concise confirmation that you have read and understood the handoff.
- The current state as you verified it (Git HEAD/branch, safety gates, six-chain
  race numbers, executor address, Solidity test status).
- The single exact NEXT TASK you intend to start (from
  `ARBICORE_X_NEXT_ACTIONS.md` — this should be "FIRST: reconcile backend
  capability to the deployed V1 ABI", unless the admin directs otherwise), and
  the exact files you would touch.
- Any discrepancies or uncertainties you noticed (do NOT silently reconcile them).

HARD CONSTRAINTS you must preserve at all times:
- Keep safety gates OFF: signing, broadcast, full-live, auto-execution;
  runtime-autostart FALSE, scanner-autostart TRUE. Never weaken them.
- Preserve the six-chain broad-parallel North Star. Do NOT narrow the project to
  Base or to Uniswap V3 or to one strategy/provider.
- Do NOT widen execution claims (e.g. `SUPPORTED_DEXES={"uniswap_v3"}`) before a
  genuine Executor V2 exists and is deployed/tested to settle the added venues.
- Do NOT modify the V1 `FlashLoanReceiver` into a generic arbitrary-call executor;
  do NOT use an upgradeable proxy to solve the settlement boundary.
- Do NOT lower economic thresholds to force a green opportunity (0 economically
  valid is a legitimate market result).
- Do NOT modify protected files:
  `app/backend/arbicore/scanners/dex_arbitrage/scanner.py`,
  `deployment/compose/docker-compose.yml`,
  `app/backend/scripts/p0_3_flash_discovery_proof.py`.
- Do NOT touch production (container, deploy, restart, executor, signing,
  broadcast, withdrawal controls) without explicit admin approval.
- Never use `--remove-orphans`; never invoke full-stack Compose as a
  certification shortcut (known `REACT_APP_BACKEND_URL` frontend issue).
- Never fabricate opportunities, quotes, liquidity, profit, receipts, or
  execution. Fork/simulation is not real execution.
- Git write actions (commit/push/merge) are done by the admin via "Save to
  GitHub"; ask before assuming.

Current one-line status: **ArbiCore X v2 is a fail-closed six-chain read-only
searcher; discovery/quote/liquidity/economics are live across all six chains
(15 candidates, 0 economically valid — real negative edge), only Uniswap V3 is
executable on-chain via a non-upgradeable Base-Sepolia FlashLoanReceiver, all
execution is OFF, and LIMITED_LIVE_PROVEN=false. The next move is a versioned
Executor V2 secure settlement dispatcher — NOT widening capability constants.**

Confirm understanding, report the verified state, and propose the exact next task
before making any change.
