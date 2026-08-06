# ArbiCore X — Executor Deployment Guide

Canonical deployment procedure for `FlashLoanReceiver` (the on-chain
executor contract) on **Base mainnet** and **Base Sepolia testnet**.

> **Status (2026-08-06):** contract is **built, tested, verified-in-repo**.
> **Not yet broadcast to any network.** Do a Base Sepolia dry-run first;
> Base mainnet only after Paper Validation + Shadow Certification.

---

## 1. Contract summary

| Item                            | Value                                                      |
| ------------------------------- | ---------------------------------------------------------- |
| Contract                        | `FlashLoanReceiver`                                        |
| Source                          | `/app/contracts/contracts/core/FlashLoanReceiver.sol`      |
| Solidity                        | `^0.8.24` (compiled with `via_ir = true`, 200 opt runs)    |
| Owner model                     | Immutable EOA (deployer) — no transfer                     |
| Providers                       | Balancer V2 (0 bps) + Aave V3 (5 bps)                      |
| DEX                             | Uniswap V3 SwapRouter02                                    |
| Entry points                    | `execute(address[],uint256[],bytes)`                       |
|                                 | `executeAave(address,uint256,bytes)`                       |
| Runtime bytecode size           | ~4988 bytes                                                |
| Test coverage                   | 8/8 Foundry unit tests passing (mock-driven, no fork)      |

Selectors (verified against `cast sig` and the Python encoder):

| Signature                                                | Selector      |
| -------------------------------------------------------- | ------------- |
| `execute(address[],uint256[],bytes)`                     | `0x64ba4bc1`  |
| `executeAave(address,uint256,bytes)`                     | `0x4343d8b2`  |
| `receiveFlashLoan(address[],uint256[],uint256[],bytes)`  | `0xf04f2707`  |
| `executeOperation(address,uint256,uint256,address,bytes)`| `0x1b11d0ff`  |

Custom-error selectors (used by `broadcast.py:_REVERT_SELECTORS`):

| Error                                                     | Selector     |
| --------------------------------------------------------- | ------------ |
| `NotOwner()`                                              | `0x30cd7471` |
| `NotAuthorized()`                                         | `0xea8e4eb5` |
| `CallerNotVault()`                                        | `0xedd7338f` |
| `CallerNotPool()`                                         | `0xe9211597` |
| `EmptyHops()`                                             | `0x199bb70b` |
| `SwapReverted(uint256)`                                   | `0x6a6fee17` |
| `ApproveFailed(address)`                                  | `0xc90bb86a` |
| `TransferFailed(address)`                                 | `0x39f1c8d9` |
| `InsufficientBalance(address,uint256,uint256)`            | `0xdb42144d` |
| `ZeroAddress()`                                           | `0xd92e233d` |

---

## 2. Prerequisites

1. **Foundry** installed (`forge` + `cast` + `anvil`).
   ```bash
   curl -L https://foundry.paradigm.xyz | bash
   foundryup
   ```
2. A funded **deployer EOA** on the target chain.
   - Base Sepolia: any faucet-funded key.
   - Base mainnet: ~0.001 ETH covers a real deploy (bytecode is ~5 KB).
3. **RPC URL** for the target chain (Alchemy / Infura / Base's public
   RPC works).
4. **BaseScan API key** (Etherscan V2 multichain key) for source
   verification.

Nothing about the pod environment is required for the deploy — it can
be run from any machine with Foundry.

---

## 3. Environment (`/app/contracts/.env`)

Copy the template and fill in secrets — **NEVER commit `.env`**.
```bash
cd /app/contracts
cp .env.example .env
${EDITOR:-vi} .env
```

Minimum required for a deploy:

- `DEPLOYER_PRIVATE_KEY`     — 0x-prefixed 32-byte hex.
- `BASE_RPC_URL`             — for a Base mainnet deploy.
- `BASE_SEPOLIA_RPC_URL`     — for a Base Sepolia dry-run.
- `BASESCAN_API_KEY`         — for `--verify`.

For testnet, override the venue addresses too (see `.env.example` for
the placeholder slots).

---

## 4. Deployment (single command)

### 4a. Base Sepolia (dry-run — **do this first**)

```bash
cd /app/contracts
source .env
forge script script/Deploy.s.sol:Deploy \
    --rpc-url base_sepolia \
    --private-key $DEPLOYER_PRIVATE_KEY \
    --broadcast \
    --verify \
    -vvvv
```

Expected output tail:
```
=====================================================
Executor deployed at: 0x<address>
=====================================================
Update backend/.env with:
  ARBICORE_EXECUTOR_ADDRESS_BASE= 0x<address>
```

### 4b. Base mainnet (final)

Same command, `--rpc-url base` instead of `base_sepolia`. **Only after
Paper Validation + Shadow Certification pass.**

```bash
forge script script/Deploy.s.sol:Deploy \
    --rpc-url base \
    --private-key $DEPLOYER_PRIVATE_KEY \
    --broadcast \
    --verify \
    -vvvv
```

---

## 5. Post-deploy — wire the address into the backend

Once the deploy address is known, populate the canonical config layer:

```bash
# backend/.env
ARBICORE_EXECUTOR_ADDRESS_BASE=0x<deployed-address>
```

Then restart the backend so `resolve_executor_address` picks it up:
```bash
sudo supervisorctl restart backend
```

Verify wiring:
```bash
curl -s -b "$JAR" "$API_URL/api/arbicore/runtime/config" | jq .executor_addresses.base
```

**Do NOT enable live execution.** The default `mode` remains `SHADOW`
until an operator explicitly promotes it via the operator wizard.

---

## 6. Verification evidence

Every deploy MUST produce, and be reviewed against, the following
artefacts:

1. **Foundry broadcast JSON** — `/app/contracts/broadcast/Deploy.s.sol/<chainId>/run-latest.json`.
   Contains the exact tx hash, block number, and constructor args.
2. **BaseScan verified source page** — the `--verify` flag produces a
   URL like `https://basescan.org/address/0x…#code`. Attach the
   screenshot to the operator handover doc.
3. **On-chain address book snapshot** — the tx receipt's `contractAddress`
   MUST match the value shown by `Deploy.s.sol` and the value written
   into `backend/.env`.
4. **Selector sanity check** — run:
   ```bash
   cast call <address> "owner()(address)" --rpc-url base
   ```
   returns the deployer address. Any deviation aborts the promotion
   to live mode.

See `docs/VERIFICATION.md` for the full checklist.

---

## 7. Rollback / redeploy

The executor is **not upgradeable**. Any bytecode change requires a
fresh deploy. The old executor keeps whatever dust it collected — the
operator can call `rescue(token, to, amount)` from the deployer EOA to
move it out before abandoning the old contract.

---

## 8. Emergency stop

The executor has no external pause switch — but every entry point is
`onlyOwner`. To halt execution:

1. Move the deployer key to a "cold" wallet the auto-executor cannot
   see (rotate the runtime signer via the operator wizard).
2. Set `mode` to `KILLED` in the backend so no new plans are broadcast.
3. Optional: transfer any residual balance out via `rescue`.
