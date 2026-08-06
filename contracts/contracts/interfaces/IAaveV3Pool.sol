// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Aave V3 Pool surface (flash-loan subset).
/// @notice Aave V3 exposes two flash-loan entry points:
///           * `flashLoanSimple` — 5 bps premium, single asset.
///           * `flashLoan`       — 5 bps premium, multi-asset,
///                                 supports opening debt positions
///                                 (`interestRateModes[]`).
///         The executor uses `flashLoanSimple` by default; `flashLoan`
///         is exposed for future multi-asset arbitrage patterns.
interface IAaveV3Pool {
    function flashLoanSimple(
        address receiverAddress,
        address asset,
        uint256 amount,
        bytes calldata params,
        uint16 referralCode
    ) external;

    function flashLoan(
        address receiverAddress,
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata interestRateModes,
        address onBehalfOf,
        bytes calldata params,
        uint16 referralCode
    ) external;

    /// @dev The `POOL()` accessor is convention across Aave V3
    ///      IFlashLoanReceiver implementations; not used by this
    ///      executor but exposed for tooling.
    function getFlashLoanPremiumTotal() external view returns (uint128);
}

/// @title Aave V3 IFlashLoanSimpleReceiver callback surface.
/// @notice The Pool invokes `executeOperation` on the receiver mid-flash;
///         the receiver must approve `amount + premium` back to the Pool
///         before returning `true`.
interface IFlashLoanSimpleReceiver {
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external returns (bool);
}

/// @title Aave V3 IFlashLoanReceiver callback surface (multi-asset).
interface IFlashLoanReceiver {
    function executeOperation(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        address initiator,
        bytes calldata params
    ) external returns (bool);
}
