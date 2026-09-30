# ARBiCore X — VPS Current State & Emergent Engineering Handoff

Date: 2026-09-30
VPS: 144.91.78.175
Repository: raghugr2013-lgtm/arbicore-x

## 1. HANDOFF PURPOSE

This branch is a controlled engineering handoff from the validated VPS investigation to Emergent.

Do NOT merge directly to production.

Do NOT modify production runtime configuration.

Do NOT enable signing, broadcasting, autonomous execution, or live trading.

The purpose of this branch is to continue implementation of the multi-chain arbitrage engine from the validated G5.79 baseline.

---

## 2. GIT BASELINE

Canonical development baseline:

Branch:
emergent/arbitrage-engineering-handoff-20260930

HEAD:
4fec11f92fecb7f7ef1f56e39cddf18277845470

Parent lineage:
origin/impl/g5-79-multirpc-provider

Production currently runs:
4fec11f92fecb7f7ef1f56e39cddf18277845470

Important:
This handoff branch is NOT a production deployment branch.

---

## 3. PRODUCTION SAFETY POSTURE

Production remains SHADOW / detection-only.

Required production posture:

ARBICORE_SHADOW_CERT_ENABLED=true
ARBICORE_SCANNER_AUTOSTART=true
ARBICORE_AUTOEXEC_AUTOSTART=false
ARBICORE_RUNTIME_AUTOSTART=false
ARBICORE_EXECUTION_MODE=SHADOW

Signing:
OFF

Broadcast:
OFF

Autonomous execution:
OFF

Full live:
OFF

Withdrawals:
OFF

Do not change these settings as part of this handoff.

---

## 4. SIX-CHAIN SCOPE

The arbitrage architecture is intended to support all six chains:

1. Ethereum
2. Arbitrum
3. Base
4. Optimism
5. Polygon
6. BNB Chain

Do not reduce the implementation to Base-only.

---

## 5. MULTI-RPC STATUS

The VPS was validated with two configured RPC endpoints per chain.

Ethereum:
- RPC count: 2
- priority 100: Alchemy
- priority 101: publicnode
- live block read: PASS

Arbitrum:
- RPC count: 2
- priority 100: Alchemy
- priority 101: publicnode
- live block read: PASS

Base:
- RPC count: 2
- priority 100: mainnet.base.org
- priority 101: Alchemy
- live block read: PASS

Optimism:
- RPC count: 2
- priority 100: Alchemy
- priority 101: publicnode
- live block read: PASS

Polygon:
- RPC count: 2
- priority 100: Alchemy
- priority 101: publicnode
- live block read: PASS

BNB:
- RPC count: 2
- priority 100: Alchemy
- priority 101: publicnode
- live block read: PASS

Provider bootstrap is present in the G5.79 development baseline.

---

## 6. DEX PROVIDER STATUS

Currently registered/observed DEX providers:

Ethereum:
- Uniswap V3
- Uniswap V2
- SushiSwap
- Balancer V2
- 1inch
- 0x

Arbitrum:
- Uniswap V3
- SushiSwap
- 1inch
- 0x

Base:
- Uniswap V3
- 1inch
- 0x

Optimism:
- Uniswap V3
- 1inch
- 0x

Polygon:
- Uniswap V3
- 1inch
- 0x

BNB:
- Uniswap V3
- PancakeSwap
- 1inch
- 0x

Important distinction:

DEX / AMM:
- Uniswap V2
- Uniswap V3
- Balancer V2
- SushiSwap
- PancakeSwap
- future Curve where genuinely implemented

Aggregators / routing infrastructure:
- 1inch
- 0x

Liquidity providers (LPs):
LPs are users/entities supplying liquidity to DEX pools.
They are not separate arbitrage venues and should not be represented as DEX adapters.

Flash-loan providers are a separate layer:
- Aave V3
- Balancer V2
- Uniswap V3 flash
- Morpho Blue

---

## 7. LIVE QUOTE VALIDATION

Live Uniswap V3 WETH/USDC quoting has been proven on all six chains.

Examples at approximately $1,000 input:

Ethereum:
- fee 500: live quote
- fee 3000: live quote
- fee 10000: live quote

Arbitrum:
- fee 500: live quote
- fee 3000: live quote
- fee 10000: live quote

Base:
- fee 500: live quote
- fee 3000: live quote
- fee 10000: live quote

Optimism:
- fee 500: live quote
- fee 3000: live quote
- fee 10000: live quote

Polygon:
- fee 500: live quote
- fee 3000: live quote
- fee 10000: live quote

BNB:
- live quote works, but WBNB decimal handling must remain chain/token aware.

Do not assume raw integer amounts are directly comparable across tokens with different decimals.

---

## 8. CROSS-VENUE QUOTE STATUS

Ethereum was successfully tested across:

- Uniswap V3
- Uniswap V2
- 1inch
- 0x
- Balancer V2

Observed status:

Uniswap V3:
LIVE QUOTABLE

Uniswap V2:
LIVE QUOTABLE

1inch:
AUTHENTICATION REQUIRED / currently returns 401 in the tested environment

0x:
AUTHENTICATION / API integration issue; current tested endpoint returned 404

Balancer V2:
Adapter incomplete for full quote discovery.
The tested provider explicitly indicated that queryBatchSwap requires pool_id + tokens and a complete Balancer V2 quote adapter is still required.

Therefore:

Do NOT treat 1inch, 0x, or Balancer V2 as production-ready quote providers merely because provider classes exist.

Capability must be based on successful live quote + correct economics.

---

## 9. SAME-POOL ROUND TRIP RESULT

Same-pool Uniswap V3 round trips were tested.

They produced negative gross results across tested chains/sizes.

This is expected for a same-pool round trip because pool fees and price impact are paid without a cross-venue price discrepancy.

This test validates quote behavior; it is NOT an arbitrage strategy.

---

## 10. ETHEREUM V2/V3 ARBITRAGE TEST

At approximately $1,000:

V2 -> V3:
gross P/L approximately -$5.91

V3 -> V2:
gross P/L approximately -$6.28

Therefore this particular V2/V3 WETH/USDC route was not profitable at the tested size/time.

Do not hardcode this result as a permanent market condition.

The system must continuously re-quote live venues.

---

## 11. H05 / H06 STATUS

H05:
Multichain exact-size borrowing architecture was implemented and validated on the six chains in a dedicated validation environment.

Validated six-chain exact-size $1,000 probes:

Ethereum: PASS
Arbitrum: PASS
Base: PASS
Optimism: PASS
Polygon: PASS
BNB: PASS

H05 architecture includes:
- exact borrow sizing
- on-chain USD price feed
- chain-aware token decimals
- fail-closed behavior
- no hardcoded/CEX/native-token USD proxy
- canonical chain RPC usage

H06:
Canonical six-chain runtime composition and isolation work was validated in its dedicated branch/environment.

IMPORTANT:

The currently running production G5.79 image does NOT expose the newer H05/H06 helper API used by the dedicated validation branch.

The running image exposes the older Base-scoped composition path.

Therefore:
Do NOT claim that the running production image already contains the full H05/H06 runtime implementation.

Emergent should continue from the Git branches/commits containing the newer H05/H06 implementation rather than assuming the currently running image is equivalent.

---

## 12. IMPORTANT G5.130 RPC SEAM STATUS

Canonical environment variables are:

ARBICORE_RPC_URL_ETHEREUM
ARBICORE_RPC_URL_ARBITRUM
ARBICORE_RPC_URL_BASE
ARBICORE_RPC_URL_OPTIMISM
ARBICORE_RPC_URL_POLYGON
ARBICORE_RPC_URL_BNB

The intended architecture is:

ARBICORE_RPC_URL_<CHAIN>
 -> env synchronization
 -> provider registry
 -> runtime
 -> live provider

The G5.79 development baseline contains managed multi-RPC bootstrap/synchronization work.

However, the exact singular-provider bridge:

sync_provider_registry_rpc_from_env()

was NOT confirmed as the active runtime invocation path in the G5.79 branch.

Do not claim that this exact seam is complete without verifying the actual runtime path.

The managed plural provider mechanism is currently proven operational.

---

## 13. CURRENT RUNNING IMAGE DIFFERENCE

Running production-ish container:

arbicore-g5-79-app

Image:

arbicore-x-backend:g5.79-green-20260927

The running image exposes:

_wire_canonical_flash_loan_scanner()
activate_canonical_flash_loan_scanner()
run_single_canonical_flash_loan_audit_tick()

It does NOT expose:

build_h05_borrow_sizer()
build_multichain_price_source()
MultichainPriceSource
MultichainUsdPriceFeed

Its live quote provider accepts:

make_live_quote_provider(
    quoter_registry,
    tvl_provider=None,
    tvl_provider_chain='base',
    eth_call_for_chain=None,
    borrow_sizer=None
)

Therefore Emergent must reconcile the Git implementation and runtime packaging before any future deployment.

---

## 14. SIX-CHAIN OPPORTUNITY RACE

A read-only six-chain opportunity race was executed.

Observed:

67 candidates seen
58 quoted
54 liquidity verified
0 economically valid
0 positive net

Per-chain observed counts:

Ethereum:
9 seen / 9 quoted / 9 liquidity verified

Arbitrum:
15 / 14 / 14

Base:
5 / 4 / 0

Optimism:
6 / 6 / 6

Polygon:
12 / 10 / 10

BNB:
20 / 15 / 15

Important:
Zero positive opportunities in this scan does NOT mean arbitrage is impossible.

It means the tested live candidates did not pass the complete economic gate at that moment.

Base had additional RPC 401/429 issues during some probes.
Polygon experienced 529 during some probes.
RPC failover allowed the broader race to continue.

---

## 15. REQUIRED ECONOMIC GATE

Every candidate must calculate:

gross output
- principal
- DEX fees
- flash-loan fee
- gas
- routing / aggregator costs
- slippage
- safety reserve
= net profit

Unknown values MUST NOT be treated as zero.

Unknown liquidity:
DENY

Unknown quote:
DENY

Unknown gas:
DENY

Unknown flash-loan fee:
DENY

Unknown USD price:
DENY

Unknown repayment:
DENY

Stale quote:
DENY

Unsupported route:
DENY

Insufficient liquidity:
DENY

Negative or zero net profit:
DENY

Only a fully proven positive net result may progress toward later paper/limited-live eligibility.

Do not lower existing economic thresholds to manufacture opportunities.

---

## 16. REQUIRED ARBITRAGE ROUTE FAMILIES

Implement and validate all genuinely supported route families:

1. GENERIC_DEX
   Buy on cheaper venue, sell on more expensive venue.

2. TRIANGULAR
   A -> B -> C -> A

3. STABLECOIN
   Example:
   USDC -> USDT -> DAI -> USDC

4. MULTI_HOP
   Multi-token and/or multi-venue route.

5. LST_LRT
   Examples include ETH/stETH/wstETH/rETH and related liquid staking/restaking assets.
   Must have stronger liquidity, price, and settlement validation.

6. CROSS_CHAIN

CROSS_CHAIN must initially support:

A. CROSS_CHAIN_SIGNAL
   Detect price discrepancies across chains.

B. CROSS_CHAIN_INVENTORY
   Execute paired trades using pre-positioned inventory on both chains.

C. CROSS_CHAIN_SETTLEMENT
   Support only when a proven settlement/solver architecture exists.

Do NOT assume that two independent flash loans on different chains create atomic cross-chain execution.

Do NOT implement:
BUY -> BRIDGE -> SELL
as if the bridge were atomic.

Bridge settlement introduces latency and price risk.

---

## 17. FLASH-LOAN PROVIDER MATRIX

Required genuine implementations:

1. Aave V3
2. Balancer V2
3. Uniswap V3 flash
4. Morpho Blue

Flash-loan providers are funding mechanisms.

They are NOT arbitrage route types.

Each provider must be independently validated for:

- availability
- fee
- supported asset
- exact borrow amount
- repayment amount
- liquidity
- callback semantics
- gas
- chain
- failure behavior

Unknown provider economics must fail closed.

---

## 18. SIX-CHAIN x ROUTE x FLASH-LOAN MATRIX

Target architecture:

6 chains
x
all genuinely implemented route families
x
all genuinely implemented flash-loan providers
x
all genuinely implemented DEX/aggregator venues

But capability must be evidence-driven.

Do NOT fabricate support merely because a class, enum, or registry entry exists.

Every matrix cell should have a state such as:

IMPLEMENTED_AND_VALIDATED
IMPLEMENTED_BUT_AUTH_REQUIRED
IMPLEMENTED_BUT_LIQUIDITY_UNPROVEN
ADAPTER_INCOMPLETE
UNSUPPORTED
VALIDATION_REQUIRED

---

## 19. EMERGENT IMPLEMENTATION PACKAGE

Continue implementation from this branch.

Priority order:

P0:
1. Complete Balancer V2 pool discovery + queryBatchSwap quote adapter.
2. Preserve exact pool IDs, token lists, pool balances, fees, and block provenance.
3. Make missing/unknown pool data fail closed.

P1:
4. Complete/modernize SushiSwap adapter where genuinely supported.
5. Complete/modernize PancakeSwap adapter where genuinely supported.
6. Add/complete Curve native adapter only where actual deployment/pools are verified.

P2:
7. Modernize 1inch integration.
   - API key must be external configuration.
   - Never hardcode credentials.
   - Missing authentication must fail closed.
   - Record quote provenance.

8. Modernize 0x integration.
   - Verify current API contract.
   - Do not depend on obsolete endpoint assumptions.
   - Missing authentication must fail closed.

P3:
9. Implement route-family orchestration for:
   GENERIC_DEX
   TRIANGULAR
   STABLECOIN
   MULTI_HOP
   LST_LRT
   CROSS_CHAIN

P4:
10. Complete flash-loan abstraction for:
    Aave V3
    Balancer V2
    Uniswap V3 flash
    Morpho Blue

P5:
11. Integrate six-chain exact-size borrowing and live quote economics.

P6:
12. Build a machine-readable capability matrix.

P7:
13. Build deterministic paper-validation scenarios.

Do NOT proceed to limited live execution until paper validation and economic evidence are complete.

---

## 20. REQUIRED TEST COVERAGE

Add tests for:

- provider registration
- provider failover
- pool discovery
- pool provenance
- quote correctness
- token decimals
- fee calculation
- flash-loan fee
- missing API authentication
- HTTP 401
- HTTP 403
- HTTP 404
- HTTP 429
- HTTP 5xx
- malformed response
- stale pool
- stale quote
- unknown pool
- insufficient liquidity
- gas failure
- unknown USD price
- unknown fee
- zero net profit
- negative net profit
- positive net profit
- route mismatch
- repayment mismatch
- unsupported chain
- unsupported token
- slippage violation
- cross-chain settlement failure
- bridge latency/risk
- fail-closed behavior

Tests must not weaken existing safety thresholds.

---

## 21. CROSS-CHAIN DESIGN REQUIREMENT

The system must distinguish:

1. Detection
2. Execution
3. Settlement

A price difference between Ethereum and Arbitrum is a SIGNAL until the system can prove executable settlement.

A true cross-chain executable opportunity requires one of:

- pre-positioned inventory on both chains
- a proven coordinated solver/settlement mechanism
- another architecture that guarantees the required economic and settlement conditions

Do not represent a bridge transfer as atomic arbitrage execution.

---

## 22. SECURITY REQUIREMENTS

Never commit:

- private keys
- seed phrases
- API secrets
- RPC secrets
- wallet credentials
- production passwords

Use environment variables or secret management.

Never log secrets.

Never enable signing/broadcasting during development validation.

Never deploy automatically from this branch.

Never modify production directly.

---

## 23. REQUIRED DELIVERABLES FROM EMERGENT

When implementation is complete, return:

1. exact commit SHA(s)
2. changed file list
3. test command(s)
4. complete test result
5. six-chain capability matrix
6. DEX capability matrix
7. aggregator capability matrix
8. flash-loan provider capability matrix
9. route-family capability matrix
10. cross-chain capability matrix
11. explicit incomplete/blocked components
12. runtime packaging/deployment requirements
13. economic-gate evidence
14. documentation updates

Do not report a component as complete merely because its code exists.

---

## 24. NEXT VALIDATION SEQUENCE

After Emergent implementation:

1. Pull branch to isolated VPS validation checkout.
2. Run unit tests.
3. Run adapter tests.
4. Run six-chain RPC tests.
5. Run live quote tests.
6. Run pool/liquidity discovery tests.
7. Run route-family paper tests.
8. Run flash-loan economic tests.
9. Run six-chain opportunity scan.
10. Run economic gate.
11. Run deterministic paper validation.
12. Run 24-hour validation.
13. Run 72-hour validation.
14. Review evidence.
15. Only then consider limited-live readiness.

No signing or broadcasting is required for these validation stages.

---

## 25. CURRENT VPS CONDITION

The VPS currently reports:

- system restart required
- approximately 253 zombie processes

Do NOT reboot the VPS as part of this handoff.

Do NOT perform unrelated system maintenance.

---

## 26. FINAL HANDOFF PRINCIPLE

The objective is not to create more adapters or registry entries.

The objective is to produce genuinely executable, economically validated arbitrage opportunities across the supported chains and route families while remaining fail-closed and SHADOW/read-only until sufficient evidence exists.

Implementation claims must be backed by tests and live read-only evidence.

END OF HANDOFF
