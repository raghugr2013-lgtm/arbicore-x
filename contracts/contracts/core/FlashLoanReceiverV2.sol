// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "../interfaces/IERC20.sol";
import {IBalancerV2Vault, IFlashLoanRecipient} from "../interfaces/IBalancerV2Vault.sol";
import {IAaveV3Pool, IFlashLoanSimpleReceiver} from "../interfaces/IAaveV3Pool.sol";
import {
    IExecutorV2,
    IMorphoBlue,
    IMorphoFlashLoanCallback,
    Venue,
    SwapHopV2
} from "../interfaces/IExecutorV2.sol";
import {MultiVenueSwapAdapter} from "../adapters/MultiVenueSwapAdapter.sol";
import {AaveV3Adapter} from "../adapters/AaveV3Adapter.sol";
import {TransferHelper} from "../libraries/TransferHelper.sol";
import {ErrorsV2} from "../libraries/ErrorsV2.sol";

/// @title FlashLoanReceiverV2 — ArbiCore X multi-provider, multi-venue executor.
/// @author ArbiCore X
/// @notice V2 receiver per Interface Freeze v1.1. NEW contract / NEW address;
///         the V1 ``FlashLoanReceiver`` and its deployments are untouched.
///
///  Flash heads (typed, provider-pinned callbacks):
///    * Balancer V2  — execute(...)       / receiveFlashLoan(...)   0 bps, push repay
///    * Aave V3      — executeAave(...)    / executeOperation(...)   5 bps, pull repay
///    * Morpho Blue  — executeMorpho(...)  / onMorphoFlashLoan(...)  0 bps, pull repay
///
///  Swap settlement: typed per-hop dispatch (MultiVenueSwapAdapter) over an
///  OWNER-ALLOWLISTED router set (+ factory allowlist for Aerodrome classic).
///  There is NO arbitrary target+calldata, NO delegatecall, NO upgradeability.
///
///  userData schema (all three heads):
///    abi.encode(SwapHopV2[] hops, address profitRecipient,
///               uint256 minProfit, uint256 deadline)
///
///  Invariants: repayment is settled BEFORE any residual is forwarded; the
///  residual (profit) of the primary borrowed asset must be >= minProfit or the
///  whole flash reverts atomically; no standing balances or allowances remain.
contract FlashLoanReceiverV2 is
    IExecutorV2, IFlashLoanRecipient, IFlashLoanSimpleReceiver, IMorphoFlashLoanCallback
{
    using MultiVenueSwapAdapter for SwapHopV2;

    // --- Immutable configuration ------------------------------------------
    address public immutable owner;
    IBalancerV2Vault public immutable balancerVault;
    IAaveV3Pool public immutable aavePool;
    IMorphoBlue public immutable morphoBlue;

    // --- Flash-window state machine ---------------------------------------
    // 0 = none, 1 = balancer_v2, 2 = aave_v3, 3 = morpho_blue
    bool private _authorized;
    uint8 private _pendingProvider;
    // Morpho's callback carries no token arg; record the borrowed token here.
    address private _morphoToken;

    // --- Owner-controlled allowlists --------------------------------------
    mapping(address => bool) public allowedRouters;
    mapping(address => bool) public allowedFactories;

    bytes32 private constant _PROVIDER_BALANCER = keccak256("balancer_v2");
    bytes32 private constant _PROVIDER_AAVE     = keccak256("aave_v3");
    bytes32 private constant _PROVIDER_MORPHO   = keccak256("morpho_blue");

    constructor(
        address _balancerVault,
        address _aavePool,
        address _morphoBlue,
        address[] memory _routers,
        address[] memory _factories
    ) {
        if (_balancerVault == address(0) || _aavePool == address(0) || _morphoBlue == address(0)) {
            revert ErrorsV2.ZeroAddress();
        }
        owner         = msg.sender;
        balancerVault = IBalancerV2Vault(_balancerVault);
        aavePool      = IAaveV3Pool(_aavePool);
        morphoBlue    = IMorphoBlue(_morphoBlue);
        for (uint256 i = 0; i < _routers.length; i++) {
            if (_routers[i] == address(0)) revert ErrorsV2.ZeroAddress();
            allowedRouters[_routers[i]] = true;
            emit RouterAllowanceUpdated(_routers[i], true);
        }
        for (uint256 i = 0; i < _factories.length; i++) {
            if (_factories[i] == address(0)) revert ErrorsV2.ZeroAddress();
            allowedFactories[_factories[i]] = true;
            emit FactoryAllowanceUpdated(_factories[i], true);
        }
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert ErrorsV2.NotOwner();
        _;
    }

    function receiverVersion() external pure override returns (string memory) {
        return "v2";
    }

    // --- Decoded userData -------------------------------------------------
    struct _Payload {
        SwapHopV2[] hops;
        address profitRecipient;
        uint256 minProfit;
        uint256 deadline;
    }

    function _decode(bytes calldata userData) private pure returns (_Payload memory p) {
        (p.hops, p.profitRecipient, p.minProfit, p.deadline) =
            abi.decode(userData, (SwapHopV2[], address, uint256, uint256));
    }

    /// @dev Runs the typed hop set with ALL security checks performed here,
    ///      before the adapter's external call. Fail-closed on every branch.
    function _runHops(SwapHopV2[] memory hops, uint256 topDeadline) private {
        if (hops.length == 0) revert ErrorsV2.EmptyHops();
        if (block.timestamp > topDeadline) {
            revert ErrorsV2.TransactionExpired(topDeadline, block.timestamp);
        }
        for (uint256 i = 0; i < hops.length; i++) {
            SwapHopV2 memory h = hops[i];
            if (block.timestamp > h.deadline) {
                revert ErrorsV2.TransactionExpired(h.deadline, block.timestamp);
            }
            if (uint8(h.venue) > uint8(Venue.ALGEBRA_V3)) {
                revert ErrorsV2.VenueNotSupported(uint8(h.venue));
            }
            if (!allowedRouters[h.router]) revert ErrorsV2.RouterNotAllowed(h.router);
            if (h.venue == Venue.AERODROME_CLASSIC && !allowedFactories[h.factory]) {
                revert ErrorsV2.FactoryNotAllowed(h.factory);
            }
            h.runHop(i);
        }
    }

    // --- Balancer V2 head (selector 0x64ba4bc1, preserved from V1) ---------
    function execute(
        address[] calldata tokens,
        uint256[] calldata amounts,
        bytes calldata userData
    ) external override onlyOwner {
        if (tokens.length != amounts.length || tokens.length == 0) {
            revert ErrorsV2.ArrayLengthMismatch();
        }
        _authorized = true;
        _pendingProvider = 1;
        IERC20[] memory ercTokens = new IERC20[](tokens.length);
        for (uint256 i = 0; i < tokens.length; i++) {
            ercTokens[i] = IERC20(tokens[i]);
        }
        balancerVault.flashLoan(address(this), ercTokens, amounts, userData);
        _authorized = false;
        _pendingProvider = 0;
    }

    function receiveFlashLoan(
        IERC20[] calldata tokens,
        uint256[] calldata amounts,
        uint256[] calldata feeAmounts,
        bytes calldata userData
    ) external override {
        if (!_authorized || _pendingProvider != 1) revert ErrorsV2.NotAuthorized();
        if (msg.sender != address(balancerVault)) revert ErrorsV2.CallerNotVault();

        _Payload memory p = _decode(userData);
        _runHops(p.hops, p.deadline);

        address primaryAsset = address(tokens[0]);
        uint256 borrowed = amounts[0];
        uint256 premium = feeAmounts[0];
        uint256 residualPaid = 0;

        // Repay every borrowed token first (push model).
        for (uint256 i = 0; i < tokens.length; i++) {
            address t = address(tokens[i]);
            uint256 owed = amounts[i] + feeAmounts[i];
            uint256 bal = IERC20(t).balanceOf(address(this));
            if (bal < owed) revert ErrorsV2.InsufficientBalance(t, owed, bal);
            TransferHelper.safeTransfer(t, address(balancerVault), owed);
            if (i == 0) residualPaid = bal - owed;
        }

        // Atomic profit floor on the PRIMARY asset residual, then forward.
        _enforceAndForwardProfit(primaryAsset, residualPaid, p.minProfit, p.profitRecipient);

        emit ExecutionCompleted(
            _PROVIDER_BALANCER, p.profitRecipient, primaryAsset, borrowed, premium, residualPaid
        );
    }

    // --- Aave V3 head (selector 0x4343d8b2, preserved from V1) -------------
    function executeAave(
        address asset,
        uint256 amount,
        bytes calldata userData
    ) external override onlyOwner {
        _authorized = true;
        _pendingProvider = 2;
        aavePool.flashLoanSimple(address(this), asset, amount, userData, 0);
        _authorized = false;
        _pendingProvider = 0;
    }

    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external override returns (bool) {
        if (!_authorized || _pendingProvider != 2) revert ErrorsV2.NotAuthorized();
        if (msg.sender != address(aavePool)) revert ErrorsV2.CallerNotPool();
        if (initiator != address(this)) revert ErrorsV2.NotAuthorized();

        _Payload memory p = _decode(params);
        _runHops(p.hops, p.deadline);

        uint256 owed = AaveV3Adapter.owedSimple(amount, premium);
        uint256 bal = IERC20(asset).balanceOf(address(this));
        if (bal < owed) revert ErrorsV2.InsufficientBalance(asset, owed, bal);
        // Aave pulls `owed` via transferFrom after this returns — approve exact.
        AaveV3Adapter.approveRepay(aavePool, asset, owed);
        uint256 residualPaid = bal - owed;

        _enforceAndForwardProfit(asset, residualPaid, p.minProfit, p.profitRecipient);

        emit ExecutionCompleted(
            _PROVIDER_AAVE, p.profitRecipient, asset, amount, premium, residualPaid
        );
        return true;
    }

    // --- Morpho Blue head (NEW in V2) -------------------------------------
    function executeMorpho(
        address token,
        uint256 amount,
        bytes calldata userData
    ) external override onlyOwner {
        if (token == address(0)) revert ErrorsV2.ZeroAddress();
        _authorized = true;
        _pendingProvider = 3;
        _morphoToken = token;                 // callback carries no token arg
        morphoBlue.flashLoan(token, amount, userData);
        _morphoToken = address(0);
        _authorized = false;
        _pendingProvider = 0;
    }

    function onMorphoFlashLoan(uint256 assets, bytes calldata data) external override {
        if (!_authorized || _pendingProvider != 3) revert ErrorsV2.NotAuthorized();
        if (msg.sender != address(morphoBlue)) revert ErrorsV2.CallerNotMorpho();
        address token = _morphoToken;
        if (token == address(0)) revert ErrorsV2.MorphoReentrancyGuard();

        _Payload memory p = _decode(data);
        _runHops(p.hops, p.deadline);

        // Morpho is 0-fee: owed == principal. Morpho pulls via transferFrom.
        uint256 owed = assets;
        uint256 bal = IERC20(token).balanceOf(address(this));
        if (bal < owed) revert ErrorsV2.InsufficientBalance(token, owed, bal);
        // Exact approval to the singleton; consumed fully by the pull ⇒ 0 left.
        TransferHelper.safeApprove(token, address(morphoBlue), owed);
        uint256 residualPaid = bal - owed;

        _enforceAndForwardProfit(token, residualPaid, p.minProfit, p.profitRecipient);

        emit ExecutionCompleted(
            _PROVIDER_MORPHO, p.profitRecipient, token, assets, 0, residualPaid
        );
    }

    // --- Profit enforcement (post-repayment) ------------------------------
    /// @dev Repayment has already been settled (pushed to Balancer, or approved
    ///      for the Aave/Morpho pull) BEFORE this is called. Enforces the atomic
    ///      minProfit floor on the primary asset residual, then forwards it.
    function _enforceAndForwardProfit(
        address asset,
        uint256 residual,
        uint256 minProfit,
        address profitRecipient
    ) private {
        if (residual < minProfit) revert ErrorsV2.ProfitBelowMinimum(minProfit, residual);
        if (residual > 0 && profitRecipient != address(0)) {
            TransferHelper.safeTransfer(asset, profitRecipient, residual);
        }
    }

    // --- Owner allowlist management ---------------------------------------
    function setRouterAllowed(address router, bool allowed) public override onlyOwner {
        if (router == address(0)) revert ErrorsV2.ZeroAddress();
        allowedRouters[router] = allowed;
        emit RouterAllowanceUpdated(router, allowed);
    }

    function setRoutersAllowed(address[] calldata routers, bool[] calldata alloweds)
        external override onlyOwner
    {
        if (routers.length != alloweds.length) revert ErrorsV2.ArrayLengthMismatch();
        for (uint256 i = 0; i < routers.length; i++) {
            setRouterAllowed(routers[i], alloweds[i]);
        }
    }

    function setFactoryAllowed(address factory, bool allowed) public override onlyOwner {
        if (factory == address(0)) revert ErrorsV2.ZeroAddress();
        allowedFactories[factory] = allowed;
        emit FactoryAllowanceUpdated(factory, allowed);
    }

    function setFactoriesAllowed(address[] calldata factories, bool[] calldata alloweds)
        external override onlyOwner
    {
        if (factories.length != alloweds.length) revert ErrorsV2.ArrayLengthMismatch();
        for (uint256 i = 0; i < factories.length; i++) {
            setFactoryAllowed(factories[i], alloweds[i]);
        }
    }

    function isRouterAllowed(address router) external view override returns (bool) {
        return allowedRouters[router];
    }

    function isFactoryAllowed(address factory) external view override returns (bool) {
        return allowedFactories[factory];
    }

    // --- Rescue (owner-only, post-mortem) ---------------------------------
    function rescue(address token, address to, uint256 amount) external override onlyOwner {
        TransferHelper.safeTransfer(token, to, amount);
        emit Rescued(token, to, amount);
    }

    // --- View hook --------------------------------------------------------
    function inFlashWindow() external view returns (bool authorized, uint8 provider) {
        return (_authorized, _pendingProvider);
    }
}
