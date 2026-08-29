# ArbiCore X — Base Executor Provisioning Readiness Report

Status date: 2026-06 · Analysis SHA baseline: `f1e5fc82a014386e983261f2460adb9b59754104`
Scope: **read-only analysis + non-broadcast provisioning**. No transaction was
broadcast. No executor safety logic, gate, profit floor, signer, broadcast path,
SHADOW mode, or production compose was modified.

## 1. Exact contract / deployment status
- Executor contract: `contracts/core/FlashLoanReceiver.sol` (`FlashLoanReceiver`,
  Solidity 0.8.24, Foundry). Single-owner, two-provider flash-loan receiver
  (Balancer V2 `execute(...)` / Aave V3 `executeAave(...)`), owner-gated, re-entry
  gated, callback caller-checked. No upgradability, no delegatecall adapters.
- Deployment infra present: `contracts/script/Deploy.s.sol` (chain-aware),
  `contracts/script/Verify.s.sol`, `contracts/foundry.toml` (basescan etherscan
  config), docs under `contracts/docs/`.

## 2. Does an executor already exist?
- **Base Sepolia (chainid 84532): YES — already deployed and successful.**
  - Address: `0x99c0b64e8F24fc1aADb07dAbA938d9f11dCD1052`
  - Deploy tx: `0x7ef61de3b016d38eca27aac4c6498297d5843f3520ac2269428bc17ff933bc6a`
    (block 45169467, receipt status `0x1`)
  - Constructor args: Balancer Vault `0xBA1222…BF2C8`, Aave V3 Pool
    `0x8bAB6d…9aE27`, Uniswap V3 Router `0x94cC0A…12bc4`
  - Source: `contracts/broadcast/Deploy.s.sol/84532/run-latest.json`
  - This address can be **safely reused/verified** on Base Sepolia (read-only
    on-chain inspection via `inspect_executor` / `GET /api/arbicore/executor/verify`).
- **Base mainnet (chainid 8453): NO** — no broadcast artifact exists; not deployed.

## 3. Base chain / network configuration
| Chain | id | Balancer V2 Vault | Aave V3 Pool | UniV3 SwapRouter02 |
|---|---|---|---|---|
| Base mainnet | 8453 | 0xBA12222222228d8Ba445958a75a0704d566BF2C8 | 0xA238Dd80C259a72e81d7e4664a9801593F98d1c5 | 0x2626664c2603336E57B271c5C0b26F421741e481 |
| Base Sepolia | 84532 | 0xBA1222…BF2C8 (unconfirmed on testnet) | 0x8bAB6d…9aE27 | 0x94cC0A…12bc4 |

## 4. Required deployment parameters (mainnet, when approved)
- Constructor: `(balancerVault, aavePool, uniRouter)` = the mainnet row above
  (auto-selected by `Deploy.s.sol` from `block.chainid`; overridable via
  `BASE_BALANCER_V2_VAULT` / `BASE_AAVE_V3_POOL` / `BASE_UNIV3_ROUTER`).
- `owner` = deployer EOA (set immutably at construction; no transfer path).

## 5. Required signer / vault authorization
- The executor is **owner-gated**: only `owner` (the deployer EOA) may call
  `execute` / `executeAave` / `rescue`. So the ArbiCore vault signer used for
  Limited-Live MUST be the SAME address that deployed the executor (or the
  executor must be redeployed with that owner).
- `AtomicExecutorSimulator.simulate_atomic` additionally gates on
  `signer_present=True`; in the read-only audit no signer is injected, so the
  atomic-sim control stays DENY until a signer public address is provisioned.
- `profitRecipient` in `userData` is typically the operator EOA.

## 6. Exact environment variables required
| Variable | Kind | Purpose |
|---|---|---|
| `ARBICORE_EXECUTOR_ADDRESS_BASE` | public | deployed executor address the runtime/audit reads (env is the ONLY source; not set by this repo) |
| `ARBICORE_RPC_URL_BASE` / `ARBICORE_RPC_URL` | secret-ish (may carry key) | Base RPC for read-only eth_call/eth_getCode/eth_blockNumber |
| `ARBICORE_EXECUTOR_BYTECODE` | public (optional) | optional state-override code for the atomic sim |
| `ARBICORE_EXECUTOR_ENTRYPOINT_SIG` | public (optional) | override; real dispatcher uses `execute(address[],uint256[],bytes)` / `executeAave(address,uint256,bytes)` |
| `ARBICORE_PRICE_MAX_BLOCK_LAG` | public (optional) | freshness block-lag policy (default 5) |
| Deploy-only (NOT runtime, never committed): `DEPLOYER_PRIVATE_KEY`, `BASE_RPC_URL`, `BASE_SEPOLIA_RPC_URL`, `BASESCAN_API_KEY` |

## 7. Exact verification steps (no broadcast)
1. Read-only on-chain identity check of an existing address:
   `GET /api/arbicore/executor/verify` (uses `inspect_executor`: `eth_getCode` +
   `owner()/ROUTER()/VAULT()` getters — never signs/broadcasts).
2. Source verification on BaseScan (already-deployed address):
   `forge verify-contract 0x99c0b64e… contracts/core/FlashLoanReceiver.sol:FlashLoanReceiver \
     --chain base_sepolia --etherscan-api-key $BASESCAN_API_KEY \
     --constructor-args $(cast abi-encode "constructor(address,address,address)" \
       0xBA1222…BF2C8 0x8bAB6d…9aE27 0x94cC0A…12bc4) --watch`
3. Non-broadcast deploy dry-run (simulation only — OMIT `--broadcast`):
   `forge script script/Deploy.s.sol:Deploy --rpc-url base_sepolia -vvvv`

## 8. Risks / blockers
- `forge` is NOT installed in the Emergent preview container → `forge build`,
  `forge test`, and the dry-run must be executed where forge is present (VPS /
  CI). Verified deterministically here instead: the committed broadcast artifact
  parses, and the new registry is consistency-checked against it (7 tests).
- No mainnet executor exists → any mainnet atomic-sim / executor-capability
  control remains DENY until a mainnet deploy is approved & broadcast.
- Owner/signer coupling: the Limited-Live vault signer must equal the executor
  owner, or the executor must be redeployed. (Blocker for eventual eligibility,
  not for this phase.)
- `ARBICORE_EXECUTOR_ENTRYPOINT_SIG` scaffold default (`executeArbitrage(...)`)
  does not match the real dispatcher; `inspect_executor` reads real selectors, so
  this is a documentation/wiring nuance, not a safety issue. NOT changed here.

## 9. Smallest safe next action
Run the **non-broadcast Base Sepolia dry-run** and the **read-only verify** of the
already-deployed Sepolia address on a host with `forge`/`cast` + a Base Sepolia
RPC (no `--broadcast`, no private key needed for verify/inspection). Then, only
with explicit approval, proceed to a mainnet deployment transaction.

**No on-chain deployment transaction will be attempted without explicit approval.**

## 10. End-to-end readiness matrix (in every audit report)
The canonical audit now emits `report["limited_live_readiness_matrix"]` classifying
every prerequisite as READY / BLOCKED / UNKNOWN / MARKET-DEPENDENT, plus
`report["operator_state"]`, `report["signer_state"]`, `report["executor_address_resolved"]`.
Categories: `software` (repo-provisionable), `onchain_operator` (deploy/verify
executor + provision signer — irreversible), `operator` (mode ladder / kill
switch), `market` (a naturally-discovered CONFIRMED + profitable candidate).

Signer authorization (no keys ever): set the PUBLIC address
`ARBICORE_EXECUTOR_SIGNER_ADDRESS` equal to the executor owner EOA. The private
key lives ONLY in the operator vault out-of-band — never in repo / env / logs.
Executor address resolution: env `ARBICORE_EXECUTOR_ADDRESS_BASE` first, else the
read-only registry for `ARBICORE_CHAIN_ID` (default 8453). `atomic_simulation`
stays BLOCKED until the signer is authorized, then becomes per-candidate MARKET.
