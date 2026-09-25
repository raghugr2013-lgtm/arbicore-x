// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "../interfaces/IERC20.sol";
import {Venue, SwapHopV2} from "../interfaces/IExecutorV2.sol";
import {
    IUniswapV3Router02,
    IUniswapV2Router,
    IAerodromeRouter,
    ISlipstreamRouter,
    IAlgebraRouter
} from "../interfaces/IV2Routers.sol";
import {TransferHelper} from "../libraries/TransferHelper.sol";
import {ErrorsV2} from "../libraries/ErrorsV2.sol";

/// @title MultiVenueSwapAdapter — typed per-hop swap dispatch (library-only).
/// @notice Executes exactly ONE swap for a single typed hop. The CALLER (the
///         executor) is responsible for the security checks (router allowlist,
///         factory allowlist, per-hop deadline) BEFORE invoking ``runHop`` —
///         this library performs no trust decisions, only the typed external
///         call for the given venue family. Approvals are set to the exact
///         input amount and reset to 0 immediately after the swap so no
///         standing router allowance is ever left behind.
library MultiVenueSwapAdapter {
    /// @param h     the typed hop (venue + router + tokens + limits + deadline)
    /// @param index hop position, surfaced in SwapReverted for trace pinpointing
    function runHop(SwapHopV2 memory h, uint256 index) internal {
        // amountIn == 0 => forward the full current tokenIn balance (chaining).
        uint256 amt = h.amountIn == 0
            ? IERC20(h.tokenIn).balanceOf(address(this))
            : h.amountIn;

        // Exact-amount approval to the (already-allowlisted) router.
        TransferHelper.safeApprove(h.tokenIn, h.router, amt);

        if (h.venue == Venue.UNISWAP_V3) {
            IUniswapV3Router02.ExactInputSingleParams memory p = IUniswapV3Router02.ExactInputSingleParams({
                tokenIn: h.tokenIn,
                tokenOut: h.tokenOut,
                fee: h.feeOrTickSpacing,
                recipient: address(this),
                amountIn: amt,
                amountOutMinimum: h.amountOutMinimum,
                sqrtPriceLimitX96: h.sqrtPriceLimitX96
            });
            try IUniswapV3Router02(h.router).exactInputSingle(p) returns (uint256) {}
            catch (bytes memory reason) { revert ErrorsV2.SwapReverted(index, reason); }
        } else if (h.venue == Venue.UNISWAP_V2) {
            address[] memory path = new address[](2);
            path[0] = h.tokenIn;
            path[1] = h.tokenOut;
            try IUniswapV2Router(h.router).swapExactTokensForTokens(
                amt, h.amountOutMinimum, path, address(this), h.deadline
            ) returns (uint256[] memory) {}
            catch (bytes memory reason) { revert ErrorsV2.SwapReverted(index, reason); }
        } else if (h.venue == Venue.AERODROME_CLASSIC) {
            IAerodromeRouter.Route[] memory routes = new IAerodromeRouter.Route[](1);
            routes[0] = IAerodromeRouter.Route({
                from: h.tokenIn, to: h.tokenOut, stable: h.stable, factory: h.factory
            });
            try IAerodromeRouter(h.router).swapExactTokensForTokens(
                amt, h.amountOutMinimum, routes, address(this), h.deadline
            ) returns (uint256[] memory) {}
            catch (bytes memory reason) { revert ErrorsV2.SwapReverted(index, reason); }
        } else if (h.venue == Venue.AERODROME_SLIPSTREAM) {
            ISlipstreamRouter.ExactInputSingleParams memory p = ISlipstreamRouter.ExactInputSingleParams({
                tokenIn: h.tokenIn,
                tokenOut: h.tokenOut,
                tickSpacing: int24(uint24(h.feeOrTickSpacing)),
                recipient: address(this),
                deadline: h.deadline,
                amountIn: amt,
                amountOutMinimum: h.amountOutMinimum,
                sqrtPriceLimitX96: h.sqrtPriceLimitX96
            });
            try ISlipstreamRouter(h.router).exactInputSingle(p) returns (uint256) {}
            catch (bytes memory reason) { revert ErrorsV2.SwapReverted(index, reason); }
        } else if (h.venue == Venue.ALGEBRA_V3) {
            IAlgebraRouter.ExactInputSingleParams memory p = IAlgebraRouter.ExactInputSingleParams({
                tokenIn: h.tokenIn,
                tokenOut: h.tokenOut,
                recipient: address(this),
                deadline: h.deadline,
                amountIn: amt,
                amountOutMinimum: h.amountOutMinimum,
                limitSqrtPrice: h.sqrtPriceLimitX96
            });
            try IAlgebraRouter(h.router).exactInputSingle(p) returns (uint256) {}
            catch (bytes memory reason) { revert ErrorsV2.SwapReverted(index, reason); }
        } else {
            revert ErrorsV2.VenueNotSupported(uint8(h.venue));
        }

        // Never leave a standing router allowance.
        TransferHelper.safeApprove(h.tokenIn, h.router, 0);
    }
}
