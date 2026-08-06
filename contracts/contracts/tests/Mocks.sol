// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "../interfaces/IERC20.sol";
import {ISwapRouter02} from "../interfaces/IUniswapV3SwapRouter.sol";
import {IBalancerV2Vault, IFlashLoanRecipient} from "../interfaces/IBalancerV2Vault.sol";
import {IAaveV3Pool, IFlashLoanSimpleReceiver} from "../interfaces/IAaveV3Pool.sol";

/// @notice Constant-1:1 exchange rate mock router. Enough to let the
///         executor's swap path complete deterministically.
contract MockSwapRouter02 is ISwapRouter02 {
    /// If non-zero, force `exactInputSingle` to revert.
    bool public shouldRevert;
    /// output/input rate scaled by 1e18. Default = 1e18 (1-to-1).
    uint256 public rate = 1e18;

    function setRevert(bool v) external { shouldRevert = v; }
    function setRate(uint256 r) external { rate = r; }

    function exactInputSingle(ExactInputSingleParams calldata p)
        external
        payable
        override
        returns (uint256 amountOut)
    {
        if (shouldRevert) revert("MockSwapRouter02: forced revert");
        // Pull tokenIn from caller (which must have approved).
        IERC20(p.tokenIn).transferFrom(msg.sender, address(this), p.amountIn);
        amountOut = (p.amountIn * rate) / 1e18;
        require(amountOut >= p.amountOutMinimum, "MockSwapRouter02: slippage");
        IERC20(p.tokenOut).transfer(p.recipient, amountOut);
    }
}

/// @notice Balancer V2 Vault mock. Forwards the caller's `flashLoan`
///         into `receiveFlashLoan` on the recipient with a 0-premium
///         schedule, then checks the recipient has actually pushed the
///         principal back to the Vault.
contract MockBalancerVault is IBalancerV2Vault {
    function flashLoan(
        address recipient,
        IERC20[] calldata tokens,
        uint256[] calldata amounts,
        bytes calldata userData
    ) external override {
        uint256 n = tokens.length;
        uint256[] memory fees = new uint256[](n);
        // Push borrowed principal to the recipient.
        for (uint256 i = 0; i < n; i++) {
            tokens[i].transfer(recipient, amounts[i]);
        }
        // Snapshot pre-callback balance (should be 0 for our test set).
        uint256[] memory preBal = new uint256[](n);
        for (uint256 i = 0; i < n; i++) {
            preBal[i] = tokens[i].balanceOf(address(this));
        }
        // Callback into the recipient.
        IFlashLoanRecipient(recipient).receiveFlashLoan(tokens, amounts, fees, userData);
        // Verify each token was pushed back.
        for (uint256 i = 0; i < n; i++) {
            uint256 postBal = tokens[i].balanceOf(address(this));
            require(postBal >= preBal[i] + amounts[i], "MockBalancerVault: not repaid");
        }
    }
}

/// @notice Aave V3 Pool mock. Charges a configurable premium and pulls
///         the repayment via `transferFrom` after the callback returns
///         (matches real Aave semantics).
contract MockAaveV3Pool is IAaveV3Pool {
    uint128 public premiumBps = 5; // 5 bps default

    function setPremiumBps(uint128 p) external { premiumBps = p; }

    function flashLoanSimple(
        address receiverAddress,
        address asset,
        uint256 amount,
        bytes calldata params,
        uint16
    ) external override {
        IERC20(asset).transfer(receiverAddress, amount);
        uint256 premium = (amount * premiumBps) / 10_000;
        uint256 preBal = IERC20(asset).balanceOf(address(this));
        require(
            IFlashLoanSimpleReceiver(receiverAddress).executeOperation(
                asset, amount, premium, receiverAddress, params
            ),
            "MockAaveV3Pool: callback returned false"
        );
        // Pull repayment via transferFrom.
        require(
            IERC20(asset).transferFrom(receiverAddress, address(this), amount + premium),
            "MockAaveV3Pool: repay pull failed"
        );
        require(
            IERC20(asset).balanceOf(address(this)) >= preBal + amount + premium,
            "MockAaveV3Pool: repay short"
        );
    }

    function flashLoan(
        address, address[] calldata, uint256[] calldata,
        uint256[] calldata, address, bytes calldata, uint16
    ) external pure override {
        revert("MockAaveV3Pool: multi-asset unused by tests");
    }

    function getFlashLoanPremiumTotal() external view override returns (uint128) {
        return premiumBps;
    }
}
