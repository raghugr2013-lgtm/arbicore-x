// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script} from "forge-std/Script.sol";
import {FlashLoanReceiverV2} from "../contracts/core/FlashLoanReceiverV2.sol";

/// @title DeployV2 — chain-aware FlashLoanReceiverV2 deployment script.
/// @notice PREPARED ONLY. Not executed in this engineering package. Selects the
///         correct venue address set + initial router/factory allowlist seeds
///         from ``block.chainid`` per Interface Freeze v1.1 (Base + Ethereum +
///         Base Sepolia staging). Arbitrum/Optimism/Polygon/BNB are out of
///         scope and intentionally have no seed set (deployment would revert).
///
///  Usage (Base Sepolia — staging first; requires operator env + funded key):
///    forge script script/DeployV2.s.sol:DeployV2 --rpc-url base_sepolia --broadcast --verify -vvvv
///
///  V1 (FlashLoanReceiver) and its deployments are unaffected by this script.
contract DeployV2 is Script {
    // Balancer V2 Vault — identical address across supported chains.
    address constant BALANCER_V2_VAULT = 0xBA12222222228d8Ba445958a75a0704d566BF2C8;

    // Aave V3 Pool.
    address constant AAVE_V3_POOL_BASE      = 0xA238Dd80C259a72e81d7e4664a9801593F98d1c5;
    address constant AAVE_V3_POOL_ETH       = 0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2;
    address constant AAVE_V3_POOL_BASE_SEP  = 0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27;

    // Morpho Blue singleton — same canonical address on Ethereum + Base.
    address constant MORPHO_BLUE = 0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb;

    // Routers (initial allowlist seeds).
    address constant UNIV3_ROUTER_BASE       = 0x2626664c2603336E57B271c5C0b26F421741e481;
    address constant UNIV3_ROUTER_ETH        = 0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45;
    address constant UNIV3_ROUTER_BASE_SEP   = 0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4;
    address constant AERODROME_ROUTER_BASE   = 0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43;
    // SushiSwap routers (Ethereum). NOTE: these are UNVERIFIED seed candidates —
    // the operator MUST confirm both against the live Ethereum deployment (and
    // Basescan/Etherscan) before any broadcast. Deployment is not performed in
    // this engineering package.
    address constant SUSHI_V2_ROUTER_ETH     = 0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F;
    address constant SUSHI_V3_ROUTER_ETH     = 0x8A21CF9ba08eb709D0d24ba1a43f87A04D09ac73;

    // Aerodrome classic PoolFactory (Base) — factory allowlist seed.
    address constant AERODROME_FACTORY_BASE  = 0x420DD381b31aEf6683db6B902084cB0FFECe40Da;

    uint256 constant BASE_MAINNET = 8453;
    uint256 constant ETH_MAINNET  = 1;
    uint256 constant BASE_SEPOLIA = 84532;

    function run() external returns (address deployed) {
        uint256 cid = block.chainid;
        address aavePool;
        address[] memory routers;
        address[] memory factories;

        if (cid == BASE_MAINNET) {
            aavePool = AAVE_V3_POOL_BASE;
            routers = new address[](2);
            routers[0] = UNIV3_ROUTER_BASE;
            routers[1] = AERODROME_ROUTER_BASE;
            factories = new address[](1);
            factories[0] = AERODROME_FACTORY_BASE;
        } else if (cid == ETH_MAINNET) {
            aavePool = AAVE_V3_POOL_ETH;
            routers = new address[](3);
            routers[0] = UNIV3_ROUTER_ETH;
            routers[1] = SUSHI_V2_ROUTER_ETH;
            routers[2] = SUSHI_V3_ROUTER_ETH;
            factories = new address[](0);
        } else if (cid == BASE_SEPOLIA) {
            aavePool = AAVE_V3_POOL_BASE_SEP;
            routers = new address[](1);
            routers[0] = UNIV3_ROUTER_BASE_SEP;
            factories = new address[](0);
        } else {
            revert("DeployV2: chain out of scope (Base/Ethereum/BaseSepolia only)");
        }

        vm.startBroadcast();
        FlashLoanReceiverV2 receiver = new FlashLoanReceiverV2(
            BALANCER_V2_VAULT, aavePool, MORPHO_BLUE, routers, factories
        );
        vm.stopBroadcast();
        deployed = address(receiver);
    }
}
