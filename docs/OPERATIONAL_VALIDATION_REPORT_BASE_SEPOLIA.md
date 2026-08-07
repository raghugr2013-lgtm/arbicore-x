# Operational Validation Report — Base Sepolia Readiness

**Date:** 2026-06 · **Session type:** shortest-safe-path to LIMITED_LIVE
**Rule honored:** no private keys, no irreversible on-chain transactions.
Work stopped at the first operator gate (deployer key / burner wallet /
broadcast approval), exactly as directed.

Target posture: **Base Sepolia** (public RPC, configurable via
`ARBICORE_RPC_URL`). Governance preserved: `flash_loan_arbitrage = SHADOW`,
no live trading, autonomous loop halts before broadcast.

---

## Slices delivered this session

### Slice 1 — Workspace bring-up & config wiring  ✅
- Created minimal `backend/.env` (`MONGO_URL`, `DB_NAME`,
  `ARBICORE_RPC_URL=https://sepolia.base.org`) and `frontend/.env`
  (`REACT_APP_BACKEND_URL`). Backend + frontend + Mongo all RUNNING.
- Backend boots clean; connects to live exchange feeds
  (Kraken/Coinbase/KuCoin/OKX OK; Binance/Bybit geo-blocked — expected)
  and to Base Sepolia RPC (HTTP 200).
- **Genuine defect found + fixed:** `operator_wizard._rpc_post` used
  `urllib` with no `User-Agent`; the public Base RPC (Coinbase CDP) 403s
  the default `Python-urllib` UA. Added a browser-like UA header. This was
  on the LIMITED_LIVE critical path (readiness + executor verify).
- After fix, `GET /api/arbicore/rpc/check` → **READY, chain_id=84532,
  live block 45,165,541.**

### Slice 2 — Executor package: compile + test + single-action deploy  ✅
- Installed Foundry 1.7.1. `forge build` OK — runtime bytecode **4987 bytes**
  (`solc 0.8.24`, `via_ir`, 200 runs). `forge test` → **8/8 PASS**
  (Balancer + Aave happy-paths + all access-control reverts).
- Selectors verified against Python encoders: `execute`=`64ba4bc1`,
  `executeAave`=`4343d8b2`, `receiveFlashLoan`=`f04f2707`,
  `executeOperation`=`1b11d0ff`.
- Made `Deploy.s.sol` **chain-aware** (auto-selects Base Sepolia vs
  mainnet venue set by `block.chainid`) and pre-filled **verified Base
  Sepolia venue addresses** (Aave V3 Pool `0x8bAB…aE27`, UniV3 SwapRouter02
  `0x94cC…2bc4`). Balancer V2 unconfirmed on Sepolia → first testnet flash
  loan uses the **Aave V3 head**.
- **Dry-run deploy simulation against Base Sepolia succeeded** (no
  broadcast, no key): constructor executes, est. gas ~1.47M (~0.0000162 ETH).
- Exported `contracts/artifacts/FlashLoanReceiver.abi.json` + bytecode.
  Runbook: `contracts/docs/DEPLOY_RUNBOOK_BASE_SEPOLIA.md`.
- Git kept clean (`out/`, `cache/`, `broadcast/` gitignored; dry-run
  artifacts removed).

### Slice 3 — End-to-end pipeline validation (up to, not incl. broadcast)  ✅- Autonomous loop running unattended: AutoExecutor 30s ticks, opportunities
  evaluated and journalled, all terminal in SHADOW → `REJECTED/NEUTRAL`
  (e.g. −$1.51 unprofitable). **Zero broadcasts. Zero operator intervention.**
- 10-step wizard (`/wizard/state`) reports honestly: kill_switch READY;
  rpc WAIT (Sepolia, mainnet gate wants 8453); mode WAIT (SHADOW);
  **wallet + executor BLOCKED** — the operator gates.
- Frontend operator UI loads (first-run admin-setup screen on fresh DB).
- Regression: 26/26 wizard + Aave-calldata unit tests PASS.

---

## Slice 4 — Operator Opportunity Probe (live quotes on Base Sepolia)  ✅

- New READ-ONLY endpoint `POST /api/arbicore/wizard/opportunity-probe`
  (integrates the existing `QuoterRegistry` + live `eth_call` path; no new
  engine). Probes UniV3 fee tiers 500/3000/10000 for a pair and reports
  which return a live quote. **No broadcast, no signing.**
- Additive: registered the Base Sepolia UniV3 QuoterV2
  (`0xC5290058841028F1614F3A6F0F5816cAd0df5E27`) under chain key
  `base-sepolia` in `quoter.py` — mainnet `base` routing unchanged.
- **Result: Base Sepolia has LIVE WETH/USDC pools on all 3 tiers** at
  block 45,167,561 — 0.01 WETH → {1.986168 (5bps), 2.079572 (30bps),
  2.067428 (100bps)} USDC. A real cross-tier spread is visible — exactly
  the EXECUTABLE candidate an operator can watch pre-broadcast.
- Verified by testing_agent: **7/7 backend tests PASS, 0 issues**
  (`/app/backend/tests/test_arbicore_opportunity_probe.py`). Confirmed
  mainnet routing intact and governance (SHADOW) preserved.
- Also swept the urllib-403 class of defect across execution modules:
  only `operator_wizard._rpc_post` was affected (fixed); `simulation.py`
  + `wallet_balance.py` use httpx / only `urllib.parse`; broadcast + gas
  use httpx. No further UA changes needed.

---

## The credential gate (where this session stops)

Everything achievable without secrets is DONE and verified. The next
four items are irreversible / secret-bearing and require the operator:

| # | Action | Blocking input |
|---|---|---|
| 1 | Deploy `FlashLoanReceiver` to Base Sepolia (`forge script … --broadcast`) | **funded Base Sepolia deployer private key** (~0.00002 ETH) |
| 2 | Set `ARBICORE_EXECUTOR_ADDRESS_BASE`, `/executor/verify` → READY | (agent, once #1 done) |
| 3 | First tiny flash loan (Aave V3 head), tiny notional | **burner wallet key** + broadcast approval |
| 4 | Flip `flash_loan_arbitrage` → LIMITED_LIVE (after green stripe) | operator mode approval |



| Step | Owner | Gate |
|---|---|---|
| Fund a deployer key + `forge script … --broadcast` (Base Sepolia) | Operator | **deployer private key** |
| Set `ARBICORE_EXECUTOR_ADDRESS_BASE`; `/executor/verify` → READY | Operator/agent | — |
| Register + fund burner gas wallet; Fernet-wrap key | Operator | **burner wallet + key** |
| Flip `flash_loan_arbitrage` SHADOW→LIMITED_LIVE; certifier pass | Operator | mode approval |
| First LIMITED_LIVE broadcast (Aave V3 head, tiny notional) | Operator | **on-chain broadcast approval** |
| After green Sepolia stripe → promote **same build** to Base mainnet | Operator | mainnet broadcast approval |

No further non-credential engineering is required to reach the first
broadcast. Resume implementation only if an operator step surfaces a
genuine defect.
