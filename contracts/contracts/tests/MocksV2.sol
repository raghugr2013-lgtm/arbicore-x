// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "../interfaces/IERC20.sol";
import {IBalancerV2Vault, IFlashLoanRecipient} from "../interfaces/IBalancerV2Vault.sol";
import {IAaveV3Pool, IFlashLoanSimpleReceiver} from "../interfaces/IAaveV3Pool.sol";
import {IMorphoBlue, IMorphoFlashLoanCallback} from "../interfaces/IExecutorV2.sol";
import {IUniswapV3Router02} from "../interfaces/IV2Routers.sol";

/// @notice V2 test mocks. A single constant-rate router implementing the
///         UniV3 exactInputSingle shape is sufficient to drive the executor's
///         swap path deterministically for the V2 family under test (the other
///         router families are exercised for allowlist/deadline/venue guards,
///         and via fork tests against real routers separately).

contract MockV3Router is IUniswapV3Router02 {
    bool public shouldRevert;
    uint256 public rate = 1e18; // out/in scaled by 1e18

    function setRevert(bool v) external { shouldRevert = v; }
    function setRate(uint256 r) external { rate = r; }

    function exactInputSingle(ExactInputSingleParams calldata p)
        external payable override returns (uint256 amountOut)
    {
        if (shouldRevert) revert("MockV3Router: forced revert");
        IERC20(p.tokenIn).transferFrom(msg.sender, address(this), p.amountIn);
        amountOut = (p.amountIn * rate) / 1e18;
        require(amountOut >= p.amountOutMinimum, "MockV3Router: slippage");
        IERC20(p.tokenOut).transfer(p.recipient, amountOut);
    }
}

contract MockBalancerVaultV2 is IBalancerV2Vault {
    function flashLoan(
        address recipient,
        IERC20[] calldata tokens,
        uint256[] calldata amounts,
        bytes calldata userData
    ) external override {
        uint256 n = tokens.length;
        uint256[] memory fees = new uint256[](n);
        for (uint256 i = 0; i < n; i++) tokens[i].transfer(recipient, amounts[i]);
        uint256[] memory preBal = new uint256[](n);
        for (uint256 i = 0; i < n; i++) preBal[i] = tokens[i].balanceOf(address(this));
        IFlashLoanRecipient(recipient).receiveFlashLoan(tokens, amounts, fees, userData);
        for (uint256 i = 0; i < n; i++) {
            require(tokens[i].balanceOf(address(this)) >= preBal[i] + amounts[i], "Balancer: not repaid");
        }
    }
}

contract MockAaveV3PoolV2 is IAaveV3Pool {
    uint128 public premiumBps = 5;
    function setPremiumBps(uint128 p) external { premiumBps = p; }

    function flashLoanSimple(
        address receiverAddress, address asset, uint256 amount, bytes calldata params, uint16
    ) external override {
        IERC20(asset).transfer(receiverAddress, amount);
        uint256 premium = (amount * premiumBps) / 10_000;
        uint256 preBal = IERC20(asset).balanceOf(address(this));
        require(
            IFlashLoanSimpleReceiver(receiverAddress).executeOperation(
                asset, amount, premium, receiverAddress, params
            ), "Aave: callback false"
        );
        require(
            IERC20(asset).transferFrom(receiverAddress, address(this), amount + premium),
            "Aave: repay pull failed"
        );
        require(IERC20(asset).balanceOf(address(this)) >= preBal + amount + premium, "Aave: short");
    }

    function flashLoan(
        address, address[] calldata, uint256[] calldata, uint256[] calldata, address, bytes calldata, uint16
    ) external pure override { revert("unused"); }

    function getFlashLoanPremiumTotal() external view override returns (uint128) { return premiumBps; }
}

/// @notice Morpho Blue singleton mock — canonical push→callback→PULL sequence
///         (safeTransfer principal, onMorphoFlashLoan, safeTransferFrom back).
contract MockMorphoBlue is IMorphoBlue {
    function flashLoan(address token, uint256 assets, bytes calldata data) external override {
        require(assets != 0, "ZERO_ASSETS");
        IERC20(token).transfer(msg.sender, assets);
        IMorphoFlashLoanCallback(msg.sender).onMorphoFlashLoan(assets, data);
        require(IERC20(token).transferFrom(msg.sender, address(this), assets), "Morpho: repay pull failed");
    }
}
