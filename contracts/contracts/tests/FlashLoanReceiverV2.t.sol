// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {FlashLoanReceiverV2} from "../core/FlashLoanReceiverV2.sol";
import {Venue, SwapHopV2} from "../interfaces/IExecutorV2.sol";
import {ErrorsV2} from "../libraries/ErrorsV2.sol";
import {IERC20} from "../interfaces/IERC20.sol";
import {MockERC20} from "./MockERC20.sol";
import {MockV3Router, MockBalancerVaultV2, MockAaveV3PoolV2, MockMorphoBlue} from "./MocksV2.sol";

/// @notice Unit + negative/security tests for FlashLoanReceiverV2 (Freeze v1.1).
///         Deterministic mocks; no forked RPC. Multi-venue fork proofs live in
///         a separate fork test (env-gated).
contract FlashLoanReceiverV2Test is Test {
    FlashLoanReceiverV2 internal exec;
    MockERC20 internal usdc;
    MockERC20 internal weth;
    MockV3Router internal router;
    MockBalancerVaultV2 internal vault;
    MockAaveV3PoolV2 internal pool;
    MockMorphoBlue internal morpho;

    address internal profitRecipient = address(0xBEEF);
    uint256 internal FAR = type(uint256).max; // never-expiring deadline

    function setUp() public {
        usdc = new MockERC20("USDC", "USDC", 6);
        weth = new MockERC20("WETH", "WETH", 18);
        router = new MockV3Router();
        vault = new MockBalancerVaultV2();
        pool = new MockAaveV3PoolV2();
        morpho = new MockMorphoBlue();

        address[] memory routers = new address[](1);
        routers[0] = address(router);
        address[] memory factories = new address[](0);
        exec = new FlashLoanReceiverV2(
            address(vault), address(pool), address(morpho), routers, factories
        );

        usdc.mint(address(vault), 1_000_000 * 1e6);
        usdc.mint(address(pool), 1_000_000 * 1e6);
        usdc.mint(address(morpho), 1_000_000 * 1e6);
        usdc.mint(address(router), 1_000_000 * 1e6);
        weth.mint(address(router), 1_000 * 1e18);
    }

    // ---- helpers ----
    function _oneHop(uint256 amtIn) internal view returns (SwapHopV2[] memory hops) {
        hops = new SwapHopV2[](1);
        hops[0] = SwapHopV2({
            venue: Venue.UNISWAP_V3, router: address(router),
            tokenIn: address(usdc), tokenOut: address(weth),
            feeOrTickSpacing: 500, stable: false, factory: address(0),
            amountIn: amtIn, amountOutMinimum: 0, sqrtPriceLimitX96: 0, deadline: FAR
        });
    }

    function _ud(SwapHopV2[] memory hops, uint256 minProfit, uint256 deadline)
        internal view returns (bytes memory)
    {
        return abi.encode(hops, profitRecipient, minProfit, deadline);
    }

    function _addr1(address a) internal pure returns (address[] memory r) {
        r = new address[](1); r[0] = a;
    }
    function _u1(uint256 v) internal pure returns (uint256[] memory r) {
        r = new uint256[](1); r[0] = v;
    }

    // ---- version ----
    function test_receiver_version_is_v2() public view {
        assertEq(exec.receiverVersion(), "v2");
    }

    // ---- constructor guards ----
    function test_constructor_reverts_on_zero_address() public {
        address[] memory rs = new address[](0);
        address[] memory fs = new address[](0);
        vm.expectRevert(ErrorsV2.ZeroAddress.selector);
        new FlashLoanReceiverV2(address(0), address(pool), address(morpho), rs, fs);
        vm.expectRevert(ErrorsV2.ZeroAddress.selector);
        new FlashLoanReceiverV2(address(vault), address(0), address(morpho), rs, fs);
        vm.expectRevert(ErrorsV2.ZeroAddress.selector);
        new FlashLoanReceiverV2(address(vault), address(pool), address(0), rs, fs);
    }

    // ---- owner gates ----
    function test_execute_not_owner_reverts() public {
        vm.prank(address(0xDEAD));
        vm.expectRevert(ErrorsV2.NotOwner.selector);
        exec.execute(_addr1(address(usdc)), _u1(100e6), "");
    }
    function test_executeAave_not_owner_reverts() public {
        vm.prank(address(0xDEAD));
        vm.expectRevert(ErrorsV2.NotOwner.selector);
        exec.executeAave(address(usdc), 100e6, "");
    }
    function test_executeMorpho_not_owner_reverts() public {
        vm.prank(address(0xDEAD));
        vm.expectRevert(ErrorsV2.NotOwner.selector);
        exec.executeMorpho(address(usdc), 100e6, "");
    }

    // ---- callback re-entry / caller pinning ----
    function test_receiveFlashLoan_unauthorized_reverts() public {
        IERC20[] memory t = new IERC20[](1); t[0] = IERC20(address(usdc));
        vm.expectRevert(ErrorsV2.NotAuthorized.selector);
        exec.receiveFlashLoan(t, _u1(100), _u1(0), "");
    }
    function test_executeOperation_unauthorized_reverts() public {
        vm.expectRevert(ErrorsV2.NotAuthorized.selector);
        exec.executeOperation(address(usdc), 100, 0, address(exec), "");
    }
    function test_onMorphoFlashLoan_unauthorized_reverts() public {
        vm.expectRevert(ErrorsV2.NotAuthorized.selector);
        exec.onMorphoFlashLoan(100, "");
    }

    // ---- Balancer happy path + profit floor + no standing allowance ----
    function test_balancer_happy_path_and_profit_forwarded() public {
        // 1 wei swap keeps balances aligned; pre-mint principal + profit.
        usdc.mint(address(exec), 100e6 + 10e6); // principal + 10 USDC profit
        SwapHopV2[] memory hops = _oneHop(1);
        exec.execute(_addr1(address(usdc)), _u1(100e6), _ud(hops, 5e6, FAR));
        (bool a, uint8 pr) = exec.inFlashWindow();
        assertFalse(a); assertEq(pr, 0);
        assertGe(usdc.balanceOf(profitRecipient), 5e6);
        // No standing router allowance.
        assertEq(usdc.allowance(address(exec), address(router)), 0);
    }

    // ---- Aave happy path ----
    function test_aave_happy_path() public {
        uint256 amt = 100e6;
        uint256 premium = (amt * 5) / 10_000;
        usdc.mint(address(exec), amt + premium + 1e6);
        SwapHopV2[] memory hops = _oneHop(1);
        exec.executeAave(address(usdc), amt, _ud(hops, 0, FAR));
        (bool a, uint8 pr) = exec.inFlashWindow();
        assertFalse(a); assertEq(pr, 0);
        // Aave allowance consumed by the pull.
        assertEq(usdc.allowance(address(exec), address(pool)), 0);
    }

    // ---- Morpho happy path + exact allowance cleared ----
    function test_morpho_happy_path_and_allowance_cleared() public {
        uint256 amt = 100e6;
        usdc.mint(address(exec), amt + 2e6);
        SwapHopV2[] memory hops = _oneHop(1);
        exec.executeMorpho(address(usdc), amt, _ud(hops, 0, FAR));
        (bool a, uint8 pr) = exec.inFlashWindow();
        assertFalse(a); assertEq(pr, 0);
        assertEq(usdc.allowance(address(exec), address(morpho)), 0);
    }

    // ---- minProfit atomic enforcement ----
    function test_min_profit_below_threshold_reverts() public {
        // Residual after repayment ≈ pre-minted amount (borrowed principal is
        // repaid). Pre-mint 1 USDC, 1-wei swap ⇒ residual = 1e6 - 1 = 999_999,
        // which is below the 50 USDC floor ⇒ atomic revert.
        usdc.mint(address(exec), 1e6);
        SwapHopV2[] memory hops = _oneHop(1);
        vm.expectRevert(abi.encodeWithSelector(ErrorsV2.ProfitBelowMinimum.selector, 50e6, uint256(999_999)));
        exec.execute(_addr1(address(usdc)), _u1(100e6), _ud(hops, 50e6, FAR));
    }

    // ---- insufficient balance to repay reverts ----
    function test_insufficient_repay_reverts() public {
        // No profit minted → after 1-wei swap the executor cannot cover principal.
        SwapHopV2[] memory hops = _oneHop(1);
        vm.expectRevert(); // InsufficientBalance(token, owed, bal)
        exec.execute(_addr1(address(usdc)), _u1(100e6), _ud(hops, 0, FAR));
    }

    // ---- router allowlist ----
    function test_disallowed_router_reverts() public {
        usdc.mint(address(exec), 200e6);
        SwapHopV2[] memory hops = _oneHop(1);
        hops[0].router = address(0x1234);
        vm.expectRevert(abi.encodeWithSelector(ErrorsV2.RouterNotAllowed.selector, address(0x1234)));
        exec.execute(_addr1(address(usdc)), _u1(100e6), _ud(hops, 0, FAR));
    }

    // ---- factory allowlist (Aerodrome classic) ----
    function test_disallowed_factory_reverts() public {
        usdc.mint(address(exec), 200e6);
        SwapHopV2[] memory hops = _oneHop(1);
        hops[0].venue = Venue.AERODROME_CLASSIC;
        hops[0].factory = address(0x9999);
        // router is allowlisted, but factory is not.
        vm.expectRevert(abi.encodeWithSelector(ErrorsV2.FactoryNotAllowed.selector, address(0x9999)));
        exec.execute(_addr1(address(usdc)), _u1(100e6), _ud(hops, 0, FAR));
    }

    // ---- deadline expiry ----
    function test_expired_deadline_reverts() public {
        usdc.mint(address(exec), 200e6);
        SwapHopV2[] memory hops = _oneHop(1);
        vm.warp(1_000_000);
        uint256 past = block.timestamp - 1;
        vm.expectRevert(abi.encodeWithSelector(ErrorsV2.TransactionExpired.selector, past, block.timestamp));
        exec.execute(_addr1(address(usdc)), _u1(100e6), _ud(hops, 0, past));
    }

    // ---- empty hops ----
    function test_empty_hops_reverts() public {
        usdc.mint(address(exec), 200e6);
        SwapHopV2[] memory hops = new SwapHopV2[](0);
        vm.expectRevert(ErrorsV2.EmptyHops.selector);
        exec.execute(_addr1(address(usdc)), _u1(100e6), _ud(hops, 0, FAR));
    }

    // ---- owner-only allowlist management ----
    function test_setRouter_not_owner_reverts() public {
        vm.prank(address(0xDEAD));
        vm.expectRevert(ErrorsV2.NotOwner.selector);
        exec.setRouterAllowed(address(0x1234), true);
    }
    function test_owner_can_manage_allowlists() public {
        exec.setRouterAllowed(address(0x1234), true);
        assertTrue(exec.isRouterAllowed(address(0x1234)));
        exec.setFactoryAllowed(address(0x5678), true);
        assertTrue(exec.isFactoryAllowed(address(0x5678)));
        exec.setRouterAllowed(address(0x1234), false);
        assertFalse(exec.isRouterAllowed(address(0x1234)));
    }

    // ---- rescue owner-only ----
    function test_rescue_owner_only() public {
        usdc.mint(address(exec), 1_000);
        vm.prank(address(0xDEAD));
        vm.expectRevert(ErrorsV2.NotOwner.selector);
        exec.rescue(address(usdc), profitRecipient, 500);
        exec.rescue(address(usdc), profitRecipient, 500);
        assertEq(usdc.balanceOf(profitRecipient), 500);
    }

    // ---- wrong-provider callback isolation ----
    function test_balancer_callback_from_wrong_caller_reverts() public {
        // Open a balancer window by calling execute through the real mock vault
        // is not possible to intercept mid-flight here; instead assert a direct
        // aave callback during no window fails closed (covered) and that a
        // non-vault caller cannot satisfy the balancer callback.
        IERC20[] memory t = new IERC20[](1); t[0] = IERC20(address(usdc));
        vm.expectRevert(ErrorsV2.NotAuthorized.selector);
        vm.prank(address(0xCAFE));
        exec.receiveFlashLoan(t, _u1(100), _u1(0), "");
    }
}
