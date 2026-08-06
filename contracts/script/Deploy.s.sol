// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {FlashLoanReceiver} from "../contracts/core/FlashLoanReceiver.sol";

/// @title Deploy — one-command executor deployment.
/// @notice Usage (Base mainnet):
///   $ source .env
///   $ forge script script/Deploy.s.sol:Deploy \
///        --rpc-url base \
///        --broadcast \
///        --verify \
///        --etherscan-api-key $BASESCAN_API_KEY \
///        -vvvv
///
///  Usage (Base Sepolia — recommended first):
///   $ forge script script/Deploy.s.sol:Deploy \
///        --rpc-url base_sepolia \
///        --broadcast \
///        --verify \
///        -vvvv
///
///  Env inputs (read via `vm.envAddress` / `vm.envUint`):
///    BASE_BALANCER_V2_VAULT       (default 0xBA12... on both chains)
///    BASE_AAVE_V3_POOL            (mainnet default is baked in)
///    BASE_UNIV3_ROUTER            (mainnet default is baked in)
///    DEPLOYER_PRIVATE_KEY         (used by --private-key)
contract Deploy is Script {
    // Canonical mainnet defaults. Overridable via env for testnet.
    address constant DEFAULT_BALANCER_V2_VAULT = 0xBA12222222228d8Ba445958a75a0704d566BF2C8;
    address constant DEFAULT_AAVE_V3_POOL      = 0xA238Dd80C259a72e81d7e4664a9801593F98d1c5;
    address constant DEFAULT_UNIV3_ROUTER      = 0x2626664c2603336E57B271c5C0b26F421741e481;

    function run() external returns (address executor) {
        address balancerVault = _envAddrOr("BASE_BALANCER_V2_VAULT", DEFAULT_BALANCER_V2_VAULT);
        address aavePool      = _envAddrOr("BASE_AAVE_V3_POOL",      DEFAULT_AAVE_V3_POOL);
        address uniRouter     = _envAddrOr("BASE_UNIV3_ROUTER",      DEFAULT_UNIV3_ROUTER);

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
        console2.log("  ARBICORE_EXECUTOR_ADDRESS_BASE=", executor);
    }

    function _envAddrOr(string memory key, address dflt) internal view returns (address) {
        try vm.envAddress(key) returns (address a) {
            return a == address(0) ? dflt : a;
        } catch {
            return dflt;
        }
    }
}
