// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Uniswap V3 SwapRouter02 surface.
/// @notice `SwapRouter02` drops the `deadline` field vs. the original
///         `SwapRouter` — the executor uses this newer variant because
///         it matches the on-chain deployment on Base + Base Sepolia
///         (address `0x2626664c2603336E57B271c5C0b26F421741e481` on Base
///         mainnet). Selector: `exactInputSingle((...)) → uint256`.
interface ISwapRouter02 {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24  fee;             // Uniswap V3 raw ppm (bps × 100)
        address recipient;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }

    function exactInputSingle(ExactInputSingleParams calldata params)
        external
        payable
        returns (uint256 amountOut);
}
