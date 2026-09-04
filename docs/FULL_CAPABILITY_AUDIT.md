# ArbiCore X — Full Repository Capability Audit (read-only)

Objective audited against: **maximum legitimate discovery coverage across all networks,
arbitrage families, venues, and flash/liquidity providers — fail-closed**. No code changed.
Safety unchanged: kill engaged, `live_execution_enabled=false`, SHADOW=READY / PAPER /
LIMITED_LIVE / FULL_AUTOMATION=BLOCKED. Base + UniV3 + Aerodrome are the furthest-along
proving surface, **not** the intended scope.

Classification key: **IMPLEMENTED**(code exists) · **WIRED**(connected into runtime) ·
**DISCOVERABLE**(emits real candidates) · **VERIFIABLE**(real quotes/verify) ·
**CERTIFIABLE**(can reach shadow/paper evidence) · **EXECUTION-CAPABLE** · **BLOCKED** ·
**NOT IMPLEMENTED**.

---

## 1. CURRENT CAPABILITY MATRIX

### A. Networks (`config/persistent.py SUPPORTED_CHAINS`, `chains/registries.py`, `chains/evm_gas.py`)
`SUPPORTED_CHAINS = (base, ethereum, arbitrum, optimism, polygon, bnb)`; Solana appears for
launch-arb (Helius/Raydium/Pump.fun). EVM executor encoders are multi-chain in code
(`calldata.py *_BY_CHAIN` for base/ethereum/arbitrum/optimism/polygon).

| Network | chainID | Scanners wired | Real quoter | Flash providers | Executor encoders | Fork/RPC proven | State |
|---|---|---|---|---|---|---|---|
| Base | 8453 | all EVM families | ✅ UniV3 QuoterV2 + Aerodrome (real eth_call) | Aave V3 (dry-proven), Balancer V2 (borrow coded) | UniV3 hops + Aave/Balancer | ✅ fork @50,863,379, anvil 1.7.1, RPC eth_call/archive/trace | **VERIFIABLE (Base)** |
| Ethereum | 1 | families support it | quoter class present, **QuoterV2 address not wired** | Aave/Balancer addrs present | present | no RPC | **WIRED, BLOCKED (RPC+quoter addr)** |
| Arbitrum | 42161 | supported | not wired | addrs present | present | no RPC | **WIRED, BLOCKED** |
| Optimism | 10 | supported | not wired | addrs present | present | no RPC | **WIRED, BLOCKED** |
| Polygon | 137 | supported | not wired | addrs present | present | no RPC | **WIRED, BLOCKED** |
| BNB | 56 | supported (pancake_v3 in config) | not wired | — | — | no RPC | **IMPLEMENTED, BLOCKED** |
| Solana | — | launch-arb (Helius) | quote **stubbed** (D-3.1) | n/a | n/a | Helius key | **IMPLEMENTED, NOT PROVEN** |

### B. Arbitrage families (`scanners/*`, all registered in `runtime/composition.py`)

| Family | Scanner | Sources real? | Emits candidates | Verify/econ/EV | Sim gate | Boot state | Class |
|---|---|---|---|---|---|---|---|
| CEX↔CEX / CEX↔DEX | `cex_arbitrage` | ✅ real public REST (bybit/okx/kucoin/mexc/gate/bitget + binance ref) | yes | yes | yes | `ARBICORE_SCANNER_CEX_ARB=false` | **DISCOVERABLE, config-gated OFF** |
| Funding | `funding_arbitrage` | ✅ real REST (bybit/okx/hyperliquid…) | yes | yes | yes | `..._FUNDING_ARB=false` | **DISCOVERABLE, config-gated OFF** |
| DEX↔DEX | `dex_arbitrage` | ✅ Base UniV3 QuoterV2 real; other chains not wired | yes (Base) | yes | yes | `..._DEX_ARB=false` + venue sources `enabled=False` | **VERIFIABLE (Base), config-gated OFF** |
| Flash-loan | `flash_loan_arbitrage` | ✅ Base live quote provider + real economics | yes | yes | 11-check sim | wired | **VERIFIABLE (Base)** |
| Triangular/multi-hop | `flash_loan_arbitrage/triangular.py`, `route_search` | ✅ (Base) | yes | yes | yes | as above | **VERIFIABLE (Base)** |
| Cross-chain | `cross_chain_arbitrage` (bridge intel, chain liveness, transfer provider) | partial (needs per-chain RPC + bridge data) | yes | yes | yes | gated | **WIRED, PARTIAL** |
| Launch/new-token | `launch_arbitrage` (Helius/DexScreener/Pump.fun; Bitquery stubbed) | mixed real/stub | yes | yes | yes | `..._LAUNCH_ARB=false` | **IMPLEMENTED, PARTIAL** |

### C/D. Venues & Quoters
- **Real on-chain quote (eth_call):** Base — Uniswap V3 (QuoterV2 `0x3d4e…B76a`), Aerodrome
  SlipStream (QuoterV2), Aerodrome classic (`Router.getAmountsOut`). `execution/quoter.py`
  fail-closed (never fabricates). `EVMV3Quoter` has a `QuoterRegistry` keyed by (dex,chain)
  but **only Base UniV3 address is populated**; other (dex,chain) raise "no QuoterV2 address".
- **API quote:** CEX tickers + funding rates via real REST (`cex_arbitrage/sources.py`,
  `funding_arbitrage/sources.py`).
- **Stubbed / not-yet-wired:** Solana/Helius launch quote (`_quote_impl` stubbed D-3.1),
  Bitquery source (`scaffolded_only`), pancake_v3 / non-Base UniV3 QuoterV2 addresses.
- **Pool identity:** `discovery/base_pool_registry.py` — UniV3 deterministic/verified;
  Aerodrome/SlipStream addresses **unresolved until runtime `getPool`** (no fabricated
  addresses — correct fail-closed).

### E. Flash / liquidity providers
| Provider | Networks (addr in code) | Fee | Borrow path | Executor swap hops | Proof |
|---|---|---|---|---|---|
| Aave V3 | base/eth/arb/op/polygon | 5 bps | `executeAave` (relayed) | UniV3 only | dry eth_call self-test path exists; fork-ready |
| Balancer V2 | base/eth/arb/op/polygon | 0 bps | `execute` (relayed) | UniV3 only | **borrow coded, on-chain UNPROVEN** |
| others (Morpho referenced in provider_selection) | — | — | — | — | **NOT IMPLEMENTED** |

### F. Execution surfaces
`FlashLoanReceiver.execute` (Balancer) / `executeAave` (Aave); route encoders = Uniswap V3
`exactInputSingle` per hop; `SUPPORTED_DEXES={uniswap_v3}`. Signing = encrypted vault (not
ingested), broadcast gated by 5 gates (KILL→MODE→CAPITAL→SECRET→PREFLIGHT). Kill switch
authoritative. **No signer/broadcast enabled.**

---

## 2. WHAT IS ALREADY COMPLETE (real, fail-closed)
- Base real read-only quoting: Uniswap V3 QuoterV2 + Aerodrome (SlipStream + classic), eth_call, fail-closed.
- Flash-loan arb + triangular discovery/economics/EV/size-opt/provider-selection/11-check sim on Base.
- CEX-arb + funding-arb **real** market-data sources (public REST) with verifiers/economics.
- Aave V3 borrow path + dry self-test; anvil 1.7.1 bundled; Base fork validation passed (chainID, executor code, state override; signed=false/broadcast=false).
- Strategy IR + provenance governance (F1–F5). Shadow-cert honest grading (`PASS_INFRASTRUCTURE_ONLY`).
- Base canonical pool registry (UniV3 deterministic; Aerodrome runtime-resolved, no fabrication).

## 3. ONLY DORMANT / CONFIG-GATED (real code, switched off — NOT missing)
- `cex_arbitrage`, `funding_arbitrage`, `dex_arbitrage`, `launch_arbitrage` scanners: OFF via
  `ARBICORE_SCANNER_{CEX,FUNDING,DEX,LAUNCH}_ARB=false` in `backend/.env`.
- All `venue_dex_pool:*` sources `enabled=False` in `scanner_config_defaults.py` (incl. Base).
- These are **disabled by design/safety**, not unimplemented. Turning them on (read-only) adds real discovery with zero execution authority.

## 4. WIRED BUT NOT PROVEN
- Balancer V2 flash borrow (coded, no on-chain self-test).
- Cross-chain arb (needs per-chain RPC + live bridge data).
- Non-Base EVM DEX quoting (QuoterRegistry lacks non-Base addresses; needs per-chain RPC).
- Genuine executable-evidence Shadow Certification (only infra-only achieved).
- Paper Validation evidence; WALLET_SIGNER readiness.

## 5. ACTUAL IMPLEMENTATION GAPS (truly missing)
- Populated multi-chain `QuoterRegistry` (real, verified QuoterV2 addresses per dex×chain).
- Solana/Helius real quote (`_quote_impl` stubbed); Bitquery source (scaffold only).
- Executor swap-hop support beyond Uniswap V3 (UniV2/Aerodrome/pancake) — deferred.
- Non-EVM (Solana) execution surface.
- Morpho / additional flash providers.

## 6. NETWORK × FAMILY × VENUE × FLASH-PROVIDER MATRIX (condensed)
- **Base:** DEX↔DEX (UniV3, Aerodrome) VERIFIABLE; flash-arb/triangular VERIFIABLE (Aave dry, Balancer coded); CEX/funding DISCOVERABLE (network-agnostic). → **the only CERTIFIABLE EVM surface today.**
- **Ethereum/Arbitrum/Optimism/Polygon:** families + executor encoders WIRED; **BLOCKED on per-chain RPC + QuoterV2 addresses.**
- **BNB:** pancake_v3 in config, BLOCKED (RPC + quoter + executor addrs).
- **Solana:** launch-arb IMPLEMENTED but quote stubbed → NOT PROVEN.
- **CEX/funding families:** venue-based, network-agnostic, real data, **DISCOVERABLE now** (config-gated OFF).

## 7. ARCHITECTURAL BOTTLENECKS
1. **QuoterRegistry is single-chain-populated.** Discovery breadth across EVM chains is gated by missing (dex,chain)→QuoterV2 address entries, not by missing logic. Generic registry already exists → fill it (per-chain RPC required).
2. **Per-chain RPC provisioning** (only Base RPC available). Every non-Base on-chain proof blocks here.
3. **Executor swap venue = UniV3 only** — caps *execution* breadth (not discovery).
4. **Scanner boot flags are coarse** (`ARBICORE_SCANNER_*`), gating whole families rather than per read-only-safe source.
5. Solana path diverges from EVM (separate quote/execution) — genuine second architecture.

## 8. SHORTEST SAFE PATH TO MAXIMUM DISCOVERY COVERAGE
Maximize discovery breadth **without** touching execution authority, in this order:
1. **Turn on the already-real, RPC-free discovery families in read-only/shadow:** CEX-arb + funding-arb (real public REST; network-agnostic). Biggest instant coverage jump, no RPC, no execution.
2. **Turn on Base DEX-arb real-quote discovery** (UniV3 + Aerodrome QuoterV2 already real; Base RPC available). Enables genuine executable-evidence toward real Shadow Certification.
3. **Populate the generic QuoterRegistry** for additional EVM chains as their read-only RPCs are provided (Ethereum → Arbitrum → Optimism/Polygon → BNB).
4. **Cross-chain + launch** discovery once their data sources/RPCs are provisioned.
Downstream gates (verify → economics → EV → size → provider → 11-check sim → paper → shadow)
decide eligibility; discovery breadth is decoupled from execution risk.

## 9. RECOMMENDED IMPLEMENTATION ORDER
1. CEX-arb + funding-arb read-only activation (+ tests, evidence).
2. Base DEX-arb read-only activation → drives genuine executable-evidence shadow cert.
3. Balancer V2 on-chain self-test (Base) once executor address supplied.
4. Multi-chain QuoterRegistry population (per-chain RPC).
5. Cross-chain + launch/Solana real quoting.
6. Executor venue expansion (UniV2/Aerodrome hops) — only if value-justified.

## 10. EXACT FIRST ENGINEERING TASK
**Activate the already-real, RPC-free discovery families (CEX-arb + funding-arb) in read-only
SHADOW mode, and surface their live candidate emission — without enabling any execution.**
- Flip `ARBICORE_SCANNER_CEX_ARB` and `ARBICORE_SCANNER_FUNDING_ARB` to `true` in `backend/.env`
  (their sources + verifiers + economics already real and enabled in config).
- Confirm candidates flow: source → scanner → candidate → verify → canonical opportunity feed,
  read-only, with all execution gates closed and kill switch engaged.
- **Why this first (not docs/plumbing):** it is the single largest increase in *genuine* discovery
  coverage available with **zero new infrastructure and zero execution authority** — real
  exchange data already wired, merely gated off. It also begins producing real, non-fabricated
  opportunity evidence that later feeds paper/shadow certification.
- **Why not "Base DEX-arb first":** also excellent and should be second; it needs the Base RPC
  wired into this env and touches the on-chain quote path, so it carries slightly more surface.
  Foundational architectural change (QuoterRegistry multi-chain fill) is **not** required for
  this first step and is deferred to step 4.

## 11. TESTS REQUIRED (for the first task)
- Scanner activation: CEX-arb + funding-arb start under supervisor; `is_running()` true; iterations increment.
- Real-data ingest: sources return live tickers/funding (mock the HTTP layer in unit tests; one guarded live smoke check).
- Candidate emission: ≥1 real candidate reaches the canonical opportunity feed with provenance.
- Safety invariants (regression): `live_execution_enabled=false`, kill engaged, no signer, sim gate still rejects (no auto-executable), readiness LIMITED_LIVE stays RED.
- No fabrication: assert every emitted candidate carries a real source ref + real price fields (no placeholder).

## 12. EVIDENCE REQUIRED
- Live candidate counts per family/venue over a window; sample candidates with source provenance + timestamps.
- Readiness snapshot before/after (overall YELLOW; LIMITED_LIVE RED unchanged).
- Safety-status snapshot (kill engaged, live off) unchanged.

## 13. CERTIFICATION REQUIREMENTS
- Genuine executable-evidence Shadow Certification needs **opportunities_processed>0 and executable_rate ≥ pass** — achievable only once real discovery (step 1–2) feeds the paper/shadow runner.
- Paper Validation evidence bundles; WALLET_SIGNER readiness; fork/operator authorization — all remain prerequisites for any live mode. No live mode auto-enables.

## 14. WHAT MUST REMAIN DISABLED
Signer ingestion/activation, broadcast, live execution, auto-confirm; executor swap-venue
expansion until justified; Solana execution; any non-Base on-chain execution; Strategy-IR reverse
control path. Kill switch authoritative. No Mongo reset/drop. No gate bypass. No fabricated
prices/pools/liquidity/profit.

---

**Bottom line:** the system is already a broad, multi-family, multi-venue discovery engine whose
breadth is mostly **config-gated OFF**, not missing. The fastest, safest way to move toward
maximum genuine discovery coverage is to switch on the already-real RPC-free families (CEX +
funding) read-only, then Base DEX-arb, then fill the generic multi-chain quoter as RPCs arrive —
keeping execution authority minimized and fail-closed throughout.
