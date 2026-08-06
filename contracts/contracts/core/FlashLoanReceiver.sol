// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "../interfaces/IERC20.sol";
import {IBalancerV2Vault, IFlashLoanRecipient} from "../interfaces/IBalancerV2Vault.sol";
import {IAaveV3Pool, IFlashLoanSimpleReceiver} from "../interfaces/IAaveV3Pool.sol";
import {ISwapRouter02} from "../interfaces/IUniswapV3SwapRouter.sol";
import {IExecutor} from "../interfaces/IExecutor.sol";
import {UniswapV3Adapter} from "../adapters/UniswapV3Adapter.sol";
import {AaveV3Adapter} from "../adapters/AaveV3Adapter.sol";
import {TransferHelper} from "../libraries/TransferHelper.sol";
import {Errors} from "../libraries/Errors.sol";

/// @title FlashLoanReceiver — canonical ArbiCore X Executor.
/// @author ArbiCore X
/// @notice Single-owner, two-provider flash-loan receiver. Owns *no*
///         standing balances between transactions; all borrowed capital
///         is repaid before the top-level flash call returns.
///
///         Two flash providers are wired:
///           1. **Balancer V2 Vault**  — entry via `execute(...)`,
///              callback `receiveFlashLoan(...)`, 0 bps premium.
///           2. **Aave V3 Pool**       — entry via `executeAave(...)`,
///              callback `executeOperation(...)`, 5 bps premium.
///
///         Both entry points share the same `userData` schema:
///             abi.encode(SwapHop[] hops, address profitRecipient)
///         where each hop is a Uniswap V3 `SwapRouter02.exactInputSingle`
///         leg. Residual balance is forwarded to `profitRecipient`
///         before repayment.
///
///         Security posture:
///           * `owner`-gated entry points (constructor-set, immutable).
///           * `_authorized` re-entry gate ensures callbacks can only
///             fire *inside* an owner-initiated flash. Direct calls to
///             `receiveFlashLoan` / `executeOperation` from outside a
///             flash window revert with `NotAuthorized()`.
///           * Callback caller is checked against the exact Vault / Pool
///             address wired at construction (`CallerNotVault()` /
///             `CallerNotPool()`).
///           * `_pendingFlashProvider` prevents a Balancer callback from
///             satisfying an Aave flash and vice versa.
///           * `rescue(...)` is owner-only and only useful post-mortem
///             when a swap left dust on the executor.
///
///         Deliberate non-features (out of scope for the v1 executor):
///           * No delegate-callable adapters — the swap set is fixed to
///             Uniswap V3 SwapRouter02.
///           * No governance / timelock — owner is an EOA the operator
///             fully controls.
///           * No upgradability — redeploy for schema changes.
contract FlashLoanReceiver is IExecutor, IFlashLoanRecipient, IFlashLoanSimpleReceiver {
    // ---------------------------------------------------------------
    // Immutable configuration
    // ---------------------------------------------------------------

    /// @notice Owner is the deployer; set at construction, no transfer path.
    address public immutable owner;
    IBalancerV2Vault public immutable balancerVault;
    IAaveV3Pool public immutable aavePool;
    ISwapRouter02 public immutable uniRouter;

    // ---------------------------------------------------------------
    // Re-entry / provider gate
    // ---------------------------------------------------------------

    /// @dev `_authorized` == true iff we are currently inside an
    ///      owner-initiated flash window. `_pendingProvider` records
    ///      which provider we are expecting a callback from:
    ///          0 = none, 1 = balancer_v2, 2 = aave_v3.
    bool private _authorized;
    uint8 private _pendingProvider;

    bytes32 private constant _PROVIDER_BALANCER = keccak256("balancer_v2");
    bytes32 private constant _PROVIDER_AAVE     = keccak256("aave_v3");

    // ---------------------------------------------------------------
    // Construction
    // ---------------------------------------------------------------

    constructor(
        address _balancerVault,
        address _aavePool,
        address _uniRouter
    ) {
        if (_balancerVault == address(0) || _aavePool == address(0) || _uniRouter == address(0)) {
            revert Errors.ZeroAddress();
        }
        owner         = msg.sender;
        balancerVault = IBalancerV2Vault(_balancerVault);
        aavePool      = IAaveV3Pool(_aavePool);
        uniRouter     = ISwapRouter02(_uniRouter);
    }

    // ---------------------------------------------------------------
    // Modifiers
    // ---------------------------------------------------------------

    modifier onlyOwner() {
        if (msg.sender != owner) revert Errors.NotOwner();
        _;
    }

    // ---------------------------------------------------------------
    // Balancer V2 flash — entry
    // ---------------------------------------------------------------

    /// @inheritdoc IExecutor
    function execute(
        address[] calldata tokens,
        uint256[] calldata amounts,
        bytes calldata userData
    ) external onlyOwner {
        // Open the re-entry window for the Balancer callback.
        _authorized = true;
        _pendingProvider = 1;

        // Down-cast the address[] into the Balancer-shaped IERC20[].
        // Solidity requires this via an inline assembly reinterpret
        // because IERC20 is an interface type; the two arrays are
        // ABI-identical at the wire level.
        IERC20[] memory ercTokens = new IERC20[](tokens.length);
        for (uint256 i = 0; i < tokens.length; i++) {
            ercTokens[i] = IERC20(tokens[i]);
        }

        balancerVault.flashLoan(address(this), ercTokens, amounts, userData);

        // Close the window (also closed via `_close()` if the callback
        // ran; this second close is a defence-in-depth guard).
        _authorized = false;
        _pendingProvider = 0;
    }

    /// @notice Balancer V2 flash-loan callback. See `IFlashLoanRecipient`.
    function receiveFlashLoan(
        IERC20[] calldata tokens,
        uint256[] calldata amounts,
        uint256[] calldata feeAmounts,
        bytes calldata userData
    ) external override {
        if (!_authorized || _pendingProvider != 1) revert Errors.NotAuthorized();
        if (msg.sender != address(balancerVault)) revert Errors.CallerNotVault();

        (UniswapV3Adapter.SwapHop[] memory hops, address profitRecipient)
            = abi.decode(userData, (UniswapV3Adapter.SwapHop[], address));

        // Route the hops through Uniswap V3.
        UniswapV3Adapter.runHops(uniRouter, hops);

        // Repay Balancer: push exactly `amounts[i] + feeAmounts[i]` back
        // to the Vault. Any residual balance is forwarded to the profit
        // recipient (typically the operator EOA).
        uint256 residualPaid = 0;
        address primaryAsset = address(0);
        uint256 borrowed     = 0;
        uint256 premium      = 0;
        for (uint256 i = 0; i < tokens.length; i++) {
            address t = address(tokens[i]);
            uint256 owed = amounts[i] + feeAmounts[i];
            uint256 bal = IERC20(t).balanceOf(address(this));
            if (bal < owed) revert Errors.InsufficientBalance(t, owed, bal);
            TransferHelper.safeTransfer(t, address(balancerVault), owed);
            uint256 leftover = bal - owed;
            if (leftover > 0 && profitRecipient != address(0)) {
                TransferHelper.safeTransfer(t, profitRecipient, leftover);
            }
            if (i == 0) {
                primaryAsset = t;
                borrowed     = amounts[i];
                premium      = feeAmounts[i];
                residualPaid = leftover;
            }
        }

        emit ExecutionCompleted(
            _PROVIDER_BALANCER, profitRecipient, primaryAsset, borrowed, premium, residualPaid
        );
    }

    // ---------------------------------------------------------------
    // Aave V3 flash — entry
    // ---------------------------------------------------------------

    /// @inheritdoc IExecutor
    function executeAave(
        address asset,
        uint256 amount,
        bytes calldata userData
    ) external onlyOwner {
        _authorized = true;
        _pendingProvider = 2;
        aavePool.flashLoanSimple(address(this), asset, amount, userData, 0);
        _authorized = false;
        _pendingProvider = 0;
    }

    /// @notice Aave V3 flash-loan callback. See `IFlashLoanSimpleReceiver`.
    /// @dev Aave *pulls* the repayment via `transferFrom` after the
    ///      callback returns, so the receiver approves rather than
    ///      transfers.
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external override returns (bool) {
        if (!_authorized || _pendingProvider != 2) revert Errors.NotAuthorized();
        if (msg.sender != address(aavePool))       revert Errors.CallerNotPool();
        if (initiator != address(this))            revert Errors.NotAuthorized();

        (UniswapV3Adapter.SwapHop[] memory hops, address profitRecipient)
            = abi.decode(params, (UniswapV3Adapter.SwapHop[], address));

        UniswapV3Adapter.runHops(uniRouter, hops);

        uint256 owed = AaveV3Adapter.owedSimple(amount, premium);
        uint256 bal  = IERC20(asset).balanceOf(address(this));
        if (bal < owed) revert Errors.InsufficientBalance(asset, owed, bal);
        AaveV3Adapter.approveRepay(aavePool, asset, owed);
        uint256 leftover = bal - owed;
        if (leftover > 0 && profitRecipient != address(0)) {
            TransferHelper.safeTransfer(asset, profitRecipient, leftover);
        }

        emit ExecutionCompleted(
            _PROVIDER_AAVE, profitRecipient, asset, amount, premium, leftover
        );
        return true;
    }

    // ---------------------------------------------------------------
    // Rescue (owner-only, post-mortem)
    // ---------------------------------------------------------------

    /// @notice Move an idle balance off the executor. Never called in
    ///         the hot path; exists purely so dust left after a
    ///         partial-revert flash can be recovered.
    function rescue(address token, address to, uint256 amount) external onlyOwner {
        TransferHelper.safeTransfer(token, to, amount);
        emit Rescued(token, to, amount);
    }

    // ---------------------------------------------------------------
    // View helpers
    // ---------------------------------------------------------------

    /// @notice Snapshot of the internal re-entry gate (test hook).
    function inFlashWindow() external view returns (bool authorized, uint8 provider) {
        return (_authorized, _pendingProvider);
    }
}
