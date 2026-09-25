// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title ArbiCore X Executor V2 — venue-typed, multi-provider surface.
/// @notice Interface Freeze v1.1. Selectors ``execute`` (0x64ba4bc1) and
///         ``executeAave`` (0x4343d8b2) are PRESERVED identical to V1;
///         ``executeMorpho`` is the new V2 flash head. Swap execution is a
///         typed per-hop dispatch over an owner-allowlisted router set — there
///         is NO arbitrary target+calldata path.

/// @notice Execution ABI families supported by FlashLoanReceiverV2. The enum
///         value is the on-chain calldata shape; the concrete DEX (e.g.
///         sushiswap_v3 vs uniswap_v3) is identified backend-side and mapped
///         onto one of these families. Fail-closed: any value outside this set
///         reverts VenueNotSupported.
enum Venue {
    UNISWAP_V3,           // 0: exactInputSingle((tokenIn,tokenOut,fee,recipient,amountIn,amountOutMinimum,sqrtPriceLimitX96))
    UNISWAP_V2,           // 1: swapExactTokensForTokens(uint256,uint256,address[],address,uint256)
    AERODROME_CLASSIC,    // 2: swapExactTokensForTokens(uint256,uint256,Route(from,to,stable,factory)[],address,uint256)
    AERODROME_SLIPSTREAM, // 3: exactInputSingle((tokenIn,tokenOut,tickSpacing,recipient,deadline,amountIn,amountOutMinimum,sqrtPriceLimitX96))
    ALGEBRA_V3            // 4: exactInputSingle((tokenIn,tokenOut,recipient,deadline,amountIn,amountOutMinimum,limitSqrtPrice))
}

/// @notice One typed swap leg. ``router`` MUST be owner-allowlisted; for
///         AERODROME_CLASSIC ``factory`` MUST be owner-allowlisted too.
struct SwapHopV2 {
    Venue   venue;               // uint8 ABI-family discriminator
    address router;              // router target — checked against allowedRouters
    address tokenIn;
    address tokenOut;
    uint24  feeOrTickSpacing;    // UniV3/Algebra fee ppm, or Slipstream tickSpacing (as uint24)
    bool    stable;              // Aerodrome classic stable/volatile selector
    address factory;             // Aerodrome classic factory — checked against allowedFactories
    uint256 amountIn;            // 0 => forward the full current tokenIn balance
    uint256 amountOutMinimum;    // per-hop slippage floor (enforced by the router)
    uint160 sqrtPriceLimitX96;   // price bound (UniV3/Slipstream/Algebra); 0 = unbounded
    uint256 deadline;            // per-hop deadline; reverts if block.timestamp > deadline
}

/// @title Morpho Blue singleton flash-loan surface (canonical).
/// @dev Verified against morpho-org/morpho-blue@main src/Morpho.sol.
interface IMorphoBlue {
    function flashLoan(address token, uint256 assets, bytes calldata data) external;
}

/// @title Morpho Blue flash-loan callback (canonical).
/// @dev IMorphoFlashLoanCallback.onMorphoFlashLoan(uint256,bytes) — selector
///      0x31f57072. The callback carries NO token argument: the receiver MUST
///      record the borrowed token in its flash window before invoking flashLoan.
interface IMorphoFlashLoanCallback {
    function onMorphoFlashLoan(uint256 assets, bytes calldata data) external;
}

/// @title IExecutorV2 — canonical external interface.
interface IExecutorV2 {
    /// @notice Balancer V2 flash head. Selector 0x64ba4bc1 (PRESERVED from V1).
    function execute(address[] calldata tokens, uint256[] calldata amounts, bytes calldata userData) external;

    /// @notice Aave V3 single-asset flash head. Selector 0x4343d8b2 (PRESERVED from V1).
    function executeAave(address asset, uint256 amount, bytes calldata userData) external;

    /// @notice Morpho Blue single-asset flash head. NEW in V2.
    function executeMorpho(address token, uint256 amount, bytes calldata userData) external;

    /// @notice Version tag bound to the deployed bytecode.
    function receiverVersion() external pure returns (string memory);

    function isRouterAllowed(address router) external view returns (bool);
    function isFactoryAllowed(address factory) external view returns (bool);
    function setRouterAllowed(address router, bool allowed) external;
    function setRoutersAllowed(address[] calldata routers, bool[] calldata alloweds) external;
    function setFactoryAllowed(address factory, bool allowed) external;
    function setFactoriesAllowed(address[] calldata factories, bool[] calldata alloweds) external;
    function rescue(address token, address to, uint256 amount) external;

    event ExecutionCompleted(
        bytes32 indexed provider,
        address indexed profitRecipient,
        address indexed primaryAsset,
        uint256 borrowed,
        uint256 premium,
        uint256 residualPaid
    );
    event RouterAllowanceUpdated(address indexed router, bool allowed);
    event FactoryAllowanceUpdated(address indexed factory, bool allowed);
    event Rescued(address indexed token, address indexed to, uint256 amount);
}
