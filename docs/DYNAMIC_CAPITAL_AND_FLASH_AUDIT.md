# ArbiCore X — Flash-Loan Path + Dynamic Capital/Sizing Audit (read-only)

CEX/funding DEFERRED. No code/config/DB changes in this report (the only action taken was the
approved scanner-state cleanup via `/kill`). Safety: kill engaged, live_exec=false, signer/
broadcast/withdraw/automation OFF, PAPER/LIMITED_LIVE/FULL_AUTOMATION BLOCKED.

## 1. Residual CEX/funding cleanup — DONE
| Scanner | Before | After |
|---|---|---|
| cex_arb | enabled=True, iter=0 | **enabled=False**, iter=0, last_run=None, not running |
| funding_arb | enabled=True, iter=0 | **enabled=False**, iter=0, last_run=None, not running |
Via `/scanners/{id}/kill` only (no Mongo writes). Runtime autostart remains `false`; kill engaged;
live_exec false; PAPER/LIMITED_LIVE/FULL_AUTOMATION blocked. Verified post-restart.

## 2–3. Dynamic wallet-balance capability

**Components that genuinely exist (real, read-only):**
- `execution/wallet_balance.py` — real `eth_getBalance` reader, multi-chain (eth/base/arb/op/polygon), RPC failover, never holds keys, returns `balance_wei/native/usd + block_number`, fail-closed.
- `execution/capital_policy.py::CapitalAllocator` — three independent hard limits, **smallest wins**: `max_pool_percent=0.5%` (of borrow-pool liquidity), `max_wallet_percent=20%` (of reference capital), `max_per_plan_usd=$2.5k`, `daily_notional=$10k`, `min_net_profit=$0.50`, `max_daily_loss=$100` stop-loss, `max_concurrent_plans=3`.
- `scanners/flash_loan_arbitrage/borrow_sizing.py` — liquidity/executor/sim-aware `BorrowSizeEval`; `feasible` requires quote_complete + economics_ok + net_profit>0 + liquidity_sufficient + executor_supported + atomic_sim_passed (fail-closed; selects an optimal feasible size, not blind max).
- `execution/pre_broadcast.py` — fresh re-read gate: block freshness, reorg protection, deadline, fresh quote, fresh price, MEV cap, real-time flash-loan availability; any None/stale/error ⇒ DENIED.
- `execution/broadcast.py:493` — **wires live balance → sizing**: `reference_capital_usd = float(_bal.balance_usd)`, and `None` when unavailable (fail-closed).

**The gap (this is the important part):**
- The **pipeline** capital gate (`pipeline.py:819`) calls `allocator.evaluate(...)` **without** `reference_capital_usd`, so it falls back to the **hard-coded default `5_000.0`** (`capital_policy.py:208`, `live_signer.py:106`, `available_liquidity_usd=1_000_000.0`). i.e. the *plan-time* wallet-percent limit is computed off a **fixed reference capital**, not the live on-chain balance. Only the **broadcast-time** path reads the live balance.
- No single **protected-gas-reserve gate** that refuses/reduces when `balance < required_gas + reserve` (gas is checked in the operator wizard and pre-broadcast reads balance, but there is no unified "reserve floor" hard gate in the sizing path).
- No explicit **balance-delta fail-closed** between sizing-time and broadcast-time (pre-broadcast revalidates *market* freshness, not "wallet balance changed since sizing → abort").

**Explicit answers to the 20 questions:**
1. Read live native balance? **YES** (`wallet_balance.py`, real eth_getBalance).
2. Distinguish gas capital / flash notional / gas reserve / max exposure / optimal size? **PARTIAL** — flash notional, exposure limits, optimal size = yes; explicit *gas reserve* bucket = weak.
3. Configurable protected gas reserve? **PARTIAL** (`ARBICORE_SAFETY_BUFFER_USD` exists; not a dedicated native-gas reserve floor).
4. Refuse when balance can't cover gas+reserve? **PARTIAL/NO** (no unified hard gate).
5. Size optimizer uses real DEX quote/liquidity? **YES** (borrow_sizing consumes real per-size economics/liquidity; quoter is real eth_call).
6. Accounts for rising price-impact/slippage with size? **YES** (per-size evaluation).
7. Accounts for real gas? **YES** (`execution/gas.py`, gas units per step + gas price).
8. Per-provider fee model? **YES** (Aave 5bps, Balancer 0bps in economics/provider_selection).
9. Max safe flash amount? **YES** (borrow-size sweep + pool% cap).
10. Economically optimal vs blind max? **YES** (selects feasible+profitable, not max liquidity).
11. Recalculate from CURRENT balance every attempt? **PARTIAL** — broadcast path re-reads; pipeline gate uses fixed 5000.
12. Re-read balance/market immediately before execution? **PARTIAL** — market yes (pre_broadcast); balance re-read in broadcast, but not a delta-abort gate.
13. Balance changed between sizing & execution → fail closed? **NO (gap)** — not an explicit gate.
14. Hard max-notional/liquidity%/slippage/gas/loss/exposure limits? **YES** (capital_policy + pre_broadcast loss breakers).
15. Limits independent of balance reading? **YES** (they are separate hard caps).
16. Auto-scale UP as balance grows? **PARTIAL** — only if reference_capital is sourced live (broadcast path yes; plan path no).
17. Auto-scale DOWN / stop as balance falls? **PARTIAL** — same caveat + stop-loss exists.
18. Any fixed initial-capital assumption in the live path? **YES (defect)** — `reference_capital_usd=5_000.0` default reached by the pipeline gate; `available_liquidity_usd=1_000_000.0` default in signer. (The `$100` values elsewhere are stop-loss/percentage math, not capital; `discovery.py 0.1 WETH` is a wiring seed, not live.)
19. Funded amount treated as permanent volume ceiling? **NO** — caps are %/absolute policy, not a frozen initial amount.
20. Runtime call path traced? **YES** (below).

## 5. Exact runtime call path (sizing → execution)
`scanner._tick (flash_loan_arb, real quote via QuoterV2 eth_call)` → candidate → verifier →
canonical opportunity → `execution/pipeline.py` stages: economics/EV → **borrow_sizing sweep**
(real liquidity/executor/sim per size) → **capital allocator gate** (`pipeline.py:819`,
*uses fixed 5000 ref-capital* ⚠️) → 11-check simulation → plan → `live_signer.sign_plan`
(kill→mode→**capital_policy**→…; ref_capital default 5000 ⚠️; emits NO signed bytes in current
wave) → `pre_broadcast.validate` (fresh re-read, fail-closed) → `broadcast.py` (*reads live
balance → reference_capital*, but broadcast disabled). Kill switch guards every entry.

## 6. Fixed-capital assumptions — verdict
Live balance reading + dynamic sizing exist and are used at broadcast time, but the **plan-time
capital gate defaults to a fixed $5,000 reference capital** instead of the live balance. That is
the single concrete "fixed capital" defect to fix. No $100 initial-capital ceiling exists.

### I. Core question — **PARTIAL**
*"Can current ArbiCore automatically use whatever balance is actually in the execution wallet and
dynamically size each opportunity without a fixed initial capital amount?"*
**PARTIAL.** The pieces exist (real balance reader, optimal liquidity-aware sizing, dynamic
reference-capital at broadcast, fail-closed revalidation, hard caps), but (a) the **plan-time**
capital gate must be wired to the **live balance** instead of the 5000 default, (b) a **protected
gas-reserve floor** gate should be added, and (c) a **balance-delta fail-closed** check between
sizing and broadcast. None is proven end-to-end (no genuine executable evidence yet).

Classification: **C (partially implemented)** for the dynamic-balance→sizing wiring;
**B (implemented, not proven)** for the balance reader + borrow-sizing + pre-broadcast.

## 7–9. Blockers
- **Genuine PAPER:** no Base RPC wired in this pod → flash quote provider returns None → 0 real candidates; runtime + flash_loan_arb scanner off; no paper evidence bundles.
- **Genuine SHADOW:** all of PAPER; shadow only reaches PASS_INFRASTRUCTURE_ONLY (0 processed); needs sustained real executable evidence.
- **LIMITED_LIVE (from live matrix):** CONFIGURATION, CONTRACTS (executor bytecode via `eth_getCode`+`ARBICORE_EXECUTOR_ADDRESS_BASE`), WALLET_SIGNER (vault-only), SIMULATION (real quotes), SECURITY, SHADOW_VALIDATION (real PASS), + operator-confirmed fork/shadow/paper. **Plus** the dynamic-capital wiring fix above should land before funding a wallet.

## 10. Smallest certifiable Limited-Live envelope
**Base · Uniswap-V3-only legs · Aave V3 flash · DEX↔DEX (+ UniV3-only triangular).** Only combo
with real quotes + fork-proven flash + fully executor-encodable legs.

## 11. Expansion path
Base Balancer self-test → Aerodrome execution encoder (unlocks UniV3↔Aerodrome) → full multi-hop
→ other EVM networks (populate QuoterRegistry + per-chain RPC + fork) → more providers (Morpho) →
cross-chain. Each: Implemented→Real Discovery→Paper→Shadow→Fork/Route→Execution Certified.

## 12. Capability matrix (Network × DEX × Flash × Strategy × Discovery × Paper × Shadow × Fork × Execution)
| Net | DEX | Flash | Strategy | Disc | Paper | Shadow | Fork | Exec |
|---|---|---|---|---|---|---|---|---|
| Base | UniV3 | Aave V3 | DEX↔DEX | REAL-capable* | BLOCKED | infra-only | **PROVEN** | CONFIGURED |
| Base | UniV3 | Balancer V2 | DEX↔DEX | REAL-capable* | BLOCKED | infra-only | harness ready | CONFIGURED (on-chain UNPROVEN) |
| Base | UniV3 | Aave | triangular/multi-hop | IMPLEMENTED | BLOCKED | infra-only | ready | PARTIAL (UniV3 legs only) |
| Base | Aerodrome (SlipStream/classic) | Aave/Bal | DEX↔DEX | REAL-capable* | BLOCKED | infra-only | pool runtime-resolved | **BLOCKED exec** (UniV3-only encoder) |
| Eth/Arb/Op/Poly | UniV3 | Aave/Bal | all | CONFIGURED | BLOCKED | — | — | BLOCKED (RPC+quoter addr) |
| BNB | pancake_v3 | — | all | CONFIGURED | — | — | — | BLOCKED |
| Solana | — | — | launch only | IMPLEMENTED (quote stub) | — | — | — | NOT IMPLEMENTED (flash) |

\* REAL-capable = real quoter exists; needs Base RPC wired + scanner/runtime on to actually emit (fail-closed otherwise).

## 13. Implemented vs merely disabled
- **Disabled/config-gated (real, off):** flash_loan_arb + dex_arb scanners, Base venue sources, runtime autostart.
- **Genuinely missing:** dynamic-balance→plan-sizing wiring + gas-reserve gate + balance-delta abort; Balancer on-chain self-test; Aerodrome/UniV2 executor swap encoders; populated multi-chain QuoterRegistry; per-chain RPC/fork proofs; Morpho/other providers; genuine Paper+Shadow evidence.

## 14. Infrastructure / credentials
Base read-only RPC wired into runtime (`ARBICORE_RPC_URL_BASE`) — required for any real discovery/
quotes/balance-USD; `ARBICORE_EXECUTOR_ADDRESS_BASE` for bytecode proof; per-network RPC + verified
QuoterV2/router/flash addrs; native-USD price source for balance_usd; signer vault-only (never .env/chat).

## 15. Execution-venue limitations
Executor swap hops = **Uniswap V3 only** → Aerodrome/UniV2/pancake legs detectable but NOT
executable (fail-closed); Balancer borrow unproven on-chain; non-Base has no executable path;
Aerodrome pools require runtime `getPool` resolution before execution.

## 16. Tests / evidence supporting conclusions
- Base fork validation (existing evidence): chainID OK, executor has code, state override OK, signed=false/broadcast=false — treated as existing, not re-run.
- Code-traced: `wallet_balance.py` (real eth_getBalance), `broadcast.py:493` (live→reference_capital), `pipeline.py:819` + `capital_policy.py:208` + `live_signer.py:106` (fixed 5000 default), `borrow_sizing.py` (fail-closed feasibility), `pre_broadcast.py` (fresh re-read).
- No genuine Paper/Shadow executable evidence exists yet (honest ZERO).

## 17. Next implementation step — ranked (await approval)
1. **[P0] Wire dynamic capital:** source `reference_capital_usd` (and available_liquidity) from the live `wallet_balance` reading in the **plan-time** capital gate (`pipeline`/`live_signer`), remove the 5000 default from the live path, add a **protected native-gas-reserve floor** gate, and a **balance-delta fail-closed** check between sizing and broadcast. Pure safety/sizing, no execution enabled. Unit-testable offline (no RPC).
2. **[P0] Wire Base read-only RPC** into runtime env (operator-provided) to enable real flash-loan discovery.
3. **[P1] Enable read-only flash_loan_arb (Base/UniV3/Aave)** → capture genuine candidate→verify→canonical→economics→sim evidence (ZERO reported honestly if none).
4. **[P1] Genuine Paper → genuine Shadow** on that real feed.
5. **[P2] Executor bytecode proof**, then operator-confirmed Limited Live on the §10 envelope.

**Recommended first task: P0 #1 (dynamic-capital wiring)** — it removes the only fixed-capital
defect, is offline/unit-testable, needs no RPC, and must precede any wallet funding. It does not
enable execution.

*Report only. No implementation started. Awaiting approval.*
