// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {FlashLoanReceiver} from "../contracts/core/FlashLoanReceiver.sol";

/// @title Deploy — one-command executor deployment (chain-aware).
/// @notice Selects the correct venue address set automatically from
///         `block.chainid`, so the operator runs the SAME command for
///         Base Sepolia and Base mainnet — only `--rpc-url` changes.
///
///  Usage (Base Sepolia — recommended first):
///   $ source .env
///   $ forge script script/Deploy.s.sol:Deploy \
///        --rpc-url base_sepolia --broadcast --verify -vvvv
///
///  Usage (Base mainnet — after Sepolia validation):
///   $ forge script script/Deploy.s.sol:Deploy \
///        --rpc-url base --broadcast --verify \
///        --etherscan-api-key $BASESCAN_API_KEY -vvvv
///
///  Optional env overrides (any left unset use the verified defaults below):
///    Base mainnet (chainid 8453):
///      BASE_BALANCER_V2_VAULT / BASE_AAVE_V3_POOL / BASE_UNIV3_ROUTER
///    Base Sepolia (chainid 84532):
///      BASE_SEPOLIA_BALANCER_V2_VAULT / BASE_SEPOLIA_AAVE_V3_POOL /
///      BASE_SEPOLIA_UNIV3_ROUTER
///    DEPLOYER_PRIVATE_KEY — consumed by forge `--private-key` at broadcast.
contract Deploy is Script {
    // --- Base mainnet (chainid 8453) canonical venue addresses -----------
    address constant MAINNET_BALANCER_V2_VAULT = 0xBA12222222228d8Ba445958a75a0704d566BF2C8;
    address constant MAINNET_AAVE_V3_POOL      = 0xA238Dd80C259a72e81d7e4664a9801593F98d1c5;
    address constant MAINNET_UNIV3_ROUTER      = 0x2626664c2603336E57B271c5C0b26F421741e481;

    // --- Base Sepolia (chainid 84532) verified venue addresses -----------
    // Aave V3 Pool + Uniswap V3 SwapRouter02 confirmed against the official
    // Aave (Coinbase CDP demo) + Uniswap Base deployment docs (2026-06).
    // Balancer V2 on Base Sepolia is NOT confirmed deployed — the first
    // testnet flash loan should use the Aave V3 head (executeAave).
    address constant SEPOLIA_BALANCER_V2_VAULT = 0xBA12222222228d8Ba445958a75a0704d566BF2C8;
    address constant SEPOLIA_AAVE_V3_POOL      = 0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27;
    address constant SEPOLIA_UNIV3_ROUTER      = 0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4;

    uint256 constant BASE_MAINNET = 8453;
    uint256 constant BASE_SEPOLIA = 84532;

    function run() external returns (address executor) {
        address balancerVault;
        address aavePool;
        address uniRouter;

        if (block.chainid == BASE_SEPOLIA) {
            balancerVault = _envAddrOr("BASE_SEPOLIA_BALANCER_V2_VAULT", SEPOLIA_BALANCER_V2_VAULT);
            aavePool      = _envAddrOr("BASE_SEPOLIA_AAVE_V3_POOL",      SEPOLIA_AAVE_V3_POOL);
            uniRouter     = _envAddrOr("BASE_SEPOLIA_UNIV3_ROUTER",      SEPOLIA_UNIV3_ROUTER);
            console2.log("Target: Base Sepolia (chainid 84532)");
        } else if (block.chainid == BASE_MAINNET) {
            balancerVault = _envAddrOr("BASE_BALANCER_V2_VAULT", MAINNET_BALANCER_V2_VAULT);
            aavePool      = _envAddrOr("BASE_AAVE_V3_POOL",      MAINNET_AAVE_V3_POOL);
            uniRouter     = _envAddrOr("BASE_UNIV3_ROUTER",      MAINNET_UNIV3_ROUTER);
            console2.log("Target: Base mainnet (chainid 8453)");
        } else {
            // Unknown chain — require explicit env, no silent mainnet default.
            balancerVault = vm.envAddress("BASE_BALANCER_V2_VAULT");
            aavePool      = vm.envAddress("BASE_AAVE_V3_POOL");
            uniRouter     = vm.envAddress("BASE_UNIV3_ROUTER");
            console2.log("Target: custom chain id:", block.chainid);
        }

        console2.log("Deploying FlashLoanReceiver with:");
        console2.log("  balancerVault:", balancerVault);
        console2.log("  aavePool:     ", aavePool);
        console2.log("  uniRouter:    ", uniRouter);

        vm.startBroadcast();
        FlashLoanReceiver r = new FlashLoanReceiver(balancerVault, aavePool, uniRouter);
        vm.stopBroadcast();

        executor = address(r);
        console2.log("=====================================================");
        console2.log("Executor deployed at:", executor);
        console2.log("=====================================================");
        console2.log("Update backend/.env with:");
        if (block.chainid == BASE_SEPOLIA) {
            console2.log("  ARBICORE_EXECUTOR_ADDRESS_BASE=", executor);
            console2.log("  (Base Sepolia RPC; verify with GET /api/arbicore/executor/verify)");
        } else {
            console2.log("  ARBICORE_EXECUTOR_ADDRESS_BASE=", executor);
        }
    }

    function _envAddrOr(string memory key, address dflt) internal view returns (address) {
        try vm.envAddress(key) returns (address a) {
            return a == address(0) ? dflt : a;
        } catch {
            return dflt;
        }
    }
}
