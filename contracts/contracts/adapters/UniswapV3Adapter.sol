// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "../interfaces/IERC20.sol";
import {ISwapRouter02} from "../interfaces/IUniswapV3SwapRouter.sol";
import {TransferHelper} from "../libraries/TransferHelper.sol";
import {Errors} from "../libraries/Errors.sol";

/// @title Uniswap V3 hop-runner adapter.
/// @notice Executes a sequence of `exactInputSingle` swaps against
///         `SwapRouter02`. Deliberately library-only (no storage) so the
///         executor can inline it and keep the callback path cheap.
library UniswapV3Adapter {
    /// @dev Kept in sync with the ABI decoded by
    ///      `abi.decode(userData, (SwapHop[], address))` inside the
    ///      core executor.
    struct SwapHop {
        address tokenIn;
        address tokenOut;
        uint24  feePpm;      // e.g. 500 = 0.05 %, 3000 = 0.30 %
        uint256 amountIn;    // 0 => forward previous hop's full output
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }

    /// @notice Run every hop, forwarding balances through in order.
    /// @dev Reverts with `SwapReverted(i)` if any leg fails so the
    ///      caller can pinpoint the failing hop in the tx trace.
    function runHops(ISwapRouter02 router, SwapHop[] memory hops) internal {
        if (hops.length == 0) revert Errors.EmptyHops();
        for (uint256 i = 0; i < hops.length; i++) {
            SwapHop memory h = hops[i];
            uint256 amt = h.amountIn;
            if (amt == 0) {
                amt = IERC20(h.tokenIn).balanceOf(address(this));
            }
            TransferHelper.safeApprove(h.tokenIn, address(router), amt);
            ISwapRouter02.ExactInputSingleParams memory p = ISwapRouter02.ExactInputSingleParams({
                tokenIn:            h.tokenIn,
                tokenOut:           h.tokenOut,
                fee:                h.feePpm,
                recipient:          address(this),
                amountIn:           amt,
                amountOutMinimum:   h.amountOutMinimum,
                sqrtPriceLimitX96:  h.sqrtPriceLimitX96
            });
            try router.exactInputSingle(p) returns (uint256) {
                // ok
            } catch {
                revert Errors.SwapReverted(i);
            }
        }
    }
}
