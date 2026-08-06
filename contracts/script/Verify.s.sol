// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";

/// @title Verify — re-verify an already-deployed executor.
/// @notice Prefer `forge script Deploy.s.sol --verify` at deploy time.
///         This helper is for the case where `--verify` failed
///         (rate-limited, wrong key) and needs re-running against an
///         already-broadcast address.
///
///         Usage:
///           $ forge verify-contract \
///                <deployed-address> \
///                contracts/core/FlashLoanReceiver.sol:FlashLoanReceiver \
///                --chain base \
///                --etherscan-api-key $BASESCAN_API_KEY \
///                --constructor-args $(cast abi-encode \
///                     "constructor(address,address,address)" \
///                     0xBA12222222228d8Ba445958a75a0704d566BF2C8 \
///                     0xA238Dd80C259a72e81d7e4664a9801593F98d1c5 \
///                     0x2626664c2603336E57B271c5C0b26F421741e481) \
///                --watch
///
///         Base Sepolia: swap `--chain base` for `--chain base_sepolia`
///         (or use the numeric chain id `84532`), and pass the testnet
///         venue addresses via `cast abi-encode`.
contract PrintVerifyCmd is Script {
    function run() external view {
        console2.log("See NatSpec comment for the exact forge verify-contract command.");
        console2.log("Alternatively, redeploy with `--verify` set on `Deploy.s.sol`.");
    }
}
