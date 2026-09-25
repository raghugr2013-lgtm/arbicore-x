// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title ErrorsV2 — canonical revert selectors for FlashLoanReceiverV2.
/// @notice Distinct from the V1 ``Errors`` library so the V1 contract and its
///         deployed bytecode remain byte-for-byte unchanged. The ArbiCore X
///         backend (`broadcast.py`) can translate these selectors into
///         human-readable causes. Every unsupported/unauthorized path is
///         fail-closed via one of these typed errors — there is no silent
///         fallback anywhere in V2.
library ErrorsV2 {
    error ZeroAddress();
    error NotOwner();
    error NotAuthorized();
    error CallerNotVault();
    error CallerNotPool();
    error CallerNotMorpho();
    error EmptyHops();
    error ArrayLengthMismatch();
    error RouterNotAllowed(address router);
    error FactoryNotAllowed(address factory);
    error VenueNotSupported(uint8 venue);
    error TransactionExpired(uint256 deadline, uint256 currentTimestamp);
    error InsufficientBalance(address token, uint256 required, uint256 available);
    error ProfitBelowMinimum(uint256 minProfit, uint256 actualProfit);
    error SwapReverted(uint256 hopIndex, bytes reason);
    error MorphoReentrancyGuard();
}
