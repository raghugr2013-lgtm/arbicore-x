# ArbiCore X — Flash-Loan Certification Capability Audit (read-only)

Scope: flash-loan-dependent **on-chain** arbitrage certification path. CEX/funding are
**deferred** (capital-dependent; must not block Limited Live). No code/config/DB changes made
in producing this report. **`.env` was reverted to the fail-closed baseline** (CEX/funding/runtime
autostart back OFF) after the prior activation was countermanded.

Safety verified now: `effective_kill_engaged=true`, `live_execution_enabled=false`,
`require_paper_validation=true`; SHADOW=READY, PAPER/LIMITED_LIVE/FULL_AUTOMATION=BLOCKED.

> ⚠️ **Residual to clean up (flagged, not yet actioned):** during the brief activation the boot
> gate persisted `enabled=True` for `cex_arb` + `funding_arb` in Mongo scanner-state. They are
> **dormant** now (runtime autostart off → 0 iterations, not running), but the flag should be
> reset to disabled via the existing `/scanners/{id}/kill` endpoint (NOT a Mongo reset) so they
> can't auto-start when we later enable runtime for the flash-loan path.

---

## CAPABILITY MATRIX — Network × DEX × Flash Provider × Strategy × Discovery × Paper × Shadow × Fork × Execution

Legend: **IMPL**=code exists · **CFG**=configured/wired · **DISC**=real discovery/quotes ·
**PROVEN**=fork/route/economics proven · **BLOCKED** · **NI**=not implemented.

### Base (chainID 8453) — the only real surface today
| DEX / pool | Flash provider | Strategy | Discovery | Paper | Shadow | Fork | Execution |
|---|---|---|---|---|---|---|---|
| Uniswap V3 (QuoterV2, real eth_call) | Aave V3 | DEX↔DEX | DISC-capable* | BLOCKED | infra-only only | PROVEN (blk 50,863,379: chainID+code+state-override) | CFG (UniV3 hops; signer OFF) |
| Uniswap V3 | Balancer V2 | DEX↔DEX | DISC-capable* | BLOCKED | infra-only | fork harness ready | CFG borrow coded, **on-chain UNPROVEN** |
| Aerodrome SlipStream (QuoterV2, real) | Aave V3 | DEX↔DEX | DISC-capable* | BLOCKED | infra-only | pool addr runtime-resolved | **BLOCKED exec** (executor swap = UniV3 only) |
| Aerodrome classic (getAmountsOut, real) | Aave/Balancer | DEX↔DEX | DISC-capable* | BLOCKED | infra-only | runtime-resolved | **BLOCKED exec** (UniV3-only hops) |
| UniV3↔Aerodrome multi-venue | Aave/Balancer | triangular / multi-hop | IMPL (`route_search`,`triangular.py`) | BLOCKED | infra-only | fork-ready | PARTIAL (only UniV3 legs executable) |

\* **DISC-capable but not live in this pod:** the flash-loan-arb live quote path needs a Base RPC
wired (`ARBICORE_RPC_URL_BASE`/`ARBICORE_RPC_URL`) + runtime autostart + scanner enabled. **No RPC
is wired in this Emergent pod** (available on the VPS). Default no-op quote provider returns
`None` → fail-closed (no fabricated quotes).

### Other EVM networks
| Network | chainID | DEX quoter | Flash addrs | Executor encoders | Fork/RPC | Class |
|---|---|---|---|---|---|---|
| Ethereum | 1 | class present, **QuoterV2 addr not populated** | Aave+Balancer present | present | no RPC | **CFG, BLOCKED (RPC + quoter addr)** |
| Arbitrum | 42161 | not populated | present | present | no RPC | **CFG, BLOCKED** |
| Optimism | 10 | not populated | present | present | no RPC | **CFG, BLOCKED** |
| Polygon | 137 | not populated | present | present | no RPC | **CFG, BLOCKED** |
| BNB | 56 | pancake_v3 in config, not populated | — | — | no RPC | **IMPL, BLOCKED** |
| Solana | — | Helius quote **stubbed** | n/a (no flash-arb path) | n/a | Helius key | **IMPL launch-only, NI for flash-arb** |

### Flash-liquidity providers
| Provider | Networks (addr in code) | Fee | Borrow encoder | Executor callback | Proof | Class |
|---|---|---|---|---|---|---|
| Aave V3 | base/eth/arb/op/polygon | 5 bps | `executeAave` | UniV3 hops | dry eth_call self-test path + Base fork checks | **CFG, PARTIALLY PROVEN** |
| Balancer V2 | base/eth/arb/op/polygon | 0 bps | `execute` | UniV3 hops | borrow coded, **no on-chain self-test** | **CFG, UNPROVEN** |
| Morpho / others | referenced in `provider_selection` | — | — | — | — | **NI** |

### Strategy types (flash-loan-dependent)
- DEX↔DEX (2-leg) — **IMPL + fork-ready** (Base, UniV3-executable).
- Triangular / multi-hop / multi-leg — **IMPL** (`route_search`, `triangular.py`); executable only where every leg is UniV3.
- Flash-funded route opportunities — **IMPL** (flash_loan_arb scanner, 6th emit site, DORMANT).
- Cross-venue (UniV3↔Aerodrome) — **discovery IMPL**, **execution BLOCKED** (Aerodrome hop not encodable).
- Cross-chain flash — **IMPL scaffolding**, BLOCKED (per-chain RPC + bridge data).
- Launch (Solana) — IMPL, quote stubbed, **not a flash-arb path**.

---

## A. Exact blockers to genuine PAPER
1. **No Base RPC wired in the runtime** → flash-loan-arb live quote provider returns `None` (fail-closed); zero real quotes → zero real candidates. (VPS has RPC; this pod does not.)
2. **Runtime substrate off** (`ARBICORE_RUNTIME_AUTOSTART=off`) and **flash-loan-arb scanner off** (`ARBICORE_SCANNER_FLASH_LOAN_ARB=off`, per-provider/per-chain flags False, scanner state False).
3. **No paper-evidence bundles yet** — Paper Validation component needs real processed opportunities with repayment/economics/EV passing, none produced.

## B. Exact blockers to genuine SHADOW
1. All of A (genuine shadow needs real executable evidence: `opportunities_processed>0` and `executable_rate ≥ pass`). Current shadow cert only reaches `PASS_INFRASTRUCTURE_ONLY` (0 processed).
2. A sustained real-discovery feed (flash-loan-arb on Base with RPC) driving the shadow runner.

## C. Exact blockers to LIMITED LIVE (from live readiness matrix)
Mandatory GREEN gates currently blocking: **CONFIGURATION, CONTRACTS, WALLET_SIGNER, SIMULATION,
SECURITY, SHADOW_VALIDATION**, plus **fork validation + operator-confirmed shadow/paper cert not
complete**. Concretely:
- **CONTRACTS** — executor bytecode proof (needs `ARBICORE_EXECUTOR_ADDRESS_BASE` + RPC `eth_getCode`).
- **WALLET_SIGNER** — signer readiness (intentionally OFF; must be operator-provisioned in vault, never in chat/.env).
- **SIMULATION** — 11-check sim gate must pass on real candidates (needs RPC + real quotes).
- **SHADOW_VALIDATION** — must be a real executable-evidence PASS (not infra-only; fix already landed).
- **SECURITY / CONFIGURATION** — remaining config/operator confirmations.

## D. First LIMITED-LIVE envelope (smallest genuinely-certifiable subset)
**Base · Uniswap-V3-only legs · Aave V3 flash · DEX↔DEX (2-leg) [+ UniV3-only triangular].**
Rationale: only combination where discovery quotes are real (UniV3 QuoterV2), the flash path has
a proven fork check, and every swap leg is executor-encodable. Excludes Aerodrome legs (not
executable) and Balancer (unproven) from the *first* envelope — both re-enter in expansion.
To reach it: wire Base RPC → enable flash-loan-arb (Base/UniV3/Aave) read-only → genuine Paper →
genuine Shadow → executor bytecode proof → operator-confirmed Limited Live (signer still gated).

## E. Expansion roadmap (Limited Live → maximum flash-loan coverage)
1. Add **Balancer V2** to the Base envelope: build the on-chain self-test (fork), then include 0-fee borrow.
2. Add **Aerodrome execution** (SlipStream/classic swap-hop encoding in executor) — unlocks UniV3↔Aerodrome cross-venue (discovery already real).
3. **Multi-hop / triangular** full execution (≥3 legs) once mixed-venue hops are encodable.
4. **Additional EVM networks** (Ethereum → Arbitrum → Optimism → Polygon → BNB): populate `QuoterRegistry` addresses + per-chain RPC + per-chain fork proof + executor addrs.
5. **More flash providers** (Morpho, etc.) via the existing provider interface + per-provider proof.
6. **Cross-chain flash** where economically valid (bridge + per-chain RPC).
7. Each step: Implemented → real discovery → Paper → Shadow → fork/route proof → execution certification. Never synthetic.

## F. Genuinely MISSING vs merely DISABLED/config-gated
**Disabled/config-gated (real, just off):** flash-loan-arb scanner, DEX-arb scanner, Base venue
sources, runtime autostart. Turning these on (with RPC) yields real discovery, no execution.
**Genuinely missing (must build):** Balancer on-chain self-test; executor swap-hop encoders for
Aerodrome/UniV2/pancake; populated multi-chain `QuoterRegistry`; per-chain RPC/fork proofs;
Solana flash path (none); Morpho/other providers; genuine Paper+Shadow executable evidence.

## G. Infrastructure / RPC / credentials required
- **Base read-only RPC** wired into the runtime (`ARBICORE_RPC_URL_BASE`/`ARBICORE_RPC_URL`) — **required for any genuine flash-loan discovery/quotes.** (Trace/archive already available on the VPS.)
- **`ARBICORE_EXECUTOR_ADDRESS_BASE`** (deployed FlashLoanReceiver, public address) — for CONTRACTS/bytecode proof + Balancer self-test.
- Per additional network: read-only RPC + verified QuoterV2/router/flash addresses.
- **Signer** stays in encrypted vault/KMS — never `.env`, never chat; only operator-provisioned at Limited-Live time.
- Anvil 1.7.x present on VPS for fork proofs (this pod has 1.8.1).

## H. Execution-venue limitations that block a discovered opportunity from executing
- **Executor swap hops = Uniswap V3 only** (`SUPPORTED_DEXES={uniswap_v3}`). Any discovered arb with an **Aerodrome / UniV2 / pancake** leg is **detectable but NOT executable** today → correctly rejected by executor-capability (fail-closed).
- **Balancer V2 borrow unproven on-chain** → Balancer-funded routes discover but shouldn't be certified for execution until the self-test passes.
- **Non-Base networks** have no executable path yet (no RPC/fork/quoter).
- Aerodrome pool addresses only exist after runtime `getPool` resolution (no fabricated addresses) — execution requires resolved+verified addresses.

---

## SHORTEST SAFE PATH (flash-loan, Base-first)
1. **Wire Base read-only RPC** into the runtime env (operator-provided; env-only).
2. **Enable read-only flash-loan-arb discovery on Base (UniV3 + Aave)** — `ARBICORE_RUNTIME_AUTOSTART=on` + `ARBICORE_SCANNER_FLASH_LOAN_ARB=on` + Base/UniV3/Aave per-provider flags; execution stays fail-closed.
3. **Verify genuine candidate → verify → canonical → economics/EV/size/11-check sim** on real quotes; capture evidence. If zero opportunities, report ZERO honestly.
4. **Genuine Paper evidence** → **genuine Shadow (executable-evidence) PASS**.
5. **Executor bytecode proof** (`ARBICORE_EXECUTOR_ADDRESS_BASE` + RPC).
6. **Operator-confirmed Limited Live** on the D envelope (signer provisioned in vault; kill switch authoritative; still fail-closed until each gate GREEN).
7. Then expand per §E.

**Nothing enabled. `.env` at fail-closed baseline. Awaiting approval before implementation.**
