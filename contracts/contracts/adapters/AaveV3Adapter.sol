// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IAaveV3Pool} from "../interfaces/IAaveV3Pool.sol";
import {TransferHelper} from "../libraries/TransferHelper.sol";
import {Errors} from "../libraries/Errors.sol";

/// @title Aave V3 flash-loan adapter (repay-side helper).
/// @notice Library-only. Called from within the receiver's
///         `executeOperation` callback to approve the Pool for the
///         repayment amount (`amount + premium`). Aave V3 pulls the
///         repayment via `transferFrom` after the callback returns, so
///         the receiver only needs to approve — not push — the funds.
library AaveV3Adapter {
    /// @notice Approve the Aave V3 Pool to pull `owed` of `asset`.
    /// @dev Reverts with `ApproveFailed(asset)` if the underlying
    ///      approve reverts (e.g. non-standard ERC-20).
    function approveRepay(IAaveV3Pool pool, address asset, uint256 owed) internal {
        TransferHelper.safeApprove(asset, address(pool), owed);
    }

    /// @notice Compute the total the receiver must repay for a single
    ///         `flashLoanSimple` leg.
    function owedSimple(uint256 amount, uint256 premium) internal pure returns (uint256) {
        return amount + premium;
    }

    /// @notice Compute the total the receiver must repay for one leg of
    ///         a multi-asset `flashLoan`. Used by future multi-asset
    ///         flash paths — the current executor uses `flashLoanSimple`
    ///         only.
    function owedMulti(uint256 amount, uint256 premium) internal pure returns (uint256) {
        return amount + premium;
    }
}
