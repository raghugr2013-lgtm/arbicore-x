// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./IERC20.sol";

/// @title Balancer V2 Vault surface (flash-loan subset).
/// @notice Signature: `flashLoan(address,address[],uint256[],bytes)`.
///         The Vault charges **0 bps premium** on every supported chain.
interface IBalancerV2Vault {
    function flashLoan(
        address recipient,
        IERC20[] calldata tokens,
        uint256[] calldata amounts,
        bytes calldata userData
    ) external;
}

/// @title Balancer V2 flash-loan callback surface.
/// @notice The Vault invokes this on `recipient` mid-`flashLoan`.
///         Recipient MUST push `amounts[i] + feeAmounts[i]` of each
///         `tokens[i]` back to the Vault before returning, or the entire
///         call reverts.
interface IFlashLoanRecipient {
    function receiveFlashLoan(
        IERC20[] calldata tokens,
        uint256[] calldata amounts,
        uint256[] calldata feeAmounts,
        bytes calldata userData
    ) external;
}
