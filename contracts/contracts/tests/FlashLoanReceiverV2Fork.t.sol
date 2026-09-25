// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {FlashLoanReceiverV2} from "../core/FlashLoanReceiverV2.sol";
import {Venue, SwapHopV2} from "../interfaces/IExecutorV2.sol";
import {ErrorsV2} from "../libraries/ErrorsV2.sol";
import {IERC20} from "../interfaces/IERC20.sol";

/// @notice V2 fork validation against REAL Base mainnet state (read/simulate
///         only — an Anvil fork is local; NOTHING is broadcast to any network).
///         Validates the complete V2 execution path end-to-end:
///           flash provider (Morpho Blue + Balancer V2) → typed UniV3/Aerodrome
///           swap → per-hop router/factory allowlist → token approvals →
///           repayment → atomic minProfit → deadline → revert behaviour →
///           allowance hygiene.
///
///  ENV-GATED (consistent with B7 / the certification manifest's
///  UNAVAILABLE_DEPENDENCY class): skips cleanly when BASE_RPC_URL is unset so
///  CI stays green without an operator RPC. Run with:
///    BASE_RPC_URL=https://mainnet.base.org forge test --match-contract ForkV2 -vv
contract FlashLoanReceiverV2ForkTest is Test {
    // Real Base mainnet addresses (chainId 8453).
    address constant USDC = 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913; // 6 dec
    address constant WETH = 0x4200000000000000000000000000000000000006; // 18 dec
    address constant BALANCER_VAULT = 0xBA12222222228d8Ba445958a75a0704d566BF2C8;
    address constant AAVE_POOL = 0xA238Dd80C259a72e81d7e4664a9801593F98d1c5;
    address constant MORPHO = 0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb;
    address constant UNIV3_ROUTER = 0x2626664c2603336E57B271c5C0b26F421741e481;
    address constant AERODROME_ROUTER = 0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43;
    address constant AERODROME_FACTORY = 0x420DD381b31aEf6683db6B902084cB0FFECe40Da;

    FlashLoanReceiverV2 internal exec;
    address internal profitRecipient = address(0xBEEF);
    uint256 internal FAR;
    bool internal forkOk;

    function setUp() public {
        string memory rpc = vm.envOr("BASE_RPC_URL", string(""));
        if (bytes(rpc).length == 0) { forkOk = false; return; }
        vm.createSelectFork(rpc);
        if (block.chainid != 8453) { forkOk = false; return; }
        forkOk = true;
        FAR = block.timestamp + 1 hours;

        address[] memory routers = new address[](2);
        routers[0] = UNIV3_ROUTER;
        routers[1] = AERODROME_ROUTER;
        address[] memory factories = new address[](1);
        factories[0] = AERODROME_FACTORY;
        exec = new FlashLoanReceiverV2(BALANCER_VAULT, AAVE_POOL, MORPHO, routers, factories);
    }

    modifier needsFork() { if (!forkOk) { return; } _; }

    function _uniV3RoundTrip(uint256 usdcIn) internal view returns (SwapHopV2[] memory hops) {
        hops = new SwapHopV2[](2);
        hops[0] = SwapHopV2({venue: Venue.UNISWAP_V3, router: UNIV3_ROUTER,
            tokenIn: USDC, tokenOut: WETH, feeOrTickSpacing: 500, stable: false,
            factory: address(0), amountIn: usdcIn, amountOutMinimum: 0,
            sqrtPriceLimitX96: 0, deadline: FAR});
        hops[1] = SwapHopV2({venue: Venue.UNISWAP_V3, router: UNIV3_ROUTER,
            tokenIn: WETH, tokenOut: USDC, feeOrTickSpacing: 500, stable: false,
            factory: address(0), amountIn: 0 /*forward full WETH bal*/, amountOutMinimum: 0,
            sqrtPriceLimitX96: 0, deadline: FAR});
    }

    function _ud(SwapHopV2[] memory hops, uint256 minProfit) internal view returns (bytes memory) {
        return abi.encode(hops, profitRecipient, minProfit, FAR);
    }

    // ---- Real on-chain identity sanity (bytecode present on the fork) ----
    function test_fork_chain_identity_and_targets() public needsFork {
        assertEq(block.chainid, 8453);
        assertGt(MORPHO.code.length, 0);
        assertGt(BALANCER_VAULT.code.length, 0);
        assertGt(UNIV3_ROUTER.code.length, 0);
        assertEq(exec.receiverVersion(), "v2");
        assertTrue(exec.isRouterAllowed(UNIV3_ROUTER));
        assertTrue(exec.isFactoryAllowed(AERODROME_FACTORY));
    }

    // ---- Morpho Blue flash → real UniV3 round-trip → repay (pull) ----
    function test_fork_morpho_flash_univ3_roundtrip_repays() public needsFork {
        uint256 flashAmt = 1_000 * 1e6;             // 1,000 USDC (0-fee Morpho)
        uint256 cushion = 50 * 1e6;                  // cover swap fees/slippage
        deal(USDC, address(exec), cushion);          // realistic pre-fund
        exec.executeMorpho(USDC, flashAmt, _ud(_uniV3RoundTrip(0), 0));
        // Morpho pulled exactly the principal back (0 fee); no standing allowance.
        assertEq(IERC20(USDC).allowance(address(exec), MORPHO), 0);
        (bool a, uint8 pr) = exec.inFlashWindow();
        assertFalse(a); assertEq(pr, 0);
    }

    // ---- Balancer V2 flash → real UniV3 round-trip → repay (push) ----
    function test_fork_balancer_flash_univ3_roundtrip_repays() public needsFork {
        uint256 flashAmt = 500 * 1e6;
        uint256 cushion = 30 * 1e6;
        deal(USDC, address(exec), cushion);
        address[] memory toks = new address[](1); toks[0] = USDC;
        uint256[] memory amts = new uint256[](1); amts[0] = flashAmt;
        exec.execute(toks, amts, _ud(_uniV3RoundTrip(0), 0));
        assertEq(IERC20(USDC).allowance(address(exec), UNIV3_ROUTER), 0);
        (bool a, uint8 pr) = exec.inFlashWindow();
        assertFalse(a); assertEq(pr, 0);
    }

    // ---- Aerodrome Classic (typed factory allowlist) real swap path ----
    function test_fork_aerodrome_classic_swap_executes() public needsFork {
        uint256 flashAmt = 200 * 1e6;
        uint256 cushion = 10 * 1e6;
        deal(USDC, address(exec), cushion);
        SwapHopV2[] memory hops = new SwapHopV2[](2);
        hops[0] = SwapHopV2({venue: Venue.AERODROME_CLASSIC, router: AERODROME_ROUTER,
            tokenIn: USDC, tokenOut: WETH, feeOrTickSpacing: 0, stable: false,
            factory: AERODROME_FACTORY, amountIn: flashAmt, amountOutMinimum: 0,
            sqrtPriceLimitX96: 0, deadline: FAR});
        hops[1] = SwapHopV2({venue: Venue.AERODROME_CLASSIC, router: AERODROME_ROUTER,
            tokenIn: WETH, tokenOut: USDC, feeOrTickSpacing: 0, stable: false,
            factory: AERODROME_FACTORY, amountIn: 0, amountOutMinimum: 0,
            sqrtPriceLimitX96: 0, deadline: FAR});
        exec.executeMorpho(USDC, flashAmt, _ud(hops, 0));
        assertEq(IERC20(USDC).allowance(address(exec), AERODROME_ROUTER), 0);
    }

    // ---- Atomic minProfit enforcement (revert path) ----
    function test_fork_minprofit_floor_reverts() public needsFork {
        uint256 flashAmt = 100 * 1e6;
        deal(USDC, address(exec), 5 * 1e6);
        // minProfit far above any achievable residual ⇒ whole flash reverts.
        vm.expectRevert(); // ProfitBelowMinimum(minProfit, residual)
        exec.executeMorpho(USDC, flashAmt, _ud(_uniV3RoundTrip(0), 1_000_000 * 1e6));
    }

    // ---- RouterNotAllowed (negative) ----
    function test_fork_disallowed_router_reverts() public needsFork {
        deal(USDC, address(exec), 10 * 1e6);
        SwapHopV2[] memory hops = _uniV3RoundTrip(0);
        hops[0].router = address(0xDEAD);
        vm.expectRevert(abi.encodeWithSelector(ErrorsV2.RouterNotAllowed.selector, address(0xDEAD)));
        exec.executeMorpho(USDC, 100 * 1e6, _ud(hops, 0));
    }

    // ---- FactoryNotAllowed (negative) ----
    function test_fork_disallowed_factory_reverts() public needsFork {
        deal(USDC, address(exec), 10 * 1e6);
        SwapHopV2[] memory hops = new SwapHopV2[](1);
        hops[0] = SwapHopV2({venue: Venue.AERODROME_CLASSIC, router: AERODROME_ROUTER,
            tokenIn: USDC, tokenOut: WETH, feeOrTickSpacing: 0, stable: false,
            factory: address(0x9999), amountIn: 1e6, amountOutMinimum: 0,
            sqrtPriceLimitX96: 0, deadline: FAR});
        vm.expectRevert(abi.encodeWithSelector(ErrorsV2.FactoryNotAllowed.selector, address(0x9999)));
        exec.executeMorpho(USDC, 100 * 1e6, _ud(hops, 0));
    }

    // ---- Expired deadline (negative) ----
    function test_fork_expired_deadline_reverts() public needsFork {
        deal(USDC, address(exec), 10 * 1e6);
        uint256 past = block.timestamp - 1;
        SwapHopV2[] memory hops = _uniV3RoundTrip(0);
        hops[0].deadline = past;
        bytes memory ud = abi.encode(hops, profitRecipient, 0, past);
        vm.expectRevert(); // TransactionExpired
        exec.executeMorpho(USDC, 100 * 1e6, ud);
    }
}
