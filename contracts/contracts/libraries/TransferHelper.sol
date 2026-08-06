// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "../interfaces/IERC20.sol";
import {Errors} from "./Errors.sol";

/// @title Safe ERC-20 transfer + approve helpers.
/// @notice Tolerates non-standard tokens that return no data or return
///         false on failure. Uses low-level `call` + return-data
///         inspection rather than pulling in an entire OZ SafeERC20
///         (keeps the executor bytecode compact).
library TransferHelper {
    function safeTransfer(address token, address to, uint256 value) internal {
        if (to == address(0)) revert Errors.ZeroAddress();
        (bool ok, bytes memory data) = token.call(
            abi.encodeWithSelector(IERC20.transfer.selector, to, value)
        );
        if (!ok || (data.length > 0 && !abi.decode(data, (bool)))) {
            revert Errors.TransferFailed(token);
        }
    }

    function safeApprove(address token, address spender, uint256 value) internal {
        // Some tokens (USDT most famously) revert if allowance is set from
        // non-zero to non-zero. Reset to 0 first when necessary.
        uint256 current = IERC20(token).allowance(address(this), spender);
        if (current != 0 && value != 0) {
            (bool ok0, bytes memory d0) = token.call(
                abi.encodeWithSelector(IERC20.approve.selector, spender, 0)
            );
            if (!ok0 || (d0.length > 0 && !abi.decode(d0, (bool)))) {
                revert Errors.ApproveFailed(token);
            }
        }
        (bool ok, bytes memory data) = token.call(
            abi.encodeWithSelector(IERC20.approve.selector, spender, value)
        );
        if (!ok || (data.length > 0 && !abi.decode(data, (bool)))) {
            revert Errors.ApproveFailed(token);
        }
    }

    function balanceOf(address token, address owner) internal view returns (uint256) {
        return IERC20(token).balanceOf(owner);
    }
}
