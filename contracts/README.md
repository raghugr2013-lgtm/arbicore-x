# ArbiCore X — Executor Contract Package

Foundry-based Solidity project for the canonical **FlashLoanReceiver**
executor. Deploy-ready, unit-tested, and pre-verified against the
Python calldata encoders in the ArbiCore X backend.

**Status (2026-08-06):** built + tested. **Not broadcast to any network.**

---

## Layout

```
contracts/
├── foundry.toml              — Foundry config (solc 0.8.24, via_ir)
├── remappings.txt            — forge-std/=lib/forge-std/src/
├── .env.example              — Env template (RPC + BaseScan + venue addrs)
├── contracts/
│   ├── core/
│   │   └── FlashLoanReceiver.sol   — Canonical executor
│   ├── adapters/
│   │   ├── UniswapV3Adapter.sol    — hop-runner library
│   │   └── AaveV3Adapter.sol       — repay helper library
│   ├── interfaces/
│   │   ├── IERC20.sol
│   │   ├── IBalancerV2Vault.sol
│   │   ├── IAaveV3Pool.sol
│   │   ├── IUniswapV3SwapRouter.sol
│   │   └── IExecutor.sol
│   ├── libraries/
│   │   ├── TransferHelper.sol      — safe transfer + approve
│   │   └── Errors.sol              — canonical revert selectors
│   └── tests/
│       ├── MockERC20.sol
│       ├── Mocks.sol               — Vault / Pool / Router mocks
│       └── FlashLoanReceiver.t.sol — 8 Foundry unit tests
├── script/
│   ├── Deploy.s.sol                — one-command deploy
│   └── Verify.s.sol                — verify helper
└── docs/
    ├── DEPLOYMENT.md               — step-by-step deploy guide
    └── VERIFICATION.md             — post-deploy checklist
```

## Quick start

```bash
# Prerequisites (one-time)
curl -L https://foundry.paradigm.xyz | bash
foundryup

# Build + test
cd /app/contracts
forge build
forge test          # ⇒ 8/8 passing

# Deploy (Base Sepolia dry-run first — see docs/DEPLOYMENT.md)
cp .env.example .env
${EDITOR:-vi} .env  # fill in RPC + key
source .env
forge script script/Deploy.s.sol:Deploy \
    --rpc-url base_sepolia --broadcast --verify -vvvv
```

## Key invariants

- **Owner** = deployer EOA (immutable, no transfer path).
- **Providers** = Balancer V2 (0 bps) + Aave V3 (5 bps).
- **DEX** = Uniswap V3 SwapRouter02.
- **No standing balances** between transactions — every wei of borrowed
  capital is repaid before the top-level flash returns; residuals go to
  `profitRecipient`.
- **No upgrade path** — redeploy for schema changes.

## Python selector parity

The Python encoders in `/app/app/backend/arbicore/execution/calldata.py`
emit exactly the same 4-byte selectors as the compiled contract:

| Signature                                          | Selector       |
| -------------------------------------------------- | -------------- |
| `execute(address[],uint256[],bytes)`               | `0x64ba4bc1`   |
| `executeAave(address,uint256,bytes)`               | `0x4343d8b2`   |
| `flashLoanSimple(address,address,uint256,bytes,uint16)` | `0x42b0b77c` |
| `flashLoan(address,address[],uint256[],uint256[],address,bytes,uint16)` | `0xab9c4b5d` |

## Docs

- [DEPLOYMENT.md](./docs/DEPLOYMENT.md) — step-by-step deploy procedure
  for Base + Base Sepolia.
- [VERIFICATION.md](./docs/VERIFICATION.md) — post-deploy checklist
  operators must complete before promoting to `LIMITED_LIVE` mode.
