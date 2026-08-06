// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Canonical revert selectors — one place to keep them stable.
/// @notice The ArbiCore X backend (`broadcast.py`) uses these
///         selectors to translate revert data into human-readable
///         causes. Keep in sync with `_ERROR_SELECTORS` in the
///         backend.
library Errors {
    /// selector 0x30cd7471 — keccak256("NotOwner()")[:4]
    error NotOwner();
    /// selector 0xea8e4eb5 — keccak256("NotAuthorized()")[:4]
    error NotAuthorized();
    /// selector 0xedd7338f — keccak256("CallerNotVault()")[:4]
    error CallerNotVault();
    /// selector 0xe9211597 — keccak256("CallerNotPool()")[:4]
    error CallerNotPool();
    /// selector 0x199bb70b — keccak256("EmptyHops()")[:4]
    error EmptyHops();
    /// selector 0x6a6fee17 — keccak256("SwapReverted(uint256)")[:4]
    error SwapReverted(uint256 hopIndex);
    /// selector 0xc90bb86a — keccak256("ApproveFailed(address)")[:4]
    error ApproveFailed(address token);
    /// selector 0x39f1c8d9 — keccak256("TransferFailed(address)")[:4]
    error TransferFailed(address token);
    /// selector 0xdb42144d — keccak256("InsufficientBalance(address,uint256,uint256)")[:4]
    error InsufficientBalance(address token, uint256 needed, uint256 has);
    /// selector 0xd92e233d — keccak256("ZeroAddress()")[:4]
    error ZeroAddress();
}
