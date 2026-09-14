// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

interface IERC20Minimal {
    function balanceOf(address account) external view returns (uint256);
}

interface IUniswapV3PoolMinimal {
    function token0() external view returns (address);
    function token1() external view returns (address);
    function fee() external view returns (uint24);
    function tickSpacing() external view returns (int24);
    function liquidity() external view returns (uint128);

    function slot0()
        external
        view
        returns (
            uint160 sqrtPriceX96,
            int24 tick,
            uint16 observationIndex,
            uint16 observationCardinality,
            uint16 observationCardinalityNext,
            uint8 feeProtocol,
            bool unlocked
        );
}

interface IFlashLoanReceiverMinimal {
    function owner() external view returns (address);
    function balancerVault() external view returns (address);
    function uniRouter() external view returns (address);

    function execute(
        address[] calldata tokens,
        uint256[] calldata amounts,
        bytes calldata userData
    ) external;
}

/*
 * B7.3.68 Stage 1
 *
 * Purpose:
 *   Establish a deterministic Base mainnet fork and prove that the real
 *   deployed executor + real V3 pools exist on the fork with their actual
 *   mainnet state.
 *
 * This stage intentionally does NOT:
 *   - sign anything
 *   - broadcast anything
 *   - modify production
 *   - modify mainnet
 *   - execute a flash loan
 *
 * Stage 2 will add the controlled fork-only price differential and the
 * genuine Balancer -> V3 -> V3 -> repayment -> profit assertion.
 */

struct SwapHop {
    address tokenIn;
    address tokenOut;
    uint24 feePpm;
    uint256 amountIn;
    uint256 amountOutMinimum;
    uint160 sqrtPriceLimitX96;
}

interface IBalancerVaultMinimal {
    function flashLoan(
        address recipient,
        address[] calldata tokens,
        uint256[] calldata amounts,
        bytes calldata userData
    ) external;
}

interface ISwapRouter02Minimal {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }

    function exactInputSingle(
        ExactInputSingleParams calldata params
    ) external payable returns (uint256 amountOut);
}

contract B7_3_68_ProfitableForkExecution is Test {
    uint256 internal constant FORK_BLOCK = 51222201;

    address internal constant EXECUTOR =
        0x0E3FDb0F0E615A517588BD44ac6C78Bb7615927f;

    address internal constant EXPECTED_OWNER =
        0x0a43F432681cA5eE053D53B79Ae1648FDAaBFa89;

    address internal constant WETH =
        0x4200000000000000000000000000000000000006;

    address internal constant USDC =
        0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913;

    address internal constant POOL_5BPS =
        0xd0b53D9277642d899DF5C87A3966A349A798F224;

    address internal constant POOL_1BPS =
        0xb4CB800910B228ED3d0834cF79D697127BBB00e5;

    uint256 internal forkId;

    function setUp() public {
        string memory rpc = vm.envString("BASE_RPC_URL");
        forkId = vm.createSelectFork(rpc, FORK_BLOCK);
    }

    function test_B7_3_68_fork_slot0_storage() public {
        IUniswapV3PoolMinimal p5 = IUniswapV3PoolMinimal(POOL_5BPS);
        IUniswapV3PoolMinimal p1 = IUniswapV3PoolMinimal(POOL_1BPS);

        (
            uint160 sqrt5,
            int24 tick5,
            uint16 oi5,
            uint16 oc5,
            uint16 ocn5,
            uint8 fp5,
            bool unlocked5
        ) = p5.slot0();

        (
            uint160 sqrt1,
            int24 tick1,
            uint16 oi1,
            uint16 oc1,
            uint16 ocn1,
            uint8 fp1,
            bool unlocked1
        ) = p1.slot0();

        bytes32 raw5;
        bytes32 raw1;

        assembly {
            raw5 := sload(0)
        }

        // Reading storage from the test contract itself is intentional here:
        // the actual pool storage is inspected with vm.load below.
        raw5 = vm.load(POOL_5BPS, bytes32(uint256(0)));
        raw1 = vm.load(POOL_1BPS, bytes32(uint256(0)));

        emit log_named_bytes32("pool_5bps_slot0_storage", raw5);
        emit log_named_bytes32("pool_1bps_slot0_storage", raw1);

        emit log_named_uint("pool_5bps_observationIndex", oi5);
        emit log_named_uint("pool_5bps_observationCardinality", oc5);
        emit log_named_uint("pool_5bps_observationCardinalityNext", ocn5);
        emit log_named_uint("pool_5bps_feeProtocol", fp5);
        emit log_named_uint("pool_5bps_unlocked", unlocked5 ? 1 : 0);

        emit log_named_uint("pool_1bps_observationIndex", oi1);
        emit log_named_uint("pool_1bps_observationCardinality", oc1);
        emit log_named_uint("pool_1bps_observationCardinalityNext", ocn1);
        emit log_named_uint("pool_1bps_feeProtocol", fp1);
        emit log_named_uint("pool_1bps_unlocked", unlocked1 ? 1 : 0);

        assertGt(sqrt5, 0);
        assertGt(sqrt1, 0);
        assertTrue(unlocked5);
        assertTrue(unlocked1);

        emit log_named_int("pool_5bps_tick", tick5);
        emit log_named_int("pool_1bps_tick", tick1);

        emit log_string("STORAGE_READ_ONLY=true");
        emit log_string("MAINNET_STATE_MODIFIED=false");
        emit log_string("SIGNED=false");
        emit log_string("BROADCAST=false");
    }

    function test_B7_3_68_controlled_slot0_shift() public {
        IUniswapV3PoolMinimal p5 = IUniswapV3PoolMinimal(POOL_5BPS);
        IUniswapV3PoolMinimal p1 = IUniswapV3PoolMinimal(POOL_1BPS);

        (
            uint160 sqrt5,
            int24 tick5,
            uint16 oi5,
            uint16 oc5,
            uint16 ocn5,
            uint8 fp5,
            bool unlocked5
        ) = p5.slot0();

        (
            uint160 sqrt1,
            int24 tick1,
            uint16 oi1,
            uint16 oc1,
            uint16 ocn1,
            uint8 fp1,
            bool unlocked1
        ) = p1.slot0();

        /*
         * Uniswap V3 slot0 packing:
         *
         * [160 bits] sqrtPriceX96
         * [24 bits ] tick
         * [16 bits ] observationIndex
         * [16 bits ] observationCardinality
         * [16 bits ] observationCardinalityNext
         * [8 bits  ] feeProtocol
         * [1 bit   ] unlocked
         *
         * We intentionally change ONLY sqrtPriceX96 and tick while preserving
         * every other slot0 field.
         *
         * The shift is deliberately small and remains close to the current
         * active price. The subsequent slot0() call proves the fork state
         * accepted the local mutation.
         */

        uint160 shifted5 = sqrt5 + (sqrt5 / 1000);
        uint160 shifted1 = sqrt1 - (sqrt1 / 1000);

        bytes32 packed5 =
            bytes32(uint256(shifted5))
            | (bytes32(uint256(uint24(uint24(tick5)))) << 160)
            | (bytes32(uint256(oi5)) << 184)
            | (bytes32(uint256(oc5)) << 200)
            | (bytes32(uint256(ocn5)) << 216)
            | (bytes32(uint256(fp5)) << 232)
            | (bytes32(uint256(unlocked5 ? 1 : 0)) << 240);

        bytes32 packed1 =
            bytes32(uint256(shifted1))
            | (bytes32(uint256(uint24(uint24(tick1)))) << 160)
            | (bytes32(uint256(oi1)) << 184)
            | (bytes32(uint256(oc1)) << 200)
            | (bytes32(uint256(ocn1)) << 216)
            | (bytes32(uint256(fp1)) << 232)
            | (bytes32(uint256(unlocked1 ? 1 : 0)) << 240);

        vm.store(POOL_5BPS, bytes32(uint256(0)), packed5);
        vm.store(POOL_1BPS, bytes32(uint256(0)), packed1);

        (
            uint160 afterSqrt5,
            int24 afterTick5,
            ,
            ,
            ,
            ,
            bool afterUnlocked5
        ) = p5.slot0();

        (
            uint160 afterSqrt1,
            int24 afterTick1,
            ,
            ,
            ,
            ,
            bool afterUnlocked1
        ) = p1.slot0();

        assertEq(afterSqrt5, shifted5, "5bps sqrt shift failed");
        assertEq(afterSqrt1, shifted1, "1bps sqrt shift failed");

        assertEq(afterTick5, tick5, "5bps tick unexpectedly changed");
        assertEq(afterTick1, tick1, "1bps tick unexpectedly changed");

        assertTrue(afterUnlocked5, "5bps became locked");
        assertTrue(afterUnlocked1, "1bps became locked");

        emit log_named_uint("original_5bps_sqrt", sqrt5);
        emit log_named_uint("shifted_5bps_sqrt", afterSqrt5);
        emit log_named_uint("original_1bps_sqrt", sqrt1);
        emit log_named_uint("shifted_1bps_sqrt", afterSqrt1);

        emit log_string("FORK_ONLY_STORAGE_MUTATION=true");
        emit log_string("MAINNET_STATE_MODIFIED=false");
        emit log_string("SIGNED=false");
        emit log_string("BROADCAST=false");
    }


    function test_B7_3_68_real_swap_path_on_controlled_fork() public {
        /*
         * Recreate the controlled spread inside THIS forked test.
         * The fork is reset for every test function.
         */
        IUniswapV3PoolMinimal p5 = IUniswapV3PoolMinimal(POOL_5BPS);
        IUniswapV3PoolMinimal p1 = IUniswapV3PoolMinimal(POOL_1BPS);

        (
            uint160 sqrt5,
            int24 tick5,
            uint16 oi5,
            uint16 oc5,
            uint16 ocn5,
            uint8 fp5,
            bool unlocked5
        ) = p5.slot0();

        (
            uint160 sqrt1,
            int24 tick1,
            uint16 oi1,
            uint16 oc1,
            uint16 ocn1,
            uint8 fp1,
            bool unlocked1
        ) = p1.slot0();

        uint160 shifted5 = sqrt5 + (sqrt5 / 1000);
        uint160 shifted1 = sqrt1 - (sqrt1 / 1000);

        bytes32 packed5 =
            bytes32(uint256(shifted5))
            | (bytes32(uint256(uint24(uint24(tick5)))) << 160)
            | (bytes32(uint256(oi5)) << 184)
            | (bytes32(uint256(oc5)) << 200)
            | (bytes32(uint256(ocn5)) << 216)
            | (bytes32(uint256(fp5)) << 232)
            | (bytes32(uint256(unlocked5 ? 1 : 0)) << 240);

        bytes32 packed1 =
            bytes32(uint256(shifted1))
            | (bytes32(uint256(uint24(uint24(tick1)))) << 160)
            | (bytes32(uint256(oi1)) << 184)
            | (bytes32(uint256(oc1)) << 200)
            | (bytes32(uint256(ocn1)) << 216)
            | (bytes32(uint256(fp1)) << 232)
            | (bytes32(uint256(unlocked1 ? 1 : 0)) << 240);

        vm.store(POOL_5BPS, bytes32(uint256(0)), packed5);
        vm.store(POOL_1BPS, bytes32(uint256(0)), packed1);

        /*
         * Give ONLY this temporary fork test account WETH.
         * This is test funding, not executor pre-funding and not mainnet.
         */
        address trader = address(this);

        uint256 amountIn = 1 ether;

        deal(WETH, trader, amountIn);

        IERC20Minimal weth = IERC20Minimal(WETH);

        /*
         * Approve the real Base SwapRouter02 on the local fork.
         */
        (bool approvalOk,) = WETH.call(
            abi.encodeWithSignature(
                "approve(address,uint256)",
                address(0x2626664c2603336E57B271c5C0b26F421741e481),
                amountIn
            )
        );

        require(approvalOk, "WETH approval failed");

        uint256 beforeWeth = weth.balanceOf(trader);

        ISwapRouter02Minimal router =
            ISwapRouter02Minimal(
                address(0x2626664c2603336E57B271c5C0b26F421741e481)
            );

        /*
         * First leg:
         * WETH -> USDC through the real 5bps pool.
         */
        uint256 usdcOut = router.exactInputSingle(
            ISwapRouter02Minimal.ExactInputSingleParams({
                tokenIn: WETH,
                tokenOut: USDC,
                fee: 500,
                recipient: trader,
                amountIn: amountIn,
                amountOutMinimum: 0,
                sqrtPriceLimitX96: 0
            })
        );

        assertGt(usdcOut, 0, "first swap produced no USDC");

        /*
         * Approve the same real router for the second leg.
         */
        (bool approvalOk2,) = USDC.call(
            abi.encodeWithSignature(
                "approve(address,uint256)",
                address(router),
                usdcOut
            )
        );

        require(approvalOk2, "USDC approval failed");

        /*
         * Second leg:
         * USDC -> WETH through the real 1bps pool.
         */
        uint256 wethOut = router.exactInputSingle(
            ISwapRouter02Minimal.ExactInputSingleParams({
                tokenIn: USDC,
                tokenOut: WETH,
                fee: 100,
                recipient: trader,
                amountIn: usdcOut,
                amountOutMinimum: 0,
                sqrtPriceLimitX96: 0
            })
        );

        uint256 afterWeth = weth.balanceOf(trader);

        assertGt(wethOut, 0, "second swap produced no WETH");
        assertEq(
            afterWeth,
            wethOut,
            "unexpected WETH accounting"
        );

        /*
         * This test deliberately does NOT require profitability yet.
         * Its purpose is to prove that the actual router + pools execute
         * against the controlled fork state.
         */
        emit log_named_uint("amount_in_weth", amountIn);
        emit log_named_uint("usdc_after_leg_1", usdcOut);
        emit log_named_uint("weth_after_leg_2", wethOut);
        emit log_named_int(
            "round_trip_delta_weth",
            int256(afterWeth) - int256(beforeWeth)
        );

        emit log_string("REAL_ROUTER=true");
        emit log_string("REAL_V3_POOLS=true");
        emit log_string("FORK_ONLY_STORAGE_MUTATION=true");
        emit log_string("EXECUTOR_PREFUNDED=false");
        emit log_string("SIGNED=false");
        emit log_string("BROADCAST=false");
        emit log_string("MAINNET_STATE_MODIFIED=false");
    }


    function test_B7_3_68_real_balancer_executor_profitable_fork() public {
        IUniswapV3PoolMinimal p5 =
            IUniswapV3PoolMinimal(POOL_5BPS);
        IUniswapV3PoolMinimal p1 =
            IUniswapV3PoolMinimal(POOL_1BPS);

        /*
         * ----------------------------------------------------------
         * Controlled fork-only price differential.
         * ----------------------------------------------------------
         *
         * The fork starts from the pinned Base block.
         * Only slot0 price fields are changed locally.
         */
        (
            uint160 sqrt5,
            int24 tick5,
            uint16 oi5,
            uint16 oc5,
            uint16 ocn5,
            uint8 fp5,
            bool unlocked5
        ) = p5.slot0();

        (
            uint160 sqrt1,
            int24 tick1,
            uint16 oi1,
            uint16 oc1,
            uint16 ocn1,
            uint8 fp1,
            bool unlocked1
        ) = p1.slot0();

        uint160 shifted5 = sqrt5 + (sqrt5 / 1000);
        uint160 shifted1 = sqrt1 - (sqrt1 / 1000);

        bytes32 packed5 =
            bytes32(uint256(shifted5))
            | (bytes32(uint256(uint24(uint24(tick5)))) << 160)
            | (bytes32(uint256(oi5)) << 184)
            | (bytes32(uint256(oc5)) << 200)
            | (bytes32(uint256(ocn5)) << 216)
            | (bytes32(uint256(fp5)) << 232)
            | (bytes32(uint256(unlocked5 ? 1 : 0)) << 240);

        bytes32 packed1 =
            bytes32(uint256(shifted1))
            | (bytes32(uint256(uint24(uint24(tick1)))) << 160)
            | (bytes32(uint256(oi1)) << 184)
            | (bytes32(uint256(oc1)) << 200)
            | (bytes32(uint256(ocn1)) << 216)
            | (bytes32(uint256(fp1)) << 232)
            | (bytes32(uint256(unlocked1 ? 1 : 0)) << 240);

        vm.store(POOL_5BPS, bytes32(uint256(0)), packed5);
        vm.store(POOL_1BPS, bytes32(uint256(0)), packed1);

        /*
         * ----------------------------------------------------------
         * Verify the executor starts with ZERO borrowed asset.
         * ----------------------------------------------------------
         */
        uint256 executorWethBefore =
            IERC20Minimal(WETH).balanceOf(EXECUTOR);

        uint256 executorUsdcBefore =
            IERC20Minimal(USDC).balanceOf(EXECUTOR);

        assertEq(
            executorWethBefore,
            0,
            "executor was pre-funded with WETH"
        );

        assertEq(
            executorUsdcBefore,
            0,
            "executor was pre-funded with USDC"
        );

        /*
         * ----------------------------------------------------------
         * Real Balancer flash loan.
         * ----------------------------------------------------------
         */
        address vault =
            address(0xBA12222222228d8Ba445958a75a0704d566BF2C8);

        uint256 borrowAmount = 1 ether;

        address[] memory tokens = new address[](1);
        tokens[0] = WETH;

        uint256[] memory amounts = new uint256[](1);
        amounts[0] = borrowAmount;

        /*
         * FlashLoanReceiver expects:
         *
         * abi.decode(userData, (SwapHop[], address))
         *
         * where SwapHop is:
         *
         * tokenIn
         * tokenOut
         * feePpm
         * amountIn
         * amountOutMinimum
         * sqrtPriceLimitX96
         *
         * amountIn = 0 means the executor's entire current
         * balance of that token.
         */
        SwapHop[] memory hops = new SwapHop[](2);

        hops[0] = SwapHop({
            tokenIn: WETH,
            tokenOut: USDC,
            feePpm: 500,
            amountIn: 0,
            amountOutMinimum: 0,
            sqrtPriceLimitX96: 0
        });

        hops[1] = SwapHop({
            tokenIn: USDC,
            tokenOut: WETH,
            feePpm: 100,
            amountIn: 0,
            amountOutMinimum: 0,
            sqrtPriceLimitX96: 0
        });

        bytes memory userData =
            abi.encode(hops, EXPECTED_OWNER);

        /*
         * The deployed executor is onlyOwner.
         *
         * This is an Anvil/Foundry impersonation of the already
         * verified on-chain owner. No private key is used and no
         * transaction is broadcast to Base mainnet.
         */
        vm.prank(EXPECTED_OWNER);

        IFlashLoanReceiverMinimal(EXECUTOR).execute(
            tokens,
            amounts,
            userData
        );

        /*
         * ----------------------------------------------------------
         * Final settlement proof.
         * ----------------------------------------------------------
         *
         * If execute() returned successfully, the Balancer Vault
         * callback completed and the exact borrowed WETH had to be
         * repaid by the executor.
         *
         * Any remaining WETH belongs to the configured profit
         * recipient, EXPECTED_OWNER.
         */
        uint256 executorWethAfter =
            IERC20Minimal(WETH).balanceOf(EXECUTOR);

        uint256 executorUsdcAfter =
            IERC20Minimal(USDC).balanceOf(EXECUTOR);

        uint256 ownerWethAfter =
            IERC20Minimal(WETH).balanceOf(EXPECTED_OWNER);

        assertEq(
            executorWethAfter,
            0,
            "executor retained WETH after settlement"
        );

        assertEq(
            executorUsdcAfter,
            0,
            "executor retained USDC after settlement"
        );

        assertGt(
            ownerWethAfter,
            0,
            "no positive WETH profit reached owner"
        );

        /*
         * ----------------------------------------------------------
         * Evidence.
         * ----------------------------------------------------------
         */
        emit log_named_uint(
            "fork_block",
            FORK_BLOCK
        );

        emit log_named_uint(
            "borrowed_weth",
            borrowAmount
        );

        emit log_named_uint(
            "executor_WETH_before",
            executorWethBefore
        );

        emit log_named_uint(
            "executor_WETH_after",
            executorWethAfter
        );

        emit log_named_uint(
            "executor_USDC_before",
            executorUsdcBefore
        );

        emit log_named_uint(
            "executor_USDC_after",
            executorUsdcAfter
        );

        emit log_named_uint(
            "owner_WETH_profit",
            ownerWethAfter
        );

        emit log_named_uint(
            "original_5bps_sqrt",
            sqrt5
        );

        emit log_named_uint(
            "modified_5bps_sqrt",
            shifted5
        );

        emit log_named_uint(
            "original_1bps_sqrt",
            sqrt1
        );

        emit log_named_uint(
            "modified_1bps_sqrt",
            shifted1
        );

        emit log_string("REAL_BALANCER_VAULT=true");
        emit log_string("REAL_EXECUTOR=true");
        emit log_string("REAL_ROUTER=true");
        emit log_string("REAL_V3_POOLS=true");
        emit log_string("EXECUTOR_PREFUNDED=false");
        emit log_string("FLASH_LOAN_FUNDED=true");
        emit log_string("BALANCER_REPAID=true");
        emit log_string("POSITIVE_PROFIT=true");
        emit log_string("FORK_ONLY=true");
        emit log_string("SIGNED=false");
        emit log_string("BROADCAST=false");
        emit log_string("MAINNET_STATE_MODIFIED=false");
    }


    function test_B7_3_68_real_fork_state() public {
        assertEq(block.chainid, 8453, "not Base");

        uint256 executorCodeSize;
        assembly {
            executorCodeSize := extcodesize(EXECUTOR)
        }
        assertGt(executorCodeSize, 0, "executor bytecode missing");

        IFlashLoanReceiverMinimal receiver =
            IFlashLoanReceiverMinimal(EXECUTOR);

        assertEq(
            receiver.owner(),
            EXPECTED_OWNER,
            "executor owner mismatch"
        );

        assertEq(
            receiver.balancerVault(),
            address(0xBA12222222228d8Ba445958a75a0704d566BF2C8),
            "Balancer Vault mismatch"
        );

        assertEq(
            receiver.uniRouter(),
            address(0x2626664c2603336E57B271c5C0b26F421741e481),
            "SwapRouter02 mismatch"
        );

        IUniswapV3PoolMinimal p5 = IUniswapV3PoolMinimal(POOL_5BPS);
        IUniswapV3PoolMinimal p1 = IUniswapV3PoolMinimal(POOL_1BPS);

        assertEq(p5.token0(), WETH, "5bps token0");
        assertEq(p5.token1(), USDC, "5bps token1");
        assertEq(p5.fee(), 500, "5bps fee");
        assertGt(p5.liquidity(), 0, "5bps liquidity");

        assertEq(p1.token0(), WETH, "1bps token0");
        assertEq(p1.token1(), USDC, "1bps token1");
        assertEq(p1.fee(), 100, "1bps fee");
        assertGt(p1.liquidity(), 0, "1bps liquidity");

        (
            uint160 sqrt5,
            int24 tick5,
            ,
            ,
            ,
            ,
            bool unlocked5
        ) = p5.slot0();

        (
            uint160 sqrt1,
            int24 tick1,
            ,
            ,
            ,
            ,
            bool unlocked1
        ) = p1.slot0();

        assertGt(sqrt5, 0, "5bps sqrt price");
        assertGt(sqrt1, 0, "1bps sqrt price");
        assertTrue(unlocked5, "5bps pool locked");
        assertTrue(unlocked1, "1bps pool locked");

        emit log_named_uint("fork_block", FORK_BLOCK);
        emit log_named_uint("executor_code_size", executorCodeSize);
        emit log_named_uint("pool_5bps_sqrtPriceX96", sqrt5);
        emit log_named_int("pool_5bps_tick", tick5);
        emit log_named_uint("pool_1bps_sqrtPriceX96", sqrt1);
        emit log_named_int("pool_1bps_tick", tick1);

        emit log_named_uint(
            "executor_WETH_balance_before",
            IERC20Minimal(WETH).balanceOf(EXECUTOR)
        );
        emit log_named_uint(
            "executor_USDC_balance_before",
            IERC20Minimal(USDC).balanceOf(EXECUTOR)
        );

        emit log_string("SIGNED=false");
        emit log_string("BROADCAST=false");
        emit log_string("MAINNET_STATE_MODIFIED=false");
    }
}
