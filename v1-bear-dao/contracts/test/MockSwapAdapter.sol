// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "../interfaces/ISwapAdapter.sol";

/// @dev Mock swap adapter that simulates swaps at a fixed rate for testing.
///      1 USDC (6 dec) = 0.0004 PAXG (18 dec) → gold at ~$2500/oz
///      1 WETH (18 dec) = 1.0 PAXG (18 dec)   → simplified 1:1
contract MockSwapAdapter is ISwapAdapter {
    using SafeERC20 for IERC20;

    address public paxg;
    address public usdc;
    address public weth;

    // Configurable rate: paxgOut per 1e6 USDC (in PAXG 18-decimal units)
    uint256 public usdcToPaxgRate = 0.0004e18; // 0.0004 PAXG per USDC
    uint256 public wethToPaxgRate = 1e18; // 1:1

    constructor(address _paxg, address _usdc, address _weth) {
        paxg = _paxg;
        usdc = _usdc;
        weth = _weth;
    }

    function swapExactInput(
        address tokenIn,
        address /* tokenOut */,
        uint256 amountIn,
        uint256 amountOutMinimum,
        bytes calldata /* path */
    ) external override returns (uint256 amountOut) {
        // Pull input tokens
        IERC20(tokenIn).safeTransferFrom(msg.sender, address(this), amountIn);

        // Calculate output
        if (tokenIn == usdc) {
            amountOut = (amountIn * usdcToPaxgRate) / 1e6;
        } else if (tokenIn == weth) {
            amountOut = (amountIn * wethToPaxgRate) / 1e18;
        } else if (tokenIn == paxg) {
            // Reverse swap: PAXG → USDC
            amountOut = (amountIn * 1e6) / usdcToPaxgRate;
        } else {
            revert("Unknown token");
        }

        require(amountOut >= amountOutMinimum, "Insufficient output");

        // Mint output tokens (mock adapter has infinite liquidity)
        // We need the mock PAXG to have a mint function
        (bool success, ) = paxg.call(
            abi.encodeWithSignature("mint(address,uint256)", msg.sender, amountOut)
        );
        require(success, "Mint failed");
    }

    function setRates(uint256 _usdcRate, uint256 _wethRate) external {
        usdcToPaxgRate = _usdcRate;
        wethToPaxgRate = _wethRate;
    }
}
