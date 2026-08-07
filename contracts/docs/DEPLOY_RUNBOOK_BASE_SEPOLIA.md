# Executor Deployment Runbook — Base Sepolia → Base Mainnet

**Status:** Compiled ✓ · 8/8 Foundry tests ✓ · Base Sepolia deploy
**simulated** ✓ (chain-aware, dry-run, no key). Deployment is now a
**single operator action** blocked only on a funded deployer key.

Contract: `contracts/contracts/core/FlashLoanReceiver.sol`
Artifacts: `contracts/artifacts/FlashLoanReceiver.abi.json` (+ bytecode)
Runtime bytecode: **4987 bytes** · `solc 0.8.24` · `via_ir` · 200 runs.

Verified selectors (match the Python encoders byte-for-byte):

| Function | Selector |
|---|---|
| `execute(address[],uint256[],bytes)` (Balancer head) | `64ba4bc1` |
| `executeAave(address,uint256,bytes)` (Aave head) | `4343d8b2` |
| `receiveFlashLoan(...)` (Balancer callback) | `f04f2707` |
| `executeOperation(...)` (Aave callback) | `1b11d0ff` |

---

## Venue addresses (baked as chain-aware defaults in `Deploy.s.sol`)

| Venue | Base Sepolia (84532) | Base Mainnet (8453) |
|---|---|---|
| Balancer V2 Vault | `0xBA12…2C8` *(not confirmed deployed on Sepolia)* | `0xBA12…2C8` |
| Aave V3 Pool | `0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27` | `0xA238Dd80C259a72e81d7e4664a9801593F98d1c5` |
| Uniswap V3 SwapRouter02 | `0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4` | `0x2626664c2603336E57B271c5C0b26F421741e481` |

> **First testnet flash loan → use the Aave V3 head (`executeAave`).**
> Balancer V2 is not confirmed on Base Sepolia; Aave V3 Pool is live.
> On Base mainnet, Balancer V2 (0 bps) becomes the preferred head.

---

## Operator action (single command — THIS IS THE GATE)

```bash
cd contracts
cp .env.example .env          # Sepolia venue addresses already pre-filled
# set DEPLOYER_PRIVATE_KEY=0x...   <-- the only secret required

source .env
forge script script/Deploy.s.sol:Deploy \
    --rpc-url base_sepolia --broadcast --verify -vvvv
```

The script auto-detects `block.chainid` and picks the Sepolia venue set.
On success it prints:

```
Executor deployed at: 0x....
Update backend/.env with:
  ARBICORE_EXECUTOR_ADDRESS_BASE=0x....
```

## Wire back into the backend

```bash
# backend/.env
ARBICORE_EXECUTOR_ADDRESS_BASE=0x....   # deployed address
ARBICORE_RPC_URL=https://sepolia.base.org
```
Restart backend, then confirm identity:

```bash
curl $BACKEND/api/arbicore/executor/verify
# expect: address_configured READY, contract_deployed READY,
#         vault_matches / router_matches READY, owner_matches READY
```

## Mainnet promotion (after Sepolia validation)

Same command, `--rpc-url base` + `--etherscan-api-key $BASESCAN_API_KEY`.
The **exact same build** is promoted — no code changes.

---

## Estimated cost (from Base Sepolia simulation)

~1,472,932 gas @ 0.011 gwei ≈ **0.0000162 ETH** for deployment.
