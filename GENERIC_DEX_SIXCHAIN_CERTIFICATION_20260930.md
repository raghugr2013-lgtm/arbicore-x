# GENERIC_DEX Six-Chain Shadow Economic Certification

Date: 2026-09-30

## Scope

GENERIC_DEX two-leg round-trip economic validation:

WETH -> USDC -> WETH

Flash provider:

Aave V3

Validation size:

USD 1,000

Minimum atomic profit floor:

USD 25

Execution posture:

SHADOW / detection and economic evaluation only

Signing:

DISABLED

Broadcast:

DISABLED

Live execution:

DISABLED

## Implementation

Canonical GENERIC_DEX implementation commit:

57618f6cf9154173cc21c15af81d4aa79c94b36e

The route engine uses:

- QuoterRegistry for live route quotes
- route-level gas aggregation
- canonical ChainGasModel
- native wrapped-token pricing
- flash-loan economics
- immutable USD 25 minimum atomic-profit floor
- fail-closed unknown gas/price/liquidity conditions

## Six-Chain Live Certification

### Ethereum

WETH/USD:
2691.132533

Route gas:
177473

Result:
non_positive_net

Eligible:
false

Gross profit:
-1.012294 USD

Gas:
0.355048 USD

Flash fee:
0.500000 USD

Net:
-6.867342 USD

### Arbitrum

WETH/USD:
2691.264183

Route gas:
191366

Result:
non_positive_net

Eligible:
false

Gross profit:
-1.010115 USD

Gas:
0.013348 USD

Flash fee:
0.500000 USD

Net:
-6.523463 USD

### Base

WETH/USD:
2691.164723

Route gas:
159248

Result:
non_positive_net

Eligible:
false

Gross profit:
-1.026847 USD

Gas:
0.003231 USD

Flash fee:
0.500000 USD

Net:
-6.530077 USD

Gas model:
BaseGasModel

### Optimism

WETH/USD:
2680.069504

Route gas:
300866

Result:
non_positive_net

Eligible:
false

Gross profit:
-4.048903 USD

Gas:
0.001033 USD

Flash fee:
0.500000 USD

Net:
-9.549936 USD

### Polygon

WETH/USD:
2687.774380

WMATIC/USD:
0.1138

Route gas:
357308

Result:
unknown_gas

Eligible:
false

Reason:

Canonical Polygon gas model failed closed because the live gas-price condition exceeded the configured gas-price ceiling.

No gas-price ceiling was reduced for certification.

### BNB Chain

WETH/USD:
2438.023049

WBNB/USD:
611.015488

Route gas:
404463

Result:
non_positive_net

Eligible:
false

Gross profit:
-81.537706 USD

Gas:
0.015446 USD

Flash fee:
0.500000 USD

Net:
-87.053152 USD

## Certification Interpretation

All six chains reached a deterministic fail-closed decision.

Five chains reached the economic gate and correctly rejected the tested round trip because net profit was non-positive.

Polygon correctly failed closed at the gas validation layer because its live gas-price condition exceeded the configured safety ceiling.

No chain was forced into eligibility by lowering an economic or gas threshold.

## Test Evidence

Focused GENERIC_DEX route and gas tests:

53 passed

Combined GENERIC_DEX + SP5 + H06 targeted gate:

71 passed

No repository modifications were produced by the disposable live certification harness.

## Safety

This certification did not:

- sign transactions
- broadcast transactions
- activate live execution
- modify production configuration
- modify the production checkout
- lower economic thresholds
- lower gas-price ceilings
- transfer funds

## Status

GENERIC_DEX:

CERTIFIED FOR SIX-CHAIN SHADOW ECONOMIC EVALUATION

Not certified for live execution.

Next route-family package:

TRIANGULAR
