// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title ArbiCore X Executor — external interface.
/// @notice The canonical entry points the ArbiCore X backend broadcasts
///         to. Selectors are stable across executor upgrades.
interface IExecutor {
    /// @notice Balancer V2 flash-loan entry point. Selector `0x64ba4bc1`
    ///         (= keccak256("execute(address[],uint256[],bytes)")[:4]).
    /// @param  tokens    Assets to borrow via `IBalancerV2Vault.flashLoan`.
    /// @param  amounts   1:1 with `tokens`.
    /// @param  userData  ABI-encoded `(SwapHop[], address profitRecipient)`;
    ///                   forwarded by the Vault into `receiveFlashLoan`
    ///                   on this contract, where it is decoded and
    ///                   converted into `SwapRouter02.exactInputSingle`
    ///                   calls.
    function execute(
        address[] calldata tokens,
        uint256[] calldata amounts,
        bytes calldata userData
    ) external;

    /// @notice Aave V3 single-asset flash-loan entry point. Selector
    ///         `0x` computed at compile time from
    ///         `executeAave(address,uint256,bytes)`.
    /// @param  asset      Single asset to borrow via
    ///                    `IAaveV3Pool.flashLoanSimple`.
    /// @param  amount     Notional to borrow.
    /// @param  userData   ABI-encoded `(SwapHop[], address profitRecipient)`
    ///                    forwarded verbatim to the Aave callback.
    function executeAave(
        address asset,
        uint256 amount,
        bytes calldata userData
    ) external;

    /// @notice Emitted after a Balancer flash successfully repays the
    ///         Vault. `residualPaid` is the residual balance forwarded
    ///         to the profit recipient for the primary borrowed asset.
    event ExecutionCompleted(
        bytes32 indexed provider,
        address indexed profitRecipient,
        address indexed primaryAsset,
        uint256 borrowed,
        uint256 premium,
        uint256 residualPaid
    );

    /// @notice Emitted when the owner rescues an idle balance from the
    ///         executor. Used post-mortem after a reverted flash.
    event Rescued(address indexed token, address indexed to, uint256 amount);
}
